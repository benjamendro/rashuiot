"""
eshkol_matcher.py — Reusable double-key (code + name) matcher for Eshkol entities.

Implements the rules from docs/eshkol_matching_skill.md:
  1. Exact match
  2. Sanitization (strip quotes/geresh/gershayim/brackets, unify hyphen->space)
  3. Manual / hardcoded mapping  -> supplied by the config table itself
  4. Fuzzy match, cutoff >= 0.85 (difflib)

Core principle (skill §3.3): CBS regional-council codes can collide with
locality codes. Therefore we NEVER trust a code alone — every match is
cross-validated on BOTH the code AND the name. Any code that resolves to an
Eshkol target but whose name disagrees is reported as a HARD error so the
caller can HALT (skill §1).

Single source of truth: config/eshkol_mapping.xlsx  (the צימודים table).
Adding a cluster = adding rows there. No code changes.
"""

import os
import re
import difflib
import pandas as pd

FUZZY_CUTOFF = 0.85  # skill §2.4 — never below this

# Hebrew column header  ->  internal field name
_COL_MAP = {
    'שם ברשימת אשכול': 'eshkol_name',
    'סוג ישות':        'entity_type',   # רשות / יישוב
    'קבוצה/שיוך':       'affiliation',   # cluster (for רשות) or parent RC name (for יישוב)
    'קוד למס (סמל)':    'code',
    'שם רשמי בלמס':     'official_name',
    'שיטת התאמה':       'method',
}


def _default_mapping_path():
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (
        os.path.join(here, 'eshkol_mapping.xlsx'),            # standalone skill folder
        os.path.join(here, '..', 'data', 'config', 'eshkol_mapping.xlsx'),  # repo layout (etl/)
        os.path.join(here, '..', 'config', 'eshkol_mapping.xlsx'),
        os.path.join(here, 'config', 'eshkol_mapping.xlsx'),
    ):
        if os.path.exists(cand):
            return os.path.abspath(cand)
    return None


def sanitize(name):
    """Normalize a Hebrew authority/settlement name for comparison.

    Removes quote marks (ascii/Hebrew/curly), drops bracket characters while
    KEEPING their inner text, unifies hyphen/dash -> space, collapses runs of
    whitespace. Order-preserving; does not strip the definite article.
    """
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ''
    s = str(name).strip()
    s = re.sub(r'["\'׳״‘’“”`]', '', s)  # quotes / geresh / gershayim
    s = re.sub(r'[()\[\]{}]', ' ', s)                                 # brackets -> space (keep content)
    s = re.sub(r'[\-‐-―]', ' ', s)                          # hyphen/dash family -> space
    s = re.sub(r'\s+', ' ', s).strip()
    return s


class EshkolMatcher:
    def __init__(self, mapping_path=None):
        self.mapping_path = mapping_path or _default_mapping_path()
        if not self.mapping_path or not os.path.exists(self.mapping_path):
            raise FileNotFoundError(
                "Eshkol mapping table not found. Pass mapping_path or place it at "
                "config/eshkol_mapping.xlsx"
            )
        df = pd.read_excel(self.mapping_path)
        missing = [h for h in _COL_MAP if h not in df.columns]
        if missing:
            raise ValueError(f"Mapping table missing expected columns: {missing}")
        df = df.rename(columns=_COL_MAP)[list(_COL_MAP.values())].copy()
        df['code'] = pd.to_numeric(df['code'], errors='coerce').astype('Int64')
        df = df.dropna(subset=['code'])

        dup = df['code'][df['code'].duplicated()].tolist()
        if dup:
            raise ValueError(f"Duplicate codes in mapping table (must be unique): {dup}")

        self.targets = df.reset_index(drop=True)

        # Lookups
        self.by_code = {int(r['code']): r.to_dict() for _, r in self.targets.iterrows()}
        # normalized accepted names -> code  (both eshkol + official variants)
        self._name_to_code = {}
        self._accepted = {}  # code -> set(normalized names)
        for code, rec in self.by_code.items():
            variants = {sanitize(rec['eshkol_name']), sanitize(rec['official_name'])}
            variants.discard('')
            self._accepted[code] = variants
            for v in variants:
                self._name_to_code.setdefault(v, set()).add(code)
        self._all_norm_names = list(self._name_to_code.keys())

    # ---- introspection helpers (used by the ETL) ----
    def target_codes(self, entity_type=None, affiliation=None):
        df = self.targets
        if entity_type is not None:
            df = df[df['entity_type'] == entity_type]
        if affiliation is not None:
            df = df[df['affiliation'] == affiliation]
        return [int(c) for c in df['code'].tolist()]

    def name_for(self, code):
        rec = self.by_code.get(int(code))
        return rec['eshkol_name'] if rec else None

    # ---- name<->code resolution ----
    def _name_matches_code(self, name, code):
        """Return (ok, how) for whether `name` is an acceptable label for `code`."""
        accepted = self._accepted.get(int(code))
        if not accepted:
            return False, 'code_not_target'
        n = sanitize(name)
        if n == '':
            return False, 'empty_name'
        if n in accepted:
            return True, 'exact_or_sanitized'
        hit = difflib.get_close_matches(n, list(accepted), n=1, cutoff=FUZZY_CUTOFF)
        if hit:
            ratio = difflib.SequenceMatcher(None, n, hit[0]).ratio()
            return True, f'fuzzy_{ratio:.2f}'
        return False, 'name_mismatch'

    def match_dataframe(self, df, name_col, code_col=None):
        """Match a source dataframe against the Eshkol target list.

        Returns (result_df, errors).
          result_df : df + columns matched(bool), match_code, match_eshkol_name,
                      match_status. Only rows resolving to an Eshkol target are
                      flagged matched=True.
          errors    : list of dicts. issue ∈
                      {'code_name_mismatch'  (HARD — possible code collision),
                       'ambiguous_name', 'name_only_no_code'}
        """
        out = df.copy()
        matched, mcode, mname, status = [], [], [], []
        errors = []
        for idx, row in df.iterrows():
            raw_name = row.get(name_col)
            raw_code = row.get(code_col) if code_col else None
            code = pd.to_numeric(raw_code, errors='coerce') if code_col else None
            is_match, tcode, tstatus = False, None, 'out_of_scope'

            if code is not None and pd.notna(code):
                c = int(code)
                if c in self.by_code:
                    ok, how = self._name_matches_code(raw_name, c)
                    if ok:
                        is_match, tcode, tstatus = True, c, how
                    else:
                        tstatus = 'code_name_mismatch'
                        errors.append({
                            'row': idx, 'source_name': raw_name, 'source_code': c,
                            'issue': 'code_name_mismatch',
                            'detail': f"code {c} is Eshkol '{self.by_code[c]['eshkol_name']}' "
                                      f"but source name '{raw_name}' does not match",
                        })
                # code not in targets -> genuinely out of scope, not an error
            else:
                # No code: name-only fallback (weaker; cannot cross-validate)
                n = sanitize(raw_name)
                hits = self._name_to_code.get(n)
                if not hits:
                    close = difflib.get_close_matches(n, self._all_norm_names, n=1, cutoff=FUZZY_CUTOFF)
                    if close:
                        hits = self._name_to_code.get(close[0])
                if hits and len(hits) == 1:
                    c = next(iter(hits))
                    is_match, tcode, tstatus = True, c, 'name_only'
                    errors.append({
                        'row': idx, 'source_name': raw_name, 'source_code': None,
                        'issue': 'name_only_no_code',
                        'detail': f"matched '{raw_name}' to code {c} by name alone (no code to cross-check)",
                    })
                elif hits and len(hits) > 1:
                    errors.append({
                        'row': idx, 'source_name': raw_name, 'source_code': None,
                        'issue': 'ambiguous_name',
                        'detail': f"name '{raw_name}' maps to multiple codes {sorted(hits)}",
                    })

            matched.append(is_match)
            mcode.append(tcode)
            mname.append(self.by_code[tcode]['eshkol_name'] if tcode else None)
            status.append(tstatus)

        out['matched'] = matched
        out['match_code'] = mcode
        out['match_eshkol_name'] = mname
        out['match_status'] = status
        return out, errors

    def verify_targets_present(self, found_codes, entity_type=None, affiliation=None):
        """Which expected target codes were NOT found in `found_codes`.

        Returns a list of dicts {code, eshkol_name, entity_type, affiliation}.
        The caller decides whether a given absence is fatal (e.g. RCs legitimately
        miss the localities file; small settlements miss the 2,000+ estimates).
        """
        found = {int(c) for c in found_codes if pd.notna(c)}
        missing = []
        for code in self.target_codes(entity_type=entity_type, affiliation=affiliation):
            if code not in found:
                rec = self.by_code[code]
                missing.append({
                    'code': code, 'eshkol_name': rec['eshkol_name'],
                    'entity_type': rec['entity_type'], 'affiliation': rec['affiliation'],
                })
        return missing


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    m = EshkolMatcher()
    print(f"Loaded mapping: {m.mapping_path}")
    print(f"Targets: {len(m.targets)}  "
          f"(רשות={len(m.target_codes(entity_type='רשות'))}, "
          f"יישוב={len(m.target_codes(entity_type='יישוב'))})")
    # self-checks
    assert m._name_matches_code('פקיעין (בוקייעה)', 536)[0]      # bracketed
    assert m._name_matches_code('מעלות-תרשיחא', 1063)[0]          # hyphen
    assert m._name_matches_code('הגליל העליון', 5501)[0]          # definite article RC
    assert m._name_matches_code('גליל עליון', 5501)[0]            # eshkol variant
    assert not m._name_matches_code('תל אביב', 5501)[0]           # wrong name -> reject
    print("Self-checks passed.")

"""Stage 0 - input validation and the Eshkol matching gate.

* Every Excel file in the repo must be configured or explicitly excluded.
* The year printed inside a file must equal the year it is configured as
  (this is how p_libud_2019.xlsx was found to be the 2022 file).
* No two files may carry the same numeric content.
* Eshkol gate (eshkol-matching/SKILL.md §1, §3): every Eshkol authority must be found
  in every year by code AND name; any code/name mismatch halts the pipeline.
"""

import collections
import glob
import hashlib
import os
import re

import pandas as pd

from .common import clean_text, parse_value
from .extract import read_grid
from .matching import EshkolMatcher

_YEAR_PATTERNS = [r'רשויות מקומיות\s+((?:19|20)\d{2})', r'שנת עדכון:\s*((?:19|20)\d{2})',
                  r'סמל הרשות\s+((?:19|20)\d{2})', r'לשנת\s+((?:19|20)\d{2})']


class GateError(RuntimeError):
    """Raised when the pipeline must stop for a human decision."""


def _physical_sheet(path):
    sheets = pd.ExcelFile(path).sheet_names
    return next(s for s in sheets if s.startswith('נתונים פיזיים'))


def detect_title_year(path):
    """Most common year mentioned in the title/header rows of the physical sheet."""
    rows, _ = read_grid(path, _physical_sheet(path))
    years = collections.Counter()
    for r in rows[:4]:
        for v in r:
            t = clean_text(v)
            for pat in _YEAR_PATTERNS:
                years.update(re.findall(pat, t))
    return int(years.most_common(1)[0][0]) if years else None


def numeric_fingerprint(path):
    """Hash of the multiset of numeric cells of the physical sheet (layout-independent)."""
    rows, _ = read_grid(path, _physical_sheet(path))
    vals = []
    for r in rows:
        for v in r:
            num, _, _ = parse_value(v)
            if num is not None:
                vals.append(f'{num:.6g}')
    return hashlib.sha1('|'.join(sorted(vals)).encode()).hexdigest()[:12], len(vals)


def validate_files(cfg, root):
    """Return a DataFrame describing every Excel file and whether it is usable."""
    configured = {y['file']: year for year, y in cfg['years'].items()}
    excluded = {e['file']: e['reason'] for e in cfg.get('excluded', [])}
    recs = []
    for path in sorted(glob.glob(os.path.join(root, '*.xls*'))):
        f = os.path.basename(path)
        title_year = detect_title_year(path)
        fp, n = numeric_fingerprint(path)
        recs.append({'file': f, 'configured_year': configured.get(f), 'title_year': title_year,
                     'fingerprint': fp, 'n_numeric_cells': n,
                     'status': 'use' if f in configured else ('excluded' if f in excluded else 'UNCONFIGURED'),
                     'note': excluded.get(f, '')})
    df = pd.DataFrame(recs)
    problems = []
    for _, r in df.iterrows():
        if r.status == 'UNCONFIGURED':
            problems.append(f"{r.file}: not in sources.yaml (add it or exclude it)")
        if r.status == 'use' and r.title_year != r.configured_year:
            problems.append(f"{r.file}: configured as {r.configured_year} but its title says {r.title_year}")
    dup = df[df.duplicated('fingerprint', keep=False)].groupby('fingerprint').file.apply(list)
    for fp, files in dup.items():
        used = [f for f in files if f in configured]
        if len(used) > 1:
            problems.append(f"identical content in {used}")
        df.loc[df.fingerprint == fp, 'duplicate_of'] = ', '.join(files)
    return df, problems


def eshkol_gate(registry, matcher=None):
    """Cross-check every year's authority list against eshkol_mapping.xlsx.

    Returns (report DataFrame, problems list). Problems mean HALT.
    """
    matcher = matcher or EshkolMatcher()
    targets = matcher.targets[matcher.targets['entity_type'] == 'רשות']
    recs, problems = [], []
    for year, reg in registry.groupby('year'):
        res, errors = matcher.match_dataframe(reg, name_col='name', code_col='muni_code')
        for e in errors:
            if e['issue'] == 'code_name_mismatch':
                problems.append(f"{year}: {e['detail']}")
        found = res[res['matched']]
        missing = matcher.verify_targets_present(found['match_code'], entity_type='רשות')
        for m in missing:
            problems.append(f"{year}: Eshkol authority {m['eshkol_name']} ({m['code']}) not found")
        for _, t in targets.iterrows():
            hit = found[found['match_code'] == t['code']]
            recs.append({'year': year, 'eshkol_name': t['eshkol_name'], 'code': int(t['code']),
                         'cluster': t['affiliation'],
                         'source_name': hit['name'].iloc[0] if len(hit) else None,
                         'source_raw_code': int(hit['raw_code'].iloc[0]) if len(hit) else None,
                         'match_status': hit['match_status'].iloc[0] if len(hit) else 'MISSING'})
    return pd.DataFrame(recs), problems

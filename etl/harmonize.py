"""Stage 2 - Harmonize columns across years into one indicator catalogue (DRAFT).

Each (year, sheet, column) is matched to an indicator, newest year first, so every
indicator is anchored to its most recent CBS label. Match methods, strongest first:

  exact         same normalized label path (period tokens removed)
  unit_variant  same path once unit words are removed -> listed in units_review
  leaf          same last two levels (group/category renamed)
  tokens        same words in another order/nesting (pre-2017 flat labels)
  fuzzy         similarity >= 0.85 (eshkol SKILL cutoff) -> needs human review
  new           no counterpart in a newer year

An indicator takes at most one column per (file year, sheet part, data period): the
pre-2017 files carry two data years of some measures (e.g. arnona 2013 and 2014 in the
2014 file); both belong to the same indicator, distinguished by data_period.

Units are NOT converted here. units_review lists every indicator whose unit label or
value scale changes between years, for a human decision before stage 2b applies it.
"""

import difflib
import hashlib
import math
import re

import numpy as np
import pandas as pd

from .common import extract_period, norm_label, strip_period

FUZZY_CUTOFF = 0.85
DOMAIN_GROUP = {'physical': 'physical', 'landuse': 'physical', 'budget': 'budget'}

# Unit words CBS writes in labels, in parentheses, after " - ב..." or as a sub-header.
_UNIT_TERMS = [
    'אלפי ש"ח', 'אלפי ₪', 'ש"ח', '₪', 'אלפים', 'אלפי מ"ק', 'מ"ק לנפש', 'מ"ק', 'אלפי מ"ר',
    'מ"ר', 'קמ"ר', 'ק"מ', 'ק"ג ליום לנפש', 'אחוזים', 'אחוז', '%', 'שנים', 'נפשות לקמ"ר',
    'מספרים מוחלטים', 'מספר',
]
_UNIT_ALT = '|'.join(re.escape(u) for u in sorted(_UNIT_TERMS, key=len, reverse=True))
_UNIT_PAREN_RE = re.compile(rf'\(\s*(?:שטח\s+)?ב?({_UNIT_ALT})\s*\)')
_UNIT_SUFFIX_RE = re.compile(rf'\s*-\s*(?:שטח\s+)?ב({_UNIT_ALT})\s*$')
_UNIT_LEVEL_RE = re.compile(rf'^(?:שטח\s+)?ב?({_UNIT_ALT})$')
_UNIT_TRAIL_RE = re.compile(r'\s+(אלפים)$')                 # 'סך הכל אלפים'
UNIT_SYNONYMS = {'₪': 'ש"ח', 'אלפי ₪': 'אלפי ש"ח', 'אחוזים': 'אחוז', '%': 'אחוז'}
SAMPLE_AUTHORITY = (8000, 'צפת')        # shown in units_review to make scales tangible


def split_unit(label):
    """'צריכת מים (אלפי מ"ק)' -> ('צריכת מים', 'אלפי מ"ק')."""
    units = []
    for rx in (_UNIT_PAREN_RE, _UNIT_SUFFIX_RE, _UNIT_TRAIL_RE):
        units += rx.findall(label)
        label = rx.sub(' ', label)
    return re.sub(r'\s+', ' ', label).strip(' -'), units


_SYNONYMS = None


def load_synonyms(path=None):
    """[(compiled regex, replacement)] from config/label_synonyms.yaml (cached)."""
    global _SYNONYMS
    if _SYNONYMS is None or path:
        import os
        import yaml
        path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config',
                                    'label_synonyms.yaml')
        with open(path, encoding='utf-8') as f:
            _SYNONYMS = [(re.compile(p), r) for p, r in (yaml.safe_load(f) or [])]
    return _SYNONYMS


def apply_synonyms(level):
    out = level
    for rx, rep in load_synonyms():
        out = rx.sub(rep, out)
    out = re.sub(r'\s+', ' ', out).strip()
    return out, out != level


def describe_column(levels_str, period_row_label, sheet_data_period, year):
    """Normalized keys, unit hint and data period for one column."""
    raw_levels = [lv for lv in levels_str.split(' › ') if lv] if levels_str else []
    flat_label = len(raw_levels) == 1
    if flat_label:
        # pre-2017 flat labels use ' - ' between levels: 'בתי ספר - סה"כ תשע"ה 2014/15'
        raw_levels = [p for p in norm_label(raw_levels[0]).split(' - ') if p]
    periods = [extract_period(lv) for lv in raw_levels]
    levels, base, units = [], [], []
    synonym = False
    raw_key = []                                # key before synonyms, to locate bridges
    for lv in raw_levels:
        pre = norm_label(strip_period(lv))
        if pre:
            raw_key.append(pre)
        n, changed = apply_synonyms(pre)
        synonym = synonym or changed
        if not n:
            continue
        levels.append(n)
        m = _UNIT_LEVEL_RE.match(n)
        if m:                                   # the whole level is a unit word
            units.append(m.group(1))
            continue
        b, u = split_unit(n)
        units += u
        if b:
            base.append(b)
    if period_row_label:
        period, src = period_row_label, 'period_row'
    elif any(periods):
        period, src = ' '.join(p for p in periods if p), 'label'
    elif sheet_data_period:
        period, src = str(sheet_data_period), 'sheet'
    else:
        period, src = str(year), 'file_default'
    return {
        'key': ' › '.join(levels),
        'key_raw': ' › '.join(raw_key),
        'base_key': ' › '.join(base),
        'leaf_key': ' › '.join(levels[-2:]),
        'flat': ' '.join(levels),
        # the first level of a multi-row header is a category; of a flat label it is not
        'flat_no_top': ' '.join(levels[1:]) if len(levels) > 1 and not flat_label else ' '.join(levels),
        'unit_hint': ' / '.join(dict.fromkeys(UNIT_SYNONYMS.get(u, u) for u in units)),
        'data_period': period,
        'period_source': src,
        'synonym_applied': synonym,
    }


def _tokens(s):
    return sorted(t for t in re.findall(r'[^\s,()›:]+', s) if t != '-')


def _similarity(a, b):
    ta, tb = ' '.join(_tokens(a)), ' '.join(_tokens(b))
    sm = difflib.SequenceMatcher(None, ta, tb)
    if sm.real_quick_ratio() < FUZZY_CUTOFF or sm.quick_ratio() < FUZZY_CUTOFF:
        return 0.0
    return sm.ratio()


class Indicator:
    __slots__ = ('id', 'group', 'label', 'keys', 'base_keys', 'leaf_keys', 'flats', 'token_sets',
                 'slots', 'year_parts', 'ref')

    def __init__(self, iid, group, col):
        self.id, self.group, self.label = iid, group, col['levels']
        self.keys, self.base_keys, self.leaf_keys = set(), set(), set()
        self.flats, self.token_sets, self.slots, self.year_parts = [], set(), set(), set()
        self.absorb(col)

    def absorb(self, col):
        self.keys.add(col['key'])
        if col['base_key']:
            self.base_keys.add(col['base_key'])
        self.leaf_keys.add(col['leaf_key'])
        for f in (col['flat'], col['flat_no_top']):
            self.flats.append(f)
            self.token_sets.add(tuple(_tokens(f)))
        self.slots.add(_slot(col))
        self.year_parts.add((col['year'], col['part']))
        # years run newest first, so the last absorbed column is the nearest in time to
        # the year being matched next: the data guard compares against it
        self.ref = (col['year'], col['sheet'], col['col'])


def stable_id(group, key):
    """Indicator id derived from its anchor label, so ids survive re-runs."""
    return f"{group[0].upper()}{hashlib.sha1(f'{group}|{key}'.encode()).hexdigest()[:6]}"


def load_overrides(path):
    """Manual decisions: force a source column onto an indicator (or 'NEW')."""
    try:
        ov = pd.read_csv(path, dtype={'indicator_id': str}, comment='#')
    except FileNotFoundError:
        return {}
    return {(int(r.year), r.sheet, int(r.col)): r.indicator_id.strip() for r in ov.itertuples()}


def _slot(col):
    return col['year'], col['part'], col['data_period']


# Data guard for label-similarity matches: a candidate is rejected when the values
# contradict it (Spearman rho over shared authorities against the indicator's column
# nearest in time). Templated CBS labels make text similarity alone unreliable, e.g.
# "מכוניות פרטיות - שיעור ל-1,000 תושבים" vs "שיעור פטירות מתוקנן ל-1,000 תושבים".
MIN_RHO = {'fuzzy': 0.3, 'leaf': 0.0, 'tokens': 0.0}
# Year-over-year change rates barely correlate between years by nature: no guard there.
_VOLATILE_RE = re.compile(r'שינוי|גידול|לעומת')


def _rho(a, b):
    if a is None or b is None:
        return None
    j = pd.concat([a, b], axis=1, keys=['a', 'b']).dropna()
    if len(j) < 10 or j['a'].nunique() < 2 or j['b'].nunique() < 2:
        return None
    r = j.rank()
    return float(r['a'].corr(r['b']))


def column_values(cells):
    """{(year, sheet, col): Series(muni_code -> value)} over authority rows."""
    a = cells[(cells['row_type'] == 'authority') & cells['value'].notna()]
    return {k: g.groupby('muni_code')['value'].first() for k, g in a.groupby(['year', 'sheet', 'col'])}


def match_columns(columns, overrides=None, values=None):
    """Assign indicator ids to all columns.

    Returns (column_map, indicators, warnings, guard_rejections). `values` (from
    column_values) enables the data guard on leaf / tokens / fuzzy matches.
    """
    overrides = overrides or {}
    values = values or {}
    warnings, rejected = [], []
    cols = columns.copy()
    desc = cols.apply(lambda r: describe_column(r['levels'], r['period_row_label'],
                                                r['sheet_data_period'], r['year']), axis=1)
    cols = pd.concat([cols.reset_index(drop=True), pd.DataFrame(list(desc))], axis=1)
    cols['group'] = cols['domain'].map(DOMAIN_GROUP)
    cols = cols[cols['key'] != ''].copy()

    indicators = []
    assign = {}                                   # col index -> (indicator, method, score)

    def free(ind, c, strict=False):
        # exact label matches may add another data period of the same year (arnona 2013
        # and 2014 in one file); weaker matches need the whole year to be free
        if ind.group != c['group']:
            return False
        return (c['year'], c['part']) not in ind.year_parts if strict else _slot(c) not in ind.slots

    def guard_ok(ind, c, method, score=None):
        if _VOLATILE_RE.search(c['levels']) or _VOLATILE_RE.search(ind.label):
            return True
        r = _rho(values.get((c['year'], c['sheet'], c['col'])), values.get(ind.ref))
        if r is not None and r < MIN_RHO[method]:
            rejected.append({'year': c['year'], 'sheet': c['sheet'], 'col': c['col'], 'label': c['levels'],
                             'candidate': ind.id, 'candidate_label': ind.label, 'method': method,
                             'score': score, 'rho': round(r, 3)})
            return False
        return True

    for year in sorted(cols['year'].unique(), reverse=True):
        ycols = cols[cols['year'] == year]
        for part in ycols['part'].unique():
            pending = ycols[ycols['part'] == part]
            by_id = {i.id: i for i in indicators}
            for idx, c in pending.iterrows():
                target = overrides.get((c['year'], c['sheet'], c['col']))
                if target is None or target == 'NEW':
                    continue
                if target in by_id and free(by_id[target], c):
                    assign[idx] = (by_id[target], 'override', 1.0)
                    by_id[target].absorb(c)
                else:
                    warnings.append(f"override {c['year']}/{c['sheet']}/{c['col']} -> {target}: "
                                    'target not found or slot taken')
            forced_new = {idx for idx, c in pending.iterrows()
                          if overrides.get((c['year'], c['sheet'], c['col'])) == 'NEW'}
            for idx in forced_new:
                c = pending.loc[idx]
                ind = Indicator(stable_id(c['group'], f"{c['key']}#{c['year']}#{c['col']}"), c['group'], c)
                indicators.append(ind)
                assign[idx] = (ind, 'override_new', None)
            # deterministic passes, strongest first
            for method, attr, src in [('exact', 'keys', 'key'), ('unit_variant', 'base_keys', 'base_key'),
                                      ('leaf', 'leaf_keys', 'leaf_key')]:
                strict = method == 'leaf'
                for idx, c in pending.iterrows():
                    if idx in assign or not c[src]:
                        continue
                    cands = [i for i in indicators if free(i, c, strict) and c[src] in getattr(i, attr)]
                    if strict:
                        cands = [i for i in cands if guard_ok(i, c, method)]
                    if len(cands) == 1:
                        assign[idx] = (cands[0], method, 1.0)
                        cands[0].absorb(c)
            for idx, c in pending.iterrows():
                if idx in assign:
                    continue
                ts = {tuple(_tokens(c['flat'])), tuple(_tokens(c['flat_no_top']))}
                cands = [i for i in indicators if free(i, c, True) and ts & i.token_sets]
                cands = [i for i in cands if guard_ok(i, c, 'tokens')]
                if len(cands) == 1:
                    assign[idx] = (cands[0], 'tokens', 1.0)
                    cands[0].absorb(c)
            # fuzzy: global greedy on best scores
            pairs = []
            for idx, c in pending.iterrows():
                if idx in assign:
                    continue
                for ind in indicators:
                    if not free(ind, c, True):
                        continue
                    s = max(_similarity(a, b) for a in (c['flat'], c['flat_no_top'])
                            for b in ind.flats[-4:])
                    if s >= FUZZY_CUTOFF:
                        pairs.append((s, idx, ind))
            for s, idx, ind in sorted(pairs, key=lambda t: -t[0]):
                c = cols.loc[idx]
                if idx in assign or not free(ind, c, True) or not guard_ok(ind, c, 'fuzzy', round(s, 3)):
                    continue
                assign[idx] = (ind, 'fuzzy', round(s, 3))
                ind.absorb(c)
            taken = {i.id for i in indicators}
            for idx, c in pending.iterrows():
                if idx in assign:
                    continue
                # a same-label column of another data period may have just been created
                same = [i for i in indicators if free(i, c) and c['key'] in i.keys]
                if len(same) == 1:
                    assign[idx] = (same[0], 'exact', 1.0)
                    same[0].absorb(c)
                    continue
                iid = stable_id(c['group'], c['key'])
                if iid in taken:              # same label twice in one sheet/period
                    iid = stable_id(c['group'], f"{c['key']}#{c['year']}#{c['col']}")
                taken.add(iid)
                ind = Indicator(iid, c['group'], c)
                indicators.append(ind)
                assign[idx] = (ind, 'new', None)

    cols['indicator_id'] = [assign[i][0].id for i in cols.index]
    cols['match_method'] = [assign[i][1] for i in cols.index]
    cols['match_score'] = [assign[i][2] for i in cols.index]
    cols['matched_to'] = [assign[i][0].label for i in cols.index]
    cols['review_needed'] = cols['match_method'].isin(['fuzzy', 'leaf', 'tokens'])
    return cols, indicators, warnings, pd.DataFrame(rejected)


def column_stats(cells):
    """Per-column value profile over authority rows (not summary rows)."""
    a = cells[cells['row_type'] == 'authority']
    g = a.groupby(['year', 'sheet', 'col'])
    stats = pd.DataFrame({
        'n_cells': g.size(),
        'n_numeric': g['value'].count(),
        'n_text': g['value_text'].count(),
        'n_dash': g['flag'].apply(lambda s: (s == 'dash').sum()),
        'n_not_available': g['flag'].apply(lambda s: (s == 'not_available').sum()),
        'n_low_reliability': g['flag'].apply(lambda s: (s == 'low_reliability').sum()),
        'median': g['value'].median(),
        'p10': g['value'].quantile(0.1),
        'p90': g['value'].quantile(0.9),
    }).reset_index()
    return stats


def _scale_ratio(cells_ind, y_new, y_old):
    """Median over authorities of value[y_new] / value[y_old] (robust scale check)."""
    a = cells_ind[cells_ind['year'] == y_new].groupby('muni_code')['value'].first()
    b = cells_ind[cells_ind['year'] == y_old].groupby('muni_code')['value'].first()
    j = pd.concat([a, b], axis=1, keys=['n', 'o']).dropna()
    j = j[(j['n'] != 0) & (j['o'] != 0)]
    if len(j) < 5:
        return np.nan
    return float((j['n'] / j['o']).median())


def continuity(colmap, cells):
    """Spearman correlation of each column with the same indicator in the next newer year.

    Matched on authority code. A genuine match of a stable measure correlates highly;
    a low value flags a probable wrong match (or a volatile measure) for review.
    """
    a = cells[(cells['row_type'] == 'authority') & cells['value'].notna()]
    a = a.merge(colmap[['year', 'sheet', 'col', 'indicator_id']], on=['year', 'sheet', 'col'])
    out = {}
    for iid, grp in a.groupby('indicator_id'):
        series = {k: g.groupby('muni_code')['value'].first()
                  for k, g in grp.groupby(['year', 'sheet', 'col'])}
        years = sorted({k[0] for k in series})
        for k, s in series.items():
            newer = [y for y in years if y > k[0]]
            if not newer:
                continue
            ref = pd.concat([v for kk, v in series.items() if kk[0] == newer[0]])
            ref = ref[~ref.index.duplicated()]
            j = pd.concat([s, ref], axis=1, keys=['a', 'b']).dropna()
            if len(j) >= 10 and j['a'].nunique() > 1 and j['b'].nunique() > 1:
                r = j.rank()               # Spearman = Pearson on ranks (no scipy needed)
                out[k] = round(float(r['a'].corr(r['b'])), 3)
    return pd.Series(out, name='corr_with_newer_year').rename_axis(['year', 'sheet', 'col']).reset_index()


def synonym_bridges(colmap):
    """Columns where a synonym joins two differently-worded runs of one indicator.

    Within an indicator, columns are grouped by their wording before synonyms. The
    newest column of every group except the newest group is where the series was
    bridged; only that column is flagged, not every column whose label was normalized.
    """
    out = pd.Series(False, index=colmap.index)
    for _, g in colmap.groupby('indicator_id'):
        if g['key_raw'].nunique() < 2:
            continue
        newest_group = g.loc[g['year'].idxmax(), 'key_raw']
        for k, sub in g.groupby('key_raw'):
            if k != newest_group:
                i = sub['year'].idxmax()
                out[i] = bool(colmap.at[i, 'synonym_applied'])  # only where a synonym did the joining
    return out


def review_reasons(colmap, min_corr=0.5):
    """Why a mapping needs a human look ('' = none)."""
    bridge = synonym_bridges(colmap) if 'key_raw' in colmap else pd.Series(False, index=colmap.index)

    def one(r):
        why = []
        if r['match_method'] == 'fuzzy':
            why.append(f"label similarity {r['match_score']}")
        elif r['match_method'] in ('leaf', 'tokens'):
            why.append(f"structural label match ({r['match_method']})")
        if bridge[r.name] and r['match_method'] != 'new':
            why.append('series joined across wordings (label synonym)')
        c = r.get('corr_with_newer_year')
        if (pd.notna(c) and c < min_corr and r['match_method'] != 'new'
                and not _VOLATILE_RE.search(r['levels'])):
            why.append(f'low continuity with next year (rho={c})')
        return '; '.join(why)
    return colmap.apply(one, axis=1)


def units_review(colmap, cells):
    """Indicators whose unit label or value scale changes across years.

    severity:
      scale_jump           values change by >=10x between consecutive years
                           (+ 'label contradicts values' when the unit label did not change)
      unit_label_conflict  different non-empty unit labels in different years
      unit_label_partial   unit written in some years only (usually harmless)
    Nothing is converted: column `decision` is for the reviewer.
    """
    a = cells[(cells['row_type'] == 'authority') & cells['value'].notna()]
    a = a.merge(colmap[['year', 'sheet', 'col', 'indicator_id']], on=['year', 'sheet', 'col'])
    recs = []
    for iid, grp in colmap.groupby('indicator_id'):
        years = sorted(grp['year'].unique())
        if len(years) < 2:
            continue
        units = grp.groupby('year')['unit_hint'].agg(lambda s: ' + '.join(sorted({u for u in s if u})))
        ai = a[a['indicator_id'] == iid]
        jumps, contradictions = [], []
        # year-over-year change rates swing by nature; a ratio test means nothing there
        volatile = grp['levels'].str.contains('שינוי').any()
        for y_old, y_new in ([] if volatile else zip(years, years[1:])):
            r = _scale_ratio(ai, y_new, y_old)
            if not np.isnan(r) and r > 0 and abs(math.log10(r)) >= 1:
                jumps.append(f'{y_old}->{y_new}: x{r:,.4g}')
                if units[y_old] == units[y_new]:
                    contradictions.append(f'{y_old}->{y_new}')
        labelled = {u for u in units if u}
        if jumps:
            severity = 'scale_jump'
        elif len(labelled) > 1:
            severity = 'unit_label_conflict'
        elif labelled and (units == '').any():
            severity = 'unit_label_partial'
        else:
            continue
        sample = ai[ai['muni_code'] == SAMPLE_AUTHORITY[0]].groupby('year')['value'].first()
        latest = grp[grp['year'] == years[-1]].iloc[0]
        recs.append({
            'indicator_id': iid, 'severity': severity, 'label_latest': latest['levels'],
            'unit_by_year': '; '.join(f'{y}: {u or "—"}' for y, u in units.items()),
            'scale_jumps': '; '.join(jumps),
            'label_contradicts_values': '; '.join(contradictions),
            'median_by_year': '; '.join(
                f'{y}: {v:,.4g}' for y, v in ai.groupby('year')['value'].median().items()),
            f'sample_{SAMPLE_AUTHORITY[1]}': '; '.join(f'{y}: {v:,.6g}' for y, v in sample.items()),
            'decision': '',            # for the reviewer, e.g. "x1000 for 2014-2017"
        })
    order = {'scale_jump': 0, 'unit_label_conflict': 1, 'unit_label_partial': 2}
    df = pd.DataFrame(recs)
    return df.sort_values(['severity', 'indicator_id'], key=lambda s: s.map(order) if s.name == 'severity' else s) \
        if len(df) else df


def catalog(colmap):
    """One row per indicator. Expects colmap already joined with column_stats()."""
    m = colmap
    recs = []
    for iid, grp in m.groupby('indicator_id'):
        grp = grp.sort_values('year')
        latest = grp.iloc[-1]
        lv = latest['levels'].split(' › ')
        recs.append({
            'indicator_id': iid, 'domain': latest['domain'], 'category': lv[0] if len(lv) > 1 else '',
            'label_latest': latest['levels'],
            'years': ','.join(str(y) for y in sorted(grp['year'].unique())),
            'n_years': grp['year'].nunique(),
            'unit_hints': ' | '.join(sorted({u for u in grp['unit_hint'] if u})),
            'data_periods': ' | '.join(f"{r.year}:{r.data_period}" for r in grp.itertuples()
                                       if r.data_period != str(r.year)),
            'value_kind': 'text' if grp['n_text'].sum() > grp['n_numeric'].sum() else 'numeric',
            'match_methods': ','.join(sorted(set(grp['match_method']) - {'new'})),
            'review_needed': bool(grp['review_needed'].any()),
            'other_labels': ' || '.join(sorted(set(grp['levels']) - {latest['levels']})),
        })
    return pd.DataFrame(recs)

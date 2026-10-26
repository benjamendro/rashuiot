"""Independent audit of the database against the CBS source files.

The checks deliberately avoid the pipeline's own code paths where possible: source
sheets are re-read with pandas (not the extractor), numbers are parsed by a separate
function, and totals are compared with the figures CBS itself publishes.

  A  every extracted cell equals the source cell; no numeric source cell is missing;
     every row's authority name equals the name in the source row
  B  every non-empty header cell of a source column appears in that column's label
     (catches column shifts in the header reconstruction)
  C  number of authorities per year and status = CBS "רשויות - סך הכל" counts
  D  population summed by municipal status = CBS status totals (after unit decisions)
  E  invariants: one primary value per (indicator, authority, year); value =
     published x factor; years in range; indices 1-10; percentages 0-100
  F  systematic breaks: a year transition where many authorities jump >= 10x at once
     (a unit or definition change nobody reviewed)
  G  identities between columns (config/consistency_rules.yaml): population = men +
     women, age shares sum to 100, water shares = their components
  H  mixed scale inside one column: fractions and percentages in the same year

Usage:  python -m etl.audit      (exit code 1 if a critical check fails)
"""

import json
import math
import unicodedata
import os
import re
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
CONFIG = os.path.join(ROOT, 'etl', 'config')


def _clean(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ''
    return re.sub(r'\s+', ' ', str(v)).strip()


def _num(v):
    """Independent numeric reading of a source cell (None if not a number).

    Written separately from etl.common.parse_value on purpose: it removes every Unicode
    'format' character (category Cf) rather than a fixed list, so a blind spot in the
    extractor's list shows up here as a missed number.
    """
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float, np.integer, np.floating)):
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    s = ''.join(ch for ch in str(v) if unicodedata.category(ch) != 'Cf')
    s = re.sub(r'\s+', ' ', s.replace('\u00a0', ' ')).strip().replace(',', '')
    s = re.sub(r'\s*\*+$', '', s)                                  # footnote mark
    m = re.fullmatch(r'\(\s*(-?\d+(?:\.\d+)?)\s*\)', s)       # '( 2.3)' low reliability
    if m:
        return float(m.group(1))
    if not re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?', s):
        return None
    return float(s)


def _same(a, b):
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


class Audit:
    def __init__(self):
        self.results = []

    def add(self, check, name, ok, critical, detail, examples=None):
        self.results.append({'check': check, 'name': name, 'ok': bool(ok), 'critical': critical,
                             'detail': detail, 'examples': (examples or [])[:15]})
        print(f"[{'PASS' if ok else ('FAIL' if critical else 'WARN')}] {check} {name}: {detail}", flush=True)


# ---- A + B: cells and headers against the source -----------------------------------

def check_cells_and_headers(audit, cfg, cells, colmap):
    mism, missing, extra, name_bad, hdr_bad, empty_rows = [], [], [], [], [], []
    n_cmp = 0
    by_sheet = {k: g for k, g in cells.groupby(['year', 'sheet'])}
    cols_by_sheet = {k: g for k, g in colmap.groupby(['year', 'sheet'])}
    for year, ycfg in sorted(cfg['years'].items()):
        path = os.path.join(ROOT, ycfg['file'])
        for s in ycfg['sheets']:
            raw = pd.read_excel(path, sheet_name=s['name'], header=None, dtype=object)
            got = by_sheet.get((year, s['name']))
            if got is None:
                audit.add('A', f'{year}/{s["name"]}', False, True, 'sheet has no extracted cells')
                continue
            rows = sorted(got['row'].unique())
            # values and names, cell by cell
            for r in got.itertuples():
                src = raw.iat[r.row, r.col] if r.row < raw.shape[0] and r.col < raw.shape[1] else None
                n_cmp += 1
                srcn = _num(src)
                if r.value == r.value:                              # extracted a number
                    if srcn is None or not _same(srcn, r.value):
                        mism.append((year, s['name'], r.row, r.col, _clean(src), r.value))
                elif srcn is not None and r.flag not in ('malformed_number',):
                    mism.append((year, s['name'], r.row, r.col, _clean(src), 'not extracted as number'))
            first = got.drop_duplicates('row').set_index('row')['muni_name']
            for row, name in first.items():
                src_name = _clean(raw.iat[row, 0]).rstrip('*').strip()
                if src_name != name:
                    name_bad.append((year, s['name'], row, src_name, name))
            # completeness: numeric source cells in extracted rows that were not extracted
            have = set(zip(got['row'], got['col']))
            id_cols = {0} | ({s.get('code_col', 1)} if s.get('code_col', 1) is not None else set())
            width = raw.shape[1]
            for row in rows:
                for c in range(width):
                    if c in id_cols:
                        continue
                    if _num(raw.iat[row, c]) is not None and (row, c) not in have:
                        missing.append((year, s['name'], row, c, _clean(raw.iat[row, c])))
            # data rows that were skipped: a code + name present but row not extracted
            code_col = s.get('code_col', 1)
            start = max(s['header_rows'] + [s.get('period_row') or 0]) + 1
            if code_col is not None:
                for row in range(start, raw.shape[0]):
                    nm = _clean(raw.iat[row, 0])
                    cd = _num(raw.iat[row, code_col])
                    if nm and cd is not None and float(cd).is_integer() and row not in first.index:
                        has_data = any(_clean(raw.iat[row, c]) for c in range(width) if c not in id_cols)
                        (extra if has_data else empty_rows).append((year, s['name'], row, nm, cd))
            # B: header containment
            hrows = [h for h in s['header_rows'] if h != s.get('period_row')]
            cm = cols_by_sheet.get((year, s['name']))
            if cm is not None:
                for c, levels in zip(cm['col'], cm['levels'].fillna('')):
                    lv = _clean(levels)
                    for h in hrows:
                        t = _clean(raw.iat[h, c]) if c < raw.shape[1] else ''
                        if t and t not in lv:
                            hdr_bad.append((year, s['name'], c, h, t, lv[:120]))
    audit.add('A', 'cell values equal the source', not mism, True,
              f'{n_cmp:,} cells compared, {len(mism)} differ', mism)
    audit.add('A', 'no numeric source cell missed', not missing, True,
              f'{len(missing)} numeric source cells in extracted rows were not extracted', missing)
    audit.add('A', 'no authority row with data skipped', not extra, True,
              f'{len(extra)} source rows with a name, a code and data were not extracted', extra)
    audit.add('A', 'authority rows without any data (info)', True, False,
              f'{len(empty_rows)} rows list an authority but every value is empty '
              '(CBS footnote: data not reported)', empty_rows)
    audit.add('A', 'row names equal the source', not name_bad, True,
              f'{len(name_bad)} rows whose name differs from the source', name_bad)
    audit.add('B', 'headers contained in labels', not hdr_bad, True,
              f'{len(hdr_bad)} header cells missing from their column label', hdr_bad)


def check_codes(audit, cells, registry):
    """Every row's code resolves to the registry authority of that year with that name."""
    reg = registry.set_index(['year', 'muni_code'])['name']
    a = cells[cells['row_type'] == 'authority'].drop_duplicates(['year', 'sheet', 'row'])
    from .matching import sanitize
    aliases = {sanitize(k): sanitize(v) for k, v in (yaml.safe_load(open(os.path.join(CONFIG, 'sources.yaml'), encoding='utf-8')).get('name_aliases') or {}).items()}
    bad = []
    for r in a.itertuples():
        rn = reg.get((r.year, r.muni_code))
        if rn is None:
            bad.append((r.year, r.sheet, r.row, r.muni_name, r.muni_code, 'code not in registry'))
            continue
        x, y = sanitize(r.muni_name), sanitize(rn)
        if x != y and aliases.get(x) != y:
            bad.append((r.year, r.sheet, r.row, r.muni_name, r.muni_code, f'registry: {rn}'))
    audit.add('A', 'codes resolve to the same-named authority', not bad, True,
              f'{len(a):,} rows checked, {len(bad)} mismatches', bad)
    dup = registry[registry.duplicated(['year', 'muni_code'], keep=False)]
    audit.add('A', 'one authority per code per year', dup.empty, True,
              f'{len(dup)} duplicated (year, code) pairs', dup.values.tolist())


# ---- C + D: against CBS published totals --------------------------------------------

_STATUS_GROUP = {'עירייה': 'municipality', 'מועצה מקומית': 'local_council', 'מועצה אזורית': 'regional_council'}


def check_cbs_totals(audit, summary, facts, registry, pop_id):
    # C: counts of authorities
    counts = summary[summary['label'].str.contains(r'^(?:רשויות|עיריות|מועצות מקומיות|מועצות אזוריות) - סך הכל', regex=True)]
    bad, n = [], 0
    for r in counts.itertuples():
        lab = r.label
        y = r.year
        if lab.startswith('רשויות'):
            exp = registry[registry.year == y].shape[0]
        else:
            st = {'עיריות': 'עירייה', 'מועצות מקומיות': 'מועצה מקומית', 'מועצות אזוריות': 'מועצה אזורית'}[lab.split(' - ')[0]]
            exp = registry[(registry.year == y) & (registry.status == st)].shape[0]
        n += 1
        if r.value != exp:
            bad.append((y, lab, r.value, exp))
    audit.add('C', 'authority counts = CBS', not bad, False,
              f'{n} published counts compared, {len(bad)} differ', bad)

    # D: population by status (authorities' sum vs CBS status totals)
    pop = facts[(facts.indicator_id == pop_id) & (facts.row_type == 'authority')]
    pop = pop[pop.data_period.astype(str) == pop.file_year.astype(str)]   # the file's own year
    reg = registry[['year', 'muni_code', 'status']].rename(columns={'year': 'file_year'})
    pop = pop.merge(reg, on=['file_year', 'muni_code'], how='left')
    sums = pop.groupby(['file_year', 'status'])['value'].sum()
    rows, bad = [], []
    # in-sheet summary rows (2022+), already in facts
    s_in = facts[(facts.indicator_id == pop_id) & (facts.row_type == 'summary')]
    for r in s_in.itertuples():
        rows.append((r.file_year, r.summary_group, r.value, 1.0))
    # transposed sheets: published in thousands until 2017
    lab = summary[summary['label'].str.contains(r'^סה"כ אוכלוסייה בסוף', regex=True)
                  & summary['section'].fillna('').str.contains('דמוגרפיה|אוכלוסייה|כללי', regex=True)]
    for r in lab.drop_duplicates(['year', 'summary_group']).itertuples():
        scale = 1000.0 if 'אלפים' in r.label or (r.value < 20000 and r.summary_group != 'national') else 1.0
        if r.summary_group == 'national' and r.value < 20000:
            scale = 1000.0
        rows.append((r.year, r.summary_group, r.value * scale, scale))
    n = 0
    for y, grp, cbs_val, scale in rows:
        if grp == 'national':
            continue
        st = {v: k for k, v in _STATUS_GROUP.items()}[grp]
        mine = sums.get((y, st))
        if mine is None or not cbs_val:
            continue
        n += 1
        tol = 0.002 if scale == 1.0 else 0.02        # published in thousands: rounding
        rel = abs(mine - cbs_val) / cbs_val
        if rel > tol:
            bad.append((int(y), grp, round(mine), round(cbs_val), f'{rel:.2%}'))
    audit.add('D', 'population by status = CBS totals', not bad, False,
              f'{n} (year, status) totals compared, {len(bad)} outside tolerance', bad)


# ---- E: invariants -------------------------------------------------------------------

def check_invariants(audit, facts, catalog, keys):
    a = facts[facts.row_type == 'authority']
    p = a[a.is_primary]
    dup = p[p.duplicated(['indicator_id', 'muni_code', 'period_year'], keep=False)]
    audit.add('E', 'one primary value per indicator/authority/year', dup.empty, True,
              f'{len(dup)} duplicate primary rows', dup.head(15).values.tolist())
    orphan = a.groupby(['indicator_id', 'muni_code', 'period_year'])['is_primary'].sum()
    audit.add('E', 'every observed value has a primary', (orphan == 1).all(), True,
              f'{int((orphan != 1).sum())} keys without exactly one primary')
    calc = (a.value - a.value_raw * a.unit_factor).abs() > 1e-9 * a.value.abs().clip(lower=1)
    audit.add('E', 'value = published x unit factor', not calc.any(), True, f'{int(calc.sum())} rows differ')
    # files are published 1-2 years after their year and may include later events
    # (the 2022 file has the February 2024 local elections)
    fut = a[a.period_year > a.file_year + 2]
    audit.add('E', 'no data year more than 2 years after its file year', fut.empty, True,
              f'{len(fut)} rows', fut[['indicator_id', 'file_year', 'data_period']].drop_duplicates().head(15).values.tolist())
    later = a[(a.period_year > a.file_year) & (a.period_year <= a.file_year + 2)]
    audit.add('E', 'data years after the file year (info)', True, False,
              f'{later.indicator_id.nunique()} indicators', later[['indicator_id', 'file_year', 'data_period']].drop_duplicates().head(15).values.tolist())
    for k in ('ses_cluster', 'periphery_cluster'):
        v = p[p.indicator_id == keys[k]].value.dropna()     # '..' / '-' rows carry no number
        bad = v[(v < 1) | (v > 10) | (v != v.round())]
        audit.add('E', f'{k} values are integers 1-10', bad.empty, True, f'{len(bad)} out of range')
    labels = catalog.set_index('indicator_id')['label_latest']
    # the measure itself (last label level) is a share; change rates and losses may be negative
    leaf = labels.astype(str).str.split(' › ').str[-1]
    pct_ids = [i for i, l in leaf.items() if re.search(r'^(?!.*(שינוי|גידול|לעומת|יחס|פחת)).*(אחוז|\(%\)|באחוזים)', l)]
    pp = p[p.indicator_id.isin(pct_ids)]
    out = pp[(pp.value < -0.5) | (pp.value > 100.5)]                 # CBS rounding: 100.3 occurs
    by = out.groupby('indicator_id').size().sort_values(ascending=False)
    audit.add('E', 'percentages within 0-100', out.empty, False,
              f'{len(out)} values in {len(by)} percentage indicators outside 0-100',
              [(i, labels[i][:70], int(n)) for i, n in by.head(15).items()])
    pop = p[p.indicator_id == keys['population']]
    neg = pop[pop.value <= 0]
    audit.add('E', 'population positive', neg.empty, True, f'{len(neg)} non-positive')


# ---- F: systematic breaks ---------------------------------------------------------------

_VOLATILE = re.compile(r'שינוי|גידול|לעומת|עודף|גירעון|מאזן|ריבוי|הנחת|התחלת|גמר|סלילת|עולים|השתקעות|נכנסים|יוצאים|תאונות|הרוגים|בחירות|הצבעה|הגירה|מלוות|מענק')


def check_breaks(audit, facts, catalog, unit_decisions):
    """Year transitions where >= 25% of authorities change by >= 10x together."""
    labels = catalog.set_index('indicator_id')['label_latest']
    decided = {d['indicator_id'] for d in unit_decisions}
    p = facts[(facts.row_type == 'authority') & facts.is_primary & (facts.value.abs() > 0)]
    p = p[['indicator_id', 'muni_code', 'period_year', 'value']].sort_values(['indicator_id', 'muni_code', 'period_year'])
    p['prev'] = p.groupby(['indicator_id', 'muni_code'])['value'].shift()
    p['prev_year'] = p.groupby(['indicator_id', 'muni_code'])['period_year'].shift()
    p = p.dropna(subset=['prev'])
    p = p[p.prev.abs() > 0]
    # ignore tiny values (0.01 -> 0.4 is not a unit change): both below the indicator's
    # 25th percentile of absolute values
    floor = p.groupby('indicator_id')['value'].transform(lambda s: s.abs().quantile(0.25))
    p = p[(p.value.abs() >= floor) | (p.prev.abs() >= floor)]
    p['jump'] = (np.log10((p.value / p.prev).abs()).abs() >= 1)
    g = p.groupby(['indicator_id', 'prev_year', 'period_year']).agg(n=('jump', 'size'), j=('jump', 'sum'))
    g = g[(g.n >= 20) & (g.j / g.n >= 0.25)].reset_index()
    g['label'] = g.indicator_id.map(labels)
    g = g[~g.label.fillna('').str.contains(_VOLATILE)]
    open_ = g[~g.indicator_id.isin(decided)]
    audit.add('F', 'no unreviewed systematic 10x breaks', open_.empty, False,
              f'{len(open_)} transitions in {open_.indicator_id.nunique()} indicators where >=25% of '
              'authorities jump >=10x together (not covered by a unit decision)',
              [(r.indicator_id, int(r.prev_year), int(r.period_year), f'{r.j}/{r.n}', str(r.label)[:70])
               for r in open_.sort_values('j', ascending=False).itertuples()])
    return open_


# ---- G: identities between columns; H: mixed scale inside one column -----------------

def check_consistency(audit, facts, catalog):
    rules = yaml.safe_load(open(os.path.join(CONFIG, 'consistency_rules.yaml'), encoding='utf-8')) or []
    by_label = {}
    for r in catalog.itertuples():
        by_label.setdefault(r.label_latest, []).append(r.indicator_id)
    p = facts[(facts.row_type == 'authority') & facts.is_primary & facts.value.notna()]
    wide_cache = {}

    def series(label):
        ids = by_label.get(label, [])
        if len(ids) != 1:
            raise RuntimeError(f'consistency rule label resolves to {len(ids)} indicators: {label}')
        iid = ids[0]
        if iid not in wide_cache:
            wide_cache[iid] = p[p.indicator_id == iid].set_index(['muni_code', 'period_year'])['value']
        return iid, wide_cache[iid]

    out = []
    for rule in rules:
        if rule['kind'] in ('sum', 'sum_const'):
            parts = [series(l) for l in rule['parts']]
            df = pd.concat([s for _, s in parts], axis=1, keys=[i for i, _ in parts]).dropna()
            got = df.sum(axis=1)
            if rule['kind'] == 'sum':
                tid, total = series(rule['total'])
                j = pd.concat([total, got], axis=1, keys=['exp', 'got']).dropna()
                flag_ids = [tid]
            else:
                j = pd.DataFrame({'exp': rule['value'], 'got': got})
                flag_ids = [i for i, _ in parts]
        else:
            rid, res = series(rule['result'])
            _, num = series(rule['numerator'])
            _, den = series(rule['denominator'])
            calc = (100 * num / den.where(den != 0))
            j = pd.concat([res, calc], axis=1, keys=['got', 'exp']).dropna()
            flag_ids = [rid]
        tol = pd.Series(rule.get('tolerance_abs', 0.0), index=j.index)
        if 'tolerance_rel' in rule:
            tol = np.maximum(tol, rule['tolerance_rel'] * j['exp'].abs())
        bad = j[(j['got'] - j['exp']).abs() > tol]
        for (muni, yr), r in bad.iterrows():
            for iid in flag_ids:
                out.append({'rule': rule['name'], 'indicator_id': iid, 'muni_code': muni,
                            'period_year': yr, 'published': r['got'], 'expected': r['exp']})
        by_year = bad.reset_index().groupby('period_year').size()
        audit.add('G', rule['name'], bad.empty, False,
                  f'{len(j):,} authority-years checked, {len(bad)} violate the identity',
                  [(int(y), int(n)) for y, n in by_year.sort_values(ascending=False).head(10).items()])
    return pd.DataFrame(out, columns=['rule', 'indicator_id', 'muni_code', 'period_year', 'published', 'expected'])


def check_mixed_scale(audit, facts, catalog):
    """Percentage columns where, in one year, some authorities are fractions (<= 1) and
    others percentages (> 10) with nothing in between: a scale mix inside the source."""
    labels = catalog.set_index('indicator_id')['label_latest'].astype(str)
    leaf = labels.str.split(' › ').str[-1]
    pct = [i for i, l in leaf.items() if re.search(r'^(?!.*(שינוי|גידול|לעומת|יחס)).*(אחוז|\(%\))', l)]
    p = facts[(facts.row_type == 'authority') & facts.is_primary & facts.indicator_id.isin(pct)
              & facts.value.notna()]
    # a value <= 1 counts as a fraction only if the same authority's value in an adjacent
    # year is ~100x larger (Arab localities really have 0.3% "Jews and others")
    series = p.set_index(['indicator_id', 'muni_code', 'period_year'])['value']
    rows, found = [], []
    for (iid, yr), g in p.groupby(['indicator_id', 'period_year']):
        v = g['value']
        low, high, mid = (v > 0) & (v <= 1), v > 10, (v > 1) & (v <= 10)
        if not (low.sum() >= 0.1 * len(v) and high.sum() >= 0.1 * len(v) and len(v) >= 20):
            continue
        confirmed = []
        for m, x in zip(g.loc[low, 'muni_code'], v[low]):
            nb = [series.get((iid, m, yr + d)) for d in (-2, -1, 1, 2)]
            if any(n is not None and n == n and 50 * x <= n <= 200 * x for n in nb):
                confirmed.append(m)
        if len(confirmed) >= 0.1 * len(v):
            found.append((iid, int(yr), len(confirmed), int(high.sum()), labels[iid][:70]))
            rows += [{'indicator_id': iid, 'muni_code': m, 'period_year': yr} for m in confirmed]
    audit.add('H', 'no mixed fraction/percent scale within a column', not found, False,
              f'{len(found)} indicator-years mix fractions and percentages', found)
    return pd.DataFrame(rows, columns=['indicator_id', 'muni_code', 'period_year'])


def main():
    from .extract import load_config
    from .gold import load_yaml, resolve_key_indicators
    cfg = load_config(os.path.join(CONFIG, 'sources.yaml'))
    cells = pd.read_parquet(os.path.join(DATA, 'bronze', 'cells.parquet'))
    summary = pd.read_parquet(os.path.join(DATA, 'bronze', 'summary_cells.parquet'))
    registry = pd.read_csv(os.path.join(DATA, 'bronze', 'authority_registry.csv'))
    colmap = pd.read_csv(os.path.join(DATA, 'silver', 'column_map_DRAFT.csv'))
    catalog = pd.read_csv(os.path.join(DATA, 'silver', 'indicator_catalog_DRAFT.csv'))
    facts = pd.read_parquet(os.path.join(DATA, 'gold', 'facts.parquet'))
    keys = resolve_key_indicators(catalog)
    unit_decisions = load_yaml('unit_decisions.yaml') or []

    audit = Audit()
    check_cells_and_headers(audit, cfg, cells, colmap)
    check_codes(audit, cells, registry)
    check_cbs_totals(audit, summary, facts, registry, keys['population'])
    check_invariants(audit, facts, catalog, keys)
    breaks = check_breaks(audit, facts, catalog, unit_decisions)
    consistency = check_consistency(audit, facts, catalog)
    mixed = check_mixed_scale(audit, facts, catalog)

    os.makedirs(os.path.join(DATA, 'qa'), exist_ok=True)
    with open(os.path.join(DATA, 'qa', 'audit.json'), 'w', encoding='utf-8') as f:
        json.dump(audit.results, f, ensure_ascii=False, indent=1, default=str)
    breaks.to_csv(os.path.join(DATA, 'qa', 'audit_breaks.csv'), index=False, encoding='utf-8-sig')
    consistency.to_csv(os.path.join(DATA, 'qa', 'consistency_violations.csv'), index=False, encoding='utf-8-sig')
    mixed.to_csv(os.path.join(DATA, 'qa', 'mixed_scale.csv'), index=False, encoding='utf-8-sig')
    failed = [r for r in audit.results if not r['ok'] and r['critical']]
    print(f"\n{sum(r['ok'] for r in audit.results)}/{len(audit.results)} checks passed; "
          f"{len(failed)} critical failures")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

"""Stages 2b-3 - Silver facts and authority dimensions.

  facts            every numeric value (authorities + CBS summary rows) with its indicator,
                   the data year it describes (period_year), the unit decision applied and
                   whether it is the primary revision
  dim_authority    one row per authority: names, status, district, Eshkol cluster/sector
  authority_year   one row per authority and year: population, SES cluster (as of that
                   year and in the latest edition), peripherality

Usage:  python -m etl.gold      (after python -m etl.run)
"""

import os
import re

import numpy as np
import pandas as pd
import yaml

from .classify import classify
from .matching import EshkolMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
CONFIG = os.path.join(ROOT, 'etl', 'config')

_YEAR4 = re.compile(r'(?:19|20)\d{2}')
_YEAR_SHORT = re.compile(r'((?:19|20)\d{2})\s*[-/]\s*(\d{2})(?!\d)')


def period_year(period):
    """Single year a period string describes: the latest year it mentions.

    '2023' -> 2023 · 'תשפ"ד 2023/24' -> 2024 · '2020-2024' -> 2024 · '2015 2014' -> 2015
    """
    s = str(period)
    years = [int(y) for y in _YEAR4.findall(s)]
    for full, short in _YEAR_SHORT.findall(s):
        years.append(int(full[:2] + short))
    return max(years) if years else None


def _out(*parts):
    path = os.path.join(DATA, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def load_yaml(name):
    with open(os.path.join(CONFIG, name), encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_key_indicators(catalog):
    out = {}
    for name, label in load_yaml('key_indicators.yaml').items():
        hit = catalog[(catalog['label_latest'] == label) & (catalog['domain'] == 'physical')]
        if len(hit) != 1:
            raise RuntimeError(f"key indicator '{name}' resolves to {len(hit)} indicators: {label}")
        out[name] = hit['indicator_id'].iloc[0]
    return out


# ---- facts -------------------------------------------------------------------------

def build_facts(cells, colmap, unit_decisions):
    """Every published cell of a mapped column: numbers and every CBS symbol or text, so
    nothing a source cell says is dropped (value is NaN where there is no number)."""
    cols = colmap[['year', 'sheet', 'col', 'indicator_id', 'data_period', 'unit_hint', 'review_needed']]
    f = cells.merge(cols, on=['year', 'sheet', 'col'], how='inner')
    f = f.rename(columns={'year': 'file_year', 'value': 'value_raw'})
    f['period_year'] = f['data_period'].map(period_year).astype('Int64')
    f.loc[f['period_year'].isna(), 'period_year'] = f['file_year']

    # unit decisions: multiplier per (indicator, file year)
    fac = {(d['indicator_id'], int(y)): float(v) for d in unit_decisions if d['status'] == 'apply'
           for y, v in (d.get('factors') or {}).items()}
    keys = list(zip(f['indicator_id'], f['file_year']))
    f['unit_factor'] = [fac.get(k, 1.0) for k in keys]
    f['value'] = f['value_raw'] * f['unit_factor']
    f['low_reliability'] = f['flag'].eq('low_reliability')
    f['nil_as_zero'] = False
    f = f.rename(columns={'review_needed': 'mapping_review'})
    return f[['indicator_id', 'row_type', 'summary_group', 'muni_code', 'muni_name', 'file_year',
              'sheet', 'col', 'data_period', 'period_year', 'value_raw', 'unit_factor', 'value',
              'value_text', 'flag', 'raw', 'unit_hint', 'low_reliability', 'nil_as_zero',
              'mapping_review']].reset_index(drop=True)


def apply_nil_as_zero(facts, catalog):
    """CBS '-' means "חוסר מקרים" (no cases). For counts that is 0; for rates, indices and
    attributes it stays empty (a rate with no cases is undefined). Marked nil_as_zero."""
    counts = set(catalog.loc[catalog['measure_type'] == 'count', 'indicator_id'])
    m = facts['flag'].eq('dash') & facts['indicator_id'].isin(counts)
    facts.loc[m, 'value'] = 0.0
    facts.loc[m, 'nil_as_zero'] = True
    return facts


def infer_unlabelled_editions(facts, ids, report):
    """SES columns of the 2003-2004 files name no edition. A file whose values equal the
    next file's (>= 99% of authorities) takes that file's edition; otherwise the edition
    is marked unspecified and dated one year before the earliest labelled edition."""
    for iid in ids:
        a = facts[(facts['indicator_id'] == iid) & (facts['row_type'] == 'authority')]
        labelled = a[a['data_period'].astype(str) != a['file_year'].astype(str)]
        if labelled.empty:
            continue
        first_lab = int(labelled['file_year'].min())
        first_edition = int(labelled.loc[labelled['file_year'] == first_lab, 'period_year'].iloc[0])
        for fy in sorted(a.loc[a['file_year'] < first_lab, 'file_year'].unique(), reverse=True):
            cur = a[a['file_year'] == fy].set_index('muni_code')['value']
            nxt_year = a.loc[a['file_year'] > fy, 'file_year'].min()
            nxt = a[a['file_year'] == nxt_year].set_index('muni_code')['value']
            j = pd.concat([cur, nxt], axis=1, keys=['c', 'n']).dropna()
            share = float((j['c'] == j['n']).mean()) if len(j) else 0.0
            m = (facts['indicator_id'] == iid) & (facts['file_year'] == fy)
            if share >= 0.99:
                ed = int(a.loc[a['file_year'] == nxt_year, 'period_year'].iloc[0])
                facts.loc[m, ['data_period', 'period_year']] = [f'{ed} (inferred)', ed]
                report.append(f'{iid}: file {fy} edition inferred = {ed} ({share:.0%} identical to file {nxt_year})')
            else:
                facts.loc[m, ['data_period', 'period_year']] = ['unspecified (<' f'{first_edition})',
                                                                first_edition - 1]
                report.append(f'{iid}: file {fy} edition unspecified ({share:.0%} identical to file '
                              f'{nxt_year}); dated {first_edition - 1} for ordering only')
                a = facts[(facts['indicator_id'] == iid) & (facts['row_type'] == 'authority')]
    return facts


def mark_primary(facts):
    """The newest file is the primary revision of each (indicator, authority, period year)."""
    a = facts['row_type'] == 'authority'
    key = ['indicator_id', 'muni_code', 'period_year']
    # prefer a row with a value; among those the newest file (a later '..' must not hide
    # a number an earlier file gave for the same year)
    facts['_has'] = facts['value'].notna() | facts['value_text'].notna()
    order = facts[a].sort_values(key + ['_has', 'file_year', 'col'],
                                 ascending=[True, True, True, False, False, True])
    first = ~order.duplicated(key)
    facts['is_primary'] = False
    facts.loc[order.index[first.values], 'is_primary'] = True
    s = facts['row_type'] == 'summary'
    skey = ['indicator_id', 'summary_group', 'period_year']
    sorder = facts[s].sort_values(skey + ['_has', 'file_year'], ascending=[True, True, True, False, False])
    facts.loc[sorder.index[~sorder.duplicated(skey).values], 'is_primary'] = True
    return facts.drop(columns='_has')


def revision_report(facts):
    """Where several files report the same authority/indicator/year with different values."""
    a = facts[(facts['row_type'] == 'authority') & facts['value'].notna()]
    g = a.groupby(['indicator_id', 'muni_code', 'period_year'])['value']
    stats = g.agg(['count', 'min', 'max'])
    multi = stats[stats['count'] > 1]
    differ = multi[(multi['max'] - multi['min']).abs() > 1e-9 * multi['max'].abs().clip(lower=1)]
    return len(multi), differ.reset_index()


# ---- authorities ---------------------------------------------------------------------

def build_dim_authority(registry):
    matcher = EshkolMatcher()
    t = matcher.targets
    full = pd.read_excel(matcher.mapping_path)
    full = full.rename(columns={'קוד למס (סמל)': 'code', 'אשכול': 'eshkol', 'מגזר': 'sector',
                                'צורת יישוב': 'settlement_form', 'סוג ישות': 'entity_type',
                                'שם ברשימת אשכול': 'eshkol_name'})
    full = full[full['entity_type'] == 'רשות'][['code', 'eshkol_name', 'eshkol', 'sector', 'settlement_form']]
    reg = registry.sort_values('year')
    last = reg.groupby('muni_code').tail(1).set_index('muni_code')
    dim = pd.DataFrame({
        'muni_code': last.index,
        'name': last['name'].values,
        'status': last['status'].values,
        'district': last['district'].values,
        'first_year': reg.groupby('muni_code')['year'].min().reindex(last.index).values,
        'last_year': reg.groupby('muni_code')['year'].max().reindex(last.index).values,
        'n_years': reg.groupby('muni_code')['year'].nunique().reindex(last.index).values,
        'other_names': reg.groupby('muni_code')['name'].agg(
            lambda s: ' | '.join(sorted(set(s) - {s.iloc[-1]}))).reindex(last.index).values,
    })
    dim = dim.merge(full.rename(columns={'code': 'muni_code'}), on='muni_code', how='left')
    dim['eshkol'] = dim['eshkol'].fillna('')
    assert set(t[t['entity_type'] == 'רשות']['code'].astype(int)) <= set(dim['muni_code'])
    return dim.sort_values(['eshkol', 'name'], ascending=[False, True]).reset_index(drop=True)


def _edition_lookup(facts, iid):
    """{muni: [(edition_year, label, value), ...] sorted} from primary facts of an index."""
    a = facts[(facts['indicator_id'] == iid) & (facts['row_type'] == 'authority') & facts['is_primary']]
    out = {}
    for r in a.sort_values('period_year').itertuples():
        out.setdefault(r.muni_code, []).append((int(r.period_year), str(r.data_period), r.value))
    return out


def _as_of(eds, year):
    """Latest edition with edition year <= year; the earliest edition for earlier years."""
    if not eds:
        return (None, None, np.nan)
    prior = [e for e in eds if e[0] <= year]
    return prior[-1] if prior else eds[0]


def build_authority_year(facts, registry, dim, keys):
    years = sorted(registry['year'].unique())
    ses = _edition_lookup(facts, keys['ses_cluster'])
    ses_v = _edition_lookup(facts, keys['ses_value'])
    per = _edition_lookup(facts, keys['periphery_cluster'])
    pop = facts[(facts['indicator_id'] == keys['population']) & (facts['row_type'] == 'authority')
                & facts['is_primary']].set_index(['muni_code', 'period_year'])['value']
    latest_ed = max(e[0] for v in ses.values() for e in v)
    reg = registry.set_index(['muni_code', 'year'])
    rows = []
    for (code, year), r in reg.iterrows():
        s_ed, s_lab, s_c = _as_of(ses.get(code, []), year)
        _, _, s_val = _as_of(ses_v.get(code, []), year)
        latest = [e for e in ses.get(code, []) if e[0] == latest_ed]
        p_ed, p_lab, p_c = _as_of(per.get(code, []), year)
        rows.append({
            'muni_code': code, 'year': year, 'name': r['name'], 'status': r['status'],
            'district': r['district'], 'population': pop.get((code, year), np.nan),
            'ses_cluster': s_c, 'ses_value': s_val, 'ses_edition': s_lab,
            'ses_cluster_latest': latest[0][2] if latest else np.nan,
            'ses_edition_latest': latest[0][1] if latest else None,
            'periphery_cluster': p_c, 'periphery_edition': p_lab,
        })
    ay = pd.DataFrame(rows).merge(dim[['muni_code', 'eshkol', 'sector']], on='muni_code', how='left')
    for c in ('ses_cluster', 'ses_cluster_latest', 'periphery_cluster'):
        ay[c] = ay[c].round().astype('Int64')
    return ay.sort_values(['muni_code', 'year']).reset_index(drop=True)


def main():
    colmap = pd.read_csv(os.path.join(DATA, 'silver', 'column_map_DRAFT.csv'))
    catalog = pd.read_csv(os.path.join(DATA, 'silver', 'indicator_catalog_DRAFT.csv'))
    cells = pd.read_parquet(os.path.join(DATA, 'bronze', 'cells.parquet'))
    registry = pd.read_csv(os.path.join(DATA, 'bronze', 'authority_registry.csv'))
    keys = resolve_key_indicators(catalog)
    report = [f'key indicators: {keys}']

    facts = build_facts(cells, colmap, load_yaml('unit_decisions.yaml') or [])
    facts = infer_unlabelled_editions(facts, [keys['ses_cluster'], keys['ses_value'], keys['ses_rank']], report)
    facts = mark_primary(facts)                      # provisional, for classification
    classified = classify(catalog, facts, keys['population'])
    facts = apply_nil_as_zero(facts, classified)
    facts = mark_primary(facts)
    moved = classified['measure_type_basis'].ne('label').sum()
    report.append(f"measure types: {classified['measure_type'].value_counts().to_dict()}; "
                  f"{moved} reclassified by the data check")
    report.append(f"'-' (no cases) stored as 0 for count measures: {int(facts['nil_as_zero'].sum()):,} cells")
    n_multi, differ = revision_report(facts)
    report.append(f'{n_multi:,} (indicator, authority, year) reported by more than one file; '
                  f'{len(differ):,} of them with different values (newest file kept as primary)')

    dim = build_dim_authority(registry)
    ay = build_authority_year(facts, registry, dim, keys)

    facts.to_parquet(_out('gold', 'facts.parquet'), index=False)
    classified.to_csv(_out('gold', 'indicators_classified.csv'), index=False, encoding='utf-8-sig')
    differ.to_csv(_out('qa', 'revisions.csv'), index=False, encoding='utf-8-sig')
    dim.to_csv(_out('gold', 'dim_authority.csv'), index=False, encoding='utf-8-sig')
    ay.to_csv(_out('gold', 'authority_year.csv'), index=False, encoding='utf-8-sig')
    with open(_out('qa', 'gold_notes.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(report) + '\n')
    print('\n'.join(report))
    print(f'facts {len(facts):,} rows ({facts.is_primary.sum():,} primary) · dim {len(dim)} · authority_year {len(ay):,}')
    return facts, dim, ay, keys


if __name__ == '__main__':
    main()

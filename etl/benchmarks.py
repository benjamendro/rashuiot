"""Stages 4-5 - Benchmarks and Eshkol comparisons.

benchmarks          statistics of every numeric indicator per data year and peer group:
                    national · municipal status · SES cluster as of that year · SES cluster
                    in the latest edition · SES x status · Eshkol cluster
comparison_eshkol   every Eshkol authority x indicator x year against those groups:
                    differences, percentiles, z-score within its SES cluster
eastern_galilee.xlsx  analyst workbook for the East Galilee (latest year per indicator)

Count indicators (births, budget in NIS thousands, ...) are not comparable across
authorities of different sizes, so each also gets a derived "per 1,000 residents" version.

Usage:  python -m etl.benchmarks     (after python -m etl.gold)
"""

import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')

GROUPS = [('national', None), ('status', 'status'), ('ses', 'ses_cluster'),
          ('ses_latest', 'ses_cluster_latest'), ('ses_status', 'ses_status'), ('eshkol', 'eshkol')]


def _out(*parts):
    path = os.path.join(DATA, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def attach_attributes(f, ay):
    """Peer-group attributes of each (authority, data year): the authority_year row of
    that year, or the authority's nearest year when the data year is outside the files."""
    a = ay[['muni_code', 'year', 'status', 'ses_cluster', 'ses_cluster_latest', 'eshkol',
            'population']].copy()
    a['year'] = a['year'].astype('int64')
    a['muni_code'] = a['muni_code'].astype('int64')
    f = f.copy()
    f['period_year'] = f['period_year'].astype('int64')
    f['muni_code'] = f['muni_code'].astype('int64')
    f['_ord'] = np.arange(len(f))
    f = f.sort_values('period_year')
    a = a.sort_values('year')
    m = pd.merge_asof(f, a, left_on='period_year', right_on='year', by='muni_code',
                      direction='nearest')
    m = m.sort_values('_ord').drop(columns=['_ord', 'year'])
    for c in ('ses_cluster', 'ses_cluster_latest'):
        m[c] = m[c].round().astype('Int64')
    m['ses_status'] = m['ses_cluster'].astype('string') + ' | ' + m['status'].astype('string')
    m['eshkol'] = m['eshkol'].replace('', np.nan)
    return m


def derived_per_1000(f, catalog_types, pop_id):
    """Counts -> per 1,000 residents, using the population of the same authority and year."""
    pop = f[f['indicator_id'] == pop_id].groupby(['muni_code', 'period_year'])['value'].first()
    counts = f[f['indicator_id'].map(catalog_types).eq('count') & (f['indicator_id'] != pop_id)].copy()
    p = pd.Series(list(zip(counts['muni_code'], counts['period_year']))).map(pop).values
    counts['value'] = counts['value'] / p * 1000
    counts['indicator_id'] = counts['indicator_id'] + '_k'
    return counts[np.isfinite(counts['value'].astype(float))]


def group_stats(f):
    rows = []
    for gname, col in GROUPS:
        keys = ['indicator_id', 'period_year'] + ([col] if col else [])
        d = f.dropna(subset=[col]) if col else f
        g = d.groupby(keys, observed=True)
        s = g['value'].agg(n='count', mean='mean', median='median', std='std', min='min', max='max')
        s['p25'] = g['value'].quantile(0.25)
        s['p75'] = g['value'].quantile(0.75)
        w = d.assign(_wv=d['value'] * d['population'], _w=d['population'].where(d['value'].notna()))
        gw = w.groupby(keys, observed=True)
        s['pop_weighted_mean'] = gw['_wv'].sum(min_count=1) / gw['_w'].sum(min_count=1)
        s = s.reset_index()
        s.insert(2, 'group_type', gname)
        s.insert(3, 'group', s.pop(col).astype(str) if col else 'all')
        rows.append(s)
    return pd.concat(rows, ignore_index=True)


def ranks(f):
    """Percentile (0-100) nationally and within the SES cluster; z-score within the cluster."""
    out = f[['indicator_id', 'period_year', 'muni_code']].copy()
    g = f.groupby(['indicator_id', 'period_year'])['value']
    out['pct_rank_national'] = g.rank(pct=True) * 100
    gs = f.groupby(['indicator_id', 'period_year', 'ses_cluster'])['value']
    out['pct_rank_ses'] = gs.rank(pct=True) * 100
    out['z_ses'] = (f['value'] - gs.transform('mean')) / gs.transform('std')
    return out


def main():
    facts = pd.read_parquet(os.path.join(DATA, 'gold', 'facts.parquet'))
    ay = pd.read_csv(os.path.join(DATA, 'gold', 'authority_year.csv'))
    dim = pd.read_csv(os.path.join(DATA, 'gold', 'dim_authority.csv')).fillna({'eshkol': ''})
    catalog = pd.read_csv(os.path.join(DATA, 'gold', 'indicators_classified.csv'))
    colmap = pd.read_csv(os.path.join(DATA, 'silver', 'column_map_DRAFT.csv'),
                         usecols=['indicator_id', 'review_needed'])
    from .gold import load_yaml, resolve_key_indicators
    keys = resolve_key_indicators(catalog)

    types = catalog.set_index('indicator_id')['measure_type']      # from etl.classify

    prim = facts[(facts['row_type'] == 'authority') & facts['is_primary'] & facts['value'].notna()].copy()
    prim = prim[prim['indicator_id'].map(types).isin(['rate', 'count', 'index'])]
    f = attach_attributes(prim, ay)
    k = derived_per_1000(f, types, keys['population'])
    f = pd.concat([f, k], ignore_index=True)

    bench = group_stats(f)
    cbs = facts[(facts['row_type'] == 'summary') & facts['is_primary'] & facts['value'].notna()]
    cbs = cbs.pivot_table(index=['indicator_id', 'period_year'], columns='summary_group',
                          values='value', aggfunc='first')
    cbs.columns = [f'cbs_{c}' for c in cbs.columns]

    # ---- final catalog (with derived indicators) ----
    review = colmap.groupby('indicator_id')['review_needed'].sum().rename('columns_flagged')
    unit_dec = {d['indicator_id']: d for d in (load_yaml('unit_decisions.yaml') or [])}
    cat = catalog.merge(review, on='indicator_id', how='left')
    cat['unit_decision'] = cat['indicator_id'].map(
        lambda i: '' if i not in unit_dec else
        f"{unit_dec[i]['status']} {unit_dec[i].get('factors') or ''}".strip())
    der = cat[cat['measure_type'] == 'count'].copy()
    der['indicator_id'] = der['indicator_id'] + '_k'
    der['label_latest'] = der['label_latest'] + ' — ל-1,000 תושבים (נגזר)'
    der['measure_type'] = 'derived_per_1000'
    cat = pd.concat([cat, der], ignore_index=True)

    # ---- comparison for Eshkol authorities ----
    esh = f[f['eshkol'].notna()].copy()
    esh = esh.merge(ranks(f), on=['indicator_id', 'period_year', 'muni_code'], how='left')

    def pick(gtype, col, prefix, stats=('n', 'median', 'mean', 'p25', 'p75')):
        b = bench[bench['group_type'] == gtype][['indicator_id', 'period_year', 'group', *stats]]
        b = b.rename(columns={s: f'{prefix}_{s}' for s in stats})
        if col:
            esh[f'_{col}'] = esh[col].astype(str)
            return b.rename(columns={'group': f'_{col}'}), ['indicator_id', 'period_year', f'_{col}']
        return b.drop(columns='group'), ['indicator_id', 'period_year']

    for gtype, col, prefix, stats in [
            ('national', None, 'nat', ('n', 'median', 'mean', 'p25', 'p75', 'pop_weighted_mean')),
            ('ses', 'ses_cluster', 'ses', ('n', 'median', 'mean')),
            ('ses_latest', 'ses_cluster_latest', 'seslatest', ('n', 'median')),
            ('status', 'status', 'status', ('n', 'median')),
            ('ses_status', 'ses_status', 'sesstatus', ('n', 'median')),
            ('eshkol', 'eshkol', 'cluster', ('n', 'median', 'mean'))]:
        b, on = pick(gtype, col, prefix, stats)
        esh = esh.merge(b, on=on, how='left')
    esh = esh.drop(columns=[c for c in esh.columns if c.startswith('_')])
    esh = esh.merge(cbs, left_on=['indicator_id', 'period_year'], right_index=True, how='left')
    for ref in ('nat', 'ses'):
        esh[f'diff_{ref}_median'] = esh['value'] - esh[f'{ref}_median']
        esh[f'diff_{ref}_median_pct'] = esh[f'diff_{ref}_median'] / esh[f'{ref}_median'].abs() * 100
    esh = esh.merge(cat[['indicator_id', 'label_latest', 'measure_type', 'domain']],
                    on='indicator_id', how='left')
    names = dim.set_index('muni_code')['name']
    esh.insert(0, 'name', esh['muni_code'].map(names))
    lead = ['name', 'muni_code', 'eshkol', 'status', 'ses_cluster', 'ses_cluster_latest',
            'indicator_id', 'label_latest', 'measure_type', 'domain', 'period_year', 'data_period',
            'value', 'unit_hint', 'low_reliability', 'mapping_review',
            'nat_n', 'nat_median', 'nat_mean', 'nat_p25', 'nat_p75', 'nat_pop_weighted_mean',
            'cbs_national', 'pct_rank_national', 'diff_nat_median', 'diff_nat_median_pct',
            'ses_n', 'ses_median', 'ses_mean', 'pct_rank_ses', 'z_ses', 'diff_ses_median',
            'diff_ses_median_pct', 'seslatest_n', 'seslatest_median', 'status_n', 'status_median',
            'sesstatus_n', 'sesstatus_median', 'cluster_n', 'cluster_median', 'cluster_mean']
    for c in lead:
        if c not in esh.columns:
            esh[c] = np.nan
    esh = esh[lead].sort_values(['eshkol', 'name', 'indicator_id', 'period_year'])

    bench.to_parquet(_out('gold', 'benchmarks.parquet'), index=False)
    esh.to_parquet(_out('gold', 'comparison_eshkol.parquet'), index=False)
    cat.to_csv(_out('gold', 'indicator_catalog.csv'), index=False, encoding='utf-8-sig')
    write_workbook(esh[esh['eshkol'] == 'גליל מזרחי'], ay, dim, cat)
    print(f'benchmarks {len(bench):,} rows · comparison {len(esh):,} rows '
          f'({esh.muni_code.nunique()} authorities) · catalog {len(cat):,} indicators '
          f'({(cat.measure_type == "derived_per_1000").sum()} derived)')
    return bench, esh, cat


README_ROWS = [
    ('מה בקובץ', 'השוואה של 18 רשויות הגליל המזרחי לכל המדדים בקבצי "הרשויות המקומיות בישראל" של הלמ"ס, 2003–2024.'),
    ('השוואה - שנה אחרונה', 'לכל רשות ומדד: הערך בשנת הנתון האחרונה, מול הארץ ומול רשויות באותו אשכול חברתי-כלכלי.'),
    ('אשכול חברתי-כלכלי', 'ses_cluster = האשכול לפי המהדורה האחרונה שפורסמה עד שנת הנתון. '
                          'ses_cluster_latest = האשכול במהדורה האחרונה (2021), קבוצת השוואה קבועה לאורך השנים.'),
    ('חציון ארצי', 'nat_median = חציון כל הרשויות (ללא שקלול). nat_pop_weighted_mean = ממוצע משוקלל באוכלוסייה. '
                   'cbs_national = הנתון הארצי הרשמי של הלמ"ס, כשהקובץ מפרסם אותו (2022 ואילך). '
                   'הרשמי כולל גם אוכלוסייה שאינה בתחום רשות, ולכן שונה מממוצע הרשויות.'),
    ('אחוזונים', 'pct_rank_national / pct_rank_ses: 0–100, מיקום הרשות בין כל הרשויות / בין רשויות האשכול. '
                 'z_ses: מרחק מממוצע האשכול ביחידות סטיית תקן.'),
    ('מדדי ספירה', 'measure_type=count: ערך מוחלט (לא בר-השוואה בין רשויות בגדלים שונים). לכל מדד כזה יש גרסה '
                   'נגזרת ל-1,000 תושבים (מזהה עם _k).'),
    ('כיוון', 'הקובץ אינו קובע אם ערך גבוה "טוב" או "רע"; זה תלוי במדד.'),
    ('אמינות', 'low_reliability = אומדן עם טעות דגימה גבוהה (בסוגריים בקובץ המקור). '
               'mapping_review = העמודה הותאמה בין שנים באופן שעדיין דורש בדיקה בדף הבקרה.'),
    ('יחידות', 'הומרו לפי החלטות דף הבקרה (למשל אוכלוסייה 2003–2017 מאלפים). ראו etl/config/unit_decisions.yaml.'),
]


HEB_COLS = {
    'name': 'רשות', 'muni_code': 'סמל', 'eshkol': 'אשכול', 'status': 'מעמד',
    'ses_cluster': 'אשכול חב"כ (לשנת הנתון)', 'ses_cluster_latest': 'אשכול חב"כ (מהדורה אחרונה)',
    'indicator_id': 'מזהה מדד', 'label_latest': 'מדד', 'measure_type': 'סוג מדד', 'domain': 'תחום',
    'period_year': 'שנת נתון', 'data_period': 'תקופה', 'value': 'ערך', 'unit_hint': 'יחידה',
    'low_reliability': 'אומדן לא אמין', 'mapping_review': 'מיפוי לבדיקה',
    'nat_n': 'ארצי: מס\' רשויות', 'nat_median': 'ארצי: חציון', 'nat_mean': 'ארצי: ממוצע',
    'nat_p25': 'ארצי: רבעון 1', 'nat_p75': 'ארצי: רבעון 3', 'nat_pop_weighted_mean': 'ארצי: ממוצע משוקלל',
    'cbs_national': 'ארצי רשמי (למ"ס)', 'pct_rank_national': 'אחוזון ארצי',
    'diff_nat_median': 'פער מחציון ארצי', 'diff_nat_median_pct': 'פער מחציון ארצי (%)',
    'ses_n': 'אשכול חב"כ: מס\' רשויות', 'ses_median': 'אשכול חב"כ: חציון', 'ses_mean': 'אשכול חב"כ: ממוצע',
    'pct_rank_ses': 'אחוזון באשכול חב"כ', 'z_ses': 'ציון z באשכול חב"כ',
    'diff_ses_median': 'פער מחציון האשכול', 'diff_ses_median_pct': 'פער מחציון האשכול (%)',
    'seslatest_n': 'אשכול חב"כ אחרון: מס\' רשויות', 'seslatest_median': 'אשכול חב"כ אחרון: חציון',
    'status_n': 'אותו מעמד: מס\' רשויות', 'status_median': 'אותו מעמד: חציון',
    'sesstatus_n': 'אשכול×מעמד: מס\' רשויות', 'sesstatus_median': 'אשכול×מעמד: חציון',
    'cluster_n': 'גליל מזרחי: מס\' רשויות', 'cluster_median': 'גליל מזרחי: חציון',
    'cluster_mean': 'גליל מזרחי: ממוצע',
}


def write_workbook(eg, ay, dim, cat):
    path = _out('gold', 'eastern_galilee.xlsx')
    latest = eg.sort_values('period_year').groupby(['muni_code', 'indicator_id']).tail(1)
    latest = latest.sort_values(['domain', 'indicator_id', 'name'])
    eg_codes = dim.loc[dim['eshkol'] == 'גליל מזרחי', 'muni_code']
    a = ay[ay['muni_code'].isin(eg_codes)]
    prof = dim[dim['muni_code'].isin(eg_codes)][['name', 'muni_code', 'status', 'district', 'sector',
                                                  'settlement_form', 'first_year', 'other_names']]
    wide = {c: a.pivot_table(index='name', columns='year', values=c) for c in
            ('population', 'ses_cluster', 'periphery_cluster')}
    used = cat[cat['indicator_id'].isin(eg['indicator_id'].unique())]
    with pd.ExcelWriter(path, engine='openpyxl') as xw:
        pd.DataFrame(README_ROWS, columns=['נושא', 'הסבר']).to_excel(xw, sheet_name='קרא אותי', index=False)
        prof.to_excel(xw, sheet_name='רשויות', index=False)
        wide['population'].round(0).to_excel(xw, sheet_name='אוכלוסייה לפי שנה')
        wide['ses_cluster'].to_excel(xw, sheet_name='אשכול חברתי-כלכלי לפי שנה')
        wide['periphery_cluster'].to_excel(xw, sheet_name='אשכול פריפריאליות לפי שנה')
        latest.round(3).rename(columns=HEB_COLS).to_excel(xw, sheet_name='השוואה - שנה אחרונה', index=False)
        used.to_excel(xw, sheet_name='מדדים', index=False)
        for ws in xw.book.worksheets:
            ws.sheet_view.rightToLeft = True
            ws.freeze_panes = 'B2'
            if ws.max_row > 1:
                ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                width = max(len(str(c.value or '')) for c in list(col)[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width * 0.9), 60)


if __name__ == '__main__':
    main()

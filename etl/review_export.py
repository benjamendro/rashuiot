"""Export stage-2 drafts to review/review_data.json for the interactive review page.

Usage:  python -m etl.review_export      (after python -m etl.run)

Unit suggestions are computed, not hand-written: for every year, the median over
authorities of value[latest year] / value[year] gives that year's scale relative to
the latest year; rounded to a power of ten, a non-zero exponent means "multiply this
year by 10^k to match the latest year". The reviewer accepts or overrides it.
"""

import json
import math
import os

import numpy as np
import pandas as pd

from .extract import load_config
from .matching import EshkolMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
OUT = os.path.join(ROOT, 'review', 'review_data.json')
SAMPLE_CODE = 8000                          # צפת: in every year, East Galilee


def _num(v, digits=6):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return float(f'{v:.{digits}g}')


def _scale_vs_latest(vals, years):
    """{year: power-of-ten exponent k such that value[year] * 10^k ~ value[latest]}."""
    latest = years[-1]
    ref = vals[vals['year'] == latest].groupby('muni_code')['value'].first()
    out = {}
    for y in years:
        cur = vals[vals['year'] == y].groupby('muni_code')['value'].first()
        j = pd.concat([ref, cur], axis=1, keys=['r', 'c']).dropna()
        j = j[(j['r'] != 0) & (j['c'] != 0)]
        if len(j) < 5:
            out[y] = None
            continue
        r = float((j['r'] / j['c']).median())
        out[y] = {'ratio': _num(r, 4), 'k': int(round(math.log10(r))) if r > 0 else None}
    return out


def main():
    colmap = pd.read_csv(os.path.join(DATA, 'silver', 'column_map_DRAFT.csv'))
    from .release import mapping_confidence
    colmap['mapping_confidence'] = mapping_confidence(colmap)   # only medium/low go to review
    catalog = pd.read_csv(os.path.join(DATA, 'silver', 'indicator_catalog_DRAFT.csv'))
    units = pd.read_csv(os.path.join(DATA, 'silver', 'units_review.csv')).fillna('')
    cells = pd.read_parquet(os.path.join(DATA, 'bronze', 'cells.parquet'))
    files = pd.read_csv(os.path.join(DATA, 'qa', 'file_validation.csv'))
    cfg = load_config(os.path.join(ROOT, 'etl', 'config', 'sources.yaml'))

    a = cells[(cells['row_type'] == 'authority') & cells['value'].notna()]
    a = a.merge(colmap[['year', 'sheet', 'col', 'indicator_id']], on=['year', 'sheet', 'col'])

    matcher = EshkolMatcher()
    eg = matcher.targets[(matcher.targets['entity_type'] == 'רשות') &
                         (matcher.targets['affiliation'] == 'גליל מזרחי')]
    eg_codes = {int(c): n for c, n in zip(eg['code'], eg['eshkol_name'])}

    sheets = sorted(colmap['sheet'].unique())
    sheet_idx = {s: i for i, s in enumerate(sheets)}
    sample = a[a['muni_code'] == SAMPLE_CODE].groupby(['year', 'sheet', 'col'])['value'].first()

    # ---- units ------------------------------------------------------------------
    unit_items = []
    for _, u in units.iterrows():
        iid = u['indicator_id']
        grp = colmap[colmap['indicator_id'] == iid]
        years = sorted(grp['year'].unique())
        vals = a[a['indicator_id'] == iid]
        scale = _scale_vs_latest(vals, years)
        per_year = []
        for y in years:
            g = grp[grp['year'] == y]
            v = vals[vals['year'] == y]
            per_year.append({
                'year': int(y),
                'unit': ' + '.join(sorted({x for x in g['unit_hint'].fillna('') if x})),
                'label': g['levels'].iloc[0],
                'period': str(g['data_period'].iloc[0]),
                'median': _num(v['value'].median()),
                'sample': _num(v[v['muni_code'] == SAMPLE_CODE]['value'].iloc[0])
                if (v['muni_code'] == SAMPLE_CODE).any() else None,
                'scale': scale.get(y),
            })
        # suggest only clear order-of-magnitude scale changes (>= x100) on scale jumps;
        # ratios of signed or volatile measures (deficits, pipe laying) mean nothing
        fix = {str(p['year']): p['scale']['k'] for p in per_year
               if u['severity'] == 'scale_jump' and p['scale'] and p['scale']['k'] is not None
               and abs(p['scale']['k']) >= 2}
        eg_rows = []
        for code, name in eg_codes.items():
            s = vals[vals['muni_code'] == code].groupby('year')['value'].first()
            if len(s):
                eg_rows.append({'name': name, 'values': {str(int(y)): _num(v) for y, v in s.items()}})
        unit_items.append({
            'id': iid, 'severity': u['severity'], 'label': u['label_latest'],
            'jumps': u['scale_jumps'], 'contradicts': u['label_contradicts_values'],
            'years': per_year, 'suggest': fix, 'eg': eg_rows,
        })

    # ---- mapping ----------------------------------------------------------------
    inds = []
    for _, c in catalog.iterrows():
        grp = colmap[colmap['indicator_id'] == c['indicator_id']].sort_values(['year', 'part', 'col'])
        cols = []
        for r in grp.itertuples():
            cols.append({
                'y': int(r.year), 's': sheet_idx[r.sheet], 'c': int(r.col), 'part': r.part,
                'label': r.levels, 'period': str(r.data_period), 'unit': r.unit_hint if isinstance(r.unit_hint, str) else '',
                'm': r.match_method, 'score': _num(r.match_score, 3),
                'corr': _num(r.corr_with_newer_year, 3),
                'median': _num(r.median), 'sample': _num(sample.get((r.year, r.sheet, r.col), np.nan)),
                'why': (f"[{r.mapping_confidence}] {r.review_reason}" if isinstance(r.review_reason, str)
                        and r.review_reason else f'[{r.mapping_confidence}]') if r.mapping_confidence != 'high' else '',
                'n': int(r.n_numeric) if not pd.isna(r.n_numeric) else 0,
            })
        inds.append({
            'id': c['indicator_id'], 'domain': c['domain'], 'label': c['label_latest'],
            'category': c['category'] if isinstance(c['category'], str) else '',
            'kind': c['value_kind'], 'cols': cols,
        })

    payload = {
        'generated_from': 'data/silver/*_DRAFT.csv + data/bronze/cells.parquet',
        'sample_authority': 'צפת',
        'years_present': sorted(int(y) for y in colmap['year'].unique()),
        'years_missing': cfg.get('missing_years', []),
        'files': files.fillna('').to_dict('records'),
        'sheets': sheets,
        'units': unit_items,
        'indicators': inds,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    print(f'wrote {OUT}: {len(unit_items)} unit items, {len(inds)} indicators, '
          f'{sum(len(i["cols"]) for i in inds)} columns, {os.path.getsize(OUT) / 1e6:.2f} MB')


if __name__ == '__main__':
    main()

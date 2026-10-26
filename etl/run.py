"""Run stages 0-2.  Usage:  python -m etl.run

Outputs (data/):
  qa/file_validation.csv        every Excel file: configured year vs title year, duplicates
  qa/eshkol_gate.csv            Eshkol authorities x years, how each was matched
  qa/extraction_issues.csv      code-resolution notes (fuzzy / alias / unresolved)
  qa/report.md                  human-readable summary
  bronze/cells.parquet          every cell, long format, values as published
  bronze/summary_cells.parquet  CBS national / per-status totals (transposed sheets)
  bronze/authority_registry.csv authorities per year with canonical codes
  silver/column_map_DRAFT.csv   every source column -> indicator_id (+ method, score)
  silver/indicator_catalog_DRAFT.csv
  silver/units_review.csv       unit/scale changes for human decision (nothing converted)
"""

import os
import sys

import pandas as pd

from . import harmonize
from .extract import extract_summary_sheet, extract_year, load_config
from .validate import GateError, eshkol_gate, validate_files

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data')


def _out(*parts):
    path = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def main():
    cfg = load_config(os.path.join(ROOT, 'etl', 'config', 'sources.yaml'))

    # ---- Stage 0a: files --------------------------------------------------------
    files, problems = validate_files(cfg, ROOT)
    files.to_csv(_out('qa', 'file_validation.csv'), index=False, encoding='utf-8-sig')
    if problems:
        raise GateError('File validation failed:\n  ' + '\n  '.join(problems))

    # ---- Stage 1: extraction ----------------------------------------------------
    parts = {'cells': [], 'columns': [], 'registry': [], 'issues': [], 'summary': []}
    for year, ycfg in sorted(cfg['years'].items()):
        print(f'extracting {year} ({ycfg["file"]})', flush=True)
        r = extract_year(year, ycfg, ROOT, aliases=cfg.get('name_aliases'))
        for k in ('cells', 'columns', 'registry', 'issues'):
            parts[k].append(r[k])
        parts['summary'].append(extract_summary_sheet(year, ycfg, ROOT))
    cells = pd.concat(parts['cells'], ignore_index=True)
    columns = pd.concat(parts['columns'], ignore_index=True)
    registry = pd.concat(parts['registry'], ignore_index=True)
    issues = pd.concat([i for i in parts['issues'] if len(i)], ignore_index=True) \
        if any(len(i) for i in parts['issues']) else parts['issues'][0]
    summary = pd.concat(parts['summary'], ignore_index=True)

    # ---- Stage 0b: Eshkol gate (needs the registry) --------------------------------
    gate, gate_problems = eshkol_gate(registry)
    gate.to_csv(_out('qa', 'eshkol_gate.csv'), index=False, encoding='utf-8-sig')
    issues.to_csv(_out('qa', 'extraction_issues.csv'), index=False, encoding='utf-8-sig')
    unresolved = issues[issues['issue'].isin(['unresolved_code', 'unknown_status'])]
    if gate_problems or len(unresolved):
        msgs = gate_problems + [f"{r.year} {r.sheet} row {r.row}: {r['name']} ({r.raw_code}) {r.detail}"
                                for _, r in unresolved.iterrows()]
        raise GateError('Matching gate failed - stopping for review:\n  ' + '\n  '.join(msgs))

    cells.to_parquet(_out('bronze', 'cells.parquet'), index=False)
    summary.to_parquet(_out('bronze', 'summary_cells.parquet'), index=False)
    registry.to_csv(_out('bronze', 'authority_registry.csv'), index=False, encoding='utf-8-sig')

    # ---- Stage 2: harmonization drafts -------------------------------------------
    print('matching columns across years', flush=True)
    overrides = harmonize.load_overrides(os.path.join(ROOT, 'etl', 'config', 'column_overrides.csv'))
    colmap, _, ov_warnings = harmonize.match_columns(columns, overrides)
    for w in ov_warnings:
        print('WARNING', w)
    stats = harmonize.column_stats(cells)
    colmap = colmap.merge(stats, on=['year', 'sheet', 'col'], how='left')
    colmap = colmap.merge(harmonize.continuity(colmap, cells), on=['year', 'sheet', 'col'], how='left')
    colmap['review_reason'] = harmonize.review_reasons(colmap)
    colmap['review_needed'] = colmap['review_reason'] != ''
    keep = ['indicator_id', 'year', 'file', 'sheet', 'domain', 'part', 'col', 'levels',
            'data_period', 'period_source', 'unit_hint', 'match_method', 'match_score',
            'matched_to', 'review_needed', 'review_reason', 'corr_with_newer_year', 'n_cells', 'n_numeric', 'n_text', 'n_dash',
            'n_not_available', 'n_low_reliability', 'median', 'p10', 'p90']
    colmap = colmap[keep].sort_values(['indicator_id', 'year', 'part'])
    colmap.to_csv(_out('silver', 'column_map_DRAFT.csv'), index=False, encoding='utf-8-sig')
    cat = harmonize.catalog(colmap)
    cat.to_csv(_out('silver', 'indicator_catalog_DRAFT.csv'), index=False, encoding='utf-8-sig')
    units = harmonize.units_review(colmap, cells)
    units.to_csv(_out('silver', 'units_review.csv'), index=False, encoding='utf-8-sig')

    write_report(cfg, files, registry, gate, issues, cells, summary, colmap, cat, units)
    print('done. STOP: units are not converted - see data/silver/units_review.csv')


def write_report(cfg, files, registry, gate, issues, cells, summary, colmap, cat, units):
    L = ['# QA report - stages 0-2', '']
    L += ['## Stage 0 - input files', '',
          '| file | configured year | title year | status | note |', '|---|---|---|---|---|']
    for _, r in files.iterrows():
        cy = '' if pd.isna(r.configured_year) else int(r.configured_year)
        L.append(f"| {r.file} | {cy} | {r.title_year} | {r.status} | "
                 f"{(r.note or '').strip()[:140]} |")
    L += ['', f"Missing years (not in repo): {', '.join(map(str, cfg.get('missing_years', [])))}", '']

    L += ['## Stage 0 - Eshkol matching gate', '',
          'All Eshkol authorities were found in every year by code **and** name '
          '(regional-council codes normalized to 5500+n).', '']
    eg = gate[gate['cluster'] == 'גליל מזרחי']
    nonexact = gate[~gate['match_status'].eq('exact_or_sanitized')]
    L.append(f"- East Galilee: {eg['eshkol_name'].nunique()} authorities x "
             f"{eg['year'].nunique()} years = {len(eg)} matches, "
             f"{(eg['match_status'] == 'MISSING').sum()} missing.")
    for _, r in nonexact.drop_duplicates(['eshkol_name', 'source_name', 'match_status']).iterrows():
        L.append(f"- {r.eshkol_name} ← '{r.source_name}' ({r.match_status})")
    L.append('')

    L += ['## Stage 1 - extraction', '',
          '| year | authorities | columns | cells | dash (-) | not available (..) | low reliability ( ) |',
          '|---|---|---|---|---|---|---|']
    for y, g in cells.groupby('year'):
        L.append(f"| {y} | {registry[registry.year == y].shape[0]} | "
                 f"{colmap[colmap.year == y].shape[0]} | {len(g):,} | {(g.flag == 'dash').sum():,} | "
                 f"{(g.flag == 'not_available').sum():,} | {(g.flag == 'low_reliability').sum():,} |")
    L += ['', f"Summary rows (national/status totals): {len(summary):,} cells from transposed sheets "
          f"(2014-2021) + {(cells.row_type == 'summary').sum():,} cells from in-sheet rows (2022-2024).", '']
    if len(issues):
        L += ['Code-resolution notes:', '']
        for _, r in issues.iterrows():
            L.append(f"- {r.year} / {r.sheet}: '{r['name']}' ({r.raw_code}) → {r.issue}: {r.detail}")
        L.append('')

    L += ['## Stage 2 - cross-year indicator matching (DRAFT, for review)', '']
    mc = colmap['match_method'].value_counts()
    L += ['| method | columns |', '|---|---|'] + [f'| {k} | {v} |' for k, v in mc.items()]
    L += ['', f"Indicators: {len(cat)}; in all {colmap.year.nunique()} years: "
          f"{(cat.n_years == colmap.year.nunique()).sum()}; flagged for review: {cat.review_needed.sum()}.", '']
    L += ['## Stage 2 - units (STOPPED HERE, nothing converted)', '',
          'See `silver/units_review.csv`; column `decision` is for you.', '']
    if len(units):
        L += ['| severity | indicators |', '|---|---|'] + \
             [f'| {k} | {v} |' for k, v in units['severity'].value_counts().items()] + ['']
        for _, r in units[units['severity'] != 'unit_label_partial'].iterrows():
            extra = f" — **label contradicts values: {r.label_contradicts_values}**" \
                if r.label_contradicts_values else ''
            L.append(f"- **{r.indicator_id}** [{r.severity}] {r.label_latest}: "
                     f"{r.scale_jumps or r.unit_by_year}{extra}")
    with open(_out('qa', 'report.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')


if __name__ == '__main__':
    try:
        main()
    except GateError as e:
        print(f'\nHALT: {e}', file=sys.stderr)
        sys.exit(2)

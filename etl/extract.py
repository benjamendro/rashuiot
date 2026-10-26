"""Stage 1 - Bronze: every cell of every configured sheet, in long format.

All ~255 authorities are kept (national benchmarks need them), plus the CBS summary
rows (national / per municipal status). Values are parsed but NOT converted: units
stay exactly as published.
"""

import difflib
import os
import re
from functools import lru_cache

import openpyxl
import pandas as pd
import yaml

from .common import (SUMMARY_ROW_GROUPS, STATUS_NORMALIZE, clean_text, parse_code,
                     parse_value, normalize_code)
from .headers import build_header_paths, single_row_headers
from .matching import sanitize

NAME_COL, CODE_COL = 0, 1
FUZZY_CUTOFF = 0.85


def load_config(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=4)
def _workbook(path):
    return openpyxl.load_workbook(path, data_only=True)


def read_grid(path, sheet):
    """Return (rows as list-of-lists, openpyxl worksheet or None for .xls)."""
    if path.lower().endswith('.xlsx'):
        ws = _workbook(path)[sheet]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        width = max((len(r) for r in rows), default=0)
        rows = [r + [None] * (width - len(r)) for r in rows]
        return rows, ws
    df = pd.read_excel(path, sheet_name=sheet, header=None, dtype=object)
    return df.where(df.notna(), None).values.tolist(), None


def _trim_width(rows):
    """Drop trailing columns that are empty in the header and data area."""
    width = len(rows[0]) if rows else 0
    while width > 0 and all(clean_text(r[width - 1]) == '' for r in rows):
        width -= 1
    return width


def sheet_headers(scfg, rows, ws, width):
    if len(scfg['header_rows']) == 1:
        return single_row_headers(rows[scfg['header_rows'][0]][:width])
    return build_header_paths(ws, scfg['header_rows'], scfg.get('period_row'),
                              scfg.get('main_row'), width, leaf_rows=scfg.get('leaf_rows', ()))


def iter_data_rows(rows, data_start):
    """Yield (row_idx, name, raw_code, row_type, summary_group)."""
    for i in range(data_start, len(rows)):
        name = clean_text(rows[i][NAME_COL]).rstrip('*').strip()   # '*' marks a footnote
        code = parse_code(rows[i][CODE_COL])
        if name and code is not None:
            yield i, name, code, 'authority', None
        elif name in SUMMARY_ROW_GROUPS and code is None:
            yield i, name, None, 'summary', SUMMARY_ROW_GROUPS[name]


class Registry:
    """Authorities of one year, built from the sheets that carry municipal status."""

    def __init__(self, year, aliases=None):
        self.year = year
        self.aliases = {sanitize(k): sanitize(v) for k, v in (aliases or {}).items()}
        self.records = []          # dicts: code, raw_code, name, status, district

    def add(self, raw_code, name, status, district):
        code = normalize_code(raw_code, status)
        self.records.append({'year': self.year, 'muni_code': code, 'raw_code': raw_code,
                             'name': name, 'status': status, 'district': district})
        return code

    def resolve(self, raw_code, name):
        """Map (raw code, name) from a sheet without a status column to a canonical code.

        Codes alone are ambiguous (26 = ראש פינה and also RC מטה יהודה before 2024),
        so the name is always used to confirm. Returns (code, method) or (None, reason).
        """
        cands = [r for r in self.records if raw_code in (r['raw_code'], r['muni_code'])]
        if not cands:
            return None, 'code_not_in_registry'
        n = sanitize(name)
        exact = [r for r in cands if sanitize(r['name']) == n]
        if len(exact) == 1:
            return exact[0]['muni_code'], 'code+name'
        alias = self.aliases.get(n)
        aliased = [r for r in cands if alias and sanitize(r['name']) == alias]
        if len(aliased) == 1:
            return aliased[0]['muni_code'], 'code+name_alias'
        scored = sorted(((difflib.SequenceMatcher(None, n, sanitize(r['name'])).ratio(), r)
                         for r in cands), key=lambda t: -t[0])
        if scored[0][0] >= FUZZY_CUTOFF and (len(scored) == 1 or scored[1][0] < FUZZY_CUTOFF):
            return scored[0][1]['muni_code'], f'code+fuzzy_name_{scored[0][0]:.2f}'
        if len(cands) == 1:
            return None, f"name_mismatch: registry has '{cands[0]['name']}'"
        return None, 'ambiguous_code'


def extract_year(year, ycfg, root, aliases=None):
    path = os.path.join(root, ycfg['file'])
    registry = Registry(year, aliases)
    cell_frames, col_frames, issues = [], [], []

    # registry sheets first, so other sheets can resolve codes against them
    ordered = sorted(ycfg['sheets'], key=lambda s: not s.get('registry', False))
    for scfg in ordered:
        rows, ws = read_grid(path, scfg['name'])
        width = _trim_width(rows)
        headers = sheet_headers(scfg, rows, ws, width)
        data_start = max(scfg['header_rows'] + [scfg.get('period_row') or 0]) + 1

        col_frames.append(pd.DataFrame([{
            'year': year, 'file': ycfg['file'], 'sheet': scfg['name'], 'domain': scfg['domain'],
            'part': scfg['part'], 'col': c, 'levels': ' › '.join(h['levels']),
            'n_levels': len(h['levels']), 'period_row_label': h['period'],
            'sheet_data_period': scfg.get('data_period', ''),
        } for c, h in enumerate(headers) if c not in (NAME_COL, CODE_COL)]))

        recs = []
        for i, name, raw_code, row_type, group in iter_data_rows(rows, data_start):
            row = rows[i]
            code, status = None, None
            if row_type == 'authority':
                if scfg.get('registry'):
                    status = STATUS_NORMALIZE.get(clean_text(row[scfg['status_col']]))
                    if status is None:
                        issues.append({'year': year, 'sheet': scfg['name'], 'row': i, 'name': name,
                                       'raw_code': raw_code, 'issue': 'unknown_status',
                                       'detail': clean_text(row[scfg['status_col']])})
                    code = registry.add(raw_code, name, status, clean_text(row[2]))
                else:
                    code, how = registry.resolve(raw_code, name)
                    if code is None:
                        issues.append({'year': year, 'sheet': scfg['name'], 'row': i, 'name': name,
                                       'raw_code': raw_code, 'issue': 'unresolved_code', 'detail': how})
                        continue
                    if how != 'code+name':
                        kind = 'resolved_alias' if how == 'code+name_alias' else 'resolved_fuzzy'
                        issues.append({'year': year, 'sheet': scfg['name'], 'row': i, 'name': name,
                                       'raw_code': raw_code, 'issue': kind, 'detail': how})
            for c in range(width):
                if c in (NAME_COL, CODE_COL):
                    continue
                value, text, flag = parse_value(row[c])
                if flag == 'blank':
                    continue
                recs.append((year, scfg['name'], scfg['domain'], scfg['part'], c, i, row_type,
                             group, code, raw_code, name, value, text, flag,
                             clean_text(row[c]) if flag else None))
        cell_frames.append(pd.DataFrame.from_records(recs, columns=[
            'year', 'sheet', 'domain', 'part', 'col', 'row', 'row_type', 'summary_group',
            'muni_code', 'raw_code', 'muni_name', 'value', 'value_text', 'flag', 'raw']))

    cells = pd.concat(cell_frames, ignore_index=True)
    cells['muni_code'] = cells['muni_code'].astype('Int64')
    cells['raw_code'] = cells['raw_code'].astype('Int64')
    return {
        'cells': cells,
        'columns': pd.concat(col_frames, ignore_index=True),
        'registry': pd.DataFrame(registry.records),
        'issues': pd.DataFrame(issues, columns=['year', 'sheet', 'row', 'name', 'raw_code',
                                                'issue', 'detail']),
    }


# ---- transposed summary sheets ("סיכומים לפי מעמד מוניציפלי", "רשויות מקומיות") ----

_GROUP_HEADERS = [('כלל ארצי', 'national'), ('עיריות', 'municipality'),
                  ('מועצות מקומיות', 'local_council'), ('מועצות אזוריות', 'regional_council')]


def extract_summary_sheet(year, ycfg, root):
    """National / per-status totals published as a separate, transposed sheet."""
    sheet = ycfg.get('summary_sheet')
    if not sheet:
        return pd.DataFrame()
    rows, _ = read_grid(os.path.join(root, ycfg['file']), sheet)
    hdr_row = next(i for i, r in enumerate(rows[:6])
                   if any(clean_text(v).startswith('כלל ארצי') for v in r))
    group_cols = {}
    for c, v in enumerate(rows[hdr_row]):
        t = re.sub(r'\d+$', '', clean_text(v))
        for prefix, g in _GROUP_HEADERS:
            if t.startswith(prefix) and g not in group_cols:
                group_cols[g] = c
    label_col = group_cols['national'] - 1
    section = ''
    recs = []
    for i in range(hdr_row + 1, len(rows)):
        r = rows[i]
        if clean_text(r[0]).startswith('מקרא'):
            break
        section = clean_text(r[label_col - 1]) or section if label_col >= 1 else ''
        label = clean_text(r[label_col])
        if not label:
            continue
        for g, c in group_cols.items():
            value, text, flag = parse_value(r[c])
            if flag == 'blank':
                continue
            recs.append({'year': year, 'sheet': sheet, 'row': i, 'section': section,
                         'label': label, 'summary_group': g, 'value': value,
                         'value_text': text, 'flag': flag, 'raw': clean_text(r[c]) if flag else None})
    return pd.DataFrame(recs)

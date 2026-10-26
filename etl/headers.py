"""Reconstruct CBS multi-row column headers.

CBS group labels span several columns, but how the span is encoded differs by file:
  * 2017-2018: real merged cells.
  * 2020+: no merges; the label sits (often centred) somewhere inside a block that is
    delimited by cell borders, e.g. "לפי פרקי תקציב" is written in col 11 of a block
    spanning cols 7-18.
So for every header row we resolve spans by: merged ranges -> border-delimited
blocks -> hierarchical forward-fill (reset wherever a higher header row starts a new
label). The result is one label path per column.
"""

from .common import clean_text, is_blank


def _border_blocks(ws, row, ncols):
    """Split columns [0, ncols) into blocks using left/right borders of `row` (1-based).

    Returns a list of (start, end) inclusive 0-based column ranges, or None when the
    row has no vertical borders at all (then borders tell us nothing).
    """
    lefts, rights = [], []
    any_border = False
    for c in range(ncols):
        b = ws.cell(row=row, column=c + 1).border
        lft, rgt = bool(b.left and b.left.style), bool(b.right and b.right.style)
        lefts.append(lft)
        rights.append(rgt)
        any_border = any_border or lft or rgt
    if not any_border:
        return None
    blocks, start = [], 0
    for c in range(ncols):
        last = c == ncols - 1
        if last or rights[c] or lefts[c + 1]:
            blocks.append((start, c))
            start = c + 1
    return blocks


def _apply_merges(ws, row, ncols, out):
    covered = [False] * ncols
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= row <= rng.max_row:
            top_left = clean_text(ws.cell(row=rng.min_row, column=rng.min_col).value)
            for c in range(rng.min_col - 1, min(rng.max_col, ncols)):
                out[c] = top_left
                covered[c] = True
    return covered


def _spread_row(ws, row, ncols, raw, higher_new):
    """Spread the labels of one group header row across their spans (merges, then borders).

    higher_new[c] is True where a higher header row starts a new label at column c.
    """
    out = list(raw)
    covered = _apply_merges(ws, row, ncols, out)
    blocks = _border_blocks(ws, row, ncols)
    if blocks is None:
        return out, False
    carry = ''
    for s, e in blocks:
        if any(covered[s:e + 1]):
            carry = out[e]
            continue
        labels = [(c, out[c]) for c in range(s, e + 1) if out[c]]
        if len(labels) == 1:
            for c in range(s, e + 1):
                out[c] = labels[0][1]
        elif len(labels) > 1:              # several labels in one block: ffill inside it
            cur = ''
            for c in range(s, e + 1):
                cur = out[c] or cur
                out[c] = cur
        else:
            # A block without a label (columns boxed one by one) continues the group on
            # its left, unless a higher header row starts a new group here.
            if higher_new[s]:
                carry = ''
            for c in range(s, e + 1):
                out[c] = carry
        carry = out[e]
    return out, True


def build_header_paths(ws, header_rows, period_row, main_row, ncols, leaf_rows=(),
                       first_data_col=2):
    """Return per-column dicts {levels: [..], period: str} for an openpyxl worksheet.

    header_rows / period_row / main_row / leaf_rows are 0-based row indices.
    leaf_rows hold per-column sub-labels: they spread only through real merges.
    The main row spreads only to its own sub-columns (filled from the left below).
    """
    raw = {r: [clean_text(ws.cell(row=r + 1, column=c + 1).value) for c in range(ncols)]
           for r in sorted(set(header_rows) | ({period_row} if period_row is not None else set()))}

    label_rows = [r for r in header_rows if r != period_row]
    filled = {}
    for i, r in enumerate(label_rows):
        if r in leaf_rows or r == main_row:
            spread = list(raw[r])
            _apply_merges(ws, r + 1, ncols, spread)
            filled[r] = spread
            continue
        higher_new = [any(raw[h][c] for h in label_rows[:i]) for c in range(ncols)]
        spread, had_borders = _spread_row(ws, r + 1, ncols, raw[r], higher_new)
        if not had_borders:
            # Hierarchical ffill: carry a label right until a higher row starts a new one
            cur = ''
            for c in range(ncols):
                higher_new = any(raw[h][c] for h in label_rows[:i])
                if spread[c]:
                    cur = spread[c]
                elif higher_new:
                    cur = ''
                spread[c] = cur
        filled[r] = spread

    # Sub-columns under a main header (main-row cell blank) belong to the group on
    # their left. Fill main row the same way when borders did not resolve it.
    if main_row is not None and main_row in filled:
        cur = ''
        for c in range(first_data_col, ncols):
            if raw[main_row][c]:
                cur = raw[main_row][c]
            elif not filled[main_row][c]:
                filled[main_row][c] = cur

    out = []
    for c in range(ncols):
        levels = []
        for r in label_rows:
            lab = filled[r][c]
            if lab and (not levels or levels[-1] != lab):
                levels.append(lab)
        period = ''
        if period_row is not None:
            period = raw[period_row][c]
            if not period and main_row is not None and not raw[main_row][c]:
                # sub-column: inherit the period of its group
                for cc in range(c - 1, first_data_col - 1, -1):
                    if raw[period_row][cc]:
                        period = raw[period_row][cc]
                        break
                    if raw[main_row][cc]:
                        break
        out.append({'levels': levels, 'period': period})
    return out


def single_row_headers(values):
    """Pre-2017 sheets: one header row, the period is embedded in the label."""
    return [{'levels': [clean_text(v)] if not is_blank(v) else [], 'period': ''} for v in values]

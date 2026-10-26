"""Shared helpers: text normalization, CBS value parsing, authority-code normalization."""

import re
import math

import pandas as pd

# CBS regional councils were numbered 1-2 digits until the 2023 file; the 2024 file
# switched to 5500 + number (e.g. הגליל העליון 01 -> 5501). Verified for all 54 RCs.
RC_CODE_OFFSET = 5500

# Rows CBS puts above the authorities from 2022 onward (national total + per status).
SUMMARY_ROW_GROUPS = {
    'כלל ארצי': 'national',
    'עיריות': 'municipality',
    'עיריות סך הכל': 'municipality',
    'מועצות מקומיות': 'local_council',
    'מועצות מקומיות סך הכל': 'local_council',
    'מועצות אזוריות': 'regional_council',
    'מועצות אזוריות סך הכל': 'regional_council',
}

STATUS_NORMALIZE = {
    'עירייה': 'עירייה', 'עיריה': 'עירייה',
    'מועצה מקומית': 'מועצה מקומית',
    'מועצה אזורית': 'מועצה אזורית',
}


def is_blank(v):
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return isinstance(v, str) and v.strip() == ''


def clean_text(v):
    """Collapse whitespace/newlines; '' for blanks."""
    if is_blank(v):
        return ''
    return re.sub(r'\s+', ' ', str(v)).strip()


_RANGE_RE = re.compile(r'\b(\d[\d,]*)-(\d[\d,]*)\b')


def _ascending_range(m):
    """CBS writes ranges both ways ('4-0', '4,999-2,000', '2,000-4,999'): sort them."""
    a, b = m.group(1), m.group(2)
    try:
        if float(a.replace(',', '')) > float(b.replace(',', '')):
            a, b = b, a
    except ValueError:
        pass
    return f'{a}-{b}'


def norm_label(s):
    """Normalize a header label for cross-year comparison.

    Unifies quote/geresh variants, dashes, spelling variants CBS alternates between
    years, and drops footnote digits glued to Hebrew words ("שם הרשות1").
    """
    s = clean_text(s)
    s = s.replace('״', '"').replace("''", '"').replace('׳', "'").replace('`', "'")
    s = s.replace('“', '"').replace('”', '"').replace('’', "'")
    s = re.sub(r'[‐-―]', '-', s)
    s = re.sub(r'(?<=[א-ת])\d+\b', '', s)          # footnote marks: 'הכל2' -> 'הכל'
    s = s.replace('מוניציפאלי', 'מוניציפלי').replace('עיריה', 'עירייה')
    s = re.sub(r'סך הכול|סך הכל|סה"כ|סה״כ', 'סה"כ', s)
    s = re.sub(r'(?<=\S)-\s+|\s+-(?=\S)', ' - ', s)   # 'א -ב' / 'א- ב' -> 'א - ב'
    s = _RANGE_RE.sub(_ascending_range, s)
    s = re.sub(r'\s+', ' ', s).strip(' .:')
    return s


# Data-period tokens embedded in labels: 2014, 2020-2024, 2024-25, 2023/24, תשפ"ד
_PERIOD_RE = re.compile(
    r'(?:תש[א-ת]"?[א-ת]\s*)?\b(?:19|20)\d{2}(?:\s*[-/]\s*(?:19|20)?\d{2})?\b'
    r'|\bתש[א-ת]"[א-ת]\b'
)


def extract_period(s):
    """Return the period tokens found in a label ('' if none)."""
    found = [m.group(0).strip() for m in _PERIOD_RE.finditer(clean_text(s))]
    return ' '.join(found)


def strip_period(s):
    """Remove period tokens and the words that typically wrap them."""
    s = _PERIOD_RE.sub(' ', clean_text(s))
    s = re.sub(r'\bבסוף\s+(?=\(|$|-|\s)', 'בסוף השנה ', s)   # 'בסוף 2014' -> 'בסוף השנה'
    s = re.sub(r'\(\s*\)', ' ', s)
    s = re.sub(r'\s*-\s*$', '', s)
    return re.sub(r'\s+', ' ', s).strip(' -')


# ---- CBS cell values ---------------------------------------------------------------

_NUM_RE = re.compile(r'^-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$')
_PAREN_RE = re.compile(r'^\(\s*(-?\d+(?:\.\d+)?)\s*\)$')


def parse_value(v):
    """Parse a CBS cell into (value: float|None, text: str|None, flag: str|None).

    CBS conventions (see the legend in each file):
      '-'      -> flag 'dash'            nil / no cases / not applicable
      '..'     -> flag 'not_available'   data not available or suppressed
      '( 2.3)' -> value 2.3, flag 'low_reliability'  (high sampling/relative error)
    Anything else non-numeric is kept as text (district, status, category labels).
    """
    if is_blank(v):
        return None, None, 'blank'
    if isinstance(v, bool):
        return float(v), None, None
    if isinstance(v, (int, float)):
        return float(v), None, None
    s = clean_text(v)
    t = s.replace(',', '')
    if _NUM_RE.match(t):
        return float(t), None, None
    if s in ('-', '–', '—'):
        return None, None, 'dash'
    if s in ('..', '...', '. .'):
        return None, None, 'not_available'
    m = _PAREN_RE.match(t)
    if m:
        return float(m.group(1)), None, 'low_reliability'
    return None, s, 'text'


def parse_code(v):
    """Raw authority code (int or zero-padded text like '0026') -> int, or None."""
    if is_blank(v):
        return None
    s = clean_text(v)
    try:
        f = float(s)
    except ValueError:
        return None
    if f != int(f) or f < 0:
        return None
    return int(f)


def normalize_code(raw_code, status):
    """Canonical authority code (the 2024 scheme): RCs get 5500 + number."""
    if raw_code is None:
        return None
    if status == 'מועצה אזורית' and raw_code < 100:
        return RC_CODE_OFFSET + raw_code
    return raw_code

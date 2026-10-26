"""Release layer: the database analysts and agents use (data/release/).

Everything a consumer needs to discover the data lives in the data itself:
  indicators   what exists, for which years, at what quality, related indicators
  coverage     how many authorities have a value per indicator and year
  about        build facts, sources, audit summary
and the documentation of every table and column is defined once, in SCHEMA below, from
which schema.json, the README tables and the DuckDB column comments are generated. The
build fails if a table and its documentation disagree, or if a key or a reference breaks.

Usage:  python -m etl.release        (after etl.run, etl.gold, etl.benchmarks, etl.audit)
"""

import datetime as dt
import difflib
import json
import os
import re
import subprocess

import numpy as np
import pandas as pd
import yaml

from .common import norm_label, strip_period
from .harmonize import apply_synonyms
from .matching import sanitize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
OUT = os.path.join(DATA, 'release')
CONFIG = os.path.join(ROOT, 'etl', 'config')

FLAG_MAP = {'low_reliability': 'estimate', 'dash': 'nil', 'not_available': 'not_available',
            'footnote': 'footnote', 'range': 'range', 'malformed_number': 'malformed_number'}

# ---- the documentation of every table and column (single source of truth) ------------

SCHEMA = {
    'about': {
        'grain': 'key', 'primary_key': ['key'],
        'he': 'מידע על הבנייה: תאריך, מקורות, שנים, סיכום הבדיקות.',
        'en': 'Build information: date, sources, years, audit summary.',
        'columns': {
            'key': ('שם הפריט', 'item'),
            'value': ('ערך', 'value'),
        }},
    'topics': {
        'grain': 'topic', 'primary_key': ['topic'],
        'he': 'נושאים קבועים לקיבוץ מדדים, עם מספר המדדים בכל נושא.',
        'en': 'Stable topics grouping the indicators, with the number of indicators in each.',
        'columns': {
            'topic': ('מפתח הנושא (אנגלית)', 'topic key'),
            'topic_name': ('שם הנושא', 'topic name (Hebrew)'),
            'n_indicators': ('מספר מדדים בנושא', 'number of indicators'),
        }},
    'indicators': {
        'grain': 'indicator', 'primary_key': ['indicator_id'],
        'he': 'קטלוג המדדים: מה קיים, לאילו שנים, באיזו איכות ומה קשור למה. נקודת הפתיחה לכל שאילתה.',
        'en': 'Indicator catalogue: what exists, for which years, at what quality and how indicators relate. Start every query here.',
        'columns': {
            'indicator_id': ('מזהה יציב. P = נתונים פיזיים ואוכלוסייה, B = תקציב. סיומת _k = נגזר ל-1,000 תושבים',
                             'stable id. P = physical/population sheets, B = budget sheets. Suffix _k = derived per 1,000 residents'),
            'name': ('שם המדד בלי שנים והערות שוליים, רמות מופרדות ב-›', 'indicator name without years or footnote marks; levels joined by ›'),
            'full_label': ('הכותרת המלאה כפי שהופיעה בקובץ האחרון', 'full header as printed in the latest file'),
            'topic': ('נושא (ראו טבלת topics)', 'topic (see topics)'),
            'topic_name': ('שם הנושא', 'topic name'),
            'domain': ('גיליון מקור: physical / budget / landuse / derived', 'source sheet family'),
            'measure_type': ('count = כמות מוחלטת (גדלה עם גודל הרשות) · rate = שיעור/אחוז/ממוצע · index = מדד מורכב/אשכול/דירוג · attribute = תכונה/מזהה',
                             'count | rate | index | attribute'),
            'measure_type_basis': ('על מה מבוסס הסיווג: label, או בדיקת נתונים שתיקנה אותו', 'basis of measure_type: label, or a data check that corrected it'),
            'value_type': ('numeric או text (למשל מחוז, רמת פריפריאליות בקטגוריות)', 'numeric or text'),
            'unit': ('יחידה (אחרי המרת יחידות). ריק = לא צוינה בכותרת', 'unit after unit decisions; empty = not stated in the header'),
            'unit_note': ('המרות יחידה שהוחלו, לפי שנות קובץ', 'unit conversions applied, by file year'),
            'period_kind': ('calendar_year · school_year (שנת לימודים, השנה = שנת הסיום) · multi_year (ממוצע רב-שנתי, השנה = שנת הסיום) · reference_year (מהדורת מדד / שנת ייחוס)',
                            'what `year` means for this indicator'),
            'first_year': ('שנת הנתון הראשונה עם ערך', 'first data year with a value'),
            'last_year': ('שנת הנתון האחרונה עם ערך', 'last data year with a value'),
            'n_years': ('מספר שנות נתון עם ערך', 'number of data years with a value'),
            'years': ('כל שנות הנתון עם ערך, מופרדות בפסיקים', 'all data years with a value'),
            'missing_years': ('שנים בתוך הטווח שאין בהן ערך', 'years inside the range without a value'),
            'n_authorities_last_year': ('מספר רשויות עם ערך בשנה האחרונה', 'authorities with a value in the last year'),
            'applies_to': ('מעמדות הרשויות שיש להן ערכים (עירייה / מועצה מקומית / מועצה אזורית)', 'municipal statuses that have values'),
            'quality_flags': ('סיכום בעיות איכות ידועות במדד (ריק = אין)', 'summary of known quality issues (empty = none)'),
            'mapping_uncertain_columns': ('מספר עמודות מקור שהשיוך שלהן לסדרה ברמת ביטחון medium/low', 'source columns mapped with medium/low confidence'),
            'revised_values': ('מספר ערכים שקובץ מאוחר דיווח עליהם ערך שונה', 'values a later file revised'),
            'consistency_violations': ('מספר ערכים שסותרים זהות פנימית בנתוני הלמ"ס (למשל אחוז ≠ מונה/מכנה)', 'values violating an internal identity of the CBS data'),
            'mixed_scale_values': ('מספר ערכים שנראים כשבר בעמודה של אחוזים (בעיה בקובץ המקור)', 'values that look like fractions inside a percentage column (source problem)'),
            'systematic_breaks': ('מעברי שנים שבהם רבות מהרשויות קופצות פי 10 ומעלה יחד (שינוי יחידה/הגדרה לא מטופל)', 'year transitions where many authorities jump >=10x together'),
            'estimate_share': ('שיעור הערכים שהם אומדן (בסוגריים במקור)', 'share of values that are estimates'),
            'same_values_as': ('מדדים עם ערכים זהים (אותו נתון שפורסם בשני מקומות)', 'indicators with identical values (the same data published twice)'),
            'continues': ('מדדים שייתכן שהם אותה סדרה לפני שינוי ניסוח/מבנה (לא אוחדו; לבדיקה)', 'indicators that may be this series before a wording/structure change (not merged)'),
            'continued_by': ('מדדים שייתכן שהם המשך הסדרה (לא אוחדו; לבדיקה)', 'indicators that may continue this series (not merged)'),
            'derived_from': ('למדד נגזר: המדד שממנו חושב', 'for a derived indicator: its base indicator'),
            'label_history': ('הכותרות בקבצי המקור לפי שנות קובץ', 'source headers by file year'),
            'source_columns': ('מספר עמודות מקור שמרכיבות את המדד', 'number of source columns forming the indicator'),
        }},
    'coverage': {
        'grain': 'indicator × year', 'primary_key': ['indicator_id', 'year'],
        'he': 'זמינות: לכל מדד ושנה, כמה רשויות יש להן ערך, "אין מקרים", "לא ידוע", אומדן.',
        'en': 'Availability per indicator and year: authorities with a value, nil, not available, estimate.',
        'columns': {
            'indicator_id': ('מזהה מדד', 'indicator id'),
            'year': ('שנת נתון', 'data year'),
            'n_authorities': ('מספר הרשויות הקיימות באותה שנה', 'authorities existing that year'),
            'n_values': ('רשויות עם ערך (מספר או טקסט)', 'authorities with a value'),
            'n_nil': ('רשויות שסומנו "-" (אין מקרים)', 'authorities marked "-" (no cases)'),
            'n_not_available': ('רשויות שסומנו ".." (לא ידוע / לא לפרסום)', 'authorities marked ".." (unknown / not publishable)'),
            'n_estimate': ('ערכים שהם אומדן', 'values that are estimates'),
            'n_east_galilee': ('רשויות הגליל המזרחי עם ערך', 'East Galilee authorities with a value'),
            'n_west_galilee': ('רשויות הגליל המערבי עם ערך', 'West Galilee authorities with a value'),
            'share_with_value': ('n_values / n_authorities', 'n_values / n_authorities'),
        }},
    'authorities': {
        'grain': 'authority', 'primary_key': ['muni_code'],
        'he': 'הרשויות המקומיות (כל מי שהופיעה בשנה כלשהי), עם שיוך לאשכול.',
        'en': 'Local authorities (any that appeared in any year), with Eshkol membership.',
        'columns': {
            'muni_code': ('סמל הרשות בלמ"ס (סכמת 2024: מועצה אזורית = 5500 + מספר)', 'CBS authority code (2024 scheme: regional council = 5500 + number)'),
            'name': ('השם בקובץ האחרון שבו הופיעה', 'name in the latest file it appears in'),
            'status': ('מעמד מוניציפלי אחרון', 'latest municipal status'),
            'district': ('מחוז אחרון', 'latest district'),
            'first_year': ('השנה הראשונה שבה הופיעה', 'first year present'),
            'last_year': ('השנה האחרונה שבה הופיעה', 'last year present'),
            'n_years': ('מספר שנים שבהן הופיעה', 'years present'),
            'eshkol': ('אשכול: גליל מזרחי / גליל מערבי / ריק', 'Eshkol cluster or empty'),
            'eshkol_name': ('השם ברשימת האשכול', 'name in the Eshkol list'),
            'sector': ('מגזר (לרשויות האשכול)', 'sector (Eshkol authorities)'),
            'settlement_form': ('צורת יישוב (לרשויות האשכול)', 'settlement form (Eshkol authorities)'),
            'aliases': ('כל הכתיבים המוכרים, מופרדים ב-|', 'all known spellings, |-separated'),
        }},
    'authority_aliases': {
        'grain': 'alias × authority', 'primary_key': ['alias', 'muni_code'],
        'he': 'כל כתיב של שם רשות (למ"ס לאורך השנים, רשימת האשכול) → סמל. לחיפוש לפי שם השתמשו ב-alias_normalized.',
        'en': 'Every spelling of an authority name → code. Search on alias_normalized.',
        'columns': {
            'alias': ('הכתיב כפי שהופיע', 'spelling as it appeared'),
            'alias_normalized': ('הכתיב אחרי ניקוי (בלי גרשיים, מקפים, סוגריים)', 'normalized: no quotes, hyphens, brackets'),
            'muni_code': ('סמל הרשות', 'authority code'),
            'source': ('מקור הכתיב', 'where the spelling comes from'),
        }},
    'authority_year': {
        'grain': 'authority × year', 'primary_key': ['muni_code', 'year'],
        'he': 'מאפייני רשות לפי שנה: מעמד, אוכלוסייה, אשכול חברתי-כלכלי ופריפריאליות.',
        'en': 'Authority attributes by year: status, population, socio-economic and peripherality clusters.',
        'columns': {
            'muni_code': ('סמל הרשות', 'authority code'),
            'year': ('שנה (שנת הקובץ)', 'year (file year)'),
            'name': ('השם באותה שנה', 'name that year'),
            'status': ('מעמד מוניציפלי באותה שנה', 'municipal status that year'),
            'district': ('מחוז באותה שנה', 'district that year'),
            'population': ('אוכלוסייה בסוף השנה (נפשות)', 'population at year end (persons)'),
            'ses_cluster': ('אשכול חברתי-כלכלי 1–10 לפי המהדורה האחרונה שפורסמה עד אותה שנה', 'SES cluster 1-10, latest edition published by that year'),
            'ses_value': ('ערך המדד החברתי-כלכלי באותה מהדורה', 'SES index value, same edition'),
            'ses_edition': ('שנת מהדורת המדד החברתי-כלכלי שבה השתמשנו', 'SES edition used'),
            'ses_cluster_latest': ('אשכול חברתי-כלכלי במהדורה האחרונה (קבוצת השוואה קבועה לאורך השנים)', 'SES cluster in the latest edition (fixed peer group)'),
            'ses_edition_latest': ('שנת המהדורה האחרונה', 'latest SES edition'),
            'periphery_cluster': ('אשכול פריפריאליות 1–10 (1 = הפריפריאלי ביותר)', 'peripherality cluster 1-10 (1 = most peripheral)'),
            'periphery_edition': ('מהדורת מדד הפריפריאליות', 'peripherality edition'),
            'eshkol': ('אשכול: גליל מזרחי / גליל מערבי / ריק', 'Eshkol cluster or empty'),
        }},
    'observations': {
        'grain': 'authority × indicator × year', 'primary_key': ['muni_code', 'indicator_id', 'year'],
        'he': 'הערכים. שורה לכל רשות, מדד ושנת נתון, כולל ערכים שהלמ"ס סימנה בסמל מיוחד, עם דגלי איכות ברמת הערך.',
        'en': 'The values: one row per authority, indicator and data year, including CBS special symbols, with row-level quality flags.',
        'columns': {
            'muni_code': ('סמל הרשות', 'authority code'),
            'indicator_id': ('מזהה מדד', 'indicator id'),
            'year': ('שנת הנתון (לא שנת הקובץ). ראו indicators.period_kind', 'data year (not the file year); see indicators.period_kind'),
            'value': ('הערך המספרי אחרי המרת יחידות. "אין מקרים" = 0 במדדי כמות; ריק כשאין מספר', 'numeric value after unit decisions; nil = 0 for counts; empty when no number'),
            'value_text': ('ערך טקסט (למדדי טקסט), או הטקסט המקורי כשהמספר פגום/טווח', 'text value, or the original text when the number is malformed or a band'),
            'flag': ('ריק = ערך רגיל · estimate = אומדן (בסוגריים במקור) · nil = "-" אין מקרים · not_available = ".." לא ידוע/לא לפרסום · footnote = עם הערת שוליים · range = טווח במקום מספר · malformed_number = מספר פגום במקור',
                     'empty | estimate | nil | not_available | footnote | range | malformed_number'),
            'value_published': ('המספר כפי שפורסם, לפני המרת יחידות', 'number as published, before unit decisions'),
            'unit_factor': ('המקדם שהוחל (1 = ללא המרה)', 'multiplier applied (1 = none)'),
            'data_period': ('התקופה כפי שנכתבה בכותרת (למשל תשפ"ד 2023/24, 2020-2024)', 'period as written in the header'),
            'source_file_year': ('שנת הקובץ שממנו נלקח הערך (הקובץ החדש ביותר שיש בו ערך)', 'file the value comes from (newest file with a value)'),
            'is_derived': ('ערך נגזר (ל-1,000 תושבים), לא פורסם ישירות', 'derived value (per 1,000 residents), not published'),
            'mapping_confidence': ('ביטחון בשיוך עמודת המקור לסדרה: high = כותרת זהה, או התאמה שהנתונים מאששים (מתאם ≥0.9 עם השנה הסמוכה) · medium = אין נתונים לאישור / מתאם 0.5–0.9 · low = הנתונים לא ממשיכים (מתאם <0.5)',
                                   'confidence that the source column belongs to this series: high | medium | low'),
            'consistency_issue': ('הערך סותר זהות פנימית בנתוני הלמ"ס', 'value violates an internal CBS identity'),
            'mixed_scale': ('הערך נראה כשבר בעמודת אחוזים (בעיה במקור)', 'value looks like a fraction in a percentage column'),
            'revised': ('קובץ אחר דיווח ערך שונה לאותה רשות ושנה (ראו observation_revisions)', 'another file reported a different value (see observation_revisions)'),
        }},
    'observation_revisions': {
        'grain': 'authority × indicator × year × source file', 'primary_key': ['muni_code', 'indicator_id', 'year', 'source_file_year'],
        'he': 'ערכים שקבצים קודמים דיווחו לאותה רשות ושנה ושונים מהערך הנבחר.',
        'en': 'Values earlier files reported for the same authority and year that differ from the chosen value.',
        'columns': {
            'muni_code': ('סמל הרשות', 'authority code'),
            'indicator_id': ('מזהה מדד', 'indicator id'),
            'year': ('שנת נתון', 'data year'),
            'source_file_year': ('הקובץ שדיווח את הגרסה הזו', 'file reporting this version'),
            'value': ('הערך בגרסה הזו (אחרי המרת יחידות)', 'value in this version'),
            'chosen_value': ('הערך שנבחר ב-observations', 'value chosen in observations'),
            'chosen_file_year': ('הקובץ של הערך שנבחר', 'file of the chosen value'),
        }},
    'cbs_totals': {
        'grain': 'indicator × year × group × source', 'primary_key': ['row_id'],
        'he': 'סיכומים רשמיים של הלמ"ס: ארצי ולפי מעמד. כולל עמודה מקורית כשלא הותאמה למדד.',
        'en': 'Official CBS totals: national and by municipal status.',
        'columns': {
            'row_id': ('מזהה שורה', 'row id'),
            'indicator_id': ('מזהה מדד (ריק אם הכותרת בגיליון הסיכום לא הותאמה)', 'indicator id (empty if the summary label was not matched)'),
            'year': ('שנת נתון', 'data year'),
            'group': ('national / municipality / local_council / regional_council', 'national / municipality / local_council / regional_council'),
            'value': ('הערך אחרי המרת יחידות', 'value after unit decisions'),
            'value_published': ('הערך כפי שפורסם', 'value as published'),
            'label': ('הכותרת בגיליון הסיכום', 'label in the summary sheet'),
            'source': ('summary_sheet (2011–2021) או in_sheet_row (2022 ואילך)', 'summary_sheet or in_sheet_row'),
            'source_file_year': ('שנת הקובץ', 'file year'),
        }},
    'benchmarks': {
        'grain': 'indicator × year × group', 'primary_key': ['indicator_id', 'year', 'group_type', 'group'],
        'he': 'סטטיסטיקות של כל הרשויות לפי קבוצות השוואה. ממוצעים ללא שקלול, אלא אם צוין.',
        'en': 'Statistics over authorities per peer group. Unweighted unless stated.',
        'columns': {
            'indicator_id': ('מזהה מדד', 'indicator id'),
            'year': ('שנת נתון', 'data year'),
            'group_type': ('national · status · ses (אשכול לשנה) · ses_latest (מהדורה אחרונה) · ses_status · eshkol', 'peer group family'),
            'group': ('ערך הקבוצה (למשל 5, עירייה, "5 | עירייה")', 'group value'),
            'n': ('מספר רשויות עם ערך', 'authorities with a value'),
            'mean': ('ממוצע', 'mean'), 'median': ('חציון', 'median'), 'std': ('סטיית תקן', 'standard deviation'),
            'min': ('מינימום', 'min'), 'max': ('מקסימום', 'max'),
            'p25': ('רבעון תחתון', '25th percentile'), 'p75': ('רבעון עליון', '75th percentile'),
            'pop_weighted_mean': ('ממוצע משוקלל באוכלוסייה', 'population-weighted mean'),
        }},
    'peer_comparison': {
        'grain': 'Eshkol authority × indicator × year', 'primary_key': ['muni_code', 'indicator_id', 'year'],
        'he': 'רשויות האשכול מול קבוצות ההשוואה: פערים, אחוזונים וציון z.',
        'en': 'Eshkol authorities against peer groups: gaps, percentiles, z-score.',
        'columns': {
            'muni_code': ('סמל הרשות', 'authority code'),
            'indicator_id': ('מזהה מדד', 'indicator id'),
            'year': ('שנת נתון', 'data year'),
            'value': ('הערך', 'value'),
            'ses_cluster': ('אשכול חברתי-כלכלי לשנה', 'SES cluster for the year'),
            'national_median': ('חציון ארצי', 'national median'),
            'national_n': ('מספר רשויות בארצי', 'authorities nationally'),
            'cbs_national': ('הנתון הארצי הרשמי (2022 ואילך)', 'official national figure (2022+)'),
            'pct_rank_national': ('אחוזון ארצי 0–100', 'national percentile 0-100'),
            'gap_national_median': ('פער מהחציון הארצי', 'gap from the national median'),
            'ses_median': ('חציון האשכול החברתי-כלכלי', 'median of the SES cluster'),
            'ses_n': ('מספר רשויות באשכול', 'authorities in the SES cluster'),
            'pct_rank_ses': ('אחוזון בתוך האשכול', 'percentile within the SES cluster'),
            'z_ses': ('ציון z בתוך האשכול', 'z-score within the SES cluster'),
            'gap_ses_median': ('פער מחציון האשכול', 'gap from the SES-cluster median'),
            'ses_latest_median': ('חציון האשכול במהדורה האחרונה', 'median of the latest-edition SES cluster'),
            'status_median': ('חציון רשויות באותו מעמד', 'median of authorities with the same status'),
            'eshkol_median': ('חציון רשויות האשכול הגלילי', 'median of the Eshkol cluster'),
        }},
}

ORDER = ['about', 'topics', 'indicators', 'coverage', 'authorities', 'authority_aliases', 'authority_year',
         'observations', 'observation_revisions', 'cbs_totals', 'benchmarks', 'peer_comparison']
CSV_TABLES = ['about', 'topics', 'indicators', 'coverage', 'authorities', 'authority_aliases',
              'authority_year', 'cbs_totals']


def _read(*p, **kw):
    path = os.path.join(DATA, *p)
    return pd.read_parquet(path, **kw) if path.endswith('.parquet') else pd.read_csv(path, **kw)


def _years_str(years):
    return ','.join(str(int(y)) for y in sorted(set(years)))


def _ranges(years):
    ys = sorted(set(int(y) for y in years))
    out, start, prev = [], None, None
    for y in ys:
        if start is None:
            start = prev = y
        elif y == prev + 1:
            prev = y
        else:
            out.append((start, prev))
            start = prev = y
    if start is not None:
        out.append((start, prev))
    return ', '.join(f'{a}' if a == b else f'{a}–{b}' for a, b in out)


# ---- observations -------------------------------------------------------------------

_VOLATILE = re.compile(r'שינוי|גידול|לעומת|עודף|גירעון|מאזן|ריבוי|הנחת|התחלת|גמר|סלילת|עולים|השתקעות|'
                       r'נכנסים|יוצאים|תאונות|הרוגים|בחירות|הצבעה|הגירה|מלוות|מענק')


def mapping_confidence(colmap):
    """Evidence that each source column belongs to its series.

    high    identical label (or a manual override), or a structural / fuzzy match whose
            values correlate >= 0.9 with the adjacent year of the series
    medium  no overlapping data to confirm, a measure that is volatile by nature, or
            correlation 0.5-0.9
    low     the values do not continue (correlation < 0.5) for a non-volatile measure
    A column kept apart because the data contradicted a label match is medium, so it
    stays visible for review.
    """
    def one(r):
        c = r.corr_with_newer_year
        volatile = bool(_VOLATILE.search(str(r.levels)))
        if 'data guard rejected' in str(getattr(r, 'review_reason', '')):
            return 'medium'           # kept apart because its values contradicted the match
        if r.match_method in ('override', 'override_new', 'new'):
            return 'high'
        if r.match_method == 'exact':
            return 'medium' if (c == c and c < 0.5 and not volatile) else 'high'
        if c != c or volatile:
            return 'medium'
        return 'high' if c >= 0.9 else ('medium' if c >= 0.5 else 'low')
    return colmap.apply(one, axis=1)


def build_observations(facts, cat, pop_id, consistency, mixed, conf):
    a = facts[facts.row_type == 'authority'].copy()
    a['muni_code'] = a['muni_code'].astype('int64')
    a['period_year'] = a['period_year'].astype('int64')
    prim = a[a.is_primary].copy()
    # revisions: other files with a different number for the same key
    num = a[a.value.notna()]
    chosen = prim.set_index(['indicator_id', 'muni_code', 'period_year'])[['value', 'file_year']]
    other = num[~num.is_primary].join(chosen, on=['indicator_id', 'muni_code', 'period_year'], rsuffix='_chosen')
    diff = other[(other.value - other.value_chosen).abs() > 1e-9 * other.value_chosen.abs().clip(lower=1)]
    revisions = pd.DataFrame({
        'muni_code': diff.muni_code, 'indicator_id': diff.indicator_id, 'year': diff.period_year,
        'source_file_year': diff.file_year, 'value': diff.value, 'chosen_value': diff.value_chosen,
        'chosen_file_year': diff.file_year_chosen}).drop_duplicates(
        ['muni_code', 'indicator_id', 'year', 'source_file_year'])
    rev_keys = set(zip(revisions.muni_code, revisions.indicator_id, revisions.year))

    obs = pd.DataFrame({
        'muni_code': prim.muni_code, 'indicator_id': prim.indicator_id, 'year': prim.period_year,
        'value': prim.value, 'value_text': prim.value_text,
        'flag': prim.flag.map(FLAG_MAP).fillna(''),
        'value_published': prim.value_raw, 'unit_factor': prim.unit_factor,
        'data_period': prim.data_period.astype(str), 'source_file_year': prim.file_year.astype('int64'),
        'is_derived': False,
        'mapping_confidence': [conf.get(k, 'high') for k in zip(prim.file_year, prim.sheet, prim.col)]})
    ck = set(zip(consistency.muni_code, consistency.indicator_id, consistency.period_year)) if len(consistency) else set()
    mk = set(zip(mixed.muni_code, mixed.indicator_id, mixed.period_year)) if len(mixed) else set()
    keys = list(zip(obs.muni_code, obs.indicator_id, obs.year))
    obs['consistency_issue'] = [k in ck for k in keys]
    obs['mixed_scale'] = [k in mk for k in keys]
    obs['revised'] = [k in rev_keys for k in keys]

    # derived: counts per 1,000 residents of the same authority and year
    counts = set(cat.loc[cat.measure_type == 'count', 'indicator_id']) - {pop_id}
    pop = obs[obs.indicator_id == pop_id].set_index(['muni_code', 'year'])['value']
    c = obs[obs.indicator_id.isin(counts) & obs.value.notna()].copy()
    p = pd.Series(list(zip(c.muni_code, c.year))).map(pop).values
    c['value'] = c['value'] / p * 1000
    c = c[np.isfinite(c['value'].astype(float))]
    c['indicator_id'] = c['indicator_id'] + '_k'
    c[['value_published', 'unit_factor']] = np.nan
    c['is_derived'] = True
    c['revised'] = False
    obs = pd.concat([obs, c], ignore_index=True)
    obs = obs.sort_values(['indicator_id', 'muni_code', 'year']).reset_index(drop=True)
    return obs, revisions.reset_index(drop=True)


# ---- indicators ---------------------------------------------------------------------

def _period_kind(periods, years):
    p = [str(x) for x in periods]
    if any('תש' in x or re.search(r'\d{4}/\d{2,4}', x) for x in p):
        return 'school_year'
    if any(re.search(r'(19|20)\d{2}\s*-\s*(19|20)\d{2}', x) for x in p):
        return 'multi_year'
    if any(x.isdigit() and int(x) not in years for x in p) or any('inferred' in x or 'unspecified' in x for x in p):
        return 'reference_year'
    return 'calendar_year'


def find_same_values(obs):
    """Indicators publishing identical values for the same authorities and year."""
    base = obs[~obs.is_derived & obs.value.notna()]
    sig = {}
    for (iid, y), g in base.groupby(['indicator_id', 'year']):
        if len(g) < 20 or g['value'].nunique() < 5:
            continue
        h = hash(tuple(zip(g.muni_code, g.value.round(6))))
        sig.setdefault((y, h), []).append(iid)
    pairs = {}
    for ids in sig.values():
        for i in ids:
            for j in ids:
                if i != j:
                    pairs.setdefault(i, set()).add(j)
    return {k: sorted(v) for k, v in pairs.items()}


def find_continuations(cat, obs, names):
    """Series that end where a similarly named series starts (not merged; for review)."""
    base = obs[~obs.is_derived & obs.value.notna()]
    span = base.groupby('indicator_id')['year'].agg(['min', 'max'])
    med = base.groupby(['indicator_id', 'year'])['value'].median()
    vals = {k: g.set_index('muni_code')['value'] for k, g in base.groupby(['indicator_id', 'year'])}
    leaf = {i: n.split(' › ')[-1] for i, n in names.items()}
    topic = cat.set_index('indicator_id')['topic']
    cont, cont_by = {}, {}
    ids = list(span.index)
    starts = span.sort_values('min')
    for a in ids:
        a_end = span.at[a, 'max']
        cands = starts[(starts['min'] > a_end) & (starts['min'] <= a_end + 3)].index
        for b in cands:
            if b == a or topic.get(a) != topic.get(b):
                continue
            sim = max(difflib.SequenceMatcher(None, names[a], names[b]).ratio(),
                      difflib.SequenceMatcher(None, leaf[a], leaf[b]).ratio())
            if sim < 0.6:
                continue
            b_start = span.at[b, 'min']
            va, vb = vals.get((a, a_end)), vals.get((b, b_start))
            if va is None or vb is None:
                continue
            j = pd.concat([va, vb], axis=1, keys=['a', 'b']).dropna()
            if len(j) < 15 or j['a'].nunique() < 3 or j['b'].nunique() < 3:
                continue
            r = j.rank()
            rho = float(r['a'].corr(r['b']))
            if rho < 0.7:
                continue
            ma, mb = med.get((a, a_end)), med.get((b, b_start))
            scale = ''
            if ma and mb and ma > 0 and mb > 0:
                k = round(np.log10(mb / ma))
                if abs(np.log10(mb / ma)) >= 0.8 and k != 0:
                    scale = f', scale differs ×10^{k}'
            note_b = f'{b} ({b_start}–{span.at[b, "max"]}, name {sim:.2f}, rho {rho:.2f}{scale})'
            note_a = f'{a} ({span.at[a, "min"]}–{a_end}, name {sim:.2f}, rho {rho:.2f}{scale})'
            cont_by.setdefault(a, []).append(note_b)
            cont.setdefault(b, []).append(note_a)
    return cont, cont_by


def build_indicators(cat, obs, colmap, authority_year, consistency, mixed, breaks, unit_decisions, revisions):
    colmap = colmap.assign(review_needed=colmap['mapping_confidence'] != 'high')
    names = cat.set_index('indicator_id')['name'].to_dict()
    has = obs[obs.value.notna() | obs.value_text.notna()]
    yrs = has.groupby('indicator_id')['year'].apply(list)
    last = has.groupby('indicator_id')['year'].max()
    status = authority_year.set_index(['muni_code', 'year'])['status']
    same = find_same_values(obs)
    cont, cont_by = find_continuations(cat, obs, names)
    dec = {d['indicator_id']: d for d in unit_decisions if d['status'] == 'apply'}
    cm = colmap.copy()
    hist = cm.groupby('indicator_id').apply(
        lambda g: ' | '.join(f"{_ranges(s.year)}: {lab}" for lab, s in g.groupby('levels', sort=False)),
        include_groups=False)
    unit_latest = cm.sort_values('year').groupby('indicator_id')['unit_hint'].agg(
        lambda s: next((u for u in reversed(s.tolist()) if isinstance(u, str) and u), ''))
    periods = cm.groupby('indicator_id')['data_period'].apply(list)
    ncols = cm.groupby('indicator_id').size()
    review = cm.groupby('indicator_id')['review_needed'].sum()
    cons = consistency.groupby('indicator_id').size() if len(consistency) else pd.Series(dtype=int)
    mix = mixed.groupby('indicator_id').size() if len(mixed) else pd.Series(dtype=int)
    brk = breaks.groupby('indicator_id').apply(
        lambda g: ', '.join(f'{int(a)}→{int(b)}' for a, b in zip(g.prev_year, g.period_year)),
        include_groups=False) if len(breaks) else pd.Series(dtype=str)
    rev = revisions.groupby('indicator_id').size()
    est = obs.groupby('indicator_id')['flag'].apply(lambda s: round(float((s == 'estimate').mean()), 4))

    rows = []
    for r in cat.itertuples():
        iid = r.indicator_id
        ys = sorted(set(yrs.get(iid, [])))
        ly = last.get(iid)
        in_last = has[(has.indicator_id == iid) & (has.year == ly)] if ly is not None else has.iloc[0:0]
        st = sorted({status.get((m, ly)) for m in in_last.muni_code} - {None}) if ly is not None else []
        unit = unit_latest.get(iid, '') or ('%' if re.search(r'אחוז|\(%\)', r.name.split(' › ')[-1]) else '')
        note = ''
        if iid in dec:
            groups = {}
            for y, f in (dec[iid].get('factors') or {}).items():
                groups.setdefault(f, []).append(int(y))
            note = '; '.join(f"×{f:g} applied to file years {_ranges(ys_)}" for f, ys_ in groups.items())
        qf = []
        if review.get(iid, 0):
            qf.append(f'cross-year mapping uncertain for {int(review[iid])} of {int(ncols.get(iid, 0))} source columns')
        if cons.get(iid, 0):
            qf.append(f'internal inconsistency in {int(cons[iid])} values')
        if mix.get(iid, 0):
            qf.append(f'fractions in a percentage column: {int(mix[iid])} values')
        if isinstance(brk.get(iid), str):
            qf.append(f'systematic 10x break at {brk[iid]}')
        if rev.get(iid, 0):
            qf.append(f'{int(rev[iid])} values revised by a later file')
        if not ys:
            qf.append('no values')
        rows.append({
            'indicator_id': iid, 'name': r.name, 'full_label': r.label_latest, 'topic': r.topic,
            'topic_name': r.topic_name, 'domain': r.domain, 'measure_type': r.measure_type,
            'measure_type_basis': r.measure_type_basis, 'value_type': r.value_kind, 'unit': unit,
            'unit_note': note, 'period_kind': _period_kind(periods.get(iid, []), ys),
            'first_year': min(ys) if ys else None, 'last_year': max(ys) if ys else None, 'n_years': len(ys),
            'years': _years_str(ys), 'missing_years': _years_str(set(range(min(ys), max(ys) + 1)) - set(ys)) if ys else '',
            'n_authorities_last_year': int(in_last.muni_code.nunique()), 'applies_to': ', '.join(st),
            'quality_flags': '; '.join(qf), 'mapping_uncertain_columns': int(review.get(iid, 0)),
            'revised_values': int(rev.get(iid, 0)), 'consistency_violations': int(cons.get(iid, 0)),
            'mixed_scale_values': int(mix.get(iid, 0)), 'systematic_breaks': brk.get(iid, '') if isinstance(brk.get(iid), str) else '',
            'estimate_share': est.get(iid, 0.0), 'same_values_as': ', '.join(same.get(iid, [])),
            'continues': ' | '.join(cont.get(iid, [])), 'continued_by': ' | '.join(cont_by.get(iid, [])),
            'derived_from': '', 'label_history': hist.get(iid, ''), 'source_columns': int(ncols.get(iid, 0)),
        })
    ind = pd.DataFrame(rows)
    # derived per-1,000 indicators
    der_ids = sorted(set(obs.loc[obs.is_derived, 'indicator_id']))
    base = ind.set_index('indicator_id')
    drows = []
    for d in der_ids:
        b = base.loc[d[:-2]]
        ys = sorted(set(yrs.get(d, [])))
        ly = last.get(d)
        in_last = has[(has.indicator_id == d) & (has.year == ly)]
        drows.append({**{k: '' for k in ind.columns}, 'indicator_id': d, 'name': f'{b["name"]} — ל-1,000 תושבים (נגזר)',
                      'full_label': '', 'topic': b['topic'], 'topic_name': b['topic_name'], 'domain': 'derived',
                      'measure_type': 'rate', 'measure_type_basis': 'derived: base count / population × 1,000',
                      'value_type': 'numeric', 'unit': f'{b["unit"] + " " if b["unit"] else ""}ל-1,000 תושבים'.strip(),
                      'unit_note': b['unit_note'], 'period_kind': b['period_kind'],
                      'first_year': min(ys), 'last_year': max(ys), 'n_years': len(ys), 'years': _years_str(ys),
                      'missing_years': _years_str(set(range(min(ys), max(ys) + 1)) - set(ys)),
                      'n_authorities_last_year': int(in_last.muni_code.nunique()), 'applies_to': b['applies_to'],
                      'quality_flags': b['quality_flags'], 'mapping_uncertain_columns': b['mapping_uncertain_columns'],
                      'revised_values': 0, 'consistency_violations': 0, 'mixed_scale_values': 0,
                      'systematic_breaks': b['systematic_breaks'], 'estimate_share': est.get(d, 0.0),
                      'derived_from': d[:-2], 'source_columns': 0})
    ind = pd.concat([ind, pd.DataFrame(drows)], ignore_index=True)
    for c in ('first_year', 'last_year'):
        ind[c] = ind[c].astype('Int64')
    for c in ('mapping_uncertain_columns', 'revised_values', 'consistency_violations', 'mixed_scale_values',
              'source_columns', 'n_years', 'n_authorities_last_year'):
        ind[c] = pd.to_numeric(ind[c]).astype('int64')
    return ind


# ---- coverage, authorities, totals --------------------------------------------------

def build_coverage(obs, authority_year, authorities):
    n_auth = authority_year.groupby('year').size()
    east = set(authorities.loc[authorities.eshkol == 'גליל מזרחי', 'muni_code'])
    west = set(authorities.loc[authorities.eshkol == 'גליל מערבי', 'muni_code'])
    o = obs.assign(_has=obs.value.notna() | obs.value_text.notna())
    g = o.groupby(['indicator_id', 'year'])
    cov = pd.DataFrame({
        'n_values': g['_has'].sum(),
        'n_nil': g['flag'].apply(lambda s: int((s == 'nil').sum())),
        'n_not_available': g['flag'].apply(lambda s: int((s == 'not_available').sum())),
        'n_estimate': g['flag'].apply(lambda s: int((s == 'estimate').sum())),
        'n_east_galilee': o[o.muni_code.isin(east) & o._has].groupby(['indicator_id', 'year']).size(),
        'n_west_galilee': o[o.muni_code.isin(west) & o._has].groupby(['indicator_id', 'year']).size(),
    }).fillna(0).reset_index()
    yrs = np.array(sorted(n_auth.index))
    cov['n_authorities'] = [int(n_auth[yrs[np.abs(yrs - y).argmin()]]) for y in cov['year']]
    cov['share_with_value'] = (cov['n_values'] / cov['n_authorities']).round(4)
    for c in ('n_values', 'n_nil', 'n_not_available', 'n_estimate', 'n_east_galilee', 'n_west_galilee'):
        cov[c] = cov[c].astype('int64')
    return cov[list(SCHEMA['coverage']['columns'])]


def build_authorities(dim, registry):
    rows, aliases = [], []
    from .matching import EshkolMatcher
    t = EshkolMatcher().targets
    for r in dim.itertuples():
        names = set(registry.loc[registry.muni_code == r.muni_code, 'name'])
        for n in sorted(names):
            ys = registry.loc[(registry.muni_code == r.muni_code) & (registry.name == n), 'year']
            aliases.append((n, r.muni_code, f'CBS files {_ranges(ys)}'))
        if isinstance(r.eshkol_name, str) and r.eshkol_name:
            aliases.append((r.eshkol_name, r.muni_code, 'Eshkol list (eshkol_mapping.xlsx)'))
        off = t.loc[t.code == r.muni_code, 'official_name']
        if len(off):
            aliases.append((off.iloc[0], r.muni_code, 'Eshkol list: official CBS name'))
        rows.append({'muni_code': int(r.muni_code), 'name': r.name, 'status': r.status, 'district': r.district,
                     'first_year': int(r.first_year), 'last_year': int(r.last_year), 'n_years': int(r.n_years),
                     'eshkol': r.eshkol if isinstance(r.eshkol, str) else '',
                     'eshkol_name': r.eshkol_name if isinstance(r.eshkol_name, str) else '',
                     'sector': r.sector if isinstance(r.sector, str) else '',
                     'settlement_form': r.settlement_form if isinstance(r.settlement_form, str) else '',
                     'aliases': ''})
    al = pd.DataFrame(aliases, columns=['alias', 'muni_code', 'source'])
    al = al.groupby(['alias', 'muni_code'], as_index=False)['source'].agg(lambda s: '; '.join(sorted(set(s))))
    al['alias_normalized'] = al['alias'].map(sanitize)
    al['muni_code'] = al['muni_code'].astype('int64')
    auth = pd.DataFrame(rows)
    auth['aliases'] = auth['muni_code'].map(al.groupby('muni_code')['alias'].agg(lambda s: '|'.join(sorted(set(s)))))
    return auth, al[['alias', 'alias_normalized', 'muni_code', 'source']]


def build_cbs_totals(facts, summary, colmap, unit_decisions):
    rows = []
    s = facts[(facts.row_type == 'summary') & facts.is_primary & facts.value.notna()]
    for r in s.itertuples():
        rows.append({'indicator_id': r.indicator_id, 'year': int(r.period_year), 'group': r.summary_group,
                     'value': r.value, 'value_published': r.value_raw, 'label': '', 'source': 'in_sheet_row',
                     'source_file_year': int(r.file_year)})
    # transposed summary sheets: match each label to a column of the same file
    fac = {(d['indicator_id'], int(y)): float(v) for d in unit_decisions if d['status'] == 'apply'
           for y, v in (d.get('factors') or {}).items()}

    def norm(x):
        return apply_synonyms(norm_label(strip_period(x)))[0]
    keys = {}
    for r in colmap.itertuples():
        lv = [norm(p) for p in str(r.levels).split(' › ') if p]
        for k in {lv[-1] if lv else '', ' › '.join(lv[-2:]), ' - '.join(lv[-2:]), ' '.join(lv)}:
            if k:
                keys.setdefault((r.year, k), set()).add((r.indicator_id, r.data_period))
    matched = 0
    sv = summary[summary.value.notna()]
    for r in sv.itertuples():
        cands = keys.get((r.year, norm(r.label)), set())
        iid, period = (next(iter(cands)) if len({c[0] for c in cands}) == 1 else (None, None))
        if iid:
            matched += 1
        from .gold import period_year
        y = period_year(period) if period else period_year(r.label) or r.year
        f = fac.get((iid, int(r.year)), 1.0) if iid else 1.0
        rows.append({'indicator_id': iid, 'year': int(y), 'group': r.summary_group, 'value': r.value * f,
                     'value_published': r.value, 'label': r.label, 'source': 'summary_sheet',
                     'source_file_year': int(r.year)})
    t = pd.DataFrame(rows)
    t.insert(0, 'row_id', np.arange(1, len(t) + 1))
    return t, matched, len(sv)


# ---- validation and outputs ---------------------------------------------------------

def validate(tables):
    errors = []
    for name, spec in SCHEMA.items():
        df = tables[name]
        cols = list(spec['columns'])
        if list(df.columns) != cols:
            errors.append(f'{name}: columns {list(df.columns)} != documented {cols}')
            continue
        pk = spec['primary_key']
        if df[pk].isna().any().any():
            errors.append(f'{name}: null in primary key {pk}')
        if df.duplicated(pk).any():
            errors.append(f'{name}: {int(df.duplicated(pk).sum())} duplicate keys {pk}')
        for c, (he, en) in spec['columns'].items():
            if not he or not en:
                errors.append(f'{name}.{c}: undocumented')
    ind = set(tables['indicators'].indicator_id)
    mun = set(tables['authorities'].muni_code)
    for name in ('observations', 'coverage', 'benchmarks', 'peer_comparison', 'observation_revisions'):
        bad = set(tables[name].indicator_id) - ind
        if bad:
            errors.append(f'{name}: {len(bad)} indicator ids not in indicators, e.g. {sorted(bad)[:3]}')
    for name in ('observations', 'authority_year', 'authority_aliases', 'peer_comparison', 'observation_revisions'):
        bad = set(tables[name].muni_code) - mun
        if bad:
            errors.append(f'{name}: {len(bad)} authority codes not in authorities')
    bad = set(tables['cbs_totals'].indicator_id.dropna()) - ind
    if bad:
        errors.append(f'cbs_totals: {len(bad)} unknown indicator ids')
    o = tables['observations']
    has = o[o.value.notna() | o.value_text.notna()]
    n = has.groupby(['indicator_id', 'year']).size()
    cov = tables['coverage'].set_index(['indicator_id', 'year'])['n_values']
    if not n.reindex(cov.index).fillna(0).astype(int).equals(cov.astype(int)):
        errors.append('coverage.n_values does not equal the observations count')
    span = has.groupby('indicator_id')['year'].agg(['min', 'max'])
    i2 = tables['indicators'].set_index('indicator_id')
    bad = [k for k in span.index if (i2.at[k, 'first_year'], i2.at[k, 'last_year']) != (span.at[k, 'min'], span.at[k, 'max'])]
    if bad:
        errors.append(f'indicators first/last year disagree with observations for {len(bad)} indicators')
    if errors:
        raise RuntimeError('release validation failed:\n  ' + '\n  '.join(errors))


def schema_json(tables, about):
    return {
        'name': 'rashuiot — CBS local authorities database (Israel), 2003–2024',
        'about': dict(zip(about.key, about.value)),
        'how_to_open': {
            'duckdb': "import duckdb; con = duckdb.connect(); con.execute(open('data/release/open.sql').read())",
            'python': "from etl.db import connect; con = connect()",
            'pandas': "pd.read_parquet('data/release/parquet/<table>.parquet')",
        },
        'tables': [{
            'name': t, 'grain': SCHEMA[t]['grain'], 'primary_key': SCHEMA[t]['primary_key'],
            'description_he': SCHEMA[t]['he'], 'description_en': SCHEMA[t]['en'], 'rows': int(len(tables[t])),
            'files': {'parquet': f'data/release/parquet/{t}.parquet',
                      **({'csv': f'data/release/csv/{t}.csv'} if t in CSV_TABLES else {})},
            'columns': [{'name': c, 'type': str(tables[t][c].dtype), 'description_he': he, 'description_en': en}
                        for c, (he, en) in SCHEMA[t]['columns'].items()],
        } for t in ORDER],
    }


def open_sql():
    q = lambda s: s.replace("'", "''")
    lines = ['-- Opens the release as DuckDB views with documented columns. Run from the repository root:',
             "--   duckdb -init data/release/open.sql   or   con.execute(open('data/release/open.sql').read())",
             "-- List every table and column with its meaning:",
             "--   SELECT table_name, column_name, comment FROM duckdb_columns() WHERE comment IS NOT NULL;", '']
    for t in ORDER:
        s = SCHEMA[t]
        lines.append(f"CREATE OR REPLACE VIEW {t} AS SELECT * FROM read_parquet('data/release/parquet/{t}.parquet');")
        lines.append(f"COMMENT ON VIEW {t} IS '{q(s['en'] + ' | ' + s['he'] + ' | grain: ' + s['grain'])}';")
        for c, (he, en) in s['columns'].items():
            lines.append(f"COMMENT ON COLUMN {t}.\"{c}\" IS '{q(en + ' | ' + he)}';")
        lines.append('')
    return '\n'.join(lines)


def write_catalog_xlsx(tables, path):
    ind = tables['indicators']
    cov = tables['coverage'].pivot_table(index='indicator_id', columns='year', values='n_values', fill_value=0)
    cov = ind[['indicator_id', 'topic_name', 'name']].merge(cov, left_on='indicator_id', right_index=True, how='left')
    with pd.ExcelWriter(path, engine='openpyxl') as xw:
        tables['about'].to_excel(xw, sheet_name='about', index=False)
        tables['topics'].to_excel(xw, sheet_name='topics', index=False)
        ind.to_excel(xw, sheet_name='indicators', index=False)
        cov.to_excel(xw, sheet_name='coverage (authorities)', index=False)
        tables['authorities'].to_excel(xw, sheet_name='authorities', index=False)
        tables['authority_aliases'].to_excel(xw, sheet_name='authority_aliases', index=False)
        doc = [(t, c, he, en) for t in ORDER for c, (he, en) in SCHEMA[t]['columns'].items()]
        pd.DataFrame(doc, columns=['table', 'column', 'תיאור', 'description']).to_excel(xw, sheet_name='columns', index=False)
        for ws in xw.book.worksheets:
            ws.sheet_view.rightToLeft = True
            ws.freeze_panes = 'B2'
            if ws.max_row > 1:
                ws.auto_filter.ref = ws.dimensions


README_INTRO = """# מסד נתוני הרשויות המקומיות (למ"ס), 2003–2024

מסד נתונים אחד לכל קבצי "הרשויות המקומיות בישראל" של הלמ"ס, 2003–2024: כל הרשויות, כל המדדים, לאורך כל השנים,
עם השוואה ארצית ולפי אשכול חברתי-כלכלי. רשויות אשכול הגליל המזרחי והמערבי מסומנות.

> **This file is generated** by `etl/release.py` from the same definitions as `schema.json` and the DuckDB column
> comments. Edit the definitions there, not this file.

## איך פותחים

| כלי | איך |
|---|---|
| Python + DuckDB (מומלץ) | `from etl.db import connect; con = connect()` ואז `con.sql("SELECT ...")`. כל טבלה ועמודה מתועדת: `SELECT table_name, column_name, comment FROM duckdb_columns() WHERE comment IS NOT NULL` |
| DuckDB CLI | מתיקיית ה-repo: `duckdb -init data/release/open.sql` |
| pandas / R / Power BI | `data/release/parquet/<table>.parquet` |
| Excel | `data/release/catalog.xlsx` (מדדים, זמינות לפי שנה, רשויות, מילון עמודות) · טבלאות קטנות ב-`data/release/csv/` |
| סוכן AI | `AGENTS.md` בשורש ה-repo, ו-`data/release/schema.json` |

## איך הנתונים מאורגנים — מושגי יסוד

* **מתחילים מ-`indicators`**: כל מדד עם נושא (`topic`), סוג (`measure_type`), יחידה, **שנות הנתון** הזמינות
  (`first_year`, `last_year`, `missing_years`), אילו רשויות מכוסות (`applies_to`), בעיות איכות ידועות (`quality_flags`)
  ומדדים קשורים (`same_values_as`, `continues`, `continued_by`, `derived_from`). `coverage` מראה לכל מדד ושנה כמה רשויות
  יש להן ערך.
* **חיפוש מדד לפי שם**: השם מתחיל בכותרת הפרק של הלמ"ס והרמות מופרדות ב-` › ` (`דמוגרפיה › סה"כ אוכלוסייה בסוף השנה`),
  ולכן מחפשים מילה בתוך השם (`name LIKE '%אוכלוסייה%'`) ולא תחילית. הכתיב אחיד: כתיב מלא (אוכלוסייה, עירייה) ו-`סה"כ`.
  אוכלוסייה, אשכול חברתי-כלכלי ופריפריאליות לכל רשות ושנה מוכנים ב-`authority_year`.
* **`year` הוא שנת הנתון, לא שנת הקובץ.** קובץ 2024 מכיל שכר של 2023 ושנת לימודים תשפ"ד (= 2024). משמעות השנה לכל
  מדד ב-`indicators.period_kind`; הנוסח המקורי ב-`observations.data_period`; הקובץ שממנו נלקח הערך ב-`source_file_year`.
* **סמל רשות** (`muni_code`) לפי סכמת 2024: מועצה אזורית = 5500 + מספר (הגליל העליון = 5501). חיפוש לפי שם — דרך
  `authority_aliases.alias_normalized` (כל הכתיבים: קרית/קריית, עג'ר/ע'ג'ר...).
* **ערכים מיוחדים** (`observations.flag`): `estimate` = אומדן (בסוגריים במקור) · `nil` = "-" "חוסר מקרים" (נשמר כ-0
  במדדי כמות, ריק בשיעורים) · `not_available` = ".." · `footnote` · `range` · `malformed_number`. שורה עם דגל היא
  מידע, לא חוסר: היא מבחינה בין "לא פורסם" לבין "אפס".
* **יחידות**: הערכים אחרי המרות שאושרו (`etl/config/unit_decisions.yaml`), למשל אוכלוסייה 2003–2017 שפורסמה באלפים.
  הערך המקורי ב-`value_published`, המקדם ב-`unit_factor`, וההסבר ב-`indicators.unit_note`.
* **סוגי מדדים**: `count` (גדל עם גודל הרשות — להשוואה בין רשויות השתמשו בגרסה `_k` ל-1,000 תושבים) · `rate` ·
  `index` · `attribute`.
* **אשכול חברתי-כלכלי** בשתי גרסאות ב-`authority_year`: `ses_cluster` = המהדורה האחרונה שפורסמה עד אותה שנה;
  `ses_cluster_latest` = המהדורה האחרונה לכל השנים (קבוצת השוואה קבועה).
* **סדרות שנשברו**: כשהלמ"ס שינתה ניסוח או מבנה (למשל טבלאות התקציב ב-2017), אותו מושג עשוי להופיע כשני מדדים.
  הם **לא אוחדו** אוטומטית; הקשר מופיע ב-`continues` / `continued_by` עם מתאם הערכים.
* **ביטחון בשיוך** (`observations.mapping_confidence`): high / medium / low — האם עמודת המקור שייכת לסדרה.
* **גרסאות**: כשכמה קבצים מדווחים על אותה שנה, נבחר הקובץ החדש ביותר שיש בו ערך; ערכים שונים מקבצים אחרים ב-
  `observation_revisions`.
"""


def write_readme(tables, about, audit):
    L = [README_INTRO]
    L += ['## הטבלאות', '', '| טבלה | שורה אחת לכל | שורות | תיאור |', '|---|---|---|---|']
    for t in ORDER:
        L.append(f"| `{t}` | {SCHEMA[t]['grain']} | {len(tables[t]):,} | {SCHEMA[t]['he']} |")
    L += ['', 'מפתחות: `observations` ← (`muni_code`, `indicator_id`, `year`); `indicator_id` → `indicators`; '
          '`muni_code` → `authorities`; `authority_year` ← (`muni_code`, `year`).', '']
    L += ['## נושאים', '', '| topic | נושא | מדדים |', '|---|---|---|']
    L += [f'| `{r.topic}` | {r.topic_name} | {r.n_indicators} |' for r in tables['topics'].itertuples()]
    L += ['', '## אמינות: מה נבדק', '',
          'כל בנייה מריצה בדיקה עצמאית מול קבצי המקור (`etl/audit.py`, תוצאות ב-`data/qa/audit.json`). '
          'כשל קריטי עוצר את הבנייה ושום דבר לא מתפרסם.', '',
          '| בדיקה | תוצאה | פירוט |', '|---|---|---|']
    for r in audit:
        res = 'עבר' if r['ok'] else ('נכשל' if r['critical'] else 'אזהרה')
        L.append(f"| {r['check']} · {r['name']} | {res} | {r['detail']} |")
    L += ['', '## בעיות ידועות במקור ובמסד', '',
          '* **שיעורי צריכת המים 2022–2023** (ביתית וחקלאית) בקבצי הלמ"ס אינם תואמים את נפחי הצריכה שבאותם קבצים. '
          'הערכים נשמרו כפי שפורסמו ומסומנים `consistency_issue`; לשנים אלה עדיף לחשב מהנפחים.',
          '* **"אחוז עובדי הוראה משתלמים" 2019**: בחלק מהרשויות פורסם שבר (0.77) במקום אחוז (77) באותה עמודה. '
          'מסומן `mixed_scale`; לא הומר.',
          '* **מספרים פגומים** (`malformed_number`, למשל `569.453.0`) בחיוב ארנונה לקרקע תפוסה במפעל עתיר שטח, 2013–2015. '
          'הטקסט המקורי ב-`value_text`; לא פוענח.',
          '* **2003 ו-2008**: הלמ"ס השאירה תאים ריקים במקום "-"/"..", ולכן אין הבחנה בין אפס לחוסר נתון.',
          '* **מבנה התקציב השתנה ב-2017**: רוב סדרות התקציב נשברות בין 2016 ל-2017 (ראו `continues`).',
          '* **ארנונה "ליתר סוגי נכס"** משנה הגדרה כשנוספים סוגי נכס; ערכים שונים בין קבצים ב-`observation_revisions`.',
          '* **שימושי קרקע**: מהדורות 2002, 2013 ו-2021 בסיווגים שונים; לא בהכרח ברי-השוואה.',
          '* **שבירה פתוחה**: חיוב ארנונה למבנה חקלאי (ש"ח) 2012→2013 — קפיצה של פי 10 בחלק מהרשויות, טרם הוחלט.',
          '* **"כלל ארצי" הרשמי** גבוה מסכום הרשויות (אוכלוסייה שאינה בתחום רשות). הסיכומים הרשמיים ב-`cbs_totals`; '
          'סטטיסטיקות על הרשויות ב-`benchmarks`.',
          '* **מהדורת המדד החברתי-כלכלי בקובץ 2003** אינה מצוינת (`ses_edition` = "unspecified").',
          f"* **גיליונות הסיכום של הלמ\"ס 2011–2021**: "
          f"{about.set_index('key').at['cbs_summary_labels_matched', 'value'].split()[0]} ערכים הותאמו "
          'למדד; השאר נשמרו ב-`cbs_totals` עם הכותרת המקורית ו-`indicator_id` ריק.', '']
    L += ['## מאיפה הנתונים מגיעים', '',
          '`*.xls*` (קבצי הלמ"ס, שורש ה-repo) → `etl/run.py` (בדיקת קבצים, חילוץ כל תא, התאמת עמודות בין שנים) → '
          '`etl/gold.py` (המרות יחידה, בחירת גרסה) → `etl/benchmarks.py` → `etl/audit.py` → `etl/release.py`. '
          'בנייה מלאה: `python -m etl.build`. החלטות אנושיות: `etl/config/` (`unit_decisions.yaml`, '
          '`column_overrides.csv`, `label_synonyms.yaml`, `consistency_rules.yaml`, `topics.yaml`).', '']
    L += ['## מילון עמודות', '']
    for t in ORDER:
        s = SCHEMA[t]
        L += [f'### `{t}`', '', f"{s['he']}  ", f"*{s['en']}* — grain: {s['grain']}; key: `{', '.join(s['primary_key'])}`", '',
              '| עמודה | סוג | תיאור | description |', '|---|---|---|---|']
        for c, (he, en) in s['columns'].items():
            L.append(f"| `{c}` | {tables[t][c].dtype} | {he} | {en} |")
        L.append('')
    with open(os.path.join(OUT, 'README.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))


def main():
    from .gold import load_yaml, resolve_key_indicators
    facts = _read('gold', 'facts.parquet')
    cat = _read('gold', 'indicators_classified.csv')
    colmap = _read('silver', 'column_map_DRAFT.csv')
    registry = _read('bronze', 'authority_registry.csv')
    summary = _read('bronze', 'summary_cells.parquet')
    ay = _read('gold', 'authority_year.csv')
    dim = _read('gold', 'dim_authority.csv')
    bench = _read('gold', 'benchmarks.parquet')
    comp = _read('gold', 'comparison_eshkol.parquet')
    consistency = _read('qa', 'consistency_violations.csv')
    mixed = _read('qa', 'mixed_scale.csv')
    breaks = _read('qa', 'audit_breaks.csv')
    audit = json.load(open(os.path.join(DATA, 'qa', 'audit.json'), encoding='utf-8'))
    unit_decisions = load_yaml('unit_decisions.yaml') or []
    keys = resolve_key_indicators(cat)

    colmap['mapping_confidence'] = mapping_confidence(colmap)
    conf = dict(zip(zip(colmap.year, colmap.sheet, colmap.col), colmap.mapping_confidence))
    obs, revisions = build_observations(facts, cat, keys['population'], consistency, mixed, conf)
    ind = build_indicators(cat, obs, colmap, ay, consistency, mixed, breaks, unit_decisions, revisions)
    auth, aliases = build_authorities(dim, registry)
    ay2 = ay.copy()
    ay2['eshkol'] = ay2['eshkol'].fillna('')
    ay2 = ay2[list(SCHEMA['authority_year']['columns'])]
    cov = build_coverage(obs, ay2, auth)
    totals, n_matched, n_summary = build_cbs_totals(facts, summary, colmap, unit_decisions)
    totals = totals[list(SCHEMA['cbs_totals']['columns'])]
    topics = ind[ind.domain != 'derived'].groupby(['topic', 'topic_name']).size().reset_index(name='n_indicators')

    bench = bench.rename(columns={'period_year': 'year'})[list(SCHEMA['benchmarks']['columns'])]
    pc = comp.rename(columns={'period_year': 'year', 'nat_median': 'national_median', 'nat_n': 'national_n',
                              'diff_nat_median': 'gap_national_median', 'diff_ses_median': 'gap_ses_median',
                              'seslatest_median': 'ses_latest_median', 'cluster_median': 'eshkol_median'})
    pc['muni_code'] = pc['muni_code'].astype('int64')
    pc = pc[list(SCHEMA['peer_comparison']['columns'])]

    passed = sum(r['ok'] for r in audit)
    git = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
    about = pd.DataFrame([
        ('built_at', dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')),
        ('pipeline_commit', git),
        ('source', 'CBS (הלמ"ס) "הרשויות המקומיות בישראל" files, one per year'),
        ('data_years', f"annual series {int(obs[obs.indicator_id.isin(ind.loc[ind.period_kind == 'calendar_year', 'indicator_id'])].year.min())}"
                       f"–{int(obs[obs.indicator_id.isin(ind.loc[ind.period_kind == 'calendar_year', 'indicator_id'])].year.max())}; "
                       f"files 2003–2024; reference periods range {int(obs.year.min())}–{int(obs.year.max())} "
                       "(e.g. climate normals 1964–1974, a June 2025 housing register)"),
        ('authorities', str(len(auth))),
        ('indicators', f"{(ind.domain != 'derived').sum()} published + {(ind.domain == 'derived').sum()} derived per 1,000 residents"),
        ('observations', f'{len(obs):,}'),
        ('audit', f'{passed}/{len(audit)} checks passed (data/qa/audit.json); every source cell re-read and compared'),
        ('cbs_summary_labels_matched', f'{n_matched}/{n_summary} summary-sheet values matched to an indicator'),
        ('year_semantics', 'year = the data year a value describes, not the file year; see indicators.period_kind'),
        ('unit_decisions', 'etl/config/unit_decisions.yaml'),
        ('mapping', 'cross-year mapping confidence per value in observations.mapping_confidence; '
                    'manual decisions: etl/config/column_overrides.csv'),
        ('docs', 'data/release/README.md · data/release/schema.json · AGENTS.md'),
    ], columns=['key', 'value'])

    tables = {'about': about, 'topics': topics, 'indicators': ind, 'coverage': cov, 'authorities': auth,
              'authority_aliases': aliases, 'authority_year': ay2, 'observations': obs,
              'observation_revisions': revisions[list(SCHEMA['observation_revisions']['columns'])],
              'cbs_totals': totals, 'benchmarks': bench, 'peer_comparison': pc}
    validate(tables)

    os.makedirs(os.path.join(OUT, 'parquet'), exist_ok=True)
    os.makedirs(os.path.join(OUT, 'csv'), exist_ok=True)
    for t in ORDER:
        tables[t].to_parquet(os.path.join(OUT, 'parquet', f'{t}.parquet'), index=False, compression='zstd')
    for t in CSV_TABLES:
        tables[t].to_csv(os.path.join(OUT, 'csv', f'{t}.csv'), index=False, encoding='utf-8-sig')
    with open(os.path.join(OUT, 'schema.json'), 'w', encoding='utf-8') as f:
        json.dump(schema_json(tables, about), f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, 'open.sql'), 'w', encoding='utf-8') as f:
        f.write(open_sql())
    write_catalog_xlsx(tables, os.path.join(OUT, 'catalog.xlsx'))
    write_readme(tables, about, audit)
    print(f'release written: {", ".join(f"{t} {len(tables[t]):,}" for t in ORDER)}')
    print(f'cbs summary-sheet values matched to indicators: {n_matched}/{n_summary}')
    return tables


if __name__ == '__main__':
    main()

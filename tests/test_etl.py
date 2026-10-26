import os

import openpyxl
import pytest
from openpyxl.styles import Border, Side

from etl.common import norm_label, normalize_code, parse_code, parse_value, strip_period
from etl.harmonize import describe_column, split_unit
from etl.headers import build_header_paths

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---- common ---------------------------------------------------------------------

@pytest.mark.parametrize('raw, expected', [
    (12.5, (12.5, None, None)),
    ('1,234', (1234.0, None, None)),
    ('-', (None, None, 'dash')),
    ('..', (None, None, 'not_available')),
    ('( 2.3)', (2.3, None, 'low_reliability')),
    ('הצפון', (None, 'הצפון', 'text')),
    ('576.650.0', (None, '576.650.0', 'malformed_number')),
    (None, (None, None, 'blank')),
])
def test_parse_value(raw, expected):
    assert parse_value(raw) == expected


def test_codes():
    assert parse_code('0026') == 26
    assert normalize_code(26, 'מועצה מקומית') == 26          # ראש פינה
    assert normalize_code(26, 'מועצה אזורית') == 5526        # מטה יהודה (pre-2024 code)
    assert normalize_code(5501, 'מועצה אזורית') == 5501      # already 2024 scheme


def test_norm_label():
    assert norm_label('סך הכל  אוכלוסייה') == 'סה"כ אוכלוסייה'
    assert norm_label('כלל ארצי1') == 'כלל ארצי'
    assert norm_label('מעמד מוניציפאלי') == 'מעמד מוניציפלי'
    assert norm_label('יישובים 4,999-2,000 תושבים') == 'יישובים 2,000-4,999 תושבים'
    assert norm_label('בני 4-0') == 'בני 0-4'
    assert norm_label('תחבורה ימית 2013 -אחוז') == 'תחבורה ימית 2013 - אחוז'


def test_strip_period():
    assert strip_period('סה"כ אוכלוסייה בסוף 2014 (אלפים)') == 'סה"כ אוכלוסייה בסוף השנה (אלפים)'
    assert strip_period('בתי ספר - סה"כ תשע"ה 2014/15') == 'בתי ספר - סה"כ'


# ---- harmonize ------------------------------------------------------------------

def test_split_unit():
    assert split_unit('צריכת מים (אלפי מ"ק)') == ('צריכת מים', ['אלפי מ"ק'])
    assert split_unit('חיובי ארנונה לפי סוג נכס - באלפי ש"ח') == ('חיובי ארנונה לפי סוג נכס', ['אלפי ש"ח'])


def test_describe_column_old_and_new_align():
    old = describe_column('אחוז בני 4-0 באוכלוסייה בסוף 2014', '', '', 2014)
    new = describe_column('דמוגרפיה › אחוז באוכלוסייה בסוף השנה › בני 4-0', '', '', 2024)
    assert old['data_period'] == '2014' and old['period_source'] == 'label'
    assert new['data_period'] == '2024' and new['period_source'] == 'file_default'
    assert sorted(old['flat_no_top'].split()) == sorted(new['flat_no_top'].split())


def test_describe_column_flat_label_keeps_first_level():
    d = describe_column('גמר בנייה: שטח (אלפי מ"ר) - סה"כ 2015', '', '', 2015)
    assert d['flat_no_top'] == d['flat']          # no category to drop in flat labels


def test_population_unit_variant():
    a = describe_column('דמוגרפיה › סה"כ אוכלוסייה בסוף השנה (אלפים)', '', '', 2017)
    b = describe_column('דמוגרפיה › סה"כ אוכלוסייה בסוף השנה', '', '', 2018)
    assert a['key'] != b['key'] and a['base_key'] == b['base_key']
    assert a['unit_hint'] == 'אלפים' and b['unit_hint'] == ''


# ---- headers --------------------------------------------------------------------

def _ws(rows, borders=()):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r, row in enumerate(rows, start=1):
        for c, v in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=v)
    thin = Side(style='thin')
    for (r, c, side) in borders:                     # 0-based row/col
        cell = ws.cell(row=r + 1, column=c + 1)
        cell.border = Border(left=thin if side == 'L' else None, right=thin if side == 'R' else None)
    return ws


def test_border_block_spreads_centred_label():
    # group label written in the middle (col 4) of a block bordered at cols 2..5
    rows = [['שם', 'סמל', None, None, 'קבוצה', None],
            ['שם', 'סמל', 'א', 'ב', 'ג', 'ד']]
    ws = _ws(rows, borders=[(0, 1, 'R'), (0, 5, 'R')])
    paths = build_header_paths(ws, [0, 1], None, None, 6)
    assert [p['levels'] for p in paths[2:]] == [['קבוצה', x] for x in 'אבגד']


def test_leaf_row_does_not_leak():
    rows = [['קטגוריה', None, None, None],
            [None, None, None, None],
            ['שם', 'סמל', 'מדד א', 'מדד ב'],
            [None, None, 'גברים', None]]
    ws = _ws(rows)
    paths = build_header_paths(ws, [0, 1, 2, 3], 1, 2, 4, leaf_rows=[3])
    assert paths[2]['levels'] == ['קטגוריה', 'מדד א', 'גברים']
    assert paths[3]['levels'] == ['קטגוריה', 'מדד ב']


# ---- real files (skipped when the CBS files are absent) -------------------------

needs_files = pytest.mark.skipif(not os.path.exists(os.path.join(ROOT, 'p_libud_24.xlsx')),
                                 reason='CBS source files not present')


@needs_files
def test_mislabeled_2019_file_detected():
    from etl.validate import detect_title_year, numeric_fingerprint
    assert detect_title_year(os.path.join(ROOT, 'p_libud_2019.xlsx')) == 2022
    assert numeric_fingerprint(os.path.join(ROOT, 'p_libud_2019.xlsx')) == \
        numeric_fingerprint(os.path.join(ROOT, 'p_libud_22.xlsx'))


@needs_files
def test_2017_rc_codes_normalized_and_collision_resolved():
    from etl.extract import extract_year, load_config
    cfg = load_config(os.path.join(ROOT, 'etl', 'config', 'sources.yaml'))
    r = extract_year(2017, cfg['years'][2017], ROOT, cfg.get('name_aliases'))
    reg = r['registry'].set_index('muni_code')
    assert reg.loc[5501, 'name'] == 'הגליל העליון'
    assert reg.loc[26, 'name'] == 'ראש פינה'
    assert reg.loc[5526, 'name'] == 'מטה יהודה'
    assert reg.index.is_unique
    # the budget sheet has no status column: codes resolved through the registry
    budget = r['cells'][r['cells']['sheet'] == 'נתוני תקציב']
    assert {5501, 26, 5526} <= set(budget['muni_code'].dropna().astype(int))


def test_hebrew_school_year_periods():
    assert strip_period('תלמידים - סה"כ תש"ע 2009/10') == 'תלמידים - סה"כ'
    assert strip_period('בתי ספר - סה"כ תשע"ה 2014/15') == 'בתי ספר - סה"כ'


def test_synonyms_unify_ses_wordings_and_keep_unrelated_words():
    from etl.harmonize import apply_synonyms
    target = 'מדד חברתי-כלכלי - אשכול (מ-1 עד 10, 1 הנמוך ביותר)'
    for old in ['רמה חברתית-כלכלית (10 הגבוה ביותר) 2006', 'אשכול חברתי-כלכלי 2008 (1 נמוך, 10 גבוה)',
                'מדד חברתי-כלכלי 2013 - אשכול (מ-1 עד 10, 1 הנמוך ביותר)']:
        out, _ = apply_synonyms(norm_label(strip_period(old)))
        assert out == target
    assert apply_synonyms('אחוז ישראלים') == ('אחוז ישראלים', False)       # 'ראלי' inside a word
    assert apply_synonyms('רמה חברתית-כלכלית - מותאמת (משולבת) (10 הגבוה ביותר)')[1] is False


def test_cohort_year_is_not_a_period():
    from etl.common import extract_period
    assert extract_period('אחוז עולי 1990+ מסך האוכלוסייה') == ''
    assert extract_period('אחוז עולי 1990+ מסך האוכלוסייה 2005') == '2005'


def test_period_year():
    from etl.gold import period_year
    assert period_year('2023') == 2023
    assert period_year('תשפ"ד 2023/24') == 2024
    assert period_year('2020 - 2024') == 2024
    assert period_year('2015 2014') == 2015
    assert period_year('תשס"ח 2008/2007') == 2008


# ---- gold / benchmarks ------------------------------------------------------------

def test_measure_type():
    from etl.benchmarks import measure_type
    assert measure_type('דמוגרפיה › לידות חי') == 'count'
    assert measure_type('דמוגרפיה › שיעור פטירות מתוקנן ל-1,000 תושבים') == 'rate'
    assert measure_type('רווחה › אחוז מקבלי דמי אבטלה מבני 67-20 (שנתי)') == 'rate'
    assert measure_type('כללי › סמל ועדת תכנון ובנייה') == 'attribute'


def test_ses_as_of_year():
    from etl.gold import _as_of
    eds = [(2003, '2003', 4), (2008, '2008', 5), (2013, '2013', 6)]
    assert _as_of(eds, 2007)[2] == 4          # latest edition published by then
    assert _as_of(eds, 2008)[2] == 5
    assert _as_of(eds, 2024)[2] == 6
    assert _as_of(eds, 2001)[2] == 4          # before the first edition: the earliest one


def test_group_stats_and_ranks_on_known_data():
    import pandas as pd
    from etl.benchmarks import group_stats, ranks
    f = pd.DataFrame({
        'indicator_id': ['X'] * 4, 'period_year': [2020] * 4, 'muni_code': [1, 2, 3, 4],
        'value': [10.0, 20.0, 30.0, 40.0], 'population': [100, 100, 100, 700],
        'status': ['עירייה', 'עירייה', 'מועצה מקומית', 'מועצה מקומית'],
        'ses_cluster': [1, 1, 2, 2], 'ses_cluster_latest': [1, 1, 2, 2],
        'ses_status': ['1|a', '1|a', '2|b', '2|b'], 'eshkol': ['גליל מזרחי', None, None, None],
    })
    b = group_stats(f).set_index(['group_type', 'group'])
    assert b.loc[('national', 'all'), 'median'] == 25.0
    assert b.loc[('national', 'all'), 'pop_weighted_mean'] == 34.0      # (10+20+30)*100+40*700 / 1000
    assert b.loc[('ses', '2'), 'mean'] == 35.0
    assert b.loc[('eshkol', 'גליל מזרחי'), 'n'] == 1
    r = ranks(f).set_index('muni_code')
    assert r.loc[4, 'pct_rank_national'] == 100.0
    assert r.loc[3, 'pct_rank_ses'] == 50.0

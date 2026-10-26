# QA report - stages 0-2

## Stage 0 - input files

| file | configured year | title year | status | note |
|---|---|---|---|---|
| 2014.xls | 2014 | 2014 | use |  |
| 2015.xls | 2015 | 2015 | use |  |
| 2017.xlsx | 2017 | 2017 | use |  |
| 2018.xlsx | 2018 | 2018 | use |  |
| 2020.xlsx | 2020 | 2020 | use |  |
| p_libud_2019.xlsx |  | 2022 | excluded | Despite its name this is the 2022 file (title "רשויות מקומיות 2022"); after dropping two added columns ("אשכול גליל מזרחי") every cell equal |
| p_libud_2021.xlsx | 2021 | 2021 | use |  |
| p_libud_22.xlsx | 2022 | 2022 | use |  |
| p_libud_23.xlsx | 2023 | 2023 | use |  |
| p_libud_24.xlsx | 2024 | 2024 | use |  |

Missing years (not in repo): 2016, 2019

## Stage 0 - Eshkol matching gate

All Eshkol authorities were found in every year by code **and** name (regional-council codes normalized to 5500+n).

- East Galilee: 18 authorities x 9 years = 162 matches, 0 missing.
- נהריה ← 'נהרייה' (fuzzy_0.91)
- קרית שמונה ← 'קריית שמונה' (fuzzy_0.95)
- טובא-זנגריה ← 'טובא-זנגרייה' (fuzzy_0.96)

## Stage 1 - extraction

| year | authorities | columns | cells | dash (-) | not available (..) | low reliability ( ) |
|---|---|---|---|---|---|---|
| 2014 | 255 | 775 | 108,795 | 11,350 | 2,631 | 91 |
| 2015 | 255 | 692 | 89,101 | 11,056 | 2,320 | 87 |
| 2017 | 255 | 388 | 97,714 | 16,271 | 6,696 | 179 |
| 2018 | 255 | 400 | 101,837 | 16,969 | 5,946 | 159 |
| 2020 | 255 | 405 | 103,093 | 17,643 | 6,648 | 155 |
| 2021 | 255 | 406 | 103,368 | 9,241 | 6,122 | 170 |
| 2022 | 256 | 419 | 108,346 | 9,283 | 6,616 | 96 |
| 2023 | 257 | 429 | 106,562 | 9,053 | 6,242 | 84 |
| 2024 | 257 | 429 | 111,271 | 7,462 | 6,416 | 70 |

Summary rows (national/status totals): 5,778 cells from transposed sheets (2014-2021) + 3,766 cells from in-sheet rows (2022-2024).

Code-resolution notes:

- 2020 / נתוני תקציב: 'יהוד' (9400) → resolved_alias: code+name_alias

## Stage 2 - cross-year indicator matching (DRAFT, for review)

| method | columns |
|---|---|
| exact | 3072 |
| new | 732 |
| tokens | 207 |
| fuzzy | 200 |
| leaf | 103 |
| unit_variant | 29 |

Indicators: 732; in all 9 years: 201; flagged for review: 413.

## Stage 2 - units (STOPPED HERE, nothing converted)

See `silver/units_review.csv`; column `decision` is for you.

| severity | indicators |
|---|---|
| unit_label_partial | 8 |
| scale_jump | 6 |

- **B6024f0** [scale_jump] תקבולים בתקציב הרגיל - לפי סוג ההכנסה › ארנונה למגורים: יחס גבייה ב-% לכלל החיובים: 2021->2022: x0.01005; 2022->2023: x98.08 — **label contradicts values: 2021->2022; 2022->2023**
- **Ba4faad** [scale_jump] תקבולים בתקציב הרגיל - לפי סוג ההכנסה › ארנונה למגורים: יחס גבייה ב-% לחיוב השנה: 2021->2022: x0.009987; 2022->2023: x98.04 — **label contradicts values: 2021->2022; 2022->2023**
- **P32dabd** [scale_jump] דמוגרפיה › סה"כ נשים בסוף השנה: 2017->2018: x1,016 — **label contradicts values: 2017->2018**
- **P8704bd** [scale_jump] שימושי קרקע קיבוץ ל-14 קטגוריות › אוכלוסייה סוף 2021 סך הכל: 2020->2021: x1,142
- **Pe3fe55** [scale_jump] דמוגרפיה › סה"כ גברים בסוף השנה: 2017->2018: x1,019 — **label contradicts values: 2017->2018**
- **Pfb4027** [scale_jump] דמוגרפיה › סה"כ אוכלוסייה בסוף השנה: 2017->2018: x1,017

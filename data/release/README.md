# מסד נתוני הרשויות המקומיות (למ"ס), 2003–2024

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

## הטבלאות

| טבלה | שורה אחת לכל | שורות | תיאור |
|---|---|---|---|
| `about` | key | 13 | מידע על הבנייה: תאריך, מקורות, שנים, סיכום הבדיקות. |
| `topics` | topic | 20 | נושאים קבועים לקיבוץ מדדים, עם מספר המדדים בכל נושא. |
| `indicators` | indicator | 1,345 | קטלוג המדדים: מה קיים, לאילו שנים, באיזו איכות ומה קשור למה. נקודת הפתיחה לכל שאילתה. |
| `coverage` | indicator × year | 10,548 | זמינות: לכל מדד ושנה, כמה רשויות יש להן ערך, "אין מקרים", "לא ידוע", אומדן. |
| `authorities` | authority | 269 | הרשויות המקומיות (כל מי שהופיעה בשנה כלשהי), עם שיוך לאשכול. |
| `authority_aliases` | alias × authority | 303 | כל כתיב של שם רשות (למ"ס לאורך השנים, רשימת האשכול) → סמל. לחיפוש לפי שם השתמשו ב-alias_normalized. |
| `authority_year` | authority × year | 5,600 | מאפייני רשות לפי שנה: מעמד, אוכלוסייה, אשכול חברתי-כלכלי ופריפריאליות. |
| `observations` | authority × indicator × year | 2,392,849 | הערכים. שורה לכל רשות, מדד ושנת נתון, כולל ערכים שהלמ"ס סימנה בסמל מיוחד, עם דגלי איכות ברמת הערך. |
| `observation_revisions` | authority × indicator × year × source file | 3,738 | ערכים שקבצים קודמים דיווחו לאותה רשות ושנה ושונים מהערך הנבחר. |
| `cbs_totals` | indicator × year × group × source | 14,030 | סיכומים רשמיים של הלמ"ס: ארצי ולפי מעמד. כולל עמודה מקורית כשלא הותאמה למדד. |
| `benchmarks` | indicator × year × group | 513,632 | סטטיסטיקות של כל הרשויות לפי קבוצות השוואה. ממוצעים ללא שקלול, אלא אם צוין. |
| `peer_comparison` | Eshkol authority × indicator × year | 322,432 | רשויות האשכול מול קבוצות ההשוואה: פערים, אחוזונים וציון z. |

מפתחות: `observations` ← (`muni_code`, `indicator_id`, `year`); `indicator_id` → `indicators`; `muni_code` → `authorities`; `authority_year` ← (`muni_code`, `year`).

## נושאים

| topic | נושא | מדדים |
|---|---|---|
| `budget_arnona` | תקציב: חיובי ארנונה | 63 |
| `budget_balance` | תקציב: עודף/גירעון ומלוות | 21 |
| `budget_expenditure` | תקציב: הוצאות | 91 |
| `budget_revenue` | תקציב: הכנסות | 128 |
| `construction_housing` | בנייה ודיור | 26 |
| `crime` | פשיעה ומשפט | 17 |
| `demography` | דמוגרפיה | 109 |
| `education` | חינוך והשכלה | 65 |
| `elections` | בחירות | 12 |
| `general` | כללי וגאוגרפיה | 17 |
| `health` | בריאות | 18 |
| `income` | שכר והכנסה | 30 |
| `indices` | מדדים: חברתי-כלכלי, פריפריאליות, קומפקטיות, טופוגרפיה | 58 |
| `land_use` | שימושי קרקע | 127 |
| `rc_settlements` | יישובים ומרחקים במועצות אזוריות | 25 |
| `survey` | סקר: שביעות רצון | 64 |
| `transport` | תחבורה | 17 |
| `waste` | פסולת | 2 |
| `water` | מים וביוב | 39 |
| `welfare` | רווחה וביטוח לאומי | 60 |

## אמינות: מה נבדק

כל בנייה מריצה בדיקה עצמאית מול קבצי המקור (`etl/audit.py`, תוצאות ב-`data/qa/audit.json`). כשל קריטי עוצר את הבנייה ושום דבר לא מתפרסם.

| בדיקה | תוצאה | פירוט |
|---|---|---|
| A · cell values equal the source | עבר | 1,827,712 cells compared, 0 differ |
| A · no numeric source cell missed | עבר | 0 numeric source cells in extracted rows were not extracted |
| A · no authority row with data skipped | עבר | 0 source rows with a name, a code and data were not extracted |
| A · authority rows without any data (info) | עבר | 13 rows list an authority but every value is empty (CBS footnote: data not reported) |
| A · row names equal the source | עבר | 0 rows whose name differs from the source |
| B · headers contained in labels | עבר | 0 header cells missing from their column label |
| A · codes resolve to the same-named authority | עבר | 11,422 rows checked, 0 mismatches |
| A · one authority per code per year | עבר | 0 duplicated (year, code) pairs |
| C · authority counts = CBS | עבר | 44 published counts compared, 0 differ |
| D · population by status = CBS totals | עבר | 42 (year, status) totals compared, 0 outside tolerance |
| E · one primary value per indicator/authority/year | עבר | 0 duplicate primary rows |
| E · every observed value has a primary | עבר | 0 keys without exactly one primary |
| E · value = published x unit factor | עבר | 0 rows differ |
| E · no data year more than 2 years after its file year | עבר | 0 rows |
| E · data years after the file year (info) | עבר | 13 indicators |
| E · ses_cluster values are integers 1-10 | עבר | 0 out of range |
| E · periphery_cluster values are integers 1-10 | עבר | 0 out of range |
| E · percentages within 0-100 | אזהרה | 68 values in 1 percentage indicators outside 0-100 |
| E · population positive | עבר | 0 non-positive |
| F · no unreviewed systematic 10x breaks | אזהרה | 4 transitions in 3 indicators where >=25% of authorities jump >=10x together (not covered by a unit decision) |
| G · population = men + women | עבר | 5,600 authority-years checked, 0 violate the identity |
| G · age-group shares sum to 100 | עבר | 5,600 authority-years checked, 0 violate the identity |
| G · domestic water share = domestic / total consumption | אזהרה | 1,995 authority-years checked, 393 violate the identity |
| G · agricultural water share = agricultural / total consumption | אזהרה | 2,500 authority-years checked, 173 violate the identity |
| G · water loss share = loss / receipts | אזהרה | 4,323 authority-years checked, 2 violate the identity |
| H · no mixed fraction/percent scale within a column | אזהרה | 1 indicator-years mix fractions and percentages |

## בעיות ידועות במקור ובמסד

* **שיעורי צריכת המים 2022–2023** (ביתית וחקלאית) בקבצי הלמ"ס אינם תואמים את נפחי הצריכה שבאותם קבצים. הערכים נשמרו כפי שפורסמו ומסומנים `consistency_issue`; לשנים אלה עדיף לחשב מהנפחים.
* **"אחוז עובדי הוראה משתלמים" 2019**: בחלק מהרשויות פורסם שבר (0.77) במקום אחוז (77) באותה עמודה. מסומן `mixed_scale`; לא הומר.
* **מספרים פגומים** (`malformed_number`, למשל `569.453.0`) בחיוב ארנונה לקרקע תפוסה במפעל עתיר שטח, 2013–2015. הטקסט המקורי ב-`value_text`; לא פוענח.
* **2003 ו-2008**: הלמ"ס השאירה תאים ריקים במקום "-"/"..", ולכן אין הבחנה בין אפס לחוסר נתון.
* **מבנה התקציב השתנה ב-2017**: רוב סדרות התקציב נשברות בין 2016 ל-2017 (ראו `continues`).
* **ארנונה "ליתר סוגי נכס"** משנה הגדרה כשנוספים סוגי נכס; ערכים שונים בין קבצים ב-`observation_revisions`.
* **שימושי קרקע**: מהדורות 2002, 2013 ו-2021 בסיווגים שונים; לא בהכרח ברי-השוואה.
* **שבירה פתוחה**: חיוב ארנונה למבנה חקלאי (ש"ח) 2012→2013 — קפיצה של פי 10 בחלק מהרשויות, טרם הוחלט.
* **"כלל ארצי" הרשמי** גבוה מסכום הרשויות (אוכלוסייה שאינה בתחום רשות). הסיכומים הרשמיים ב-`cbs_totals`; סטטיסטיקות על הרשויות ב-`benchmarks`.
* **מהדורת המדד החברתי-כלכלי בקובץ 2003** אינה מצוינת (`ses_edition` = "unspecified").
* **גיליונות הסיכום של הלמ"ס 2011–2021**: 6351/10332 ערכים הותאמו למדד; השאר נשמרו ב-`cbs_totals` עם הכותרת המקורית ו-`indicator_id` ריק.

## מאיפה הנתונים מגיעים

`*.xls*` (קבצי הלמ"ס, שורש ה-repo) → `etl/run.py` (בדיקת קבצים, חילוץ כל תא, התאמת עמודות בין שנים) → `etl/gold.py` (המרות יחידה, בחירת גרסה) → `etl/benchmarks.py` → `etl/audit.py` → `etl/release.py`. בנייה מלאה: `python -m etl.build`. החלטות אנושיות: `etl/config/` (`unit_decisions.yaml`, `column_overrides.csv`, `label_synonyms.yaml`, `consistency_rules.yaml`, `topics.yaml`).

## מילון עמודות

### `about`

מידע על הבנייה: תאריך, מקורות, שנים, סיכום הבדיקות.  
*Build information: date, sources, years, audit summary.* — grain: key; key: `key`

| עמודה | סוג | תיאור | description |
|---|---|---|---|
| `key` | str | שם הפריט | item |
| `value` | str | ערך | value |

### `topics`

נושאים קבועים לקיבוץ מדדים, עם מספר המדדים בכל נושא.  
*Stable topics grouping the indicators, with the number of indicators in each.* — grain: topic; key: `topic`

| עמודה | סוג | תיאור | description |
|---|---|---|---|
| `topic` | str | מפתח הנושא (אנגלית) | topic key |
| `topic_name` | str | שם הנושא | topic name (Hebrew) |
| `n_indicators` | int64 | מספר מדדים בנושא | number of indicators |

### `indicators`

קטלוג המדדים: מה קיים, לאילו שנים, באיזו איכות ומה קשור למה. נקודת הפתיחה לכל שאילתה.  
*Indicator catalogue: what exists, for which years, at what quality and how indicators relate. Start every query here.* — grain: indicator; key: `indicator_id`

| עמודה | סוג | תיאור | description |
|---|---|---|---|
| `indicator_id` | str | מזהה יציב. P = נתונים פיזיים ואוכלוסייה, B = תקציב. סיומת _k = נגזר ל-1,000 תושבים | stable id. P = physical/population sheets, B = budget sheets. Suffix _k = derived per 1,000 residents |
| `name` | str | שם המדד בלי שנים והערות שוליים, רמות מופרדות ב-› | indicator name without years or footnote marks; levels joined by › |
| `full_label` | str | הכותרת המלאה כפי שהופיעה בקובץ האחרון | full header as printed in the latest file |
| `topic` | str | נושא (ראו טבלת topics) | topic (see topics) |
| `topic_name` | str | שם הנושא | topic name |
| `domain` | str | גיליון מקור: physical / budget / landuse / derived | source sheet family |
| `measure_type` | str | count = כמות מוחלטת (גדלה עם גודל הרשות) · rate = שיעור/אחוז/ממוצע · index = מדד מורכב/אשכול/דירוג · attribute = תכונה/מזהה | count | rate | index | attribute |
| `measure_type_basis` | str | על מה מבוסס הסיווג: label, או בדיקת נתונים שתיקנה אותו | basis of measure_type: label, or a data check that corrected it |
| `value_type` | str | numeric או text (למשל מחוז, רמת פריפריאליות בקטגוריות) | numeric or text |
| `unit` | str | יחידה (אחרי המרת יחידות). ריק = לא צוינה בכותרת | unit after unit decisions; empty = not stated in the header |
| `unit_note` | str | המרות יחידה שהוחלו, לפי שנות קובץ | unit conversions applied, by file year |
| `period_kind` | str | calendar_year · school_year (שנת לימודים, השנה = שנת הסיום) · multi_year (ממוצע רב-שנתי, השנה = שנת הסיום) · reference_year (מהדורת מדד / שנת ייחוס) | what `year` means for this indicator |
| `first_year` | Int64 | שנת הנתון הראשונה עם ערך | first data year with a value |
| `last_year` | Int64 | שנת הנתון האחרונה עם ערך | last data year with a value |
| `n_years` | int64 | מספר שנות נתון עם ערך | number of data years with a value |
| `years` | str | כל שנות הנתון עם ערך, מופרדות בפסיקים | all data years with a value |
| `missing_years` | str | שנים בתוך הטווח שאין בהן ערך | years inside the range without a value |
| `n_authorities_last_year` | int64 | מספר רשויות עם ערך בשנה האחרונה | authorities with a value in the last year |
| `applies_to` | str | מעמדות הרשויות שיש להן ערכים (עירייה / מועצה מקומית / מועצה אזורית) | municipal statuses that have values |
| `quality_flags` | str | סיכום בעיות איכות ידועות במדד (ריק = אין) | summary of known quality issues (empty = none) |
| `mapping_uncertain_columns` | int64 | מספר עמודות מקור שהשיוך שלהן לסדרה ברמת ביטחון medium/low | source columns mapped with medium/low confidence |
| `revised_values` | int64 | מספר ערכים שקובץ מאוחר דיווח עליהם ערך שונה | values a later file revised |
| `consistency_violations` | int64 | מספר ערכים שסותרים זהות פנימית בנתוני הלמ"ס (למשל אחוז ≠ מונה/מכנה) | values violating an internal identity of the CBS data |
| `mixed_scale_values` | int64 | מספר ערכים שנראים כשבר בעמודה של אחוזים (בעיה בקובץ המקור) | values that look like fractions inside a percentage column (source problem) |
| `systematic_breaks` | str | מעברי שנים שבהם רבות מהרשויות קופצות פי 10 ומעלה יחד (שינוי יחידה/הגדרה לא מטופל) | year transitions where many authorities jump >=10x together |
| `estimate_share` | float64 | שיעור הערכים שהם אומדן (בסוגריים במקור) | share of values that are estimates |
| `same_values_as` | str | מדדים עם ערכים זהים (אותו נתון שפורסם בשני מקומות) | indicators with identical values (the same data published twice) |
| `continues` | str | מדדים שייתכן שהם אותה סדרה לפני שינוי ניסוח/מבנה (לא אוחדו; לבדיקה) | indicators that may be this series before a wording/structure change (not merged) |
| `continued_by` | str | מדדים שייתכן שהם המשך הסדרה (לא אוחדו; לבדיקה) | indicators that may continue this series (not merged) |
| `derived_from` | str | למדד נגזר: המדד שממנו חושב | for a derived indicator: its base indicator |
| `label_history` | str | הכותרות בקבצי המקור לפי שנות קובץ | source headers by file year |
| `source_columns` | int64 | מספר עמודות מקור שמרכיבות את המדד | number of source columns forming the indicator |

### `coverage`

זמינות: לכל מדד ושנה, כמה רשויות יש להן ערך, "אין מקרים", "לא ידוע", אומדן.  
*Availability per indicator and year: authorities with a value, nil, not available, estimate.* — grain: indicator × year; key: `indicator_id, year`

| עמודה | סוג | תיאור | description |
|---|---|---|---|
| `indicator_id` | str | מזהה מדד | indicator id |
| `year` | int64 | שנת נתון | data year |
| `n_authorities` | int64 | מספר הרשויות הקיימות באותה שנה | authorities existing that year |
| `n_values` | int64 | רשויות עם ערך (מספר או טקסט) | authorities with a value |
| `n_nil` | int64 | רשויות שסומנו "-" (אין מקרים) | authorities marked "-" (no cases) |
| `n_not_available` | int64 | רשויות שסומנו ".." (לא ידוע / לא לפרסום) | authorities marked ".." (unknown / not publishable) |
| `n_estimate` | int64 | ערכים שהם אומדן | values that are estimates |
| `n_east_galilee` | int64 | רשויות הגליל המזרחי עם ערך | East Galilee authorities with a value |
| `n_west_galilee` | int64 | רשויות הגליל המערבי עם ערך | West Galilee authorities with a value |
| `share_with_value` | float64 | n_values / n_authorities | n_values / n_authorities |

### `authorities`

הרשויות המקומיות (כל מי שהופיעה בשנה כלשהי), עם שיוך לאשכול.  
*Local authorities (any that appeared in any year), with Eshkol membership.* — grain: authority; key: `muni_code`

| עמודה | סוג | תיאור | description |
|---|---|---|---|
| `muni_code` | int64 | סמל הרשות בלמ"ס (סכמת 2024: מועצה אזורית = 5500 + מספר) | CBS authority code (2024 scheme: regional council = 5500 + number) |
| `name` | str | השם בקובץ האחרון שבו הופיעה | name in the latest file it appears in |
| `status` | str | מעמד מוניציפלי אחרון | latest municipal status |
| `district` | str | מחוז אחרון | latest district |
| `first_year` | int64 | השנה הראשונה שבה הופיעה | first year present |
| `last_year` | int64 | השנה האחרונה שבה הופיעה | last year present |
| `n_years` | int64 | מספר שנים שבהן הופיעה | years present |
| `eshkol` | str | אשכול: גליל מזרחי / גליל מערבי / ריק | Eshkol cluster or empty |
| `eshkol_name` | str | השם ברשימת האשכול | name in the Eshkol list |
| `sector` | str | מגזר (לרשויות האשכול) | sector (Eshkol authorities) |
| `settlement_form` | str | צורת יישוב (לרשויות האשכול) | settlement form (Eshkol authorities) |
| `aliases` | str | כל הכתיבים המוכרים, מופרדים ב-| | all known spellings, |-separated |

### `authority_aliases`

כל כתיב של שם רשות (למ"ס לאורך השנים, רשימת האשכול) → סמל. לחיפוש לפי שם השתמשו ב-alias_normalized.  
*Every spelling of an authority name → code. Search on alias_normalized.* — grain: alias × authority; key: `alias, muni_code`

| עמודה | סוג | תיאור | description |
|---|---|---|---|
| `alias` | str | הכתיב כפי שהופיע | spelling as it appeared |
| `alias_normalized` | str | הכתיב אחרי ניקוי (בלי גרשיים, מקפים, סוגריים) | normalized: no quotes, hyphens, brackets |
| `muni_code` | int64 | סמל הרשות | authority code |
| `source` | str | מקור הכתיב | where the spelling comes from |

### `authority_year`

מאפייני רשות לפי שנה: מעמד, אוכלוסייה, אשכול חברתי-כלכלי ופריפריאליות.  
*Authority attributes by year: status, population, socio-economic and peripherality clusters.* — grain: authority × year; key: `muni_code, year`

| עמודה | סוג | תיאור | description |
|---|---|---|---|
| `muni_code` | int64 | סמל הרשות | authority code |
| `year` | int64 | שנה (שנת הקובץ) | year (file year) |
| `name` | str | השם באותה שנה | name that year |
| `status` | str | מעמד מוניציפלי באותה שנה | municipal status that year |
| `district` | str | מחוז באותה שנה | district that year |
| `population` | float64 | אוכלוסייה בסוף השנה (נפשות) | population at year end (persons) |
| `ses_cluster` | float64 | אשכול חברתי-כלכלי 1–10 לפי המהדורה האחרונה שפורסמה עד אותה שנה | SES cluster 1-10, latest edition published by that year |
| `ses_value` | float64 | ערך המדד החברתי-כלכלי באותה מהדורה | SES index value, same edition |
| `ses_edition` | str | שנת מהדורת המדד החברתי-כלכלי שבה השתמשנו | SES edition used |
| `ses_cluster_latest` | float64 | אשכול חברתי-כלכלי במהדורה האחרונה (קבוצת השוואה קבועה לאורך השנים) | SES cluster in the latest edition (fixed peer group) |
| `ses_edition_latest` | float64 | שנת המהדורה האחרונה | latest SES edition |
| `periphery_cluster` | float64 | אשכול פריפריאליות 1–10 (1 = הפריפריאלי ביותר) | peripherality cluster 1-10 (1 = most peripheral) |
| `periphery_edition` | float64 | מהדורת מדד הפריפריאליות | peripherality edition |
| `eshkol` | str | אשכול: גליל מזרחי / גליל מערבי / ריק | Eshkol cluster or empty |

### `observations`

הערכים. שורה לכל רשות, מדד ושנת נתון, כולל ערכים שהלמ"ס סימנה בסמל מיוחד, עם דגלי איכות ברמת הערך.  
*The values: one row per authority, indicator and data year, including CBS special symbols, with row-level quality flags.* — grain: authority × indicator × year; key: `muni_code, indicator_id, year`

| עמודה | סוג | תיאור | description |
|---|---|---|---|
| `muni_code` | int64 | סמל הרשות | authority code |
| `indicator_id` | str | מזהה מדד | indicator id |
| `year` | int64 | שנת הנתון (לא שנת הקובץ). ראו indicators.period_kind | data year (not the file year); see indicators.period_kind |
| `value` | float64 | הערך המספרי אחרי המרת יחידות. "אין מקרים" = 0 במדדי כמות; ריק כשאין מספר | numeric value after unit decisions; nil = 0 for counts; empty when no number |
| `value_text` | str | ערך טקסט (למדדי טקסט), או הטקסט המקורי כשהמספר פגום/טווח | text value, or the original text when the number is malformed or a band |
| `flag` | str | ריק = ערך רגיל · estimate = אומדן (בסוגריים במקור) · nil = "-" אין מקרים · not_available = ".." לא ידוע/לא לפרסום · footnote = עם הערת שוליים · range = טווח במקום מספר · malformed_number = מספר פגום במקור | empty | estimate | nil | not_available | footnote | range | malformed_number |
| `value_published` | float64 | המספר כפי שפורסם, לפני המרת יחידות | number as published, before unit decisions |
| `unit_factor` | float64 | המקדם שהוחל (1 = ללא המרה) | multiplier applied (1 = none) |
| `data_period` | str | התקופה כפי שנכתבה בכותרת (למשל תשפ"ד 2023/24, 2020-2024) | period as written in the header |
| `source_file_year` | int64 | שנת הקובץ שממנו נלקח הערך (הקובץ החדש ביותר שיש בו ערך) | file the value comes from (newest file with a value) |
| `is_derived` | bool | ערך נגזר (ל-1,000 תושבים), לא פורסם ישירות | derived value (per 1,000 residents), not published |
| `mapping_confidence` | str | ביטחון בשיוך עמודת המקור לסדרה: high = כותרת זהה, או התאמה שהנתונים מאששים (מתאם ≥0.9 עם השנה הסמוכה) · medium = אין נתונים לאישור / מתאם 0.5–0.9 · low = הנתונים לא ממשיכים (מתאם <0.5) | confidence that the source column belongs to this series: high | medium | low |
| `consistency_issue` | bool | הערך סותר זהות פנימית בנתוני הלמ"ס | value violates an internal CBS identity |
| `mixed_scale` | bool | הערך נראה כשבר בעמודת אחוזים (בעיה במקור) | value looks like a fraction in a percentage column |
| `revised` | bool | קובץ אחר דיווח ערך שונה לאותה רשות ושנה (ראו observation_revisions) | another file reported a different value (see observation_revisions) |

### `observation_revisions`

ערכים שקבצים קודמים דיווחו לאותה רשות ושנה ושונים מהערך הנבחר.  
*Values earlier files reported for the same authority and year that differ from the chosen value.* — grain: authority × indicator × year × source file; key: `muni_code, indicator_id, year, source_file_year`

| עמודה | סוג | תיאור | description |
|---|---|---|---|
| `muni_code` | int64 | סמל הרשות | authority code |
| `indicator_id` | str | מזהה מדד | indicator id |
| `year` | int64 | שנת נתון | data year |
| `source_file_year` | int64 | הקובץ שדיווח את הגרסה הזו | file reporting this version |
| `value` | float64 | הערך בגרסה הזו (אחרי המרת יחידות) | value in this version |
| `chosen_value` | float64 | הערך שנבחר ב-observations | value chosen in observations |
| `chosen_file_year` | int64 | הקובץ של הערך שנבחר | file of the chosen value |

### `cbs_totals`

סיכומים רשמיים של הלמ"ס: ארצי ולפי מעמד. כולל עמודה מקורית כשלא הותאמה למדד.  
*Official CBS totals: national and by municipal status.* — grain: indicator × year × group × source; key: `row_id`

| עמודה | סוג | תיאור | description |
|---|---|---|---|
| `row_id` | int64 | מזהה שורה | row id |
| `indicator_id` | str | מזהה מדד (ריק אם הכותרת בגיליון הסיכום לא הותאמה) | indicator id (empty if the summary label was not matched) |
| `year` | int64 | שנת נתון | data year |
| `group` | str | national / municipality / local_council / regional_council | national / municipality / local_council / regional_council |
| `value` | float64 | הערך אחרי המרת יחידות | value after unit decisions |
| `value_published` | float64 | הערך כפי שפורסם | value as published |
| `label` | str | הכותרת בגיליון הסיכום | label in the summary sheet |
| `source` | str | summary_sheet (2011–2021) או in_sheet_row (2022 ואילך) | summary_sheet or in_sheet_row |
| `source_file_year` | int64 | שנת הקובץ | file year |

### `benchmarks`

סטטיסטיקות של כל הרשויות לפי קבוצות השוואה. ממוצעים ללא שקלול, אלא אם צוין.  
*Statistics over authorities per peer group. Unweighted unless stated.* — grain: indicator × year × group; key: `indicator_id, year, group_type, group`

| עמודה | סוג | תיאור | description |
|---|---|---|---|
| `indicator_id` | str | מזהה מדד | indicator id |
| `year` | int64 | שנת נתון | data year |
| `group_type` | str | national · status · ses (אשכול לשנה) · ses_latest (מהדורה אחרונה) · ses_status · eshkol | peer group family |
| `group` | str | ערך הקבוצה (למשל 5, עירייה, "5 | עירייה") | group value |
| `n` | int64 | מספר רשויות עם ערך | authorities with a value |
| `mean` | float64 | ממוצע | mean |
| `median` | float64 | חציון | median |
| `std` | float64 | סטיית תקן | standard deviation |
| `min` | float64 | מינימום | min |
| `max` | float64 | מקסימום | max |
| `p25` | float64 | רבעון תחתון | 25th percentile |
| `p75` | float64 | רבעון עליון | 75th percentile |
| `pop_weighted_mean` | float64 | ממוצע משוקלל באוכלוסייה | population-weighted mean |

### `peer_comparison`

רשויות האשכול מול קבוצות ההשוואה: פערים, אחוזונים וציון z.  
*Eshkol authorities against peer groups: gaps, percentiles, z-score.* — grain: Eshkol authority × indicator × year; key: `muni_code, indicator_id, year`

| עמודה | סוג | תיאור | description |
|---|---|---|---|
| `muni_code` | int64 | סמל הרשות | authority code |
| `indicator_id` | str | מזהה מדד | indicator id |
| `year` | int64 | שנת נתון | data year |
| `value` | float64 | הערך | value |
| `ses_cluster` | Int64 | אשכול חברתי-כלכלי לשנה | SES cluster for the year |
| `national_median` | float64 | חציון ארצי | national median |
| `national_n` | int64 | מספר רשויות בארצי | authorities nationally |
| `cbs_national` | float64 | הנתון הארצי הרשמי (2022 ואילך) | official national figure (2022+) |
| `pct_rank_national` | float64 | אחוזון ארצי 0–100 | national percentile 0-100 |
| `gap_national_median` | float64 | פער מהחציון הארצי | gap from the national median |
| `ses_median` | float64 | חציון האשכול החברתי-כלכלי | median of the SES cluster |
| `ses_n` | float64 | מספר רשויות באשכול | authorities in the SES cluster |
| `pct_rank_ses` | float64 | אחוזון בתוך האשכול | percentile within the SES cluster |
| `z_ses` | float64 | ציון z בתוך האשכול | z-score within the SES cluster |
| `gap_ses_median` | float64 | פער מחציון האשכול | gap from the SES-cluster median |
| `ses_latest_median` | float64 | חציון האשכול במהדורה האחרונה | median of the latest-edition SES cluster |
| `status_median` | float64 | חציון רשויות באותו מעמד | median of authorities with the same status |
| `eshkol_median` | float64 | חציון רשויות האשכול הגלילי | median of the Eshkol cluster |

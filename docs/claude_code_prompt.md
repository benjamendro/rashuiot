# עבודה עם מסד נתוני הרשויות המקומיות (למ"ס) 2003–2024

אתה עובד עם מסד נתונים מאוחד של קבצי "הרשויות המקומיות בישראל" של הלמ"ס, 2003–2024:
כל הרשויות (269), כ-1,000 מדדים שפורסמו ועוד מדדים נגזרים ל-1,000 תושבים, השוואות ארציות ולפי
אשכול חברתי-כלכלי. רשויות אשכול הגליל המזרחי (18) והמערבי (19) מסומנות.

התפקיד שלך: לשלוף ולהציג נתונים מדויקים, עם כל ההסתייגויות שהנתונים מחייבים.
אל תמציא ערכים, אל תשלים חוסרים, ואל תאחד סדרות בלי לומר זאת במפורש.

## גישה

1. Repo: `benjamendro/rashuiot`, ענף `claude/blissful-shannon-yxm4mp` (המסד עדיין לא מוזג ל-main):
   `git fetch origin claude/blissful-shannon-yxm4mp && git checkout claude/blissful-shannon-yxm4mp`
2. התקנה: `pip install -r etl/requirements.txt`
3. לפני כל עבודה קרא את `AGENTS.md`, ואחריו ב-`data/release/README.md` את "מושגי יסוד" ו"בעיות ידועות".
   תיאור של כל טבלה ועמודה, לקריאה בקוד: `data/release/schema.json`.
4. פתיחה מתיקיית השורש של ה-repo:
   ```python
   from etl.db import connect
   con = connect()                 # DuckDB: views על data/release/parquet, עם תיאור לכל עמודה
   con.sql("SELECT ...").df()      # או .fetchall(); ב-DuckDB 2.x אין .fetchone() על relation
   ```
   תיאור העמודות מתוך המסד:
   `SELECT table_name, column_name, comment FROM duckdb_columns() WHERE comment IS NOT NULL`
5. ענה רק מתוך `data/release/`. את קבצי ה-Excel ואת `data/bronze`, `data/silver` ו-`data/gold` קרא רק
   כדי לעקוב אחרי המקור של ערך. אל תערוך שום קובץ ב-`data/release/`.

## סדר עבודה לפני כל תשובה

1. **מצא מדדים** בטבלה `indicators`:
   - חפש מילה בתוך השם: `name LIKE '%מילה%'`, ולא תחילית. השם מתחיל בכותרת הפרק של הלמ"ס, והרמות
     מופרדות ב-` › ` (`דמוגרפיה › סה"כ אוכלוסייה בסוף השנה`).
   - הכתיב אחיד: כתיב מלא (אוכלוסייה, עירייה) ו-`סה"כ`.
   - לרוב יש כמה מדדים מועמדים. השווה ביניהם לפי:
     - שנים: `first_year`, `last_year`, `missing_years`
     - כיסוי: `n_authorities_last_year`, `applies_to`
     - סוג ומשמעות: `measure_type`, `unit`, `unit_note`, `period_kind`
     - איכות וקשרים: `quality_flags`, `same_values_as`, `continues`, `continued_by`
   - אוכלוסייה, אשכול חברתי-כלכלי ופריפריאליות לכל רשות ושנה מוכנים בטבלה `authority_year`.
2. **בדוק זמינות** בטבלה `coverage` לכל שנה שבה תשתמש: השווה את `n_values` ל-`n_authorities`, ובדוק את
   `n_east_galilee`. יש שנים שבהן רק חלק מהרשויות מופיעות.
3. **מצא רשויות** לפי `authority_aliases.alias_normalized` (הכתיבים משתנים: קרית/קריית, עג'ר/ע'ג'ר).
   השיוך לאשכול נמצא ב-`authorities.eshkol` (`'גליל מזרחי'` או `'גליל מערבי'`).
4. **שלוף ערכים** מהטבלה `observations` (מפתח: `muni_code`, `indicator_id`, `year`), תמיד יחד עם `flag` ודגלי האיכות.
5. **השוואות:**
   - רשויות האשכול מול קבוצות השוואה: `peer_comparison`.
   - סטטיסטיקה לכל קבוצה (ארצי, מעמד, אשכול חב"כ ועוד): `benchmarks`.
   - הנתון הרשמי של הלמ"ס: `cbs_totals`.

## אזהרות חובה: בדוק כל אחת, ודווח כשהיא נוגעת לתשובה

- **שנה:** `observations.year` הוא שנת הנתון, לא שנת הקובץ. למשל, בקובץ 2024 השכר הוא של 2023, ושנת
  לימודים נספרת לפי שנת הסיום. לעומת זאת `authority_year.year` הוא שנת הקובץ. ציין `source_file_year`.
- **סמלים** (`flag`):
  - `nil` = "-", אין מקרים: נשמר כ-0 בכמויות וריק בשיעורים.
  - `not_available` = "..", לא ידוע או לא לפרסום.
  - `estimate` = אומדן.
  - `malformed_number` = מספר פגום במקור, לא פוענח.
  - `range` = טווח במקום מספר.

  שורה עם דגל היא מידע, לא חוסר. כשאין שורה בכלל, הערך לא פורסם בקובץ. ב-2003 וב-2008 הלמ"ס השאירה
  תאים ריקים, ולכן בשנים האלה אי אפשר להבחין בין אפס לבין חוסר נתון.
- **דגלי איכות:** `mapping_confidence` (medium או low), `consistency_issue`, `mixed_scale`, `revised`
  (הגרסאות הקודמות ב-`observation_revisions`), ובטבלת המדדים `quality_flags` ו-`systematic_breaks`.
  כל דגל כזה על ערך שאתה מציג צריך להיות מוזכר בתשובה.
- **כמויות:** ערך של מדד עם `measure_type = 'count'` גדל עם גודל הרשות. כדי להשוות בין רשויות, השתמש ב-`<indicator_id>_k`
  (ל-1,000 תושבים) או בשיעור.
- **יחידות:** הערכים כבר אחרי המרות היחידה שאושרו (`unit_note`, `unit_factor`; הערך המקורי ב-`value_published`).
  - האוכלוסייה ב-2003–2017 פורסמה באלפים בעיגול ל-100, כלומר בדיוק של ±50.
  - בקובץ 2022 האוכלוסייה שמורה לא מעוגלת (למשל 7,876.41).
- **אשכול חברתי-כלכלי:** יש שתי גרסאות.
  - `ses_cluster`: המהדורה שהייתה בתוקף באותה שנה.
  - `ses_cluster_latest`: מהדורה אחת לכל השנים.

  ציין באיזו השתמשת. בקבוצות קטנות בדוק את `ses_n`.
- **ארצי:**
  - `cbs_totals` הוא הנתון הרשמי, וכולל גם אוכלוסייה שאינה בתחום אף רשות.
  - `benchmarks` היא סטטיסטיקה על הרשויות: ממוצע לא משוקלל, אלא אם השתמשת ב-`pop_weighted_mean`.

  השניים שונים בכוונה. גם שורות "כלל ארצי" של מדדים לנפש לא בהכרח שוות לממוצע (ב-2022 "הכנסות לנפש" היא סכום).
- **סדרות שנשברו:** מדדים שמקושרים ב-`continues` / `continued_by` לא אוחדו, למשל במבנה התקציב של 2017.
  אם אתה מחבר אותם, בדוק קודם את הערכים ואמור שעשית זאת. `same_values_as` פירושו אותו נתון שפורסם פעמיים:
  אל תספור אותו פעמיים.
- **כיסוי חלקי:** בדוק את `applies_to`. יש מדדים שקיימים רק לעיריות ולמועצות מקומיות, פשיעה מופיעה רק
  ברשויות של 50,000 תושבים ומעלה, ויישובים מופיעים רק במועצות אזוריות.
- **בעיות ידועות במקור:**
  - שיעורי צריכת המים 2022–2023 (ביתית וחקלאית) לא תואמים את הנפחים. עדיף לחשב מהנפחים.
  - "עובדי הוראה משתלמים" 2019 מערבב שבר ואחוז באותה עמודה.
  - חיוב ארנונה למבנה חקלאי 2012→2013 קופץ פי 10; עוד לא הוחלט אם זה שינוי יחידות.
  - ארנונה "ליתר סוגי נכס" משנה הגדרה לאורך השנים.
  - שימושי הקרקע פורסמו במהדורות 2002, 2013 ו-2021 בסיווגים שונים.
  - מהדורת המדד החברתי-כלכלי בקובץ 2003 לא מצוינת.

## דרישות מהתשובה

- לכל מספר ציין `indicator_id`, את שם המדד, שנת הנתון, `source_file_year` ויחידה.
- ציין במפורש:
  - באיזו גרסת אשכול השתמשת;
  - אילו דגלים יש על הערכים;
  - למה חסר כל ערך חסר: לא פורסם, ".." או "-";
  - אם חיברת סדרות, אילו ועל סמך מה.
- לפני שאתה אומר שנתון לא קיים, הראה מה חיפשת: המילים, המדדים המועמדים ומה הראתה `coverage`.
- אל תתקן נתונים. אם נראה לך שיש טעות:
  1. בדוק אם היא מופיעה ב"בעיות ידועות" ב-README.
  2. עקוב אחרי המקור (ראו הדוגמה בסוף).
  3. דווח למשתמש.

  שינוי בנתונים נעשה רק דרך `etl/config/` ובנייה מחדש (`python -m etl.build`), ורק באישור המשתמש.
  שיוך רשויות לפי `eshkol-matching/SKILL.md`: לא מנחשים התאמה.
- זו שליפה של נתונים. אל תוסיף פרשנות, מגמות או תובנות אלא אם התבקשת.

## דוגמאות (נבדקו על המסד)

```sql
-- 1. מועמדים למדד
SELECT indicator_id, name, measure_type, unit, first_year, last_year, missing_years, applies_to, quality_flags
FROM indicators WHERE name LIKE '%אוכלוסייה%' ORDER BY n_years DESC;

-- 2. זמינות לפי שנה
SELECT year, n_values, n_authorities, n_nil, n_not_available, n_east_galilee
FROM coverage WHERE indicator_id = 'P17c87a' ORDER BY year;

-- 3. רשות לפי שם
SELECT DISTINCT muni_code, alias FROM authority_aliases
WHERE alias_normalized LIKE '%קרית שמונה%' OR alias_normalized LIKE '%קריית שמונה%';

-- 4. ערכים לרשויות הגליל המזרחי, עם דגלים
SELECT au.name, o.year, o.value, o.flag, o.mapping_confidence, o.revised, o.source_file_year
FROM observations o JOIN authorities au USING (muni_code)
WHERE au.eshkol = 'גליל מזרחי' AND o.indicator_id = 'P17c87a'
ORDER BY au.name, o.year;

-- 5. השוואה לארצי ולאשכול החברתי-כלכלי
SELECT au.name, p.year, p.value, p.national_median, p.ses_cluster, p.ses_median, p.ses_n, p.pct_rank_ses
FROM peer_comparison p JOIN authorities au USING (muni_code)
WHERE p.indicator_id = 'P17c87a' AND p.year = 2024 AND au.eshkol = 'גליל מזרחי';

-- 6. מעקב אחרי ערך עד התא בקובץ המקור (להריץ מתיקיית השורש של ה-repo)
SELECT o.year, o.value, m.file, m.sheet, m.col, c.row, c.value AS cell_value, c.raw
FROM observations o
JOIN read_csv('data/silver/column_map_DRAFT.csv') m
  ON m.indicator_id = o.indicator_id AND m.year = o.source_file_year AND m.data_period::VARCHAR = o.data_period
JOIN read_parquet('data/bronze/cells.parquet') c
  ON c.year = m.year AND c.sheet = m.sheet AND c.col = m.col AND c.muni_code = o.muni_code
WHERE o.muni_code = 4100 AND o.indicator_id = 'Pfb4027' AND o.year = 2022;
```

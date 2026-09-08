/* ───────────────────────────────────────────────────────────────
   content.js — THE REPORT. Edit this object (Method B), or edit
   content.md and regenerate (Method A), or use ✏️ edit mode in the
   browser. This file ships with a worked EXAMPLE — replace the text
   and numbers with your own.
   See AUTHORING.md for the full schema and section catalogue.
   ─────────────────────────────────────────────────────────────── */
window.REPORT = {
  "brand": {
    "name": "שם הארגון שלך",
    "nameEn": "YOUR ORGANIZATION",
    "logo": "assets/logo.jpg"
  },
  "theme": "mosaic",
  "nav": [
    { "id": "intro", "label": "מבוא" },
    { "id": "trend", "label": "מגמה" },
    { "id": "breakdown", "label": "פילוח" },
    { "id": "recs", "label": "המלצות" },
    { "id": "sources", "label": "מקורות" }
  ],
  "hero": {
    "meta": ["סוג הדוח", "עדכון: חודש שנה"],
    "title": "כותרת ראשית של הדוח",
    "titleAccent": "תת-כותרת מודגשת",
    "sub": "פסקת פתיחה קצרה שמסבירה במשפט-שניים על מה הדוח ומה הקורא עומד לגלות.",
    "foot": ["מדד 1", "מדד 2", "מדד 3", "מדד 4"]
  },
  "sections": [
    {
      "id": "intro", "kind": "rich", "kicker": "מבוא",
      "title": "כותרת המבוא",
      "lede": "משפט מוביל אחד שתופס את המסר המרכזי של הדוח.",
      "body": [
        "פסקת גוף ראשונה. אפשר להשתמש ב<strong>הדגשה</strong> לטקסט חשוב.",
        "פסקת גוף שנייה — הקשר, רקע, או הגדרת מונחים."
      ]
    },
    {
      "id": "kpis", "kind": "kpis", "kicker": "במספרים", "title": "המדדים המרכזיים",
      "items": [
        { "value": 85, "unit": "%", "label": "מדד ראשי", "note": "הערת הסבר" },
        { "value": 734, "unit": "", "label": "סך הנמדדים", "note": "כלל האוכלוסייה" },
        { "value": 12, "unit": "", "label": "מדד שלישי", "note": "הערה" },
        { "value": 3.4, "unit": "", "label": "מדד רביעי", "note": "הערה" }
      ]
    },
    {
      "id": "trend", "kind": "line", "kicker": "מגמה לאורך זמן",
      "title": "כותרת הגרף",
      "sub": "תיאור קצר של מה שהגרף מציג.",
      "source": "מקור הנתונים והערה פרשנית קצרה על המגמה.",
      "unit": "%",
      "x": ["ינואר", "פברואר", "מרץ", "אפריל", "מאי"],
      "values": [50, 59, 38, 26, 56],
      "color": "var(--c-cyan)"
    },
    {
      "id": "breakdown", "kind": "barRanked", "kicker": "פילוח", "band": "alt",
      "title": "דירוג לפי קטגוריה",
      "sub": "תיאור קצר.",
      "source": "מקור הנתונים.",
      "unit": "%",
      "data": [
        { "label": "קטגוריה א", "value": 77 },
        { "label": "קטגוריה ב", "value": 62 },
        { "label": "קטגוריה ג", "value": 54 },
        { "label": "קטגוריה ד", "value": 53 }
      ]
    },
    {
      "id": "share", "kind": "donut", "kicker": "התפלגות", "title": "חלוקה לפי סטטוס",
      "sub": "תיאור קצר.", "unit": "פריטים",
      "data": [
        { "label": "קבוצה 1", "value": 408, "color": "var(--c-lime)" },
        { "label": "קבוצה 2", "value": 88, "color": "var(--c-gold)" },
        { "label": "קבוצה 3", "value": 205, "color": "var(--c-navy)" },
        { "label": "קבוצה 4", "value": 33, "color": "var(--c-magenta)" }
      ]
    },
    {
      "id": "method", "kind": "flow", "kicker": "מתודולוגיה", "title": "איך הופקו התוצאות",
      "body": "תיאור קצר של שלבי העיבוד.",
      "steps": [
        { "n": "1", "title": "שלב ראשון", "body": "מה נעשה בשלב זה.", "tools": ["כלי", "מקור"] },
        { "n": "2", "title": "שלב שני", "body": "מה נעשה בשלב זה.", "tools": ["כלי"] },
        { "n": "3", "title": "שלב שלישי", "body": "מה נעשה בשלב זה.", "tools": ["כלי"] }
      ]
    },
    {
      "id": "recs", "kind": "recs", "kicker": "המלצות", "title": "המלצות למקבלי החלטות",
      "items": [
        { "tag": "תגית", "title": "המלצה ראשונה", "body": "הסבר קצר על ההמלצה ועל הצעד המעשי." },
        { "tag": "תגית", "title": "המלצה שנייה", "body": "הסבר קצר." },
        { "tag": "תגית", "title": "המלצה שלישית", "body": "הסבר קצר." }
      ]
    },
    {
      "id": "sources", "kind": "sources", "kicker": "מקורות נתונים", "title": "מאגרי המידע",
      "cols": ["מקור", "היקף", "תקופה", "איכות", "הערות"],
      "rows": [
        { "nm": "מקור ראשי", "scope": "היקף", "period": "תקופה", "quality": "high", "notes": "הערה" },
        { "nm": "מקור משני", "scope": "היקף", "period": "תקופה", "quality": "med", "notes": "הערה" }
      ]
    }
  ],
  "footer": {
    "meta": ["תאריך הפקה: __/__/____", "מקור: __"],
    "sig": "הופק על ידי שם הארגון שלך."
  }
};

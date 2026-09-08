# Interactive StoryReport — Template
### תבנית דוח אינטראקטיבי · מרכז הידע האזורי גליל מזרחי

A reusable, brand-driven **interactive report** (Hebrew, RTL): a scroll-driven story with
animated charts, KPI counters, a methodology flow, recommendations, and an event invite.
Built to be re-used for **any** project — change the content, optionally the brand, done.

**Open:** `Knowledge Center Report.html`

---

## עברית — מדריך מהיר

### מה זה
דוח אינטראקטיבי בעברית (RTL) שמספר סיפור נתונים תוך כדי גלילה: תרשימים מונפשים, מספרי-מפתח,
מתודולוגיה, המלצות והזמנה לאירוע. התבנית מיועדת לשימוש חוזר — מחליפים תוכן, ומקבלים דוח חדש.

### איך כותבים דוח חדש
**הדרך הקלה ביותר — עורך ללא קוד:** פתחו את **`Report Editor.html`**. עורכים את הטקסט בצד,
התצוגה מתעדכנת מיד, ובסיום מורידים `content.js` ושמים בתיקיית `template/`.
**או דרך הסוכן:** עורכים את **`template/content.md`** ומבקשים *"apply content.md"*.
הקובץ מגיע מלא בדוגמה (הדוח הנוכחי).

### החלפת מותג (לפרויקט אחר)
- **לוגו:** החליפו את `assets/logo.jpg`.
- **שם:** עדכנו `name` / `nameEn` בראש `content.md`.
- **צבעים וערכת נושא:** לוח ה-Tweaks (פתחו דרך סרגל הכלים) — שלוש ערכות נושא, בחירת צבע, וצפיפות.

### צפייה ושיתוף
פותחים את `Knowledge Center Report.html`. אפשר לייצא ל-PDF או לקובץ HTML עצמאי (בקשו מהסוכן).

---

## English — Quick start

### Three ways to author
| | How | Best for |
|---|---|---|
| **A · No-code editor** | Open **`Report Editor.html`** — edit text on the left, watch the live preview on the right, then download `content.js` | Editing yourself, no agent |
| **B · Markdown + agent** | Edit `template/content.md`, then tell the agent *"apply content.md"* | Letting the AI fill it from your context |
| **C · Config** | Edit `template/content.js` (`window.REPORT`) directly | Full control |
| **Look** | Open the **Tweaks** panel → theme / accent / density | Restyling only |

### Use it for a different project
1. **Rebrand** — replace `assets/logo.jpg`; set `name`/`nameEn` and `theme` at the top of
   `content.md`. The palette is sampled from the logo; pick a new accent in Tweaks.
2. **Rewrite content** — in `content.md`, change the hero, nav, and each `## section`.
   Add/remove/reorder sections freely. Each section's `[kind]` picks its layout.
3. **Apply** — *"apply content.md"*, or edit `content.js` directly.

### Section kinds (pick per section)
`rich` (text) · `kpis` (stat cards) · `barRanked` (ranked bars) · `barColumns` (columns) ·
`grouped` (two-series compare) · `donut` · `line` · `pull` (giant number) · `flow`
(methodology) · `sources` (table) · `recs` (recommendation cards) · `limits` (caveats) ·
`event` (invite + agenda). Full schema → **`template/AUTHORING.md`**.

### As an AI-agent skill
Hand the agent this repo + a content brief (or a filled `content.md`). It follows
`template/AUTHORING.md` to rebuild `content.js` — never touching layout, CSS, or charts.
`CLAUDE.md` already instructs any agent in this project to edit content only.

### Themes
`mosaic` (default, bold, brand mosaic motif) · `academic` (calm, serif, lots of air) ·
`civic` (structured data dashboard). Switch live in Tweaks or set `theme:` in content.

---

## Files
```
Knowledge Center Report.html   ← open this (the report)
Report Editor.html             ← no-code editor (edit text → live preview)
README.md                      ← you are here
CLAUDE.md                      ← rules for any AI agent working here
assets/logo.jpg                ← brand logo (replace to rebrand)
template/
  content.md     ← edit this (Markdown, no code) — used by the editor & agent
  content.js     ← or edit this (structured config) — what the report runs on
  md.js          ← Markdown → config parser (powers the editor)
  preview.html   ← live-preview frame used by the editor
  AUTHORING.md   ← full schema + Markdown convention
  brand.css      ← design system (RTL, 3 themes, components)
  charts.js      ← SVG chart engine (RTL-aware)
  render.js      ← builds the report from content.js
  tweaks-*.jsx   ← theme switcher (Tweaks panel)
```

# מדריך עריכה · Report Template Authoring Guide
### Interactive StoryReport — reusable, brand-driven report template

There are **three** ways to author/edit a report. Pick the one that fits:

| Method | Who | How |
|---|---|---|
| **C — ✏️ edit mode** | anyone, fastest | open the report, click **✏️ עריכת טקסט**, edit text in place |
| **A — Markdown** | non-coders | edit `template/content.md`, ask an agent to *"apply content.md"* |
| **B — config** | full control | edit `window.REPORT` in `template/content.js` directly |

You never need to touch `brand.css`, `charts.js`, `render.js`, or `edit-mode.js`.

---

## ✦ Method C — in-browser edit mode (WYSIWYG, no code, no Markdown)

The report ships with a floating **✏️ עריכת טקסט** button (bottom-left).

1. Click it → every text element (headings, ledes, paragraphs, KPI labels,
   recommendations, captions) becomes editable in place.
2. Type your changes. They **autosave to the browser** (`localStorage`) and survive reloads.
3. **⬇ ייצוא עריכות** downloads `report_overrides.json` — a small file of your edits.
4. **↺ איפוס** clears all edits and restores the original.

**What is protected:** numbers, charts, tables and any element with structural children
are *not* editable — you cannot break the data or the visuals by accident.

**Making edits permanent / shareable:** hand `report_overrides.json` to your agent (or
build script). It re-applies the edits onto `content.js`, so rebuilding from fresh data
never loses your wording. See *Applying exported edits* below.

עברית: פותחים את הדוח, לוחצים **✏️ עריכת טקסט**, עורכים טקסט במקום. נשמר אוטומטית בדפדפן.
**⬇ ייצוא עריכות** מוריד קובץ; מוסרים אותו לסוכן כדי להטמיע לצמיתות.

---

## ✦ Method A — write your text in Markdown

1. Open **`template/content.md`** — the whole report as fill-in-the-blanks Markdown.
2. Edit the text after each `:` and the numbers in the tables. Don't rename the field
   keys (`kicker`, `title`, …) or the `[kind]` tags.
3. Hand the file to your agent and say *"apply content.md"* — it regenerates
   `template/content.js`.

## ✦ Method B — edit the config directly

Edit **`template/content.js`** (`window.REPORT`). Same content, structured. Schema below.

**להחלפת לוגו:** החליפו את `assets/logo.jpg`. **לעיצוב:** לוח ה-Tweaks (ערכת נושא, צבע).

---

## For an AI agent — how to author / update a report

- Produce a report by **rewriting `window.REPORT` in `template/content.js`** to match the
  user's content. Keep the **schema** below. Do not edit `brand.css`, `charts.js`,
  `render.js`, or `edit-mode.js`.
- Hebrew RTL is the default. Write copy in the user's language. Preserve `**bold**` as
  `<strong>…</strong>`.
- Use **real figures** the user supplies. If a number is missing, leave a clearly-marked
  placeholder and tell the user.
- Pick the right `kind` per section. Order sections to tell a story:
  intro → KPIs → findings (charts) → recommendations → methodology → sources.
- **If a `report_overrides.json` exists, apply it last** (see below) so user edits win.

### `REPORT` top-level keys
| key | purpose |
|---|---|
| `brand` | `{ logo, name, nameEn }` — logo + names in the top bar |
| `theme` | `"mosaic"` \| `"academic"` \| `"civic"` |
| `nav`   | `[{ id, label }]` — top-bar links; each `id` must match a section `id` |
| `hero`  | `{ meta:[…], title, titleAccent, sub, foot:[…] }` |
| `sections` | ordered array of section objects (below) |
| `footer` | `{ sig, meta:[…] }` |

### Section `kind` catalogue
| kind | what it renders | key fields |
|---|---|---|
| `rich` | heading + paragraphs | `kicker, title, lede, body:[html…]` |
| `kpis` | 4 animated stat cards | `items:[{ value, unit, label, note }]` |
| `barColumns` | vertical bar (distribution) | `data:[{label,value}], unit, source, split?` |
| `barRanked` | horizontal ranked bars | `data:[{label,value}], unit, source, split?` |
| `grouped` | 2-series comparison | `series:[{name,color}], data:[{label,values:[a,b]}]` |
| `donut` | ring / share | `data:[{label,value,color?}], unit` |
| `line` | trend over time | `x:[…], values:[…], unit, color` |
| `pull` | giant number + sentence | `big, txt` (use `band:"dark"`) |
| `flow` | methodology steps | `steps:[{n,title,body,tools:[]}]` |
| `sources` | data-source table | `cols:[…], rows:[{nm,scope,period,quality,notes}]` |
| `recs` | recommendation cards | `items:[{tag,title,body}]` |
| `limits` | caveats grid | `items:[{mk,html}]` |
| `event` | event invite + agenda | `date:{d,m,dow}, agenda:[{t,txt}], contact` |

**Shared optional fields on any section:**
- `id` (string, required) — anchor + nav target.
- `band` — `"alt"` (subtle background) or `"dark"` (dark brand band). Omit for default.
- `kicker`, `title`, `sub`, `source` — labels around the content.
- `split` (on chart kinds) — narrative beside the chart: `{ title, body, pull?:{ big, txt } }`.

### Chart colors
Pin a color with `color:"var(--c-magenta)"`. Brand vars: `--c-cyan --c-sky --c-blue
--c-bluedeep --c-navy --c-magenta --c-lime --c-gold`. Quality bars: `high` גבוהה,
`med` בינונית, `low` מוגבלת.

---

## Applying exported edits (`report_overrides.json`)

Edit mode (Method C) exports a flat JSON of `key → HTML`. Keys mirror `REPORT`:

```
{sectionId}::title | lede | sub
{sectionId}::body::{i}                  (rich body paragraph i)
{sectionId}::items::{j}::{field}        (kpis: label/note · recs: tag/title/body · limits: html)
{sectionId}::steps::{j}::{field}        (flow: title/body)
```

To apply: for each key, locate the section by `id` and set the field. Pseudocode:

```js
for (const [key, val] of Object.entries(overrides)) {
  const [sid, field, i, sub] = key.split('::');
  const sec = REPORT.sections.find(s => s.id === sid); if (!sec) continue;
  if (['title','lede','sub','kicker'].includes(field)) sec[field] = val;
  else if (field === 'body')  sec.body[+i] = val;
  else if (field === 'items') sec.items[+i][sub] = val;
  else if (field === 'steps') sec.steps[+i][sub] = val;
}
```

Apply overrides **after** building the report object from data, then write `content.js`.
This makes user wording survive data refreshes. (A real example lives in the
business-return project's `build_business_storyreport.py`.)

---

## Advanced — data-driven & interactive (hybrid) reports

The static template covers most reports. For a **data pipeline** report (numbers/charts
computed from a dataset) the pattern is:

1. A build script reads the data and **emits `content.js`** (`window.REPORT`) — same schema.
2. For **interactive charts** (sliders, dropdowns, Plotly), add a `rich` section whose
   `body` contains placeholder `<div id="my-chart"></div>` elements, then append a
   `<script>` to the report HTML that loads a chart lib and draws into those divs on the
   `report:ready` event. Keep computed numbers out of edit mode (they live in the data).
3. Apply `report_overrides.json` last (above).

The business-return report (`build_business_storyreport.py`) is a full worked example:
month slider, weekly trend dropdowns, raw/adjusted toggle, plus edit mode.

---

## Files
```
Report.html        ← open this
assets/logo.jpg    ← brand logo (replace with yours)
Report Editor.html ← optional: side-by-side Markdown editor with live preview
template/
  content.md   ← Method A (Markdown source)
  content.js   ← Method B (window.REPORT) — what the report actually renders
  brand.css    ← design system: RTL, 3 themes, components   (do not edit)
  charts.js    ← SVG chart engine (RTL-aware)                (do not edit)
  render.js    ← builds the report from content.js           (do not edit)
  edit-mode.js ← ✏️ in-browser WYSIWYG text editing          (do not edit)
  preview.html ← live-preview frame used by Report Editor
  tweaks-*.jsx ← theme switcher (Tweaks)
```

---

## Markdown convention (`content.md` → `content.js`)

- `# REPORT` → `brand` (`name`,`nameEn`,`logo`) + `theme`.
- `# HERO` → `hero` (`meta` split on ` | `; `title`; `accent`→`titleAccent`; `sub`;
  `foot` split on ` | `).
- `# NAV` lines `label -> id` → `nav:[{id,label}]`.
- `## <id> [<kind>] {<band>}` → one section (`{band}` optional: `alt`/`dark`).
- `key: value` lines → fields; dotted keys (`split.title`, `split.pull.big`) → nested.
- A Markdown **table** → the section's data array, keyed by the header row
  (`kpis`→`items`; `barRanked`/`barColumns`→`data`; `grouped`→`data` + `series:` line;
  `recs`→`items`; `flow`→`steps` (tools comma-split); `sources`→`rows`; `limits`→`items`).
- `# FOOTER` → `footer` (`sig`, `meta` list). Preserve `**bold**` → `<strong>`.

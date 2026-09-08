# Project: Interactive StoryReport Template — מרכז הידע האזורי גליל מזרחי

This project is a **reusable, brand-driven interactive report template** (Hebrew RTL).

## To create or edit a report
**Easiest (no code):** edit `template/content.md` (plain Markdown — headings, fields, and
tables for chart numbers), then apply it by regenerating `template/content.js` to match.
Alternatively edit `template/content.js` directly — it holds every heading, paragraph,
KPI and chart as the `window.REPORT` object.

The renderer (`template/render.js`), styles (`template/brand.css`) and chart engine
(`template/charts.js`) are generic — do not edit them unless changing the design system.

When asked to "apply content.md": parse `template/content.md` per the convention in
`template/AUTHORING.md` and rewrite `template/content.js` to match. Don't touch layout/CSS/charts.

Full schema + section-kind catalogue + Markdown convention: **`template/AUTHORING.md`**.

## Brand
- Logo: `assets/logo.jpg`. Palette sampled from it (cyans, blues, navy, magenta, lime, gold).
- Signature motif: pixel-mosaic squares (from the logo's speech-bubble mark).
- Three switchable themes via the Tweaks panel: `mosaic` (default), `academic`, `civic`.
- Default language: Hebrew, RTL.

## Open
`Knowledge Center Report.html`

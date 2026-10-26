# Guide for AI agents

This repository holds a database of Israeli local authorities built from the CBS
"הרשויות המקומיות בישראל" files, 2003–2024 (all authorities, ~1,000 indicators), plus
the pipeline that builds it. Use the **release**, not the raw Excel files or the
intermediate `data/bronze|silver|gold` layers.

## Where things are

| What | Where |
|---|---|
| The database | `data/release/parquet/*.parquet` (12 tables) |
| Open it with documented columns | `from etl.db import connect; con = connect()` (DuckDB views + column comments) |
| Every table and column, machine-readable | `data/release/schema.json` |
| Human documentation, known issues, audit results | `data/release/README.md` |
| Build facts (date, years, audit summary) | table `about` |
| Rebuild everything | `python -m etl.build` (stops if the audit fails) · tests: `python -m pytest tests` |

## Discover before you answer

1. **Find indicators** in `indicators` by `name` or `topic`. A name starts with the CBS section heading
   and joins levels with ` › ` (`דמוגרפיה › סה"כ אוכלוסייה בסוף השנה`), so search with
   `name LIKE '%stem%'`, never a prefix. Spelling is normalized: full spelling (אוכלוסייה, עירייה) and `סה"כ`.
   Population, SES and periphery per authority and year are ready in `authority_year`.
   Several indicators can match a concept: compare `first_year`/`last_year`, `n_authorities_last_year`,
   `applies_to` and `quality_flags`, and read `same_values_as`, `continues`, `continued_by`.
2. **Check availability** in `coverage` (per indicator and year) before saying data is missing
   or comparing years: a year can exist with only a few authorities.
3. **Find authorities** through `authority_aliases.alias_normalized` (spellings vary:
   קרית/קריית, עג'ר/ע'ג'ר, מבואות חרמון/מבואות החרמון). Eshkol membership: `authorities.eshkol`.
4. **Fetch values** from `observations` (key: `muni_code`, `indicator_id`, `year`).

## Rules that prevent wrong or incomplete answers

* `year` is the **data year**, not the file year. `indicators.period_kind` says what it means
  (school year → end year; multi-year average → end year; index edition → reference year).
* Read `observations.flag`. `nil` = CBS "-" (no cases; 0 for counts, empty for rates),
  `not_available` = "..", `estimate` = high sampling error. Do not treat these rows as missing data
  without saying so.
* Report quality flags you rely on: `mapping_confidence` (medium/low), `consistency_issue`,
  `mixed_scale`, `revised`, and `indicators.quality_flags`.
* `measure_type = count` values grow with authority size; compare authorities with the derived
  `<indicator_id>_k` (per 1,000 residents) or a rate.
* Two SES clusters exist in `authority_year`: `ses_cluster` (edition current at that year) and
  `ses_cluster_latest` (one edition for all years). State which one you use.
* `cbs_totals` holds official CBS totals (the national total includes population outside any
  authority); `benchmarks` holds statistics over authorities. They differ by design.
* Series that CBS restructured are **not merged** (`continues` / `continued_by`). Join them only
  after checking the values, and say that you did.
* Cite `indicator_id` and `source_file_year` so a value can be traced to its source column
  (`data/silver/column_map_DRAFT.csv`) and cell (`data/bronze/cells.parquet`).

## Changing the data

Human decisions live in `etl/config/` (unit conversions, column overrides, label synonyms,
consistency rules, topics). Change a decision there and rebuild; do not edit release files.
Matching rules for authority names and codes: `eshkol-matching/SKILL.md`.

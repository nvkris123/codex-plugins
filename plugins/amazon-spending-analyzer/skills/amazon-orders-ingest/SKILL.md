---
name: amazon-orders-ingest
description: Ingest an Amazon "Your Orders" export folder into categorized annual CSVs using the bundled deterministic Python pipeline. Use when the user asks to import, ingest, process, categorize, or update Amazon order history, including requests limited to specific years.
---

# Amazon Orders Ingest

Use the bundled deterministic script. Do not load raw order CSVs into context unless the user explicitly asks for row-level inspection.

## Inputs

- The input should be the top-level Amazon export folder named `Your Orders`.
- If the user does not provide a path, try common local paths in this order:
  - `$HOME/Downloads/Your Orders`
  - `./Your Orders`
- Default output workdir is `amazon-history-categorized`.

## Command Mapping

Resolve `<plugin-root>` as the root of this installed plugin, two directories above this `SKILL.md`.

```bash
python3 "<plugin-root>/scripts/amazon_order_category_pipeline.py" "<Your Orders folder>"
```

Map year language to script flags:

- "only 2025" -> `--start-year 2025 --end-year 2025`
- "2023 to 2025" -> `--start-year 2023 --end-year 2025`
- "since 2024" -> `--start-year 2024`
- "through 2025" -> `--end-year 2025`
- no year range -> omit both flags

If the user says "no fetch", "offline", or "use existing cache only", add `--no-fetch`.

If the user says "use this workdir" or similar, pass `--workdir <path>`.

## Category Review

The ingestion script never invokes AI. It writes unresolved rows to:

```text
<workdir>/review/orders-YYYY-category-review.csv
```

Default behavior after ingest:

1. Check whether any review CSVs exist and have rows.
2. Unless the user said "no AI", "deterministic only", or "leave unresolved", continue with the `amazon-orders-resolve-categories` workflow.
3. After resolutions are applied, report the updated unresolved count.

## Output

Report:

- Workdir path
- Years processed
- Rows added
- Ambiguous rows remaining
- Whether category review was also run

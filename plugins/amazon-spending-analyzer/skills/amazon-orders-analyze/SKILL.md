---
name: amazon-orders-analyze
description: Answer questions about categorized Amazon order history by running the bundled analysis script over amazon-history-categorized/orders/orders-YYYY.csv and reading the generated aggregate summaries. Use for questions about biggest categories, spend by year, trends, top categories, source mix, or category comparisons.
---

# Amazon Orders Analyze

Use aggregate outputs from the bundled script. Do not load full annual order CSVs into context unless the user explicitly asks for item-level details.

## Command

Resolve `<plugin-root>` as the root of this installed plugin, two directories above this `SKILL.md`.

```bash
python3 "<plugin-root>/scripts/amazon_order_analysis.py" \
  --workdir "amazon-history-categorized"
```

Map year language to flags:

- "only 2025" -> `--start-year 2025 --end-year 2025`
- "2023 to 2025" -> `--start-year 2023 --end-year 2025`
- "since 2024" -> `--start-year 2024`
- "through 2025" -> `--end-year 2025`

Optional flags:

- `--top N` for top N categories
- `--category-depth N` to group by N breadcrumb levels
- `--include-returned` only if the user explicitly wants returned items included
- `--workdir <path>` if the user names a custom workdir

## Outputs To Read

Read the generated JSON first:

```text
<workdir>/analysis/category-summary-<period>.json
```

Use the CSV/Markdown only when useful for presentation:

```text
<workdir>/analysis/category-summary-<period>.csv
<workdir>/analysis/category-summary-<period>.md
```

## Answering

Answer from the aggregate summary:

- State period, returned-item handling, total spend, and row count when relevant.
- For "biggest categories", rank by `spend`.
- For trend questions, compare the `years` objects inside each category.
- Mention that returned rows are excluded by default.

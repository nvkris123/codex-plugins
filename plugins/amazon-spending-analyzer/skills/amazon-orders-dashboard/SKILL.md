---
name: amazon-orders-dashboard
description: Build a static HTML dashboard from categorized Amazon order history generated under amazon-history-categorized. Use when the user asks for an Amazon spending dashboard, charts, visual report, or browsable summary of categorized order history.
---

# Amazon Orders Dashboard

Run the bundled dashboard builder over annual categorized order CSVs.

## Command

Resolve `<plugin-root>` as the root of this installed plugin, two directories above this `SKILL.md`.

```bash
python3 "<plugin-root>/scripts/build_amazon_order_dashboard.py" \
  --workdir "amazon-history-categorized" \
  --output "./amazon-order-dashboard.html"
```

Map year language to flags:

- "only 2025" -> `--start-year 2025 --end-year 2025`
- "2023 to 2025" -> `--start-year 2023 --end-year 2025`
- "since 2024" -> `--start-year 2024`
- "through 2025" -> `--end-year 2025`

Optional flags:

- `--include-returned` only if the user explicitly wants returned items included
- `--output <path>` if the user requests a specific dashboard file
- `--workdir <path>` if the user names a custom workdir

Default output:

```text
./amazon-order-dashboard.html
```

## Response

After building, report the dashboard path and record count. Do not paste raw order rows into the answer.

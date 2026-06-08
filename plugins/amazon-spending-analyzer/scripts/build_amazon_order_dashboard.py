#!/usr/bin/env python3
"""Build a static Amazon spending dashboard from pipeline annual order CSVs."""

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_WORKDIR = Path("amazon-history-categorized")
DEFAULT_OUTPUT_NAME = "amazon-order-dashboard.html"
ORDER_PATTERN = "orders-*.csv"


TOP_CATEGORY_NORMALIZATION = {
    "Health, Household & Baby Care": "Health & Household",
    "Cell Phones & Accessories": "Electronics",
    "Computers": "Electronics",
    "Sports, Fitness & Outdoors": "Sports & Outdoors",
    "Everything Else": "Other / Uncategorized",
    "Amazon Devices & Accessories": "Electronics",
    "Grocery & Gourmet Foods": "Grocery & Gourmet Food",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a static Amazon spending dashboard from categorized annual order CSV files."
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=DEFAULT_WORKDIR,
        help=f"Pipeline work directory containing orders/{ORDER_PATTERN!r}. Default: {DEFAULT_WORKDIR}",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        help="First order year to include, inclusive.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        help="Last order year to include, inclusive.",
    )
    parser.add_argument(
        "--include-returned",
        action="store_true",
        help="Include rows marked is_returned=true. Returned rows are excluded by default.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=f"HTML dashboard output path. Default: <workdir>/dashboard/{DEFAULT_OUTPUT_NAME}",
    )
    return parser.parse_args()


def parse_date(value):
    text = (value or "").strip()
    if not text:
        return None
    if "T" in text:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text).astimezone(timezone.utc)
        except ValueError:
            text = text.split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_amount(value):
    text = (value or "").strip()
    if not text or text in {"Not Available", "Not Applicable", "No Refund"}:
        return None
    text = text.replace("$", "").replace(",", "").replace("'", "")
    try:
        return float(text)
    except ValueError:
        return None


def year_from_filename(path):
    match = re.search(r"orders-(\d{4})\.csv$", path.name)
    return int(match.group(1)) if match else None


def truthy(value):
    return (value or "").strip().lower() in {"1", "true", "yes", "y"}


def row_amount(row):
    for column in ("Total Amount", "Transaction Amount", "Price", "Shipment Item Subtotal", "Unit Price"):
        amount = parse_amount(row.get(column))
        if amount is not None:
            return amount
    return None


def row_status(row):
    return (row.get("Order Status") or row.get("Fullfilment Status") or row.get("Shipment Status") or "UNKNOWN").strip() or "UNKNOWN"


def row_website(row):
    return (
        row.get("Website")
        or row.get("Marketplace")
        or row.get("source_marketplace")
        or row.get("source_type")
        or "UNKNOWN"
    ).strip() or "UNKNOWN"


def row_currency(row):
    return (
        row.get("Currency")
        or row.get("Price Currency Code")
        or row.get("Transaction Amount Currency Code")
        or row.get("Base Currency Code")
        or "USD"
    ).strip() or "USD"


def row_asin(row):
    url = (row.get("normalized_asin_url") or "").strip()
    asin = (row.get("ASIN") or "").strip()
    return url or asin


def category_parts(category):
    full = (category or "").strip() or "Other / Uncategorized"
    parts = [part.strip() for part in full.split(" > ") if part.strip()]
    if not parts:
        parts = ["Other / Uncategorized"]
    level_1_raw = parts[0]
    level_1 = TOP_CATEGORY_NORMALIZATION.get(level_1_raw, level_1_raw)
    if level_1_raw == "Grocery & Gourmet Foods":
        parts[0] = level_1
        full = " > ".join(parts)
    level_2 = parts[1] if len(parts) > 1 else ""
    return full, level_1, level_1_raw, level_2


def read_orders(workdir, start_year=None, end_year=None, include_returned=False):
    orders_dir = workdir / "orders"
    files = []
    records = []
    skipped = {
        "missing_date": 0,
        "missing_amount": 0,
        "missing_category": 0,
        "returned": 0,
        "outside_year_window": 0,
    }

    for path in sorted(orders_dir.glob(ORDER_PATTERN)):
        source_year = year_from_filename(path)
        if source_year is None:
            continue
        if start_year and source_year < start_year:
            continue
        if end_year and source_year > end_year:
            continue
        files.append(path)
        with path.open(newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                if not include_returned and truthy(row.get("is_returned")):
                    skipped["returned"] += 1
                    continue
                order_date = parse_date(row.get("source_order_date") or row.get("Order Date"))
                amount = row_amount(row)
                if not order_date:
                    skipped["missing_date"] += 1
                    continue
                if amount is None:
                    skipped["missing_amount"] += 1
                    continue
                year = order_date.year
                if start_year and year < start_year:
                    skipped["outside_year_window"] += 1
                    continue
                if end_year and year > end_year:
                    skipped["outside_year_window"] += 1
                    continue

                category_full, category_level_1, category_level_1_raw, category_level_2 = category_parts(
                    row.get("category")
                )
                if not (row.get("category") or "").strip():
                    skipped["missing_category"] += 1

                month = order_date.month
                records.append(
                    {
                        "date": order_date.date().isoformat(),
                        "year": year,
                        "month": month,
                        "yearMonth": f"{year:04d}-{month:02d}",
                        "amount": round(amount, 2),
                        "currency": row_currency(row),
                        "status": row_status(row),
                        "website": row_website(row),
                        "productName": (row.get("Product Name") or "").strip(),
                        "asin": row_asin(row),
                        "categoryFull": category_full,
                        "categoryLevel1": category_level_1,
                        "categoryLevel1Raw": category_level_1_raw,
                        "categoryLevel2": category_level_2,
                        "sourceFile": path.name,
                        "sourceYear": source_year,
                    }
                )

    return files, records, skipped


def build_html(records, files, skipped, workdir, include_returned):
    payload = {
        "records": records,
        "meta": {
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sourceFiles": [path.name for path in files],
            "recordCount": len(records),
            "skipped": skipped,
            "amountField": "first available amount field",
            "defaultYearStart": 2016,
            "workdir": str(workdir),
            "returnedRowsIncluded": include_returned,
        },
    }
    data_json = json.dumps(payload, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Amazon Spending Dashboard</title>
  <style>
    :root {{
      --bg: #f7f2ed;
      --panel: #fffdf9;
      --ink: #25323a;
      --muted: #6f7d78;
      --line: #e7dcd1;
      --blue: #7fc8ba;
      --green: #6ab7aa;
      --orange: #efad83;
      --red: #d98d78;
      --purple: #9eb7a9;
      --shadow: 0 10px 24px rgba(91, 72, 58, 0.10);
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      min-width: 320px;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}

    header {{
      padding: 28px 32px 18px;
      background: #fffaf4;
      border-bottom: 1px solid var(--line);
    }}

    header h1 {{
      margin: 0 0 6px;
      font-size: 28px;
      font-weight: 750;
    }}

    header p {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }}

    main {{
      padding: 20px 32px 36px;
      max-width: 1480px;
      margin: 0 auto;
    }}

    .toolbar {{
      display: grid;
      grid-template-columns: repeat(9, minmax(112px, 1fr));
      gap: 12px;
      align-items: end;
      padding: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}

    label {{
      display: grid;
      gap: 6px;
      min-width: 0;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }}

    select {{
      width: 100%;
      min-width: 0;
      min-height: 38px;
      border: 1px solid #d9cfc4;
      border-radius: 6px;
      padding: 7px 10px;
      background: #fffdf9;
      color: var(--ink);
      font-size: 14px;
    }}

    .checkbox-label {{
      display: inline-flex;
      grid-template-columns: none;
      align-items: center;
      gap: 8px;
      width: fit-content;
      min-height: 32px;
      cursor: pointer;
    }}

    .checkbox-label input {{
      width: 16px;
      height: 16px;
      margin: 0;
      accent-color: #69b7ad;
    }}

    .category-filter {{
      grid-column: 1 / -1;
    }}

    .filter-heading {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }}

    .category-options {{
      display: grid;
      max-height: 178px;
      overflow: auto;
      border: 1px solid #d9cfc4;
      border-radius: 6px;
      background: #fffdf9;
    }}

    .category-option {{
      display: flex;
      grid-template-columns: none;
      align-items: center;
      gap: 8px;
      min-height: 30px;
      padding: 5px 8px;
      color: var(--ink);
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      user-select: none;
    }}

    .category-option:hover {{
      background: #f3ebe2;
    }}

    .category-option:has(input:checked) {{
      background: #dcefeb;
    }}

    .category-option input {{
      width: 16px;
      height: 16px;
      margin: 0;
      accent-color: #69b7ad;
      flex: 0 0 auto;
    }}

    .hint {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 500;
    }}

    .secondary-button {{
      width: fit-content;
      min-height: 32px;
      border: 1px solid #d9cfc4;
      border-radius: 6px;
      padding: 6px 10px;
      background: #fff8f1;
      color: var(--ink);
      font-size: 12px;
      font-weight: 650;
      cursor: pointer;
    }}

    .secondary-button:hover {{
      background: #f4e5d8;
    }}

    .detail-toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }}

    .detail-actions {{
      display: flex;
      align-items: end;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}

    .compact-label {{
      width: 190px;
    }}

    .detail-summary {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}

    .clickable-row {{
      cursor: pointer;
    }}

    .clickable-row:hover {{
      background: #fff8f1;
    }}

    .product-cell {{
      max-width: 620px;
      line-height: 1.35;
    }}

    .product-cell a {{
      font-weight: inherit;
    }}

    .item-meta {{
      display: block;
      margin-top: 3px;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.35;
    }}

    .sort-button {{
      appearance: none;
      border: 0;
      padding: 0;
      background: transparent;
      color: inherit;
      font: inherit;
      font-weight: inherit;
      text-transform: inherit;
      cursor: pointer;
    }}

    .sort-button:hover {{
      color: var(--ink);
      text-decoration: underline;
    }}

    a {{
      color: #427f77;
      font-weight: 650;
      text-decoration: none;
    }}

    a:hover {{
      text-decoration: underline;
    }}

    .kpis {{
      display: grid;
      grid-template-columns: repeat(5, minmax(150px, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}

    .kpi, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}

    .kpi {{
      padding: 16px;
      min-height: 96px;
    }}

    .kpi .label {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      margin-bottom: 8px;
    }}

    .kpi .value {{
      font-size: 24px;
      font-weight: 780;
      line-height: 1.15;
      overflow-wrap: anywhere;
    }}

    .kpi .sub {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 7px;
      line-height: 1.4;
    }}

    .grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.4fr) minmax(340px, 0.8fr);
      gap: 14px;
      margin-top: 14px;
    }}

    .panel {{
      min-width: 0;
      padding: 16px;
    }}

    .panel h2 {{
      margin: 0 0 4px;
      font-size: 16px;
      font-weight: 760;
    }}

    .panel .note {{
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}

    .wide {{
      grid-column: 1 / -1;
    }}

    svg {{
      display: block;
      width: 100%;
      height: auto;
      overflow: visible;
    }}

    .axis, .caption {{
      fill: var(--muted);
      font-size: 11px;
    }}

    .chart-empty {{
      min-height: 220px;
      display: grid;
      place-items: center;
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 8px;
    }}

    #trendChart, #stackedChart, .chart-scroll {{
      overflow-x: auto;
      max-width: 100%;
    }}

    .chart-tooltip {{
      position: fixed;
      z-index: 1000;
      max-width: 320px;
      padding: 8px 10px;
      border: 1px solid #d9cfc4;
      border-radius: 6px;
      background: #25323a;
      color: #fffdf9;
      font-size: 12px;
      line-height: 1.35;
      box-shadow: 0 8px 20px rgba(37, 50, 58, 0.18);
      pointer-events: none;
      opacity: 0;
      transform: translate(10px, 10px);
      transition: opacity 70ms ease;
    }}

    .chart-tooltip.visible {{
      opacity: 1;
    }}

    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 14px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
    }}

    .legend span {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}

    .comparison-controls {{
      display: grid;
      grid-template-columns: repeat(5, minmax(130px, 1fr));
      gap: 12px;
      align-items: end;
      margin: 12px 0 10px;
    }}

    .comparison-summary {{
      min-height: 18px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}

    .is-hidden {{
      display: none !important;
    }}

    .monthly-rank-grid {{
      display: flex;
      gap: 12px;
      overflow-x: auto;
      padding: 4px 0 12px;
      scroll-snap-type: x proximity;
    }}

    .monthly-rank-calendar-group {{
      flex: 0 0 auto;
      padding: 10px;
      border: 1px solid #eadfd4;
      border-radius: 8px;
      background: #fffaf4;
      scroll-snap-align: start;
    }}

    .monthly-rank-calendar-group:nth-child(even) {{
      background: #f7f2ed;
    }}

    .monthly-rank-calendar-title {{
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
      text-transform: uppercase;
    }}

    .monthly-rank-calendar-cards {{
      display: flex;
      gap: 12px;
    }}

    .monthly-rank-month {{
      flex: 0 0 270px;
      scroll-snap-align: start;
      padding: 12px;
      border: 1px solid #eadfd4;
      border-radius: 8px;
      background: #fff8f1;
    }}

    .monthly-rank-title {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
      color: var(--ink);
      font-size: 13px;
      font-weight: 760;
    }}

    .monthly-rank-row {{
      display: grid;
      grid-template-columns: 20px minmax(0, 1fr);
      gap: 8px;
      align-items: start;
      margin-top: 9px;
    }}

    .rank-number {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 760;
      line-height: 1.5;
      text-align: right;
    }}

    .rank-main {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      min-width: 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}

    .rank-name {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .rank-amount {{
      flex: 0 0 auto;
      font-variant-numeric: tabular-nums;
    }}

    .rank-track {{
      height: 7px;
      margin-top: 5px;
      overflow: hidden;
      border-radius: 999px;
      background: #efe5db;
    }}

    .rank-fill {{
      display: block;
      height: 100%;
      min-width: 3px;
      border-radius: inherit;
    }}

    .swatch {{
      width: 10px;
      height: 10px;
      border-radius: 2px;
      display: inline-block;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}

    th, td {{
      padding: 10px 8px;
      border-bottom: 1px solid #efe5db;
      text-align: left;
      vertical-align: top;
    }}

    th {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 760;
      background: #fff8f1;
      position: sticky;
      top: 0;
    }}

    td.num, th.num {{
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}

    .table-wrap {{
      max-height: 520px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}

    .insights {{
      display: grid;
      grid-template-columns: repeat(4, minmax(160px, 1fr));
      gap: 12px;
    }}

    .insight {{
      padding: 13px;
      background: #fff8f1;
      border: 1px solid #eadfd4;
      border-radius: 8px;
      min-height: 92px;
    }}

    .insight b {{
      display: block;
      margin-bottom: 7px;
      font-size: 13px;
    }}

    .insight span {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}

    footer {{
      margin-top: 16px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.55;
    }}

    @media (max-width: 1100px) {{
      main {{ padding: 16px; }}
      header {{ padding: 22px 16px 16px; }}
      .toolbar {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .comparison-controls {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .grid {{ grid-template-columns: 1fr; }}
      .insights {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}

    @media (max-width: 640px) {{
      .toolbar, .kpis, .insights {{ grid-template-columns: 1fr; }}
      .comparison-controls {{ grid-template-columns: 1fr; }}
      .category-filter {{ grid-column: auto; }}
      .kpi .value {{ font-size: 22px; }}
      header h1 {{ font-size: 24px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Amazon Spending Dashboard</h1>
    <p>Amazon expenses by category and time window. Data uses categorized annual pipeline CSV files and excludes returned rows by default.</p>
  </header>

  <main>
    <section class="toolbar" aria-label="Dashboard filters">
      <label>Start Year
        <select id="startYear"></select>
      </label>
      <label>Start Month
        <select id="startMonth"></select>
      </label>
      <label>End Year
        <select id="endYear"></select>
      </label>
      <label>End Month
        <select id="endMonth"></select>
      </label>
      <label>Aggregate
        <select id="aggregation">
          <option value="month">Monthly</option>
          <option value="year">Yearly</option>
        </select>
      </label>
      <label class="checkbox-label" title="When monthly aggregation is selected, show January across all selected years, then February across all selected years, and so on.">
        <input id="groupByMonth" type="checkbox">
        Group by month
      </label>
      <label>Currency
        <select id="currency"></select>
      </label>
      <label>Category View
        <select id="categoryMode">
          <option value="level1">Level 1 (top category)</option>
          <option value="full">Full path (category > subcategory)</option>
        </select>
      </label>
      <div class="category-filter">
        <div class="filter-heading">Categories <span class="hint">No selection = all categories; sorted alphabetically</span></div>
        <div class="category-options" id="categoryFilter" role="group" aria-label="Categories"></div>
        <button class="secondary-button" id="clearCategoryFilter" type="button">Clear Categories</button>
      </div>
    </section>

    <section class="kpis" aria-label="Summary">
      <div class="kpi"><div class="label">Total Spend</div><div class="value" id="kpiTotal">$0</div><div class="sub" id="kpiWindow">-</div></div>
      <div class="kpi"><div class="label">Average Period Spend</div><div class="value" id="kpiAverage">$0</div><div class="sub" id="kpiAverageSub">-</div></div>
      <div class="kpi"><div class="label">Items</div><div class="value" id="kpiItems">0</div><div class="sub" id="kpiStatuses">-</div></div>
      <div class="kpi"><div class="label">Top Category</div><div class="value" id="kpiTopCategory">-</div><div class="sub" id="kpiTopCategorySub">-</div></div>
      <div class="kpi"><div class="label">Peak Period</div><div class="value" id="kpiPeak">-</div><div class="sub" id="kpiPeakSub">-</div></div>
    </section>

    <section class="grid">
      <article class="panel">
        <h2>Spend Over Time</h2>
        <p class="note">Total spend by selected aggregation period.</p>
        <div id="trendChart"></div>
      </article>

      <article class="panel">
        <h2>Category Breakdown</h2>
        <p class="note">Ranked categories for the selected window.</p>
        <div id="categoryChart"></div>
      </article>

      <article class="panel wide">
        <h2>Month Comparison</h2>
        <p class="note">Cumulative daily spend for one month against another month. Uses closed orders plus the selected currency and category filters.</p>
        <div class="comparison-controls">
          <label>Base Year
            <select id="comparisonBaseYear"></select>
          </label>
          <label>Base Month
            <select id="comparisonBaseMonth"></select>
          </label>
          <label>Compare Against
            <select id="comparisonMode">
              <option value="previousMonth">Previous month</option>
              <option value="sameMonthPreviousYear">Same month previous year</option>
              <option value="customMonth">Custom month</option>
            </select>
          </label>
          <label id="comparisonCompareYearLabel">Compare Year
            <select id="comparisonCompareYear"></select>
          </label>
          <label id="comparisonCompareMonthLabel">Compare Month
            <select id="comparisonCompareMonth"></select>
          </label>
        </div>
        <div class="comparison-summary" id="comparisonSummary"></div>
        <div id="comparisonChart"></div>
      </article>

      <article class="panel wide">
        <h2>Top Categories Over Time</h2>
        <p class="note">Stacked trend of the largest level-1 categories. Smaller categories are grouped as Other.</p>
        <div id="stackedChart"></div>
        <div class="legend" id="stackedLegend"></div>
      </article>

      <article class="panel wide">
        <h2>Monthly Category Leaders</h2>
        <p class="note">Each month is ranked independently from highest-spend category to lowest. Uses closed orders plus the selected currency, category view, and category filters.</p>
        <div id="monthlyRankGrid"></div>
      </article>

      <article class="panel wide">
        <h2>Category Detail</h2>
        <p class="note">Totals, share of spend, item count, average item amount, and highest-spend period. Click a row to drill into the items behind that category.</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th class="num">Spend</th>
                <th class="num">Share</th>
                <th class="num">Items</th>
                <th class="num">Avg Item</th>
                <th>Peak Period</th>
              </tr>
            </thead>
            <tbody id="categoryTable"></tbody>
          </table>
        </div>
      </article>

      <article class="panel wide">
        <div class="detail-toolbar">
          <div>
            <h2>Item Drilldown</h2>
            <p class="note" id="itemDetailNote">Select categories above or click a category row to see individual items.</p>
          </div>
          <div class="detail-actions">
            <label class="checkbox-label">
              <input id="collateProducts" type="checkbox">
              Collate products
            </label>
            <button class="secondary-button" id="clearItemDetail" type="button" title="Clears a category row drilldown. Use Clear Categories to remove category filters.">Clear Item Detail</button>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th><button class="sort-button" data-item-sort="date" type="button">Date</button></th>
                <th><button class="sort-button" data-item-sort="productName" type="button">Product</button></th>
                <th class="num"><button class="sort-button" data-item-sort="amount" type="button">Amount</button></th>
                <th><button class="sort-button" data-item-sort="category" type="button">Category</button></th>
              </tr>
            </thead>
            <tbody id="itemTable"></tbody>
          </table>
        </div>
      </article>

      <article class="panel wide">
        <h2>Spend Signals</h2>
        <p class="note">Quick diagnostics for optimization discussions.</p>
        <div class="insights" id="insights"></div>
      </article>
    </section>

    <footer id="footer"></footer>
  </main>
  <div class="chart-tooltip" id="chartTooltip" role="tooltip"></div>

  <script id="dashboard-data" type="application/json">{data_json}</script>
  <script>
    const payload = JSON.parse(document.getElementById("dashboard-data").textContent);
    const records = payload.records;
    const meta = payload.meta;
    const colors = ["#86cbbb", "#efad83", "#69b7ad", "#f2cdb7", "#d88f78", "#a9d6c8", "#d7e7dc", "#bfa891", "#78aaa4", "#e6b8a2"];
    const monthBoundsByYear = new Map();

    const els = {{
      startYear: document.getElementById("startYear"),
      endYear: document.getElementById("endYear"),
      startMonth: document.getElementById("startMonth"),
      endMonth: document.getElementById("endMonth"),
      aggregation: document.getElementById("aggregation"),
      groupByMonth: document.getElementById("groupByMonth"),
      currency: document.getElementById("currency"),
      categoryMode: document.getElementById("categoryMode"),
      categoryFilter: document.getElementById("categoryFilter"),
      clearCategoryFilter: document.getElementById("clearCategoryFilter"),
      trendChart: document.getElementById("trendChart"),
      categoryChart: document.getElementById("categoryChart"),
      comparisonBaseYear: document.getElementById("comparisonBaseYear"),
      comparisonBaseMonth: document.getElementById("comparisonBaseMonth"),
      comparisonMode: document.getElementById("comparisonMode"),
      comparisonCompareYearLabel: document.getElementById("comparisonCompareYearLabel"),
      comparisonCompareYear: document.getElementById("comparisonCompareYear"),
      comparisonCompareMonthLabel: document.getElementById("comparisonCompareMonthLabel"),
      comparisonCompareMonth: document.getElementById("comparisonCompareMonth"),
      comparisonSummary: document.getElementById("comparisonSummary"),
      comparisonChart: document.getElementById("comparisonChart"),
      stackedChart: document.getElementById("stackedChart"),
      stackedLegend: document.getElementById("stackedLegend"),
      monthlyRankGrid: document.getElementById("monthlyRankGrid"),
      categoryTable: document.getElementById("categoryTable"),
      collateProducts: document.getElementById("collateProducts"),
      itemTable: document.getElementById("itemTable"),
      itemDetailNote: document.getElementById("itemDetailNote"),
      clearItemDetail: document.getElementById("clearItemDetail"),
      insights: document.getElementById("insights"),
      footer: document.getElementById("footer"),
      chartTooltip: document.getElementById("chartTooltip")
    }};
    let activeDetailCategory = "";
    let activeDetailMode = "level1";
    let detailSort = {{ key: "amount", direction: "desc" }};
    let lastCategoryCheckbox = null;

    function money(value, currency) {{
      try {{
        return new Intl.NumberFormat("en-US", {{ style: "currency", currency, maximumFractionDigits: 0 }}).format(value || 0);
      }} catch {{
        return `${{currency}} ${{Math.round(value || 0).toLocaleString("en-US")}}`;
      }}
    }}

    function moneyExact(value, currency) {{
      try {{
        return new Intl.NumberFormat("en-US", {{ style: "currency", currency, maximumFractionDigits: 2 }}).format(value || 0);
      }} catch {{
        return `${{currency}} ${{Number(value || 0).toLocaleString("en-US", {{ maximumFractionDigits: 2 }})}}`;
      }}
    }}

    function compact(value) {{
      return Number(value || 0).toLocaleString("en-US", {{ maximumFractionDigits: 0 }});
    }}

    function escapeHtml(value) {{
      return String(value || "").replace(/[&<>"']/g, char => ({{
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }}[char]));
    }}

    function labelPeriod(period, aggregation) {{
      if (aggregation === "year") return period;
      const [year, month] = period.split("-");
      return new Date(Number(year), Number(month) - 1, 1).toLocaleDateString("en-US", {{ month: "short", year: "2-digit" }});
    }}

    function periodLabelVisible(index, total, plotWidth, aggregation, groupByMonth = false) {{
      if (!total) return false;
      if (aggregation === "year") return true;
      if (groupByMonth) return true;
      const maxLabels = Math.max(2, Math.floor(plotWidth / 86));
      const interval = Math.max(1, Math.ceil(total / maxLabels));
      return index === 0 || index === total - 1 || index % interval === 0;
    }}

    function monthRange(start, end) {{
      const out = [];
      let [year, month] = start.split("-").map(Number);
      const [endYear, endMonth] = end.split("-").map(Number);
      while (year < endYear || (year === endYear && month <= endMonth)) {{
        out.push(`${{year}}-${{String(month).padStart(2, "0")}}`);
        month += 1;
        if (month === 13) {{ month = 1; year += 1; }}
      }}
      return out;
    }}

    function periodsFor(start, end, aggregation) {{
      if (aggregation === "month") return monthRange(start, end);
      return [...new Set(monthRange(start, end).map(month => month.slice(0, 4)))];
    }}

    function groupMonthsByCalendarMonth(months) {{
      return [...months].sort((a, b) => {{
        const [yearA, monthA] = a.split("-").map(Number);
        const [yearB, monthB] = b.split("-").map(Number);
        if (monthA !== monthB) return monthA - monthB;
        return yearA - yearB;
      }});
    }}

    function chartPeriodsFor(state) {{
      const periods = periodsFor(state.start, state.end, state.aggregation);
      if (state.aggregation === "month" && state.groupByMonth) {{
        return groupMonthsByCalendarMonth(periods);
      }}
      return periods;
    }}

    function monthGroupBlocks(periods, left, slot, top, plotH) {{
      const blocks = [];
      let start = 0;
      while (start < periods.length) {{
        const month = periods[start].slice(5, 7);
        let end = start;
        while (end + 1 < periods.length && periods[end + 1].slice(5, 7) === month) {{
          end += 1;
        }}
        blocks.push({{
          start,
          end,
          month,
          x: left + start * slot,
          width: (end - start + 1) * slot,
          label: monthName(month)
        }});
        start = end + 1;
      }}
      return blocks;
    }}

    function renderMonthGroupBackground(periods, left, slot, top, plotH, labelY) {{
      return monthGroupBlocks(periods, left, slot, top, plotH).map((block, index) => {{
        const fill = index % 2 === 0 ? "#fff8f1" : "#f7f2ed";
        const separator = index > 0 ? `<line x1="${{block.x}}" y1="${{top}}" x2="${{block.x}}" y2="${{top + plotH}}" stroke="#dbcfc3" stroke-dasharray="4 4"/>` : "";
        return `
          <rect x="${{block.x}}" y="${{top}}" width="${{block.width}}" height="${{plotH}}" fill="${{fill}}" opacity="0.62"></rect>
          ${{separator}}
          <text class="caption" x="${{block.x + block.width / 2}}" y="${{labelY}}" text-anchor="middle">${{block.label}}</text>
        `;
      }}).join("");
    }}

    function monthValue(year, month, edge) {{
      const bounds = monthBoundsByYear.get(String(year)) || {{ first: "01", last: "12" }};
      const resolvedMonth = month || (edge === "start" ? bounds.first : bounds.last);
      return `${{year}}-${{resolvedMonth}}`;
    }}

    function monthName(value) {{
      if (!value) return "All months";
      return new Date(2000, Number(value) - 1, 1).toLocaleDateString("en-US", {{ month: "long" }});
    }}

    function monthPeriodName(yearMonth) {{
      if (!yearMonth) return "-";
      const [year, month] = yearMonth.split("-").map(Number);
      return new Date(year, month - 1, 1).toLocaleDateString("en-US", {{ month: "long", year: "numeric" }});
    }}

    function windowLabel(state) {{
      const startMonth = state.startMonth ? monthName(state.startMonth) : monthName(state.start.slice(5, 7));
      const endMonth = state.endMonth ? monthName(state.endMonth) : monthName(state.end.slice(5, 7));
      return `${{startMonth}} ${{state.startYear}} through ${{endMonth}} ${{state.endYear}}`;
    }}

    function groupSum(items, keyFn) {{
      const map = new Map();
      for (const item of items) {{
        const key = keyFn(item);
        const current = map.get(key) || {{ key, amount: 0, count: 0 }};
        current.amount += item.amount;
        current.count += 1;
        map.set(key, current);
      }}
      return [...map.values()];
    }}

    function statusAllowed(status, mode) {{
      if (mode === "all") return true;
      if (mode === "noncancelled") return status !== "Cancelled";
      if (mode === "active") return status === "Closed" || status === "Authorized";
      return status === "Closed";
    }}

    function categoryCheckboxes() {{
      return Array.from(els.categoryFilter.querySelectorAll("input[type='checkbox']"));
    }}

    function selectedCategoryValues() {{
      return categoryCheckboxes().filter(input => input.checked).map(input => input.value);
    }}

    function monthShift(yearMonth, delta) {{
      const [year, month] = yearMonth.split("-").map(Number);
      const date = new Date(year, month - 1 + delta, 1);
      return `${{date.getFullYear()}}-${{String(date.getMonth() + 1).padStart(2, "0")}}`;
    }}

    function getState() {{
      const startYear = els.startYear.value;
      const endYear = els.endYear.value;
      const startMonth = els.startMonth.value;
      const endMonth = els.endMonth.value;
      const categoryMode = els.categoryMode.value;
      return {{
        startYear,
        endYear,
        startMonth,
        endMonth,
        start: monthValue(startYear, startMonth, "start"),
        end: monthValue(endYear, endMonth, "end"),
        aggregation: els.aggregation.value,
        groupByMonth: els.groupByMonth.checked && els.aggregation.value === "month",
        currency: els.currency.value,
        statusMode: "closed",
        categoryMode,
        selectedCategories: selectedCategoryValues()
      }};
    }}

    function getComparisonState() {{
      const base = `${{els.comparisonBaseYear.value}}-${{els.comparisonBaseMonth.value}}`;
      let compare = `${{els.comparisonCompareYear.value}}-${{els.comparisonCompareMonth.value}}`;
      if (els.comparisonMode.value === "previousMonth") compare = monthShift(base, -1);
      if (els.comparisonMode.value === "sameMonthPreviousYear") compare = monthShift(base, -12);
      return {{
        base,
        compare,
        mode: els.comparisonMode.value
      }};
    }}

    function filteredRecords(state) {{
      return records.filter(record =>
        record.yearMonth >= state.start &&
        record.yearMonth <= state.end &&
        record.currency === state.currency &&
        statusAllowed(record.status, state.statusMode) &&
        (!state.selectedCategories.length || state.selectedCategories.includes(categoryKey(record, state.categoryMode)))
      );
    }}

    function categoryKey(record, mode) {{
      return mode === "full" ? record.categoryFull : record.categoryLevel1;
    }}

    function populateCategoryFilter(preserveSelection = true) {{
      const mode = els.categoryMode.value;
      const existing = preserveSelection ? new Set(selectedCategoryValues()) : new Set();
      const categories = groupSum(records, record => categoryKey(record, mode))
        .sort((a, b) => a.key.localeCompare(b.key, undefined, {{ numeric: true, sensitivity: "base" }}))
        .map(row => row.key);
      els.categoryFilter.innerHTML = "";
      for (const category of categories) {{
        const label = document.createElement("label");
        label.className = "category-option";

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = category;
        checkbox.checked = existing.has(category);

        const text = document.createElement("span");
        text.textContent = category;

        label.appendChild(checkbox);
        label.appendChild(text);
        els.categoryFilter.appendChild(label);
      }}
    }}

    function emptyChart(container, message) {{
      container.innerHTML = `<div class="chart-empty">${{message}}</div>`;
    }}

    function renderTrend(items, state) {{
      const periods = chartPeriodsFor(state);
      const totals = new Map(periods.map(period => [period, 0]));
      for (const item of items) {{
        const period = state.aggregation === "year" ? String(item.year) : item.yearMonth;
        totals.set(period, (totals.get(period) || 0) + item.amount);
      }}
      const rows = periods.map(period => {{ return {{ period, amount: totals.get(period) || 0 }}; }});
      if (!rows.length || rows.every(row => row.amount === 0)) return emptyChart(els.trendChart, "No spend in this window");

      const width = Math.max(760, rows.length * (state.groupByMonth ? 48 : 18));
      const height = state.groupByMonth ? 304 : 280;
      const left = 58;
      const right = 18;
      const top = state.groupByMonth ? 42 : 18;
      const bottom = 54;
      const plotW = width - left - right;
      const plotH = height - top - bottom;
      const max = Math.max(...rows.map(row => row.amount), 1);
      const slot = plotW / rows.length;
      const barW = Math.max(3, Math.min(26, slot * 0.72));
      const ticks = [0, max / 2, max];
      const svgStyle = state.groupByMonth ? ` style="min-width:${{width}}px"` : "";
      let svg = `<svg viewBox="0 0 ${{width}} ${{height}}" role="img" aria-label="Spend over time chart"${{svgStyle}}>`;
      if (state.groupByMonth) {{
        svg += renderMonthGroupBackground(periods, left, slot, top, plotH, 18);
      }}
      for (const tick of ticks) {{
        const y = top + plotH - (tick / max) * plotH;
        svg += `<line x1="${{left}}" y1="${{y}}" x2="${{width - right}}" y2="${{y}}" stroke="#eadfd4"/>`;
        svg += `<text class="axis" x="${{left - 8}}" y="${{y + 4}}" text-anchor="end">${{money(tick, state.currency)}}</text>`;
      }}
      rows.forEach((row, index) => {{
        const x = left + index * slot + (slot - barW) / 2;
        const h = (row.amount / max) * plotH;
        const y = top + plotH - h;
        svg += `<rect x="${{x}}" y="${{y}}" width="${{barW}}" height="${{h}}" fill="${{colors[0]}}" rx="2" data-tip="${{escapeHtml(`${{labelPeriod(row.period, state.aggregation)}}: ${{moneyExact(row.amount, state.currency)}}`)}}"></rect>`;
        const showLabel = periodLabelVisible(index, rows.length, plotW, state.aggregation, state.groupByMonth);
        if (showLabel) svg += `<text class="axis" x="${{x + barW / 2}}" y="${{height - 18}}" text-anchor="middle">${{labelPeriod(row.period, state.aggregation)}}</text>`;
      }});
      svg += `</svg>`;
      els.trendChart.innerHTML = state.groupByMonth ? `<div class="chart-scroll">${{svg}}</div>` : svg;
    }}

    function renderCategoryChart(items, state) {{
      const grouped = groupSum(items, item => categoryKey(item, state.categoryMode))
        .sort((a, b) => b.amount - a.amount)
        .slice(0, 15);
      if (!grouped.length) return emptyChart(els.categoryChart, "No category spend in this window");

      const width = 560;
      const rowH = 30;
      const height = Math.max(230, grouped.length * rowH + 28);
      const left = 190;
      const right = 94;
      const max = Math.max(...grouped.map(row => row.amount), 1);
      let svg = `<svg viewBox="0 0 ${{width}} ${{height}}" role="img" aria-label="Category breakdown chart">`;
      grouped.forEach((row, index) => {{
        const y = 20 + index * rowH;
        const w = ((width - left - right) * row.amount) / max;
        const label = row.key.length > 28 ? row.key.slice(0, 27) + "..." : row.key;
        svg += `<text class="axis" x="${{left - 10}}" y="${{y + 14}}" text-anchor="end">${{label}}</text>`;
        svg += `<rect x="${{left}}" y="${{y}}" width="${{Math.max(2, w)}}" height="18" fill="${{colors[index % colors.length]}}" rx="3" data-tip="${{escapeHtml(`${{row.key}}: ${{moneyExact(row.amount, state.currency)}}`)}}"></rect>`;
        svg += `<text class="axis" x="${{left + w + 8}}" y="${{y + 14}}">${{money(row.amount, state.currency)}}</text>`;
      }});
      svg += `</svg>`;
      els.categoryChart.innerHTML = svg;
    }}

    function comparisonFilteredRecords(state, yearMonth) {{
      return records.filter(record =>
        record.yearMonth === yearMonth &&
        record.currency === state.currency &&
        statusAllowed(record.status, state.statusMode) &&
        (!state.selectedCategories.length || state.selectedCategories.includes(categoryKey(record, state.categoryMode)))
      );
    }}

    function cumulativeMonthSeries(items, yearMonth) {{
      const [year, month] = yearMonth.split("-").map(Number);
      const days = new Date(year, month, 0).getDate();
      const daily = Array(days).fill(0);
      for (const item of items) {{
        const day = Number(item.date.slice(8, 10));
        if (day >= 1 && day <= days) daily[day - 1] += item.amount;
      }}
      let running = 0;
      return daily.map((amount, index) => {{
        running += amount;
        return {{ day: index + 1, amount: running, daily: amount }};
      }});
    }}

    function renderComparisonChart(state) {{
      const comparison = getComparisonState();
      const baseItems = comparisonFilteredRecords(state, comparison.base);
      const compareItems = comparisonFilteredRecords(state, comparison.compare);
      const baseSeries = cumulativeMonthSeries(baseItems, comparison.base);
      const compareSeries = cumulativeMonthSeries(compareItems, comparison.compare);
      const maxDays = Math.max(baseSeries.length, compareSeries.length);
      const baseTotal = baseSeries.at(-1)?.amount || 0;
      const compareTotal = compareSeries.at(-1)?.amount || 0;

      if (!baseSeries.length && !compareSeries.length) {{
        els.comparisonSummary.textContent = "";
        return emptyChart(els.comparisonChart, "No month comparison data available");
      }}

      els.comparisonSummary.textContent = `${{monthPeriodName(comparison.base)}}: ${{moneyExact(baseTotal, state.currency)}} across ${{baseItems.length}} items · ${{monthPeriodName(comparison.compare)}}: ${{moneyExact(compareTotal, state.currency)}} across ${{compareItems.length}} items`;

      const width = 900;
      const height = 320;
      const left = 66;
      const right = 24;
      const top = 18;
      const bottom = 58;
      const plotW = width - left - right;
      const plotH = height - top - bottom;
      const max = Math.max(baseTotal, compareTotal, 1);
      const xFor = day => left + ((day - 1) / Math.max(maxDays - 1, 1)) * plotW;
      const yFor = amount => top + plotH - (amount / max) * plotH;
      const lineFor = series => series.map(point => `${{xFor(point.day)}},${{yFor(point.amount)}}`).join(" ");
      const ticks = [0, max / 2, max];
      const baseColor = "#ef7d4f";
      const compareColor = "#8b8b88";

      let svg = `<svg viewBox="0 0 ${{width}} ${{height}}" role="img" aria-label="Month comparison chart">`;
      for (const tick of ticks) {{
        const y = yFor(tick);
        svg += `<line x1="${{left}}" y1="${{y}}" x2="${{width - right}}" y2="${{y}}" stroke="#eadfd4"/>`;
        svg += `<text class="axis" x="${{left - 8}}" y="${{y + 4}}" text-anchor="end">${{money(tick, state.currency)}}</text>`;
      }}
      for (const day of [1, 5, 10, 15, 20, 25, maxDays]) {{
        if (day > maxDays) continue;
        const x = xFor(day);
        svg += `<text class="axis" x="${{x}}" y="${{height - 20}}" text-anchor="middle">${{day}}</text>`;
      }}
      if (compareSeries.length) {{
        svg += `<polyline points="${{lineFor(compareSeries)}}" fill="none" stroke="${{compareColor}}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></polyline>`;
      }}
      if (baseSeries.length) {{
        svg += `<polyline points="${{lineFor(baseSeries)}}" fill="none" stroke="${{baseColor}}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></polyline>`;
      }}
      compareSeries.forEach(point => {{
        svg += `<circle cx="${{xFor(point.day)}}" cy="${{yFor(point.amount)}}" r="5" fill="${{compareColor}}" opacity="0" data-tip="${{escapeHtml(`${{monthPeriodName(comparison.compare)}} day ${{point.day}}: ${{moneyExact(point.amount, state.currency)}} cumulative`)}}"></circle>`;
      }});
      baseSeries.forEach(point => {{
        svg += `<circle cx="${{xFor(point.day)}}" cy="${{yFor(point.amount)}}" r="5" fill="${{baseColor}}" opacity="0" data-tip="${{escapeHtml(`${{monthPeriodName(comparison.base)}} day ${{point.day}}: ${{moneyExact(point.amount, state.currency)}} cumulative`)}}"></circle>`;
      }});
      svg += `<text class="caption" x="${{left}}" y="${{height - 4}}">Day of month</text>`;
      svg += `<text class="caption" x="${{width - right}}" y="${{height - 4}}" text-anchor="end"><tspan fill="${{compareColor}}">— ${{monthPeriodName(comparison.compare)}}</tspan><tspan dx="18" fill="${{baseColor}}">— ${{monthPeriodName(comparison.base)}}</tspan></text>`;
      svg += `</svg>`;
      els.comparisonChart.innerHTML = svg;
    }}

    function renderStacked(items, state) {{
      const periods = chartPeriodsFor(state);
      const topCats = groupSum(items, item => item.categoryLevel1)
        .sort((a, b) => b.amount - a.amount)
        .slice(0, 8)
        .map(row => row.key);
      if (!periods.length || !topCats.length) {{
        els.stackedLegend.innerHTML = "";
        return emptyChart(els.stackedChart, "No category trend in this window");
      }}

      const periodData = periods.map(period => {{
        const buckets = Object.fromEntries([...topCats, "Other"].map(cat => [cat, 0]));
        for (const item of items) {{
          const itemPeriod = state.aggregation === "year" ? String(item.year) : item.yearMonth;
          if (itemPeriod !== period) continue;
          const key = topCats.includes(item.categoryLevel1) ? item.categoryLevel1 : "Other";
          buckets[key] += item.amount;
        }}
        return {{ period, buckets, total: Object.values(buckets).reduce((sum, value) => sum + value, 0) }};
      }});

      const width = Math.max(800, periods.length * (state.groupByMonth ? 48 : 18));
      const height = state.groupByMonth ? 344 : 320;
      const left = 58;
      const right = 18;
      const top = state.groupByMonth ? 42 : 18;
      const bottom = 54;
      const plotW = width - left - right;
      const plotH = height - top - bottom;
      const max = Math.max(...periodData.map(row => row.total), 1);
      const slot = plotW / periods.length;
      const barW = Math.max(3, Math.min(28, slot * 0.74));
      const cats = [...topCats, "Other"];

      const svgStyle = state.groupByMonth ? ` style="min-width:${{width}}px"` : "";
      let svg = `<svg viewBox="0 0 ${{width}} ${{height}}" role="img" aria-label="Stacked category trend chart"${{svgStyle}}>`;
      if (state.groupByMonth) {{
        svg += renderMonthGroupBackground(periods, left, slot, top, plotH, 18);
      }}
      for (const tick of [0, max / 2, max]) {{
        const y = top + plotH - (tick / max) * plotH;
        svg += `<line x1="${{left}}" y1="${{y}}" x2="${{width - right}}" y2="${{y}}" stroke="#eadfd4"/>`;
        svg += `<text class="axis" x="${{left - 8}}" y="${{y + 4}}" text-anchor="end">${{money(tick, state.currency)}}</text>`;
      }}
      periodData.forEach((row, index) => {{
        const x = left + index * slot + (slot - barW) / 2;
        let yCursor = top + plotH;
        cats.forEach((cat, catIndex) => {{
          const amount = row.buckets[cat] || 0;
          if (!amount) return;
          const h = (amount / max) * plotH;
          yCursor -= h;
          svg += `<rect x="${{x}}" y="${{yCursor}}" width="${{barW}}" height="${{h}}" fill="${{colors[catIndex % colors.length]}}" data-tip="${{escapeHtml(`${{labelPeriod(row.period, state.aggregation)}} - ${{cat}}: ${{moneyExact(amount, state.currency)}}`)}}"></rect>`;
        }});
        const showLabel = periodLabelVisible(index, periods.length, plotW, state.aggregation, state.groupByMonth);
        if (showLabel) svg += `<text class="axis" x="${{x + barW / 2}}" y="${{height - 18}}" text-anchor="middle">${{labelPeriod(row.period, state.aggregation)}}</text>`;
      }});
      svg += `</svg>`;
      els.stackedChart.innerHTML = state.groupByMonth ? `<div class="chart-scroll">${{svg}}</div>` : svg;
      els.stackedLegend.innerHTML = cats.map((cat, index) => `<span><i class="swatch" style="background:${{colors[index % colors.length]}}"></i>${{cat}}</span>`).join("");
    }}

    function renderMonthlyLeaders(items, state) {{
      const months = state.groupByMonth ? groupMonthsByCalendarMonth(monthRange(state.start, state.end)) : monthRange(state.start, state.end);
      const monthRows = months.map(month => {{
        const monthItems = items.filter(item => item.yearMonth === month);
        const grouped = groupSum(monthItems, item => categoryKey(item, state.categoryMode))
          .sort((a, b) => {{
            if (b.amount !== a.amount) return b.amount - a.amount;
            return a.key.localeCompare(b.key);
          }});
        const total = grouped.reduce((sum, row) => sum + row.amount, 0);
        return {{ month, grouped: grouped.slice(0, 6), total }};
      }}).filter(row => row.total > 0);

      if (!monthRows.length) {{
        return emptyChart(els.monthlyRankGrid, "No monthly category leaders in this window");
      }}

      const cardFor = monthRow => {{
        const max = Math.max(monthRow.grouped[0]?.amount || 0, 1);
        const rows = monthRow.grouped.map((row, index) => {{
          const width = Math.max(2, (row.amount / max) * 100);
          const share = monthRow.total ? (row.amount / monthRow.total) * 100 : 0;
          return `
            <div class="monthly-rank-row" data-tip="${{escapeHtml(`${{monthPeriodName(monthRow.month)}} - #${{index + 1}} ${{row.key}}: ${{moneyExact(row.amount, state.currency)}} (${{share.toFixed(1)}}%)`)}}">
              <span class="rank-number">${{index + 1}}</span>
              <div>
                <div class="rank-main">
                  <span class="rank-name">${{escapeHtml(row.key)}}</span>
                  <span class="rank-amount">${{money(row.amount, state.currency)}}</span>
                </div>
                <div class="rank-track"><span class="rank-fill" style="width:${{width}}%; background:${{colors[index % colors.length]}}"></span></div>
              </div>
            </div>
          `;
        }}).join("");
        return `
          <section class="monthly-rank-month" aria-label="${{escapeHtml(monthPeriodName(monthRow.month))}} category ranking">
            <div class="monthly-rank-title">
              <span>${{labelPeriod(monthRow.month, "month")}}</span>
              <span>${{money(monthRow.total, state.currency)}}</span>
            </div>
            ${{rows}}
          </section>
        `;
      }};

      if (state.groupByMonth) {{
        const groups = [];
        for (const row of monthRows) {{
          const month = row.month.slice(5, 7);
          const current = groups[groups.length - 1];
          if (current && current.month === month) {{
            current.rows.push(row);
          }} else {{
            groups.push({{ month, rows: [row] }});
          }}
        }}
        els.monthlyRankGrid.innerHTML = `<div class="monthly-rank-grid">${{groups.map(group => `
          <section class="monthly-rank-calendar-group" aria-label="${{escapeHtml(monthName(group.month))}} category leaders">
            <div class="monthly-rank-calendar-title">${{monthName(group.month)}}</div>
            <div class="monthly-rank-calendar-cards">${{group.rows.map(cardFor).join("")}}</div>
          </section>
        `).join("")}}</div>`;
        return;
      }}

      els.monthlyRankGrid.innerHTML = `<div class="monthly-rank-grid">${{monthRows.map(cardFor).join("")}}</div>`;
    }}

    function renderTable(items, state) {{
      const total = items.reduce((sum, item) => sum + item.amount, 0);
      const periods = periodsFor(state.start, state.end, state.aggregation);
      const rows = groupSum(items, item => categoryKey(item, state.categoryMode)).map(row => {{
        const periodTotals = new Map(periods.map(period => [period, 0]));
        for (const item of items) {{
          if (categoryKey(item, state.categoryMode) !== row.key) continue;
          const period = state.aggregation === "year" ? String(item.year) : item.yearMonth;
          periodTotals.set(period, (periodTotals.get(period) || 0) + item.amount);
        }}
        const peak = [...periodTotals.entries()].sort((a, b) => b[1] - a[1])[0] || ["-", 0];
        return {{ ...row, share: total ? row.amount / total : 0, avg: row.count ? row.amount / row.count : 0, peak }};
      }}).sort((a, b) => b.amount - a.amount);

      els.categoryTable.innerHTML = rows.map(row => `
        <tr class="clickable-row" data-category="${{escapeHtml(row.key)}}">
          <td>${{row.key}}</td>
          <td class="num">${{moneyExact(row.amount, state.currency)}}</td>
          <td class="num">${{(row.share * 100).toFixed(1)}}%</td>
          <td class="num">${{compact(row.count)}}</td>
          <td class="num">${{moneyExact(row.avg, state.currency)}}</td>
          <td>${{labelPeriod(row.peak[0], state.aggregation)}} · ${{money(row.peak[1], state.currency)}}</td>
        </tr>
      `).join("");
      els.categoryTable.querySelectorAll("tr[data-category]").forEach(row => {{
        row.addEventListener("click", () => {{
          activeDetailCategory = row.dataset.category;
          activeDetailMode = state.categoryMode;
          renderItemDetails(items, state);
        }});
      }});
    }}

    function asinLink(asin) {{
      if (!asin || asin === "_ASINLESS_") return "";
      if (asin.startsWith("http://") || asin.startsWith("https://")) return asin;
      return "";
    }}

    function itemSortValue(item, key, state) {{
      if (key === "category") return categoryKey(item, state.categoryMode);
      if (key === "amount") return item.amount;
      return item[key] || "";
    }}

    function compareItems(a, b, state) {{
      const key = detailSort.key;
      const direction = detailSort.direction === "asc" ? 1 : -1;
      const aValue = itemSortValue(a, key, state);
      const bValue = itemSortValue(b, key, state);

      let result = 0;
      if (key === "amount") {{
        result = aValue - bValue;
      }} else {{
        result = String(aValue).localeCompare(String(bValue), undefined, {{ numeric: true, sensitivity: "base" }});
      }}

      if (result !== 0) return result * direction;
      return b.amount - a.amount || b.date.localeCompare(a.date);
    }}

    function collateSimilarItems(items, state) {{
      const groups = new Map();
      for (const item of items) {{
        const productName = item.productName || "(no product name)";
        const category = categoryKey(item, state.categoryMode);
        const key = JSON.stringify([
          productName.trim().toLowerCase().replace(/\\s+/g, " "),
          category,
          item.website || "",
          item.asin || ""
        ]);
        const existing = groups.get(key) || {{
          ...item,
          productName,
          amount: 0,
          count: 0,
          firstDate: item.date,
          lastDate: item.date,
          category
        }};
        existing.amount += item.amount;
        existing.count += 1;
        existing.firstDate = item.date < existing.firstDate ? item.date : existing.firstDate;
        existing.lastDate = item.date > existing.lastDate ? item.date : existing.lastDate;
        existing.date = existing.lastDate;
        existing.dateLabel = existing.firstDate === existing.lastDate ? existing.firstDate : `${{existing.firstDate}} to ${{existing.lastDate}}`;
        groups.set(key, existing);
      }}
      return [...groups.values()];
    }}

    function updateItemSortHeaders() {{
      document.querySelectorAll("[data-item-sort]").forEach(button => {{
        const label = button.textContent.replace(/\\s*[▲▼]\\s*$/g, "");
        const active = button.dataset.itemSort === detailSort.key;
        button.textContent = active ? `${{label}} ${{detailSort.direction === "asc" ? "▲" : "▼"}}` : label;
        button.setAttribute("aria-sort", active ? (detailSort.direction === "asc" ? "ascending" : "descending") : "none");
      }});
    }}

    function positionChartTooltip(event) {{
      const tooltip = els.chartTooltip;
      const padding = 14;
      const offset = 12;
      let x = event.clientX + offset;
      let y = event.clientY + offset;
      const rect = tooltip.getBoundingClientRect();
      if (x + rect.width + padding > window.innerWidth) {{
        x = event.clientX - rect.width - offset;
      }}
      if (y + rect.height + padding > window.innerHeight) {{
        y = event.clientY - rect.height - offset;
      }}
      tooltip.style.left = `${{Math.max(padding, x)}}px`;
      tooltip.style.top = `${{Math.max(padding, y)}}px`;
    }}

    function showChartTooltip(event) {{
      const target = event.target.closest("[data-tip]");
      if (!target) return;
      els.chartTooltip.textContent = target.dataset.tip;
      els.chartTooltip.classList.add("visible");
      positionChartTooltip(event);
    }}

    function hideChartTooltip() {{
      els.chartTooltip.classList.remove("visible");
    }}

    function renderItemDetails(items, state) {{
      const selected = state.selectedCategories;
      const clickCategoryApplies = activeDetailCategory && activeDetailMode === state.categoryMode;
      const categories = clickCategoryApplies ? [activeDetailCategory] : selected;
      const collated = els.collateProducts.checked;
      updateItemSortHeaders();

      const allCategories = !categories.length;
      const matchingItems = allCategories
        ? items
        : items.filter(item => categories.includes(categoryKey(item, state.categoryMode)));
      const detailRows = (collated ? collateSimilarItems(matchingItems, state) : matchingItems)
        .sort((a, b) => compareItems(a, b, state));
      const shown = detailRows.slice(0, 250);
      const total = matchingItems.reduce((sum, item) => sum + item.amount, 0);
      const categoryLabel = allCategories ? "all categories" : (categories.length === 1 ? categories[0] : `${{categories.length}} selected categories`);
      const sortButton = document.querySelector(`[data-item-sort="${{detailSort.key}}"]`);
      const sortLabel = (sortButton?.textContent || "Amount").replace(/\\s*[▲▼]\\s*$/g, "").toLowerCase();
      const sortDirection = detailSort.direction === "asc" ? "ascending" : "descending";
      const rowLabel = collated ? "product groups" : "items";
      const sourceLabel = collated ? ` from ${{matchingItems.length}} purchases` : "";
      els.itemDetailNote.textContent = `Showing ${{shown.length}} of ${{detailRows.length}} ${{rowLabel}}${{sourceLabel}} for ${{categoryLabel}} · ${{moneyExact(total, state.currency)}} total. Sorted by ${{sortLabel}} ${{sortDirection}}.`;

      els.itemTable.innerHTML = shown.map(item => {{
        const link = asinLink(item.asin);
        const productName = escapeHtml(item.productName || "(no product name)");
        const productCell = link ? `<a href="${{escapeHtml(link)}}" target="_blank" rel="noopener">${{productName}}</a>` : productName;
        const productMeta = collated ? `<span class="item-meta">${{compact(item.count)}} purchases</span>` : "";
        return `
          <tr>
            <td>${{escapeHtml(item.dateLabel || item.date)}}</td>
            <td class="product-cell">${{productCell}}${{productMeta}}</td>
            <td class="num">${{moneyExact(item.amount, state.currency)}}</td>
            <td>${{escapeHtml(categoryKey(item, state.categoryMode))}}</td>
          </tr>
        `;
      }}).join("");
    }}

    function renderKpis(items, state) {{
      const periods = periodsFor(state.start, state.end, state.aggregation);
      const total = items.reduce((sum, item) => sum + item.amount, 0);
      const groupedPeriods = groupSum(items, item => state.aggregation === "year" ? String(item.year) : item.yearMonth);
      const peak = groupedPeriods.sort((a, b) => b.amount - a.amount)[0];
      const categories = groupSum(items, item => item.categoryLevel1).sort((a, b) => b.amount - a.amount);
      const top = categories[0];
      const statuses = groupSum(items, item => item.status).sort((a, b) => b.count - a.count);

      document.getElementById("kpiTotal").textContent = money(total, state.currency);
      document.getElementById("kpiWindow").textContent = windowLabel(state);
      document.getElementById("kpiAverage").textContent = money(periods.length ? total / periods.length : 0, state.currency);
      document.getElementById("kpiAverageSub").textContent = `${{periods.length}} selected ${{state.aggregation === "year" ? "years" : "months"}}`;
      document.getElementById("kpiItems").textContent = compact(items.length);
      document.getElementById("kpiStatuses").textContent = statuses.map(row => `${{row.key}}: ${{compact(row.count)}}`).join(" · ") || "-";
      document.getElementById("kpiTopCategory").textContent = top ? top.key : "-";
      document.getElementById("kpiTopCategorySub").textContent = top ? `${{money(top.amount, state.currency)}} · ${{((top.amount / Math.max(total, 1)) * 100).toFixed(1)}}%` : "-";
      document.getElementById("kpiPeak").textContent = peak ? labelPeriod(peak.key, state.aggregation) : "-";
      document.getElementById("kpiPeakSub").textContent = peak ? money(peak.amount, state.currency) : "-";
    }}

    function renderInsights(items, state) {{
      const total = items.reduce((sum, item) => sum + item.amount, 0);
      const periods = periodsFor(state.start, state.end, state.aggregation);
      const periodTotals = new Map(periods.map(period => [period, 0]));
      for (const item of items) {{
        const period = state.aggregation === "year" ? String(item.year) : item.yearMonth;
        periodTotals.set(period, (periodTotals.get(period) || 0) + item.amount);
      }}
      const periodRows = [...periodTotals.entries()];
      const last = periodRows[periodRows.length - 1] || ["-", 0];
      const prev = periodRows[periodRows.length - 2] || ["-", 0];
      const delta = last[1] - prev[1];
      const cats = groupSum(items, item => item.categoryLevel1).sort((a, b) => b.amount - a.amount);
      const topThree = cats.slice(0, 3);
      const other = cats.slice(3).reduce((sum, row) => sum + row.amount, 0);
      const uncategorized = cats.find(row => row.key === "Other / Uncategorized");
      const biggestAvg = cats.map(row => {{ return {{ ...row, avg: row.amount / row.count }}; }}).sort((a, b) => b.avg - a.avg)[0];

      const cards = [
        {{
          title: "Concentration",
          body: topThree.length ? `${{topThree.map(row => row.key).join(", ")}} account for ${{((topThree.reduce((sum, row) => sum + row.amount, 0) / Math.max(total, 1)) * 100).toFixed(1)}}% of spend.` : "No category concentration for this window."
        }},
        {{
          title: "Recent Change",
          body: periodRows.length >= 2 ? `${{labelPeriod(last[0], state.aggregation)}} is ${{money(Math.abs(delta), state.currency)}} ${{delta >= 0 ? "above" : "below"}} ${{labelPeriod(prev[0], state.aggregation)}}.` : "Select at least two periods to compare recent change."
        }},
        {{
          title: "Long Tail",
          body: cats.length > 3 ? `Categories outside the top three total ${{money(other, state.currency)}} across ${{Math.max(0, cats.length - 3)}} categories.` : "Spend is concentrated in three or fewer categories."
        }},
        {{
          title: "Review Queue",
          body: uncategorized ? `${{money(uncategorized.amount, state.currency)}} is still in Other / Uncategorized. Highest average item category is ${{biggestAvg.key}} at ${{moneyExact(biggestAvg.avg, state.currency)}}.` : `No Other / Uncategorized spend in this window. Highest average item category is ${{biggestAvg ? biggestAvg.key : "-"}}.`
        }}
      ];
      els.insights.innerHTML = cards.map(card => `<div class="insight"><b>${{card.title}}</b><span>${{card.body}}</span></div>`).join("");
    }}

    function render() {{
      const state = getState();
      if (state.start > state.end) {{
        const startYear = els.startYear.value;
        const startMonth = els.startMonth.value;
        els.startYear.value = els.endYear.value;
        els.startMonth.value = els.endMonth.value;
        els.endYear.value = startYear;
        els.endMonth.value = startMonth;
        return render();
      }}
      const items = filteredRecords(state);
      renderKpis(items, state);
      renderTrend(items, state);
      renderCategoryChart(items, state);
      renderComparisonChart(state);
      renderStacked(items, state);
      renderMonthlyLeaders(items, state);
      renderTable(items, state);
      renderItemDetails(items, state);
      renderInsights(items, state);
    }}

    function syncComparisonControls() {{
      const custom = els.comparisonMode.value === "customMonth";
      els.comparisonCompareYear.disabled = !custom;
      els.comparisonCompareMonth.disabled = !custom;
      els.comparisonCompareYearLabel.classList.toggle("is-hidden", !custom);
      els.comparisonCompareMonthLabel.classList.toggle("is-hidden", !custom);
    }}

    function syncTimeGroupingControls() {{
      els.groupByMonth.disabled = els.aggregation.value !== "month";
    }}

    function init() {{
      const months = [...new Set(records.map(record => record.yearMonth))].sort();
      const years = [...new Set(records.map(record => record.year))].sort((a, b) => a - b);
      for (const month of months) {{
        const year = month.slice(0, 4);
        const monthPart = month.slice(5, 7);
        const current = monthBoundsByYear.get(year) || {{ first: monthPart, last: monthPart }};
        current.first = monthPart < current.first ? monthPart : current.first;
        current.last = monthPart > current.last ? monthPart : current.last;
        monthBoundsByYear.set(year, current);
      }}
      const defaultStartYear = years.includes(meta.defaultYearStart) ? meta.defaultYearStart : years[0];
      const defaultEndYear = Number(months[months.length - 1].slice(0, 4));
      const yearOptions = years.map(year => `<option value="${{year}}">${{year}}</option>`).join("");
      const monthOptions = [
        `<option value="">All months</option>`,
        ...Array.from({{ length: 12 }}, (_, index) => {{
          const value = String(index + 1).padStart(2, "0");
          return `<option value="${{value}}">${{monthName(value)}}</option>`;
        }})
      ].join("");

      els.startYear.innerHTML = yearOptions;
      els.endYear.innerHTML = yearOptions;
      els.comparisonBaseYear.innerHTML = yearOptions;
      els.comparisonCompareYear.innerHTML = yearOptions;
      els.startMonth.innerHTML = monthOptions;
      els.endMonth.innerHTML = monthOptions;
      els.comparisonBaseMonth.innerHTML = monthOptions.replace(`<option value="">All months</option>`, "");
      els.comparisonCompareMonth.innerHTML = monthOptions.replace(`<option value="">All months</option>`, "");
      els.startYear.value = defaultStartYear;
      els.endYear.value = defaultEndYear;
      els.startMonth.value = "";
      els.endMonth.value = "";
      els.comparisonBaseYear.value = defaultEndYear;
      els.comparisonBaseMonth.value = months[months.length - 1].slice(5, 7);
      els.comparisonCompareYear.value = defaultEndYear;
      els.comparisonCompareMonth.value = months[months.length - 1].slice(5, 7);
      syncComparisonControls();
      syncTimeGroupingControls();

      const currencies = [...new Set(records.map(record => record.currency))].sort();
      els.currency.innerHTML = currencies.map(currency => `<option value="${{currency}}">${{currency}}</option>`).join("");
      els.currency.value = currencies.includes("USD") ? "USD" : currencies[0];

      detailSort = {{ key: "amount", direction: "desc" }};
      populateCategoryFilter(false);

      els.categoryFilter.addEventListener("click", event => {{
        const checkbox = event.target.closest("input[type='checkbox']");
        if (!checkbox || !els.categoryFilter.contains(checkbox)) return;

        const boxes = categoryCheckboxes();
        if (event.shiftKey && lastCategoryCheckbox && boxes.includes(lastCategoryCheckbox)) {{
          const start = boxes.indexOf(lastCategoryCheckbox);
          const end = boxes.indexOf(checkbox);
          const [from, to] = start < end ? [start, end] : [end, start];
          for (const box of boxes.slice(from, to + 1)) {{
            box.checked = checkbox.checked;
          }}
        }}
        lastCategoryCheckbox = checkbox;
      }});

      for (const control of [els.startYear, els.startMonth, els.endYear, els.endMonth, els.aggregation, els.groupByMonth, els.currency, els.categoryFilter]) {{
        control.addEventListener("change", () => {{
          syncTimeGroupingControls();
          render();
        }});
      }}
      for (const control of [els.comparisonBaseYear, els.comparisonBaseMonth, els.comparisonCompareYear, els.comparisonCompareMonth]) {{
        control.addEventListener("change", render);
      }}
      els.comparisonMode.addEventListener("change", () => {{
        syncComparisonControls();
        render();
      }});
      els.clearCategoryFilter.addEventListener("click", () => {{
        categoryCheckboxes().forEach(input => input.checked = false);
        lastCategoryCheckbox = null;
        activeDetailCategory = "";
        render();
      }});
      els.clearItemDetail.addEventListener("click", () => {{
        activeDetailCategory = "";
        detailSort = {{ key: "amount", direction: "desc" }};
        renderItemDetails(filteredRecords(getState()), getState());
      }});
      document.querySelectorAll("[data-item-sort]").forEach(button => {{
        button.addEventListener("click", () => {{
          const key = button.dataset.itemSort;
          if (detailSort.key === key) {{
            detailSort.direction = detailSort.direction === "asc" ? "desc" : "asc";
          }} else {{
            detailSort.key = key;
            detailSort.direction = key === "amount" || key === "date" ? "desc" : "asc";
          }}
          renderItemDetails(filteredRecords(getState()), getState());
        }});
      }});
      els.collateProducts.addEventListener("change", () => {{
        renderItemDetails(filteredRecords(getState()), getState());
      }});
      document.addEventListener("pointerover", showChartTooltip);
      document.addEventListener("pointermove", event => {{
        if (event.target.closest("[data-tip]")) positionChartTooltip(event);
      }});
      document.addEventListener("pointerout", event => {{
        if (event.target.closest("[data-tip]")) hideChartTooltip();
      }});
      els.categoryMode.addEventListener("change", () => {{
        categoryCheckboxes().forEach(input => input.checked = false);
        lastCategoryCheckbox = null;
        activeDetailCategory = "";
        populateCategoryFilter(false);
        render();
      }});

      const sourceYears = [...new Set(records.map(record => record.sourceYear).filter(Boolean))].sort((a, b) => a - b);
      const sourceYearLabel = sourceYears.length ? `${{sourceYears[0]}}-${{sourceYears[sourceYears.length - 1]}}` : "-";
      const returnedLabel = meta.returnedRowsIncluded ? "Returned rows included." : "Returned rows excluded.";
      els.footer.innerHTML = `Generated ${{new Date(meta.generatedAt).toLocaleString()}} from ${{meta.sourceFiles.length}} annual CSV files in ${{escapeHtml(meta.workdir)}}. Loaded ${{compact(meta.recordCount)}} rows using ${{meta.amountField}}. Source years: ${{sourceYearLabel}}. ${{returnedLabel}} Skipped rows: ${{Object.entries(meta.skipped).map(([key, value]) => `${{key}}=${{value}}`).join(", ")}}.`;

      render();
    }}

    init();
  </script>
</body>
</html>
"""


def main():
    args = parse_args()
    if args.start_year and args.end_year and args.start_year > args.end_year:
        raise SystemExit("--start-year cannot be greater than --end-year")
    output = args.output or (args.workdir / "dashboard" / DEFAULT_OUTPUT_NAME)
    files, records, skipped = read_orders(args.workdir, args.start_year, args.end_year, args.include_returned)
    if not files:
        raise SystemExit(f"No files matched {ORDER_PATTERN!r} in {args.workdir / 'orders'}")
    if not records:
        raise SystemExit("No usable records found.")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(records, files, skipped, args.workdir, args.include_returned), encoding="utf-8")

    years = sorted({record["sourceYear"] for record in records if record.get("sourceYear")})
    currencies = sorted({record["currency"] for record in records})
    year_label = f"{years[0]}-{years[-1]}" if years else "-"
    print(f"output={output}")
    print(f"source_files={len(files)} records={len(records)} years={year_label} currencies={','.join(currencies)}")
    print(f"skipped={skipped}")


if __name__ == "__main__":
    main()

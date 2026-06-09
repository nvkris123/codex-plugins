#!/usr/bin/env python3
"""Apply reviewed Amazon category decisions to categorized annual order CSVs."""

import argparse
import csv
import datetime as dt
import json
from pathlib import Path


DEFAULT_WORKDIR = "amazon-history-categorized"
OTHER_CATEGORY = "Other / Uncategorized"
APPROVED_TOP_LEVEL_CATEGORIES = {
    "Amazon Devices & Accessories",
    "Arts, Crafts & Sewing",
    "Automotive",
    "Baby Products",
    "Beauty & Personal Care",
    "Books",
    "Cell Phones & Accessories",
    "Clothing & Accessories",
    "Clothing, Shoes & Jewelry",
    "Computers",
    "Digital Services & Subscriptions",
    "Electronics",
    "Everything Else",
    "Grocery & Gourmet Food",
    "Grocery & Gourmet Foods",
    "Health & Household",
    "Health, Household & Baby Care",
    "Home & Kitchen",
    "Home Improvement",
    "Office Products",
    "Pet Supplies",
    "Software",
    "Sports & Outdoors",
    "Sports, Fitness & Outdoors",
    "Tools & Home Improvement",
    "Toys & Games",
    OTHER_CATEGORY,
}


def clean(value):
    return str(value or "").strip()


def truthy(value):
    return clean(value).lower() in {"1", "true", "yes", "y"}


def read_csv(path):
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def valid_category(category):
    text = clean(category)
    if not text:
        return False
    return any(text == top or text.startswith(top + " > ") for top in APPROVED_TOP_LEVEL_CATEGORIES)


def load_decisions(path):
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise SystemExit("Decision JSON must be a list of objects")
        rows = data
    else:
        _, rows = read_csv(path)

    decisions = []
    for row in rows:
        product_name = clean(row.get("product_name") or row.get("Product Name"))
        category = clean(row.get("category") or row.get("resolved_category"))
        if not product_name or not valid_category(category):
            continue
        decisions.append(
            {
                "product_name": product_name,
                "asin": clean(row.get("asin") or row.get("ASIN")),
                "url": clean(row.get("url") or row.get("normalized_asin_url")),
                "category": category,
                "notes": clean(row.get("notes")),
                "source": clean(row.get("source") or row.get("resolution_source")) or "ai_skill",
            }
        )
    return decisions


def decision_keys(decision):
    keys = []
    if decision["url"]:
        keys.append(("url", decision["url"]))
    if decision["asin"] and decision["asin"] != "_ASINLESS_":
        keys.append(("asin", decision["asin"]))
    keys.append(("product_name", decision["product_name"]))
    return keys


def append_overrides(workdir, decisions):
    path = workdir / "category-overrides.csv"
    fieldnames = ["match_type", "match_value", "category", "source", "notes", "created_at"]
    existing = set()
    if path.exists():
        _, rows = read_csv(path)
        existing.update((clean(row.get("match_type")), clean(row.get("match_value"))) for row in rows)

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    new_rows = []
    for decision in decisions:
        for match_type, match_value in decision_keys(decision):
            key = (match_type, match_value)
            if key in existing:
                continue
            new_rows.append(
                {
                    "match_type": match_type,
                    "match_value": match_value,
                    "category": decision["category"],
                    "source": decision["source"],
                    "notes": decision["notes"],
                    "created_at": now,
                }
            )
            existing.add(key)

    if not new_rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(new_rows)
    return len(new_rows)


def build_lookup(decisions):
    lookup = {}
    for decision in decisions:
        for key in decision_keys(decision):
            lookup[key] = decision
    return lookup


def row_decision(row, lookup):
    keys = [
        ("url", clean(row.get("normalized_asin_url") or row.get("url"))),
        ("asin", clean(row.get("ASIN") or row.get("asin"))),
        ("product_name", clean(row.get("Product Name") or row.get("product_name"))),
    ]
    for key in keys:
        if key[1] and key in lookup:
            return lookup[key]
    return None


def apply_to_orders(workdir, decisions):
    lookup = build_lookup(decisions)
    updated = 0
    touched_files = 0
    for path in sorted((workdir / "orders").glob("orders-*.csv")):
        fieldnames, rows = read_csv(path)
        changed = False
        for row in rows:
            if row.get("category_needs_review") != "true":
                continue
            decision = row_decision(row, lookup)
            if not decision:
                continue
            row["category"] = decision["category"]
            row["category_source"] = decision["source"]
            row["category_confidence"] = "medium"
            row["category_reason"] = decision["notes"] or "AI skill category review"
            row["category_needs_review"] = "false"
            updated += 1
            changed = True
        if changed:
            write_csv(path, fieldnames, rows)
            touched_files += 1
    return updated, touched_files


def refresh_review_files(workdir, decisions):
    lookup = build_lookup(decisions)
    removed = 0
    for path in sorted((workdir / "review").glob("orders-*-category-review.csv")):
        fieldnames, rows = read_csv(path)
        remaining = []
        for row in rows:
            if row_decision(row, lookup):
                removed += 1
            else:
                remaining.append(row)
        if remaining:
            write_csv(path, fieldnames, remaining)
        elif path.exists():
            path.unlink()
    return removed


def parse_args():
    parser = argparse.ArgumentParser(
        description="Apply AI/manual Amazon category decisions to annual categorized CSVs."
    )
    parser.add_argument("--workdir", type=Path, default=Path(DEFAULT_WORKDIR), help=f"Default: {DEFAULT_WORKDIR}")
    parser.add_argument(
        "--decisions",
        type=Path,
        required=True,
        help="JSON or CSV file with product_name and category fields. Optional fields: asin, url, notes, source.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.workdir.exists():
        raise SystemExit(f"Missing workdir: {args.workdir}")
    decisions = load_decisions(args.decisions)
    if not decisions:
        raise SystemExit("No valid decisions found")

    overrides_added = append_overrides(args.workdir, decisions)
    rows_updated, files_updated = apply_to_orders(args.workdir, decisions)
    review_rows_removed = refresh_review_files(args.workdir, decisions)

    print("Amazon category resolutions applied")
    print(f"decisions={len(decisions)}")
    print(f"overrides_added={overrides_added}")
    print(f"order_rows_updated={rows_updated}")
    print(f"order_files_updated={files_updated}")
    print(f"review_rows_removed={review_rows_removed}")


if __name__ == "__main__":
    main()

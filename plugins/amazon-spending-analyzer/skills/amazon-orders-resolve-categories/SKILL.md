---
name: amazon-orders-resolve-categories
description: Resolve ambiguous Amazon order categories left in amazon-history-categorized review CSVs using AI reasoning, then apply those decisions with the bundled helper script. Use when the user asks to resolve remaining Amazon categories, finish categorization, classify review rows, or continue after deterministic ingest.
---

# Amazon Orders Resolve Categories

Use AI reasoning only on review CSVs. Do not read the full annual order CSVs for category resolution.

## Files

Default workdir:

```text
amazon-history-categorized
```

Review inputs:

```text
<workdir>/review/orders-*-category-review.csv
```

Decision output:

```text
<workdir>/review/category-decisions-YYYYMMDD-HHMMSS.json
```

Apply command:

```bash
python3 "<plugin-root>/scripts/apply_category_resolutions.py" \
  --workdir "<workdir>" \
  --decisions "<decision-json>"
```

## Workflow

Resolve `<plugin-root>` as the root of this installed plugin, two directories above this `SKILL.md`.

1. Read review CSV rows only.
2. Deduplicate by `product_name`, keeping `asin`, `url`, `source_type`, and `website_or_marketplace` as context.
3. Classify each unique product into a category.
4. Write a JSON list using this schema:

```json
[
  {
    "product_name": "exact product name from review CSV",
    "asin": "optional ASIN from review CSV",
    "url": "optional URL from review CSV",
    "category": "category",
    "notes": "short reason",
    "source": "ai_skill"
  }
]
```

5. Run the apply command.
6. Report decisions made, order rows updated, and review rows remaining.

## Category Rules

Prefer a specific Amazon-style category when clear, using `Top Level > Subcategory` when helpful.

Allowed top-level categories:

- Amazon Devices & Accessories
- Arts, Crafts & Sewing
- Automotive
- Baby Products
- Beauty & Personal Care
- Books
- Cell Phones & Accessories
- Clothing & Accessories
- Clothing, Shoes & Jewelry
- Computers
- Digital Services & Subscriptions
- Electronics
- Everything Else
- Grocery & Gourmet Food
- Grocery & Gourmet Foods
- Health & Household
- Health, Household & Baby Care
- Home & Kitchen
- Home Improvement
- Office Products
- Pet Supplies
- Software
- Sports & Outdoors
- Sports, Fitness & Outdoors
- Tools & Home Improvement
- Toys & Games
- Other / Uncategorized

Use `Other / Uncategorized` only when the product name is genuinely too vague.

## Context Discipline

If there are many review rows, process them in batches. Write and apply decisions incrementally rather than loading annual order CSVs into context.

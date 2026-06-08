#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


DEFAULT_WORKDIR = "amazon-history-categorized"
PLACEHOLDER_ASINS = {"", "_ASINLESS_", "Not Available", "Not Applicable"}
OTHER_CATEGORY = "Other / Uncategorized"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

HELPER_COLUMNS = [
    "source_file",
    "source_type",
    "source_order_date",
    "source_marketplace",
    "normalized_asin_url",
]
RETURN_COLUMNS = ["is_returned"]
CATEGORY_COLUMNS = [
    "category",
    "category_source",
    "category_confidence",
    "category_reason",
    "category_needs_review",
]
MANAGED_COLUMNS = HELPER_COLUMNS + RETURN_COLUMNS + CATEGORY_COLUMNS

APPROVED_TOP_LEVEL_CATEGORIES = [
    "Grocery & Gourmet Food",
    "Home & Kitchen",
    "Electronics",
    "Clothing, Shoes & Jewelry",
    "Health & Household",
    "Beauty & Personal Care",
    "Tools & Home Improvement",
    "Toys & Games",
    "Books",
    "Office Products",
    "Sports & Outdoors",
    "Arts, Crafts & Sewing",
    "Automotive",
    "Pet Supplies",
    "Digital Services & Subscriptions",
    "Magazine Subscriptions",
    OTHER_CATEGORY,
]

CATEGORY_RULES = [
    ("Digital Services & Subscriptions", r"\b(amazon prime|prime shopping edition|payment method verification)\b"),
    ("Electronics > Cables & Accessories", r"\b(toslink|optical audio|sound\s*bar|soundbar|cable|charger|usb|hdmi|adapter|connector|screen protector|earbud|airpods|power strip|extension cord)\b"),
    ("Electronics", r"\b(galaxy tab|tablet|electronics|phone|iphone|ipad|laptop|computer|monitor|keyboard|mouse|headphone|speaker|camera|ssd|router|wifi|bluetooth|kindle|echo|alexa|fire tv|led bulb|bulbs?|dimmable|edison)\b"),
    ("Clothing, Shoes & Jewelry", r"\b(children's place|girls?|boys?|women's|mens?|shirts?|t-shirts?|jumpsuits?|blouses?|clothes|dress|gloves?|flip flop|loafer|salwar|kameez|tights|leotards?|costume|fashion|lanyard|badge holder|socks?|shoe|sneaker|boot|jacket|hoodie|belt|watch|hat|sunglasses|wallet|backpack|bracelets?|jewelry|palazzo pants|trousers|crossbody bag|shoulder bag)\b"),
    ("Books", r"\b(book|paperback|hardcover|novel|workbook|chapter book|stories|box set|author|stock operator|reminiscences)\b"),
    ("Health & Household", r"\b(motion sickness|nausea|massage gun|massager|toothpaste|teeth whitening|whitening strips|partysmart|liver support|vitamin|supplement|medicine|allergy|tooth|dental|diaper|wipes|baby|health|sanitizer|thermometer|bandage|first aid|masks?|condoms?|latex-free|pre-lubricated|sensitive skin)\b"),
    ("Beauty & Personal Care", r"\b(fragrances?|perfumes?|cotton balls?|shampoo|conditioner|lotion|cream|skincare|skin care|razor|deodorant|body wash|sunscreen|makeup|beauty|hair|crest|lumineux|cleansing bar|odor control|moisturizing|soap)\b"),
    ("Home & Kitchen > Cleaning & Laundry", r"\b(laundry detergent|detergent pods|hand soap|soap refill|dishwasher rinse aid|moving blankets?|laundry hamper)\b"),
    ("Home & Kitchen", r"\b(mini fridge|silicone mat|induction cooktop|electric stove|griddle|kitchen|pan|pot|knife|bowl|plate|cup|mug|glass|bottle|towel|sheet|pillow|blanket|lamp|desk|chair|table|shelf|rack|curtain|rug|vacuum|humidifier|container|organizer|home|basket|fridge)\b"),
    ("Automotive", r"\b(mazda|retainer clip|tire pressure|tire gauge|cars?\b|auto|automotive)\b"),
    ("Tools & Home Improvement > Safety & Security", r"\b(smoke|carbon monoxide|detector|alarm)\b"),
    ("Tools & Home Improvement", r"\b(tool|screw|drill|wrench|hardware|paint|adhesive|glue|garage|command strip|filter)\b"),
    ("Toys & Games", r"\b(relative insanity|sonic|goodie bags|party favor|cupcake decorations|scrabble|board games?|collectible stickers?|hello kitty pez|toy|game|puzzle|lego|cards|magnetic building|fidget|kids|playground)\b"),
    ("Arts, Crafts & Sewing", r"\b(bead|beading|bracelet|string|brayer|printmaking|craft)\b"),
    ("Office Products", r"\b(sign stand|display|sign holder|frame 8\.5x11|architectural scale ruler|straight ruler|triangular ruler|architects|engineers|notebook|pen|pencil|paper|printer|ink|marker|binder|folder|office|label|stapler|tape|scissors)\b"),
    ("Sports & Outdoors", r"\b(yoga|exercise|fitness|gym|bike|bicycle|running|camping|hiking|sports|ball|outdoor|swim|goggles|pickleball|paddles|racket)\b"),
    ("Pet Supplies", r"\b(cat|dog|pet|litter|leash|collar|treats|kibble)\b"),
    ("Grocery & Gourmet Food > Frozen Foods", r"\b(frozen|ice cream|yasso|pizza|waffles|tenders|smoothie)\b"),
    ("Grocery & Gourmet Food > Dairy, Eggs & Cheese", r"\b(parmesan|cheese|brie|oatmilk|oat milk|milk|yogurt|yoghurt|eggs|butter|cream|mozzarella|siggi|a2 milk)\b"),
    ("Grocery & Gourmet Food > Produce", r"\b(organic banana|banana|apple|berries|blueberries|raspberries|strawberries|broccoli|beets|tomatoes|lettuce|salad|avocado|produce|fruit|vegetable|cilantro|spinach|kale|potato|onion|garlic|carrot|cucumber|mushroom|pepper|lemon|lime|pineapple|watermelon|green bean|bean green|chunks?|cloves)\b"),
    ("Grocery & Gourmet Food > Meat, Seafood & Deli", r"\b(chicken|ham|salami|turkey|beef|pork|salmon|tuna|sushi|sausage|bacon|meat|deli|pepperoni|rotisserie)\b"),
    ("Grocery & Gourmet Food > Bakery", r"\b(bread|bagel|bagels|croissant|waffle|muffin|bakery|bun|buns|tortilla|naan|cake|cookies)\b"),
    ("Grocery & Gourmet Food > Beverages", r"\b(water|tea|coffee|soda|juice|sparkling|beverage|kombucha|drink)\b"),
    ("Grocery & Gourmet Food > Pantry", r"\b(maggi|masala|cocorolls|pez|candy|refill roll|linguine|pasta|gum|superfood|xylitol|spice|protein bar|snack bar|granola bar|chocolate bar|nutrition bar|honey|sugar|chocolate|beans|nuts|oil|flour|cracker|chickpea puffs|snacks)\b"),
    ("Grocery & Gourmet Food > Prepared Foods", r"\b(tzatziki|prepared)\b"),
    ("Grocery & Gourmet Food", r"\b(grocery|organic|snack|chips|cereal|rice|sauce|food)\b"),
]
COMPILED_RULES = [(category, re.compile(pattern, re.I)) for category, pattern in CATEGORY_RULES]


def truthy(value):
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def clean_cell(value):
    return (value or "").strip()


def is_placeholder(value):
    return clean_cell(value) in PLACEHOLDER_ASINS


def parse_order_date(value):
    text = clean_cell(value)
    if not text or text in {"Not Available", "Not Applicable"}:
        return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if not match:
        return None
    try:
        return dt.date.fromisoformat(match.group(0))
    except ValueError:
        return None


def date_sort_key(row):
    parsed = parse_order_date(row.get("source_order_date") or row.get("Order Date"))
    return (parsed or dt.date.min, clean_cell(row.get("source_type")), clean_cell(row.get("Order ID")), clean_cell(row.get("Product Name")))


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def append_csv(path, fieldnames, rows):
    if not rows:
        return
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writerows(rows)


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_html(text):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<.*?>", " ", text or "", flags=re.S))).strip()


def parse_title(body):
    match = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    return clean_html(match.group(1)) if match else ""


def parse_crumbs(body):
    for pattern in [
        r'id=["\']wayfinding-breadcrumbs_feature_div["\'](.*?)(?:</ul>|</div>\s*</div>)',
        r'class=["\'][^"\']*a-breadcrumb[^"\']*["\'](.*?)(?:</ul>|</div>)',
    ]:
        match = re.search(pattern, body, re.S | re.I)
        if match:
            crumbs = [clean_html(x) for x in re.findall(r"<a[^>]*>(.*?)</a>", match.group(1), re.S | re.I)]
            crumbs = [c for c in crumbs if c and c.lower() != "back to results"]
            if crumbs:
                return crumbs
    return []


def title_suffix(title):
    parts = [part.strip() for part in title.split(" : ")]
    if len(parts) >= 2 and 2 <= len(parts[-1]) <= 80 and not parts[-1].lower().startswith("amazon"):
        return parts[-1]
    return ""


def source_marketplace(row):
    return clean_cell(row.get("Website")) or clean_cell(row.get("Marketplace")) or clean_cell(row.get("source_marketplace"))


def asin_to_url(asin_value, marketplace):
    asin = clean_cell(asin_value)
    if asin in PLACEHOLDER_ASINS or asin.startswith(("http://", "https://")):
        return asin
    source = clean_cell(marketplace).lower()
    domain = "www.amazon.in" if "amazon.in" in source or "audible.in" in source or source == "amazon.in" else "www.amazon.com"
    return f"https://{domain}/dp/{asin}"


def fetch_context(url, cache, timeout):
    if url in cache:
        return cache[url]

    info = {"title": "", "crumbs": [], "title_suffix": "", "error": ""}
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "ignore")
        title = parse_title(body)
        info["title"] = title
        info["crumbs"] = parse_crumbs(body)
        info["title_suffix"] = title_suffix(title)
        if "captcha" in body[:200000].lower() and not title:
            info["error"] = "captcha_or_blocked"
    except Exception as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"[:200]

    cache[url] = info
    return info


def asinless_category(product_name):
    name = (product_name or "").lower()
    if "magazine" in name:
        return "Magazine Subscriptions"
    if "book" in name:
        return "Books"
    return "Grocery & Gourmet Food"


def regex_category(product_name):
    for category, pattern in COMPILED_RULES:
        if pattern.search(product_name or ""):
            return category
    return ""


def digital_category(row):
    if row.get("source_type") != "digital":
        return ""
    text = " ".join(
        clean_cell(row.get(name))
        for name in [
            "Product Name",
            "Marketplace",
            "Seller of Record",
            "Publisher",
            "Subscription Order Type",
            "Subscription Order Info List",
            "Offer Type Code",
            "Digital Order Item Attributes",
        ]
    ).lower()
    if re.search(r"\b(subscription|signup|renewal|starz|channel|prime video|music unlimited)\b", text):
        return "Digital Services & Subscriptions"
    if re.search(r"\b(audible|audiobook|kindle|ebook|e-book|publisher)\b", text):
        return "Books"
    return ""


def load_overrides(path):
    overrides = {"asin": {}, "url": {}, "product_name": {}}
    if not path.exists():
        return overrides
    fieldnames, rows = read_csv(path)
    for row in rows:
        match_type = clean_cell(row.get("match_type"))
        match_value = clean_cell(row.get("match_value"))
        category = clean_cell(row.get("category"))
        if match_type in overrides and match_value and category:
            overrides[match_type][match_value] = category
    return overrides


def append_overrides(path, new_overrides):
    if not new_overrides:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["match_type", "match_value", "category", "source", "notes", "created_at"]
    existing = set()
    if path.exists():
        _, rows = read_csv(path)
        for row in rows:
            existing.add((clean_cell(row.get("match_type")), clean_cell(row.get("match_value"))))
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for row in new_overrides:
            key = (clean_cell(row.get("match_type")), clean_cell(row.get("match_value")))
            if key in existing:
                continue
            writer.writerow(row)
            existing.add(key)


def apply_override(row, overrides):
    asin = clean_cell(row.get("ASIN"))
    url = clean_cell(row.get("normalized_asin_url"))
    product = clean_cell(row.get("Product Name"))
    for match_type, value in [("url", url), ("asin", asin), ("product_name", product)]:
        if value and value in overrides.get(match_type, {}):
            return overrides[match_type][value], f"{match_type}:{value}"
    return "", ""


def infer_category(row, cache, overrides):
    override_category, override_reason = apply_override(row, overrides)
    if override_category:
        return {
            "category": override_category,
            "category_source": "override",
            "category_confidence": "high",
            "category_reason": override_reason,
            "category_needs_review": "false",
        }

    asin = clean_cell(row.get("ASIN"))
    product_name = row.get("Product Name") or ""
    url = clean_cell(row.get("normalized_asin_url"))

    if asin == "_ASINLESS_":
        return {
            "category": asinless_category(product_name),
            "category_source": "asinless_rule",
            "category_confidence": "high",
            "category_reason": "_ASINLESS_ product-name rule",
            "category_needs_review": "false",
        }

    info = cache.get(url, {}) if url.startswith(("http://", "https://")) else {}
    crumbs = [c for c in info.get("crumbs", []) if c and c.lower() != "back to results"]
    if crumbs:
        return {
            "category": " > ".join(crumbs[:5]),
            "category_source": "amazon_breadcrumb",
            "category_confidence": "high",
            "category_reason": "Amazon breadcrumb cache",
            "category_needs_review": "false",
        }

    suffix = clean_cell(info.get("title_suffix"))
    if suffix and suffix.lower() not in {"amazon.com", "amazon.in"}:
        return {
            "category": suffix,
            "category_source": "amazon_title_suffix",
            "category_confidence": "medium",
            "category_reason": "Amazon title suffix",
            "category_needs_review": "false",
        }

    category = regex_category(product_name)
    if category:
        return {
            "category": category,
            "category_source": "regex_rule",
            "category_confidence": "medium",
            "category_reason": "product-name regex",
            "category_needs_review": "false",
        }

    category = digital_category(row)
    if category:
        return {
            "category": category,
            "category_source": "source_default",
            "category_confidence": "medium",
            "category_reason": "digital source fields",
            "category_needs_review": "false",
        }

    marketplace = source_marketplace(row)
    if marketplace in {"panda01", "Amazon Go"}:
        return {
            "category": "Grocery & Gourmet Food",
            "category_source": "source_default",
            "category_confidence": "medium",
            "category_reason": f"{marketplace} source default",
            "category_needs_review": "false",
        }

    return {
        "category": OTHER_CATEGORY,
        "category_source": "unresolved",
        "category_confidence": "low",
        "category_reason": "no deterministic category signal",
        "category_needs_review": "true",
    }


def discover_sources(orders_folder):
    amazon_orders = orders_folder / "Your Amazon Orders"
    returns_folder = orders_folder / "Your Returns & Refunds"
    if not amazon_orders.exists():
        raise SystemExit(f"Missing expected folder: {amazon_orders}")

    exact_retail = None
    for child in amazon_orders.iterdir():
        if child.is_file() and child.name.lower() in {"orderhistory.csv", "order history.csv"}:
            exact_retail = child
            break

    if exact_retail:
        retail_path = exact_retail
    else:
        candidates = []
        for child in amazon_orders.glob("Order History *.csv"):
            name = child.name
            if re.fullmatch(r"Order History \d{4}( Updated)?\.csv", name):
                continue
            if re.search(r"\d{4}.*\d{4}", name):
                candidates.append(child)
        if len(candidates) != 1:
            listed = "\n".join(str(p) for p in candidates) or "(none)"
            raise SystemExit(f"Could not identify a single retail order-history source. Candidates:\n{listed}")
        retail_path = candidates[0]

    return {
        "retail": retail_path,
        "digital": amazon_orders / "Digital Content Orders.csv",
        "digital_returns": amazon_orders / "Digital Returns.csv",
        "refund_details": returns_folder / "Refund Details.csv",
        "returns_status": returns_folder / "Returns Status.csv",
        "return_requests": returns_folder / "Return Requests.csv",
    }


def require_columns(path, fieldnames, required):
    missing = [name for name in required if name not in fieldnames]
    if missing:
        raise SystemExit(f"{path} is missing required column(s): {', '.join(missing)}")


def normalize_row(row, source_type, source_file):
    normalized = dict(row)
    marketplace = source_marketplace(row)
    normalized["source_file"] = str(source_file)
    normalized["source_type"] = source_type
    normalized["source_order_date"] = clean_cell(row.get("Order Date"))
    normalized["source_marketplace"] = marketplace
    normalized["normalized_asin_url"] = asin_to_url(row.get("ASIN"), marketplace)
    normalized.setdefault("is_returned", "false")
    for column in CATEGORY_COLUMNS:
        normalized.setdefault(column, "")
    return normalized


def read_source_rows(path, source_type):
    if not path.exists():
        return [], []
    fieldnames, rows = read_csv(path)
    require_columns(path, fieldnames, ["ASIN", "Product Name", "Order Date"])
    return fieldnames, [normalize_row(row, source_type, path) for row in rows]


def include_year(parsed_date, start_year, end_year):
    if not parsed_date:
        return False
    if start_year is not None and parsed_date.year < start_year:
        return False
    if end_year is not None and parsed_date.year > end_year:
        return False
    return True


def build_fieldnames(source_fieldnames):
    fieldnames = []
    for name in MANAGED_COLUMNS + source_fieldnames:
        if name not in fieldnames:
            fieldnames.append(name)
    return fieldnames


def output_path_for_year(workdir, year):
    return workdir / "orders" / f"orders-{year}.csv"


def review_path_for_year(workdir, year):
    return workdir / "review" / f"orders-{year}-category-review.csv"


def last_existing_date(path):
    if not path.exists():
        return None
    _, rows = read_csv(path)
    for row in reversed(rows):
        parsed = parse_order_date(row.get("source_order_date") or row.get("Order Date"))
        if parsed:
            return parsed
    return None


def numeric_positive(value):
    text = clean_cell(value)
    if text in {"", "Not Available", "Not Applicable", "No Refund"}:
        return False
    try:
        return float(text.replace(",", "")) > 0
    except ValueError:
        return False


def successful_refund_detail(row):
    if clean_cell(row.get("Order ID")) == "":
        return False
    if clean_cell(row.get("Disbursement Type")) not in {"Refund", "Not Applicable"}:
        return False
    if clean_cell(row.get("Payment Status")) == "Completed" or clean_cell(row.get("Reversal Status")) == "Completed":
        return numeric_positive(row.get("Refund Amount")) or clean_cell(row.get("Reversal Amount State")) == "Final"
    return False


def successful_return_status(row):
    if clean_cell(row.get("Order ID")) == "":
        return False
    resolution = clean_cell(row.get("Return Resolution"))
    state = clean_cell(row.get("Return Receivable State"))
    if state in {"Cancelled", "Expired"}:
        return False
    return parse_order_date(row.get("Date of Return")) is not None and resolution in {"Refund", "Return", "Exchange"}


def successful_digital_return(row):
    if clean_cell(row.get("Order ID")) == "":
        return False
    if clean_cell(row.get("Processing Successful")).lower() == "yes":
        return True
    if clean_cell(row.get("Return Status")) == "Customer Return Complete" and numeric_positive(row.get("Amount Refunded")):
        return True
    return False


def build_return_index(sources):
    retail_orders = set()
    retail_item_keys = set()
    retail_orders_with_item_keys = set()
    digital_orders = set()
    digital_item_keys = set()
    digital_orders_with_item_keys = set()
    contributing_files = []

    refund_details = sources["refund_details"]
    if refund_details.exists():
        before = len(retail_orders)
        _, rows = read_csv(refund_details)
        for row in rows:
            if successful_refund_detail(row):
                retail_orders.add(clean_cell(row.get("Order ID")))
        if len(retail_orders) > before:
            contributing_files.append(str(refund_details))

    returns_status = sources["returns_status"]
    if returns_status.exists():
        before = len(retail_orders)
        _, rows = read_csv(returns_status)
        for row in rows:
            if successful_return_status(row):
                retail_orders.add(clean_cell(row.get("Order ID")))
        if len(retail_orders) > before:
            contributing_files.append(str(returns_status))

    return_requests = sources["return_requests"]
    if return_requests.exists():
        before = len(retail_item_keys)
        _, rows = read_csv(return_requests)
        for row in rows:
            order_id = clean_cell(row.get("Order ID"))
            asin = clean_cell(row.get("ASIN"))
            product = clean_cell(row.get("Product Name"))
            if order_id and order_id in retail_orders:
                if asin:
                    retail_item_keys.add((order_id, asin))
                    retail_orders_with_item_keys.add(order_id)
                if product:
                    retail_item_keys.add((order_id, product.lower()))
                    retail_orders_with_item_keys.add(order_id)
        if len(retail_item_keys) > before:
            contributing_files.append(str(return_requests))

    digital_returns = sources["digital_returns"]
    if digital_returns.exists():
        before = len(digital_orders)
        _, rows = read_csv(digital_returns)
        for row in rows:
            if successful_digital_return(row):
                order_id = clean_cell(row.get("Order ID"))
                asin = clean_cell(row.get("ASIN"))
                product = clean_cell(row.get("Product Name"))
                digital_orders.add(order_id)
                if asin:
                    digital_item_keys.add((order_id, asin))
                    digital_orders_with_item_keys.add(order_id)
                if product:
                    digital_item_keys.add((order_id, product.lower()))
                    digital_orders_with_item_keys.add(order_id)
        if len(digital_orders) > before:
            contributing_files.append(str(digital_returns))

    return {
        "retail_orders": retail_orders,
        "retail_item_keys": retail_item_keys,
        "retail_orders_with_item_keys": retail_orders_with_item_keys,
        "digital_orders": digital_orders,
        "digital_item_keys": digital_item_keys,
        "digital_orders_with_item_keys": digital_orders_with_item_keys,
        "contributing_files": contributing_files,
    }


def row_is_returned(row, return_index):
    order_id = clean_cell(row.get("Order ID"))
    if not order_id:
        return False
    asin = clean_cell(row.get("ASIN"))
    product = clean_cell(row.get("Product Name")).lower()
    source_type = clean_cell(row.get("source_type"))

    if source_type == "digital":
        if (order_id, asin) in return_index["digital_item_keys"] or (order_id, product) in return_index["digital_item_keys"]:
            return True
        if order_id in return_index["digital_orders_with_item_keys"]:
            return False
        return order_id in return_index["digital_orders"]

    if (order_id, asin) in return_index["retail_item_keys"] or (order_id, product) in return_index["retail_item_keys"]:
        return True
    if order_id in return_index["retail_orders_with_item_keys"]:
        return False
    return order_id in return_index["retail_orders"]


def update_existing_return_flags(path, return_index):
    if not path.exists():
        return 0
    fieldnames, rows = read_csv(path)
    if "is_returned" not in fieldnames:
        fieldnames.append("is_returned")
    changed = 0
    for row in rows:
        if not truthy(row.get("is_returned")) and row_is_returned(row, return_index):
            row["is_returned"] = "true"
            changed += 1
        elif "is_returned" not in row:
            row["is_returned"] = "false"
    if changed:
        write_csv(path, fieldnames, rows)
    return changed


def prepare_cache_for_rows(rows, cache, cache_path, workers, timeout, no_fetch):
    urls = sorted(
        {
            clean_cell(row.get("normalized_asin_url"))
            for row in rows
            if clean_cell(row.get("normalized_asin_url")).startswith(("http://", "https://"))
        }
    )
    to_fetch = [url for url in urls if url not in cache]
    print(
        f"    Amazon page cache: unique_urls={len(urls)} cached={len(urls) - len(to_fetch)} "
        f"to_fetch={0 if no_fetch else len(to_fetch)}"
    )
    if no_fetch or not to_fetch:
        return {"unique_urls": len(urls), "fetched": 0, "cached": len(urls) - len(to_fetch)}

    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(fetch_context, url, cache, timeout): url for url in to_fetch}
        for future in as_completed(futures):
            completed += 1
            future.result()
            if completed % 100 == 0 or completed == len(to_fetch):
                save_json(cache_path, cache)
                print(f"fetched {completed}/{len(to_fetch)} Amazon pages")
    save_json(cache_path, cache)
    return {"unique_urls": len(urls), "fetched": len(to_fetch), "cached": len(urls) - len(to_fetch)}


def categorize_rows(rows, cache, overrides):
    for row in rows:
        result = infer_category(row, cache, overrides)
        row.update(result)


def review_rows_for_year(year, rows):
    review_rows = []
    for row in rows:
        if row.get("category_needs_review") != "true":
            continue
        review_rows.append(
            {
                "year": str(year),
                "order_date": clean_cell(row.get("source_order_date") or row.get("Order Date")),
                "source_type": clean_cell(row.get("source_type")),
                "asin": clean_cell(row.get("ASIN")),
                "url": clean_cell(row.get("normalized_asin_url")),
                "product_name": clean_cell(row.get("Product Name")),
                "website_or_marketplace": source_marketplace(row),
                "proposed_category": clean_cell(row.get("category")),
                "reason": clean_cell(row.get("category_reason")),
                "resolved_category": "",
                "resolution_source": "",
                "notes": "",
            }
        )
    return review_rows


def write_review_file(path, rows):
    fieldnames = [
        "year",
        "order_date",
        "source_type",
        "asin",
        "url",
        "product_name",
        "website_or_marketplace",
        "proposed_category",
        "reason",
        "resolved_category",
        "resolution_source",
        "notes",
    ]
    if rows:
        write_csv(path, fieldnames, rows)
    elif path.exists():
        path.unlink()


def ensure_workdir(workdir):
    for child in ["orders", "review", "logs"]:
        (workdir / child).mkdir(parents=True, exist_ok=True)


def collect_rows_by_year(rows, start_year, end_year):
    by_year = defaultdict(list)
    invalid = 0
    for row in rows:
        parsed = parse_order_date(row.get("source_order_date"))
        if not parsed:
            invalid += 1
            continue
        if include_year(parsed, start_year, end_year):
            by_year[parsed.year].append(row)
    for year in by_year:
        by_year[year].sort(key=date_sort_key)
    return by_year, invalid


def read_existing_fieldnames(path, fallback):
    if not path.exists():
        return fallback
    fieldnames, _ = read_csv(path)
    return fieldnames or fallback


def process_year(year, source_rows, fieldnames, workdir, cache, cache_path, overrides, return_index, args):
    output_path = output_path_for_year(workdir, year)
    previous_last_date = last_existing_date(output_path)
    print(f"  Year {year}: source_rows={len(source_rows)}")
    if previous_last_date:
        print(f"    existing output found: {output_path}")
        print(f"    last existing order date: {previous_last_date.isoformat()}")
    else:
        print(f"    no existing annual output; creating {output_path}")

    print("    updating existing is_returned flags if needed")
    return_updates = update_existing_return_flags(output_path, return_index)

    if previous_last_date:
        new_rows = [
            row
            for row in source_rows
            if (parse_order_date(row.get("source_order_date")) or dt.date.min) > previous_last_date
        ]
    else:
        new_rows = list(source_rows)

    new_rows.sort(key=date_sort_key)
    print(f"    new rows to categorize/append: {len(new_rows)}")
    for row in new_rows:
        row["is_returned"] = "true" if row_is_returned(row, return_index) else "false"
    print(f"    new rows marked returned: {sum(1 for row in new_rows if truthy(row.get('is_returned')))}")

    print("    fetching/reusing Amazon category context")
    cache_stats = prepare_cache_for_rows(new_rows, cache, cache_path, args.workers, args.timeout, args.no_fetch)
    print("    applying deterministic category rules")
    categorize_rows(new_rows, cache, overrides)
    unresolved_before_ai = sum(1 for row in new_rows if row.get("category_needs_review") == "true")
    print(f"    unresolved after deterministic rules: {unresolved_before_ai}")
    if unresolved_before_ai:
        print("    unresolved rows will be written to review CSV")

    review_rows = review_rows_for_year(year, new_rows)
    print(f"    writing review rows: {len(review_rows)}")
    write_review_file(review_path_for_year(workdir, year), review_rows)

    output_fieldnames = read_existing_fieldnames(output_path, fieldnames)
    if output_path.exists():
        print(f"    appending annual CSV rows: {len(new_rows)}")
        append_csv(output_path, output_fieldnames, new_rows)
    else:
        print(f"    writing annual CSV rows: {len(new_rows)}")
        write_csv(output_path, output_fieldnames, new_rows)

    return {
        "rows_added": len(new_rows),
        "returned_rows_added": sum(1 for row in new_rows if truthy(row.get("is_returned"))),
        "return_flags_updated": return_updates,
        "ambiguous_rows": len(review_rows),
        **cache_stats,
    }


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Build append-only annual categorized CSVs from an Amazon 'Your Orders' export folder.\n\n"
            "The input is the top-level 'Your Orders' folder from an Amazon data export, not an\n"
            "individual CSV. The script discovers retail orders, digital orders, returns/refunds,\n"
            "and digital returns under that folder.\n\n"
            "Outputs are written under the work directory, defaulting to:\n"
            f"  {DEFAULT_WORKDIR}/\n\n"
            "Important generated files:\n"
            "  orders/orders-YYYY.csv                 annual retail+digital categorized CSVs\n"
            "  amazon-category-cache-shared.json      cached Amazon page title/breadcrumb signals\n"
            "  category-overrides.csv                 durable manual/Codex skill category decisions\n"
            "  review/orders-YYYY-category-review.csv unresolved rows for Codex/manual review\n"
            "  logs/run-summary-YYYYMMDD-HHMMSS.json  run summary and counts\n\n"
            "The pipeline is append-only for order rows. Existing rows are not recategorized.\n"
            "The only existing-field update allowed is changing is_returned from blank/false to true\n"
            "when a later export reports a successful return."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  Full deterministic run:\n"
            "    python3 scripts/amazon_order_category_pipeline.py \"$HOME/Downloads/Your Orders\"\n\n"
            "  Process only 2025 and 2026:\n"
            "    python3 scripts/amazon_order_category_pipeline.py \"$HOME/Downloads/Your Orders\" --start-year 2025 --end-year 2026\n\n"
            "  Fast structural run without fetching Amazon product pages:\n"
            "    python3 scripts/amazon_order_category_pipeline.py \"$HOME/Downloads/Your Orders\" --no-fetch\n"
        ),
    )
    parser.add_argument(
        "orders_folder",
        type=Path,
        help=(
            "Top-level Amazon export folder named 'Your Orders'. Expected subfolders include "
            "'Your Amazon Orders' and, when present, 'Your Returns & Refunds'."
        ),
    )
    parser.add_argument(
        "--start-year",
        type=int,
        help="First order year to process, inclusive. If omitted, processing starts at the earliest year in the export.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        help="Last order year to process, inclusive. If omitted, processing continues through the latest year in the export.",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path(DEFAULT_WORKDIR),
        help=(
            f"Directory for all generated outputs, caches, overrides, review files, and logs. "
            f"Default: {DEFAULT_WORKDIR}"
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help=(
            "Number of Amazon product pages to fetch in parallel when breadcrumbs are missing from the cache. "
            "Higher values can be faster but may increase throttling risk. Default: 6"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=18,
        help=(
            "Maximum seconds to wait for each individual Amazon product-page fetch. Default: 18"
        ),
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help=(
            "Do not fetch missing Amazon product pages. Use existing cache entries and deterministic product-name "
            "fallback rules only."
        ),
    )
    return parser


def main():
    args = build_argument_parser().parse_args()
    orders_folder = args.orders_folder
    print("Amazon order categorization pipeline")
    print(f"current working directory: {Path.cwd()}")
    print(f"input folder: {orders_folder}")
    if not orders_folder.exists() or not orders_folder.is_dir():
        raise SystemExit(f"Input must be an Amazon 'Your Orders' folder: {orders_folder}")
    if args.start_year and args.end_year and args.start_year > args.end_year:
        raise SystemExit("--start-year cannot be greater than --end-year")

    workdir = args.workdir
    print(f"work directory: {workdir}")
    print("creating/reusing work directory structure")
    ensure_workdir(workdir)
    cache_path = workdir / "amazon-category-cache-shared.json"
    overrides_path = workdir / "category-overrides.csv"

    print("loading reusable state")
    cache = load_json(cache_path, {})
    cache_entries_before = len(cache)
    overrides = load_overrides(overrides_path)
    override_count = sum(len(values) for values in overrides.values())
    print(f"  cache: {cache_path} entries={cache_entries_before}")
    print(f"  overrides: {overrides_path} entries={override_count}")

    print("discovering source files")
    sources = discover_sources(orders_folder)
    print(f"  retail orders: {sources['retail']}")
    print(f"  digital orders: {sources['digital'] if sources['digital'].exists() else '(missing)'}")

    print("reading retail and digital rows")
    retail_fieldnames, retail_rows = read_source_rows(sources["retail"], "retail")
    digital_fieldnames, digital_rows = read_source_rows(sources["digital"], "digital") if sources["digital"].exists() else ([], [])
    print(f"  retail rows: {len(retail_rows)}")
    print(f"  digital rows: {len(digital_rows)}")

    source_fieldnames = []
    for name in retail_fieldnames + digital_fieldnames:
        if name not in source_fieldnames and name not in MANAGED_COLUMNS:
            source_fieldnames.append(name)
    output_fieldnames = build_fieldnames(source_fieldnames)

    all_rows = retail_rows + digital_rows
    print("grouping rows by order year")
    rows_by_year, invalid_date_rows = collect_rows_by_year(all_rows, args.start_year, args.end_year)
    print(f"  valid dated rows: {len(all_rows) - invalid_date_rows}")
    print(f"  invalid dated rows skipped: {invalid_date_rows}")
    print(f"  years to process: {sorted(rows_by_year)}")

    print("building return/refund index")
    return_index = build_return_index(sources)
    print(f"  return source files contributing matches: {len(return_index['contributing_files'])}")
    for path in return_index["contributing_files"]:
        print(f"    {path}")
    print(f"  returned retail order ids: {len(return_index['retail_orders'])}")
    print(f"  returned digital order ids: {len(return_index['digital_orders'])}")

    yearly_stats = {}
    for year in sorted(rows_by_year):
        yearly_stats[str(year)] = process_year(
            year,
            rows_by_year[year],
            output_fieldnames,
            workdir,
            cache,
            cache_path,
            overrides,
            return_index,
            args,
        )
        overrides = load_overrides(overrides_path)

    save_json(cache_path, cache)
    summary = {
        "source_folder": str(orders_folder),
        "retail_source_file": str(sources["retail"]),
        "digital_source_file": str(sources["digital"]) if sources["digital"].exists() else "",
        "return_source_files": return_index["contributing_files"],
        "workdir": str(workdir),
        "start_year": args.start_year,
        "end_year": args.end_year,
        "retail_rows_read": len(retail_rows),
        "digital_rows_read": len(digital_rows),
        "rows_with_valid_order_date": len(all_rows) - invalid_date_rows,
        "invalid_date_rows": invalid_date_rows,
        "years_seen": sorted({parse_order_date(row.get("source_order_date")).year for row in all_rows if parse_order_date(row.get("source_order_date"))}),
        "years_processed": sorted(rows_by_year),
        "yearly_stats": yearly_stats,
        "ambiguous_rows": sum(stats["ambiguous_rows"] for stats in yearly_stats.values()),
        "returned_rows_marked": sum(stats["returned_rows_added"] for stats in yearly_stats.values()),
        "return_flags_updated": sum(stats["return_flags_updated"] for stats in yearly_stats.values()),
        "cache_entries_before": cache_entries_before,
        "cache_entries_after": len(cache),
    }
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    summary_path = workdir / "logs" / f"run-summary-{timestamp}.json"
    print("writing run summary")
    save_json(summary_path, summary)

    print("complete")
    print(f"workdir={workdir}")
    print(f"years_processed={summary['years_processed']}")
    print(f"rows_added={sum(stats['rows_added'] for stats in yearly_stats.values())}")
    print(f"ambiguous_rows={summary['ambiguous_rows']}")
    print(f"returned_rows_marked={summary['returned_rows_marked']}")
    print(f"return_flags_updated={summary['return_flags_updated']}")
    print(f"summary={summary_path}")


if __name__ == "__main__":
    main()

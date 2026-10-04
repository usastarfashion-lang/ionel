#!/usr/bin/env python3
"""Generate a Google Merchant Center supplemental feed for USASTARFASHION.

Reads the public Shopify storefront product JSON and writes a CSV that can be
uploaded in Merchant Center → Products → Supplemental feeds.

This targets the common Shopping / free-listings failures for personalised
apparel stores:
  - missing GTIN / identifier_exists
  - personalised variants needing custom-product treatment
  - weak brand / MPN / color / size attributes
  - digital downloads that should be excluded from Shopping

Item IDs match the Shopify Google & YouTube channel format:
  shopify_{COUNTRY}_{SHOP_ID}_{VARIANT_ID}
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DEFAULT_STORE = "https://www.usastarfashion.com"
DEFAULT_SHOP_ID = "81835753803"
DEFAULT_COUNTRY = "GB"
DEFAULT_LANGUAGE = "en"
DEFAULT_CURRENCY = "GBP"

UA = {
    "User-Agent": "USAF-MerchantFeed/1.0 (+https://www.usastarfashion.com)",
    "Accept": "application/json",
}

# High-level Google product categories for apparel / accessories.
TYPE_TO_GOOGLE_CATEGORY = {
    "caps": "Apparel & Accessories > Clothing Accessories > Hats",
    "trucker caps": "Apparel & Accessories > Clothing Accessories > Hats",
    "beanies": "Apparel & Accessories > Clothing Accessories > Hats",
    "bucket hats": "Apparel & Accessories > Clothing Accessories > Hats",
    "patches": "Apparel & Accessories > Clothing Accessories > Patches",
    "t-shirts": "Apparel & Accessories > Clothing > Shirts & Tops",
    "kids t-shirts": "Apparel & Accessories > Clothing > Shirts & Tops",
    "polo shirts": "Apparel & Accessories > Clothing > Shirts & Tops",
    "hoodies": "Apparel & Accessories > Clothing > Shirts & Tops",
    "sweatshirts": "Apparel & Accessories > Clothing > Shirts & Tops",
    "jackets & gilets": "Apparel & Accessories > Clothing > Outerwear",
    "jackets & fleeces": "Apparel & Accessories > Clothing > Outerwear",
    "aprons": "Apparel & Accessories > Clothing Accessories",
    "tote bags": "Apparel & Accessories > Handbags, Wallets & Cases > Shopping Totes",
    "bags": "Apparel & Accessories > Handbags, Wallets & Cases",
    "bags & backpacks": "Apparel & Accessories > Handbags, Wallets & Cases",
    "baby clothing": "Apparel & Accessories > Clothing",
    "kids & baby": "Apparel & Accessories > Clothing",
    "workwear & safety": "Apparel & Accessories > Clothing > Outerwear",
    "digital designs": "Media > Product Manuals",
}

PERSONALISATION_TOKENS = (
    "personal",
    "custom",
    "embroider",
    "dtf",
    "printlab",
    "logo",
)

DIGITAL_TOKENS = (
    "digital designs",
    "digital download",
    "png pack",
    "halftone design pack",
)

COLOR_OPTION_NAMES = {"color", "colour", "colors", "colours"}
SIZE_OPTION_NAMES = {"size", "sizes", "fit"}
DECORATION_OPTION_NAMES = {
    "decoration",
    "decoration type",
    "personalisation",
    "personalization",
    "personalisation type",
    "personalization type",
    "print type",
    "finish",
}


def fetch_json(url: str, retries: int = 4) -> Any:
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as err:
            last_err = err
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def iter_products(store: str, page_size: int = 250) -> Iterable[Dict[str, Any]]:
    page = 1
    while True:
        url = f"{store.rstrip('/')}/products.json?limit={page_size}&page={page}"
        payload = fetch_json(url)
        products = payload.get("products") or []
        if not products:
            break
        for product in products:
            yield product
        if len(products) < page_size:
            break
        page += 1
        time.sleep(0.2)


def option_map(product: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    options = product.get("options") or []
    for idx, option in enumerate(options, start=1):
        name = str(option.get("name") or "").strip()
        value = variant.get(f"option{idx}")
        if name and value not in (None, "", "Default Title"):
            mapping[name] = str(value)
    return mapping


def pick_option(options: Dict[str, str], names: set[str]) -> str:
    for key, value in options.items():
        if key.strip().lower() in names:
            return value
    return ""


def _tags_text(product: Dict[str, Any]) -> str:
    tags = product.get("tags") or []
    if isinstance(tags, list):
        return " ".join(str(t) for t in tags).lower()
    return str(tags).lower()


def _decoration_value(options: Dict[str, str]) -> str:
    """Prefer explicit personalisation options; ignore colour names like 'Leopard Print'."""
    preferred = {
        "personalisation type",
        "personalization type",
        "decoration",
        "decoration type",
        "print type",
        "finish",
    }
    for key, value in options.items():
        if key.strip().lower() in preferred or key.strip().lower() in DECORATION_OPTION_NAMES:
            return str(value).strip()
    return ""


def is_personalised(product: Dict[str, Any], variant: Dict[str, Any], options: Dict[str, str]) -> bool:
    """Return True when this offer is a decorated / custom Shopping item."""
    decoration = _decoration_value(options).lower()
    parts = [p.strip() for p in str(variant.get("title") or "").lower().split("/")]
    last_part = parts[-1] if parts else ""

    if decoration in {"blank", "none", "undecorated", "no personalisation", "no personalization"}:
        return False
    if last_part == "blank":
        return False

    decorated_markers = ("dtf", "embroid", "personal", "custom dtf", "custom embroid")
    if decoration:
        if any(marker in decoration for marker in decorated_markers) or decoration.endswith("print"):
            # 'DTF Print' / 'Embroidery' etc. — not fabric names.
            if decoration not in {"leopard print", "animal print"}:
                return True

    tag_text = _tags_text(product)
    title = str(product.get("title") or "").lower()
    handle = str(product.get("handle") or "").lower()
    product_blob = f"{title} {handle} {tag_text}"

    # Explicitly personalised products.
    if any(token in product_blob for token in ("personalised", "personalized", "printlab")):
        if decoration and decoration not in {"blank", "none", "undecorated"}:
            return True
        # No blank/decorated option split — every offer is a custom product.
        if not decoration:
            return True
    return False


def is_digital(product: Dict[str, Any]) -> bool:
    blob = " ".join(
        [
            str(product.get("title") or ""),
            str(product.get("product_type") or ""),
            str(product.get("handle") or ""),
            strip_html(str(product.get("body_html") or ""))[:400],
        ]
    ).lower()
    if any(token in blob for token in DIGITAL_TOKENS):
        return True
    # Shopify digital products usually do not require shipping.
    variants = product.get("variants") or []
    if variants and all(not v.get("requires_shipping", True) for v in variants):
        return True
    return False


def google_category(product: Dict[str, Any]) -> str:
    ptype = str(product.get("product_type") or "").strip().lower()
    if ptype in TYPE_TO_GOOGLE_CATEGORY:
        return TYPE_TO_GOOGLE_CATEGORY[ptype]
    for key, value in TYPE_TO_GOOGLE_CATEGORY.items():
        if key in ptype:
            return value
    return "Apparel & Accessories"


def brand_for(product: Dict[str, Any]) -> str:
    vendor = str(product.get("vendor") or "").strip()
    if vendor and vendor.upper() not in {"USASTARFASHION", "USA STAR FASHION"}:
        return vendor
    return "USASTARFASHION"


def mpn_for(product: Dict[str, Any], variant: Dict[str, Any]) -> str:
    sku = str(variant.get("sku") or "").strip()
    if sku:
        return sku
    handle = str(product.get("handle") or "").strip()
    vid = variant.get("id")
    if handle and vid:
        return f"{handle}-{vid}"
    return str(vid or "")


def shopping_title(product: Dict[str, Any], variant: Dict[str, Any], personalised: bool) -> str:
    title = str(product.get("title") or "").strip()
    # Remove internal duplicate markers that hurt Shopping quality.
    title = re.sub(r"\s*\(Copy\)(?:\s*\(Copy\))*", "", title, flags=re.I).strip()
    title = re.sub(r"\s+", " ", title)
    options = option_map(product, variant)
    color = pick_option(options, COLOR_OPTION_NAMES)
    size = pick_option(options, SIZE_OPTION_NAMES)
    decoration = pick_option(options, DECORATION_OPTION_NAMES)

    bits = [title]
    if color:
        bits.append(color)
    if size and size.lower() not in {"one size", "o/s", "os"}:
        bits.append(size)
    if decoration and decoration.lower() not in {"blank", "default title"}:
        bits.append(decoration)

    out = " – ".join(bits)
    if personalised and not re.search(r"\b(personalised|personalized|custom)\b", out, re.I):
        out = f"Personalised {out}"
    out = re.sub(r"\bPersonalised\s+Personalised\b", "Personalised", out, flags=re.I)
    # Google title soft limit guidance ~150 chars.
    return out[:150].rstrip(" –-")


def item_id(shop_id: str, country: str, variant_id: Any) -> str:
    return f"shopify_{country}_{shop_id}_{variant_id}"


def build_rows(
    products: Iterable[Dict[str, Any]],
    shop_id: str,
    country: str,
    exclude_digital: bool = True,
) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    rows: List[Dict[str, str]] = []
    stats = {
        "products": 0,
        "variants": 0,
        "personalised": 0,
        "digital_excluded": 0,
        "identifier_exists_false": 0,
        "missing_sku": 0,
    }

    for product in products:
        stats["products"] += 1
        digital = is_digital(product)
        if digital and exclude_digital:
            stats["digital_excluded"] += len(product.get("variants") or [])
            continue

        for variant in product.get("variants") or []:
            stats["variants"] += 1
            options = option_map(product, variant)
            personalised = is_personalised(product, variant, options)
            if personalised:
                stats["personalised"] += 1

            sku = str(variant.get("sku") or "").strip()
            barcode = str(variant.get("barcode") or "").strip()
            if not sku:
                stats["missing_sku"] += 1

            # Personalised / no barcode → tell Google identifiers do not exist.
            # Branded blanks with SKU still get brand + mpn for matching help.
            identifier_exists = "no"
            if barcode and not personalised:
                identifier_exists = "yes"
            if identifier_exists == "no":
                stats["identifier_exists_false"] += 1

            availability = "in_stock"
            if variant.get("available") is False:
                availability = "out_of_stock"

            row = {
                "id": item_id(shop_id, country, variant.get("id")),
                "item_group_id": str(product.get("id") or ""),
                "title": shopping_title(product, variant, personalised),
                "brand": brand_for(product),
                "mpn": mpn_for(product, variant),
                "gtin": barcode,
                "identifier_exists": identifier_exists,
                "condition": "new",
                "gender": "unisex",
                "age_group": "adult",
                "color": pick_option(options, COLOR_OPTION_NAMES),
                "size": pick_option(options, SIZE_OPTION_NAMES),
                "google_product_category": google_category(product),
                "product_type": str(product.get("product_type") or ""),
                "custom_label_0": "personalised" if personalised else "blank_catalogue",
                "custom_label_1": "digital" if digital else "physical",
                "is_bundle": "yes" if personalised else "no",
                "ships_from_country": country,
                "link": f"{DEFAULT_STORE}/products/{product.get('handle')}?variant={variant.get('id')}",
                "price": f"{variant.get('price')} {DEFAULT_CURRENCY}",
                "availability": availability,
                "canonical_link": f"{DEFAULT_STORE}/products/{product.get('handle')}",
            }
            rows.append(row)
    return rows, stats


FIELDNAMES = [
    "id",
    "item_group_id",
    "title",
    "brand",
    "mpn",
    "gtin",
    "identifier_exists",
    "condition",
    "gender",
    "age_group",
    "color",
    "size",
    "google_product_category",
    "product_type",
    "custom_label_0",
    "custom_label_1",
    "is_bundle",
    "ships_from_country",
    "link",
    "price",
    "availability",
    "canonical_link",
]


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, stats: Dict[str, int], sample_issues: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Merchant supplemental feed report",
        "",
        f"- Products scanned: {stats['products']}",
        f"- Variants written: {stats['variants']}",
        f"- Personalised variants: {stats['personalised']}",
        f"- Digital variants excluded: {stats['digital_excluded']}",
        f"- identifier_exists=no: {stats['identifier_exists_false']}",
        f"- Variants missing SKU: {stats['missing_sku']}",
        "",
        "## Next steps in Google Merchant Center",
        "",
        "1. Products → Supplemental feeds → Add supplemental feed → Upload CSV.",
        "2. Join on `id` (already in Shopify Google & YouTube format).",
        "3. In Shopify → Sales channels → Google & YouTube → manage products,",
        "   set **Custom product = True** for personalised / Printlab items.",
        "4. Request a review after the feed processes (often a few hours).",
        "",
        "## Sample issues observed",
        "",
    ]
    lines.extend(f"- {item}" for item in sample_issues or ["None"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--shop-id", default=DEFAULT_SHOP_ID)
    parser.add_argument("--country", default=DEFAULT_COUNTRY)
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "feeds" / "merchant_supplemental_feed.csv"),
    )
    parser.add_argument(
        "--report",
        default=str(Path(__file__).resolve().parents[1] / "feeds" / "merchant_feed_report.md"),
    )
    parser.add_argument("--include-digital", action="store_true")
    parser.add_argument("--limit-products", type=int, default=0, help="0 = all products")
    args = parser.parse_args(argv)

    products: List[Dict[str, Any]] = []
    for product in iter_products(args.store):
        products.append(product)
        if args.limit_products and len(products) >= args.limit_products:
            break

    rows, stats = build_rows(
        products,
        shop_id=args.shop_id,
        country=args.country,
        exclude_digital=not args.include_digital,
    )

    sample_issues: List[str] = []
    for product in products:
        handle = str(product.get("handle") or "")
        if "copy" in handle.lower():
            sample_issues.append(f"Rename duplicate handle/title: {handle}")
        if any(not (variant.get("sku") or "").strip() for variant in product.get("variants") or []):
            sample_issues.append(f"Missing SKU on one or more variants: {handle or product.get('id')}")
    # Keep the report short but useful.
    sample_issues = sample_issues[:25]
    if stats["missing_sku"]:
        sample_issues.insert(0, f"{stats['missing_sku']} variants are missing SKUs")
    copy_handles = sum(1 for product in products if "copy" in str(product.get("handle") or "").lower())
    if copy_handles:
        sample_issues.insert(0, f"{copy_handles} products still use a -copy handle")

    out_path = Path(args.out)
    report_path = Path(args.report)
    write_csv(out_path, rows)
    write_report(report_path, stats, sample_issues)

    print(json.dumps({"out": str(out_path), "report": str(report_path), **stats}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

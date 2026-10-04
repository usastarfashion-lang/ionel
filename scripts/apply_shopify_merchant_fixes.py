#!/usr/bin/env python3
"""Apply Shopify-side Google Merchant Shopping fixes via Admin API.

Requires a custom app Admin API token (does NOT use a staff seat):

  export SHOPIFY_SHOP=4ec0cc-d5.myshopify.com
  export SHOPIFY_ADMIN_TOKEN=shpat_...
  python3 scripts/apply_shopify_merchant_fixes.py

What it does:
  1) Sets mm-google-shopping.custom_product=true on personalised / Printlab products
  2) Sets mm-google-shopping.condition=new on variants missing it
  3) Fills blank variant SKUs from a stable generated value
  4) Reports remaining -copy handles for manual rename
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

SHOP = os.environ.get("SHOPIFY_SHOP", "4ec0cc-d5.myshopify.com").strip()
TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN", "").strip()
CLIENT_ID = os.environ.get("SHOPIFY_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "").strip()
API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2025-01").strip()
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in {"1", "true", "yes"}


def request_client_credentials_token() -> str:
    """Dev Dashboard apps: exchange client id/secret for a short-lived Admin token."""
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://{SHOP}/admin/oauth/access_token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")
        die(f"Token exchange HTTP {err.code}: {detail}")
    token = payload.get("access_token")
    if not token:
        die(f"No access_token in response: {payload}")
    print(f"Got client-credentials token; scopes={payload.get('scope')}")
    return token


def ensure_token() -> str:
    global TOKEN
    if TOKEN:
        return TOKEN
    if CLIENT_ID and CLIENT_SECRET:
        TOKEN = request_client_credentials_token()
        return TOKEN
    die(
        "Missing Shopify credentials.\n"
        "Dev Dashboard path:\n"
        "  1) Settings → Apps → Develop apps → Build apps in Dev Dashboard\n"
        "  2) Create app, set read_products + write_products, install on store\n"
        "  3) Copy Client ID + Client secret\n"
        "  4) export SHOPIFY_CLIENT_ID=... SHOPIFY_CLIENT_SECRET=...\n"
        "Or set SHOPIFY_ADMIN_TOKEN if you already have an access token."
    )
    return ""

PERSONAL_RE = re.compile(
    r"personalised|personalized|printlab|custom product|blank or personalised",
    re.I,
)


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def admin_graphql(query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    token = ensure_token()
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")
        die(f"Shopify API HTTP {err.code}: {detail}")
    if payload.get("errors"):
        die(f"Shopify GraphQL errors: {json.dumps(payload['errors'], indent=2)}")
    return payload["data"]


def iter_products() -> List[Dict[str, Any]]:
    products: List[Dict[str, Any]] = []
    cursor = None
    query = """
    query Products($cursor: String) {
      products(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          title
          handle
          tags
          status
          metafield(namespace: "mm-google-shopping", key: "custom_product") {
            value
          }
          variants(first: 100) {
            nodes {
              id
              sku
              title
              metafield(namespace: "mm-google-shopping", key: "condition") {
                value
              }
            }
          }
        }
      }
    }
    """
    while True:
        data = admin_graphql(query, {"cursor": cursor})
        conn = data["products"]
        products.extend(conn["nodes"])
        if not conn["pageInfo"]["hasNextPage"]:
            break
        cursor = conn["pageInfo"]["endCursor"]
        time.sleep(0.25)
    return products


def is_personalised(product: Dict[str, Any]) -> bool:
    blob = " ".join(
        [
            str(product.get("title") or ""),
            str(product.get("handle") or ""),
            " ".join(product.get("tags") or []),
        ]
    )
    return bool(PERSONAL_RE.search(blob))


def metafields_set(items: List[Dict[str, str]]) -> None:
    if not items:
        return
    if DRY_RUN:
        print(f"DRY_RUN metafieldsSet x{len(items)}")
        return
    mutation = """
    mutation Set($metafields: [MetafieldsSetInput!]!) {
      metafieldsSet(metafields: $metafields) {
        userErrors { field message code }
      }
    }
    """
    # API max 25 per call
    for i in range(0, len(items), 25):
        chunk = items[i : i + 25]
        data = admin_graphql(mutation, {"metafields": chunk})
        errors = data["metafieldsSet"]["userErrors"]
        if errors:
            die(f"metafieldsSet errors: {json.dumps(errors, indent=2)}")
        time.sleep(0.2)


def product_variants_bulk_update(product_id: str, variants: List[Dict[str, str]]) -> None:
    if not variants:
        return
    if DRY_RUN:
        print(f"DRY_RUN variant sku updates for {product_id}: {len(variants)}")
        return
    mutation = """
    mutation VariantBulk($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
      productVariantsBulkUpdate(productId: $productId, variants: $variants) {
        userErrors { field message }
      }
    }
    """
    for i in range(0, len(variants), 100):
        chunk = variants[i : i + 100]
        data = admin_graphql(mutation, {"productId": product_id, "variants": chunk})
        errors = data["productVariantsBulkUpdate"]["userErrors"]
        if errors:
            die(f"productVariantsBulkUpdate errors: {json.dumps(errors, indent=2)}")
        time.sleep(0.25)


def stable_sku(product: Dict[str, Any], variant: Dict[str, Any]) -> str:
    handle = re.sub(r"[^a-zA-Z0-9]+", "-", str(product.get("handle") or "item")).strip("-").upper()
    vid = str(variant.get("id") or "").rsplit("/", 1)[-1]
    title = re.sub(r"[^a-zA-Z0-9]+", "-", str(variant.get("title") or "DEFAULT")).strip("-").upper()
    sku = f"USAF-{handle[:40]}-{title[:40]}-{vid[-6:]}"
    return sku[:64]


def main() -> int:
    print(f"Shop={SHOP} dry_run={DRY_RUN}")
    products = iter_products()
    print(f"Loaded {len(products)} products")

    custom_metafields: List[Dict[str, str]] = []
    condition_metafields: List[Dict[str, str]] = []
    sku_updates: List[Tuple[str, List[Dict[str, str]]]] = []
    copy_handles: List[str] = []

    personalised_count = 0
    already_custom = 0
    missing_sku = 0

    for product in products:
        handle = product.get("handle") or ""
        if "copy" in handle.lower():
            copy_handles.append(handle)

        personalised = is_personalised(product)
        if personalised:
            personalised_count += 1
            current = ((product.get("metafield") or {}) or {}).get("value")
            if str(current).lower() in {"true", "1"}:
                already_custom += 1
            else:
                custom_metafields.append(
                    {
                        "ownerId": product["id"],
                        "namespace": "mm-google-shopping",
                        "key": "custom_product",
                        "type": "boolean",
                        "value": "true",
                    }
                )

        variant_sku_inputs: List[Dict[str, str]] = []
        for variant in (product.get("variants") or {}).get("nodes") or []:
            cond = ((variant.get("metafield") or {}) or {}).get("value")
            if not cond:
                condition_metafields.append(
                    {
                        "ownerId": variant["id"],
                        "namespace": "mm-google-shopping",
                        "key": "condition",
                        "type": "single_line_text_field",
                        "value": "new",
                    }
                )
            if not (variant.get("sku") or "").strip():
                missing_sku += 1
                variant_sku_inputs.append({"id": variant["id"], "sku": stable_sku(product, variant)})
        if variant_sku_inputs:
            sku_updates.append((product["id"], variant_sku_inputs))

    print(
        json.dumps(
            {
                "personalised_products": personalised_count,
                "already_custom_product_true": already_custom,
                "custom_product_to_set": len(custom_metafields),
                "condition_to_set": len(condition_metafields),
                "variants_missing_sku": missing_sku,
                "copy_handles": copy_handles,
            },
            indent=2,
        )
    )

    metafields_set(custom_metafields)
    metafields_set(condition_metafields)
    for product_id, variants in sku_updates:
        product_variants_bulk_update(product_id, variants)

    print("Done." if not DRY_RUN else "Dry run complete — set SHOPIFY_ADMIN_TOKEN and rerun without DRY_RUN=1.")
    print(
        "Merchant Center feed rule still needed in your Google account: "
        "Products → Feeds → Feed rules → Identifier exists = no"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

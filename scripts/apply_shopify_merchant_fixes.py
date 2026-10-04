#!/usr/bin/env python3
"""Apply Shopify-side Google Merchant Shopping fixes via Admin API.

Auth (Dev Dashboard app installed on the store):

  export SHOPIFY_SHOP=4ec0cc-d5.myshopify.com
  export SHOPIFY_CLIENT_ID=...
  export SHOPIFY_CLIENT_SECRET=...
  # or: export SHOPIFY_ADMIN_TOKEN=shpat_...
  python3 -u scripts/apply_shopify_merchant_fixes.py
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

PERSONAL_RE = re.compile(
    r"personalised|personalized|printlab|custom product|blank or personalised|\bbtc\b",
    re.I,
)


def log(msg: str) -> None:
    print(msg, flush=True)


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr, flush=True)
    raise SystemExit(code)


def request_client_credentials_token() -> str:
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
    log(f"Got client-credentials token; scopes={payload.get('scope')}")
    return token


def ensure_token() -> str:
    global TOKEN
    if TOKEN:
        return TOKEN
    if CLIENT_ID and CLIENT_SECRET:
        TOKEN = request_client_credentials_token()
        return TOKEN
    die("Missing SHOPIFY_ADMIN_TOKEN or SHOPIFY_CLIENT_ID/SHOPIFY_CLIENT_SECRET")
    return ""


def admin_request(method: str, path: str, payload: Optional[Dict[str, Any]] = None, retries: int = 6) -> Any:
    token = ensure_token()
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    url = f"https://{SHOP}/admin/api/{API_VERSION}{path}"
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": token,
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")
            if err.code in {429, 500, 502, 503, 504} and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                last_err = err
                continue
            die(f"Shopify HTTP {err.code} {path}: {detail[:500]}")
        except Exception as err:  # noqa: BLE001
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                last_err = err
                continue
            die(f"Shopify request failed {path}: {err}")
    die(f"Shopify request failed after retries: {last_err}")
    return {}


def admin_graphql(query: str, variables: Optional[Dict[str, Any]] = None, retries: int = 6) -> Dict[str, Any]:
    token = ensure_token()
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    for attempt in range(retries):
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
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")
            if err.code in {429, 500, 502, 503, 504} and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            die(f"Shopify GraphQL HTTP {err.code}: {detail[:500]}")
        if payload.get("errors"):
            msg = json.dumps(payload["errors"])
            if "Throttled" in msg and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            die(f"Shopify GraphQL errors: {json.dumps(payload['errors'], indent=2)}")
        return payload["data"]
    die("Shopify GraphQL failed after retries")
    return {}


def iter_products_rest() -> List[Dict[str, Any]]:
    products: List[Dict[str, Any]] = []
    since_id = 0
    page = 0
    while True:
        page += 1
        path = (
            f"/products.json?limit=250&since_id={since_id}"
            "&fields=id,title,handle,tags,variants"
        )
        payload = admin_request("GET", path)
        batch = payload.get("products") or []
        if not batch:
            break
        products.extend(batch)
        since_id = batch[-1]["id"]
        log(f"REST products page {page}: +{len(batch)} (total {len(products)})")
        time.sleep(0.2)
        if len(batch) < 250:
            break
    return products


def is_personalised(product: Dict[str, Any]) -> bool:
    tags = product.get("tags") or ""
    if isinstance(tags, list):
        tags = ",".join(tags)
    blob = " ".join([str(product.get("title") or ""), str(product.get("handle") or ""), str(tags)])
    return bool(PERSONAL_RE.search(blob))


def metafields_set(items: List[Dict[str, str]]) -> None:
    if not items:
        return
    if DRY_RUN:
        log(f"DRY_RUN metafieldsSet x{len(items)}")
        return
    mutation = """
    mutation Set($metafields: [MetafieldsSetInput!]!) {
      metafieldsSet(metafields: $metafields) {
        userErrors { field message code }
      }
    }
    """
    for i in range(0, len(items), 25):
        chunk = items[i : i + 25]
        data = admin_graphql(mutation, {"metafields": chunk})
        errors = data["metafieldsSet"]["userErrors"]
        if errors:
            die(f"metafieldsSet errors: {json.dumps(errors, indent=2)}")
        log(f"Set metafields {i + 1}-{i + len(chunk)} / {len(items)}")
        time.sleep(0.15)


def product_variants_bulk_update(product_gid: str, variants: List[Dict[str, str]]) -> None:
    if not variants:
        return
    if DRY_RUN:
        log(f"DRY_RUN variant sku updates for {product_gid}: {len(variants)}")
        return
    # API 2024+/2025: SKU lives under inventoryItem, not top-level sku.
    mutation = """
    mutation VariantBulk($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
      productVariantsBulkUpdate(productId: $productId, variants: $variants) {
        userErrors { field message }
      }
    }
    """
    for i in range(0, len(variants), 50):
        chunk_in = variants[i : i + 50]
        chunk = [
            {"id": row["id"], "inventoryItem": {"sku": row["sku"]}}
            for row in chunk_in
        ]
        data = admin_graphql(mutation, {"productId": product_gid, "variants": chunk})
        errors = data["productVariantsBulkUpdate"]["userErrors"]
        if errors:
            die(f"productVariantsBulkUpdate errors: {json.dumps(errors, indent=2)}")
        time.sleep(0.2)


def stable_sku(product: Dict[str, Any], variant: Dict[str, Any]) -> str:
    handle = re.sub(r"[^a-zA-Z0-9]+", "-", str(product.get("handle") or "item")).strip("-").upper()
    vid = str(variant.get("id") or "")
    title = re.sub(r"[^a-zA-Z0-9]+", "-", str(variant.get("title") or "DEFAULT")).strip("-").upper()
    sku = f"USAF-{handle[:40]}-{title[:40]}-{vid[-6:]}"
    return sku[:64]


def main() -> int:
    only_skus = os.environ.get("ONLY_SKUS", "").lower() in {"1", "true", "yes"}
    log(f"Shop={SHOP} dry_run={DRY_RUN} only_skus={only_skus}")
    products = iter_products_rest()
    log(f"Loaded {len(products)} products")

    custom_metafields: List[Dict[str, str]] = []
    condition_metafields: List[Dict[str, str]] = []
    sku_updates: List[Tuple[str, List[Dict[str, str]]]] = []
    copy_handles: List[str] = []

    personalised_count = 0
    missing_sku = 0

    for product in products:
        handle = str(product.get("handle") or "")
        if "copy" in handle.lower():
            copy_handles.append(handle)

        product_gid = f"gid://shopify/Product/{product['id']}"
        personalised = is_personalised(product)
        if personalised:
            personalised_count += 1
            custom_metafields.append(
                {
                    "ownerId": product_gid,
                    "namespace": "mm-google-shopping",
                    "key": "custom_product",
                    "type": "boolean",
                    "value": "true",
                }
            )

        variant_sku_inputs: List[Dict[str, str]] = []
        for variant in product.get("variants") or []:
            variant_gid = f"gid://shopify/ProductVariant/{variant['id']}"
            if not only_skus:
                condition_metafields.append(
                    {
                        "ownerId": variant_gid,
                        "namespace": "mm-google-shopping",
                        "key": "condition",
                        "type": "single_line_text_field",
                        "value": "new",
                    }
                )
            if not str(variant.get("sku") or "").strip():
                missing_sku += 1
                variant_sku_inputs.append({"id": variant_gid, "sku": stable_sku(product, variant)})
        if variant_sku_inputs:
            sku_updates.append((product_gid, variant_sku_inputs))

    summary = {
        "personalised_products": personalised_count,
        "custom_product_to_set": 0 if only_skus else len(custom_metafields),
        "condition_to_set": 0 if only_skus else len(condition_metafields),
        "variants_missing_sku": missing_sku,
        "copy_handles": copy_handles,
    }
    log(json.dumps(summary, indent=2))

    def dedupe(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        seen = set()
        out = []
        for item in items:
            key = (item["ownerId"], item["namespace"], item["key"])
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    if not only_skus:
        metafields_set(dedupe(custom_metafields))
        metafields_set(dedupe(condition_metafields))
    for product_gid, variants in sku_updates:
        product_variants_bulk_update(product_gid, variants)
        log(f"Updated SKUs on {product_gid} ({len(variants)} variants)")

    log("Done." if not DRY_RUN else "Dry run complete.")
    log(
        "Next in Google Merchant Center: Products → Feeds → Feed rules → Identifier exists = no, then Request review."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

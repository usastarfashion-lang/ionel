#!/usr/bin/env python3
"""Update USASTARFASHION public business identity across Shopify.

Required Dev Dashboard Admin API scopes (in addition to products):
  write_legal_policies
  read_legal_policies
  write_content
  read_content
  write_themes
  read_themes

Then reinstall/reauthorize the app and run:

  export SHOPIFY_SHOP=4ec0cc-d5.myshopify.com
  export SHOPIFY_CLIENT_ID=...
  export SHOPIFY_CLIENT_SECRET=...
  python3 -u scripts/update_business_identity.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

SHOP = os.environ.get("SHOPIFY_SHOP", "4ec0cc-d5.myshopify.com").strip()
TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN", "").strip()
CLIENT_ID = os.environ.get("SHOPIFY_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "").strip()
API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2025-01").strip()

LEGAL = "Ionel Niscoveanu trading as USASTARFASHION"
BRAND = "USASTARFASHION"
EMAIL = "support@usastarfashion.com"
PHONE_E164 = "+447933733089"
PHONE_DISPLAY = "+44 7933 733089"
ADDRESS_HTML = "43 Castle Grange, Skelton-in-Cleveland, Saltburn-by-the-Sea, TS12 2DN, United Kingdom"

CONTACT_BODY = f"""
<p><strong>{LEGAL}</strong></p>
<p>Brand name: {BRAND}</p>
<p>Website: <a href="https://www.usastarfashion.com">https://www.usastarfashion.com</a></p>
<p>Email: <a href="mailto:{EMAIL}">{EMAIL}</a></p>
<p>Phone: <a href="tel:{PHONE_E164}">{PHONE_DISPLAY}</a></p>
<p>Business address:<br>{ADDRESS_HTML}</p>
<p>For orders, returns and product questions, contact {EMAIL} or {PHONE_DISPLAY}.</p>
""".strip()

IDENTITY_BANNER = (
    f"<p><strong>Business identity:</strong> {LEGAL}. "
    f"Contact <a href=\"mailto:{EMAIL}\">{EMAIL}</a> · "
    f"<a href=\"tel:{PHONE_E164}\">{PHONE_DISPLAY}</a>. "
    f"Address: {ADDRESS_HTML}.</p>"
)


def log(msg: str) -> None:
    print(msg, flush=True)


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr, flush=True)
    raise SystemExit(code)


def ensure_token() -> str:
    global TOKEN
    if TOKEN:
        return TOKEN
    if not (CLIENT_ID and CLIENT_SECRET):
        die("Set SHOPIFY_ADMIN_TOKEN or SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET")
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
    ).encode()
    req = urllib.request.Request(
        f"https://{SHOP}/admin/oauth/access_token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.loads(resp.read().decode())
    TOKEN = payload.get("access_token") or ""
    if not TOKEN:
        die(f"Token exchange failed: {payload}")
    log(f"Token scopes: {payload.get('scope')}")
    return TOKEN


def gql(query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    token = ensure_token()
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
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
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        die(f"GraphQL HTTP {err.code}: {err.read().decode()[:500]}")
    if payload.get("errors"):
        die(json.dumps(payload["errors"], indent=2))
    return payload["data"]


def ensure_identity_banner(html: str) -> str:
    html = html or ""
    if "Ionel Niscoveanu trading as USASTARFASHION" in html:
        # Still normalize old landline if present.
        html = html.replace("+442046170370", PHONE_E164)
        html = html.replace("+44 20 4617 0370", PHONE_DISPLAY)
        return html
    if re.search(r"<h1[^>]*>", html, re.I):
        return re.sub(r"(<h1[^>]*>.*?</h1>)", r"\1\n" + IDENTITY_BANNER, html, count=1, flags=re.I | re.S)
    return IDENTITY_BANNER + "\n" + html


def update_policies() -> None:
    type_map = {
        "CONTACT_INFORMATION": CONTACT_BODY,
        "PRIVACY_POLICY": None,
        "REFUND_POLICY": None,
        "SHIPPING_POLICY": None,
        "TERMS_OF_SERVICE": None,
        "SUBSCRIPTION_POLICY": None,
    }
    # Load current bodies
    data = gql(
        """
        query {
          shop {
            shopPolicies { type body title url }
          }
        }
        """
    )
    current = {p["type"]: p for p in data["shop"]["shopPolicies"]}
    mutation = """
    mutation policyUpdate($shopPolicy: ShopPolicyInput!) {
      shopPolicyUpdate(shopPolicy: $shopPolicy) {
        userErrors { field message }
      }
    }
    """
    for ptype in type_map:
        existing = current.get(ptype)
        if not existing:
            log(f"skip missing policy {ptype}")
            continue
        body = type_map[ptype]
        if body is None:
            body = ensure_identity_banner(existing.get("body") or "")
        result = gql(mutation, {"shopPolicy": {"type": ptype, "body": body}})
        errs = result["shopPolicyUpdate"]["userErrors"]
        if errs:
            die(f"{ptype} errors: {errs}")
        log(f"Updated policy {ptype}")


def update_contact_page() -> None:
    data = gql(
        """
        query {
          pages(first: 50) {
            nodes { id title handle body }
          }
        }
        """
    )
    pages = data["pages"]["nodes"]
    targets = [p for p in pages if p.get("handle") in {"contact-us", "contact", "about", "about-us"}]
    if not targets:
        log("No contact/about pages found to update")
        return
    mutation = """
    mutation pageUpdate($id: ID!, $page: PageUpdateInput!) {
      pageUpdate(id: $id, page: $page) {
        userErrors { field message }
      }
    }
    """
    body = CONTACT_BODY + (
        "<p>USASTARFASHION creates personalised clothing and accessories in the UK "
        "using DTF printing and embroidery.</p>"
    )
    for page in targets:
        result = gql(mutation, {"id": page["id"], "page": {"body": body}})
        errs = result["pageUpdate"]["userErrors"]
        if errs:
            die(f"pageUpdate {page['handle']} errors: {errs}")
        log(f"Updated page {page['handle']}")


def main() -> int:
    log(f"Updating business identity on {SHOP}")
    log(f"Legal name: {LEGAL}")
    update_policies()
    update_contact_page()
    log("Done. Also set Merchant Center Business information to the same legal name/phone/email/address, then Request review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# ionel — USASTARFASHION Google Merchant Shopping fix

Toolkit to repair **Google Merchant Center / Shopping** product data for [usastarfashion.com](https://www.usastarfashion.com).

## Quick start

```bash
python3 scripts/generate_merchant_supplemental_feed.py
```

Then upload `feeds/merchant_supplemental_feed.csv` as a Merchant Center supplemental feed and follow `docs/merchant-shopping-fix.md`.

## Contents

- `scripts/generate_merchant_supplemental_feed.py` — builds the supplemental feed from the live Shopify catalogue
- `feeds/` — generated CSV + report
- `shopify/snippets/usaf-merchant-product-schema.liquid` — product JSON-LD snippet for Shopping-friendly structured data
- `docs/merchant-shopping-fix.md` — step-by-step Merchant Center + Shopify Google channel checklist

# ionel — USASTARFASHION Google Merchant Shopping fix

Owner-only toolkit to repair **Google Merchant Center / Shopping** for [usastarfashion.com](https://www.usastarfashion.com).

**Staff limit?** You do not need to add staff. Follow the owner steps in `docs/merchant-shopping-fix.md` (Merchant feed rule + Google & YouTube custom products).

## Quick start

```bash
python3 scripts/generate_merchant_supplemental_feed.py
python3 scripts/validate_merchant_feed.py
```

Upload `feeds/merchant_supplemental_feed.csv` as a Merchant supplemental feed, or just set the **Identifier exists = no** feed rule (see docs).

## Contents

- `scripts/generate_merchant_supplemental_feed.py` — builds the supplemental feed from the live Shopify catalogue
- `feeds/` — generated CSV + report
- `shopify/snippets/usaf-merchant-product-schema.liquid` — product JSON-LD snippet
- `docs/merchant-shopping-fix.md` — owner-only Merchant Center + Shopify checklist

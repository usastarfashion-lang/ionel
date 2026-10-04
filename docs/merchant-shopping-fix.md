# Fix Google Merchant / Shopping for USASTARFASHION

Your Shopify store is already linked to Google (`MC-PS24C2TF30`). Most catalogue items are personalised apparel **without GTINs**, which is the usual reason Merchant Center limits or disapproves Shopping / free listings.

## What was wrong

From a live catalogue scan:

- ~1,380 products, nearly all personalised / Printlab-ready
- Many variants had no GTIN/barcode in the feed Google expects
- Some products still used duplicate handles/titles (`…-copy-copy`)
- Digital downloads were mixed into the same catalogue Google Shopping reads
- Storefront Product schema often exposed only one offer and no MPN/GTIN

## Fix pack in this repo

| Path | Purpose |
| --- | --- |
| `scripts/generate_merchant_supplemental_feed.py` | Builds a Merchant Center supplemental CSV from your live Shopify catalogue |
| `feeds/merchant_supplemental_feed.csv` | Generated upload file (id, identifier_exists, brand, mpn, color, size, custom labels…) |
| `shopify/snippets/usaf-merchant-product-schema.liquid` | Theme snippet so Google sees full variant offers + sku/mpn/gtin |

## Do this in order

### 1) Upload the supplemental feed

1. Open [Google Merchant Center](https://merchants.google.com/)
2. **Products → Supplemental feeds → Add supplemental feed**
3. Upload `feeds/merchant_supplemental_feed.csv`
4. Join key: `id` (format `shopify_GB_81835753803_<variantId>`)
5. Wait for processing, then check **Products → Needs attention**

Regenerate anytime:

```bash
python3 scripts/generate_merchant_supplemental_feed.py
```

### 2) Mark personalised items as custom in Shopify

1. Shopify admin → **Sales channels → Google & YouTube**
2. Open product feed / manage products
3. For Printlab / personalised products set **Custom product = True**
4. Save and allow the Content API feed to sync

### 3) Install the theme schema snippet

1. Themes → Edit code → Snippets → add `usaf-merchant-product-schema`
2. Paste `shopify/snippets/usaf-merchant-product-schema.liquid`
3. Render it on product pages in `<head>`:

```liquid
{% if template.name == 'product' %}
  {% render 'usaf-merchant-product-schema' %}
{% endif %}
```

### 4) Clean catalogue quality issues

- Rename products/handles that still contain `(Copy)` / `-copy-copy`
- Exclude pure digital downloads from the Google sales channel (or keep them excluded via the generator’s default)
- Ensure every sellable variant has a SKU (blank barcode is OK for custom goods when `identifier_exists=no`)
- In Google Search Console, request indexing for `/` and key collection URLs if old titles/snippets still show

### 5) Request review

After the supplemental feed is healthy and Shopify custom flags are saved, use Merchant Center **Request review** on account or product issues.

## Notes for personalised products

Google expects:

- “Personalised” / “Custom” near the start of the title when the offer is customised
- Final customer price (including decoration)
- `identifier_exists = no` when there is no real GTIN
- Accurate availability and landing-page match

# Fix Google Merchant / Shopping for USASTARFASHION

**No staff invite needed.** Do these steps while logged in as the store owner (`usastarfashion@gmail.com`).

Your Shopify store is already linked to Google (`MC-PS24C2TF30`). Most catalogue items are personalised apparel **without GTINs**, which is the usual reason Merchant Center limits or disapproves Shopping / free listings.

## Fastest fix (about 5 minutes)

### A) Google Merchant Center — feed rule (required)

1. Open [merchants.google.com](https://merchants.google.com/) with the Google account linked to the store
2. Go to **Products → Feeds**
3. Open the Shopify feed (usually named **Content API** or similar)
4. Open **Feed rules** → **Add rule**
5. Attribute: **Identifier exists**
6. Set value to: `no` (must be English `no` / `false`)
7. Save, then wait for the feed to reprocess
8. Check **Products → Needs attention** — missing-identifier issues should clear

Optional stronger fix: also upload the supplemental CSV from this repo  
`feeds/merchant_supplemental_feed.csv` under **Products → Supplemental feeds** (join on `id`).

### B) Shopify — mark custom products (required)

1. In Shopify admin left sidebar (not Settings), open **Sales channels**
2. Click **Google & YouTube**
3. Open **Manage products** / product feed editor
4. Set **Custom product = True** for personalised / Printlab items  
   (filter by tag `personalised` or `printlab` if available, then bulk set)
5. Save and let it sync

### C) Request review

In Merchant Center, open any remaining account/product issues and click **Request review**.

## Extra fixes (when you have time)

### Theme schema (helps Google read variants correctly)

1. Shopify → **Online Store → Themes → Edit code**
2. Snippets → Add snippet `usaf-merchant-product-schema`
3. Paste contents from `shopify/snippets/usaf-merchant-product-schema.liquid`
4. In the theme `<head>` (often `layout/theme.liquid` or `snippets/meta-tags.liquid`) add:

```liquid
{% if template.name == 'product' %}
  {% render 'usaf-merchant-product-schema' %}
{% endif %}
```

### Catalogue cleanup

- Rename the 2 products whose handles still contain `-copy`
- Add SKUs to the ~110 variants that are missing them
- Keep digital downloads excluded from the Google sales channel

## If you want me to finish it in admin for you

Staff seats are full, so **do not** try Add staff.

Instead create an API token (does not use a staff seat):

1. Shopify → **Settings → Apps and sales channels → Develop apps**
2. **Allow custom app development** (if asked)
3. **Create an app** → name it `Cursor Merchant Fix`
4. **Configure Admin API scopes**: `read_products`, `write_products`, `read_product_listings`
5. **Install app** → copy the **Admin API access token** (starts with `shpat_`)
6. Paste that token here in chat

With the token I can bulk-set custom flags / SKUs via API. Merchant Center feed rules still need step A in your Google account (or a Merchant invite).

## Regenerate the CSV anytime

```bash
python3 scripts/generate_merchant_supplemental_feed.py
python3 scripts/validate_merchant_feed.py
```

## What Google expects for personalised products

- “Personalised” / “Custom” near the start of the title when decorated
- Final customer price (including decoration)
- `identifier_exists = no` when there is no real GTIN
- Accurate availability and landing-page match

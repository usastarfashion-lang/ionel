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

## If you want the agent to finish Shopify for you

Staff seats are full, so **do not** try Add staff.  
Legacy “Create custom app” is closed (Jan 2026) — use **Dev Dashboard**.

1. Shopify → **Settings → Apps → Develop apps**
2. Click the black button **Build apps in Dev Dashboard**
3. **Create app** → name `Cursor Merchant Fix`
4. Set Admin API scopes: `read_products`, `write_products`
5. **Install / Release** the app on store `4ec0cc-d5`
6. In the app **Settings**, copy **Client ID** and **Client secret**
7. Paste both here in chat (not your Shopify password)

The agent will request an Admin access token and run:

```bash
python3 scripts/apply_shopify_merchant_fixes.py
```

That sets Google `custom_product=true`, variant `condition=new`, and fills missing SKUs.

Merchant Center **Identifier exists = no** feed rule still needs step A in your Google account.

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

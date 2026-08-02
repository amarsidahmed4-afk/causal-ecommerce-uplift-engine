# Real-Time Causal Uplift Engine v2.2: GTM & Storefront Integration Guide

## Overview
This document provides technical instructions for integrating an e-commerce storefront (Shopify, WooCommerce, custom web application) with the Causal Ecommerce Uplift Engine v2.2 via Google Tag Manager (GTM).

The microservice evaluates Conditional Average Treatment Effect (CATE) and Risk-Adjusted Expected Monetary Value (EMV). The API returns `trigger_discount: true` only when offering an incentive yields positive net expected profit after accounting for discount costs, gross margins, and prediction variance.

## ⚠️ Trust Model — Read Before Integrating

**This is a client-side integration. Code on this page runs in every visitor's browser, which means:**

1. **Any API key embedded here is public.** Anyone can open devtools, read the rendered tag, and copy it out. There is no way to ship a secret to a browser and have it remain secret — that's a property of browsers, not a bug in this API. Do not treat the key below as confidential.
2. **Every field in the payload is self-reported by that same browser.** A visitor (or a script impersonating one) can send any values the schema allows, whether or not they reflect real behavior.

Because of (1) and (2), this endpoint authenticates client-side requests with a separate, lower-privilege **`PUBLIC_API_KEY`** — never your real `API_KEY` — and every response returned to a request authenticated this way is tagged `"trust_level": "advisory"`.

**Advisory responses are for UI hints only** (show a banner, highlight a coupon field). **They must never be wired directly to a real coupon application or checkout discount.** Doing so re-opens exactly the exploit this trust model exists to close — see Step 4 and Step 4b below for the pattern that's actually safe to ship.

If your platform can run a GTM Server-Side container or an equivalent backend, prefer `GTM_SERVER_SIDE_INTEGRATION.md` for anything that touches real money — that path can hold the authoritative key and isn't exposed to the browser.

---

## Step 1: Frontend Data Layer Payload Specification

On key behavioral events (e.g., `cart_item_added`, `product_viewed`, `checkout_intent`), the frontend pushes telemetry to `window.dataLayer`.

### JavaScript `dataLayer.push` Example

```javascript
window.dataLayer = window.dataLayer || [];
window.dataLayer.push({
  'event': 'evaluate_causal_intent',
  'causal_payload': {
    "visitor_type_encoded": 1,
    "traffic_type": 2,
    "session_duration_sec": 145.5,
    "product_views_count": 6,
    "cart_add_count": 2,
    "price_sum_viewed": 220.0,
    "time_since_last_action": 14.2,
    "cart_value_override": null
  }
});
```

### Parameter Schema

| Parameter | Type | Range | Description |
| :--- | :--- | :--- | :--- |
| `visitor_type_encoded` | Integer | `0`, `1`, `2` | `0` = New Visitor, `1` = Returning Visitor, `2` = Other |
| `traffic_type` | Integer | `1` – `20` | Traffic channel identifier |
| `session_duration_sec` | Float | $\ge 0.0$ | Active session duration in seconds |
| `product_views_count` | Integer | $\ge 0$ | Total product detail pages viewed |
| `cart_add_count` | Integer | $\ge 0$ | Items added to shopping cart |
| `price_sum_viewed` | Float | $\ge 0.0$ | Cumulative price of products viewed ($) |
| `time_since_last_action` | Float | $\ge 0.0$ | Seconds elapsed since last click/scroll |
| `cart_value_override` | Float / Null | $\ge 0.0$ or `null` | Explicit cart subtotal ($) if available |

---

## Step 2: Configure GTM Data Layer Variables

In Google Tag Manager Web Container:
1. Go to Variables -> User-Defined Variables -> New.
2. Select Data Layer Variable.
3. Variable Name: `dlv - causal_payload`.
4. Data Layer Variable Name: `causal_payload`.
5. Data Layer Version: Version 2.
6. Save and publish the variable.

---

## Step 3: Configure Custom HTML Webhook Tag

Create a Custom HTML Tag in GTM triggered on the `evaluate_causal_intent` custom event.

```html
<script>
  (function() {
    var payload = {{dlv - causal_payload}};
    var apiUrl = "https://YOUR_CLOUD_RUN_URL/predict_v2";
    // Public/advisory tier only. This value WILL be visible to visitors —
    // that's expected and fine. Never put your authoritative API_KEY here.
    var apiKey = "YOUR_PUBLIC_API_KEY";

    fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey
      },
      body: JSON.stringify(payload)
    })
    .then(function(response) {
      if (!response.ok) {
        throw new Error('API Error: ' + response.status);
      }
      return response.json();
    })
    .then(function(data) {
      if (data.trigger_discount === true) {
        window.dataLayer.push({
          'event': 'trigger_causal_incentive'
        });
      }
    })
    .catch(function(error) {
      console.error('Causal Engine Error:', error);
    });
  })();
</script>
```

---

## Step 4: Triggering Storefront Actions (Advisory / UI Only)

When `data.trigger_discount === true`, the script fires the `trigger_causal_incentive` custom event in the `dataLayer`.

Because this response came from the **public/advisory** key, GTM triggers listening for `trigger_causal_incentive` should only do things a visitor could self-serve anyway with no financial exposure if wrong in either direction:
* Dynamic Discount Modals: Display a coupon *field* the visitor can enter manually.
* Cart Banners: Show a notification bar ("You may qualify for free shipping!").

**Do not** use this event to silently apply a discount code to the checkout session. That was the previous recommendation and it is what made this endpoint an open discount oracle: anyone can call `/predict_v2` directly with hand-crafted numbers and get `trigger_discount: true` back, with nothing downstream re-checking whether any of it was real. If real, no-click discount application is a requirement, use Step 4b.

---

## Step 4b: Applying a Real Discount (Authoritative Only)

If you want the discount to actually apply without the visitor typing a code — the original goal — that decision has to be re-made server-side, from data the server itself trusts, not from anything the browser reported:

1. At checkout (or cart-update), your backend — or a GTM Server-Side container, see `GTM_SERVER_SIDE_INTEGRATION.md` — calls `/predict_v2` again using the **authoritative** `API_KEY`.
2. Critically, it populates the payload from **server-known state** (actual cart contents from your platform's cart/order API), not from anything forwarded out of the browser session. This is the real fix for the input-spoofing problem — the advisory/authoritative key split only fixes *who can pretend to be a trusted caller*; using real server-side cart data fixes *what the numbers actually mean*.
3. Only a response with `"trust_level": "authoritative"` and `"trigger_discount": true` is allowed to actually mint/apply a coupon.

An advisory response is a hint to show the visitor something. An authoritative response, built from data the server itself observed, is the only thing allowed to move money.

---

## Step 5: API Response Format

```json
{
  "trigger_discount": true,
  "model_source": "trained_artifact",
  "is_holdout": false,
  "version": "2.3.0",
  "tracking_mode": "client_side",
  "trust_level": "advisory"
}
```

`trust_level` will be `"advisory"` for every response returned to a `PUBLIC_API_KEY` caller — including this one — regardless of what `trigger_discount` says. Check it before deciding what a `true` is allowed to do.
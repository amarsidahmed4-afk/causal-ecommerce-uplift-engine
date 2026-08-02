# Real-Time Causal Uplift Engine v2.2: GTM & Storefront Integration Guide

## Overview
This document provides technical instructions for integrating an e-commerce storefront (Shopify, WooCommerce, custom web application) with the Causal Ecommerce Uplift Engine v2.2 via Google Tag Manager (GTM).

The microservice evaluates Conditional Average Treatment Effect (CATE) and Risk-Adjusted Expected Monetary Value (EMV). The API returns `trigger_discount: true` only when offering an incentive yields positive net expected profit after accounting for discount costs, gross margins, and prediction variance.

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

    fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
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

## Step 4: Triggering Storefront Actions

When `data.trigger_discount === true`, the script fires the `trigger_causal_incentive` custom event in the `dataLayer`.

GTM triggers listening for `trigger_causal_incentive` can execute:
* Dynamic Discount Modals: Display coupon codes.
* Cart Banners: Show notification bars.
* Coupon Code Pre-application: Apply discount codes directly to checkout sessions.

---

## Step 5: API Response Format

```json
{
  "trigger_discount": true,
  "model_source": "trained_artifact",
  "is_holdout": false,
  "version": "2.2.0",
  "tracking_mode": "client_side"
}
```
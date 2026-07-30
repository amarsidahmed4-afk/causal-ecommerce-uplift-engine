# Real-Time Causal Uplift Engine v2.0: GTM & Storefront Integration Guide

## Overview
This document provides the technical handoff guide to connect an e-commerce storefront (Shopify, WooCommerce, React/Next.js) to the **Causal Ecommerce Uplift Engine v2.0** via **Google Tag Manager (GTM)**.

Unlike legacy propensity systems that trigger discounts for any user with high intent, v2.0 evaluates **Conditional Average Treatment Effect (CATE)** and **Expected Monetary Value (EMV)**. The API returns `trigger_discount: true` **only** if offering an incentive generates net incremental profit after accounting for discount costs and gross margins.

---

## Step 1: Front-End Data Layer Payload Specification

On key behavioral triggers (e.g., `cart_item_added`, `product_viewed`, `idle_intent_threshold`), the website frontend must push the real-time intra-session telemetry payload to the `window.dataLayer`.

### JavaScript `dataLayer.push` Example

```javascript
window.dataLayer = window.dataLayer || [];
window.dataLayer.push({
  'event': 'evaluate_causal_intent',
  'causal_payload': {
    "visitor_type_encoded": 1,      // Integer: 0 (New), 1 (Returning), 2 (Other)
    "traffic_type": 2,               // Integer: Traffic channel ID (1-20)
    "session_duration_sec": 145.5,   // Float: Active browsing duration in seconds
    "product_views_count": 6,        // Integer: Product pages viewed in current session
    "cart_add_count": 2,             // Integer: Count of items currently in cart
    "price_sum_viewed": 220.0,       // Float: Cumulative sum of item prices viewed ($)
    "time_since_last_action": 14.2,  // Float: Seconds elapsed since last user action
    "cart_value_override": null      // Float/null: Optional explicit shopping cart $ value
  }
});
```

### Field Definitions & Data Types

| Parameter Name | Data Type | Range / Format | Description |
| :--- | :--- | :--- | :--- |
| `visitor_type_encoded` | Integer | `0`, `1`, `2` | `0` = New Visitor, `1` = Returning Visitor, `2` = Other. |
| `traffic_type` | Integer | `1` – `20` | Traffic acquisition source ID (e.g. Organic, Paid, Direct). |
| `session_duration_sec` | Float | $\ge 0.0$ | Active user session duration in seconds. |
| `product_views_count` | Integer | $\ge 0$ | Total product detail pages viewed during this session. |
| `cart_add_count` | Integer | $\ge 0$ | Total items added to the cart during this session. |
| `price_sum_viewed` | Float | $\ge 0.0$ | Sum of price values of all products viewed ($). |
| `time_since_last_action`| Float | $\ge 0.0$ | Inactivity delay in seconds since last click/scroll. |
| `cart_value_override` | Float / Null | $\ge 0.0$ or `null` | Optional explicit cart subtotal ($) (overrides `price_sum_viewed`). |

---

## Step 2: Configure GTM Data Layer Variables

In your Google Tag Manager Web Container:
1. Go to **Variables** $\rightarrow$ **User-Defined Variables** $\rightarrow$ Click **New**.
2. Variable Type: **Data Layer Variable**.
3. Variable Name: `dlv - causal_payload`.
4. Data Layer Variable Name: `causal_payload`.
5. Data Layer Version: **Version 2**.
6. Save and publish the variable.

---

## Step 3: Set Up the Async Webhook Custom HTML Tag

Create a **Custom HTML Tag** in GTM that fires on the `evaluate_causal_intent` Custom Event trigger.

*(Replace `[YOUR_CLOUD_RUN_URL]` with your live Google Cloud Run service URL).*

```html
<script>
  (function() {
    var payload = {{dlv - causal_payload}};
    var apiUrl = "[YOUR_CLOUD_RUN_URL]/predict_v2";

    fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
    .then(function(response) {
      if (!response.ok) {
        throw new Error('API Response Error: ' + response.status);
      }
      return response.json();
    })
    .then(function(data) {
      // Check if Expected Monetary Value (EMV) decision is positive
      if (data.trigger_discount === true) {
        
        // Push positive decision event back into dataLayer
        window.dataLayer.push({
          'event': 'trigger_causal_incentive',
          'net_emv_dollars': data.net_emv_dollars,
          'cate_uplift': data.cate_uplift
        });
      }
    })
    .catch(function(error) {
      console.error('Causal Intent Engine Connection Error:', error);
    });
  })();
</script>
```

---

## Step 4: Triggering Marketing Interventions

When `data.trigger_discount === true`, the script fires the `trigger_causal_incentive` custom event in your `dataLayer`.

You can create a GTM Trigger listening for `trigger_causal_incentive` to fire high-impact conversion tools:
* **Dynamic Discount Modal:** Display a 10% coupon popup to close the sale.
* **Cart Exit-Intent Banner:** Show a free-shipping bar if the user moves their mouse toward the close tab.
* **Ad Retargeting Pixels:** Fire a Meta / Google Ads high-intent custom event pixel.

---

## Step 5: Expected API JSON Response Format

The API returns a synchronous JSON response in sub-20 milliseconds:

```json
{
  "trigger_discount": true,
  "net_emv_dollars": 2.24,
  "cate_uplift": 0.1712,
  "p_control": 0.35,
  "p_treatment": 0.5212,
  "version": "2.0.0"
}
```
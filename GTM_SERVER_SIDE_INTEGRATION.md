# Server-Side Tracking Integration Guide (GTM Server-Side & Node.js)

## Overview
Server-Side tracking routes telemetry server-to-server rather than directly from the user's browser.

### Benefits of Server-Side Tracking
1. Ad-Blocker Resilience: Bypasses uBlock Origin, Brave, Privacy Badger, and browser extension blocks.
2. Safari ITP Compliance: Extends cookie lifespans and complies with Safari Intelligent Tracking Prevention limits.
3. Mobile Latency Reduction: Removes JavaScript processing overhead from mobile devices.

---

## Architecture

```text
[ Browser / Storefront ] ──► [ First-Party Subdomain: metrics.store.com ] ──► [ Causal API Endpoint ]
                                (GTM Server-Side Container)
```

---

## Step 1: Configure GTM Server-Side Container

1. Deploy a GTM Server-Side Container on Google Cloud Run or Stape.io.
2. Map a first-party custom domain (e.g., `metrics.yourstore.com`) to the GTM Server Container.
3. In GTM Server-Side, create an HTTP Request Tag.

---

## Step 2: HTTP Tag Configuration in GTM Server-Side

* Destination URL: `https://YOUR_CLOUD_RUN_URL/confirm_discount`
* HTTP Method: `POST`
* HTTP Headers:
  * `Content-Type`: `application/json`
  * `X-Tracking-Mode`: `server_side`
  * `X-API-Key`: `{{Your GTM Secret Variable}}`  // Store your authoritative API Key as a secret variable in GTM Server-Side

### Request Payload Format (Server-to-Server)

```json
{
  "event": {
    "visitor_type_encoded": 1,
    "traffic_type": 2,
    "session_duration_sec": 180.0,
    "product_views_count": 5,
    "cart_add_count": 1,
    "price_sum_viewed": 150.0,
    "time_since_last_action": 10.0,
    "session_id": "ga4_client_id_987654321",
    "tracking_mode": "server_side"
  },
  "server_cart_value": 150.00
}
```

---

## Step 3: Server-Side Response Handling

The API returns the definitive decision payload to the GTM Server Container:

```json
{
  "apply_discount": true,
  "net_emv_dollars": 12.50,
  "session_id": "ga4_client_id_987654321"
}
```

Because this endpoint (`/confirm_discount`) strictly requires the authoritative `API_KEY`, it does not return a `trust_level` field — authentication is enforced at the network edge. **This is the only path in this system that should ever result in a real coupon/checkout discount being applied.** The client-side integration (`GTM_INTEGRATION_V2.md`) uses `/predict_v2` which returns `"trust_level": "advisory"` and is UI-hint-only by design, because the browser cannot hold a secret or be trusted to self-report accurate behavioral data.

If `apply_discount === true`, the GTM Server Container returns an HTTP header or cookie to the browser to display the storefront offer, or directly interfaces with the e-commerce backend to apply the coupon to the active cart.

**Important caveat on "server-side":** this container is only as trustworthy as the data it forwards. If the payload fields above (`session_duration_sec`, `cart_add_count`, etc.) are populated by relaying whatever the browser's `dataLayer` sent — which is the common GTM Server-Side setup — you've moved the network hop but not the trust boundary; the input is still visitor-controlled. For a real discount-application decision, this container must independently look up cart state from your platform's server-side cart/order API to populate the `server_cart_value` field, rather than forwarding client-reported values.

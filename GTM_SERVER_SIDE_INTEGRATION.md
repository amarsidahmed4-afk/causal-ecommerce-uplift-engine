# Server-Side Tracking Integration Guide (GTM Server-Side & Node.js)

## Overview
Server-Side tracking routes telemetry **server-to-server** rather than directly from the user's browser.

### Advantages of Server-Side Tracking:
1. **100% Ad-Blocker Immunity:** Completely bypasses uBlock Origin, Brave, Privacy Badger, and browser extension blocks.
2. **Safari ITP Compliance:** Extends cookie lifespans and bypasses Safari Intelligent Tracking Prevention limits.
3. **Zero Mobile Latency:** Removes JavaScript processing overhead from low-end mobile devices.

---

## Architecture

```text
[ Browser / Storefront ] ──► [ Custom Subdomain: metrics.store.com ] ──► [ Causal API Endpoint ]
                                (GTM Server-Side Container)
```

---

## Step 1: Configure GTM Server-Side Container

1. Deploy a **GTM Server-Side Container** on Google Cloud Run or Stape.io.
2. Map a **first-party custom domain** (e.g., `metrics.yourstore.com`) to the GTM Server Container.
3. In GTM Server-Side, create an **HTTP Request Tag**.

---

## Step 2: HTTP Tag Configuration in GTM Server-Side

* **Destination URL:** `https://causal-ecommerce-uplift-engine-347039794179.europe-west1.run.app/predict_v2`
* **HTTP Method:** `POST`
* **HTTP Headers:**
  * `Content-Type`: `application/json`
  * `X-Tracking-Mode`: `server_side`

### Request Payload Format (Server-to-Server)

```json
{
  "visitor_type_encoded": 1,
  "traffic_type": 2,
  "session_duration_sec": 180.0,
  "product_views_count": 5,
  "cart_add_count": 1,
  "price_sum_viewed": 150.0,
  "time_since_last_action": 10.0,
  "session_id": "ga4_client_id_987654321",
  "tracking_mode": "server_side"
}
```

---

## Step 3: Server-Side Response Handling

The API returns the decision payload to the GTM Server Container in <20ms:

```json
{
  "trigger_discount": true,
  "net_emv_dollars": 2.24,
  "cate_uplift": 0.1712,
  "p_control": 0.35,
  "p_treatment": 0.5212,
  "version": "2.0.0",
  "tracking_mode": "server_side"
}
```

If `trigger_discount === true`, the GTM Server Container returns a HTTP header or cookie to the browser to display the storefront offer.
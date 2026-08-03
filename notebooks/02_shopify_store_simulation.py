"""
Shopify Storefront & Customer Intent Simulation.
Simulates live customer traffic across 3 distinct Shopify buyer personas:
  1. Persuadable Buyer (Active cart, price sensitive -> High CATE Uplift -> DISCOUNT TRIGGERED)
  2. Organic Buyer (Loyal returning customer -> High Baseline -> DISCOUNT SUPPRESSED to save margin)
  3. Window Shopper (Bounces quickly -> Low Baseline/Uplift -> DISCOUNT SUPPRESSED)
"""
import os
import sys
import time
import random
import requests

# Add project root directory to Python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import settings

API_URL = "http://127.0.0.1:8000/predict_v2?verbose=true"

# Merchant Store Economics
MERCHANT_AOV = 85.00          # Average Order Value ($)
GROSS_MARGIN = 0.40          # 40% Gross Profit Margin ($34.00 profit)
DISCOUNT_RATE = 0.10         # 10% Discount Offer ($8.50 cost)
DISCOUNT_COST = MERCHANT_AOV * DISCOUNT_RATE

# 3 Real-World Shopify Customer Personas
PERSONAS = [
    {
        "name": "Persuadable Buyer (Cart Active)",
        "visitor_type_encoded": 1,
        "traffic_type": 2,
        "session_duration_sec": 240.0,
        "product_views_count": 7,
        "cart_add_count": 2,
        "price_sum_viewed": 170.0,
        "time_since_last_action": 15.0,
    },
    {
        "name": "Organic Buyer (High Intent)",
        "visitor_type_encoded": 1,
        "traffic_type": 1,
        "session_duration_sec": 450.0,
        "product_views_count": 12,
        "cart_add_count": 4,
        "price_sum_viewed": 340.0,
        "time_since_last_action": 5.0,
    },
    {
        "name": "Window Shopper (Bounces)",
        "visitor_type_encoded": 0,
        "traffic_type": 5,
        "session_duration_sec": 25.0,
        "product_views_count": 1,
        "cart_add_count": 0,
        "price_sum_viewed": 45.0,
        "time_since_last_action": 18.0,
    }
]


def run_shopify_simulation(num_sessions: int = 30):
    print(f"🛍️ Initializing Shopify Storefront Traffic Simulation ({num_sessions} Customer Sessions)...")
    print(f"💰 Store Specs: AOV=${MERCHANT_AOV:.2f} | Margin={GROSS_MARGIN*100:.0f}% | Discount Offer=10% (${DISCOUNT_COST:.2f} cost)\n")

    stats = {
        "total_sessions": 0,
        "discounts_triggered": 0,
        "discounts_suppressed": 0,
        "margin_saved_organic_buyers": 0.0,
        "estimated_net_emv_dollars": 0.0
    }

    for i in range(1, num_sessions + 1):
        persona = random.choice(PERSONAS)

        # Inject realistic browser noise per session
        payload = {
            "visitor_type_encoded": persona["visitor_type_encoded"],
            "traffic_type": persona["traffic_type"],
            "session_duration_sec": max(10.0, persona["session_duration_sec"] + random.uniform(-20, 20)),
            "product_views_count": max(1, persona["product_views_count"] + random.randint(-1, 2)),
            "cart_add_count": max(0, persona["cart_add_count"] + random.randint(-1, 1)),
            "price_sum_viewed": max(20.0, persona["price_sum_viewed"] + random.uniform(-30, 30)),
            "time_since_last_action": max(2.0, persona["time_since_last_action"] + random.uniform(-5, 5)),
            "cart_value_override": MERCHANT_AOV
        }

        start_time = time.time()
        try:
            res = requests.post(API_URL, json=payload, timeout=5)
            latency_ms = (time.time() - start_time) * 1000

            if res.status_code == 200:
                data = res.json()
                trigger = data["trigger_discount"]
                emv = data.get("net_emv_dollars") or 0.0
                cate = data.get("cate_uplift") or 0.0
                p_ctrl = data.get("p_control") or 0.35

                stats["total_sessions"] += 1
                stats["estimated_net_emv_dollars"] += (emv if trigger else 0.0)

                status_badge = "🔥 TRIGGER DISCOUNT" if trigger else "🧊 SUPPRESS DISCOUNT"

                if trigger:
                    stats["discounts_triggered"] += 1
                else:
                    stats["discounts_suppressed"] += 1
                    if p_ctrl > 0.60:
                        stats["margin_saved_organic_buyers"] += DISCOUNT_COST

                print(f"[{i:02d}/{num_sessions}] Customer: {persona['name']:<32} | {status_badge:<22} | Uplift: +{cate*100:4.1f}% | EMV: ${emv:+6.2f} | Latency: {latency_ms:.1f}ms")
            else:
                print(f"❌ Error {res.status_code}: {res.text}")
        except Exception as e:
            print(f"❌ Connection Failed: {e}. Make sure uvicorn server is running!")
            break

        time.sleep(0.05)

    # Print Executive Financial Summary
    print("\n" + "="*75)
    print(" 📊 SHOPIFY MERCHANT EXECUTIVE FINANCIAL SUMMARY ")
    print("="*75)
    print(f" Total Customer Sessions Analyzed  : {stats['total_sessions']}")
    print(f" Discounts Triggered (Persuadables): {stats['discounts_triggered']} ({(stats['discounts_triggered']/stats['total_sessions'])*100:.1f}%)")
    print(f" Discounts Suppressed (Organic/Cold): {stats['discounts_suppressed']} ({(stats['discounts_suppressed']/stats['total_sessions'])*100:.1f}%)")
    print(f" Profit Margin Saved               : ${stats['margin_saved_organic_buyers']:.2f} (Prevented cannibalization on organic buyers)")
    print(f" Estimated Net Dollar Lift ($)      : +${stats['estimated_net_emv_dollars']:.2f}")
    print("="*75)


if __name__ == "__main__":
    run_shopify_simulation(num_sessions=30)
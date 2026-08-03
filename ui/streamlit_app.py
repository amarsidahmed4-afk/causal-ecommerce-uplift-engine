"""
Interactive Causal Uplift & EMV Decision Simulator (Streamlit Dashboard).
"""
import os
import requests
import streamlit as st

# FIX: Append ?verbose=true so the API returns CATE and EMV variables
API_URL = os.getenv("API_URL", "http://127.0.0.1:8080/predict_v2?verbose=true")

# Include the mandatory API key for the dashboard to function
headers = {
"Content -Type": "application/json",
"X-API-Key": os.getenv("PUBLIC_API_KEY", "your-public -key-here")
}

st.set_page_config(
    page_title="Causal Ecommerce Uplift Engine v2.0",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ Causal Ecommerce Uplift Engine v2.0")
st.markdown("Interactive simulator for real-time intra-session CATE uplift estimation & EMV financial decision gating.")

# Sidebar Parameters
st.sidebar.header("⚙️ Financial Override")
aov_override = st.sidebar.number_input("Custom Order Value ($)", min_value=0.0, value=0.0, step=10.0, help="Leave 0.0 to use sum of viewed items")

# Main Layout Columns
col1, col2, col3 = st.columns([1, 1, 1.2])

with col1:
    st.subheader("👤 User Context")
    visitor_type = st.selectbox("Visitor Type", options=[0, 1, 2], format_func=lambda x: ["0: New Visitor", "1: Returning Visitor", "2: Other"][x])
    traffic_type = st.slider("Traffic Source ID", 1, 20, 2)
    session_duration = st.slider("Session Duration (sec)", 0.0, 1200.0, 180.0)

with col2:
    st.subheader("🖱️ Intra-Session Actions")
    product_views = st.slider("Product Views Count", 0, 50, 5)
    cart_adds = st.slider("Cart Adds Count", 0, 10, 1)
    price_sum = st.slider("Cumulative Price Viewed ($)", 0.0, 1000.0, 150.0)
    time_since_action = st.slider("Seconds Since Last Action", 0.0, 300.0, 15.0)

with col3:
    st.subheader("🧠 Causal ML & EMV Output")
    st.markdown("---")

    payload = {
        "visitor_type_encoded": visitor_type,
        "traffic_type": traffic_type,
        "session_duration_sec": session_duration,
        "product_views_count": product_views,
        "cart_add_count": cart_adds,
        "price_sum_viewed": price_sum,
        "time_since_last_action": time_since_action,
        "cart_value_override": aov_override if aov_override > 0 else None
    }

    if st.button("🚀 Evaluate Causal Decision", use_container_width=True):
        with st.spinner("Pinging Causal API..."):
            try:
                res = requests.post(API_URL, json=payload, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    cate = data["cate_uplift"]
                    emv = data["net_emv_dollars"]
                    p_ctrl = data["p_control"]
                    p_treat = data["p_treatment"]
                    trigger = data["trigger_discount"]

                    st.metric("CATE Uplift τ(X)", f"+{cate * 100:.1f}%")
                    st.metric("Net Expected Value (EMV)", f"${emv:.2f}")

                    st.caption(f"P(Buy | No Discount): {p_ctrl*100:.1f}%  →  P(Buy | Discount): {p_treat*100:.1f}%")

                    if trigger:
                        st.success(f"🔥 **TRIGGER INCENTIVE**\n\nNet EMV is **+${emv:.2f}**. Discount is profitable.")
                    else:
                        st.warning(f"🧊 **SUPPRESS INCENTIVE**\n\nNet EMV is **${emv:.2f}**. Discount would destroy margin.")
                else:
                    st.error(f"API Error {res.status_code}: {res.text}")
            except Exception as e:
                st.error(f"Connection Failed: {e}")
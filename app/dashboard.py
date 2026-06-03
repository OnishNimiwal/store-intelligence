import os
import random
import time
import uuid
from datetime import datetime
import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

# 1. Custom CSS for Premium Glassmorphic Design and Aesthetics
st.set_page_config(page_title="Apex Retail — Store Intelligence", layout="wide", initial_sidebar_state="expanded")

# Google Fonts and Custom Modern Styling
st.markdown(
    """
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>
        /* Base styles */
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            background-color: #0A0E1A;
            color: #E2E8F0;
        }
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Outfit', sans-serif;
            font-weight: 700;
            color: #FFFFFF !important;
            letter-spacing: -0.02em;
        }
        
        /* Sidebar Styling */
        section[data-testid="stSidebar"] {
            background-color: #0F172A !important;
            border-right: 1px solid #1E293B;
        }
        
        /* Top Navigation Header Styling */
        .header-container {
            background: linear-gradient(135deg, #1E1B4B 0%, #0F172A 100%);
            padding: 2rem;
            border-radius: 16px;
            border: 1px solid #312E81;
            margin-bottom: 2rem;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .header-title {
            font-size: 2.5rem;
            background: linear-gradient(to right, #C084FC, #6366F1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0;
        }
        
        .header-subtitle {
            font-size: 1rem;
            color: #94A3B8;
            margin-top: 0.5rem;
        }

        /* Glassmorphic Metric Cards */
        .metric-card {
            background: rgba(15, 23, 42, 0.6);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            padding: 1.5rem;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            transition: transform 0.3s ease, border-color 0.3s ease;
        }
        .metric-card:hover {
            transform: translateY(-5px);
            border-color: rgba(99, 102, 241, 0.4);
        }
        .metric-title {
            font-size: 0.875rem;
            font-weight: 500;
            color: #94A3B8;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .metric-value {
            font-size: 2.25rem;
            font-weight: 700;
            color: #FFFFFF;
            margin-top: 0.5rem;
            font-family: 'Outfit', sans-serif;
        }
        
        /* Card Glowing Borders */
        .glow-purple { border-left: 5px solid #A855F7 !important; }
        .glow-green { border-left: 5px solid #10B981 !important; }
        .glow-orange { border-left: 5px solid #F97316 !important; }
        .glow-red { border-left: 5px solid #EF4444 !important; }
        
        /* Anomaly Warning Styling */
        .anomaly-card {
            background: rgba(239, 68, 68, 0.08);
            border: 1px solid rgba(239, 68, 68, 0.2);
            border-radius: 12px;
            padding: 1rem;
            margin-bottom: 1rem;
            display: flex;
            gap: 1rem;
            align-items: center;
        }
        .anomaly-card.warn {
            background: rgba(249, 115, 22, 0.08);
            border: 1px solid rgba(249, 115, 22, 0.2);
        }
        .anomaly-card.info {
            background: rgba(59, 130, 246, 0.08);
            border: 1px solid rgba(59, 130, 246, 0.2);
        }
        
        /* Modern Table Customisation */
        .stDataFrame div {
            border-radius: 12px !important;
            overflow: hidden !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# 2. Header and Setup
st.markdown(
    """
    <div class="header-container">
        <div>
            <h1 class="header-title">Apex Retail — Store Intelligence</h1>
            <p class="header-subtitle">Real-time CCTV behavior streaming analytics and checkout funnel optimization</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Sidebar controls
st.sidebar.markdown("### 🎛️ Store Control Panel")

# Limit options to exactly ST1008 and STORE_BLR_002
store_display_options = ["ST1008", "STORE_BLR_002"]
store_id = st.sidebar.selectbox("Active Store Location", store_display_options, index=0)
auto_refresh = st.sidebar.checkbox("Live Refresh (3s)", value=True)

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚡ Live Stream Simulator")

if st.sidebar.button("Simulate Customer Entrance", help="Push a simulated customer event batch into the pipeline"):
    vis_id = f"VIS_SIM_{random.randint(1000, 9999)}"
    now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = [
        {
            "event_id": str(uuid.uuid4()),
            "store_id": store_id,
            "camera_id": "CAM_ENTRY_01",
            "visitor_id": vis_id,
            "event_type": "ENTRY",
            "timestamp": now_str,
            "dwell_ms": 0,
            "is_staff": False,
            "confidence": 0.95,
            "metadata": {"session_seq": 1},
        }
    ]
    try:
        res = requests.post(f"{API_URL}/events/ingest", json=payload, timeout=5)
        if res.status_code == 201:
            st.sidebar.success(f"Ingested {vis_id} Entry Batch")
        else:
            st.sidebar.error(f"Status Code {res.status_code}")
    except Exception as exc:
        st.sidebar.error(str(exc))

if st.sidebar.button("Simulate Group Entry (3 People)", help="Simulate a group of 3 customers entering simultaneously"):
    now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = []
    for _ in range(3):
        vis_id = f"VIS_SIM_{random.randint(1000, 9999)}"
        payload.append({
            "event_id": str(uuid.uuid4()),
            "store_id": store_id,
            "camera_id": "CAM_ENTRY_01",
            "visitor_id": vis_id,
            "event_type": "ENTRY",
            "timestamp": now_str,
            "dwell_ms": 0,
            "is_staff": False,
            "confidence": 0.92,
            "metadata": {"session_seq": 1},
        })
    try:
        res = requests.post(f"{API_URL}/events/ingest", json=payload, timeout=5)
        if res.status_code == 201:
            st.sidebar.success("Ingested Group Entry Batch")
        else:
            st.sidebar.error(f"Status Code {res.status_code}")
    except Exception as exc:
        st.sidebar.error(str(exc))

# 3. Ingestion statistics & API communication
try:
    metrics = requests.get(f"{API_URL}/stores/{store_id}/metrics", timeout=5).json()
    funnel = requests.get(f"{API_URL}/stores/{store_id}/funnel", timeout=5).json()
    heatmap = requests.get(f"{API_URL}/stores/{store_id}/heatmap", timeout=5).json()
    anomalies = requests.get(f"{API_URL}/stores/{store_id}/anomalies", timeout=5).json()
    health = requests.get(f"{API_URL}/health", timeout=5).json()
    
    # Retrieve raw event stream and linked sales data
    raw_events = requests.get(f"{API_URL}/stores/{store_id}/raw-events", timeout=5).json()
    linked_conversions = requests.get(f"{API_URL}/stores/{store_id}/linked-conversions", timeout=5).json()
    
    connected = True
except Exception:
    connected = False
    st.error("⚠️ Connection Error: Unable to reach the Store Intelligence API. Please ensure the backend is running with 'docker compose up'")

if connected:
    # 4. Premium KPI Cards Row
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        st.markdown(
            f"""
            <div class="metric-card glow-purple">
                <div class="metric-title">Unique Visitors</div>
                <div class="metric-value">{metrics["unique_visitors"]}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
    with c2:
        st.markdown(
            f"""
            <div class="metric-card glow-green">
                <div class="metric-title">Conversion Rate</div>
                <div class="metric-value">{metrics["conversion_rate"] * 100:.2f}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
    with c3:
        st.markdown(
            f"""
            <div class="metric-card glow-orange">
                <div class="metric-title">Current Queue Depth</div>
                <div class="metric-value">{metrics["current_queue_depth"]}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
    with c4:
        st.markdown(
            f"""
            <div class="metric-card glow-red">
                <div class="metric-title">Queue Abandonment</div>
                <div class="metric-value">{metrics["abandonment_rate"] * 100:.1f}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # 5. Funnel and Heatmap Visualization
    col_left, col_right = st.columns([3, 2])
    
    with col_left:
        st.subheader("📊 Session Conversion Funnel")
        funnel_df = pd.DataFrame(funnel["stages"])
        if not funnel_df.empty:
            # Format funnel stages beautifully
            formatted_funnel = funnel_df.copy()
            formatted_funnel["drop_off_pct"] = formatted_funnel["drop_off_pct"].apply(lambda val: f"{val:.1f}% Drop-off")
            formatted_funnel.columns = ["Funnel Stage", "Unique Visitors Count", "Drop-off Rate"]
            st.dataframe(formatted_funnel, width="stretch", hide_index=True)
            
            # Simple custom bar graph for funnel
            st.bar_chart(
                data=funnel_df,
                x="stage_name",
                y="count",
                width="stretch",
            )
        else:
            st.info("No active funnel data available.")

    with col_right:
        st.subheader("🔥 Zone Heatmap Score")
        if heatmap["heatmap"]:
            df_heatmap = pd.DataFrame(heatmap["heatmap"])
            st.markdown(
                f"""
                <div style="background: rgba(15,23,42,0.4); border-radius: 12px; padding: 1rem; margin-bottom: 1rem; border: 1px solid rgba(255,255,255,0.05)">
                    <b>Confidence Status:</b> {"🟢 High (>= 20 sessions)" if heatmap["data_confidence"] else "🟡 Low (< 20 sessions)"}
                </div>
                """,
                unsafe_allow_html=True,
            )
            # Display vertical bar chart for heatmaps
            st.bar_chart(df_heatmap.set_index("zone_id")["score"])
            
            # Structured details
            formatted_heatmap = df_heatmap.copy()
            formatted_heatmap.columns = ["Zone", "Total Visits", "Avg Dwell (sec)", "Normalized Score"]
            st.dataframe(formatted_heatmap, width="stretch", hide_index=True)
        else:
            st.info("No active heatmap data captured yet.")

    st.markdown("---")

    # 6. Deep Data Inspection & Association
    st.subheader("🔍 Deep Data Inspection & Association")
    
    tab_events, tab_conversions = st.tabs(["📋 Raw Event Stream", "🔗 POS Conversion Association"])
    
    with tab_events:
        st.markdown("This tab displays all camera events ingested into the store database, including their camera origin, visitor ID tracking token, confidence score, and timestamps.")
        if raw_events and isinstance(raw_events, list):
            df_ev = pd.DataFrame(raw_events)
            df_ev["dwell_sec"] = df_ev["dwell_ms"] / 1000.0
            
            df_ev_display = df_ev[[
                "timestamp", "visitor_id", "event_type", "zone_id", "sku_zone", 
                "dwell_sec", "confidence", "is_staff", "camera_id"
            ]].copy()
            df_ev_display.columns = [
                "Timestamp", "Visitor ID", "Event Type", "Zone ID", "SKU Zone",
                "Dwell (sec)", "Confidence", "Is Staff?", "Camera ID"
            ]
            st.dataframe(df_ev_display, width="stretch", hide_index=True)
        else:
            st.info("No raw events found for this store location.")

    with tab_conversions:
        st.markdown("This tab maps POS transactions directly to visitor sessions detected in the billing zone (`zone_id` = `BILLING` or `Billing Counter Queue`) during the 5-minute window preceding each sale timestamp.")
        if linked_conversions and isinstance(linked_conversions, list):
            df_lc = pd.DataFrame(linked_conversions)
            df_lc_display = df_lc[[
                "transaction_index", "timestamp", "basket_value", 
                "converted_visitors_count", "converted_visitor_ids"
            ]].copy()
            df_lc_display.columns = [
                "Transaction #", "Sale Timestamp", "Basket Value (INR)", 
                "Matched Sessions Count", "Correlated Session IDs"
            ]
            st.dataframe(df_lc_display, width="stretch", hide_index=True)
            
            # Interactive explorer
            st.markdown("### 🕵️ Transaction-level Visitor Presence Inspector")
            tx_options = [f"Transaction #{item['transaction_index']} at {item['timestamp']}" for item in linked_conversions]
            selected_tx = st.selectbox("Select Transaction to Inspect", tx_options)
            if selected_tx:
                tx_idx = int(selected_tx.split("#")[1].split(" ")[0]) - 1
                selected_txn_data = linked_conversions[tx_idx]
                
                st.write(f"**Transaction Value:** {selected_txn_data['basket_value']} INR")
                st.write(f"**Matched Billing Sessions:** {selected_txn_data['converted_visitors_count']}")
                
                presence_list = selected_txn_data['matching_billing_presence']
                if presence_list:
                    df_pres = pd.DataFrame(presence_list)
                    df_pres.columns = ["Visitor Session ID", "Billing Presence Timestamp", "Event Type"]
                    st.dataframe(df_pres, width="stretch", hide_index=True)
                else:
                    st.warning("No visitor presence detected in the billing zone during the 5-minute window before this transaction.")
        else:
            st.info("No POS transactions or linked conversions found for this store location.")

    st.markdown("---")

    # 7. Operational Anomalies Section
    st.subheader("🚨 Active Operational Anomalies")
    active_anomalies = anomalies.get("anomalies", [])
    if active_anomalies:
        for anom in active_anomalies:
            severity = anom["severity"].upper()
            card_class = "info"
            icon = "ℹ️"
            if severity == "CRITICAL":
                card_class = "danger"
                icon = "🛑"
            elif severity == "WARN":
                card_class = "warn"
                icon = "⚠️"
                
            st.markdown(
                f"""
                <div class="anomaly-card {card_class}">
                    <div style="font-size: 1.5rem;">{icon}</div>
                    <div style="flex-grow: 1;">
                        <div style="font-size: 0.8rem; font-weight: 500; color: #94A3B8; text-transform: uppercase;">[{severity}] {anom["type"]}</div>
                        <div style="font-size: 1.05rem; font-weight: 600; color: #FFFFFF; margin: 2px 0;">{anom["details"]}</div>
                        <div style="font-size: 0.9rem; color: #C084FC;">💡 Action Plan: {anom["suggested_action"]}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.success("✅ Operational Status: Excellent. No anomalies detected in the store pipeline.")

    # 8. Systems & Pipelines Feed Health
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🔌 IoT Feed & System Health")
    
    hc1, hc2, hc3 = st.columns(3)
    system_status = health.get("status", "unknown").upper()
    status_color = "🟢 HEALTHY" if system_status == "HEALTHY" else "🟡 WARNING"
    
    with hc1:
        st.markdown(f"**System State:** `{status_color}`")
    with hc2:
        st.markdown(f"**Database Persistence:** `CONNECTED (SQLite)`")
    with hc3:
        st.markdown(f"**Node Latency:** `{health.get('timestamp', 'N/A')}`")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**Feed Latency Status:**")
    st.json(health.get("store_feeds", {}))

    # Auto refresh handling
    if auto_refresh:
        time.sleep(3)
        st.rerun()

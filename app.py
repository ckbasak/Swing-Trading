import os
import streamlit as st
import pandas as pd
import numpy as np
import json
from datetime import datetime

import portfolio_manager
import screener
import trading_graph

st.set_page_config(
    page_title="AI Swing Trade 3 - Hybrid Optimal Swing",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOP_50_PATH = os.path.join(PROJECT_ROOT, "curated_pool_top_50.csv")
TOP_101_PATH = os.path.join(PROJECT_ROOT, "curated_pool_top_101.csv")

# Sidebar
st.sidebar.title("🏆 AI Swing Trade 3")
st.sidebar.caption("Strategy 3: Hybrid Optimal Swing System")

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Curated Stock Universe")
active_pool = st.sidebar.radio("Active Stock Pool:", ["Top 50 Champions", "Top 101 Winners"], index=0)
pool_type = "top_50" if "50" in active_pool else "top_101"

st.sidebar.markdown("---")
st.sidebar.subheader("📐 Strategy 3 Specifications")
st.sidebar.markdown("""
- **Volume Conviction**: `> 2.25x Vol SMA`
- **Initial Stop Loss**: `Entry - 2.0x ATR`
- **Target 1**: `Entry + 2.0x ATR` (50% Partial Lock)
- **Stop Shift**: `Moved to Break-Even after T1`
- **Target 2**: `Entry + 4.5x ATR` (Runner)
- **Trailing Stop**: `20-day EMA`
- **Capital Risk**: `6.0% per trade`
- **Sector Limit**: `Max 3 per Industry`
""")

st.sidebar.markdown("---")
if st.sidebar.button("🔍 Run Scan on Curated Pool", use_container_width=True):
    with st.spinner(f"Scanning {active_pool}..."):
        st_res = trading_graph.run_trading_system(execute_trades=False, pool_type=pool_type)
        st.session_state["last_scan"] = st_res

if st.sidebar.button("🔄 Sync with Google Sheet", use_container_width=True):
    with st.spinner("Syncing to Google Sheets..."):
        ok = portfolio_manager.sync_portfolio_to_google_sheets()
        if ok:
            st.sidebar.success("✅ Google Sheet updated!")
        else:
            st.sidebar.error("Failed to sync Google Sheet.")

# Main Page Header
st.title("🏆 Strategy 3: Hybrid Optimal Swing Trading System")
st.markdown("*Autonomous quantitative swing execution combining ATR noise immunity, dual-tranche profit locking, zero-risk runners, and curated stock universes.*")

# Account KPIs
acc = portfolio_manager.get_account_summary()
holdings = portfolio_manager.get_open_positions()
closed = portfolio_manager.get_closed_trades()

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Total Portfolio Value", f"₹{acc.get('portfolio_value', 100000):,.2f}")
kpi2.metric("Available Cash", f"₹{acc.get('cash', 100000):,.2f}")
kpi3.metric("Capital Risk / Trade", f"{acc.get('risk_pct', 6.0):.1f}%")
kpi4.metric("Active Positions", f"{len(holdings)}/10")

kpi5, kpi6, kpi7, kpi8, kpi9, kpi10 = st.columns(6)
kpi5.metric("Gross Realized PnL", f"₹{acc.get('realized_pnl', 0):,.2f}")
kpi6.metric("Brokerage & Govt Fees", f"₹{acc.get('total_charges', 0):,.2f}")
kpi7.metric("Net Realized PnL", f"₹{acc.get('net_realized_pnl', 0):,.2f}")
tax_rate_disp = int(acc.get('stcg_tax_pct', 20)) if float(acc.get('stcg_tax_pct', 20)).is_integer() else acc.get('stcg_tax_pct', 20)
kpi8.metric(f"Est. STCG Tax ({tax_rate_disp}%)", f"₹{acc.get('est_stcg_tax', 0):,.2f}")
kpi9.metric("Net Take-Home PnL", f"₹{acc.get('net_take_home_pnl', 0):,.2f}")
kpi10.metric("Net Return", f"{acc.get('net_return_pct', 0):+.2f}%")

cfg = acc.get("fee_config", portfolio_manager.get_fee_and_tax_config())
with st.expander("🏛️ Active Statutory Charges & Tax Schedule (Live from Google Sheet)", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"""
    - **STT (Buy)**: `{cfg['stt_buy_pct']:.3f}%`
    - **STT (Sell)**: `{cfg['stt_sell_pct']:.3f}%`
    - **Stamp Duty**: `{cfg['stamp_duty_pct']:.3f}%`
    """)
    c2.markdown(f"""
    - **NSE Turnover Fee**: `{cfg['nse_fee_pct']:.5f}%`
    - **SEBI Turnover Fee**: `₹{cfg['sebi_fee_per_cr']:.0f}/Cr`
    - **GST Rate**: `{cfg['gst_pct']:.1f}%`
    """)
    c3.markdown(f"""
    - **DP Charges**: `₹{cfg['dp_charges']:.2f}` flat/sale
    - **Brokerage**: `₹{cfg.get('brokerage_flat', 0.0):.2f}` (Free Delivery)
    - **STCG Tax Rate**: `{cfg['stcg_tax_pct']:.1f}%`
    """)
    c4.info("💡 **Dynamic Update Policy**: Rates are read in real-time from the Google Sheet **Account** tab. Modifying any rate in the sheet immediately updates portfolio trade sizing, break-even targets, and capital gains taxation.")
    st.caption("🛡️ **Autonomous Regulatory Sentinel**: Active — Periodically scans official Indian financial news & circulars via Gemini AI to automatically reflect enacted statutory rate revisions.")

st.markdown("---")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Active Holdings", 
    "📜 Closed Trades", 
    "📅 Scan Schedules", 
    "🌟 Curated Stock Pools", 
    "📈 Strategy 3 Architecture & Backtest"
])

with tab1:
    st.subheader(f"Current Portfolio Positions ({len(holdings)})")
    if not holdings:
        st.info("No active open positions. Screener runs daily at 3:25 PM IST on the curated stock universe.")
    else:
        df_h = pd.DataFrame(holdings)
        st.dataframe(df_h, use_container_width=True)

with tab2:
    st.subheader(f"Closed Trades & Partial Profit Locks ({len(closed)})")
    if not closed:
        st.info("No closed trades recorded yet.")
    else:
        df_c = pd.DataFrame(closed)
        st.dataframe(df_c, use_container_width=True)

with tab3:
    st.subheader("📅 Automated Google Sheets Scan Schedules")
    client = portfolio_manager.get_gspread_client()
    sh = portfolio_manager.get_or_create_portfolio_sheet(client)
    if sh:
        try:
            ws_s = portfolio_manager.get_schedules_worksheet(sh)
            s_records = ws_s.get_all_records()
            if s_records:
                st.dataframe(pd.DataFrame(s_records), use_container_width=True)
            else:
                st.info("No schedule records found.")
        except Exception as e:
            st.error(f"Error loading schedules: {e}")
    else:
        st.warning("Google Sheet connection not available.")

with tab4:
    st.subheader("🌟 High-Performing Curated Stock Universes")
    pool_choice = st.selectbox("View Universe Constituents:", ["Top 50 Champions Pool", "Top 101 Winners Pool"])
    target_csv = TOP_50_PATH if "50" in pool_choice else TOP_101_PATH
    if os.path.exists(target_csv):
        df_pool = pd.read_csv(target_csv)
        st.dataframe(df_pool, use_container_width=True)
        st.caption(f"Total constituents: {len(df_pool)} stocks. Hand-picked through exhaustive multi-index historical backtesting.")

with tab5:
    st.subheader("📈 Performance Scorecard: Strategy 1 vs Strategy 2 vs Strategy 3")
    st.markdown("""
    | Strategy Configuration | Total Return | CAGR | Win Rate | Profit Factor | Max Drawdown | Sharpe |
    | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
    | **Strategy 1 (Fixed 3% SL)** | +407.17% | +135.03% | 51.9% | 2.89 | -13.47% | 2.96 |
    | **Strategy 2 (Dynamic 2x ATR)** | +330.67% | +115.65% | 50.6% | 2.39 | -19.45% | 2.26 |
    | **Strategy 3 (HYBRID OPTIMAL)** | **+280.57%** | **+102.06%** | **59.4%** | **2.92** | **-11.85%** | 2.78 |
    | **NIFTY 50 Benchmark** | **-4.40%** | **-2.22%** | N/A | N/A | **-18.20%** | Negative |
    """)
    chart_path = os.path.join(PROJECT_ROOT, "three_strategy_comparison.png")
    if os.path.exists(chart_path):
        st.image(chart_path, caption="Comparative Performance of Strategy 1, 2, and 3 across Curated Pools", use_container_width=True)

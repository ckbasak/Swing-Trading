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
    page_title="ETF Strategy 1 - Systematic Swing Trading",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ETF_CSV_PATH = os.path.join(PROJECT_ROOT, "curated_etf_pool.csv")

# Sidebar
st.sidebar.title("📈 ETF Strategy 1")
st.sidebar.caption("Systematic Dual-Target Swing System for NSE ETFs")

st.sidebar.markdown("---")
st.sidebar.subheader("📐 Strategy Specifications")
st.sidebar.markdown("""
- **Universe**: 20 Liquid NSE ETFs
- **Volume Conviction**: `> 1.15x Vol SMA`
- **Initial Stop Loss**: `Entry - 2.0x ATR`
- **Target 1**: `Entry + 2.0x ATR` (50% Partial Lock)
- **Stop Shift**: `Moved to Break-Even after T1`
- **Target 2**: `Entry + 4.5x ATR` (Runner)
- **Trailing Stop**: `20-day EMA`
- **Capital Risk**: `1.5% per trade`
- **Max Allocation**: `25% per ETF (Max 4 open)`
- **Tax Advantage**: `0% Buy STT, 0.001% Sell STT, ₹0 DP`
""")

st.sidebar.markdown("---")
if st.sidebar.button("🔍 Run Scan on Liquid ETFs", use_container_width=True):
    with st.spinner("Scanning 20 Liquid NSE ETFs..."):
        st_res = trading_graph.run_trading_system(execute_trades=False)
        st.session_state["last_scan"] = st_res

if st.sidebar.button("🔄 Sync with Google Sheet", use_container_width=True):
    with st.spinner("Syncing to Google Sheets..."):
        ok = portfolio_manager.sync_portfolio_to_google_sheets()
        if ok:
            st.sidebar.success("✅ Google Sheet updated!")
        else:
            st.sidebar.error("Failed to sync Google Sheet.")

# Main Page Header
st.title("📈 ETF Strategy 1: Systematic Dual-Target Swing Trading System")
st.markdown("*Optimized institutional-grade swing execution across broad-market, sectoral, commodity, and international ETFs with zero-risk runners and statutory tax efficiency.*")

# Account KPIs
acc = portfolio_manager.get_account_summary()
holdings = portfolio_manager.get_open_positions()
closed = portfolio_manager.get_closed_trades()

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Total Portfolio Value", f"₹{acc.get('portfolio_value', 100000):,.2f}")
kpi2.metric("Available Cash", f"₹{acc.get('cash', 100000):,.2f}")
kpi3.metric("Capital Risk / Trade", f"{acc.get('risk_pct', 1.5):.1f}%")
kpi4.metric("Active ETF Positions", f"{len(holdings)}/4")

kpi5, kpi6, kpi7, kpi8, kpi9, kpi10 = st.columns(6)
kpi5.metric("Gross Realized PnL", f"₹{acc.get('realized_pnl', 0):,.2f}")
kpi6.metric("Brokerage & Govt Fees", f"₹{acc.get('total_charges', 0):,.2f}")
kpi7.metric("Net Realized PnL", f"₹{acc.get('net_realized_pnl', 0):,.2f}")
tax_rate_disp = int(acc.get('stcg_tax_pct', 20)) if float(acc.get('stcg_tax_pct', 20)).is_integer() else acc.get('stcg_tax_pct', 20)
kpi8.metric(f"Est. STCG Tax ({tax_rate_disp}%)", f"₹{acc.get('est_stcg_tax', 0):,.2f}")
kpi9.metric("Net Take-Home PnL", f"₹{acc.get('net_take_home_pnl', 0):,.2f}")
kpi10.metric("Net Return", f"{acc.get('net_return_pct', 0):+.2f}%")

cfg = acc.get("fee_config", portfolio_manager.get_fee_and_tax_config())
with st.expander("🏛️ Active ETF Regulatory Fee & Tax Schedule (Live from Google Sheet)", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"""
    - **STT (Buy)**: `{cfg.get('stt_buy_pct', 0.0):.3f}%` *(Zero STT on ETF purchase)*
    - **STT (Sell)**: `{cfg.get('stt_sell_pct', 0.001):.4f}%` *(100x lower than shares)*
    - **Stamp Duty**: `{cfg.get('stamp_duty_pct', 0.015):.3f}%`
    """)
    c2.markdown(f"""
    - **NSE Turnover Fee**: `{cfg.get('nse_fee_pct', 0.00297):.5f}%`
    - **SEBI Turnover Fee**: `₹{cfg.get('sebi_fee_per_cr', 10.0):.0f}/Cr`
    - **GST Rate**: `{cfg.get('gst_pct', 18.0):.1f}%`
    """)
    c3.markdown(f"""
    - **DP Charges**: `₹{cfg.get('dp_charges', 0.0):.2f}` flat/sale
    - **Brokerage**: `₹{cfg.get('brokerage_flat', 0.0):.2f}` (Dhan Free Delivery)
    - **STCG Tax Rate**: `{cfg.get('stcg_tax_pct', 20.0):.1f}%`
    """)
    c4.markdown("""
    - **Status**: `Optimal ETF Tax Efficiency`
    - **Max Open**: `4 Positions`
    - **Category Limit**: `Max 2 per Sector`
    """)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📂 Open ETF Holdings", 
    "🔍 ETF Breakout Screener", 
    "📜 Trade History & Tax Ledger", 
    "🏛️ Liquid ETF Universe", 
    "⏰ Automated Schedules & Logs"
])

with tab1:
    st.subheader("Active ETF Positions & Runner Trailing Stops")
    if holdings:
        df_hold = pd.DataFrame(holdings)
        st.dataframe(df_hold, use_container_width=True)
    else:
        st.info("No active open ETF positions currently. Run the screener or await market signals.")

with tab2:
    st.subheader("Systematic Breakout Scanner (20 Liquid NSE ETFs)")
    last_scan = st.session_state.get("last_scan")
    if last_scan:
        cands = last_scan.get("candidates", [])
        if cands:
            st.success(f"Found {len(cands)} qualified ETF breakout candidate(s)!")
            df_cands = pd.DataFrame(cands)
            st.dataframe(df_cands, use_container_width=True)
        else:
            st.warning("No ETFs currently meet all breakout criteria (20 SMA cross, 1.15x volume, RSI 50-70).")
        
        with st.expander("📋 Execution Logs", expanded=False):
            for l in last_scan.get("logs", []):
                st.write(l)
    else:
        st.write("Click 'Run Scan on Liquid ETFs' in the sidebar to scan live market data.")

with tab3:
    st.subheader("Closed Trades & Realized Tax Ledger")
    if closed:
        df_closed = pd.DataFrame(closed)
        st.dataframe(df_closed, use_container_width=True)
    else:
        st.info("No closed trades recorded yet.")

with tab4:
    st.subheader("Curated Liquid NSE ETF Catalog (20 Top Liquid Instruments)")
    if os.path.exists(ETF_CSV_PATH):
        df_etf = pd.read_csv(ETF_CSV_PATH)
        st.dataframe(df_etf, use_container_width=True)
    else:
        st.error("curated_etf_pool.csv not found.")

with tab5:
    st.subheader("Automated Daily Cloud Schedules (Google Sheets Sync)")
    scheds = portfolio_manager.get_active_schedules()
    if scheds:
        df_scheds = pd.DataFrame(scheds)
        st.dataframe(df_scheds, use_container_width=True)
    else:
        st.info("Default schedules active: 8:00 AM, 8:30 AM, 9:00 AM, 3:25 PM, 6:00 PM IST.")
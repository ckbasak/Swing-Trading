import os
import sys
import subprocess
import time
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import dhan_client
import portfolio_analyzer
import portfolio_manager

st.set_page_config(
    page_title="Manage-Dhan-Portfolio | Swing Advisory & Capital Recycling",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Failsafe background bot supervisor
def _ensure_bot_running():
    try:
        # Check if running on Render / Linux server
        if os.environ.get("RENDER") or os.environ.get("BOT_STARTED_BY_SCRIPT"):
            return
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                if any('bot.py' in arg for arg in cmdline) and proc.pid != os.getpid():
                    return
            except Exception:
                continue
    except Exception:
        pass
    try:
        cmd = [sys.executable, "-u", "bot.py"]
        subprocess.Popen(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
    except Exception as e:
        st.warning(f"Could not launch bot daemon: {e}")

_ensure_bot_running()

# Header Section
st.title("📈 Manage-Dhan-Portfolio: Swing Trade Advisor")
st.caption("Autonomous Dhan Portfolio Analyzer, Swing Signal Matrix, Paper Trading & Capital Recycling Planner")

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ System Control & Sync")
    
    dhan_configured = dhan_client.is_dhan_configured()
    if dhan_configured:
        st.success("🟢 Dhan API Configured")
    else:
        st.info("🟡 Dhan API Offline / Demo Mode (Using Sample Holdings)")
        
    sheets_client = portfolio_manager.get_gspread_client()
    if sheets_client:
        st.success("🟢 Google Sheets Sync Active")
    else:
        st.warning("🔴 Google Sheets Unconfigured")
        
    st.divider()
    
    if st.button("🔄 Refresh Technical Analysis", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()

# Fetch Analysis Data
@st.cache_data(ttl=300)
def get_portfolio_data():
    holdings, summary = portfolio_analyzer.analyze_full_dhan_portfolio()
    portfolio_manager.sync_analysis_to_sheets(holdings, summary)
    return holdings, summary

holdings, summary = get_portfolio_data()

# Top KPI Metric Cards
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Total Investment", f"₹{summary['totalInvestment']:,.2f}")
with col2:
    st.metric("Current Portfolio Value", f"₹{summary['totalCurrentValue']:,.2f}")
with col3:
    st.metric(
        "Total P&L",
        f"₹{summary['totalPnL']:,.2f}",
        delta=f"{summary['totalPnLPercentage']:+.2f}%"
    )
with col4:
    st.metric(
        "Action Signals",
        f"🔴 {summary['sellCount']} | 🟢 {summary['averageCount']} | 🟡 {summary['holdCount']}"
    )
with col5:
    st.metric(
        "Freed Capital Potential",
        f"₹{summary['capitalRecycling']['totalFreedCapital']:,.2f}"
    )

st.divider()

# Main Navigation Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Holdings Matrix",
    "🎯 Swing Recommendations",
    "📈 Technical Charts",
    "📝 Paper Trade Simulator",
    "🔄 Capital Recycling Planner"
])

# TAB 1: HOLDINGS MATRIX
with tab1:
    st.subheader("📊 Dhan Holdings Technical Health Snapshot")
    
    if holdings:
        df_display = pd.DataFrame(holdings)
        
        # Color formatting helper
        def highlight_rec(val):
            if val == "SELL":
                return "background-color: #ff4d4d; color: white; font-weight: bold;"
            elif val == "AVERAGE":
                return "background-color: #2eb82e; color: white; font-weight: bold;"
            else:
                return "background-color: #ffa64d; color: black; font-weight: bold;"

        disp_cols = [
            "tradingSymbol", "type", "qty", "buyPrice", "ltp", "currentValue",
            "pnl", "pnlPercentage", "recommendation", "actionStrength",
            "rsi14", "ema20", "sma50", "sma200", "targetPrice", "stopLoss", "riskReward"
        ]
        
        df_cols_rename = {
            "tradingSymbol": "Symbol",
            "type": "Type",
            "qty": "Qty",
            "buyPrice": "Buy Price (₹)",
            "ltp": "LTP (₹)",
            "currentValue": "Value (₹)",
            "pnl": "P&L (₹)",
            "pnlPercentage": "P&L %",
            "recommendation": "Recommendation",
            "actionStrength": "Signal Strength",
            "rsi14": "RSI (14)",
            "ema20": "20-EMA",
            "sma50": "50-SMA",
            "sma200": "200-SMA",
            "targetPrice": "Target (₹)",
            "stopLoss": "Stop Loss (₹)",
            "riskReward": "R:R Ratio"
        }
        
        df_styled = df_display[disp_cols].rename(columns=df_cols_rename)
        
        st.dataframe(
            df_styled.style.applymap(highlight_rec, subset=["Recommendation"]),
            use_container_width=True,
            height=400
        )
    else:
        st.info("No holdings found.")

# TAB 2: SWING RECOMMENDATIONS
with tab2:
    st.subheader("🎯 Swing Trade Action Recommendations")
    
    sells = [h for h in holdings if h["recommendation"] == "SELL"]
    averages = [h for h in holdings if h["recommendation"] == "AVERAGE"]
    holds = [h for h in holdings if h["recommendation"] == "HOLD"]
    
    r_col1, r_col2, r_col3 = st.columns(3)
    
    with r_col1:
        st.markdown("### 🔴 SELL Signals (Exit & Liquidate)")
        st.caption("Protect capital or lock in target profits")
        if sells:
            for s in sells:
                with st.expander(f"🔴 **{s['tradingSymbol']}** ({s['type']}) - {s['actionStrength']}", expanded=True):
                    st.write(f"• **Qty**: `{s['qty']}` | **LTP**: `₹{s['ltp']:,.2f}`")
                    st.write(f"• **Current Value**: `₹{s['currentValue']:,.2f}`")
                    st.write(f"• **P&L**: `₹{s['pnl']:,.2f}` (`{s['pnlPercentage']:+.2f}%`)")
                    st.write(f"• **Target**: `₹{s['targetPrice']:,.2f}` | **SL**: `₹{s['stopLoss']:,.2f}`")
                    st.error(f"**Rationale**: {' '.join(s['rationale'])}")
        else:
            st.success("No sell signals detected. Portfolio structure is healthy.")
            
    with r_col2:
        st.markdown("### 🟢 AVERAGE Signals (Accumulate Pullback)")
        st.caption("Quality holdings in uptrend at key support")
        if averages:
            for a in averages:
                with st.expander(f"🟢 **{a['tradingSymbol']}** ({a['type']}) - {a['actionStrength']}", expanded=True):
                    st.write(f"• **Qty**: `{a['qty']}` | **LTP**: `₹{a['ltp']:,.2f}`")
                    st.write(f"• **Target Price**: `₹{a['targetPrice']:,.2f}`")
                    st.write(f"• **Stop Loss**: `₹{a['stopLoss']:,.2f}`")
                    st.write(f"• **Risk:Reward**: `{a['riskReward']}`")
                    st.success(f"**Rationale**: {' '.join(a['rationale'])}")
        else:
            st.info("No pullback accumulation setups currently active.")

    with r_col3:
        st.markdown("### 🟡 HOLD Signals (Maintain Position)")
        st.caption("Positions maintaining structural trend bounds")
        if holds:
            for h in holds:
                with st.expander(f"🟡 **{h['tradingSymbol']}** ({h['type']})"):
                    st.write(f"• **Qty**: `{h['qty']}` | **LTP**: `₹{h['ltp']:,.2f}`")
                    st.write(f"• **P&L**: `₹{h['pnl']:,.2f}` (`{h['pnlPercentage']:+.2f}%`)")
                    st.write(f"• **Target Price**: `₹{h['targetPrice']:,.2f}`")
                    st.write(f"• **Stop Loss**: `₹{h['stopLoss']:,.2f}`")
                    st.info(f"**Rationale**: {' '.join(h['rationale'])}")
        else:
            st.write("No positions on hold.")

# TAB 3: TECHNICAL CHARTS
with tab3:
    st.subheader("📈 Interactive Technical Chart Viewer")
    
    symbols_list = [h["tradingSymbol"] for h in holdings]
    if symbols_list:
        selected_sym = st.selectbox("Select Holding for Technical Charting", symbols_list)
        selected_item = next((h for h in holdings if h["tradingSymbol"] == selected_sym), None)
        
        if selected_item:
            yf_ticker = f"{selected_sym}.NS"
            df_chart = yf.Ticker(yf_ticker).history(period="6m")
            
            if not df_chart.empty:
                df_chart["EMA20"] = df_chart["Close"].ewm(span=20, adjust=False).mean()
                df_chart["SMA50"] = df_chart["Close"].rolling(window=50).mean()
                df_chart["SMA200"] = df_chart["Close"].rolling(window=200).mean()
                
                delta = df_chart["Close"].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / (loss.replace(0, np.nan))
                df_chart["RSI"] = 100 - (100 / (1 + rs))
                
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.7, 0.3])
                
                # Candlestick
                fig.add_trace(go.Candlestick(
                    x=df_chart.index,
                    open=df_chart["Open"],
                    high=df_chart["High"],
                    low=df_chart["Low"],
                    close=df_chart["Close"],
                    name="Price"
                ), row=1, col=1)
                
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["EMA20"], line=dict(color="orange", width=1.5), name="20 EMA"), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["SMA50"], line=dict(color="blue", width=1.5), name="50 SMA"), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["SMA200"], line=dict(color="purple", width=1.5), name="200 SMA"), row=1, col=1)
                
                # Buy Price & Target / SL lines
                fig.add_hline(y=selected_item["buyPrice"], line_dash="dash", line_color="cyan", annotation_text="Buy Price", row=1, col=1)
                fig.add_hline(y=selected_item["targetPrice"], line_dash="dash", line_color="green", annotation_text="Target", row=1, col=1)
                fig.add_hline(y=selected_item["stopLoss"], line_dash="dash", line_color="red", annotation_text="Stop Loss", row=1, col=1)
                
                # RSI Subplot
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["RSI"], line=dict(color="purple", width=1.5), name="RSI 14"), row=2, col=1)
                fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
                fig.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)
                
                fig.update_layout(
                    title=f"Technical Chart: {selected_sym} (LTP: ₹{selected_item['ltp']:,.2f})",
                    xaxis_rangeslider_visible=False,
                    height=600,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                
                st.plotly_chart(fig, use_container_width=True)

# TAB 4: PAPER TRADE SIMULATOR
with tab4:
    st.subheader("📝 Simulated Paper Trade Execution Engine")
    st.info("🔒 Zero real orders are placed on Dhan. All trades operate strictly in simulated paper mode.")
    
    sim_col1, sim_col2 = st.columns(2)
    
    with sim_col1:
        st.markdown("### 🔴 Execute Paper Sell")
        sell_candidates = [h for h in holdings if h["recommendation"] == "SELL"] or holdings
        selected_sell_sym = st.selectbox("Select Holding to Paper Sell", [h["tradingSymbol"] for h in sell_candidates], key="paper_sell_sym")
        
        target_sell_item = next((h for h in holdings if h["tradingSymbol"] == selected_sell_sym), None)
        if target_sell_item:
            st.write(f"• **Available Qty**: `{target_sell_item['qty']}`")
            st.write(f"• **Current LTP**: `₹{target_sell_item['ltp']:,.2f}`")
            st.write(f"• **Estimated Capital Freed**: `₹{target_sell_item['currentValue']:,.2f}`")
            
            if st.button("🔥 Execute Paper Sell Transaction", type="primary", key="btn_exec_sell"):
                success = portfolio_manager.record_paper_trade(
                    symbol=selected_sell_sym,
                    action="SELL",
                    qty=target_sell_item["qty"],
                    price=target_sell_item["ltp"],
                    total_val=target_sell_item["currentValue"],
                    rationale="Paper sell executed via dashboard"
                )
                if success:
                    st.success(f"Successfully recorded paper sell for {selected_sell_sym}! Liquid funds updated.")
                else:
                    st.success(f"Paper sell for {selected_sell_sym} simulated locally.")

    with sim_col2:
        st.markdown("### 🟢 Execute Paper Average / Buy")
        buy_candidates = [h for h in holdings if h["recommendation"] == "AVERAGE"] or holdings
        selected_buy_sym = st.selectbox("Select Holding to Paper Average", [h["tradingSymbol"] for h in buy_candidates], key="paper_buy_sym")
        
        target_buy_item = next((h for h in holdings if h["tradingSymbol"] == selected_buy_sym), None)
        if target_buy_item:
            add_qty = st.number_input("Additional Qty to Paper Buy", min_value=1, value=int(max(1, target_buy_item["qty"] * 0.3)))
            est_cost = add_qty * target_buy_item["ltp"]
            st.write(f"• **Current LTP**: `₹{target_buy_item['ltp']:,.2f}`")
            st.write(f"• **Total Estimated Cost**: `₹{est_cost:,.2f}`")
            
            if st.button("➕ Execute Paper Average Transaction", key="btn_exec_buy"):
                success = portfolio_manager.record_paper_trade(
                    symbol=selected_buy_sym,
                    action="AVERAGE",
                    qty=add_qty,
                    price=target_buy_item["ltp"],
                    total_val=est_cost,
                    rationale="Paper average executed via dashboard"
                )
                if success:
                    st.success(f"Successfully recorded paper average for {selected_buy_sym}!")
                else:
                    st.success(f"Paper average for {selected_buy_sym} simulated locally.")

    st.divider()
    st.markdown("### 📄 Recent Paper Trades Log")
    trades_log = portfolio_manager.load_paper_trades()
    if trades_log:
        st.dataframe(pd.DataFrame(trades_log), use_container_width=True)
    else:
        st.caption("No paper trades logged yet.")

# TAB 5: CAPITAL RECYCLING PLANNER
with tab5:
    st.subheader("🔄 Capital Recycling Planner")
    st.caption("Automated mapping of freed capital from paper exits to fund the 4 core swing strategies")
    
    cr = summary["capitalRecycling"]
    total_freed = cr["totalFreedCapital"]
    
    st.markdown(f"### Total Liquid Capital Freed from Exits: **₹{total_freed:,.2f}**")
    
    st.divider()
    
    cr_col1, cr_col2 = st.columns(2)
    
    with cr_col1:
        st.markdown("#### Recommended Strategic Allocation Split")
        st.write(f"1. 🚀 **Strategy 1 (Mid-Cap Swing - 30%)**: `₹{cr['strategy1_midcap']:,.2f}`")
        st.write(f"2. 🏢 **Strategy 2 (Sector Swing - 30%)**: `₹{cr['strategy2_sector']:,.2f}`")
        st.write(f"3. ⚡ **Strategy 3 (Momentum Swing - 20%)**: `₹{cr['strategy3_momentum']:,.2f}`")
        st.write(f"4. 🛡️ **ETF Strategy (Low-Beta Swing - 20%)**: `₹{cr['etf_strategy']:,.2f}`")
        
    with cr_col2:
        labels = ["Strategy 1 (Mid-Cap)", "Strategy 2 (Sector)", "Strategy 3 (Momentum)", "ETF Strategy"]
        values = [cr["strategy1_midcap"], cr["strategy2_sector"], cr["strategy3_momentum"], cr["etf_strategy"]]
        
        if sum(values) > 0:
            fig_pie = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.4)])
            fig_pie.update_layout(title="Capital Allocation Donut Chart", height=300, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Liquidate SELL candidates to calculate recycling distribution.")

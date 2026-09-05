import os
# Auto-load .env if available
def _load_env():
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except Exception:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() not in os.environ:
                            os.environ[k.strip()] = v.strip().strip("'").strip('"')
_load_env()

import streamlit as st
import gc
import pandas as pd
import yfinance as yf
import plotly.express as px
import portfolio_manager
import screener
import subprocess
import sys

# Failsafe background bot launcher (ensures bot.py runs even if Render Start Command only runs streamlit)
@st.cache_resource
def _ensure_bot_running():
    if os.environ.get("BOT_STARTED_BY_SCRIPT") == "1":
        return None
    try:
        bot_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")
        proc = subprocess.Popen([sys.executable, "-u", bot_script])
        print(f"Spawned background Telegram bot daemon (PID: {proc.pid}) from app.py")
        return proc
    except Exception as e:
        print(f"Error starting background bot from app.py: {e}")
        return None

_ensure_bot_running()

st.set_page_config(
    page_title="NSE Swing Trading Dashboard #2 (Strategy v2)",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📈 NSE Swing Trading Dashboard (Strategy #2 Optimized)")
st.markdown("Automated Quantitative System: 20-SMA Breakout • >2.5x Volume • 2× ATR Stops • Max 3/Sector")

# Refresh Button
if st.sidebar.button("🔄 Sync & Refresh Portfolio"):
    st.cache_data.clear()
    with st.spinner("Syncing portfolio targets and trailing stops..."):
        try:
            client = portfolio_manager.get_gspread_client()
            sh = portfolio_manager.get_or_create_portfolio_sheet(client)
            logs = portfolio_manager.sync_portfolio(sh)
            for log in logs:
                st.sidebar.info(log)
            st.success("Portfolio sync completed!")
        except Exception as e:
            st.sidebar.error(f"Error syncing portfolio: {e}")

# Load Sheets Data
@st.cache_data(ttl=30)
def load_data():
    try:
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        
        # Get Account details
        account = portfolio_manager.get_account_details(sh)
        
        # Get holdings
        holdings = portfolio_manager.get_all_holdings(sh)
        
        # Get schedules
        try:
            ws_sched = portfolio_manager.get_schedules_worksheet(sh)
            schedules = ws_sched.get_all_records()
        except Exception:
            schedules = []
        
        return account, holdings, schedules
    except Exception as e:
        st.error(f"Error loading data from Google Sheets: {e}")
        import json
        env_val = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        if env_val:
            try:
                if (env_val.startswith("'") and env_val.endswith("'")) or (env_val.startswith('"') and env_val.endswith('"')):
                    env_val = env_val[1:-1]
                kid = json.loads(env_val).get("private_key_id", "Unknown")
                if kid.startswith("42cd"):
                    st.warning(f"⚠️ Active Key ID on this server is OLD: `{kid}`. Please trigger 'Clear build cache & deploy' on Render.")
                else:
                    st.info(f"Active Service Account Key ID: `{kid}`")
            except Exception:
                pass
        return None, None, None

account, holdings, schedules = load_data()

if account is not None and holdings is not None:
    # Convert holdings to DataFrame
    df = pd.DataFrame(holdings)
    
    # Calculate Metrics
    cash = account.get("Cash Balance", 0.0)
    portfolio_value = account.get("Total Portfolio Value", 0.0)
    
    open_df = df[df["Status"] == "OPEN"].copy() if not df.empty and "Status" in df.columns else pd.DataFrame()
    closed_df = df[df["Status"] == "CLOSED"].copy() if not df.empty and "Status" in df.columns else pd.DataFrame()
    
    # Fetch live current prices for open holdings
    unrealized_pnl = 0.0
    open_holdings_value = 0.0
    
    if not open_df.empty:
        open_df["Entry Price"] = pd.to_numeric(open_df["Entry Price"], errors='coerce')
        open_df["Quantity"] = pd.to_numeric(open_df["Quantity"], errors='coerce')
        open_df["Target"] = pd.to_numeric(open_df["Target"], errors='coerce')
        open_df["Current SL"] = pd.to_numeric(open_df["Current SL"], errors='coerce')
        open_df["Initial SL"] = pd.to_numeric(open_df["Initial SL"], errors='coerce')
        
        tickers = open_df["Ticker"].tolist()
        try:
            prices_df = yf.download(tickers, period="1d", group_by="ticker", progress=False, threads=False)
            current_prices = {}
            for ticker in tickers:
                try:
                    if len(tickers) == 1:
                        current_prices[ticker] = float(prices_df["Close"].iloc[-1])
                    else:
                        current_prices[ticker] = float(prices_df[ticker]["Close"].iloc[-1])
                except Exception:
                    current_prices[ticker] = open_df.loc[open_df["Ticker"] == ticker, "Entry Price"].values[0]
            gc.collect()
        except Exception:
            current_prices = {row["Ticker"]: row["Entry Price"] for _, row in open_df.iterrows()}
            
        open_df["Current Price"] = open_df["Ticker"].map(current_prices)
        open_df["Current Value"] = open_df["Current Price"] * open_df["Quantity"]
        open_df["Unrealized PnL"] = (open_df["Current Price"] - open_df["Entry Price"]) * open_df["Quantity"]
        open_df["PnL %"] = ((open_df["Current Price"] - open_df["Entry Price"]) / open_df["Entry Price"]) * 100
        
        unrealized_pnl = open_df["Unrealized PnL"].sum()
        open_holdings_value = open_df["Current Value"].sum()
    
    # Realized PnL
    realized_pnl = 0.0
    if not closed_df.empty:
        closed_df["PnL"] = pd.to_numeric(closed_df["PnL"], errors='coerce')
        realized_pnl = closed_df["PnL"].sum()
        
    # KPI Columns
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🏦 Total Portfolio Value", f"₹{portfolio_value:,.2f}")
    col2.metric("💵 Available Cash Balance", f"₹{cash:,.2f}")
    
    pnl_label = "🟢 Unrealized PnL" if unrealized_pnl >= 0 else "🔴 Unrealized PnL"
    col3.metric(pnl_label, f"₹{unrealized_pnl:,.2f}", delta=f"{unrealized_pnl:,.2f}")
    
    rpnl_label = "🟢 Realized PnL" if realized_pnl >= 0 else "🔴 Realized PnL"
    col4.metric(rpnl_label, f"₹{realized_pnl:,.2f}")
    
    # Calculate CAGR & XIRR
    try:
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        perf_metrics = portfolio_manager.calculate_performance_metrics(sh)
    except Exception:
        perf_metrics = {"Total Return (%)": 0.0, "CAGR (%)": 0.0, "XIRR (%)": 0.0, "Days Elapsed": 0}
        
    st.markdown(" ")
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("📈 Total Return", f"{perf_metrics['Total Return (%)']}%")
    col6.metric("📊 CAGR (Annualized)", f"{perf_metrics['CAGR (%)']}%")
    col7.metric("🌀 XIRR", f"{perf_metrics['XIRR (%)']}%")
    col8.metric("⏱️ Days Active", f"{perf_metrics['Days Elapsed']} Days")
    
    st.markdown("---")
    
    # Main Tabs
    tab_open, tab_closed, tab_charts, tab_schedules = st.tabs([
        "📈 Open Positions", "🤝 Closed Trades", "📊 Analytics & Charts", "📅 Scan Schedules"
    ])
    
    with tab_open:
        st.subheader("Current Holdings")
        if not open_df.empty:
            if "Entry Value" not in open_df.columns or open_df["Entry Value"].isna().all():
                if "Buy Value" in open_df.columns and not open_df["Buy Value"].isna().all():
                    open_df["Entry Value"] = pd.to_numeric(open_df["Buy Value"], errors='coerce')
                elif "Traded Value" in open_df.columns and not open_df["Traded Value"].isna().all():
                    open_df["Entry Value"] = pd.to_numeric(open_df["Traded Value"], errors='coerce')
                else:
                    open_df["Entry Value"] = open_df["Entry Price"] * open_df["Quantity"]
            else:
                open_df["Entry Value"] = pd.to_numeric(open_df["Entry Value"], errors='coerce')
                
            open_df["Sector"] = open_df["Ticker"].map(screener.get_stock_sector)
            display_columns = [
                "Ticker", "Sector", "Entry Date", "Entry Price", "Quantity", "Entry Value",
                "Current Price", "Current SL", "Target", "Unrealized PnL", "PnL %"
            ]
            st.dataframe(
                open_df[display_columns].style.format({
                    "Entry Price": "₹{:.2f}",
                    "Quantity": "{:.0f}",
                    "Entry Value": "₹{:.2f}",
                    "Current Price": "₹{:.2f}",
                    "Current SL": "₹{:.2f}",
                    "Target": "₹{:.2f}",
                    "Unrealized PnL": "₹{:.2f}",
                    "PnL %": "{:+.2f}%"
                }),
                use_container_width=True
            )
        else:
            st.info("No open positions. Use the Telegram bot to scan or wait for the daily scheduled runs.")
            
    with tab_closed:
        st.subheader("Closed Trade History")
        if not closed_df.empty:
            if "Entry Value" not in closed_df.columns or closed_df["Entry Value"].isna().all():
                if "Buy Value" in closed_df.columns and not closed_df["Buy Value"].isna().all():
                    closed_df["Entry Value"] = pd.to_numeric(closed_df["Buy Value"], errors='coerce')
                else:
                    closed_df["Entry Value"] = closed_df["Entry Price"] * closed_df["Quantity"]
            else:
                closed_df["Entry Value"] = pd.to_numeric(closed_df["Entry Value"], errors='coerce')
                
        if not closed_df.empty:
            closed_df["Entry Price"] = pd.to_numeric(closed_df["Entry Price"], errors='coerce')
            closed_df["Exit Price"] = pd.to_numeric(closed_df["Exit Price"], errors='coerce')
            closed_df["Quantity"] = pd.to_numeric(closed_df["Quantity"], errors='coerce')
            closed_df["Entry Value"] = closed_df["Entry Price"] * closed_df["Quantity"]
            closed_df["Sector"] = closed_df["Ticker"].map(screener.get_stock_sector)
            
            if "Exit Value" not in closed_df.columns or closed_df["Exit Value"].isna().all():
                if "Sell Value" in closed_df.columns and not closed_df["Sell Value"].isna().all():
                    closed_df["Exit Value"] = pd.to_numeric(closed_df["Sell Value"], errors='coerce')
                else:
                    closed_df["Exit Value"] = closed_df["Exit Price"] * closed_df["Quantity"]
            else:
                closed_df["Exit Value"] = pd.to_numeric(closed_df["Exit Value"], errors='coerce')
                
            closed_df["PnL"] = pd.to_numeric(closed_df["PnL"], errors='coerce')
            closed_df["PnL %"] = ((closed_df["Exit Price"] - closed_df["Entry Price"]) / closed_df["Entry Price"]) * 100.0
                
            # Summary Metrics for Closed Trades
            win_trades = len(closed_df[closed_df["PnL"] > 0])
            total_closed = len(closed_df)
            win_rate = (win_trades / total_closed * 100.0) if total_closed > 0 else 0.0
            avg_pnl_pct = closed_df["PnL %"].mean() if total_closed > 0 else 0.0
            
            cm1, cm2, cm3 = st.columns(3)
            cm1.metric("🤝 Total Closed Trades", f"{total_closed}")
            cm2.metric("🏆 Win Rate", f"{win_rate:.1f}%", f"{win_trades}/{total_closed} profitable")
            cm3.metric("📈 Avg Trade PnL %", f"{avg_pnl_pct:+.2f}%")
            
            st.divider()
            
            display_closed = [
                "Ticker", "Sector", "Entry Date", "Entry Price", "Quantity", "Entry Value",
                "Exit Date", "Exit Price", "Exit Value", "PnL", "PnL %", "Exit Reason"
            ]
            st.dataframe(
                closed_df[display_closed].style.format({
                    "Entry Price": "₹{:.2f}",
                    "Quantity": "{:.0f}",
                    "Entry Value": "₹{:.2f}",
                    "Exit Price": "₹{:.2f}",
                    "Exit Value": "₹{:.2f}",
                    "PnL": "₹{:.2f}",
                    "PnL %": "{:+.2f}%"
                }),
                use_container_width=True
            )
        else:
            st.info("No closed trades yet.")
            
    with tab_charts:
        st.subheader("Portfolio Analytics")
        c1, c2 = st.columns(2)
        
        with c1:
            # Pie Chart of Allocation
            if not open_df.empty:
                pie_df = pd.DataFrame([
                    {"Asset": "Cash", "Value": cash},
                    *([{"Asset": row["Ticker"], "Value": row["Current Value"]} for _, row in open_df.iterrows()])
                ])
                fig_pie = px.pie(pie_df, values='Value', names='Asset', title='Portfolio Capital Allocation')
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("No open holdings to display allocation chart.")
                
        with c2:
            # Sector Concentration Chart
            if not open_df.empty:
                sector_df = open_df.groupby("Sector")["Current Value"].sum().reset_index()
                fig_sector = px.pie(
                    sector_df, 
                    values='Current Value', 
                    names='Sector', 
                    title='Sector Concentration (Max 3 Positions / Sector)',
                    hole=0.4
                )
                st.plotly_chart(fig_sector, use_container_width=True)
            elif not closed_df.empty:
                grouped_closed = closed_df.groupby("Ticker")["PnL"].sum().reset_index()
                fig_bar = px.bar(
                    grouped_closed, 
                    x='Ticker', 
                    y='PnL', 
                    title='Realized PnL by Ticker',
                    color='PnL',
                    color_continuous_scale=px.colors.diverging.RdYlGn
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("No trades to display performance chart.")
                
    with tab_schedules:
        st.subheader("📅 Automated & Custom Scan Schedules (Strategy #2)")
        st.markdown(
            "Configure schedules directly in your Google Sheet (**`NSE_Swing_Trading_Portfolio_2`** -> **`Schedules`** tab). "
            "Render monitors the schedule table every 60 seconds."
        )
        
        if schedules:
            sched_df = pd.DataFrame(schedules)
            st.dataframe(sched_df, use_container_width=True)
        else:
            st.info("No scan schedules found.")
            
        with st.expander("ℹ️ How to Add or Update Scan Schedules in Google Sheets"):
            st.markdown("""
            1. Open Google Sheet: **`NSE_Swing_Trading_Portfolio_2`**.
            2. Switch to the **`Schedules`** tab.
            3. Add or update a row:
               - **Date**: `TODAY`, `YYYY-MM-DD` (e.g. `2026-09-05`), `DAILY`, or `WEEKDAYS`.
               - **Time**: Target time in IST (24h format, e.g. `18:30`, `09:15`, `15:25`).
               - **Mode**: `EXECUTE` (auto-execute buy orders) or `PREVIEW` (preview only).
               - **Status**: `PENDING` (ready to run), `ACTIVE` (for daily recurrence), or `PAUSED`.
            4. At that exact minute, Render will trigger the scan, update status to `COMPLETED`, record `Last Run`, and send the report to Telegram!
            """)
else:
    st.info("Welcome! Please set up your Google Sheets database and add configurations to load the dashboard.")

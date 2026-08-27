import os
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import portfolio_manager

st.set_page_config(
    page_title="NSE Swing Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📈 NSE Multi-Agent Swing Trading Dashboard")
st.markdown("Automated 20 DMA Breakout System for Nifty 250 Universe")

# Refresh Button
if st.sidebar.button("🔄 Sync & Refresh Portfolio"):
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
@st.cache_data(ttl=60)
def load_data():
    try:
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        
        # Get Account details
        account = portfolio_manager.get_account_details(sh)
        
        # Get holdings
        holdings = portfolio_manager.get_all_holdings(sh)
        
        return account, holdings
    except Exception as e:
        st.error(f"Error loading data from Google Sheets: {e}")
        return None, None

account, holdings = load_data()

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
            prices_df = yf.download(tickers, period="1d", group_by="ticker", progress=False)
            current_prices = {}
            for ticker in tickers:
                try:
                    if len(tickers) == 1:
                        current_prices[ticker] = float(prices_df["Close"].iloc[-1])
                    else:
                        current_prices[ticker] = float(prices_df[ticker]["Close"].iloc[-1])
                except Exception:
                    current_prices[ticker] = open_df.loc[open_df["Ticker"] == ticker, "Entry Price"].values[0]
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
    
    st.markdown("---")
    
    # Main Tabs
    tab_open, tab_closed, tab_charts = st.tabs(["📈 Open Positions", "🤝 Closed Trades", "📊 Analytics & Charts"])
    
    with tab_open:
        st.subheader("Current Holdings")
        if not open_df.empty:
            display_columns = [
                "Ticker", "Entry Date", "Entry Price", "Quantity", 
                "Current Price", "Current SL", "Target", "Unrealized PnL", "PnL %"
            ]
            st.dataframe(
                open_df[display_columns].style.format({
                    "Entry Price": "₹{:.2f}",
                    "Quantity": "{:.0f}",
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
            display_closed = [
                "Ticker", "Entry Date", "Entry Price", "Quantity", 
                "Exit Date", "Exit Price", "PnL", "Exit Reason"
            ]
            st.dataframe(
                closed_df[display_closed].style.format({
                    "Entry Price": "₹{:.2f}",
                    "Quantity": "{:.0f}",
                    "Exit Price": "₹{:.2f}",
                    "PnL": "₹{:.2f}"
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
            # Bar chart of realized PnL per stock
            if not closed_df.empty:
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
                st.info("No closed trades to display performance chart.")
else:
    st.info("Welcome! Please set up your Google Sheets database and add configurations to load the dashboard.")

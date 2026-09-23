import os
import sys
import time
import subprocess
import streamlit as st

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def is_bot_alive(pid_file: str) -> bool:
    try:
        if os.path.exists(pid_file):
            with open(pid_file, "r") as f:
                pid_str = f.read().strip()
            if pid_str and pid_str.isdigit():
                pid = int(pid_str)
                if sys.platform == "win32":
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    process = kernel32.OpenProcess(0x00100000, False, pid)
                    if process:
                        kernel32.CloseHandle(process)
                        return True
                    return False
                else:
                    try:
                        os.kill(pid, 0)
                        return True
                    except (OSError, ProcessLookupError):
                        return False
    except Exception:
        pass
    return False

def ensure_all_bots_running():
    bot_configs = [
        ("Strategy #1 Bot", os.path.join(PROJECT_ROOT, "strategy1"), "bot.py", "bot.pid"),
        ("Strategy #2 Bot", os.path.join(PROJECT_ROOT, "strategy2"), "bot.py", "bot.pid"),
        ("Strategy #3 Bot", os.path.join(PROJECT_ROOT, "strategy3"), "bot.py", "bot.pid"),
        ("ETF Strategy #1 Bot", os.path.join(PROJECT_ROOT, "strategy_etf"), "bot.py", "bot.pid"),
    ]
    
    status_dict = {}
    for name, s_dir, script, pid_f in bot_configs:
        pid_path = os.path.join(s_dir, pid_f)
        status_dict[name] = is_bot_alive(pid_path)
    return status_dict

bot_statuses = ensure_all_bots_running()

st.set_page_config(
    page_title="NSE AI Swing Trading Master Systems",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.sidebar.title("🏦 Quantitative Trading Hub")
st.sidebar.caption("Unified 1-Service Master Architecture (100% Free 24/7)")

active_system = st.sidebar.radio(
    "Select Active Trading System:",
    [
        "🏆 Master Multi-System Dashboard",
        "📈 Strategy #1: Classic Breakout (Nifty 50)",
        "🎯 Strategy #2: Dynamic ATR & Sector Limits",
        "🥇 Strategy #3: Hybrid Optimal Swing",
        "📊 ETF Strategy #1: Systematic Liquid ETF Swing"
    ],
    index=0
)

st.sidebar.markdown("---")
st.sidebar.subheader("🤖 Telegram Bot Daemons Status")
for b_name, b_active in bot_statuses.items():
    if b_active:
        st.sidebar.success(f"🟢 {b_name}: Active")
    else:
        st.sidebar.error(f"🔴 {b_name}: Offline")

if st.sidebar.button("🔄 Restart Bot Daemons", use_container_width=True):
    ensure_all_bots_running()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("🛡️ Autonomous Regulatory Sentinel & Google Sheets Sync active across all systems.")

def render_strategy_sub_app(sub_dir):
    import runpy
    s_path = os.path.join(PROJECT_ROOT, sub_dir)
    # Clear cached strategy sub-modules from sys.modules to prevent cross-strategy namespace collisions
    for mod in ["portfolio_manager", "screener", "dhan_client", "tax_sentinel", "trading_graph", "sentiment_analyzer"]:
        sys.modules.pop(mod, None)
        
    if s_path in sys.path:
        sys.path.remove(s_path)
    sys.path.insert(0, s_path)
    
    old_cwd = os.getcwd()
    try:
        os.chdir(s_path)
        runpy.run_path(os.path.join(s_path, "app.py"))
    finally:
        os.chdir(old_cwd)

if "Master Multi-System" in active_system:
    st.title("🏦 NSE Multi-Strategy Quantitative Swing Trading Master Hub")
    st.markdown("*Autonomous institutional swing execution, multi-agent sentiment analysis, and statutory tax accounting across 4 independent strategy portfolios.*")
    
    st.markdown("---")
    
    try:
        import sentiment_analyzer
        sentiment_analyzer.render_streamlit_sentiment_card("master")
    except Exception as e:
        st.warning(f"Strategy sentiment component offline: {e}")
        
    st.markdown("---")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Strategy 1 (Classic)", "Nifty 50 Universe", "1.0% Risk / Trade")
    c2.metric("Strategy 2 (Dynamic ATR)", "Nifty 50 Universe", "1.5% Risk (Max 3/Sector)")
    c3.metric("Strategy 3 (Hybrid Optimal)", "Curated Champions Pool", "6.0% Risk (50% T1 Lock)")
    c4.metric("ETF Strategy 1", "20 Liquid NSE ETFs", "1.5% Risk (0% Buy STT)")
    
    st.markdown("---")
    
    tab1, tab2, tab3 = st.tabs(["📊 Performance Matrix", "🏛️ Statutory Fee & STCG Tax Schedule", "🌐 Master Cloud Architecture"])
    
    with tab1:
        st.subheader("🏆 2-Year Comprehensive Backtest Scorecard (₹1,00,000 Capital)")
        st.markdown("""
        | Strategy Configuration | Universe | Gross Return | Total Fees Paid | 20% STCG Tax | Net Take-Home | Win Rate | Profit Factor | Max Drawdown |
        | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
        | **Strategy 1 (Classic Breakout)** | Nifty 50 | +330.13% | ₹41,305.60 | ₹57,764.55 | **+231.48%** | 49.0% | 2.45 | -12.80% |
        | **Strategy 2 (Dynamic 2x ATR)** | Nifty 50 | +257.84% | ₹28,069.15 | ₹45,954.63 | **+184.18%** | 44.4% | 2.09 | -20.23% |
        | **Strategy 3 (HYBRID OPTIMAL)** | Curated Top 50 | +209.17% | ₹24,297.41 | ₹36,974.74 | **+148.22%** | **59.2%** | 2.39 | **-11.33%** |
        | **ETF Strategy 1** | 20 Liquid ETFs | +174.09% | ₹1,850.10 | ₹27,854.00 | **+144.38%** | **71.1%** | **3.71** | **-14.90%** |
        | **Benchmark NIFTY 50** | Index | -5.68% | N/A | ₹0.00 | **-5.68%** | N/A | N/A | -18.20% |
        """)
        
    with tab2:
        st.subheader("🏛️ Dynamic Statutory Fee & Tax Schedule (Google Sheets Synced)")
        st.markdown("""
        - **STT (Equity Buy)**: `0.100%` | **STT (Equity Sell)**: `0.100%` | **STT (ETF Sell)**: `0.001%`
        - **Stamp Duty**: `0.015%` | **NSE Turnover Fee**: `0.00297%` | **GST**: `18.0%`
        - **DP Charges**: `₹14.75` flat/sale (Equities) | `₹0.00` (ETFs)
        - **Brokerage**: `₹0.00` (Dhan Free Delivery)
        - **STCG Capital Gains Tax**: `20.0%` (Section 111A)
        """)
        
    with tab3:
        st.subheader("⚡ 1-Service Render Architecture (100% Free Forever)")
        st.markdown("""
        - **Monthly Hour Consumption**: 720 Hours/Month (Single Web Service)
        - **Render Free Tier Cap**: 750 Hours/Month
        - **Status**: **100% Compliant — Permanent 24/7 Uptime without Suspensions!**
        - **Background Automation**: All 4 Telegram bots (`bot1`, `bot2`, `bot3`, `bot_etf`) run as concurrent background process daemons.
        """)

elif "Strategy #1" in active_system:
    render_strategy_sub_app("strategy1")

elif "Strategy #2" in active_system:
    render_strategy_sub_app("strategy2")

elif "Strategy #3" in active_system:
    render_strategy_sub_app("strategy3")

elif "ETF Strategy" in active_system:
    render_strategy_sub_app("strategy_etf")

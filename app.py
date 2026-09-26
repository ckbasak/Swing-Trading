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
def get_bot_status() -> dict:
    """Checks bot process status and reads recent bot log entries."""
    running = False
    pid = None
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                if any('bot.py' in str(arg) for arg in cmdline) and proc.pid != os.getpid():
                    running = True
                    pid = proc.pid
                    break
            except Exception:
                continue
    except Exception:
        pass
        
    if not running:
        try:
            output = subprocess.check_output('wmic process where "commandline like \'%bot.py%\'" get processid', shell=True, stderr=subprocess.DEVNULL).decode()
            pids = [int(p) for p in output.split() if p.isdigit() and int(p) != os.getpid()]
            if pids:
                running = True
                pid = pids[0]
        except Exception:
            pass
        
    logs = ""
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log")
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                logs = "".join(f.readlines()[-20:])
        except Exception:
            pass
            
    return {"running": running, "pid": pid, "logs": logs}

def _ensure_bot_running():
    status = get_bot_status()
    if not status["running"]:
        try:
            cmd = [sys.executable, "-u", "bot.py"]
            subprocess.Popen(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
        except Exception as e:
            print(f"Could not launch bot daemon: {e}")

_ensure_bot_running()

# Header Section
st.title("📈 Manage-Dhan-Portfolio: Swing Trade Advisor")
st.caption("Autonomous Dhan Portfolio Analyzer, Swing Signal Matrix, Paper Trading & Capital Recycling Planner")

# Persistent Settings Manager
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cached_settings.json")

PRESET_OPTIONS = [
    "🛡️ Capital Preservation & Risk Reduction (Conservative)",
    "⚖️ Balanced Market Sentiment (Optimal)",
    "🚀 Maximum Return & Profit Pursuit (Aggressive)"
]

DEFAULT_SETTINGS = {
    "opt_preset": PRESET_OPTIONS[1],
    "target_pct_val": 10.0,
    "stop_loss_pct_val": -7.0,
    "rsi_ob_val": 70.0,
    "rsi_exit_val": 38.0,
    "rsi_pb_val": 46.0
}

import threading

def load_saved_settings() -> dict:
    """Fast instantaneous local JSON settings loader (0ms delay)."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    res = DEFAULT_SETTINGS.copy()
                    res.update(data)
                    try:
                        res["target_pct_val"] = float(res["target_pct_val"])
                        res["stop_loss_pct_val"] = float(res["stop_loss_pct_val"])
                        res["rsi_ob_val"] = float(res["rsi_ob_val"])
                        res["rsi_exit_val"] = float(res["rsi_exit_val"])
                        res["rsi_pb_val"] = float(res["rsi_pb_val"])
                    except Exception:
                        pass
                    return res
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()

def _bg_sync_sheets(settings: dict):
    try:
        portfolio_manager.save_app_settings_to_sheets(settings)
    except Exception:
        pass

def save_settings(settings: dict):
    """Fast local JSON settings writer + non-blocking background backup thread."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Error saving local settings: {e}")

    try:
        t = threading.Thread(target=_bg_sync_sheets, args=(settings,), daemon=True)
        t.start()
    except Exception:
        pass

# HTML5 LocalStorage restoration script for browser-side persistence across tab closes
js_restore = """
<script>
(function() {
    try {
        const p = new URLSearchParams(window.parent.location.search);
        if (!p.has('preset')) {
            const saved = window.parent.localStorage.getItem('dhan_user_preset_cfg');
            if (saved) {
                const c = JSON.parse(saved);
                if (c && c.opt_preset) {
                    p.set('preset', c.opt_preset);
                    if (c.target_pct_val) p.set('target', c.target_pct_val);
                    if (c.stop_loss_pct_val) p.set('stop', c.stop_loss_pct_val);
                    if (c.rsi_ob_val) p.set('rsi_ob', c.rsi_ob_val);
                    if (c.rsi_exit_val) p.set('rsi_exit', c.rsi_exit_val);
                    if (c.rsi_pb_val) p.set('rsi_pb', c.rsi_pb_val);
                    window.parent.location.search = p.toString();
                }
            }
        }
    } catch(e) {}
})();
</script>
"""
st.html(js_restore)

# Read URL Query Params if available
qp = getattr(st, "query_params", {})
saved_cfg = load_saved_settings()

init_preset = qp.get("preset", saved_cfg.get("opt_preset", PRESET_OPTIONS[1]))
if init_preset not in PRESET_OPTIONS:
    init_preset = PRESET_OPTIONS[1]

try:
    init_target = float(qp.get("target", saved_cfg.get("target_pct_val", 10.0)))
    init_stop = float(qp.get("stop", saved_cfg.get("stop_loss_pct_val", -7.0)))
    init_rsi_ob = float(qp.get("rsi_ob", saved_cfg.get("rsi_ob_val", 70.0)))
    init_rsi_exit = float(qp.get("rsi_exit", saved_cfg.get("rsi_exit_val", 38.0)))
    init_rsi_pb = float(qp.get("rsi_pb", saved_cfg.get("rsi_pb_val", 46.0)))
except Exception:
    init_target = float(saved_cfg.get("target_pct_val", 10.0))
    init_stop = float(saved_cfg.get("stop_loss_pct_val", -7.0))
    init_rsi_ob = float(saved_cfg.get("rsi_ob_val", 70.0))
    init_rsi_exit = float(saved_cfg.get("rsi_exit_val", 38.0))
    init_rsi_pb = float(saved_cfg.get("rsi_pb_val", 46.0))

# Session State Initialization for Threshold Sliders and Selectbox Key
if "opt_preset_select_key" not in st.session_state:
    st.session_state.opt_preset_select_key = init_preset
if "target_pct_val" not in st.session_state:
    st.session_state.target_pct_val = init_target
if "stop_loss_pct_val" not in st.session_state:
    st.session_state.stop_loss_pct_val = init_stop
if "rsi_ob_val" not in st.session_state:
    st.session_state.rsi_ob_val = init_rsi_ob
if "rsi_exit_val" not in st.session_state:
    st.session_state.rsi_exit_val = init_rsi_exit
if "rsi_pb_val" not in st.session_state:
    st.session_state.rsi_pb_val = init_rsi_pb

def sync_and_save_settings():
    preset = st.session_state.opt_preset_select_key
    target = st.session_state.target_pct_val
    stop = st.session_state.stop_loss_pct_val
    rsi_ob = st.session_state.rsi_ob_val
    rsi_exit = st.session_state.rsi_exit_val
    rsi_pb = st.session_state.rsi_pb_val
    
    save_settings({
        "opt_preset": preset,
        "target_pct_val": target,
        "stop_loss_pct_val": stop,
        "rsi_ob_val": rsi_ob,
        "rsi_exit_val": rsi_exit,
        "rsi_pb_val": rsi_pb
    })
    
    try:
        st.query_params["preset"] = preset
        st.query_params["target"] = str(target)
        st.query_params["stop"] = str(stop)
        st.query_params["rsi_ob"] = str(rsi_ob)
        st.query_params["rsi_exit"] = str(rsi_exit)
        st.query_params["rsi_pb"] = str(rsi_pb)
    except Exception:
        pass
        
    js_save = f"""
    <script>
    (function() {{
        try {{
            const cfg = {{
                opt_preset: "{preset}",
                target_pct_val: "{target}",
                stop_loss_pct_val: "{stop}",
                rsi_ob_val: "{rsi_ob}",
                rsi_exit_val: "{rsi_exit}",
                rsi_pb_val: "{rsi_pb}"
            }};
            window.parent.localStorage.setItem('dhan_user_preset_cfg', JSON.stringify(cfg));
        }} catch(e) {{}}
    }})();
    </script>
    """
    st.html(js_save)

def on_preset_select_change():
    preset = st.session_state.opt_preset_select_key
    if "Capital Preservation" in preset:
        st.session_state.target_pct_val = 9.5
        st.session_state.stop_loss_pct_val = -5.5
        st.session_state.rsi_ob_val = 68.0
        st.session_state.rsi_exit_val = 40.0
        st.session_state.rsi_pb_val = 44.0
    elif "Maximum Return" in preset:
        st.session_state.target_pct_val = 14.0
        st.session_state.stop_loss_pct_val = -8.5
        st.session_state.rsi_ob_val = 75.0
        st.session_state.rsi_exit_val = 35.0
        st.session_state.rsi_pb_val = 48.0
    else:
        st.session_state.target_pct_val = 11.5
        st.session_state.stop_loss_pct_val = -7.0
        st.session_state.rsi_ob_val = 70.0
        st.session_state.rsi_exit_val = 38.0
        st.session_state.rsi_pb_val = 46.0
    sync_and_save_settings()

def on_slider_change():
    sync_and_save_settings()

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ System Control & Sync")
    
    dhan_configured = dhan_client.is_dhan_configured()
    holdings_source = dhan_client.get_holdings_source()
    
    if holdings_source == "LIVE":
        st.success("🟢 Live Dhan Portfolio Connected")
    elif dhan_configured:
        st.warning("⚠️ Dhan Token Expired (Using Cached Snapshot)")
    else:
        st.info("🟡 Dhan API Offline / Demo Mode")
        
    with st.expander("🔑 Dhan API Live Token Update", expanded=(holdings_source != "LIVE")):
        st.caption("Generate a fresh 24h Access Token from **web.dhan.co** -> **My Profile** -> **Access DhanHQ APIs**:")
        client_id_val = st.text_input("Dhan Client ID", value=os.environ.get("DHAN_CLIENT_ID", "1101177354"), key="dhan_client_id_renew_input")
        new_token_val = st.text_input("Dhan Access Token", type="password", key="dhan_token_renew_input")
        if st.button("⚡ Update Token & Sync Live Portfolio", use_container_width=True, type="primary"):
            if client_id_val.strip() and new_token_val.strip():
                success = dhan_client.set_dhan_credentials(client_id_val.strip(), new_token_val.strip())
                st.cache_data.clear()
                if success:
                    st.toast("Connected to live Dhan portfolio!", icon="🟢")
                    st.rerun()
                else:
                    err_detail = dhan_client.get_last_api_error() or "Invalid authentication token"
                    st.error(f"Token verification failed: `{err_detail}`. Please verify Client ID and token copied from web.dhan.co.")
            else:
                st.warning("Please enter both Dhan Client ID and Access Token.")
        
    sh_instance = portfolio_manager.get_or_create_spreadsheet()
    if sh_instance:
        st.success("🟢 Google Sheets Sync Active")
    else:
        st.warning("🟡 Google Sheets Not Connected")
        with st.expander("📍 How to Connect Google Sheets"):
            st.markdown(
                "**1.** Open [Google Sheets](https://sheets.google.com) & create a blank spreadsheet named:\n"
                "`NSE_Dhan_Portfolio_Manager`\n\n"
                "**2.** Click **Share** (top-right) and invite service account:\n"
                "`sheets-editor@swing-trade-system-506815.iam.gserviceaccount.com`\n\n"
                "**3.** Grant **Editor** access & save."
            )

    # Telegram Bot Control Expander
    bot_info = get_bot_status()
    with st.expander("🤖 Telegram Bot Supervisor", expanded=not bot_info["running"]):
        if bot_info["running"]:
            st.success(f"🟢 Telegram Bot Active (PID: {bot_info['pid']})")
        else:
            st.error("🔴 Telegram Bot Inactive")
            
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Restart Bot", width="stretch"):
                try:
                    import psutil
                    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                        cmdline = proc.info.get('cmdline') or []
                        if any('bot.py' in str(arg) for arg in cmdline) and proc.pid != os.getpid():
                            proc.kill()
                except Exception:
                    pass
                cmd = [sys.executable, "-u", "bot.py"]
                subprocess.Popen(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
                st.toast("Telegram Bot process restarted!", icon="🚀")
                st.rerun()
        with col2:
            if st.button("🔄 Refresh", width="stretch"):
                st.rerun()
                
        if bot_info["logs"]:
            st.caption("Recent Bot Logs:")
            st.code(bot_info["logs"], language="log")

    st.divider()

    with st.expander("🎯 Auto-Optimize Thresholds & Presets", expanded=True):
        st.caption("Select market goal & auto-tune indicator criteria:")
        st.selectbox(
            "Optimization Goal",
            options=PRESET_OPTIONS,
            key="opt_preset_select_key",
            on_change=on_preset_select_change
        )
        
        if st.button("⚡ Apply / Re-Tune Selected Preset", width="stretch", type="primary"):
            on_preset_select_change()
            st.toast(f"Updated thresholds for {st.session_state.opt_preset_select_key}", icon="⚡")
            st.rerun()

        st.divider()
        st.caption("Manual Indicator Slider Controls:")
        target_pct = st.slider("Target Profit Gain %", min_value=5.0, max_value=30.0, key="target_pct_val", step=0.5, on_change=on_slider_change, help="Target gain percentage to trigger SELL signal")
        stop_loss_pct = st.slider("Stop-Loss Risk Limit %", min_value=-20.0, max_value=-2.0, key="stop_loss_pct_val", step=0.5, on_change=on_slider_change, help="Maximum allowed position drawdown before exit")
        rsi_ob = st.slider("RSI Overbought Exit", min_value=60.0, max_value=85.0, key="rsi_ob_val", step=1.0, on_change=on_slider_change)
        rsi_exit = st.slider("RSI Breakdown Exit", min_value=25.0, max_value=50.0, key="rsi_exit_val", step=1.0, on_change=on_slider_change)
        rsi_pb = st.slider("RSI Pullback Max (BUY)", min_value=30.0, max_value=55.0, key="rsi_pb_val", step=1.0, on_change=on_slider_change)
        
    if st.button("🔄 Refresh Technical Analysis", width="stretch"):
        st.cache_data.clear()
        st.rerun()

# Fetch Analysis Data
@st.cache_data(ttl=300)
def get_portfolio_data(target_pct: float, stop_loss_pct: float, rsi_ob: float, rsi_exit: float, rsi_pb: float):
    overrides = {
        "PROFIT_TARGET_PCT": target_pct,
        "STOP_LOSS_PCT": stop_loss_pct,
        "RSI_OVERBOUGHT": rsi_ob,
        "RSI_OVERSOLD_EXIT": rsi_exit,
        "RSI_PULLBACK_MAX": rsi_pb
    }
    holdings, summary = portfolio_analyzer.analyze_full_dhan_portfolio(overrides=overrides)
    portfolio_manager.sync_analysis_to_sheets(holdings, summary)
    return holdings, summary

holdings, summary = get_portfolio_data(target_pct, stop_loss_pct, rsi_ob, rsi_exit, rsi_pb)

# Macro Market Sentiment Banner (MDP V2 Engine)
macro = summary.get("macroRegime", {})
macro_label = macro.get("label", "⚖️ Market Sentiment: Balanced Volatility")
regime_name = macro.get("regime", "RECOVERY")
composite_score = macro.get("compositeScore", 0.0)
target_cash_pct = macro.get("targetCashPct", 0.25) * 100.0

no_trade = summary.get("noTradeFlag", False)
no_reasons = summary.get("noTradeReasons", [])

if regime_name == "BULL_RISK_ON":
    st.success(f"{macro_label} | **Full Risk-On Equity Deployment (Target Cash: {target_cash_pct:.0f}%)**")
elif regime_name == "RECOVERY":
    st.info(f"{macro_label} | **Selective Quality Deployment (Target Cash: {target_cash_pct:.0f}%)**")
elif regime_name == "CAUTIOUS":
    st.warning(f"{macro_label} | **Defensive Capital Preservation Active (Target Cash: {target_cash_pct:.0f}%)**")
else:
    st.error(f"{macro_label} | **BEAR_RISK_OFF: 100% Cash Defense Active (Target Cash: {target_cash_pct:.0f}%)**")

if no_trade:
    st.error(f"🚨 **MDP V2 EXPLICIT 'NO TRADE' DECISION ACTIVE**: New trade entries suspended. **Reason**: {' | '.join(no_reasons)}")

if dhan_client.get_holdings_source() == "CACHED":
    st.warning("⚠️ **Notice: Dhan API Access Token Expired** — Currently displaying cached holdings snapshot. To sync live Dhan portfolio, update your `DHAN_ACCESS_TOKEN` in the sidebar under **🔑 Dhan API Live Token Update**.")

# MDP V2 Dynamic Risk & Capital Metric Cards
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Total Portfolio Value", f"₹{summary.get('totalPortfolioValue', summary['totalCurrentValue']):,.2f}")
with col2:
    st.metric("Market Regime", f"{regime_name}", delta=f"Score: {composite_score:+.2f}")
with col3:
    cap_dep = summary.get("capitalDeployment", {})
    st.metric("Target Cash Position", f"{target_cash_pct:.0f}%", delta=f"₹{cap_dep.get('targetCashValue', 0.0):,.2f}")
with col4:
    st.metric("Allowed New Capital", f"₹{cap_dep.get('allowedNewCapital', 0.0):,.2f}")
with col5:
    port_risk = summary.get("portfolioRisk", {})
    st.metric("Portfolio Open Risk (VaR)", f"{port_risk.get('totalOpenRiskPct', 0.0):.1f}%", delta=f"Max 6.0% Cap")

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
        
        valid_cols = [c for c in disp_cols if c in df_display.columns]
        df_styled = df_display[valid_cols].rename(columns=df_cols_rename)
        
        st.dataframe(
            df_styled.style.map(highlight_rec, subset=["Recommendation"]),
            width="stretch",
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
                    
                    # Explicit Dhan Order Window Parameter Specifications (Mapped 1:1 to Dhan UI Tabs)
                    dp = s.get("dhanOrderParams", {})
                    rec_mode = dp.get("recommendedMode", "Limit")
                    rec_reason = dp.get("recommendedReason", "")
                    
                    st.divider()
                    st.info(f"💡 **Recommended Dhan Order Mode**: Select **`{rec_mode}`** Tab\n\n*{rec_reason}*")
                    
                    t1_lbl = "⚡ Limit (Quick Fill) ⭐ Recommended" if rec_mode == "Limit" else "⚡ Limit (Quick Fill)"
                    t2_lbl = "🛡️ SUPER (GTT Bracket) ⭐ Recommended" if rec_mode == "SUPER" else "🛡️ SUPER (GTT Bracket)"
                    t3_lbl = "🎯 TRAIL (Auto-Trailing) ⭐ Recommended" if rec_mode == "TRAIL" else "🎯 TRAIL (Auto-Trailing)"
                    
                    o_tab1, o_tab2, o_tab3 = st.tabs([t1_lbl, t2_lbl, t3_lbl])
                    
                    with o_tab1:
                        st.markdown(
                            f"**Mode**: `Investing` | **Toggle**: `{dp.get('toggle', 'Sell')}`\n\n"
                            f"• **Quantity**: `{dp.get('quantity', s['qty'])}` | **Price**: `₹{dp.get('limitPrice', s['ltp']):,.2f}` *(LTP - 0.3% Buffer)*\n"
                            f"• **Add Trigger Price**: `[Checked]` → **Trigger at**: `₹{dp.get('addTriggerPrice', s['stopLoss']):,.2f}`\n"
                            f"• **Validity**: `{dp.get('validity', 'DAY')}`"
                        )
                        
                    with o_tab2:
                        sp = dp.get("super", {})
                        st.markdown(
                            f"**Mode**: `Investing` → `⚡ SUPER` Tab | **Toggle**: `{dp.get('toggle', 'Sell')}`\n\n"
                            f"• **Quantity**: `{sp.get('quantity', s['qty'])}` | **Limit**: `[Checked: ₹{sp.get('limit', s['ltp']):,.2f}]`\n"
                            f"• **Target**: `[Checked: ₹{sp.get('target', s['targetPrice']):,.2f}]` | **Stoploss**: `[Checked: ₹{sp.get('stoploss', s['stopLoss']):,.2f}]`\n"
                            f"• **Book Profits in Steps**: `{sp.get('bookProfits', 'Full Exit')}`\n"
                            f"• **Add Trigger Price**: `[Checked: ₹{sp.get('addTriggerPrice', s['stopLoss']):,.2f}]`"
                        )
                        
                    with o_tab3:
                        tr = dp.get("trail", {})
                        st.markdown(
                            f"**Mode**: `Investing` → `⚡ TRAIL` Tab | **Toggle**: `{dp.get('toggle', 'Sell')}`\n\n"
                            f"• **Quantity**: `{tr.get('quantity', s['qty'])}` | **Limit**: `[Checked: ₹{tr.get('limit', s['ltp']):,.2f}]`\n"
                            f"• **Target**: `[Checked: ₹{tr.get('target', s['targetPrice']):,.2f}]` | **Stoploss**: `[Checked: ₹{tr.get('stoploss', s['stopLoss']):,.2f}]`\n"
                            f"• **TG Trail Jump**: `[Checked: {tr.get('tgTrailJump', 1)}]` | **SL Trail Jump**: `[Checked: {tr.get('slTrailJump', 1)}]`\n"
                            f"• **Add Trigger Price**: `[Checked: ₹{tr.get('addTriggerPrice', s['stopLoss']):,.2f}]`\n"
                            f"• **Validity of Order**: `{tr.get('orderValidity', '365 Days')}`"
                        )

                    one_url = "https://web.dhan.co"
                    if st.button(f"⚡ Execute SELL Order on Dhan", key=f"btn_sell_{s['tradingSymbol']}", use_container_width=True):
                        with st.spinner(f"Sending SELL order for {s['tradingSymbol']} ({s['qty']} qty) to Dhan..."):
                            res = dhan_client.place_dhan_order(s['tradingSymbol'], "SELL", s['qty'], s['ltp'])
                            if isinstance(res, dict) and (res.get("status") == "success" or "orderId" in str(res) or res.get("orderStatus") == "TRADED"):
                                st.success(f"✅ Order Sent to Dhan! Order ID: {res.get('orderId') or res.get('data') or 'PLACED'}")
                            elif isinstance(res, dict) and ("DH-905" in str(res) or "Invalid IP" in str(res) or res.get("error_code") == "DH-905"):
                                st.warning("⚠️ **Dhan API IP Cooldown Active**: Dhan account has a 7-day IP reset lock. You can review & execute this trade directly on **[web.dhan.co](https://web.dhan.co)** or in your Dhan Mobile App!")
                            else:
                                st.error(f"Dhan Order Response: {res}")
                    st.link_button("🌐 Open Dhan Web Portal", one_url, width="stretch")
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
                    
                    dp = a.get("dhanOrderParams", {})
                    rec_mode = dp.get("recommendedMode", "Limit")
                    rec_reason = dp.get("recommendedReason", "")
                    
                    st.divider()
                    st.info(f"💡 **Recommended Dhan Order Mode**: Select **`{rec_mode}`** Tab\n\n*{rec_reason}*")
                    
                    t1_lbl = "⚡ Limit (Quick Fill) ⭐ Recommended" if rec_mode == "Limit" else "⚡ Limit (Quick Fill)"
                    t2_lbl = "🛡️ SUPER (GTT Bracket) ⭐ Recommended" if rec_mode == "SUPER" else "🛡️ SUPER (GTT Bracket)"
                    t3_lbl = "🎯 TRAIL (Auto-Trailing) ⭐ Recommended" if rec_mode == "TRAIL" else "🎯 TRAIL (Auto-Trailing)"
                    
                    o_tab1, o_tab2, o_tab3 = st.tabs([t1_lbl, t2_lbl, t3_lbl])
                    
                    with o_tab1:
                        st.markdown(
                            f"**Mode**: `Investing` | **Toggle**: `{dp.get('toggle', 'Buy')}`\n\n"
                            f"• **Quantity**: `{dp.get('quantity', a['qty'])}` | **Price**: `₹{dp.get('limitPrice', a['ltp']):,.2f}` *(LTP + 0.3% Buffer)*\n"
                            f"• **Add Trigger Price**: `[Checked]` → **Trigger at**: `₹{dp.get('addTriggerPrice', a['stopLoss']):,.2f}`\n"
                            f"• **Validity**: `{dp.get('validity', 'DAY')}`"
                        )
                        
                    with o_tab2:
                        sp = dp.get("super", {})
                        st.markdown(
                            f"**Mode**: `Investing` → `⚡ SUPER` Tab | **Toggle**: `{dp.get('toggle', 'Buy')}`\n\n"
                            f"• **Quantity**: `{sp.get('quantity', a['qty'])}` | **Limit**: `[Checked: ₹{sp.get('limit', a['ltp']):,.2f}]`\n"
                            f"• **Target**: `[Checked: ₹{sp.get('target', a['targetPrice']):,.2f}]` | **Stoploss**: `[Checked: ₹{sp.get('stoploss', a['stopLoss']):,.2f}]`\n"
                            f"• **Book Profits in Steps**: `{sp.get('bookProfits', 'Full Exit')}`\n"
                            f"• **Add Trigger Price**: `[Checked: ₹{sp.get('addTriggerPrice', a['stopLoss']):,.2f}]`"
                        )
                        
                    with o_tab3:
                        tr = dp.get("trail", {})
                        st.markdown(
                            f"**Mode**: `Investing` → `⚡ TRAIL` Tab | **Toggle**: `{dp.get('toggle', 'Buy')}`\n\n"
                            f"• **Quantity**: `{tr.get('quantity', a['qty'])}` | **Limit**: `[Checked: ₹{tr.get('limit', a['ltp']):,.2f}]`\n"
                            f"• **Target**: `[Checked: ₹{tr.get('target', a['targetPrice']):,.2f}]` | **Stoploss**: `[Checked: ₹{tr.get('stoploss', a['stopLoss']):,.2f}]`\n"
                            f"• **TG Trail Jump**: `[Checked: {tr.get('tgTrailJump', 1)}]` | **SL Trail Jump**: `[Checked: {tr.get('slTrailJump', 1)}]`\n"
                            f"• **Add Trigger Price**: `[Checked: ₹{tr.get('addTriggerPrice', a['stopLoss']):,.2f}]`\n"
                            f"• **Validity of Order**: `{tr.get('orderValidity', '365 Days')}`"
                        )

                    one_url = "https://web.dhan.co"
                    if st.button(f"⚡ Execute BUY Order on Dhan", key=f"btn_buy_{a['tradingSymbol']}", use_container_width=True):
                        with st.spinner(f"Sending BUY order for {a['tradingSymbol']} ({a['qty']} qty) to Dhan..."):
                            res = dhan_client.place_dhan_order(a['tradingSymbol'], "BUY", a['qty'], a['ltp'])
                            if isinstance(res, dict) and (res.get("status") == "success" or "orderId" in str(res) or res.get("orderStatus") == "TRADED"):
                                st.success(f"✅ Order Sent to Dhan! Order ID: {res.get('orderId') or res.get('data') or 'PLACED'}")
                            elif isinstance(res, dict) and ("DH-905" in str(res) or "Invalid IP" in str(res) or res.get("error_code") == "DH-905"):
                                st.warning("⚠️ **Dhan API IP Cooldown Active**: Dhan account has a 7-day IP reset lock. You can review & execute this trade directly on **[web.dhan.co](https://web.dhan.co)** or in your Dhan Mobile App!")
                            else:
                                st.error(f"Dhan Order Response: {res}")
                    st.link_button("🌐 Open Dhan Web Portal", one_url, width="stretch")
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
                    
                    dp = h.get("dhanOrderParams", {})
                    with st.expander("🛡️ Dhan Protection & GTT Parameters", expanded=False):
                        tr = dp.get("trail", {})
                        st.markdown(
                            f"**Mode**: `Investing` → `⚡ TRAIL` Tab | **Toggle**: `Sell`\n\n"
                            f"• **Quantity**: `{tr.get('quantity', h['qty'])}` | **Limit**: `[Checked: ₹{tr.get('limit', h['ltp']):,.2f}]`\n"
                            f"• **Target**: `[Checked: ₹{tr.get('target', h['targetPrice']):,.2f}]` | **Stoploss**: `[Checked: ₹{tr.get('stoploss', h['stopLoss']):,.2f}]`\n"
                            f"• **TG Trail Jump**: `[Checked: {tr.get('tgTrailJump', 1)}]` | **SL Trail Jump**: `[Checked: {tr.get('slTrailJump', 1)}]`\n"
                            f"• **Validity of Order**: `365 Days`"
                        )
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
                
                st.plotly_chart(fig, width="stretch")

# TAB 4: PAPER TRADE SIMULATOR
with tab4:
    st.subheader("📝 Simulated Paper Trade Execution Engine & Performance Metrics")
    st.info("🔒 Zero real orders are placed on Dhan. All trades operate strictly in simulated paper mode.")
    
    trades_log = portfolio_manager.load_paper_trades()
    total_trades = len(trades_log)
    sells_log = [t for t in trades_log if t.get("Action") == "SELL"]
    buys_log = [t for t in trades_log if t.get("Action") in ["BUY", "AVERAGE"]]
    
    total_sim_freed = sum(float(t.get("Total Value", 0)) for t in sells_log)
    total_sim_invested = sum(float(t.get("Total Value", 0)) for t in buys_log)
    
    pcol1, pcol2, pcol3, pcol4 = st.columns(4)
    with pcol1:
        st.metric("Total Paper Trades Executed", f"{total_trades}")
    with pcol2:
        st.metric("Paper Exits Executed", f"{len(sells_log)}")
    with pcol3:
        st.metric("Freed Capital (Paper Exits)", f"₹{total_sim_freed:,.2f}")
    with pcol4:
        st.metric("Capital Reinvested (Paper Buys)", f"₹{total_sim_invested:,.2f}")
        
    st.divider()
    
    sim_col1, sim_col2, sim_col3 = st.columns(3)
    
    with sim_col1:
        st.markdown("### 🔴 Paper Exit (SELL)")
        sell_candidates = [h for h in holdings if h["recommendation"] == "SELL"] or holdings
        selected_sell_sym = st.selectbox("Select Holding to Paper Sell", [h["tradingSymbol"] for h in sell_candidates], key="paper_sell_sym")
        
        target_sell_item = next((h for h in holdings if h["tradingSymbol"] == selected_sell_sym), None)
        if target_sell_item:
            st.write(f"• **Available Qty**: `{target_sell_item['qty']}`")
            st.write(f"• **Current LTP**: `₹{target_sell_item['ltp']:,.2f}`")
            st.write(f"• **Estimated Capital Freed**: `₹{target_sell_item['currentValue']:,.2f}`")
            
            if st.button("🔥 Execute Paper Sell Transaction", type="primary", key="btn_exec_sell"):
                portfolio_manager.record_paper_trade(
                    symbol=selected_sell_sym,
                    action="SELL",
                    qty=target_sell_item["qty"],
                    price=target_sell_item["ltp"],
                    total_val=target_sell_item["currentValue"],
                    rationale="Paper sell executed via dashboard"
                )
                st.toast(f"Successfully recorded paper sell for {selected_sell_sym}!", icon="🔥")
                st.rerun()

    with sim_col2:
        st.markdown("### 🟢 Paper Accumulate (AVERAGE)")
        buy_candidates = [h for h in holdings if h["recommendation"] == "AVERAGE"] or holdings
        selected_buy_sym = st.selectbox("Select Holding to Paper Average", [h["tradingSymbol"] for h in buy_candidates], key="paper_buy_sym")
        
        target_buy_item = next((h for h in holdings if h["tradingSymbol"] == selected_buy_sym), None)
        if target_buy_item:
            add_qty = st.number_input("Additional Qty to Paper Buy", min_value=1, value=int(max(1, target_buy_item["qty"] * 0.3)))
            est_cost = add_qty * target_buy_item["ltp"]
            st.write(f"• **Current LTP**: `₹{target_buy_item['ltp']:,.2f}`")
            st.write(f"• **Total Estimated Cost**: `₹{est_cost:,.2f}`")
            
            if st.button("➕ Execute Paper Average Transaction", key="btn_exec_buy"):
                portfolio_manager.record_paper_trade(
                    symbol=selected_buy_sym,
                    action="AVERAGE",
                    qty=add_qty,
                    price=target_buy_item["ltp"],
                    total_val=est_cost,
                    rationale="Paper average executed via dashboard"
                )
                st.toast(f"Successfully recorded paper average for {selected_buy_sym}!", icon="🟢")
                st.rerun()

    with sim_col3:
        st.markdown("### ⚡ Custom Paper Order")
        custom_ticker = st.text_input("NSE Ticker (e.g. TATAMOTORS)", value="TATAMOTORS", key="custom_paper_ticker").upper().strip()
        custom_action = st.selectbox("Action", ["BUY", "SELL", "AVERAGE"], key="custom_paper_action")
        custom_qty = st.number_input("Quantity", min_value=1, value=10, key="custom_paper_qty")
        custom_price = st.number_input("Execution Price (₹)", min_value=0.1, value=500.0, step=0.5, key="custom_paper_price")
        
        if st.button("🚀 Submit Custom Paper Trade", type="primary", key="btn_exec_custom"):
            tot_val = custom_qty * custom_price
            portfolio_manager.record_paper_trade(
                symbol=custom_ticker,
                action=custom_action,
                qty=custom_qty,
                price=custom_price,
                total_val=tot_val,
                rationale=f"Custom {custom_action} simulation trade"
            )
            st.toast(f"Executed Custom Paper {custom_action} for {custom_qty} {custom_ticker} @ ₹{custom_price:,.2f}!", icon="🚀")
            st.rerun()

    st.divider()
    
    log_col1, log_col2 = st.columns([0.8, 0.2])
    with log_col1:
        st.markdown("### 📄 Paper Trade Execution History & Audit Log")
    with log_col2:
        if st.button("🗑️ Reset Paper Log", key="btn_clear_paper"):
            portfolio_manager.clear_paper_trades()
            st.toast("Paper trades log reset successfully!", icon="🧹")
            st.rerun()
            
    if trades_log:
        df_log = pd.DataFrame(trades_log)
        st.dataframe(df_log, width="stretch")
    else:
        st.caption("No paper trades logged yet. Execute paper trades above to build your simulation log.")

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
            st.plotly_chart(fig_pie, width="stretch")
        else:
            st.info("Liquidate SELL candidates to calculate recycling distribution.")

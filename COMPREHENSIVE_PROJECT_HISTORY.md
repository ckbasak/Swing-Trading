# Manage-Dhan-Portfolio: Unified Master Project History & Context

This document consolidates all conversation histories, user prompts, technical architecture specifications, code blueprints, cloud deployment guides, and bug fix logs across all project iterations into a single unified master context.

---

## 📜 Complete Chronological Conversation & Prompt History

### Session 1: Core System Architecture & 4-Strategy Foundation
- User initialized the 4 core swing trading strategies:
  1. **Strategy 1 (Mid-Cap Swing)**: High momentum mid-cap swing trading.
  2. **Strategy 2 (Sector Swing)**: Sector rotation swing trading.
  3. **Strategy 3 (Momentum Swing)**: High beta momentum breakout swing trading.
  4. **ETF Strategy (Low-Beta Swing)**: Benchmark index & commodity ETF swing trading.
- Implemented Google Sheets synchronization (`NSE_Swing_Trading_System`), DhanHQ API integration with TOTP auto-authentication, self-healing background bot supervisors (`bot.py`), and Render cloud deployments.

### Session 2: Manage-Dhan-Portfolio Specification & Creation
- **User Prompt**:
  > *"Now create another project named 'Manage-Dhan-Portfolio' to analyze my existing stocks and ETF in Dhan account and decide about sell, averaging, hold from swing trad perspective. Do not perform any real tranaction, only paper trading. Use authentication as per existing 4 projects. Create a a secure strategy as per current market situation. The money could be used for funding other four strategy."*
- **Implementation**:
  - Built `portfolio_analyzer.py`: Technical analysis engine evaluating 20-EMA, 50-SMA, 200-SMA, 14-RSI, 52W High/Low drawdown, and R:R ratios to yield **SELL**, **AVERAGE**, and **HOLD** signals.
  - Built `portfolio_manager.py`: Google Sheets manager for `NSE_Dhan_Portfolio_Manager` (worksheets: `Holdings_Analysis`, `Recommendations`, `Paper_Trades`, `Capital_Recycling_Log`).
  - Built `app.py`: Streamlit Web Dashboard with KPI metric cards, recommendation expanders, Plotly technical charts, paper trade simulator, and capital recycling planner.
  - Built `bot.py`: Telegram bot supporting push-button inline keyboards and commands (`/start`, `/portfolio`, `/rebalance`, `/recycle`, `/analyze`, `/renew`, `/status`).
  - Built `dhan_client.py`: DhanHQ API integration with realistic sample holdings fallback.

### Session 3: Relocation to Standalone Directory & Bot Hardening
- **User Prompts**:
  > *"No, you have misunderstood it. Please move it to project directory C:\Users\ckbas\Documents\antigravity\Manage-Dhan-Portfolio. And also move it to new project 'Manage-Dhan-Portfolio'. I will continue prompting from the new project 'Manage-Dhan-Portfolio' only."*
  > *"/start is not working in telegram bot"*
  > *"Merge all the three conversations of this project into this conversation and delete the old ones."*
- **Actions Executed**:
  - Relocated project into dedicated standalone folder `C:\Users\ckbas\Documents\antigravity\Manage-Dhan-Portfolio`.
  - Initialized independent Git repository.
  - Fixed `/start` bot issue: Diagnosed `409 Conflict: terminated by other getUpdates request` (duplicate bot instances). Updated `app.py` process detection logic (`get_bot_status`), updated `cmd_start` handler in `bot.py` with Markdown fallback handling, and launched single clean background daemon.
  - Consolidated all 3 conversation threads into this master context.

### Session 4: Dhan Token Auto-Renewal, TOTP Failsafe & Dynamic Order Mode Engine
- **Implementation**:
  - Implemented 12-hour automated Dhan token extension loop with 30-minute retries in `dhan_client.py`.
  - Added TOTP auto-authentication failsafe (`DHAN_TOTP_SECRET`) to seamlessly request fresh 24-hour access tokens if current token expires.
  - Implemented dynamic Dhan Order Mode recommendation engine (`Limit`, `⚡ SUPER`, `⚡ TRAIL`) mapped 1:1 to Dhan Web Order UI modal.
  - Added `⭐ Recommended` badge rendering and mode-specific parameter cards in `app.py`.
  - Added runtime cache persistence (`cached_settings.json`, `cached_holdings.json`) across Render container restarts.
  - Verified local and cloud deployment stability with automated test suite (`python -B verify_portfolio.py`).

---

## 🛠️ Master Component Architecture

```
C:\Users\ckbas\Documents\antigravity\Manage-Dhan-Portfolio\
├── app.py                      # Standalone Streamlit Web Dashboard UI
├── bot.py                      # Interactive Telegram Bot Daemon & Market Alerts
├── portfolio_analyzer.py       # Technical Decision Engine (SELL/AVERAGE/HOLD) & Order Mode Calculator
├── portfolio_manager.py        # Google Sheets Sync (NSE_Dhan_Portfolio_Manager)
├── dhan_client.py              # DhanHQ API Integration, TOTP Auto-Auth & Auto-Renewal Engine
├── renew_dhan_token.py         # Standalone Token Renewal Helper
├── run_dashboard.bat           # 1-Click Windows Dashboard Launcher
├── run_bot.bat                 # 1-Click Windows Bot Launcher
├── verify_portfolio.py         # Automated Verification Script
├── .env                        # Environment Credentials
├── service_account.json        # Google Sheets Service Account Key
├── Dockerfile                  # Container Spec
├── requirements.txt            # Python Dependencies
├── start.sh                    # Dual-Service Supervisor Script
└── render.yaml                 # Render Cloud Deployment Blueprint
```

---

## 💰 Capital Recycling Allocation Matrix

Liquid capital released from simulated paper exits (**SELL** recommendations) is mapped as follows:
- **Strategy 1 (Mid-Cap Swing)**: 30%
- **Strategy 2 (Sector Swing)**: 30%
- **Strategy 3 (Momentum Swing)**: 20%
- **ETF Strategy (Low-Beta Swing)**: 20%

---

## 🌐 Cloud & Local Deployment Guide

1. **Render Web Service (`render.com`)**:
   - Repository: `ckbasak/Swing-Trading`
   - Branch: `Manage-Dhan-Portfolio`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `./start.sh`
2. **Local Machine (Windows)**:
   - Run verification: `python -B verify_portfolio.py`
   - Run dashboard: `streamlit run app.py --server.port 8501`
   - Run bot daemon: `python -B bot.py`


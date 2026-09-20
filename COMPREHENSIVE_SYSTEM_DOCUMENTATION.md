# AI Swing Trade: 24x7 Cloud System Documentation & Operational Manual

This manual documents the finalized **AI Swing Trade** system powering all 4 core trading strategies 24x7 on the cloud with zero local laptop dependencies.

---

## 🚀 24x7 Cloud Services & Live Endpoints

All 4 strategies are deployed on Render running Docker containers that automatically launch Streamlit web dashboards and background Telegram bot daemons (`bot.py` via `./start.sh`):

| Strategy | Cloud URL | Live HTTP Status | GitHub Branch | Render Owner |
| :--- | :--- | :--- | :--- | :--- |
| **Strategy 1 (Mid-Cap)** | [https://swing-trading-strategy-1.onrender.com](https://swing-trading-strategy-1.onrender.com) | 🟢 **200 OK** | `master-unified` | `ckbasak+st1@gmail.com` |
| **Strategy 2 (Sector)** | [https://swing-trading-strategy-2.onrender.com](https://swing-trading-strategy-2.onrender.com) | 🟢 **200 OK** | `master-unified` | Default Workspace |
| **Strategy 3 (Momentum)** | [https://swing-trading-strategy-3.onrender.com](https://swing-trading-strategy-3.onrender.com) | 🟢 **200 OK** | `master-unified` | `ckbasak+st3@gmail.com` |
| **ETF Strategy (Low-Beta)** | [https://etf-strategy.onrender.com](https://etf-strategy.onrender.com) | 🟢 **200 OK** | `master-unified` | Default Workspace |

---

## 🤖 24x7 Automated Telegram Bots & Market Alerts

Each strategy runs its own self-healing Telegram bot supervisor that continuously polls Telegram commands and executes automated market hours alert scans (Mon-Fri 09:15–15:30 IST):

- **Slash Commands**: `/start`, `/portfolio`, `/rebalance`, `/recycle`, `/analyze`, `/renew`, `/status`.
- **Automated Market Scan**: Every 15 minutes during market hours, the bot scans live prices, evaluates buy/sell signals, syncs to Google Sheets (`NSE_Swing_Trading_System`), and sends interactive alert messages with 1-click trade buttons.
- **Fail-safe Auto-Restart**: Each strategy's `app.py` features `_ensure_bot_running()` to guarantee continuous uptime.

---

## 📊 Google Sheets Data Hub

All 4 strategies synchronize real-time portfolio metrics, recommendations, trade execution logs, and backtest results into Google Sheets:

- **Spreadsheet Title**: `NSE_Swing_Trading_System`
- **Worksheets**: `Holdings`, `Recommendations`, `Trades_Log`, `Performance_Summary`
- **Rate Limit Protection**: Built-in exponential backoff retry mechanism (`retry_gspread`).

---

## 📁 Repository Directory Structure

```
C:\Users\ckbas\Documents\antigravity\AI-Swing-Trade\
├── strategy1/                  # Strategy 1 (Mid-Cap Swing)
│   ├── app.py, bot.py, portfolio_manager.py, dhan_client.py, screener.py
│   └── start.sh, Dockerfile, requirements.txt, Procfile, render.yaml
├── strategy2/                  # Strategy 2 (Sector Swing)
│   ├── app.py, bot.py, portfolio_manager.py, dhan_client.py, screener.py
│   └── start.sh, Dockerfile, requirements.txt, Procfile, render.yaml
├── strategy3/                  # Strategy 3 (Momentum Swing)
│   ├── app.py, bot.py, portfolio_manager.py, dhan_client.py, screener.py
│   └── start.sh, Dockerfile, requirements.txt, Procfile, render.yaml
├── strategy_etf/               # ETF Strategy (Low-Beta Swing)
│   ├── app.py, bot.py, portfolio_manager.py, dhan_client.py, screener.py
│   └── start.sh, Dockerfile, requirements.txt, Procfile, render.yaml
├── COMPREHENSIVE_SYSTEM_DOCUMENTATION.md
└── system_health_check.py
```

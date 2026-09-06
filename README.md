# 📈 AI Swing Trading System #1: Classic Breakout

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Render](https://img.shields.io/badge/Render-Live_Web_App-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://ai-swing-trade-1.onrender.com)
[![Telegram Bot](https://img.shields.io/badge/Telegram_Bot-@ai__swing__trade__1__bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/ai_swing_trade_1_bot)
[![Google Sheets](https://img.shields.io/badge/Google_Sheets-Database-34A853?style=for-the-badge&logo=googlesheets&logoColor=white)](https://docs.google.com/)
[![Gemini AI](https://img.shields.io/badge/Gemini_3.6--flash-Market_Sentiment-8E75B2?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Stateful_Workflows-FF4B4B?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)

An institutional-grade, multi-agent automated swing trading and portfolio management system designed for the **NSE Nifty 50** universe. Features LangGraph stateful workflow execution, Google Sheets cloud database, Streamlit analytics dashboard, and an interactive Telegram bot with Gemini 3.6-flash market sentiment analysis.

---

## 📑 Table of Contents
- [⚡ Key Highlights & Specifications](#-key-highlights--specifications)
- [📐 Multi-Agent Architecture](#-multi-agent-architecture)
- [🎛️ Telegram Bot Commands](#️-telegram-bot-commands-ai_swing_trade_1_bot)
- [⏰ Automated Dynamic Schedules](#-automated-cron--dynamic-google-sheets-schedules)
- [🚀 Deployment & Environment Variables](#-deployment--environment-variables)
- [💻 Local Quickstart](#-local-quickstart)

---

## 📐 Multi-Agent Architecture

```mermaid
graph TD
    Trigger([Cron Trigger / Telegram Command / Sheets Scheduler]) --> Node1[1. Sync Portfolio Node]
    
    subgraph Google Sheets Database
        Holdings[(Holdings Worksheet)]
        Account[(Account Worksheet)]
        Schedules[(Schedules Worksheet)]
        Chats[(TelegramChats Worksheet)]
    end

    Node1 <--> Holdings
    Node1 <--> Account
    Node1 --> Node2[2. Scan Market Node]
    Node2 --> Node3[3. Calculate Sizing Node]
    Node3 -->|1.0% Risk, 1:2 R:R, 20 SMA Clamped| Node4[4. Execute Trades Node]
    
    Node4 --> Holdings
    Node4 --> Account
    Node4 --> Broadcast([Telegram Bot & Streamlit Dashboard])
    
    Schedules -. Polled Every 60s .-> Node2
```

## ⚡ Key Highlights & Specifications

* **Asset Universe:** NSE Nifty 50 Constituents (.NS)
* **Price Breakout:** Today's Close $> \text{20 SMA}$ and Yesterday's Close $\le \text{20 SMA}$
* **Volume Confirmation:** Today's Volume $> 2.0\times$ 20-day Volume SMA
* **RSI Filter:** 14-period Wilder smoothed RSI between 50 and 70 (inclusive)
* **Risk Management:** 1.0% portfolio risk per trade, max 3 buys/day, 90% capital allocation cap
* **Stop-Loss Method:** Breakout 20 SMA level clamped between 3% and 15%
* **Profit Target:** Fixed 1:2 Risk-to-Reward ratio
* **Trailing Stop:** Trailed upward to 20 EMA (tightening to day low if negative news detected)
* **Market Sentiment Engine:** Google News RSS + **Gemini 3.6-flash**
* **Database:** Google Sheets (NSE_Swing_Trading_Portfolio_1) with Holdings, Account, and TelegramChats

---

## 🎛️ Telegram Bot Commands (@ai_swing_trade_1_bot)

| Command | Action / Description |
| :--- | :--- |
| **/start** | Registers chat ID with Google Sheets and shows the interactive touch menu. |
| **/menu** | Displays the main button menu ([🔍 Run Market Scan], [🌐 Market Sentiment], [📈 Open Positions], [🏦 Portfolio Summary], [📅 Scan Schedules], [🤝 Trade History]). |
| **/scan** | **Preview Mode:** Scans for breakout setups without auto-executing orders.<br>• *Market Hours (9:15 AM – 3:30 PM IST):* [🚀 Confirm & Execute Market Entry]<br>• *After Hours / Weekends:* [🌙 Confirm & Execute AMO Entry] |
| **/news** | **Global & Indian Market Analysis & Guardrails:** Comprehensive dual-scope macro analysis with color-coded guardrail actions (`🟢 ALLOW`, `🟡 SELECTIVE`, `🔴 HALT`) for breakout entries and holding stock defense. |
| **/news <TICKER>** | In-depth market & stock sentiment for any specific stock (e.g. `/news RELIANCE`, `/news TATAMOTORS`, `/news Nifty 50`). |
| **/positions** | Displays live holdings, LTP, PnL (₹ & %), trailing SL, and target. |
| **/summary** | Account breakdown: Portfolio Value, Cash, Risk per trade, and Open PnL. |
| **/schedules** | Lists all pending and active Google Sheets scan schedules with exact IST times and live DUE status. |
| **/history** | Realized PnL scorecard, win rate %, and trade history. |

---

## ⏰ Automated Cron & Dynamic Google Sheets Schedules

### 1. Dynamic Google Sheets Scheduler (`Schedules` tab)
Configure any custom or recurring scan directly in Google Sheets (**`NSE_Swing_Trading_Portfolio_1`** -> **`Schedules`** worksheet). The cloud background runner monitors this table every 60 seconds:

| Column | Supported Values | Description |
| :--- | :--- | :--- |
| **Date** | `DAILY`, `WEEKDAYS`, `TODAY`, `YYYY-MM-DD` | Recurrence rule or specific execution date. |
| **Time** | Target IST time (e.g. `09:00`, `15:25`, `18:30`) | Exact time in 24-hour Indian Standard Time. |
| **Mode** | `EXECUTE`, `PREVIEW`, `SENTIMENT` / `NEWS` | • `EXECUTE`: Automated breakout entry with Dhan broker order.<br>• `PREVIEW`: Paper/preview breakout scan only.<br>• `SENTIMENT`: Market sentiment & macro guardrails briefing. |
| **Status** | `ACTIVE`, `PENDING`, `PAUSED` | `ACTIVE` for daily recurring, `PENDING` for one-off runs. Transitions to `COMPLETED` when done. |
| **Notes** | Stock Ticker, `Nifty 50`, or leave blank | In `SENTIMENT` mode: enter a ticker (e.g. `RELIANCE`, `TCS`), `Nifty 50` for benchmark, or leave blank to scan open holdings! |

### 2. Built-in Background Automations
1. **Daily Market Close Scan (3:25 PM IST Mon–Fri):** Automatically executes qualified breakout orders into Google Sheets and tags reports as `⏰ Scheduled Daily Scan Report (Auto-Execution)`.
2. **Intraday Market Sync (Every 5 minutes, Mon–Fri 9:15 AM – 3:30 PM IST):** Trails stops upward to 20 EMA and sends instant `🔔 Intraday Exit Alert` on stop or target exits.
3. **Container Keep-Alive Pinger (Every 9 minutes):** Self-pings `/_stcore/health` to keep the Render cloud service warm 24/7.
4. **Self-Healing Supervisor Loop:** Automatically catches any rolling-deploy conflicts or Telegram polling crashes and restarts `bot.py` within 5 seconds.

---

## 🚀 Deployment & Environment Variables

Deployed on Render as a Python Web Service (**[ai-swing-trade-1.onrender.com](https://ai-swing-trade-1.onrender.com)**).

| Variable | Description |
| :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API Token from @BotFather |
| `GEMINI_API_KEY` | Google Gemini API Key for sentiment analysis |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full JSON string of Google Cloud Service Account credentials |
| `SPREADSHEET_NAME` | `NSE_Swing_Trading_Portfolio_1` |
| `DHAN_CLIENT_ID` *(Optional)* | 10-digit DhanHQ Client ID |
| `DHAN_ACCESS_TOKEN` *(Optional)* | Daily DhanHQ Access Token |

---

## 💻 Local Quickstart

### 1. Clone & Switch Branch
```bash
git clone https://github.com/ckbasak/Swing-Trading.git
cd Swing-Trading
git checkout main
```

### 2. Environment Setup
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run Web Dashboard or Bot
* **Start Streamlit Dashboard**:
  ```bash
  streamlit run app.py
  ```
* **Start Telegram Bot**:
  ```bash
  python bot.py
  ```
* **Start Production Supervisor**:
  ```bash
  sh start.sh
  ```


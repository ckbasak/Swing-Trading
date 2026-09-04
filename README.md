# 📈 System #1: Classic Breakout Quantitative Swing Trading Engine

An institutional-grade, multi-agent automated swing trading and portfolio management system designed for the **NSE Nifty 50** universe. Features LangGraph stateful workflow execution, Google Sheets cloud database, Streamlit analytics dashboard, and an interactive Telegram bot with AI news sentiment analysis.

---

## ⚡ Key Highlights & Specifications

* **Asset Universe:** NSE Nifty 50 Constituents (.NS)
* **Price Breakout:** Today's Close $> \text{20 SMA}$ and Yesterday's Close $\le \text{20 SMA}$
* **Volume Confirmation:** Today's Volume $> 2.0\times$ 20-day Volume SMA
* **RSI Filter:** 14-period Wilder smoothed RSI between 50 and 70 (inclusive)
* **Risk Management:** 1.0% portfolio risk per trade, max 3 buys/day, 90% capital allocation cap
* **Stop-Loss Method:** Breakout 20 SMA level clamped between 3% and 15%
* **Profit Target:** Fixed 1:2 Risk-to-Reward ratio
* **Trailing Stop:** Trailed upward to 20 EMA (tightening to day low if negative news detected)
* **AI Sentiment Engine:** Google News RSS + **Gemini 3.6-flash**
* **Database:** Google Sheets (NSE_Swing_Trading_Portfolio_1) with Holdings, Account, and TelegramChats

---

## 🎛️ Telegram Bot Commands (@nse_swing_123_bot)

| Command | Action / Description |
| :--- | :--- |
| **/start** | Registers chat ID with Google Sheets and shows the interactive menu. |
| **/menu** | Displays the main button menu ([🔍 Run Market Scan], [📰 AI News Sentiment], [📈 Open Positions], [🏦 Portfolio Summary], [🤝 Trade History]). |
| **/scan** | **Preview Mode:** Scans for breakout setups without auto-executing orders.<br>• *Market Hours (9:15 AM – 3:30 PM IST):* [🚀 Confirm & Execute Market Entry]<br>• *After Hours / Weekends:* [🌙 Confirm & Execute AMO Entry] |
| **/news** | **AI News Sentiment:** Analyzes news sentiment across active open holdings in portfolio (or Nifty 50 benchmark if no open positions). |
| **/news <TICKER>** | In-depth news sentiment for any specific stock (e.g. /news RELIANCE, /news TATAMOTORS). |
| **/positions** | Displays live holdings, LTP, PnL (₹ & %), trailing SL, and target. |
| **/summary** | Account breakdown: Portfolio Value, Cash, Risk per trade, and Open PnL. |
| **/history** | Realized PnL scorecard, win rate %, and trade history. |

---

## ⏰ Automated Cron Schedules

1. **Daily Breakout Scan (3:25 PM IST Mon–Fri):** Automatically executes qualified breakout orders into Google Sheets and tags reports as ⏰ Scheduled Daily Scan Report (Auto-Execution).
2. **Intraday Market Sync (Every 5 minutes, Mon–Fri 9:15 AM – 3:30 PM IST):** Trails stops upward to 20 EMA and sends instant 🔔 Intraday Exit Alert on stop or target exits.

---

## 🚀 Deployment & Environment Variables

Deployed on Render as a Python Web Service (https://swing-trading-xpmp.onrender.com).

| Variable | Description |
| :--- | :--- |
| TELEGRAM_BOT_TOKEN | Telegram Bot API Token from @BotFather |
| GEMINI_API_KEY | Google Gemini API Key for sentiment analysis |
| GOOGLE_SERVICE_ACCOUNT_JSON | Full JSON string of Google Cloud Service Account credentials |
| SPREADSHEET_NAME | NSE_Swing_Trading_Portfolio_1 |
| DHAN_CLIENT_ID *(Optional)* | 10-digit DhanHQ Client ID |
| DHAN_ACCESS_TOKEN *(Optional)* | Daily DhanHQ Access Token |

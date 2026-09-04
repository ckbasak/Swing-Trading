# 📈 System #2: Strategy v2 (Optimized) Quantitative Swing Trading Engine

An institutional-grade, multi-agent quantitative swing trading and portfolio management system optimized for the **NSE Nifty 50** universe. Features volatility-adaptive stop sizing (2× ATR), sector concentration caps, LangGraph stateful orchestration, Google Sheets database, Streamlit dashboard, and interactive Telegram bot with Gemini 3.6-flash sentiment analysis.

---

## ⚡ Strategy v2 (Optimized) Upgrades & Specifications

| Parameter | Specification | Purpose & Edge |
| :--- | :--- | :--- |
| **Asset Universe** | NSE Nifty 50 Constituents (.NS) | Institutional liquidity and minimal execution slippage |
| **Price Breakout** | Today's Close $> \text{20 SMA}$ & Yesterday $\le \text{20 SMA}$ | Early capture of upward momentum breakout |
| **Volume Confirmation** | **$> 2.5\times$ (250%)** of 20-day Volume SMA | Cuts false breakout noise; captures institutional volume accumulation |
| **RSI Filter** | 14-period Wilder smoothed RSI between 50 and 70 | Filters out overbought entries |
| **Stop-Loss Method** | **$2 \times \text{ATR}(14)$ below entry** (no fixed clamp) | Volatility-adaptive stop tailored to each stock's price behavior |
| **Profit Target** | Fixed 1:2 Risk-to-Reward ratio | Mathematical expectancy where winners are double the risk |
| **Risk per Trade** | **1.5% of total portfolio value** | Sizing up on high-conviction, lower-frequency setups |
| **Sector Limits** | **Max 3 open positions per sector** | Caps systemic correlated exposure when sector breakouts cluster |
| **Trailing Stop** | 20 EMA (tightening to day low on negative news) | Protects accumulated open gains; moves strictly upward |
| **Daily Buy Limit** | Max 3 buys/day, prioritized by volume strength | Protects against market-wide drawdown clustering |
| **Capital Allocation** | 90% Max Exposure (10% cash buffer) | Preserves liquidity buffer |
| **AI News Engine** | Google News RSS + **Gemini 3.6-flash** | Macro regime filter + micro stock catalyst assessment |
| **Database** | Google Sheets (NSE_Swing_Trading_Portfolio_2) | Completely isolated Holdings, Account, TelegramChats |

---

## 🎛️ Telegram Bot Commands (@nse_swing_v2_bot)

| Command | Action / Description |
| :--- | :--- |
| **/start** | Registers chat ID with Google Sheets and displays the interactive touch menu. |
| **/menu** | Displays the main button menu ([🔍 Run Market Scan], [📰 AI News Sentiment], [📈 Open Positions], [🏦 Portfolio Summary], [🤝 Trade History]). |
| **/scan** | **Preview Mode:** Scans Strategy v2 candidates without altering Google Sheets.<br>• *Market Hours (9:15 AM – 3:30 PM IST):* [🚀 Confirm & Execute Market Entry]<br>• *After Hours / Weekends:* [🌙 Confirm & Execute AMO Entry] |
| **/news** | **AI News Sentiment:** Analyzes news sentiment across active open holdings in Strategy #2 portfolio (or Nifty 50 benchmark if no open positions). |
| **/news <TICKER>** | In-depth news sentiment for any specific stock (e.g. /news RELIANCE, /news TATAMOTORS). |
| **/positions** | Displays live holdings, Sector, LTP, PnL (₹ & %), trailing SL (2×ATR), and target. |
| **/summary** | Account breakdown: Portfolio Value, Cash, 1.5% Risk per trade, and Open PnL. |
| **/history** | Realized PnL scorecard, win rate %, and trade history with sectors. |

---

## ⏰ Automated Cron Schedules

1. **Daily Breakout Scan (3:25 PM IST Mon–Fri):** Automatically executes qualified breakout orders into Google Sheets and tags reports as ⏰ Scheduled Daily Scan Report (Auto-Execution) — Strategy #2.
2. **Intraday Market Sync (Every 5 minutes, Mon–Fri 9:15 AM – 3:30 PM IST):** Trails stops upward to 20 EMA and sends instant 🔔 Intraday Exit Alert on stop or target exits.

---

## 🚀 Deployment & Environment Variables

Deployed on Render as a Python Web Service (https://ai-swing-trade-2.onrender.com).

| Variable | Description |
| :--- | :--- |
| TELEGRAM_BOT_TOKEN_2 or TELEGRAM_BOT_TOKEN | Dedicated Telegram Bot 2 API Token from @BotFather |
| GEMINI_API_KEY | Shared Google Gemini API Key for sentiment analysis |
| GOOGLE_SERVICE_ACCOUNT_JSON | Shared JSON string of Google Cloud Service Account credentials |
| SPREADSHEET_NAME | NSE_Swing_Trading_Portfolio_2 |
| DHAN_CLIENT_ID *(Optional)* | 10-digit DhanHQ Client ID |
| DHAN_ACCESS_TOKEN *(Optional)* | Daily DhanHQ Access Token |

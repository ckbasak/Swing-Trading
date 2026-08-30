# NSE Swing Trading System: Comprehensive Documentation

This blueprint holds the comprehensive developer documentation, step-by-step setup guides, active configurations, credentials catalog, performance metrics calculation models, AI news sentiment filters, system guardrails, and the universal Master Prompt. This file acts as the primary master manual to recreate or migrate this system on any other AI coding platform.

---

## 📐 1. Architecture & Workflow Design

The system is designed as a stateful, event-driven workflow using **LangGraph**. It manages tasks across four distinct execution nodes:

```mermaid
graph TD
    A([Start: Cron Trigger]) --> B[Sync Portfolio]
    B --> C[Scan Market]
    C --> D[Calculate Sizing]
    D --> E[Execute Trades]
    E --> F([End: Status Sent to Telegram])
    
    subgraph Database Integration
        B <--> G[(Google Sheets)]
        E --> G
    end
    
    subgraph Data & AI Sentiment Feeds
        B <-- Live Prices & EMA --> I[Yahoo Finance Client]
        C <-- Historical Data SMA --> I
        B <-- News Sentiment --> J[Gemini 3.6-flash AI Client]
        C <-- News Sentiment --> J
    end
```

### Core Logic Nodes:
1. **`Sync Portfolio` (Exits, Trailing Stops, & Performance Analytics):**
   * Connects to **Yahoo Finance** to fetch current prices for all open positions.
   * Compares prices against targets (1:2 R:R) and stop losses (Current SL). If breached, it closes the trade, updates available cash, and logs exits.
   * Checks Google News RSS feed headlines for active holdings and uses **Gemini 3.6-flash** to score the news sentiment.
   * If sentiment is **NEGATIVE** (earnings shock, regulatory probe, etc.), it automatically tightens the trailing stop loss to **today's Low** to protect capital.
   * Compares the close against the rising **20 EMA**. If the 20 EMA exceeds the current stop loss, it trails the stop loss upward.
   * Computes portfolio performance analytics: **Total Return (%)**, **CAGR (%)**, and **XIRR (%)** based on the `"Initial Capital"` parameter in sheets and the earliest trade date.
2. **`Scan Market` (Breakout Screener & News Filter):**
   * Downloads the official active Nifty 50 ticker list from NSE.
   * Queries yfinance for daily historical candles and checks for breakout signals.
   * Checks **Nifty 50 Index News Sentiment**. If it is **NEGATIVE** (macro panic), all breakout entry buying is disabled for the day.
   * For individual breakout candidates, checks stock-specific news. If sentiment is **NEGATIVE**, the candidate is skipped.
3. **`Calculate Sizing` (Risk Manager & Exposure Guardrails):**
   * Reads account details. Sizes entries so that the maximum loss is exactly **1% of total portfolio value**.
   * Scales position quantities down if cash is scarce, or skips candidates if cash is exhausted.
   * Applies the **Max 90% Portfolio Exposure** guardrail (ensuring at least 10% cash is kept).
   * Applies the **Max 3 Daily Purchases** limit, selecting the candidates with the highest volume breakout ratios first.
4. **`Execute Trades` (Execution & Broadcasting):**
   * Commits buy orders to Google Sheets and broadcasts ASCII tables to Telegram.

---

## 🗄️ 2. Google Sheets Database Schema

The system utilizes Google Sheets as a relational database containing three worksheets:

### Worksheet 1: `"Holdings"` (14 Columns)
Holds every open and closed position ledger:
* **Col 1 (Ticker):** Yahoo Finance Symbol (e.g. `HDFCBANK.NS`)
* **Col 2 (Entry Date):** YYYY-MM-DD
* **Col 3 (Entry Price):** Close price on entry day
* **Col 4 (Quantity):** Shares purchased
* **Col 5 (Entry Value):** `Quantity * Entry Price`
* **Col 6 (Initial SL):** Breakout 20 SMA value
* **Col 7 (Current SL):** Trailing stop loss (20 EMA)
* **Col 8 (Target):** Profit target (1:2 R:R)
* **Col 9 (Status):** `OPEN` or `CLOSED`
* **Col 10 (Exit Date):** YYYY-MM-DD of exit
* **Col 11 (Exit Price):** Realized exit price
* **Col 12 (Exit Value):** `Quantity * Exit Price`
* **Col 13 (PnL):** Realized profit/loss (`Exit Value - Entry Value`)
* **Col 14 (Exit Reason):** `Target Hit`, `Stop Loss Hit`, or `Manual Exit`

### Worksheet 2: `"Account"` (2 Columns)
Stores parameters: 
* `Total Portfolio Value`: Current value of cash + open holdings.
* `Cash Balance`: Available cash.
* `Risk Percent`: Sizing risk per trade (e.g. `0.01` for 1%).
* `Initial Capital`: Setup deposits (defaults to `1000000` / 10 Lacs). **You can change this value in your sheet to customize your CAGR/XIRR baseline.**

### Worksheet 3: `"TelegramChats"` (1 Column)
Stores registered `ChatID` entries to receive daily broadcast scans.

---

## 🛡️ 3. System-Wide Guardrails System

The following programmatic safety filters are hardcoded into the execution cycle:

| Guardrail Name | Scope | Operational Threshold | Purpose |
| :--- | :--- | :--- | :--- |
| **Double Buy Blocker** | Portfolio | Block addition of duplicate tickers | Prevents over-exposure to a single stock |
| **Max Portfolio Allocation** | Portfolio | Limits open positions value to **90%** | Guarantees minimum **10% cash** reserves |
| **Max Daily Purchases** | Sizer | Maximum **3 buys** per scan | Prevents capital exhaustion on massive breakout days |
| **SL Tightness Guard** | Sizer | Stop Loss must be **>= 3% below Entry** | Prevents immediate stops due to minor price noise |
| **SL Bloat Guard** | Sizer | Stop Loss must be **<= 15% below Entry** | Discards high-risk, overly bloated breakout trades |
| **API Retry Session** | Connection | HTTPAdapter with exponential backoff | Avoids yfinance 429 rate limits and IP bans |
| **Sheet Write Backoff** | Database | 2-second sleep retry on gspread calls | Recovers gracefully from Google API rate limits |
| **Penny Stock Filter** | Screener | Close Price must be **>= Rs 20** | Filters out micro-cap pump-and-dump stocks |
| **Liquidity Filter** | Screener | 20-day Volume SMA must be **>= 50,000** | Protects against low-liquidity slippage traps |

---

## 📋 4. Credentials & Connection Configuration Catalog

| System / Provider | Parameter Name | Credential Value / Token ID |
| :--- | :--- | :--- |
| **Telegram Bot** | Bot Token API Key | *[Telegram Bot Token]* |
| **Telegram Bot** | Bot Username / Link | `@nse_swing_123_bot` (https://t.me/nse_swing_123_bot) |
| **Render Cloud** | REST API Key | *[Render API Key]* |
| **Render Cloud** | Service ID | `srv-da86e4ugekts73ccfr20` |
| **Render Cloud** | Owner ID | `tea-da7jlaajnfac738kogrg` |
| **Render Cloud** | Public Service Web URL | `https://nse-swing-trading.onrender.com` |
| **Google Sheets** | Service Account Email | `sheets-editor@swing-trade-system-506815.iam.gserviceaccount.com` |
| **Google Sheets** | Database Sheet Name | `NSE_Swing_Trading_Portfolio` |
| **Gemini AI** | Gemini Pro API Key | *[Gemini API Key]* |
| **GitHub Repo** | Git Code Repository | `https://github.com/ckbas/Swing-Trading.git` |

---

## 🛠️ 5. Step-by-Step Setup Guide

### Step 1: Google Sheets & Service Account
1. Create a Google Sheet named **`NSE_Swing_Trading_Portfolio`**.
2. Go to the Google Cloud Console, enable Drive & Sheets APIs, create a Service Account, and download the JSON key.
3. Share the Google Sheet with the Service Account email.

### Step 2: Telegram Bot Creation
1. Message `@BotFather` on Telegram, send `/newbot`, and copy the **Bot Token API Key**.

### Step 3: Render Cloud Deployment
1. Create a Web Service on Render connected to your GitHub repository.
2. Select **Python** as the environment, set the Build Command to `pip install -r requirements.txt`, and set the Start Command to `bash start.sh`.
3. In the **Environment** tab, click **Add Env Variable and input:**
   * `GOOGLE_SERVICE_ACCOUNT_JSON` = *[Paste contents of service_account.json]*
   * `TELEGRAM_BOT_TOKEN` = `[Your Telegram Bot Token]`
   * `GEMINI_API_KEY` = `[Your Gemini API Key]`
4. Save and deploy. Set up a free HTTPS pinger on **UptimeRobot** pointing to your Render URL.

---

## 🔮 6. Universal Master Prompt (To Recreate This System)

*Copy-paste the prompt below into any coding AI agent to build the exact same codebase from scratch in a single go:*

```text
Build a complete, production-grade NSE Swing Trading & Portfolio Manager in Python, ready to deploy to Render (Free Tier). The system must run a Streamlit web dashboard and a Telegram bot concurrently inside a single container. The database must be Google Sheets (managed via gspread).

Here are the specifications:

1. FILE STRUCTURE & RESPONSIBILITIES:
Create the following files:
- `sentiment_analyzer.py`: Connects to Google News RSS search feed for a ticker or macro index, parses XML for the top 5 recent headlines, and calls Gemini model "gemini-3.6-flash" to return 'POSITIVE', 'NEUTRAL', or 'NEGATIVE' sentiment.
- `screener.py`: Fetches Nifty 50 symbols from NSE, downloads 60d daily historical data in parallel via yfinance, and filters for breakouts. Before screening breakout stocks, check "Nifty 50 Index India" sentiment; if NEGATIVE, skip all buys. For candidate breakouts, check specific stock sentiment; if NEGATIVE, skip. Filters out penny stocks (Price < 20) and low-volume stocks (Vol SMA 20 < 50,000). Uses HTTPAdapter with exponential retry strategy.
- `portfolio_manager.py`: Google Sheets database operations. Handles sheets initialization, fetching open/closed positions, registering chat IDs, adding positions, closing positions, calculating performance metrics (Total Return, CAGR, XIRR), and syncing live quotes/EMA from yfinance. In sync_portfolio, if news sentiment for a held ticker is NEGATIVE, tighten the Stop Loss to max(current_sl, today's Low). Implements retry_gspread for 429 rate limit backoff. In add_position, blocks duplicates and checks that Stop Loss percentage is between 3% and 15% of entry price.
- `trading_graph.py`: Builds a stateful LangGraph workflow representing the trading cycle (Sync Portfolio -> Scan Market -> Position Sizer -> Execute Trades) and formats a text-based ASCII scan report. In the sizer node, enforces a maximum portfolio exposure of 90% (minimum 10% kept in cash) and a maximum daily purchase limit of 3 stocks (strongest volume breakouts first).
- `bot.py`: Telegram Bot handler and cron scheduler. Implements command callbacks and background jobs.
- `app.py`: Streamlit frontend dashboard displaying KPI cards for Value, Cash, Unrealized/Realized PnL, Total Return, CAGR, and XIRR.
- `start.sh`: Shell script launching `python -u bot.py &` in the background and `streamlit run` in the foreground.
- `Procfile`: Contains `web: sh start.sh`
- `requirements.txt`: Project dependencies (yfinance, gspread, google-auth, langgraph, streamlit, python-telegram-bot, google-generativeai, pytz).

2. STRATEGY SPECIFICATIONS:
- Tickers: Nifty 50 Index (fetched from 'https://archives.nseindia.com/content/indices/ind_nifty50list.csv'). Symbol suffix is '.NS'.
- Entry Conditions:
  - Price breakout: Today's Close > Today's 20 SMA AND Yesterday's Close <= Yesterday's 20 SMA.
  - Volume breakout: Today's Volume > 2.0 * 20-day Volume SMA.
  - RSI Filter: Today's 14-period RSI (Wilder's smoothed) must be between 50 and 70 (inclusive).
- Exit Conditions:
  - Target: Entry Price + 2 * (Entry Price - Initial SL) [1:2 Risk-to-Reward Ratio].
  - Trailing Stop: 20 EMA (Exponential Moving Average). Move Stop Loss up to 20 EMA if 20 EMA is greater than current SL. SL never moves down. Exit trade if daily close closes <= Current SL.

3. GOOGLE SHEETS SCHEMAS:
Create the sheet 'NSE_Swing_Trading_Portfolio' with the following tabs:
- 'Holdings' (14 Columns): Ticker, Entry Date, Entry Price, Quantity, Entry Value, Initial SL, Current SL, Target, Status, Exit Date, Exit Price, Exit Value, PnL, Exit Reason.
- 'Account' (2 Columns): Parameter (Total Portfolio Value, Cash Balance, Risk Percent, Initial Capital) and Value.
- 'TelegramChats' (1 Column): ChatID.

4. RISK MANAGEMENT & SIZING:
- Risk Amount: 1% of 'Total Portfolio Value' from the Account sheet.
- Quantity: Risk Amount / (Entry Price - Initial SL).
- Capital Scaling: If the purchase cost (Quantity * Entry Price) exceeds available cash, scale the quantity down to fit the cash. If cash is insufficient to buy even 1 share, skip the trade.

5. BOT COMMANDS & ASCI TABLES:
- `/start`: Registers chat ID.
- `/positions` or `/position`: Fetches holdings, queries live prices from yfinance, and outputs two monospaced ASCII tables inside ``` blocks:
  1. Prices & PnL Table: Ticker | Qty | Entry | Current | PnL%
  2. Risk & Targets Table: Ticker | SL | Target | EntryVal
- `/scan`: Triggers a manual scan and sends the formatted ASCII tables.
- `/summary`: Outputs cash balance, open positions count, realized PnL, Total Return, CAGR, and XIRR.

6. CRON SCHEDULES (IST TIMEZONE):
- Intraday Exits Sync: Run a repeating job every 5 minutes (300 seconds) on weekdays between 9:15 AM and 3:30 PM IST. Fetch live prices of open holdings, check for Target/SL breaches, close them in the sheet if hit, and send an instant Telegram alert.
- Daily Buy Scan: Run a daily scan job at 3:25 PM IST (5 minutes before market close) on weekdays. Scan the market, size positions, execute them in the sheet, and broadcast the candidates & purchases report.

7. RATE-LIMIT BYPASSING & SECURITY:
Configure yfinance downloads to use a requests Session with a custom browser headers dictionary. All credentials (Google Service Account JSON, Telegram Bot Token, Gemini API Key) must be loaded dynamically from environment variables.
```

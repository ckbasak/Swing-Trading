# NSE Swing Trading & Portfolio Management System: Final Master Operations Manual & Technical Blueprint

This blueprint is the exhaustive master reference manual for the automated NSE Swing Trading and Portfolio Management System. It contains the complete architectural layouts, database schemas, quantitative strategy rules, AI news sentiment guardrails, DhanHQ broker API configurations, memory management protocols, interactive Telegram menu systems, credentials catalog, and the Universal Master Prompt.

---

## 📐 1. System Architecture & Workflow Pipeline

The application is structured as a stateful, event-driven quantitative engine orchestrated via **LangGraph**. It coordinates multi-step decision workflows across four core processing nodes:

```mermaid
graph TD
    A([Start: Cron Trigger or Interactive Command]) --> B[Node 1: Sync Portfolio]
    B --> C[Node 2: Scan Market]
    C --> D[Node 3: Calculate Sizing]
    D --> E[Node 4: Execute Trades]
    E --> F([End: Broadcast Report to Telegram & Update Streamlit])
    
    subgraph Google Sheets Database
        B <--> G[(Worksheet: Holdings)]
        B <--> H[(Worksheet: Account)]
        E --> G
        E --> H
    end
    
    subgraph Market Data & Broker Feeds
        B <-- Real-Time Quotes --> I[DhanHQ Broker API]
        B <-- Historical 20 EMA Fallback --> J[Yahoo Finance Client]
        C <-- 60d Daily Candles SMA/RSI --> J
        B <-- Live News Headlines --> K[Gemini 3.6-flash AI Engine]
        C <-- Macro / Stock News --> K
    end
```

### Execution Nodes Breakdown:

1. **`Sync Portfolio Node` (Live Price Stream, Exits & Trailing Stops):**
   * Connects to **DhanHQ API** (`dhan_client.py`) to query real-time tick prices (LTP) for all open positions. If Dhan credentials are unset or the token expires, automatically falls back to **Yahoo Finance** (`yfinance`).
   * Evaluates exit conditions:
     * **Target Hit:** If `Live Price >= Target` (1:2 Risk-to-Reward Ratio), closes the position, calculates realized profit/loss, updates cash balance, and logs `Closed trade @ Exit Price (Reason: Target Hit, PnL: ₹... / +...%)`.
     * **Stop Loss Hit:** If `Live Price <= Current SL`, closes the position, calculates realized loss, updates cash balance, and logs `Closed trade @ Exit Price (Reason: Stop Loss Hit, PnL: ₹... / -...%)`.
   * **AI News Sentiment Guardrail (Micro):** Queries Google News RSS for news headlines on the held stock and invokes **Gemini 3.6-flash**. If news sentiment is **NEGATIVE** (e.g., earnings miss, regulatory penalty), the trailing stop loss is immediately tightened to **today's Low** to protect capital against sudden market dumps.
   * **Dynamic Trailing Stop (20 EMA):** If close price is favorable, calculates the 20-day Exponential Moving Average (20 EMA). If `20 EMA > Current SL`, updates `Current SL` in Google Sheets to `20 EMA` (Stop loss trails upward and never moves downward).
   * **Performance Tracking:** Dynamically solves for **Total Return (%)**, **CAGR (%)**, and **XIRR (%)** across active trading days.

2. **`Scan Market Node` (Breakout Screener & Macro AI News Filter):**
   * Downloads the active Nifty 50 constituent list directly from NSE Archives.
   * Downloads 60 days of daily historical OHLCV data using session retry adapters.
   * **AI News Sentiment Guardrail (Macro):** Queries news for `"Nifty 50 Index India"` and calls **Gemini 3.6-flash**. If macro sentiment is **NEGATIVE** (e.g., market-wide selloff, geopolitical panic), disables all new breakout entries for the day and logs a clear warning notice.
   * Identifies quantitative breakout candidates meeting all 3 criteria:
     1. **Price Breakout:** Today's Close > Today's 20 SMA AND Yesterday's Close <= Yesterday's 20 SMA.
     2. **Volume Confirmation:** Today's Volume > 2.0 * 20-day Volume SMA.
     3. **RSI Filter:** Today's 14-period RSI (Wilder's smoothed) is between 50 and 70 (inclusive).
   * For qualifying breakout candidates, verifies individual stock news sentiment; discards candidates with **NEGATIVE** sentiment.

3. **`Calculate Sizing Node` (Risk Management & Exposure Guardrails):**
   * Enforces strict **1% Risk-per-Trade sizing**:
     $$	ext{Quantity} = \left\lfloor rac{	ext{Total Portfolio Value} 	imes 0.01}{	ext{Entry Price} - 	ext{Initial SL}} ightfloor$$
   * **Double Buy Blocker:** Rejects candidates that already exist as active `OPEN` positions in Google Sheets.
   * **Stop Loss Distance Validation:** Verifies that the initial Stop Loss is between **3% and 15%** of the Entry Price (discards noise-prone tight stops and high-risk wide stops).
   * **90% Max Portfolio Allocation (10% Cash Buffer):** Limits total open position value to **90% of total portfolio value**, scaling down purchase quantities or skipping entries if cash is insufficient.
   * **Daily Purchase Limit:** Limits new entries to a **maximum of 3 buys per day**, prioritizing the candidates with the highest volume breakout ratios first.

4. **`Execute Trades Node` (Database Commit & Notifications):**
   * Appends executed trades into the Google Sheets `"Holdings"` worksheet with exponential rate-limit backoffs.
   * Formats ASCII monospaced summary tables and broadcasts real-time reports to registered Telegram chats.

---

## 🗄️ 2. Google Sheets Database Schema

The database is hosted on Google Sheets under the spreadsheet name **`NSE_Swing_Trading_Portfolio`**.

### Worksheet 1: `"Holdings"` (14 Relational Columns)
| Col Index | Header Name | Data Type | Description |
| :---: | :--- | :--- | :--- |
| **1** | `Ticker` | String | NSE symbol with `.NS` suffix (e.g. `HDFCBANK.NS`) |
| **2** | `Entry Date` | Date (YYYY-MM-DD) | Date when position was opened |
| **3** | `Entry Price` | Float | Execution entry price |
| **4** | `Quantity` | Integer | Total shares held |
| **5** | `Entry Value` | Float | `Quantity * Entry Price` |
| **6** | `Initial SL` | Float | Breakout 20 SMA value at entry |
| **7** | `Current SL` | Float | Trailing stop loss (trailed to 20 EMA) |
| **8** | `Target` | Float | Profit target (1:2 Risk-to-Reward Ratio) |
| **9** | `Status` | String | `OPEN` or `CLOSED` |
| **10** | `Exit Date` | Date (YYYY-MM-DD) | Date when position was closed |
| **11** | `Exit Price` | Float | Realized exit execution price |
| **12** | `Exit Value` | Float | `Quantity * Exit Price` |
| **13** | `PnL` | Float | Realized profit/loss (`Exit Value - Entry Value`) |
| **14** | `Exit Reason` | String | `Target Hit`, `Stop Loss Hit`, or `Manual Exit` |

### Worksheet 2: `"Account"` (2 Columns)
| Parameter | Default / Format | Description |
| :--- | :--- | :--- |
| `Total Portfolio Value` | Float (e.g. `1000000.00`) | Cash Balance + Current Value of Open Positions |
| `Cash Balance` | Float (e.g. `1000000.00`) | Liquid unallocated cash available for trading |
| `Risk Percent` | Float (`0.01`) | Risk percentage per trade (1%) |
| `Initial Capital` | Float (`1000000.00`) | Capital baseline for CAGR & XIRR calculations |

### Worksheet 3: `"TelegramChats"` (1 Column)
| Parameter | Description |
| :--- | :--- |
| `ChatID` | Registered Telegram Chat IDs that receive automated daily alerts and exit triggers |

---

## 🛡️ 3. Comprehensive System Guardrails Matrix

| Guardrail Name | Scope | Operational Mechanism | Risk Mitigated |
| :--- | :--- | :--- | :--- |
| **DhanHQ Fallback Engine** | Data Feed | Automatic fallback to `yfinance` if credentials expire or network times out | Prevents bot crashes & downtime |
| **Double Buy Blocker** | Portfolio | Checks database and rejects duplicate ticker purchases | Prevents single-stock overexposure |
| **Max Portfolio Allocation** | Portfolio | Restricts open holdings to **90% of total portfolio value** | Guarantees **minimum 10% cash buffer** |
| **Daily Purchase Limit** | Sizer | Maximum **3 breakout buys** per scan (highest volume ratio first) | Prevents capital exhaustion on bullish days |
| **SL Tightness Guard** | Sizer | Rejects entries where Stop Loss distance is **< 3%** | Prevents premature stops from daily noise |
| **SL Bloat Guard** | Sizer | Rejects entries where Stop Loss distance is **> 15%** | Discards bloated, high-risk trades |
| **Penny Stock Filter** | Screener | Discards stocks priced **< ₹20** | Filters micro-cap pump-and-dump stocks |
| **Liquidity Filter** | Screener | Discards stocks with 20-day Volume SMA **< 50,000 shares** | Eliminates low-liquidity slippage traps |
| **Google Sheets 429 Retry** | Database | 2-second exponential sleep retry on `429 Too Many Requests` | Prevents quota exhaustion crashes |
| **Memory Leak Guard** | Runtime | Disables multithreading, clears TZ cache, forces `gc.collect()` | Prevents Render Free Tier 512MB RAM restarts |

---

## 🎛️ 4. Telegram Bot Commands & Interactive Menu System

The Telegram Bot (`@nse_swing_123_bot`) features an interactive touch menu and a native command menu bar:

### Native Menu Bar (`[/]` Popup):
* `🎛️ /menu` — Displays the interactive touch button hub.
* `🔍 /scan` — Runs an immediate breakout scan, checks AI sentiment, and executes trades.
* `📈 /positions` — Displays open positions with real-time Dhan/Yahoo tick quotes, SL, Target, and Unrealized PnL.
* `🤝 /history` — Displays all closed trades with Entry, Exit, Realized PnL (₹), and **`PnL %`**.
* `🏦 /summary` — Summarizes Portfolio Value, Cash, Realized PnL, Win Rate %, Total Return %, CAGR %, and XIRR %.
* `🚀 /start` — Welcome guide and dynamic chat registration.

### Interactive Button Hub:
```text
┌───────────────────────────────┬───────────────────────────────┐
│     🔍 Run Market Scan        │       📈 Open Positions       │
├───────────────────────────────┼───────────────────────────────┤
│     🤝 Trade History          │       🏦 Portfolio Summary    │
└───────────────────────────────┴───────────────────────────────┘
```

---

## 🔑 5. Credentials & Environment Variables Catalog

| Provider | Environment Variable | Value / Description | Where to Set |
| :--- | :--- | :--- | :--- |
| **Dhan Broker** | `DHAN_CLIENT_ID` | Your 10-digit Dhan Client ID | Render Environment |
| **Dhan Broker** | `DHAN_ACCESS_TOKEN` | Generated from Dhan Web > Profile > DhanHQ APIs | Render Environment |
| **Telegram Bot** | `TELEGRAM_BOT_TOKEN` | `8723012283:AAFuddRfXL3-VNbeCdRRwKwoZ3438FaV0uo` | Render Environment |
| **Telegram Bot** | Bot Username | `@nse_swing_123_bot` | Telegram App |
| **Render Cloud** | Service ID | `srv-da86e4ugekts73ccfr20` | Render Dashboard |
| **Render Cloud** | Public Web URL | `https://nse-swing-trading.onrender.com` | Browser / UptimeRobot |
| **Google Sheets** | `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON content of `service_account.json` | Render Environment |
| **Google Sheets** | Service Account Email | `sheets-editor@swing-trade-system-506815.iam.gserviceaccount.com` | Google Cloud IAM |
| **Google Sheets** | Sheet Name | `NSE_Swing_Trading_Portfolio` | Google Drive |
| **Gemini AI** | `GEMINI_API_KEY` | `[Your Gemini API Key]` | Render Environment |
| **GitHub Repo** | Code Repository | `https://github.com/ckbas/Swing-Trading.git` | GitHub |

---

## 🔮 6. Universal Master Prompt (For Recreating System Anywhere)

```text
Build a complete, production-grade NSE Swing Trading & Portfolio Manager in Python, ready to deploy to Render (Free Tier). The system must run a Streamlit web dashboard and a Telegram bot concurrently inside a single container. The database must be Google Sheets (managed via gspread).

1. FILE STRUCTURE & RESPONSIBILITIES:
- `dhan_client.py`: Integrates DhanHQ API ('dhanhq'). Downloads and caches the Dhan NSE Scrip Master CSV ('https://images.dhan.co/api-data/api-scrip-master.csv') in memory to map symbols (e.g. 'RELIANCE' -> 2885). Provides get_dhan_ltp(tickers) for zero-latency live quotes with graceful fallback to yfinance if unconfigured.
- `sentiment_analyzer.py`: Connects to Google News RSS search feed for a ticker or macro index, parses XML for the top 5 recent headlines, and calls Gemini model "gemini-3.6-flash" to return 'POSITIVE', 'NEUTRAL', or 'NEGATIVE' sentiment.
- `screener.py`: Fetches Nifty 50 symbols from NSE, downloads 60d daily historical data in parallel via yfinance, and filters for breakouts. Checks macro and stock-specific news sentiment before qualifying candidates. Filters out penny stocks (Price < 20) and low-volume stocks (Vol SMA 20 < 50,000).
- `portfolio_manager.py`: Google Sheets database operations. Handles sheets initialization, fetching open/closed positions, registering chat IDs, adding positions, closing positions, calculating performance metrics (Total Return, CAGR, XIRR, PnL %), and syncing live quotes from DhanHQ (with yfinance fallback). Implements retry_gspread for 429 rate limit backoff. In add_position, blocks duplicates and checks Stop Loss percentage (3% - 15%).
- `trading_graph.py`: Builds a stateful LangGraph workflow representing the trading cycle (Sync Portfolio -> Scan Market -> Position Sizer -> Execute Trades) and formats a text-based ASCII scan report. Sizer enforces max 90% portfolio exposure (10% cash buffer), max 3 daily purchases, and minimum 3% SL buffer.
- `bot.py`: Telegram Bot handler and cron scheduler. Implements interactive InlineKeyboardMarkup button menus, native BotCommand menu registration, and commands (/menu, /scan, /positions, /history, /summary, /start).
- `app.py`: Streamlit frontend dashboard displaying KPI cards for Value, Cash, Unrealized/Realized PnL, Total Return, CAGR, XIRR, Closed Trades table with PnL % and win rate metrics, and Plotly charts.
- `start.sh`: Shell script launching `python -u bot.py &` in the background and `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.fileWatcherType none --server.headless true` in the foreground.
- `Procfile`: Contains `web: sh start.sh`
- `requirements.txt`: Dependencies (streamlit, python-telegram-bot[all], gspread, google-auth, yfinance, pandas, numpy, langgraph, pytz, plotly, requests, google-generativeai, dhanhq).

2. STRATEGY SPECIFICATIONS:
- Tickers: Nifty 50 Index (fetched from 'https://archives.nseindia.com/content/indices/ind_nifty50list.csv'). Symbol suffix is '.NS'.
- Entry Conditions:
  - Price breakout: Today's Close > Today's 20 SMA AND Yesterday's Close <= Yesterday's 20 SMA.
  - Volume breakout: Today's Volume > 2.0 * 20-day Volume SMA.
  - RSI Filter: Today's 14-period RSI (Wilder's smoothed) must be between 50 and 70 (inclusive).
- Exit Conditions:
  - Target: Entry Price + 2 * (Entry Price - Initial SL) [1:2 Risk-to-Reward Ratio].
  - Trailing Stop: 20 EMA. Move Stop Loss up to 20 EMA if 20 EMA > current SL. Exit trade if live price <= Current SL.

3. GOOGLE SHEETS SCHEMAS:
Create 'NSE_Swing_Trading_Portfolio' with tabs:
- 'Holdings' (14 Columns): Ticker, Entry Date, Entry Price, Quantity, Entry Value, Initial SL, Current SL, Target, Status, Exit Date, Exit Price, Exit Value, PnL, Exit Reason.
- 'Account' (2 Columns): Parameter (Total Portfolio Value, Cash Balance, Risk Percent, Initial Capital) and Value.
- 'TelegramChats' (1 Column): ChatID.

4. RISK MANAGEMENT & SIZING:
- Risk Amount: 1% of 'Total Portfolio Value' from Account sheet.
- Quantity: Risk Amount / (Entry Price - Initial SL).
- Capital Scaling: Ensure max 90% allocation limit; scale down if cash insufficient. Max 3 buys per day.
```

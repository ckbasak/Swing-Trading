# AI-Swing-Trade-2: Independent System Setup & Multi-Project Architecture

This document describes how **Project 1 (`AI-Swing-Trade-1`)** and **Project 2 (`AI-Swing-Trade-2`)** run side-by-side with complete runtime, database, and Telegram bot isolation while sharing common authentication credentials.

---

## 🏛️ Multi-Project Architecture Matrix

| Component | Project 1: `AI-Swing-Trade-1` | Project 2: `AI-Swing-Trade-2` | Isolation / Sharing Mechanism |
| :--- | :--- | :--- | :--- |
| **Strategy Engine** | **Strategy v1:** 20 SMA Breakout + 2.0x Volume + 14 RSI (50-70) + 20 EMA Trailing SL + 1:2 Fixed Target | **Strategy v2:** 20 SMA Breakout + 2.5x Volume + 14 RSI + 2*ATR(14) Stop Loss + Sector Limits (Max 3/sector) | **Independent:** Code inside each project directory |
| **Google Sheets Database** | Sheet: `NSE_Swing_Trading_Portfolio_1`<br>Tabs: `Holdings`, `Account`, `TelegramChats` | Sheet: `NSE_Swing_Trading_Portfolio_2`<br>Tabs: `Holdings`, `Account`, `TelegramChats` | **Separate Google Sheets:** Each project has its own dedicated spreadsheet in Google Drive |
| **Telegram Bot** | Bot #1 (`@ai_swing_trade_1_bot` / `AI Swing Trade 1`) | Bot #2 (`@ai_swing_trade_2_bot` / `AI Swing Trade 2`) | **Isolated Bot:** Separate Bot Tokens & Handlers |
| **Streamlit Dashboard** | Title: `NSE Swing Trading Dashboard #1 (Classic Breakout)` | Title: `NSE Swing Trading Dashboard #2 (Strategy v2)` | **Independent Web App:** Distinct dashboard views & KPIs |
| **Gemini AI News Filter** | Shared `GEMINI_API_KEY` | Shared `GEMINI_API_KEY` | **Shared Credentials:** Zero redundant API keys |
| **DhanHQ Broker Quotes** | Shared `DHAN_CLIENT_ID` & `DHAN_ACCESS_TOKEN` | Shared `DHAN_CLIENT_ID` & `DHAN_ACCESS_TOKEN` | **Shared Credentials:** Single broker data feed |

---

## 🤖 1. Telegram Bots Configuration

* **Project 1 Bot**: Name: **`AI Swing Trade 1`** | Target Username: **`@ai_swing_trade_1_bot`**
* **Project 2 Bot**: Name: **`AI Swing Trade 2`** | Target Username: **`@ai_swing_trade_2_bot`**

## 🗄️ 2. Separate Google Sheets Databases

Both projects now use completely separate Google Spreadsheets in your Google Drive:

* **Project 1 Database**: **`NSE_Swing_Trading_Portfolio_1`**
  - URL: `https://docs.google.com/spreadsheets/d/1SGGgkcVqef04xHMxCpb__qFgrUGyVtsJjgvysapbb6c`
  - Worksheets: `Holdings`, `Account`, `TelegramChats`
  - Strategy: Classic Breakout (1.0% Risk)

* **Project 2 Database**: **`NSE_Swing_Trading_Portfolio_2`**
  - URL: `https://docs.google.com/spreadsheets/d/1kBLrVqC8JLNY_n_ktVKyQs9CaE6u69_3Zq6vXriLcCc`
  - Worksheets: `Holdings`, `Account`, `TelegramChats`
  - Strategy: Strategy v2 Optimized (1.5% Risk, 2× ATR Stops, Max 3/Sector)

---

## ☁️ 3. Deploying Project 2 to Render (Web Service #2)

If you wish to deploy Project 2 to Render as an independent cloud service:
1. Push `AI-Swing-Trade-2` to a new GitHub repository (e.g. `https://github.com/ckbasak/AI-Swing-Trade-2.git`) or a dedicated `strategy-2` branch.
2. In [Render Dashboard](https://dashboard.render.com), click **New +** > **Web Service**.
3. Connect your repository.
4. Set the Environment Variables:
   * `TELEGRAM_BOT_TOKEN` = `[Your Bot 2 Token]`
   * `GEMINI_API_KEY` = `[Shared Gemini Key]`
   * `GOOGLE_SERVICE_ACCOUNT_JSON` = `[Content of service_account.json]`
   * `DHAN_CLIENT_ID` = `[Shared Dhan Client ID]` (Optional)
   * `DHAN_ACCESS_TOKEN` = `[Shared Dhan Access Token]` (Optional)
5. Click **Deploy Web Service**.

Both bots and dashboards will now operate 100% autonomously without ever interfering with one another!

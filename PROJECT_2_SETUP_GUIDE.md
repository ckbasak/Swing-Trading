# AI-Swing-Trade-2: Independent System Setup & Multi-Project Architecture

This document describes how **Project 1 (`AI-Swing-Trade-1`)** and **Project 2 (`AI-Swing-Trade-2`)** run side-by-side with complete runtime, database, and Telegram bot isolation while sharing common authentication credentials.

---

## 🏛️ Multi-Project Architecture Matrix

| Component | Project 1: `AI-Swing-Trade-1` | Project 2: `AI-Swing-Trade-2` | Isolation / Sharing Mechanism |
| :--- | :--- | :--- | :--- |
| **Strategy Engine** | **Strategy v1:** 20 SMA Breakout + 2.0x Volume + 14 RSI (50-70) + 20 EMA Trailing SL + 1:2 Fixed Target | **Strategy v2:** 20 SMA Breakout + 2.5x Volume + 14 RSI + 2*ATR(14) Stop Loss + Sector Limits (Max 3/sector) | **Independent:** Code inside each project directory |
| **Google Sheets Database** | Worksheets: `Holdings`, `Account`, `TelegramChats` | Worksheets: `Holdings_v2`, `Account_v2`, `TelegramChats_v2` (or dedicated sheet `NSE_Swing_Trading_Portfolio_2`) | **Isolated Database:** Shared Google Cloud Service Account (`service_account.json`) |
| **Telegram Bot** | Bot #1 (`@ai_swing_trade_1_bot` / `AI Swing Trade 1`) | Bot #2 (`@ai_swing_trade_2_bot` / `AI Swing Trade 2`) | **Isolated Bot:** Separate Bot Tokens & Handlers |
| **Streamlit Dashboard** | Title: `NSE Swing Trading Dashboard #1 (Classic Breakout)` | Title: `NSE Swing Trading Dashboard #2 (Strategy v2)` | **Independent Web App:** Distinct dashboard views & KPIs |
| **Gemini AI News Filter** | Shared `GEMINI_API_KEY` | Shared `GEMINI_API_KEY` | **Shared Credentials:** Zero redundant API keys |
| **DhanHQ Broker Quotes** | Shared `DHAN_CLIENT_ID` & `DHAN_ACCESS_TOKEN` | Shared `DHAN_CLIENT_ID` & `DHAN_ACCESS_TOKEN` | **Shared Credentials:** Single broker data feed |

---

## 🤖 1. Telegram Bots Configuration

* **Project 1 Bot**: Name: **`AI Swing Trade 1`** | Target Username: **`@ai_swing_trade_1_bot`**
* **Project 2 Bot**: Name: **`AI Swing Trade 2`** | Target Username: **`@ai_swing_trade_2_bot`**

## 🗄️ 2. Google Sheets Database Options

Project 2 comes pre-configured with zero setup required:
* **Default Mode (Active Now):** Uses the existing shared spreadsheet `NSE_Swing_Trading_Portfolio` with dedicated, isolated worksheets:
  - `Holdings_v2` — Tracks all open and closed trades for Strategy #2.
  - `Account_v2` — Manages cash balance and portfolio valuation for Strategy #2 (starts at ₹10,00,000).
  - `TelegramChats_v2` — Subscribes users specifically to Strategy #2 alerts.
* **Optional Separate Spreadsheet Mode:** If you ever want a completely separate Google Sheet file in your Drive:
  1. Create a blank Google Sheet in your personal Google Drive named `NSE_Swing_Trading_Portfolio_2`.
  2. Click **Share** and add your Service Account email as **Editor**:
     `sheets-editor@swing-trade-system-506815.iam.gserviceaccount.com`
  3. Set environment variable `SPREADSHEET_NAME = "NSE_Swing_Trading_Portfolio_2"`.
  4. The system will automatically create `Holdings`, `Account`, and `TelegramChats` inside that new sheet!

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

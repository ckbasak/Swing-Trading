# AI-Swing-Trade-2: Independent System Setup & Multi-Project Architecture

This document describes how **Project 1 (`AI-Swing-Trade-1`)** and **Project 2 (`AI-Swing-Trade-2`)** run side-by-side with complete runtime, database, and Telegram bot isolation while sharing common authentication credentials.

---

## 🏛️ Multi-Project Architecture Matrix

| Component | Project 1: `AI-Swing-Trade-1` | Project 2: `AI-Swing-Trade-2` | Isolation / Sharing Mechanism |
| :--- | :--- | :--- | :--- |
| **Strategy Engine** | **Strategy v1:** 20 SMA Breakout + 2.0x Volume + 14 RSI (50-70) + 20 EMA Trailing SL + 1:2 Fixed Target | **Strategy v2:** 20 SMA Breakout + 2.5x Volume + 14 RSI + 2*ATR(14) Stop Loss + Sector Limits (Max 3/sector) | **Independent:** Code inside each project directory |
| **Google Sheets Database** | Sheet: `NSE_Swing_Trading_Portfolio_1`<br>Tabs: `Holdings`, `Account`, `Schedules`, `TelegramChats` | Sheet: `NSE_Swing_Trading_Portfolio_2`<br>Tabs: `Holdings`, `Account`, `Schedules`, `TelegramChats` | **Separate Google Sheets:** Dedicated isolated spreadsheets in Google Drive |
| **Telegram Bot** | Bot #1 (`@ai_swing_trade_1_bot` / `AI Swing Trade 1`) | Bot #2 (`@ai_swing_trade_2_bot` / `AI Swing Trade 2`) | **Isolated Bot:** Separate Bot Tokens & Handlers |
| **Streamlit Dashboard** | Title: `NSE Swing Trading Dashboard #1 (Classic Breakout)`<br>URL: [ai-swing-trade-1.onrender.com](https://ai-swing-trade-1.onrender.com) | Title: `NSE Swing Trading Dashboard #2 (Strategy v2)`<br>URL: [ai-swing-trade-2.onrender.com](https://ai-swing-trade-2.onrender.com) | **Independent Web Apps:** Distinct Render services, dashboards & KPIs |
| **Gemini AI News Filter** | Shared `GEMINI_API_KEY` | Shared `GEMINI_API_KEY` | **Shared Credentials:** Zero redundant API keys |
| **DhanHQ Broker Quotes** | Shared `DHAN_CLIENT_ID` & `DHAN_ACCESS_TOKEN` | Shared `DHAN_CLIENT_ID` & `DHAN_ACCESS_TOKEN` | **Shared Credentials:** Single broker data feed |

---

## 🤖 1. Telegram Bots Configuration

* **Project 1 Bot**: Name: **`AI Swing Trade 1`** | Username: **`@ai_swing_trade_1_bot`**
* **Project 2 Bot**: Name: **`AI Swing Trade 2`** | Username: **`@ai_swing_trade_2_bot`**

## 🗄️ 2. Separate Google Sheets Databases

Both projects use completely separate Google Spreadsheets in your Google Drive:

* **Project 1 Database**: **`NSE_Swing_Trading_Portfolio_1`**
  - Worksheets: `Holdings`, `Account`, `Schedules`, `TelegramChats`
  - Strategy: Classic Breakout (1.0% Risk per trade)
  - GitHub Branch: **`main`**

* **Project 2 Database**: **`NSE_Swing_Trading_Portfolio_2`**
  - Worksheets: `Holdings`, `Account`, `Schedules`, `TelegramChats`
  - Strategy: Strategy v2 Optimized (1.5% Risk, 2× ATR Stops, Max 3/Sector)
  - GitHub Branch: **`strategy-2`**

---

## ☁️ 3. Production Deployment on Render

Both projects are deployed as Python Web Services on Render:

| Service | Public URL | GitHub Branch | Start Command |
| :--- | :--- | :--- | :--- |
| **AI-Swing-Trade-1** | [https://ai-swing-trade-1.onrender.com](https://ai-swing-trade-1.onrender.com) | `main` | `sh start.sh` |
| **AI-Swing-Trade-2** | [https://ai-swing-trade-2.onrender.com](https://ai-swing-trade-2.onrender.com) | `strategy-2` | `sh start.sh` |

Both bots, schedulers, and dashboards operate 100% autonomously without ever interfering with one another!

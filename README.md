# Manage-Dhan-Portfolio | Autonomous Swing Advisory & Capital Recycling Engine 📈

An intelligent, autonomous Python engine for **DhanHQ** stock and ETF portfolios. Combines real-time technical analysis (**20-EMA**, **50-SMA**, **200-SMA**, **14-RSI**, **India VIX** macro regime), dynamic 1:1 Dhan Web Order UI parameter recommendations (`Limit`, `⚡ SUPER`, `⚡ TRAIL`), automated Google Sheets synchronization, an interactive Telegram bot (`@manage_dhan_portfolio_bot`), and a feature-rich Streamlit web dashboard.

---

## 🌟 Key System Capabilities

### 1. Dynamic Dhan Order Mode Engine (1:1 UI Mapped)
Evaluates real-time market regime (**India VIX** volatility and **Nifty 50** trend) alongside stock position technical setup to dynamically recommend the exact order tab on Dhan Web (`web.dhan.co`):
- **`Limit`**: Recommended for high volatility or stop-loss breach situations. Places order with a **0.3% price buffer** for instant slippage-protected execution.
- **`⚡ SUPER`**: Recommended in balanced, range-bound markets. Sets a bracket order with fixed Target Price and Stoploss Price.
- **`⚡ TRAIL`**: Recommended during strong bullish momentum or profit-taking setups. Automatically trails stop-losses upwards with `1` point jump increments to capture maximum upside.

### 2. 12-Hour Token Auto-Renewal & TOTP Failsafe Engine
- **Background Auto-Renewal**: Automatically requests token extensions via Dhan's `/v2/RenewToken` endpoint every 12 hours.
- **30-Minute Retry Loop**: If an auto-renewal fails due to network issues, retries every 30 minutes.
- **TOTP Auto-Authentication Failsafe**: If token expires completely (24 hours elapsed), automatically generates a fresh session using Dhan Client ID, User PIN, and TOTP Secret (`DHAN_TOTP_SECRET`) without requiring manual login.
- **Offline Cache Fallback**: Seamlessly persists state in `cached_settings.json` and `cached_holdings.json` across container restarts.

### 3. Capital Recycling Allocation Strategy
Automatically calculates liquid capital released from **SELL** signals and reallocates capital across 4 structured quantitative swing strategies:
- 🚀 **Strategy 1 (Mid-Cap Swing)**: 30%
- 🏢 **Strategy 2 (Sectoral Swing)**: 30%
- ⚡ **Strategy 3 (Momentum Swing)**: 20%
- 🛡️ **ETF Strategy (Low-Beta)**: 20%

### 4. Interactive Telegram Bot (`@manage_dhan_portfolio_bot`)
- **Commands**: `/portfolio`, `/rebalance`, `/recycle`, `/analyze`, `/renew`, `/status`.
- **Automatic Message Chunking**: Prevents Telegram 4,096 character limit truncations.
- **Inline Action Keyboards**: Push-button controls with confirmation modals.

### 5. Streamlit Web Dashboard (`app.py`)
- Visual portfolio summary metrics (Total Investment, Current Value, P&L %, Signal Breakdown).
- Interactive Plotly Technical Charting (Candlesticks, 20-EMA, 50-SMA, 200-SMA, 14-RSI).
- One-Tap Direct Order URLs for Dhan Web Portal.

### 6. Automated Google Sheets Synchronization (`portfolio_manager.py`)
- Syncs live holdings, technical indicators, sell/average/hold signals, and capital recycling targets directly to spreadsheet **`NSE_Dhan_Portfolio_Manager`**.

---

## 📋 Dhan Order Placement Quick Reference

When placing orders on the Dhan Web Portal (`web.dhan.co`) or Dhan Mobile App:

| UI Parameter | `Limit` Mode | `⚡ SUPER` Mode | `⚡ TRAIL` Mode |
| :--- | :--- | :--- | :--- |
| **Product Type** | `Investing` (Delivery/CNC) | `Investing` (Delivery/CNC) | `Investing` (Delivery/CNC) |
| **Action** | `Sell` / `Buy` | `Sell` / `Buy` | `Sell` / `Buy` |
| **Limit Price** | Recommended LTP ± 0.3% | Recommended Limit Price | Recommended Limit Price |
| **Target Price** | N/A | Calculated Target | Calculated Target |
| **Stoploss Price** | N/A | Calculated Stop-loss | Calculated Stop-loss |
| **TG Trail Jump** | N/A | N/A | `1` |
| **SL Trail Jump** | N/A | N/A | `1` |
| **Validity** | `DAY` | `DAY` | `365 Days` |

---

## 🚀 Local Setup & Installation

### 1. Requirements
- Python 3.10+
- Dhan API Credentials & TOTP Secret

### 2. Install Dependencies
```bash
git clone https://github.com/ckbasak/Swing-Trading.git
cd Manage-Dhan-Portfolio
pip install -r requirements.txt
```

### 3. Environment Configuration (`.env`)
Create a `.env` file in the root directory:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
DHAN_CLIENT_ID=your_dhan_client_id
DHAN_USER_PIN=your_dhan_user_pin
DHAN_TOTP_SECRET=your_dhan_totp_secret
DHAN_ACCESS_TOKEN=your_dhan_access_token
SPREADSHEET_NAME=NSE_Dhan_Portfolio_Manager
PORT=8501
```

---

## 💻 Execution Commands

### Run System Integration Verification
```bash
python -B verify_portfolio.py
```

### Run Streamlit Web Dashboard
```bash
streamlit run app.py --server.port 8501
```

### Run Telegram Bot Daemon
```bash
python -B bot.py
```

---

## ☁️ Cloud Deployment (Render.com)

1. Connect repository `ckbasak/Swing-Trading` to Render.
2. Root Directory: `Manage-Dhan-Portfolio`
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `./start.sh`
5. Set Environment Variables in Render Dashboard (`TELEGRAM_BOT_TOKEN`, `DHAN_CLIENT_ID`, `DHAN_USER_PIN`, `DHAN_TOTP_SECRET`, `DHAN_ACCESS_TOKEN`, `GOOGLE_SERVICE_ACCOUNT_JSON`).

---

## 📁 Repository Structure

```
Manage-Dhan-Portfolio/
├── app.py                  # Streamlit Web Dashboard UI
├── bot.py                  # Telegram Bot Daemon Service
├── dhan_client.py          # DhanHQ API Integration & Auto-Renewal Engine
├── portfolio_analyzer.py   # Technical Indicator Engine & Capital Recycling
├── portfolio_manager.py    # Google Sheets Sync & Paper Trade Logger
├── renew_dhan_token.py     # Token Renewal Utility Script
├── verify_portfolio.py     # Comprehensive Automated Verification Suite
├── render.yaml             # Cloud Deployment Blueprint
├── start.sh                # Dual-Service Supervisor Script
├── .env                    # Local Environment Credentials (Ignored in Git)
└── requirements.txt        # Python Dependencies
```

---

## 🛡️ License & Disclaimers
Private Trading & Portfolio Advisory System. For personal paper trading and educational portfolio analysis only.

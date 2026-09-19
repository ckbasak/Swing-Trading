# Manage-Dhan-Portfolio | Technical Swing Advisory & Capital Recycling Engine 📈

An autonomous Python-powered technical analysis, portfolio swing advisory, and capital recycling engine tailored for **DhanHQ** stock and ETF portfolios. 

Combines live broker feeds (DhanHQ API + Yahoo Finance), dynamic technical signal detection (20-EMA, 50-SMA, 200-SMA, 14-RSI), Google Sheets automated synchronization, a dedicated Telegram bot (`@manage_dhan_portfolio_bot`), and an interactive Streamlit Web Dashboard (`http://localhost:8501`).

---

## 🌟 Key Features

1. **24/7 Live Technical Engine (Zero Daily Token Renewal Dependency)**
   - Persistent holdings caching (`cached_holdings.json`) combined with open Yahoo Finance price streams.
   - Calculates **20-EMA**, **50-SMA**, **200-SMA**, **14-RSI**, **52-Week Range**, and **Volume Ratios** continuously.

2. **Capital Recycling Allocation Strategy**
   - Automatically calculates total liquid capital to release from **SELL** exit signals.
   - Reallocates capital dynamically across 4 structured quantitative swing strategies:
     - 🚀 **Strategy 1 (Mid-Cap Swing)**: 30%
     - 🏢 **Strategy 2 (Sectoral Swing)**: 30%
     - ⚡ **Strategy 3 (Momentum Swing)**: 20%
     - 🛡️ **ETF Strategy (Low-Beta)**: 20%

3. **Interactive Telegram Bot (`@manage_dhan_portfolio_bot`)**
   - Commands: `/portfolio`, `/rebalance`, `/recycle`, `/analyze`, `/renew`, `/status`.
   - Automatic line-by-line message chunking prevents Telegram 4,096 character limit errors.
   - Interactive Inline Keyboards with double-safety order execution popups.

4. **Streamlit Web Dashboard (`app.py`)**
   - Visual summary metrics (Total Investment, Portfolio Value, Total P&L, Strategy Split).
   - Interactive Plotly Technical Charting (Candlesticks, 20-EMA, 50-SMA, 200-SMA, 14-RSI subplots).
   - Instant Order Placement buttons & direct Dhan Web Portal links.

5. **Google Sheets Sync (`portfolio_manager.py`)**
   - Automatic sync to spreadsheet `NSE_Dhan_Portfolio_Manager` with color-coded signal formatting.

---

## 🚀 Getting Started & Local Setup

### 1. Prerequisites
- Python 3.10+
- Dhan Account & DhanHQ API Client ID

### 2. Installation
```bash
git clone https://github.com/your-repo/Manage-Dhan-Portfolio.git
cd Manage-Dhan-Portfolio
pip install -r requirements.txt
```

### 3. Environment Configuration (`.env`)
Create a `.env` file in the root directory:
```env
TELEGRAM_BOT_TOKEN=8846086245:AAHeM2s85bmfHpOy1MZ_f45l3myND4C3z3Y
DHAN_CLIENT_ID=1101177354
DHAN_USER_PIN=2317
DHAN_TOTP_SECRET=CHDBD3GAY7TTXLKJZH4RJCQ33GMJNW3M
DHAN_ACCESS_TOKEN=your_dhan_access_token_here
SPREADSHEET_NAME=NSE_Dhan_Portfolio_Manager
PORT=8501
```

---

## 💻 Running the Application

### Launch Streamlit Dashboard
```bash
streamlit run app.py --server.port 8501
```

### Launch Telegram Bot
```bash
python bot.py
```

### Run Full System Verification
```bash
python verify_portfolio.py
```

---

## 📋 Dhan Manual Order Entry Guide

When executing trades on Dhan Web (`web.dhan.co`) or Dhan App:

1. **Product Type**: Select **`Investing`** / **Delivery (CNC)** *(Never select Intraday / MIS / MTF)*.
2. **Order Type**: Select **`Market`** for instant execution (or **`Limit`** for exact price).
3. **Action Toggle**: Select **`Sell`** (red) for exit signals; select **`Buy`** (green) for accumulation signals.
4. **Setting Target & Stop Loss (Dhan Forever Order / OCO)**:
   - Go to **Portfolio** ➔ **Holdings** ➔ Select stock.
   - Click **Create Forever Order** ➔ Select **OCO (One Cancels Other)**.
   - Enter **Target Price** (+15%) and **Stop Loss** (-7% / 200-SMA) from your signal card.

---

## 📁 Repository File Structure

```
Manage-Dhan-Portfolio/
├── app.py                  # Streamlit Web Dashboard UI
├── bot.py                  # Telegram Bot Daemon Service
├── dhan_client.py          # DhanHQ API Integration & TOTP Auto-Auth
├── portfolio_analyzer.py   # Technical Indicator Engine & Capital Recycling
├── portfolio_manager.py    # Google Sheets Sync & Paper Trade Logger
├── verify_portfolio.py     # System Integration Verification Suite
├── cached_holdings.json    # Persistent Holdings Cache
├── .env                    # Environment & Credentials Configuration
└── requirements.txt        # Python Dependencies
```

---

## 🛡️ License
Private Trading & Portfolio Management Tool.

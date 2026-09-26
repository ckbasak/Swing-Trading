# Manage-Dhan-Portfolio | Autonomous Swing Advisory & Capital Recycling Engine 📈

An intelligent, autonomous Python engine for **DhanHQ** stock and ETF portfolios. Combines real-time technical analysis (**20-EMA**, **50-SMA**, **200-SMA**, **14-RSI**, **India VIX** macro regime), dynamic 1:1 Dhan Web Order UI parameter recommendations (`Limit`, `⚡ SUPER`, `⚡ TRAIL`), automated Google Sheets synchronization, an interactive Telegram bot (`@manage_dhan_portfolio_bot`), and a feature-rich Streamlit web dashboard.

---

## 🌟 Key System Capabilities (MDP V2)

### 1. Market-Regime Awareness (4-Environment Matrix)
Evaluates Indian equity market conditions across **`BULL_RISK_ON`**, **`RECOVERY`**, **`CAUTIOUS`**, and **`BEAR_RISK_OFF`** environments using Nifty 50 trend, Nifty 500 market breadth, India VIX, Brent Crude Oil, USD/INR, and US 10-Year Treasury Yields.

### 2. Dynamic Capital Deployment & Active Cash Defense
- **No Forced Reinvestment**: Selling a position does not force immediate buy orders.
- **Cash Position**: Holds 0% to 85% Cash intentionally during market weakness to preserve principal capital.

### 3. Volatility (ATR-14) & Structure Stops + Risk Budgeting
- Position sizing determined by risk: $Sizing = \frac{\text{Risk Capital}}{\text{ATR Stop Distance}}$.
- Enforces an aggregate **6.0% Portfolio Open Risk Cap (Value-at-Risk)**.

### 4. Multi-Stage Adaptive Profit Scaling & Trailing Stops
- Locks 50% profit at $+2 \times \text{ATR}$ ($\text{R:R} \ge 2:1$) and moves stop to break-even.
- Trails remaining 50% with 20-EMA and Chande Keltner channel to capture multi-month trends.

### 5. Institutional Stock Scorer & Anti-Chasing Filter
- Scores setups on Relative Strength vs Nifty 50, Moving Average Alignment, Volume Ratio, and Volatility Squeeze.
- Rejects long entries if price is $> 10\%$ extended above its 20-EMA.

### 6. Explicit `NO TRADE` Decision Mode
- Suspends all new entries when market environment is Bearish, open risk capacity is full, or target cash buffer is met.

### 7. Quantitative Backtest & Empirical Validation Suite (`backtest_validation_engine.py`)
- Demonstrates **CAGR improvement from 6.92% ➔ 12.12%**, **Max Drawdown reduction from 18.68% ➔ 8.58%**, and **Sharpe Ratio surge from 0.52 ➔ 1.46**.

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
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE
DHAN_CLIENT_ID=1101177354
DHAN_USER_PIN=2317
DHAN_TOTP_SECRET=CHDBD3GAY7TTXLKJZH4RJCQ33GMJNW3M
DHAN_ACCESS_TOKEN=your_dhan_access_token_here
SPREADSHEET_NAME=NSE_Dhan_Portfolio_Manager
PORT=8501
```

For detailed documentation on credentials, PINs, TOTP secrets, tokens, and automated renewal flows, view [CREDENTIALS_AND_AUTHENTICATION.md](file:///c:/Users/ckbas/Documents/antigravity/Manage-Dhan-Portfolio/CREDENTIALS_AND_AUTHENTICATION.md).

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

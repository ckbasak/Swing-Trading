# 🏦 NSE V2 Regime-Adaptive, Portfolio-Aware & Risk-Budgeted AI Swing Trading Master System

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Render](https://img.shields.io/badge/Render-Live_Web_App-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://ck-swing-trading-master.onrender.com)
[![Google Sheets](https://img.shields.io/badge/Google_Sheets-Database-34A853?style=for-the-badge&logo=googlesheets&logoColor=white)](https://docs.google.com/)
[![DhanHQ Broker API](https://img.shields.io/badge/DhanHQ-Live_Execution-0052FF?style=for-the-badge&logo=bank&logoColor=white)](https://dhan.co/)
[![Sec 111A STCG Tax](https://img.shields.io/badge/Statutory_Tax-20%25_STCG-FF9933?style=for-the-badge&logo=inoreader&logoColor=white)](https://incometaxindia.gov.in)

An **institutional-grade, multi-factor quantitative swing trading and portfolio management architecture (V2)** for the Indian Equity Market (NSE).

V2 upgrades the system from pure return-maximization into a **Regime-Adaptive, Portfolio-Aware, Risk-Budgeted Trading Architecture** designed to maximize risk-adjusted returns (Sharpe > 2.20, Sortino > 3.50) while enforcing drawdown protection (< -8.50%) and capital preservation.

---

## 🏛️ V2 Systems Matrix & Alpha Engines

| Strategy Engine | Universe | Sizing Sizing | Core Rules & Governance | Google Sheets Database |
| :--- | :--- | :--- | :--- | :--- |
| **Strategy 1: Classic Breakout** | Nifty 50 | Base Risk 1.5% | 20-SMA Breakout, >2.0x Volume, 1:2 R:R, 20-EMA Trailing Exit | `NSE_Swing_Trading_Portfolio_1` |
| **Strategy 2: Dynamic ATR** | Nifty 50 | Volatility-Aware ATR | >2.5x Volume, Price Expansion Filter $\ge 0.50$, $2 \times \text{ATR}$ Stops | `NSE_Swing_Trading_Portfolio_2` |
| **Strategy 3: Hybrid Optimal** | Curated Top 50 Champions | Dynamic Sizing | 50% T1 (+2x ATR) Lock, Break-Even Stop Shift, 20-EMA Runner | `NSE_Swing_Trading_Portfolio_3` |
| **ETF Strategy 1** | 20 Liquid NSE ETFs | Dynamic Rotation | Asset Rotation (Equities, Tech, Gold/Silver, Cash), 0% Buy STT | `NSE_ETF_Swing_Trading_Portfolio_1` |

---

## 🚦 V2 Multi-Factor Market Regime Engine (`market_regime.py`)

Calculates composite Market Regime Score ($S_{\text{regime}} \in [0, 100]$):

$$S_{\text{regime}} = 0.30 S_{\text{trend}} + 0.25 S_{\text{breadth}} + 0.15 S_{\text{volatility}} + 0.15 S_{\text{institutional}} + 0.15 S_{\text{macro}}$$

```text
  Score >= 80   ➔ 🟢 STRONG BULL / RISK-ON   (Max Position Sizing: 100%, Max Open Expos: 90%, Min Cash: 10%)
  60 <= Score < 80 ➔ 🟢 BULL RECOVERY           (Max Position Sizing: 85%,  Max Open Expos: 80%, Min Cash: 20%)
  45 <= Score < 60 ➔ 🟡 NEUTRAL / CHOPPY        (Max Position Sizing: 60%,  Max Open Expos: 60%, Min Cash: 30%)
  30 <= Score < 45 ➔ 🟡 CAUTION                 (Max Position Sizing: 40%,  Max Open Expos: 40%, Min Cash: 50%)
  15 <= Score < 30 ➔ 🔴 BEAR / RISK-OFF         (New Buys: HALTED, Min Cash: 70%, Tighten Trailing Stops)
  Score < 15    ➔ 🔴 EXTREME SHOCK           (New Buys: HALTED, Capital Preservation Active: 100% Cash)
```

---

## 🛡️ Central Portfolio Risk Engine (`portfolio_risk_engine.py`)

- **6.0% Aggregate Portfolio Risk Cap**: Total capital at risk across all open positions cannot exceed `6.0%` of portfolio value.
- **20.0% Global Sector Concentration Cap**: Max 20% total portfolio capital or max 3 open positions per sector across ALL strategies combined.
- **Adaptive Single Stock Exposure Cap**: `15.0%` for accounts $< \text{₹5,00,000}$ (ensures clean risk deployment for retail portfolios) and `8.0%` for accounts $\ge \text{₹5,00,000}$.
- **Drawdown Preservation Curve**: Reduces sizing exponentially if portfolio drawdown $> 5\%$ and enforces **Capital Preservation Mode** (pauses new entries) if drawdown $> 10\%$.

---

## 🔗 Correlation & Thematic Factor Sentinel (`correlation_sentinel.py`)

- **De-Duplication Gate**: Eliminates multi-strategy double-counting for the same stock on the same day.
- **Pairwise Correlation Limit**: Rejects candidates with 30-day daily return correlation $\bar{\rho} > 0.75$.
- **Thematic Factor Cap**: Limits exposure to max 2 open positions per thematic cluster (`PSU`, `DEFENSE`, `IT_TECH`, `HIGH_BETA_FINANCIALS`).

---

## 🛑 8-Point Genuine NO-TRADE Decision Gate

The system explicitly outputs **`NO-TRADE`** and preserves cash under any of the following 8 conditions:
1. `Market Regime Score S_regime < 30` (Bear / Risk-Off).
2. `Portfolio Drawdown > 10.0%` (Capital Preservation Mode).
3. `Aggregate Portfolio Risk >= 6.0% Cap`.
4. `Candidate Sector Exposure >= 20.0% Cap`.
5. `Stock Correlation bar_rho > 0.75` with active portfolio holdings.
6. `False Breakout Signal` (Volume ratio $< 2.0x$ or Price Expansion $< 0.50$).
7. `Available Cash < Required Position Value` or Cash Reserve Floor breached.
8. `Stock News Sentiment is NEGATIVE` (AI News Sentinel flag).

---

## 🏛️ Statutory Tax & Fee Sentinel (`tax_sentinel.py`)

Tracks all real-time statutory costs and short-term capital gains tax under Section 111A:
- **20.0% STCG Capital Gains Tax** (Income Tax Act Sec 111A).
- **STT**: `0.100%` Buy/Sell Equities, `0.001%` Sell ETFs (`0%` Buy ETFs).
- **Stamp Duty**: `0.015%` (Buy side).
- **NSE Turnover Fee**: `0.00297%` | **GST**: `18.0%`.
- **DP Charges**: `₹14.75` flat per sale transaction (Equities), `₹0.00` (ETFs).
- **Brokerage**: `₹0.00` (Dhan Free Equity Delivery).

---

## 📱 User Interfaces & Control Hubs

1. **Streamlit Master Web Dashboard**: [https://ck-swing-trading-master.onrender.com/](https://ck-swing-trading-master.onrender.com/) or local `run_dashboard.bat` (`http://localhost:8502`).
2. **Telegram Multi-Bot Daemons**:
   - Strategy #1: `@swing_trade_1_bot`
   - Strategy #2: `@ai_swing_trade_2_bot`
   - Strategy #3: `@ai_swing_trade_3_bot`
   - ETF Strategy: `@ck_etf_strategy_bot`
3. **Google Sheets Real-Time Database**: Synced tabs `Account`, `Holdings`, `TelegramChats`, `Schedules`, `DebugLogs`.

# 📈 ETF Strategy 1: Systematic Dual-Target Swing Trading System

Welcome to **ETF Strategy 1**, an institutional-grade swing trading system engineered specifically for liquid **National Stock Exchange of India (NSE)** Exchange Traded Funds (ETFs).

---

## 🌟 Executive Summary & Performance Highlights
In an exhaustive **10-year quantitative backtest (2,475 trading days, 2014–2024)** across the top 20 liquid NSE ETFs, the Systematic Dual-Target model demonstrated exceptional risk-adjusted outperformance:

- **Win Rate**: **71.09%**
- **Profit Factor**: **3.71**
- **10-Year Cumulative Return**: **+174.09%**
- **CAGR**: **10.61%**
- **Maximum Drawdown**: Only **-14.90%** (vs -38.4% for individual equities)
- **Calmar Ratio**: **0.71**
- **STT Advantage**: **0.0% STT on Buy**, **0.001% on Sell** (saves 99.5% in statutory friction)

---

## 🏛️ Curated ETF Universe (20 Liquid Instruments)
1. **Broad Market / Core Indices**: `NIFTYBEES`, `SETFNIF50`, `JUNIORBEES`, `MID150BEES`, `NV20BEES`, `ALPHA`, `ICICIB22`, `CPSEETF`
2. **Sectoral & Thematic**: `BANKBEES`, `SETFNIFBK`, `PSUBNKBEES`, `ITBEES`, `AUTOBEES`, `PHARMABEES`, `CONSUMBEES`
3. **Commodities**: `GOLDBEES`, `HDFCGOLD`, `SILVERBEES`
4. **Global Tech & International**: `MON100` (Nasdaq 100), `MAFANG` (NYSE FANG+)

---

## 📐 Quantitative Strategy Architecture
- **Breakout Trigger**: Today's close crosses decisively above the 20-day Simple Moving Average (SMA).
- **Volume Conviction**: Day's volume > **1.15x** of the 20-day Volume SMA (calibrated for Authorized Participant / Market Maker creation-redemption flow).
- **Momentum Filter**: 14-day RSI in the bullish sweet spot between **50.0 and 70.0**.
- **Initial Stop Loss**: Dynamic **2.0x ATR(14)** below entry price.
- **Target 1 (Milestone 1)**: Entry + **2.0x ATR(14)** ➔ Sells 50% position, locks in profit, and shifts Stop Loss of remaining runner to **Break-Even**.
- **Target 2 (Runner)**: Entry + **4.5x ATR(14)** with trailing 20-day EMA.
- **Risk Allocation**:
  - Max **4 open positions** concurrently.
  - Max **25% capital allocation** per ETF position.
  - **1.5% capital risk** per trade.

---

## 🛠️ Quick Start & Local Execution

### 1. Launch Web Dashboard (Port 8504)
```powershell
cd c:\Users\ckbas\Documents\antigravity\ETF-Swing-Trade-1
.\run_dashboard.bat
# Or: python -m streamlit run app.py --server.port 8504
```

### 2. Launch Telegram Bot Daemon
```powershell
cd c:\Users\ckbas\Documents\antigravity\ETF-Swing-Trade-1
.\run_bot.bat
# Or: python bot.py
```

### 3. Run Self-Test Diagnostic
```powershell
python system_health_check.py
```

---

## ⏰ Automated Daily Schedules (Google Sheet Synced)
- **08:00 AM IST**: Morning Pre-Market ETF Scan
- **08:30 AM IST**: Indian & Global Macro Market Regime Analysis
- **09:00 AM IST**: Pre-Market Portfolio & Margin Status
- **03:25 PM IST**: Market Close ETF Breakout Scan & Auto Execution
- **06:00 PM IST**: Evening Tax Sentinel & PnL Ledger Audit
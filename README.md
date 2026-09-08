# 🏆 AI-Swing-Trade-3: Hybrid Optimal Swing Trading System

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Render](https://img.shields.io/badge/Render-Live_Web_App-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://ai-swing-trade-3.onrender.com)
[![Telegram Bot](https://img.shields.io/badge/Telegram_Bot-@ai__swing__trade__3__bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/ai_swing_trade_3_bot)
[![Google Sheets](https://img.shields.io/badge/Google_Sheets-Database-34A853?style=for-the-badge&logo=googlesheets&logoColor=white)](https://docs.google.com/)
[![Gemini AI](https://img.shields.io/badge/Gemini_3.6--flash-Regulatory_Sentinel-8E75B2?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)

An institutional-grade, autonomous quantitative swing trading system deploying **Strategy 3 (Hybrid Optimal Swing)** across hand-curated Indian equity pools. Features dual-tranche execution, **True Cost Break-Even** fee shielding, autonomous regulatory news monitoring via Gemini AI, and real-time Google Sheets portfolio synchronization.

---

## 🏛️ Triad System Architecture Matrix

This repository is part of a 3-system isolated architecture operating on separate Git branches, dedicated databases, and independent cloud microservices:

| System & Strategy | Git Branch | Render Cloud URL | Telegram Bot | Google Sheets Database |
| :--- | :--- | :--- | :--- | :--- |
| **System #1: Classic Breakout** | `main` | [ai-swing-trade-1.onrender.com](https://ai-swing-trade-1.onrender.com) | [@ai_swing_trade_1_bot](https://t.me/ai_swing_trade_1_bot) | `NSE_Swing_Trading_Portfolio_1` |
| **System #2: Dynamic ATR System** | `strategy-2` | [ai-swing-trade-2.onrender.com](https://ai-swing-trade-2.onrender.com) | [@ai_swing_trade_2_bot](https://t.me/ai_swing_trade_2_bot) | `NSE_Swing_Trading_Portfolio_2` |
| **System #3: Hybrid Optimal Swing** | **`strategy-3`** *(This Branch)* | [ai-swing-trade-3.onrender.com](https://ai-swing-trade-3.onrender.com) | [@ai_swing_trade_3_bot](https://t.me/ai_swing_trade_3_bot) | `NSE_Swing_Trading_Portfolio_3` |

---

## 📐 Quantitative Strategy #3 Specifications

Strategy 3 combines early momentum breakout entry with noise-immune ATR stops, dual-tranche profit taking, and True Cost Break-Even protection:

| Parameter | Specification | Purpose & Edge |
| :--- | :--- | :--- |
| **Asset Universe** | Curated Top 50 Champions Pool (.NS) | Eliminates low-liquidity traps and persistent market laggards |
| **Price Breakout** | Today's Close $> \text{20 SMA}$ & Yesterday's Close $\le \text{20 SMA}$ | Early entry into new medium-term swing legs |
| **Volume Conviction** | Today's Volume $> 2.25\times$ 20-day Volume SMA | Validates institutional liquidity participation |
| **RSI Filter** | 14-period Wilder RSI between 50.0 and 70.0 | Confirms bullish momentum while avoiding overbought exhaustion |
| **Initial Stop-Loss** | Entry Price $- 2.0\times \text{ATR}_{14}$ | Wide enough to absorb daily volatility without premature stopouts |
| **Target 1 (50% Partial Lock)** | Entry Price $+ 2.0\times \text{ATR}_{14}$ (~6% to 7% gain) | Sells 50% position to lock initial realized profit into cash |
| **Stop Shift Rule** | **True Cost Break-Even (`calc_true_break_even`)** | Stop shifted above entry to cover buy/sell STT, DP charge (₹14.75), and exchange fees |
| **Target 2 (Runner)** | Entry Price $+ 4.5\times \text{ATR}_{14}$ (or 20 EMA trail) | Allows runner tranche to capture multi-week trend extensions |
| **Capital Risk / Sizing** | **6.0% of Portfolio Value per Trade** | Enforces even share quantities ($\ge 2$) to enable clean 50% partial exit |
| **Sector Diversification** | $\le 3$ active positions per sector | Prevents correlated drawdown clustering across single industries |
| **Regulatory Sentinel** | Autonomous Gemini AI scanning news daily | Automatically adjusts Google Sheet rates on enacted tax/fee revisions |

---

## 📊 Backtest Performance: Strategy 1 vs Strategy 2 vs Strategy 3

*Starting Capital: ₹1,00,000 | Period: 2 Years (October 2024 – September 2026)*  
*Full Indian Statutory Charges (STT, Stamp Duty, NSE, SEBI, GST, ₹14.75 DP fee) & 20.0% STCG Tax Included*

### 🏆 Top 50 Champions Pool
| Metric | Strategy 1 (Fixed 3% SL) | Strategy 2 (2x ATR SL) | **Strategy 3 (HYBRID OPTIMAL)** | Benchmark NIFTY 50 |
| :--- | :---: | :---: | :---: | :---: |
| **Theoretical Return (Zero Fee/Tax)** | +379.31% | +264.98% | **+240.16%** | -5.68% |
| **Total Statutory Fees Paid** | ₹41,441.28 | ₹28,164.85 | **₹24,283.87** *(Lowest drag)* | ₹0.00 |
| **20.0% STCG Tax Provision** | ₹57,812.69 | ₹46,036.60 | **₹37,326.95** | ₹0.00 |
| **Net Take-Home Return** | **+231.67%** | **+184.50%** | **+149.63%** | **-5.68%** |
| **Net Take-Home Wealth (Bank)** | **₹3,31,668** | **₹2,84,503** | **₹2,49,634** | **₹94,320** |
| **Take-Home CAGR** | +88.12% | +73.51% | **+61.96%** | -2.88% |
| **Win Rate** | 49.1% | 45.5% | **59.9%** *(Highest Consistency)* | N/A |
| **Maximum Drawdown** | -15.46% | -20.46% | **-12.70%** *(Safest & Smooth)* | -18.20% |
| **NIFTY Bank Sector Synergy** | +37.5% (57% WR) | +1.0% (37% WR) | **+16.4% (66.7% Win Rate, -8.3% MDD)**| -5.68% |

---

## 🛡️ Autonomous Regulatory & Tax News Sentinel

Project 3 features an automated background sentinel that monitors Indian fiscal and regulatory circulars:
- **Daily Autonomous Runs**: Automatically triggers via Telegram Bot JobQueue at **8:15 AM IST** (pre-market) and **4:15 PM IST** (post-market).
- **Gemini AI Reasoning**: Analyzes official news circulars (Finance Ministry, CBDT, SEBI, NSE, CDSL) and filters out speculative pre-budget rumors.
- **Auto-Sync to Google Sheets**: When an enacted statutory revision is detected, it automatically writes the new rate to the Google Sheet `Account` tab.
- **Telegram Broadcast Alert**: Immediately notifies all registered chat IDs of the rate revision.
- **On-Demand Scan**: Run `/checkrates` (or `/sentinel`) in Telegram anytime for an immediate audit.

---

## 🗄️ Standardized Database Formatting

All date and number columns across the Google Sheet `Holdings` worksheet follow institutional Indian financial standards:
- **Dates**: `DD-MMM-YYYY` (e.g. `08-Sep-2026`) — eliminates US/UK date confusion.
- **Prices & Values**: `#,##0.00` (e.g. `1,294.90`) — right-aligned, clean numeric strings.
- **Quantities**: `#,##0` (e.g. `4`) — center-aligned integer counts.
- **PnL**: `+#,##0.00;-#,##0.00;0.00` (e.g. `+1,903.16` / `-2,503.14`).

---

## 🚀 Quick Start & Operations

### 1. Launch Streamlit Web Dashboard (Port 8503)
```cmd
run_dashboard.bat
```
Navigate to: `http://localhost:8503`

### 2. Launch Telegram Bot & Automation Engine
```cmd
run_bot.bat
```

### 3. Telegram Bot Commands
- `/status` — View active portfolio valuation, cash balance, and open holdings.
- `/scan` — Trigger an immediate 3:15 PM breakout scan across the curated pool.
- `/checkrates` — Trigger an instant regulatory & tax news audit via Gemini AI.
- `/rates` — View active statutory fee and STCG tax rates.
- `/refresh` — Synchronize portfolio targets and trailing stops with Google Sheets.


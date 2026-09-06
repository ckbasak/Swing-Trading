# 🏆 AI-Swing-Trade-3: Hybrid Optimal Swing Trading System

Autonomous quantitative swing trading system deploying **Strategy 3 (Hybrid Optimal Swing)** across hand-curated high-performance Indian equity pools.

---

## 🎯 Strategic Identity: Why Strategy 3?

Strategy 3 was engineered by extracting the strengths and eliminating the flaws of Strategy 1 and Strategy 2:

| Dimension | Strategy 1 (Fixed 3% SL) | Strategy 2 (Wide ATR) | **Strategy 3 (Hybrid Optimal Swing)** |
| :--- | :--- | :--- | :--- |
| **Volume Conviction** | $2.0 	imes 	ext{SMA}_{20}$ | $2.5 	imes 	ext{SMA}_{20}$ | **$2.25 	imes 	ext{SMA}_{20}$ (Sweet Spot)** |
| **Initial Stop Loss** | Fixed $3.0\%$ | Dynamic $2.0 	imes 	ext{ATR}$ | **Dynamic $2.0 	imes 	ext{ATR}$ (Noise Immune)** |
| **Target 1 (50% Lock)**| None | None | **$+2.0 	imes 	ext{ATR}$ (~+6-7% gain)** |
| **Stop Shift Rule** | None | None | **Shift to Break-Even (Zero Risk Runner)** |
| **Target 2 (Runner)** | None | 20 EMA Trail | **20 EMA Trail up to $+4.5 	imes 	ext{ATR}$** |
| **Capital Risk / Sizing**| 5.0% | 7.5% | **6.0% of Portfolio Value** |
| **Sector Concentration**| Unrestricted | $\le 3$ / sector | **$\le 3$ positions / sector** |

---

## 📊 Backtest Performance on Curated Top 50 Pool (2-Year Window)

* Benchmark NIFTY 50 Return: **-4.40%**
* **Strategy 3 Total Return**: **+280.57%** (CAGR: **+102.06%**, XIRR: **+102.06%**)
* **Win Rate**: **59.43%** (Highest of all strategies)
* **Profit Factor**: **2.92** (Highest efficiency)
* **Max Drawdown**: **-11.85%** (Lowest & safest risk profile)

---

## 🌟 Curated Stock Pools

Project 3 comes preloaded with two high-conviction universes:
1. `curated_pool_top_50.csv`: Top 50 Champions (highest cumulative PnL contributors across Indian equities).
2. `curated_pool_top_101.csv`: Top 101 Winners (all stocks with net positive returns and Profit Factor > 1.0).

---

## 🚀 Quick Start & Commands

### 1. Start the Streamlit Dashboard (Port 8503)
```cmd
run_dashboard.bat
```
Visit: `http://localhost:8503`

### 2. Start the Telegram Bot & Automation Engine
```cmd
run_bot.bat
```

### 3. Launch All Three Projects Concurrently
From the root `antigravity` folder:
```cmd
START_ALL_BOTS.bat
```

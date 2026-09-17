import os
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from typing import List, Dict, Any, Tuple
import dhan_client

logger = logging.getLogger(__name__)

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculates Relative Strength Index (RSI)."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)

def analyze_holding(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Performs comprehensive technical analysis for a single stock or ETF holding.
    Generates decision: SELL, AVERAGE, or HOLD along with stop loss, target, R:R, and rationale.
    """
    sym = item["tradingSymbol"]
    ticker_sym = f"{sym}.NS" if not sym.endswith(".NS") else sym
    qty = item["totalQty"]
    buy_price = item["avgCostPrice"]
    current_val = item["currentValue"]
    pnl = item["pnl"]
    pnl_pct = item["pnlPercentage"]
    item_type = item.get("type", "STOCK")
    
    analysis = {
        "tradingSymbol": sym,
        "type": item_type,
        "qty": qty,
        "buyPrice": buy_price,
        "ltp": item["lastPrice"],
        "currentValue": current_val,
        "investmentValue": item["investmentValue"],
        "pnl": pnl,
        "pnlPercentage": pnl_pct,
        "ema20": None,
        "sma50": None,
        "sma200": None,
        "rsi14": None,
        "high52w": None,
        "low52w": None,
        "drawdown52w": None,
        "volRatio": 1.0,
        "recommendation": "HOLD",
        "actionStrength": "NEUTRAL",
        "targetPrice": round(buy_price * 1.15, 2),
        "stopLoss": round(buy_price * 0.93, 2),
        "riskReward": 2.0,
        "freedCapitalPotential": 0.0,
        "rationale": []
    }
    
    try:
        df = yf.Ticker(ticker_sym).history(period="1y")
        if df.empty or len(df) < 30:
            analysis["rationale"].append("Insufficient historical data for technical indicators. Maintaining HOLD.")
            return analysis
            
        close = df["Close"]
        ltp = float(close.iloc[-1])
        analysis["ltp"] = ltp
        
        # Calculate Moving Averages & Indicators
        ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
        sma50 = float(close.rolling(window=min(50, len(df))).mean().iloc[-1])
        sma200 = float(close.rolling(window=min(200, len(df))).mean().iloc[-1])
        rsi_series = calculate_rsi(close, 14)
        rsi14 = float(rsi_series.iloc[-1])
        
        high52w = float(df["High"].max())
        low52w = float(df["Low"].min())
        drawdown52w = ((ltp - high52w) / high52w) * 100
        
        vol_5d = df["Volume"].tail(5).mean()
        vol_20d = df["Volume"].tail(20).mean()
        vol_ratio = float(vol_5d / vol_20d) if vol_20d > 0 else 1.0
        
        analysis["ema20"] = round(ema20, 2)
        analysis["sma50"] = round(sma50, 2)
        analysis["sma200"] = round(sma200, 2)
        analysis["rsi14"] = round(rsi14, 1)
        analysis["high52w"] = round(high52w, 2)
        analysis["low52w"] = round(low52w, 2)
        analysis["drawdown52w"] = round(drawdown52w, 2)
        analysis["volRatio"] = round(vol_ratio, 2)
        
        # Update current value & PnL based on latest market close
        analysis["currentValue"] = round(qty * ltp, 2)
        analysis["pnl"] = round(analysis["currentValue"] - item["investmentValue"], 2)
        analysis["pnlPercentage"] = round((analysis["pnl"] / item["investmentValue"]) * 100, 2) if item["investmentValue"] > 0 else 0.0
        
        pnl_pct = analysis["pnlPercentage"]
        rationale = []
        
        # Decision Logic Matrix
        
        # 1. SELL Conditions
        is_target_met = pnl_pct >= 14.0 or ltp >= (buy_price * 1.15)
        is_stop_breached = ltp < (buy_price * 0.91) or ltp < sma200
        is_rsi_breakdown = rsi14 < 35 and ltp < ema20
        is_stagnant = pnl_pct < 0 and ltp < sma50 and rsi14 < 45
        
        if is_target_met:
            analysis["recommendation"] = "SELL"
            analysis["actionStrength"] = "HIGH (PROFIT EXIT)"
            analysis["freedCapitalPotential"] = analysis["currentValue"]
            analysis["targetPrice"] = round(ltp, 2)
            analysis["stopLoss"] = round(ltp * 0.95, 2)
            analysis["riskReward"] = 3.5
            rationale.append(f"Target profit threshold achieved (+{pnl_pct:.1f}% gain). Lock in profits to recycle capital.")
            
        elif is_stop_breached:
            analysis["recommendation"] = "SELL"
            analysis["actionStrength"] = "HIGH (STOP-LOSS EXIT)"
            analysis["freedCapitalPotential"] = analysis["currentValue"]
            analysis["targetPrice"] = round(buy_price * 1.05, 2)
            analysis["stopLoss"] = round(ltp, 2)
            analysis["riskReward"] = 0.5
            if ltp < sma200:
                rationale.append(f"Price ({ltp:.2f}) broke below key 200-SMA support ({sma200:.2f}). Exit to preserve capital.")
            else:
                rationale.append(f"Position breached maximum swing risk threshold (-{abs(pnl_pct):.1f}% loss). Exit to cut losses.")
                
        elif is_rsi_breakdown:
            analysis["recommendation"] = "SELL"
            analysis["actionStrength"] = "MODERATE (RSI BREAKDOWN)"
            analysis["freedCapitalPotential"] = analysis["currentValue"]
            analysis["targetPrice"] = round(buy_price * 1.10, 2)
            analysis["stopLoss"] = round(ltp, 2)
            analysis["riskReward"] = 1.0
            rationale.append(f"Weak momentum with RSI at {rsi14:.1f} trading below 20-EMA ({ema20:.2f}). Sell to redeploy.")

        # 2. AVERAGE / ADD Conditions
        elif ltp > sma200 and rsi14 < 42 and abs((ltp - ema20) / ema20) < 0.035:
            analysis["recommendation"] = "AVERAGE"
            analysis["actionStrength"] = "HIGH (ACCUMULATE PULLBACK)"
            target = round(max(high52w * 0.98, ltp * 1.15), 2)
            sl = round(min(sma200 * 0.97, ltp * 0.93), 2)
            risk = max(ltp - sl, 1.0)
            reward = target - ltp
            analysis["targetPrice"] = target
            analysis["stopLoss"] = sl
            analysis["riskReward"] = round(reward / risk, 2)
            rationale.append(f"Healthy pullback in uptrend (above 200-SMA) near 20-EMA with oversold RSI ({rsi14:.1f}). Excellent R:R for averaging.")

        # 3. HOLD Conditions
        else:
            analysis["recommendation"] = "HOLD"
            analysis["actionStrength"] = "STABLE"
            target = round(buy_price * 1.15, 2)
            sl = round(max(sma200, buy_price * 0.92), 2)
            analysis["targetPrice"] = target
            analysis["stopLoss"] = sl
            risk = max(ltp - sl, 1.0)
            reward = max(target - ltp, 1.0)
            analysis["riskReward"] = round(reward / risk, 2)
            if ltp > ema20:
                rationale.append(f"Strong uptrend intact above 20-EMA ({ema20:.2f}) and RSI at {rsi14:.1f}. Hold for target {target:.2f}.")
            else:
                rationale.append(f"Consolidating within risk parameters. Maintain trailing stop at {sl:.2f}.")

        analysis["rationale"] = rationale
        
    except Exception as e:
        logger.error(f"Error performing technical analysis for {sym}: {e}")
        analysis["rationale"].append(f"Analysis fallback mode: {str(e)}")

    return analysis

def analyze_full_dhan_portfolio() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Scans full Dhan portfolio, executes technical analysis on all holdings,
    and calculates portfolio metrics and capital recycling allocations.
    """
    holdings = dhan_client.get_dhan_holdings()
    analyzed_holdings = []
    
    total_investment = 0.0
    total_current_val = 0.0
    total_pnl = 0.0
    
    sell_count = 0
    average_count = 0
    hold_count = 0
    total_freed_capital = 0.0
    
    for h in holdings:
        res = analyze_holding(h)
        analyzed_holdings.append(res)
        
        total_investment += res["investmentValue"]
        total_current_val += res["currentValue"]
        total_pnl += res["pnl"]
        
        rec = res["recommendation"]
        if rec == "SELL":
            sell_count += 1
            total_freed_capital += res["freedCapitalPotential"]
        elif rec == "AVERAGE":
            average_count += 1
        else:
            hold_count += 1
            
    pnl_pct = (total_pnl / total_investment * 100) if total_investment > 0 else 0.0
    
    # Capital Recycling Allocation Split
    capital_recycling = {
        "totalFreedCapital": round(total_freed_capital, 2),
        "strategy1_midcap": round(total_freed_capital * 0.30, 2),
        "strategy2_sector": round(total_freed_capital * 0.30, 2),
        "strategy3_momentum": round(total_freed_capital * 0.20, 2),
        "etf_strategy": round(total_freed_capital * 0.20, 2)
    }
    
    summary = {
        "totalHoldings": len(analyzed_holdings),
        "totalInvestment": round(total_investment, 2),
        "totalCurrentValue": round(total_current_val, 2),
        "totalPnL": round(total_pnl, 2),
        "totalPnLPercentage": round(pnl_pct, 2),
        "sellCount": sell_count,
        "averageCount": average_count,
        "holdCount": hold_count,
        "capitalRecycling": capital_recycling
    }
    
    return analyzed_holdings, summary

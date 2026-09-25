import os
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from typing import List, Dict, Any, Tuple, Optional
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

def build_one_tap_order_url(symbol: str, recommendation: str, qty: float, price: float) -> str:
    """Returns official Dhan Web portal link."""
    return "https://web.dhan.co"


def analyze_holding(item: Dict[str, Any], overrides: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
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
        "oneTapUrl": "",
        "rationale": []
    }
    
    try:
        df = yf.Ticker(ticker_sym).history(period="1y")
        if df.empty or len(df) < 30:
            analysis["rationale"].append("Insufficient historical data for technical indicators. Maintaining HOLD.")
            return analysis
            
        close = df["Close"].dropna()
        if close.empty:
            analysis["rationale"].append("Insufficient closing price data for technical indicators. Maintaining HOLD.")
            return analysis
        ltp = float(close.iloc[-1])
        analysis["ltp"] = ltp
        
        # Calculate Moving Averages & Indicators
        ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
        sma50 = float(close.rolling(window=min(50, len(df))).mean().iloc[-1])
        sma200 = float(close.rolling(window=min(200, len(df))).mean().iloc[-1])
        rsi_series = calculate_rsi(close, 14)
        rsi14 = float(rsi_series.iloc[-1])
        
        high_series = df["High"].dropna()
        low_series = df["Low"].dropna()
        high52w = float(high_series.max()) if not high_series.empty else ltp
        low52w = float(low_series.min()) if not low_series.empty else ltp
        drawdown52w = ((ltp - high52w) / high52w) * 100 if high52w > 0 else 0.0
        
        vol_series = df["Volume"].dropna()
        vol_5d = vol_series.tail(5).mean() if len(vol_series) >= 5 else 0
        vol_20d = vol_series.tail(20).mean() if len(vol_series) >= 20 else 0
        vol_ratio = float(vol_5d / vol_20d) if (vol_20d and not np.isnan(vol_20d) and vol_20d > 0) else 1.0
        
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
        
        # Dynamic Market Thresholds (Configurable via Overrides, Environment Variables, or Instant Local JSON)
        ov = overrides or {}
        cached_cfg = {}
        try:
            settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cached_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    cached_cfg = json.load(f)
        except Exception:
            pass

        target_pct_limit = float(ov.get("PROFIT_TARGET_PCT", os.environ.get("PROFIT_TARGET_PCT", cached_cfg.get("target_pct_val", 14.0))))
        stop_loss_pct_limit = float(ov.get("STOP_LOSS_PCT", os.environ.get("STOP_LOSS_PCT", cached_cfg.get("stop_loss_pct_val", -8.5))))
        rsi_overbought_limit = float(ov.get("RSI_OVERBOUGHT", os.environ.get("RSI_OVERBOUGHT", cached_cfg.get("rsi_ob_val", 75.0))))
        rsi_breakdown_limit = float(ov.get("RSI_OVERSOLD_EXIT", os.environ.get("RSI_OVERSOLD_EXIT", cached_cfg.get("rsi_exit_val", 35.0))))
        rsi_pullback_max = float(ov.get("RSI_PULLBACK_MAX", os.environ.get("RSI_PULLBACK_MAX", cached_cfg.get("rsi_pb_val", 48.0))))
        
        # Decision Logic Matrix (Market-Optimized Criteria)
        
        # 1. SELL Conditions
        is_target_met = pnl_pct >= target_pct_limit or ltp >= (buy_price * (1 + target_pct_limit / 100.0)) or rsi14 >= rsi_overbought_limit
        is_stop_breached = pnl_pct <= stop_loss_pct_limit or ltp < (buy_price * (1 + stop_loss_pct_limit / 100.0)) or ltp < sma200
        is_rsi_breakdown = rsi14 < rsi_breakdown_limit and ltp < ema20
        
        if is_target_met:
            analysis["recommendation"] = "SELL"
            analysis["actionStrength"] = "HIGH (PROFIT EXIT)"
            analysis["freedCapitalPotential"] = analysis["currentValue"]
            analysis["targetPrice"] = round(ltp, 2)
            analysis["stopLoss"] = round(ltp * 0.96, 2)
            analysis["riskReward"] = 3.5
            if rsi14 >= rsi_overbought_limit:
                rationale.append(f"RSI overbought ({rsi14:.1f} ≥ {rsi_overbought_limit:.0f}). Lock in profits at peak momentum.")
            else:
                rationale.append(f"Target profit threshold achieved (+{pnl_pct:.1f}% gain ≥ {target_pct_limit:.0f}%). Lock in profits to recycle capital.")
            
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
                rationale.append(f"Position breached maximum swing risk threshold (-{abs(pnl_pct):.1f}% loss ≤ {stop_loss_pct_limit:.0f}%). Exit to cut losses.")
                
        elif is_rsi_breakdown:
            analysis["recommendation"] = "SELL"
            analysis["actionStrength"] = "MODERATE (RSI BREAKDOWN)"
            analysis["freedCapitalPotential"] = analysis["currentValue"]
            analysis["targetPrice"] = round(buy_price * 1.08, 2)
            analysis["stopLoss"] = round(ltp, 2)
            analysis["riskReward"] = 1.0
            rationale.append(f"Weak momentum with RSI at {rsi14:.1f} (< {rsi_breakdown_limit:.0f}) trading below 20-EMA ({ema20:.2f}). Sell to redeploy.")

        # 2. AVERAGE / ADD Conditions
        elif ltp > sma200 and rsi14 <= rsi_pullback_max and abs((ltp - ema20) / ema20) <= 0.04:
            analysis["recommendation"] = "AVERAGE"
            analysis["actionStrength"] = "HIGH (ACCUMULATE PULLBACK)"
            target = round(max(high52w * 0.98, ltp * 1.12), 2)
            sl = round(min(sma200 * 0.97, ltp * 0.94), 2)
            risk = max(ltp - sl, 1.0)
            reward = target - ltp
            analysis["targetPrice"] = target
            analysis["stopLoss"] = sl
            analysis["riskReward"] = round(reward / risk, 2)
            rationale.append(f"Healthy pullback in uptrend (above 200-SMA) near 20-EMA with RSI at {rsi14:.1f} (≤ {rsi_pullback_max:.0f}). Excellent R:R for averaging.")

        # 3. HOLD Conditions
        else:
            analysis["recommendation"] = "HOLD"
            analysis["actionStrength"] = "STABLE"
            target = round(buy_price * (1 + target_pct_limit / 100.0), 2)
            sl = round(max(sma200, buy_price * (1 + stop_loss_pct_limit / 100.0)), 2)
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
        analysis["oneTapUrl"] = build_one_tap_order_url(sym, analysis["recommendation"], qty, analysis["ltp"])
        
    except Exception as e:
        logger.error(f"Error performing technical analysis for {sym}: {e}")
        analysis["rationale"].append(f"Analysis fallback mode: {str(e)}")

    return analysis

def get_market_macro_regime() -> Dict[str, Any]:
    """
    Fetches live India VIX and Nifty 50 Index trend data to compute global macro regime & risk level.
    """
    macro = {
        "vix": 15.0,
        "niftyLtp": 0.0,
        "niftyEma20": 0.0,
        "niftySma50": 0.0,
        "status": "BALANCED",
        "riskLevel": "NORMAL",
        "label": "⚖️ Market Sentiment: Balanced Volatility (VIX 15.0)",
        "badgeColor": "green"
    }
    
    try:
        vix_df = yf.Ticker("^INDIAVIX").history(period="5d")
        if not vix_df.empty:
            vix_val = float(vix_df["Close"].dropna().iloc[-1])
            macro["vix"] = round(vix_val, 2)
            
        nifty_df = yf.Ticker("^NSEI").history(period="3mo")
        if not nifty_df.empty:
            close = nifty_df["Close"].dropna()
            ltp = float(close.iloc[-1])
            ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
            sma50 = float(close.rolling(window=min(50, len(close))).mean().iloc[-1])
            
            macro["niftyLtp"] = round(ltp, 2)
            macro["niftyEma20"] = round(ema20, 2)
            macro["niftySma50"] = round(sma50, 2)
            
            if macro["vix"] >= 18.0 or ltp < sma50:
                macro["status"] = "HIGH_VOLATILITY"
                macro["riskLevel"] = "ELEVATED_RISK"
                macro["label"] = f"⚠️ Macro Alert: High Volatility (VIX {macro['vix']:.1f}) & Nifty Market Pressure"
                macro["badgeColor"] = "red"
            elif macro["vix"] < 15.0 and ltp > ema20:
                macro["status"] = "LOW_VOLATILITY"
                macro["riskLevel"] = "BULLISH_STABLE"
                macro["label"] = f"🟢 Market Sentiment: Bullish & Stable (VIX {macro['vix']:.1f})"
                macro["badgeColor"] = "green"
            else:
                macro["status"] = "BALANCED"
                macro["riskLevel"] = "MODERATE"
                macro["label"] = f"⚖️ Market Sentiment: Moderate Volatility (VIX {macro['vix']:.1f})"
                macro["badgeColor"] = "orange"
                
    except Exception as e:
        logger.warning(f"Error fetching market macro regime data: {e}")
        
    return macro

def analyze_full_dhan_portfolio(overrides: Optional[Dict[str, float]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Scans full Dhan portfolio, executes technical analysis on all holdings,
    and calculates portfolio metrics and capital recycling allocations.
    """
    macro_regime = get_market_macro_regime()
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
        res = analyze_holding(h, overrides=overrides)
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
    
    # Capital Recycling Allocation Split (Dynamic adjustment during High Macro Volatility)
    if macro_regime["status"] == "HIGH_VOLATILITY":
        cr_midcap_pct, cr_sector_pct, cr_mom_pct, cr_etf_pct = 0.25, 0.25, 0.15, 0.35
    else:
        cr_midcap_pct, cr_sector_pct, cr_mom_pct, cr_etf_pct = 0.30, 0.30, 0.20, 0.20

    capital_recycling = {
        "totalFreedCapital": round(total_freed_capital, 2),
        "strategy1_midcap": round(total_freed_capital * cr_midcap_pct, 2),
        "strategy2_sector": round(total_freed_capital * cr_sector_pct, 2),
        "strategy3_momentum": round(total_freed_capital * cr_mom_pct, 2),
        "etf_strategy": round(total_freed_capital * cr_etf_pct, 2)
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
        "capitalRecycling": capital_recycling,
        "macroRegime": macro_regime
    }
    
    return analyzed_holdings, summary

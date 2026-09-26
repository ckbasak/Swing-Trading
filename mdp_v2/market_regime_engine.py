import os
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Representative Nifty 500 Sample Tickers for Breadth Calculation
BREADTH_SAMPLE_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "BHARTIARTL.NS", "ITC.NS", "SBIN.NS", "LTIM.NS", "AXISBANK.NS",
    "LT.NS", "KOTAKBANK.NS", "HCLTECH.NS", "M&M.NS", "TATAMOTORS.NS",
    "SUNPHARMA.NS", "NTPC.NS", "ONGC.NS", "POWERGRID.NS", "TITAN.NS",
    "BAJFINANCE.NS", "ADANIENT.NS", "ULTRACEMCO.NS", "COALINDIA.NS", "HAL.NS"
]

def get_market_breadth() -> Dict[str, float]:
    """Calculates percentage of top Indian stocks trading above 50-SMA and 200-SMA."""
    pct_above_50sma = 60.0
    pct_above_200sma = 65.0
    
    try:
        above_50_cnt = 0
        above_200_cnt = 0
        total_valid = 0
        
        # Batch download short period for sample tickers
        data = yf.download(BREADTH_SAMPLE_TICKERS, period="1y", progress=False, group_by="ticker")
        if not data.empty:
            for t in BREADTH_SAMPLE_TICKERS:
                try:
                    df_t = data[t]["Close"].dropna() if t in data else pd.Series()
                    if len(df_t) >= 50:
                        ltp = float(df_t.iloc[-1])
                        sma50 = float(df_t.tail(50).mean())
                        sma200 = float(df_t.tail(200).mean()) if len(df_t) >= 200 else sma50
                        
                        if ltp > sma50:
                            above_50_cnt += 1
                        if ltp > sma200:
                            above_200_cnt += 1
                        total_valid += 1
                except Exception:
                    continue
                    
        if total_valid > 0:
            pct_above_50sma = round((above_50_cnt / total_valid) * 100.0, 1)
            pct_above_200sma = round((above_200_cnt / total_valid) * 100.0, 1)
    except Exception as e:
        logger.warning(f"Error calculating market breadth: {e}")
        
    return {
        "pctAbove50SMA": pct_above_50sma,
        "pctAbove200SMA": pct_above_200sma
    }

def get_composite_market_regime() -> Dict[str, Any]:
    """
    Computes Indian Equity Market Regime across 4 environments:
    1. BULL_RISK_ON  (Score >= +0.50)
    2. RECOVERY     (+0.10 <= Score < +0.50)
    3. CAUTIOUS     (-0.40 <= Score < +0.10)
    4. BEAR_RISK_OFF (Score < -0.40)
    
    Combines Nifty 50 Trend, Market Breadth, India VIX, Crude Oil, USD/INR, and US Yields.
    """
    regime_data = {
        "regime": "RECOVERY",
        "compositeScore": 0.20,
        "targetEquityPct": 0.70,
        "targetCashPct": 0.30,
        "maxRiskPerTradePct": 0.01, # 1.0% portfolio equity risk
        "macroRiskModifier": 0.20,
        "vixVal": 15.0,
        "niftyLtp": 0.0,
        "niftyEma20": 0.0,
        "niftySma50": 0.0,
        "niftySma200": 0.0,
        "breadth50": 60.0,
        "breadth200": 65.0,
        "crudeOil": 75.0,
        "usdInr": 83.5,
        "us10y": 4.2,
        "label": "⚡ Market Regime: Recovery / Improving",
        "badgeColor": "orange",
        "rationale": []
    }
    
    scores = []
    rationale = []
    
    try:
        # 1. Nifty 50 Index Trend Score (-1.0 to +1.0)
        nifty_df = yf.Ticker("^NSEI").history(period="1y")
        if not nifty_df.empty and len(nifty_df) >= 50:
            close = nifty_df["Close"].dropna()
            ltp = float(close.iloc[-1])
            ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
            sma50 = float(close.rolling(window=50).mean().iloc[-1])
            sma200 = float(close.rolling(window=min(200, len(close))).mean().iloc[-1])
            
            regime_data["niftyLtp"] = round(ltp, 2)
            regime_data["niftyEma20"] = round(ema20, 2)
            regime_data["niftySma50"] = round(sma50, 2)
            regime_data["niftySma200"] = round(sma200, 2)
            
            trend_score = 0.0
            if ltp > ema20 > sma50 > sma200:
                trend_score = +1.0
                rationale.append(f"Nifty 50 ({ltp:.1f}) in strong bullish alignment above 20-EMA ({ema20:.1f}) & 50-SMA ({sma50:.1f}).")
            elif ltp > sma50 > sma200:
                trend_score = +0.5
                rationale.append(f"Nifty 50 ({ltp:.1f}) trading above 50-SMA ({sma50:.1f}). Uptrend intact.")
            elif ltp < sma200:
                trend_score = -1.0
                rationale.append(f"Nifty 50 ({ltp:.1f}) trading below key 200-SMA support ({sma200:.1f}). Long-term downtrend.")
            elif ltp < sma50:
                trend_score = -0.5
                rationale.append(f"Nifty 50 ({ltp:.1f}) below 50-SMA ({sma50:.1f}). Short-term weakening.")
            else:
                trend_score = 0.0
                rationale.append("Nifty 50 consolidating near moving averages.")
                
            scores.append(0.35 * trend_score)
            
        # 2. Market Breadth Score (-1.0 to +1.0)
        breadth = get_market_breadth()
        b50 = breadth["pctAbove50SMA"]
        b200 = breadth["pctAbove200SMA"]
        regime_data["breadth50"] = b50
        regime_data["breadth200"] = b200
        
        breadth_score = 0.0
        if b50 >= 70.0 and b200 >= 70.0:
            breadth_score = +1.0
            rationale.append(f"Strong market breadth ({b50:.0f}% stocks > 50-SMA, {b200:.0f}% > 200-SMA). Broad participation.")
        elif b50 < 40.0 or b200 < 40.0:
            breadth_score = -1.0
            rationale.append(f"Weak market breadth ({b50:.0f}% stocks > 50-SMA). Narrow or deteriorating participation.")
        else:
            breadth_score = 0.0
            rationale.append(f"Moderate market breadth ({b50:.0f}% > 50-SMA). Selective stock environment.")
            
        scores.append(0.25 * breadth_score)
        
        # 3. Volatility Structure Score (India VIX) (-1.0 to +1.0)
        vix_df = yf.Ticker("^INDIAVIX").history(period="1mo")
        if not vix_df.empty:
            vix_close = vix_df["Close"].dropna()
            vix_val = float(vix_close.iloc[-1])
            regime_data["vixVal"] = round(vix_val, 2)
            
            vix_5d_change = ((vix_val - float(vix_close.iloc[-5])) / float(vix_close.iloc[-5])) * 100.0 if len(vix_close) >= 5 else 0.0
            
            vix_score = 0.0
            if vix_val < 14.0 and vix_5d_change <= 5.0:
                vix_score = +1.0
                rationale.append(f"India VIX low and calm ({vix_val:.1f}). Favorable for risk-on swing positions.")
            elif vix_val >= 18.0 or vix_5d_change >= 15.0:
                vix_score = -1.0
                rationale.append(f"India VIX elevated or spiking ({vix_val:.1f}, {vix_5d_change:+.1f}% 5d). High market volatility.")
            else:
                vix_score = 0.0
                rationale.append(f"India VIX moderate ({vix_val:.1f}). Normal volatility environment.")
                
            scores.append(0.20 * vix_score)
            
        # 4. Global Macro Risk Modifier (-1.0 to +1.0)
        macro_score = 0.0
        try:
            crude_df = yf.Ticker("CL=F").history(period="5d")
            if not crude_df.empty:
                crude_val = float(crude_df["Close"].dropna().iloc[-1])
                regime_data["crudeOil"] = round(crude_val, 2)
                if crude_val > 85.0:
                    macro_score -= 0.4
                    rationale.append(f"Elevated Crude Oil prices (${crude_val:.1f}/bbl). Macro inflation pressure.")
                    
            usd_df = yf.Ticker("INR=X").history(period="5d")
            if not usd_df.empty:
                usd_val = float(usd_df["Close"].dropna().iloc[-1])
                regime_data["usdInr"] = round(usd_val, 2)
                if usd_val > 84.5:
                    macro_score -= 0.3
                    rationale.append(f"USD/INR depreciating (₹{usd_val:.2f}/$). Foreign capital outflow pressure.")
                    
            tnx_df = yf.Ticker("^TNX").history(period="5d")
            if not tnx_df.empty:
                tnx_val = float(tnx_df["Close"].dropna().iloc[-1])
                regime_data["us10y"] = round(tnx_val, 2)
                if tnx_val > 4.5:
                    macro_score -= 0.3
                    rationale.append(f"US 10Y Treasury Yield elevated ({tnx_val:.2f}%). Global liquidity constraint.")
        except Exception as e:
            logger.warning(f"Error fetching global macro tickers: {e}")
            
        scores.append(0.20 * max(-1.0, min(+1.0, macro_score)))
        
    except Exception as e:
        logger.error(f"Error computing composite market regime: {e}")
        
    # Calculate Final Composite Score (-1.0 to +1.0)
    composite_score = round(float(sum(scores)), 2)
    regime_data["compositeScore"] = composite_score
    
    # Classify 4 Regimes
    if composite_score >= 0.40:
        regime_data["regime"] = "BULL_RISK_ON"
        regime_data["targetEquityPct"] = 1.00  # 100% Equity / 0% Cash
        regime_data["targetCashPct"] = 0.00
        regime_data["maxRiskPerTradePct"] = 0.015 # 1.5% Portfolio Equity Risk
        regime_data["macroRiskModifier"] = 0.0
        regime_data["label"] = f"🟢 Market Regime: BULL / RISK-ON (Score {composite_score:+.2f})"
        regime_data["badgeColor"] = "green"
    elif composite_score >= 0.0:
        regime_data["regime"] = "RECOVERY"
        regime_data["targetEquityPct"] = 0.75  # 75% Equity / 25% Cash
        regime_data["targetCashPct"] = 0.25
        regime_data["maxRiskPerTradePct"] = 0.010 # 1.0% Portfolio Equity Risk
        regime_data["macroRiskModifier"] = 0.25
        regime_data["label"] = f"⚖️ Market Regime: RECOVERY / IMPROVING (Score {composite_score:+.2f})"
        regime_data["badgeColor"] = "lightgreen"
    elif composite_score >= -0.40:
        regime_data["regime"] = "CAUTIOUS"
        regime_data["targetEquityPct"] = 0.40  # 40% Equity / 60% Cash
        regime_data["targetCashPct"] = 0.60
        regime_data["maxRiskPerTradePct"] = 0.005 # 0.5% Portfolio Equity Risk
        regime_data["macroRiskModifier"] = 0.60
        regime_data["label"] = f"⚠️ Market Regime: CAUTIOUS / WEAKENING (Score {composite_score:+.2f})"
        regime_data["badgeColor"] = "orange"
    else:
        regime_data["regime"] = "BEAR_RISK_OFF"
        regime_data["targetEquityPct"] = 0.15  # 15% Equity / 85% Cash (NO NEW TRADES)
        regime_data["targetCashPct"] = 0.85
        regime_data["maxRiskPerTradePct"] = 0.000 # 0.0% Risk (NO TRADE)
        regime_data["macroRiskModifier"] = 1.00
        regime_data["label"] = f"🚨 Market Regime: BEAR / RISK-OFF (Score {composite_score:+.2f})"
        regime_data["badgeColor"] = "red"
        
    regime_data["rationale"] = rationale
    return regime_data

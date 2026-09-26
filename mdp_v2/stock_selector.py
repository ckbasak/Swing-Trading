import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from .risk_manager import calculate_atr

logger = logging.getLogger(__name__)

def calculate_relative_strength_vs_nifty(stock_df: pd.DataFrame, nifty_df: Optional[pd.DataFrame] = None) -> float:
    """Calculates 21-day Relative Performance of stock vs Nifty 50 Index."""
    try:
        if len(stock_df) < 21:
            return 0.0
            
        stock_close = stock_df["Close"].dropna()
        stock_ret = ((float(stock_close.iloc[-1]) - float(stock_close.iloc[-21])) / float(stock_close.iloc[-21])) * 100.0
        
        nifty_ret = 0.0
        if nifty_df is not None and len(nifty_df) >= 21:
            nifty_close = nifty_df["Close"].dropna()
            nifty_ret = ((float(nifty_close.iloc[-1]) - float(nifty_close.iloc[-21])) / float(nifty_close.iloc[-21])) * 100.0
            
        return round(stock_ret - nifty_ret, 2)
    except Exception as e:
        logger.warning(f"Error calculating Relative Strength: {e}")
        return 0.0

def score_and_filter_stock(
    df: pd.DataFrame,
    symbol: str,
    nifty_df: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Scores a stock setup on a 0-100 scale and evaluates the Anti-Chasing Overextension Filter.
    """
    if df.empty or len(df) < 30:
        return {
            "symbol": symbol,
            "score": 0.0,
            "passedOverextensionFilter": False,
            "isApproved": False,
            "rationale": ["Insufficient historical price data."]
        }
        
    close = df["Close"].dropna()
    ltp = float(close.iloc[-1])
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    sma50 = float(close.rolling(window=min(50, len(close))).mean().iloc[-1])
    sma200 = float(close.rolling(window=min(200, len(close))).mean().iloc[-1])
    atr = calculate_atr(df, 14)
    
    # 1. Relative Strength Score (0 to 30 pts)
    rs_diff = calculate_relative_strength_vs_nifty(df, nifty_df)
    rs_score = max(0.0, min(30.0, 15.0 + (rs_diff * 1.5)))
    
    # 2. Trend Alignment Score (0 to 25 pts)
    trend_score = 0.0
    if ltp > ema20 > sma50 > sma200:
        trend_score = 25.0
    elif ltp > sma50 > sma200:
        trend_score = 18.0
    elif ltp > sma200:
        trend_score = 10.0
    else:
        trend_score = 0.0
        
    # 3. Volume Breakout Score (0 to 20 pts)
    vol_series = df["Volume"].dropna()
    vol5 = vol_series.tail(5).mean() if len(vol_series) >= 5 else 0.0
    vol20 = vol_series.tail(20).mean() if len(vol_series) >= 20 else 1.0
    vol_ratio = float(vol5 / vol20) if vol20 > 0 else 1.0
    vol_score = max(0.0, min(20.0, (vol_ratio - 0.8) * 15.0))
    
    # 4. Volatility Compression / Squeeze Score (0 to 15 pts)
    high20 = df["High"].tail(20).max()
    low20 = df["Low"].tail(20).min()
    range_pct = ((high20 - low20) / ltp) * 100.0 if ltp > 0 else 10.0
    squeeze_score = max(0.0, min(15.0, (15.0 - range_pct) * 1.5))
    
    # 5. RSI Score (0 to 10 pts)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss.replace(0, np.nan))
    rsi = float((100 - (100 / (1 + rs))).iloc[-1])
    rsi_score = 10.0 if 50.0 <= rsi <= 65.0 else (5.0 if 40.0 <= rsi < 50.0 else 2.0)
    
    total_score = round(rs_score + trend_score + vol_score + squeeze_score + rsi_score, 1)
    
    # Anti-Chasing Filter (Reject if price > 10% extended above 20-EMA)
    extension_ratio = ((ltp - ema20) / ema20) if ema20 > 0 else 0.0
    passed_overextension_filter = extension_ratio <= 0.10
    
    is_approved = (total_score >= 60.0) and passed_overextension_filter
    
    rationale = []
    rationale.append(f"Composite Quantitative Score: {total_score:.1f}/100 (RS vs Nifty: {rs_diff:+.1f}%, Trend: {trend_score:.0f}pt, VolRatio: {vol_ratio:.2f}x).")
    if not passed_overextension_filter:
        rationale.append(f"Anti-Chasing Overextension Gate REJECTED: Price is {extension_ratio*100:.1f}% above 20-EMA (> 10% cap). Avoid buying extended top.")
        
    return {
        "symbol": symbol,
        "ltp": ltp,
        "ema20": round(ema20, 2),
        "sma200": round(sma200, 2),
        "relativeStrengthDiff": rs_diff,
        "volRatio": round(vol_ratio, 2),
        "extensionRatio": round(extension_ratio, 3),
        "totalScore": total_score,
        "passedOverextensionFilter": passed_overextension_filter,
        "isApproved": is_approved,
        "rationale": rationale
    }

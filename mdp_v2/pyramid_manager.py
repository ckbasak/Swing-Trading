import logging
import pandas as pd
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def evaluate_pyramid_addition(
    item: Dict[str, Any],
    df: pd.DataFrame,
    regime_info: Dict[str, Any],
    rs_score: float = 0.5
) -> Dict[str, Any]:
    """
    Evaluates whether adding/averaging to an existing position is permitted.
    Strictly forbids averaging down into losing/weakening stocks!
    Requires positive P&L (+3%), price above 200-SMA & 20-EMA, positive RS, and Bullish/Recovery regime.
    """
    sym = item.get("tradingSymbol", "")
    ltp = item.get("lastPrice", item.get("ltp", 0.0))
    buy_price = item.get("avgCostPrice", item.get("buyPrice", 0.0))
    pnl_pct = item.get("pnlPercentage", 0.0)
    regime = regime_info.get("regime", "RECOVERY")
    
    close = df["Close"].dropna()
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    sma200 = float(close.rolling(window=min(200, len(close))).mean().iloc[-1])
    
    # Gate 1: Position must be in profit (P&L >= +3.0%)
    in_profit = pnl_pct >= 3.0
    
    # Gate 2: Technical trend confirmation (Price > 200-SMA and near 20-EMA pullback)
    above_sma200 = ltp > sma200
    near_ema20 = abs((ltp - ema20) / ema20) <= 0.04
    
    # Gate 3: Relative Strength confirmation
    positive_rs = rs_score > 0.0
    
    # Gate 4: Market Regime confirmation
    regime_ok = regime in ["BULL_RISK_ON", "RECOVERY"]
    
    can_pyramid = in_profit and above_sma200 and near_ema20 and positive_rs and regime_ok
    
    rationale = []
    if can_pyramid:
        rationale.append(f"Selective Pyramid Gate PASSED for {sym}: Position in profit (+{pnl_pct:.1f}%), trading above 200-SMA near 20-EMA with positive RS. Addition approved.")
    else:
        reasons = []
        if not in_profit:
            reasons.append(f"position not in profit ({pnl_pct:+.1f}% < +3.0%)")
        if not above_sma200:
            reasons.append("trading below 200-SMA")
        if not near_ema20:
            reasons.append("not near 20-EMA pullback")
        if not positive_rs:
            reasons.append("negative relative strength vs Nifty")
        if not regime_ok:
            reasons.append(f"unfavorable market regime ({regime})")
        rationale.append(f"Pyramid addition REJECTED for {sym}: {', '.join(reasons)}.")
        
    return {
        "tradingSymbol": sym,
        "canPyramid": can_pyramid,
        "inProfit": in_profit,
        "aboveSma200": above_sma200,
        "nearEma20": near_ema20,
        "positiveRs": positive_rs,
        "regimeOk": regime_ok,
        "rationale": rationale
    }

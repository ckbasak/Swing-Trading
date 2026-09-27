import logging
import pandas as pd
from typing import Dict, Any, List, Optional
from .risk_manager import calculate_atr

logger = logging.getLogger(__name__)

def evaluate_adaptive_exit_strategy(
    item: Dict[str, Any],
    df: pd.DataFrame
) -> Dict[str, Any]:
    """
    Evaluates multi-stage adaptive profit taking and dynamic trailing stop.
    Does not exit strong winners on overbought RSI alone!
    """
    sym = item.get("tradingSymbol", "")
    buy_price = item.get("avgCostPrice", item.get("buyPrice", 0.0))
    ltp = item.get("lastPrice", item.get("ltp", 0.0))
    pnl_pct = item.get("pnlPercentage", 0.0)
    
    close = df["Close"].dropna()
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    sma200 = float(close.rolling(window=min(200, len(close))).mean().iloc[-1])
    atr = calculate_atr(df, 14)
    
    target_stage1 = round(buy_price + (2.0 * atr), 2)
    target_stage2 = round(buy_price + (4.0 * atr), 2)
    
    high_recent = float(df["High"].tail(20).max()) if len(df) >= 20 else ltp
    trailing_stop_atr = round(high_recent - (2.5 * atr), 2)
    
    # Adaptive Trailing Stop: Max of (Buy Price break-even, 20-EMA support, Highest High - 2.5*ATR)
    if ltp >= target_stage1:
        dynamic_sl = max(buy_price, round(ema20 * 0.98, 2), trailing_stop_atr)
    else:
        dynamic_sl = max(round(sma200, 2), round(buy_price * 0.93, 2), trailing_stop_atr)
        
    action = "HOLD"
    action_strength = "STABLE"
    rationale = []
    partial_sell_qty = 0
    total_qty = item.get("totalQty", item.get("qty", 0))
    
    # 1. Stop-Loss Exit (Structure / ATR Stop Breach)
    if ltp <= dynamic_sl or ltp < sma200 or pnl_pct <= -7.0:
        action = "SELL"
        action_strength = "HIGH (STOP-LOSS EXIT)"
        rationale.append(f"Price ({ltp:.2f}) breached dynamic volatility/structure stop ({dynamic_sl:.2f}) or 200-SMA. Exit to preserve capital.")
        
    # 2. Stage 1 Partial Profit Take (+2*ATR gain)
    elif ltp >= target_stage1 and pnl_pct >= 10.0:
        action = "SELL_PARTIAL"
        action_strength = "HIGH (STAGE-1 PROFIT LOCK)"
        partial_sell_qty = max(1, total_qty // 2)
        rationale.append(f"Target-1 (+2*ATR = ₹{target_stage1:.2f}) achieved. Lock 50% profits ({partial_sell_qty} shares) & trail remaining 50% with break-even stop at ₹{buy_price:.2f}.")
        
    # 3. Stage 2 Trend Continuation (Let Winners Run)
    elif ltp > ema20 and pnl_pct > 0:
        action = "HOLD"
        action_strength = "BULLISH_TREND_RUN"
        rationale.append(f"Strong trend intact above 20-EMA ({ema20:.2f}). Trailing stop raised to ₹{dynamic_sl:.2f}. Ride profit run.")
        
    else:
        action = "HOLD"
        action_strength = "STABLE"
        rationale.append(f"Consolidating within risk boundaries. Dynamic trailing stop set at ₹{dynamic_sl:.2f}.")
        
    return {
        "tradingSymbol": sym,
        "action": action,
        "actionStrength": action_strength,
        "targetStage1": target_stage1,
        "targetStage2": target_stage2,
        "dynamicStopLoss": dynamic_sl,
        "partialSellQty": partial_sell_qty,
        "rationale": rationale
    }

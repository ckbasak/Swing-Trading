import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calculates Average True Range (ATR-14)."""
    try:
        if len(df) < period + 1:
            return float(df["Close"].iloc[-1] * 0.03) if not df.empty else 10.0
            
        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = float(tr.rolling(window=period).mean().iloc[-1])
        return round(atr, 2) if not np.isnan(atr) and atr > 0 else round(float(close.iloc[-1] * 0.03), 2)
    except Exception as e:
        logger.warning(f"Error calculating ATR: {e}")
        return 10.0

def calculate_atr_and_structure_risk(
    df: pd.DataFrame,
    entry_price: float,
    portfolio_value: float,
    max_risk_pct_per_trade: float = 0.010
) -> Dict[str, Any]:
    """
    Computes Volatility (ATR-14) and Recent Swing Structure Stop-Loss,
    and determines risk-budgeted position sizing.
    """
    atr = calculate_atr(df, 14)
    swing_low_20d = float(df["Low"].tail(20).min()) if len(df) >= 20 else entry_price * 0.95
    
    # Structure Stop: Min of (Entry - 2*ATR) and Recent 20-day Swing Low
    atr_stop = entry_price - (2.0 * atr)
    stop_loss = max(round(min(atr_stop, swing_low_20d), 2), round(entry_price * 0.85, 2))
    
    risk_per_share = max(round(entry_price - stop_loss, 2), 1.0)
    risk_pct = round((risk_per_share / entry_price) * 100.0, 2)
    
    # Risk-Budgeted Position Sizing
    max_risk_rupees = portfolio_value * max_risk_pct_per_trade
    calculated_qty = int(max_risk_rupees // risk_per_share) if risk_per_share > 0 else 0
    
    # Position Value Cap: Max 15% of Portfolio Equity per single stock
    max_position_value_cap = portfolio_value * 0.15
    capped_qty = int(min(calculated_qty, max_position_value_cap // entry_price)) if entry_price > 0 else 0
    final_qty = max(1, capped_qty) if capped_qty > 0 else 0
    
    total_position_val = round(final_qty * entry_price, 2)
    actual_risk_rupees = round(final_qty * risk_per_share, 2)
    
    return {
        "atr": atr,
        "entryPrice": entry_price,
        "stopLoss": stop_loss,
        "riskPerShare": risk_per_share,
        "riskPercentage": risk_pct,
        "maxRiskRupeesAllowed": round(max_risk_rupees, 2),
        "targetQty": final_qty,
        "positionValue": total_position_val,
        "actualRiskRupees": actual_risk_rupees,
        "positionCapPct": round((total_position_val / portfolio_value * 100.0), 2) if portfolio_value > 0 else 0.0
    }

def calculate_portfolio_aggregate_risk(
    analyzed_holdings: List[Dict[str, Any]],
    total_portfolio_value: float
) -> Dict[str, Any]:
    """
    Calculates total aggregate portfolio open risk (Value at Risk across open positions).
    Enforces a maximum aggregate open risk threshold of 6.0% of portfolio equity.
    """
    total_open_risk = 0.0
    total_invested_value = 0.0
    
    for h in analyzed_holdings:
        ltp = h.get("ltp", 0.0)
        sl = h.get("stopLoss", ltp * 0.93)
        qty = h.get("qty", 0)
        invested = h.get("currentValue", 0.0)
        
        total_invested_value += invested
        if ltp > sl and qty > 0:
            open_risk = qty * (ltp - sl)
            total_open_risk += open_risk
            
    aggregate_risk_pct = round((total_open_risk / total_portfolio_value * 100.0), 2) if total_portfolio_value > 0 else 0.0
    
    risk_capacity_exceeded = aggregate_risk_pct >= 6.0
    
    return {
        "totalOpenRiskRupees": round(total_open_risk, 2),
        "totalOpenRiskPct": aggregate_risk_pct,
        "maxAllowedOpenRiskPct": 6.0,
        "riskCapacityExceeded": risk_capacity_exceeded,
        "availableRiskBudgetPct": max(0.0, round(6.0 - aggregate_risk_pct, 2))
    }

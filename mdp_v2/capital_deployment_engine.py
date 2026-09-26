import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def calculate_dynamic_capital_deployment(
    total_portfolio_value: float,
    current_equity_exposure: float,
    available_liquid_cash: float,
    freed_capital_from_sells: float,
    regime_info: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculates dynamic capital deployment based on prevailing Market Regime and Portfolio Risk.
    Eliminates forced automatic reallocation! Cash is treated as an active risk-preservation asset.
    """
    regime = regime_info.get("regime", "RECOVERY")
    target_equity_pct = regime_info.get("targetEquityPct", 0.75)
    target_cash_pct = regime_info.get("targetCashPct", 0.25)
    
    target_equity_value = total_portfolio_value * target_equity_pct
    target_cash_value = total_portfolio_value * target_cash_pct
    
    current_cash = max(0.0, total_portfolio_value - current_equity_exposure)
    
    # Allowed headroom to deploy into new equity positions
    equity_headroom = max(0.0, target_equity_value - current_equity_exposure)
    allowed_new_capital = min(available_liquid_cash + freed_capital_from_sells, equity_headroom)
    
    # If Market Regime is BEAR_RISK_OFF or Cautious with no headroom, hold cash 100%
    hold_cash_flag = False
    deployment_status = "ACTIVE_DEPLOYMENT"
    rationale = []
    
    if regime == "BEAR_RISK_OFF":
        allowed_new_capital = 0.0
        hold_cash_flag = True
        deployment_status = "HOLD_CASH_100%"
        rationale.append(f"Market Regime is BEAR / RISK-OFF. All freed capital (₹{freed_capital_from_sells:,.2f}) held in cash to preserve capital.")
    elif allowed_new_capital < 10000.0:
        allowed_new_capital = 0.0
        hold_cash_flag = True
        deployment_status = "HOLD_CASH_TARGET_MET"
        rationale.append(f"Target cash allocation of {target_cash_pct*100:.0f}% (₹{target_cash_value:,.2f}) reached. Capital reinvestment paused.")
    else:
        rationale.append(f"Market Regime ({regime}) permits ₹{allowed_new_capital:,.2f} dynamic deployment (Target Cash: {target_cash_pct*100:.0f}%).")
        
    return {
        "regime": regime,
        "totalPortfolioValue": round(total_portfolio_value, 2),
        "currentEquityExposure": round(current_equity_exposure, 2),
        "targetEquityValue": round(target_equity_value, 2),
        "targetCashValue": round(target_cash_value, 2),
        "availableLiquidCash": round(available_liquid_cash, 2),
        "freedCapitalFromSells": round(freed_capital_from_sells, 2),
        "allowedNewCapital": round(allowed_new_capital, 2),
        "retainedCash": round((available_liquid_cash + freed_capital_from_sells) - allowed_new_capital, 2),
        "holdCashFlag": hold_cash_flag,
        "deploymentStatus": deployment_status,
        "rationale": rationale
    }

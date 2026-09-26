import math
from typing import Dict, Any, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DynamicSizing")

class DynamicSizer:
    """
    V2 Dynamic Position Sizing Engine.
    Scales trade risk based on:
    Trade Risk $ = Base Risk $ * M_regime * M_drawdown * M_quality * M_volatility
    Shares = floor(Trade Risk $ / (Entry Price - Stop Loss))
    """

    def __init__(self, base_risk_pct: float = 0.015, baseline_atr_pct: float = 0.025):
        self.base_risk_pct = base_risk_pct         # 1.5% base portfolio risk
        self.baseline_atr_pct = baseline_atr_pct   # 2.5% baseline stock ATR

    def calculate_trade_quality_multiplier(self, candidate: Dict[str, Any]) -> float:
        """
        Calculates trade quality multiplier M_quality in [0.70, 1.30].
        Evaluates volume expansion, RSI momentum, and price candle strength.
        """
        m_quality = 1.00

        vol_ratio = float(candidate.get("volume_ratio", 1.0))
        if vol_ratio >= 3.5:
            m_quality += 0.20
        elif vol_ratio >= 2.5:
            m_quality += 0.10
        elif vol_ratio < 2.0:
            m_quality -= 0.15

        rsi = float(candidate.get("rsi_14", 50.0))
        if 58.0 <= rsi <= 68.0:
            m_quality += 0.10
        elif rsi > 75.0 or rsi < 45.0:
            m_quality -= 0.10

        price_expansion = candidate.get("price_expansion", 0.65)
        if price_expansion >= 0.75:
            m_quality += 0.10
        elif price_expansion < 0.50:
            m_quality -= 0.15

        return round(float(math.fsum([0.0, max(0.70, min(1.30, m_quality))])), 2)

    def calculate_volatility_multiplier(self, entry_price: float, atr_14: float) -> float:
        """
        Calculates stock volatility multiplier M_volatility.
        Scales down position size during high volatility spikes (large ATR).
        """
        if entry_price <= 0 or atr_14 <= 0:
            return 1.00

        stock_atr_pct = atr_14 / entry_price
        if stock_atr_pct <= 0:
            return 1.00

        m_vol = self.baseline_atr_pct / stock_atr_pct
        return round(float(max(0.50, min(1.50, m_vol))), 2)

    def calculate_position_size(
        self,
        candidate: Dict[str, Any],
        portfolio_value: float,
        market_regime: Dict[str, Any],
        portfolio_risk_status: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculates adaptive position size, exact quantity, risk amount, and stop loss.
        """
        entry_price = float(candidate.get("close", 0.0))
        atr_14 = float(candidate.get("atr_14", 0.0))

        if entry_price <= 0:
            return {"error": "Invalid entry price", "quantity": 0}

        # 1. Calculate Stop Loss (2x ATR(14) below entry)
        if atr_14 > 0:
            risk_per_share = 2.0 * atr_14
            initial_sl = entry_price - risk_per_share
        else:
            risk_per_share = entry_price * 0.04
            initial_sl = entry_price - risk_per_share

        if risk_per_share <= 0:
            return {"error": "Risk per share <= 0", "quantity": 0}

        # 2. Extract Sizing Multipliers
        m_regime = float(market_regime.get("max_sizing_multiplier", 1.00))
        m_drawdown = float(portfolio_risk_status.get("drawdown_multiplier", 1.00))
        m_quality = self.calculate_trade_quality_multiplier(candidate)
        m_volatility = self.calculate_volatility_multiplier(entry_price, atr_14)

        # 3. Dynamic Trade Risk Dollars
        base_risk_dollars = portfolio_value * self.base_risk_pct
        adaptive_risk_dollars = (
            base_risk_dollars * m_regime * m_drawdown * m_quality * m_volatility
        )

        # Cap trade risk at remaining risk budget
        remaining_budget = portfolio_risk_status.get("remaining_risk_budget_val", adaptive_risk_dollars)
        adaptive_risk_dollars = min(adaptive_risk_dollars, remaining_budget)

        # 4. Shares calculation
        shares = math.floor(adaptive_risk_dollars / risk_per_share)
        total_cost = shares * entry_price
        actual_risk_deployed = shares * risk_per_share

        # 5. Cap single position value (Adaptive: 15.0% for portfolios < ₹5L, 8.0% for portfolios >= ₹5L)
        effective_cap_pct = 0.15 if portfolio_value < 500000.0 else 0.08
        max_position_cost = portfolio_value * effective_cap_pct
        if total_cost > max_position_cost:
            shares = math.floor(max_position_cost / entry_price)
            total_cost = shares * entry_price
            actual_risk_deployed = shares * risk_per_share

        target_price = entry_price + (2.0 * risk_per_share)

        return {
            "ticker": candidate.get("ticker"),
            "entry_price": round(entry_price, 2),
            "quantity": shares,
            "initial_sl": round(initial_sl, 2),
            "target_price": round(target_price, 2),
            "total_cost": round(total_cost, 2),
            "risk_per_share": round(risk_per_share, 2),
            "actual_risk_dollars": round(actual_risk_deployed, 2),
            "multipliers": {
                "m_regime": m_regime,
                "m_drawdown": m_drawdown,
                "m_quality": m_quality,
                "m_volatility": m_volatility
            }
        }

_sizer_instance = None

def get_dynamic_sizer() -> DynamicSizer:
    global _sizer_instance
    if _sizer_instance is None:
        _sizer_instance = DynamicSizer()
    return _sizer_instance

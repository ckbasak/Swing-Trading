import math
from typing import Dict, Any, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PortfolioRiskEngine")

class PortfolioRiskEngine:
    """
    V2 Central Portfolio Risk Authority & Capital Allocation Engine.
    Enforces:
    1. 6.0% Aggregate Portfolio Risk Cap across all active positions.
    2. 20.0% Global Sector Concentration Cap (or max 3 positions per sector).
    3. 8.0% Single Stock Maximum Exposure Limit.
    4. Drawdown Preservation Curve (Drawdown multiplier M_drawdown).
    5. Minimum Cash Reserve Floor based on Market Regime.
    """

    def __init__(
        self,
        max_aggregate_risk_pct: float = 0.06,  # 6.0% total capital at risk
        max_sector_exposure_pct: float = 0.20, # 20.0% sector cap
        max_stock_exposure_pct: float = 0.08,  # 8.0% single stock cap
        max_drawdown_limit_pct: float = 0.10   # 10.0% max allowed drawdown limit
    ):
        self.max_aggregate_risk_pct = max_aggregate_risk_pct
        self.max_sector_exposure_pct = max_sector_exposure_pct
        self.max_stock_exposure_pct = max_stock_exposure_pct
        self.max_drawdown_limit_pct = max_drawdown_limit_pct

    def calculate_drawdown_multiplier(
        self,
        current_portfolio_value: float,
        peak_portfolio_value: float
    ) -> Tuple[float, float, str]:
        """
        Calculates current portfolio drawdown and returns Drawdown Multiplier M_drawdown in [0.20, 1.00].
        If drawdown exceeds 10%, returns M_drawdown = 0.0 (Capital Preservation Mode).
        """
        if peak_portfolio_value <= 0 or current_portfolio_value >= peak_portfolio_value:
            return 1.0, 0.0, "PEAK_EQUITY"

        drawdown_pct = (peak_portfolio_value - current_portfolio_value) / peak_portfolio_value

        if drawdown_pct >= self.max_drawdown_limit_pct:
            return 0.0, round(drawdown_pct * 100.0, 2), "CAPITAL_PRESERVATION_MODE"

        # Linear reduction curve down to 0.20 multiplier at max allowed DD
        m_dd = max(0.20, 1.0 - (2.5 * (drawdown_pct / self.max_drawdown_limit_pct)))
        return round(m_dd, 2), round(drawdown_pct * 100.0, 2), "NORMAL_REDUCTION"

    def evaluate_portfolio_risk(
        self,
        open_positions: List[Dict[str, Any]],
        portfolio_value: float,
        cash_balance: float,
        peak_portfolio_value: float,
        market_regime: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluates overall aggregate portfolio risk metrics and returns health status.
        """
        if portfolio_value <= 0:
            return {"error": "Invalid portfolio value"}

        # 1. Total Capital at Risk calculation
        total_risk_val = 0.0
        total_open_val = 0.0
        sector_exposure_val: Dict[str, float] = {}
        sector_position_counts: Dict[str, int] = {}
        stock_exposure_val: Dict[str, float] = {}

        for pos in open_positions:
            try:
                qty = float(pos.get("Quantity", 0))
                entry = float(pos.get("Entry Price", 0.0))
                sl = float(pos.get("Stop Loss", pos.get("Trailing SL", entry * 0.95)))
                ticker = pos.get("Ticker", "")
                sector = pos.get("Sector", "Unknown")

                pos_val = qty * entry
                risk_val = max(0.0, qty * (entry - sl))

                total_open_val += pos_val
                total_risk_val += risk_val

                sector_exposure_val[sector] = sector_exposure_val.get(sector, 0.0) + pos_val
                sector_position_counts[sector] = sector_position_counts.get(sector, 0) + 1
                stock_exposure_val[ticker] = stock_exposure_val.get(ticker, 0.0) + pos_val
            except Exception as e:
                logger.warning(f"Error parsing position risk for {pos}: {e}")

        current_risk_pct = total_risk_val / portfolio_value
        max_allowed_risk_val = portfolio_value * self.max_aggregate_risk_pct
        remaining_risk_budget_val = max(0.0, max_allowed_risk_val - total_risk_val)

        # 2. Drawdown & Capital Preservation Curve
        m_dd, drawdown_pct, dd_status = self.calculate_drawdown_multiplier(
            current_portfolio_value=portfolio_value,
            peak_portfolio_value=peak_portfolio_value
        )

        # 3. Cash Floor Check
        min_cash_pct = market_regime.get("min_cash_reserve_pct", 0.10)
        min_cash_required = portfolio_value * min_cash_pct
        actual_cash_pct = cash_balance / portfolio_value

        return {
            "portfolio_value": portfolio_value,
            "cash_balance": cash_balance,
            "actual_cash_pct": round(actual_cash_pct * 100.0, 2),
            "min_cash_required_pct": round(min_cash_pct * 100.0, 2),
            "cash_floor_respected": cash_balance >= min_cash_required,
            "total_open_value": round(total_open_val, 2),
            "total_open_exposure_pct": round((total_open_val / portfolio_value) * 100.0, 2),
            "total_risk_value": round(total_risk_val, 2),
            "current_risk_pct": round(current_risk_pct * 100.0, 2),
            "max_allowed_risk_pct": round(self.max_aggregate_risk_pct * 100.0, 2),
            "remaining_risk_budget_val": round(remaining_risk_budget_val, 2),
            "risk_cap_reached": current_risk_pct >= self.max_aggregate_risk_pct,
            "drawdown_pct": drawdown_pct,
            "drawdown_multiplier": m_dd,
            "drawdown_status": dd_status,
            "sector_exposure_pct": {sec: round((val / portfolio_value) * 100.0, 2) for sec, val in sector_exposure_val.items()},
            "sector_counts": sector_position_counts,
            "stock_exposure_pct": {tkr: round((val / portfolio_value) * 100.0, 2) for tkr, val in stock_exposure_val.items()}
        }

    def validate_trade_permission(
        self,
        candidate_ticker: str,
        candidate_sector: str,
        proposed_cost: float,
        proposed_risk: float,
        portfolio_risk_status: Dict[str, Any],
        market_regime: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Validates whether a proposed trade passes central portfolio risk rules.
        Returns (is_approved, rejection_reason).
        """
        regime_label = market_regime.get("classification", "NEUTRAL_CHOPPY")

        # Check 1: Market Regime Halt
        if regime_label in ["BEAR_RISK_OFF", "EXTREME_SHOCK"]:
            return False, f"NO-TRADE Gate: Market Regime is {regime_label}. New buys strictly halted."

        # Check 2: Capital Preservation Mode
        if portfolio_risk_status.get("drawdown_status") == "CAPITAL_PRESERVATION_MODE":
            return False, f"NO-TRADE Gate: Portfolio drawdown (-{portfolio_risk_status.get('drawdown_pct')}%) exceeded 10.0% max limit."

        # Check 3: Aggregate Portfolio Risk Cap
        if portfolio_risk_status.get("risk_cap_reached", False):
            return False, f"NO-TRADE Gate: Aggregate portfolio risk cap (6.0%) fully utilized."

        remaining_risk_budget = portfolio_risk_status.get("remaining_risk_budget_val", 0.0)
        if proposed_risk > remaining_risk_budget:
            return False, f"NO-TRADE Gate: Proposed risk (₹{proposed_risk:,.2f}) exceeds remaining risk budget (₹{remaining_risk_budget:,.2f})."

        # Check 4: Sector Concentration Cap (20% or max 3 positions)
        port_val = portfolio_risk_status.get("portfolio_value", 1.0)
        curr_sector_val = portfolio_risk_status.get("sector_exposure_pct", {}).get(candidate_sector, 0.0) / 100.0 * port_val
        curr_sector_count = portfolio_risk_status.get("sector_counts", {}).get(candidate_sector, 0)

        if (curr_sector_val + proposed_cost) / port_val > self.max_sector_exposure_pct:
            return False, f"NO-TRADE Gate: Sector '{candidate_sector}' exposure would exceed 20.0% portfolio cap."

        if curr_sector_count >= 3:
            return False, f"NO-TRADE Gate: Sector '{candidate_sector}' already has 3 open positions."

        # Check 5: Single Stock Exposure Cap (Adaptive: 15.0% for portfolios < ₹5L, 8.0% for portfolios >= ₹5L)
        effective_stock_cap = 0.15 if port_val < 500000.0 else self.max_stock_exposure_pct
        curr_stock_val = portfolio_risk_status.get("stock_exposure_pct", {}).get(candidate_ticker, 0.0) / 100.0 * port_val
        if (curr_stock_val + proposed_cost) / port_val > effective_stock_cap:
            return False, f"NO-TRADE Gate: Single stock exposure for '{candidate_ticker}' would exceed {effective_stock_cap * 100:.1f}% cap."

        # Check 6: Cash Reserve Floor
        cash_balance = portfolio_risk_status.get("cash_balance", 0.0)
        min_cash_required_pct = portfolio_risk_status.get("min_cash_required_pct", 10.0) / 100.0
        min_cash_val = port_val * min_cash_required_pct

        if (cash_balance - proposed_cost) < min_cash_val:
            return False, f"NO-TRADE Gate: Trade cost (₹{proposed_cost:,.2f}) breaches minimum cash reserve floor (₹{min_cash_val:,.2f})."

        return True, "APPROVED"

_risk_engine_instance = None

def get_risk_engine() -> PortfolioRiskEngine:
    global _risk_engine_instance
    if _risk_engine_instance is None:
        _risk_engine_instance = PortfolioRiskEngine()
    return _risk_engine_instance

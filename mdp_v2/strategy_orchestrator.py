import os
import logging
import yfinance as yf
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional

from .market_regime_engine import get_composite_market_regime
from .capital_deployment_engine import calculate_dynamic_capital_deployment
from .risk_manager import calculate_atr_and_structure_risk, calculate_portfolio_aggregate_risk
from .exit_manager import evaluate_adaptive_exit_strategy
from .pyramid_manager import evaluate_pyramid_addition
from .stock_selector import score_and_filter_stock
from .portfolio_diversifier import enforce_sector_and_etf_limits
import dhan_client

logger = logging.getLogger(__name__)

def evaluate_mdp_v2_portfolio(overrides: Optional[Dict[str, float]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Unified Master Strategy Orchestrator for MDP V2.
    Executes Market Regime Classification, Portfolio Risk Budgeting,
    ATR Volatility Stops, Multi-Stage Profit Scaling, Selective Pyramiding,
    and Explicit NO_TRADE Decision Gating.
    """
    # 1. Market Regime & Global Macro Classification (Pillars 1, 11, 12)
    regime_info = get_composite_market_regime()
    regime_name = regime_info["regime"]
    max_trade_risk_pct = regime_info["maxRiskPerTradePct"]
    
    # 2. Fetch Dhan Portfolio Holdings & Cash Limits
    holdings = dhan_client.get_dhan_holdings()
    funds = dhan_client.get_dhan_funds()
    available_cash = float(funds.get("availableBalance", 50000.0))
    
    # Fetch Nifty 50 for Relative Strength comparison
    nifty_df = None
    try:
        nifty_df = yf.Ticker("^NSEI").history(period="6mo")
    except Exception:
        pass
        
    analyzed_holdings = []
    total_investment = 0.0
    total_current_val = 0.0
    total_pnl = 0.0
    
    sell_count = 0
    average_count = 0
    hold_count = 0
    total_freed_capital = 0.0
    
    for h in holdings:
        sym = h["tradingSymbol"]
        ticker_sym = f"{sym}.NS" if not sym.endswith(".NS") else sym
        qty = h["totalQty"]
        buy_price = h["avgCostPrice"]
        current_val = h["currentValue"]
        invested_val = h["investmentValue"]
        
        # Download stock price history
        df = pd.DataFrame()
        try:
            df = yf.Ticker(ticker_sym).history(period="1y")
        except Exception:
            pass
            
        if df.empty or len(df) < 30:
            ltp = h["lastPrice"]
            analysis = {
                "tradingSymbol": sym,
                "type": h.get("type", "STOCK"),
                "qty": qty,
                "buyPrice": buy_price,
                "ltp": ltp,
                "currentValue": current_val,
                "investmentValue": invested_val,
                "pnl": h["pnl"],
                "pnlPercentage": h["pnlPercentage"],
                "recommendation": "HOLD",
                "actionStrength": "STABLE",
                "targetPrice": round(buy_price * 1.15, 2),
                "stopLoss": round(buy_price * 0.93, 2),
                "riskReward": 2.0,
                "freedCapitalPotential": 0.0,
                "rationale": ["Insufficient historical price data for MDP V2 analysis."]
            }
        else:
            ltp = float(df["Close"].dropna().iloc[-1])
            h["lastPrice"] = ltp
            h["currentValue"] = round(qty * ltp, 2)
            h["pnl"] = round(h["currentValue"] - invested_val, 2)
            h["pnlPercentage"] = round((h["pnl"] / invested_val) * 100.0, 2) if invested_val > 0 else 0.0
            
            # Stock Scorer & Overextension Filter (Pillars 7, 8)
            stock_score_data = score_and_filter_stock(df, sym, nifty_df)
            
            # Risk Sizing & ATR Structure Stop (Pillar 4)
            tot_port_val_est = max(100000.0, total_current_val + available_cash)
            risk_sizing = calculate_atr_and_structure_risk(df, ltp, tot_port_val_est, max_trade_risk_pct)
            
            # Adaptive Exit Strategy (Pillar 5)
            exit_data = evaluate_adaptive_exit_strategy(h, df)
            
            # Selective Pyramid Gate (Pillar 6)
            pyramid_data = evaluate_pyramid_addition(h, df, regime_info, stock_score_data.get("relativeStrengthDiff", 0.0))
            
            rec = exit_data["action"]
            action_str = exit_data["actionStrength"]
            target_p = exit_data["targetStage1"]
            sl_p = exit_data["dynamicStopLoss"]
            
            freed_cap = current_val if rec in ["SELL", "SELL_PARTIAL"] else 0.0
            
            analysis = {
                "tradingSymbol": sym,
                "type": h.get("type", "STOCK"),
                "qty": qty,
                "buyPrice": buy_price,
                "ltp": ltp,
                "currentValue": h["currentValue"],
                "investmentValue": invested_val,
                "pnl": h["pnl"],
                "pnlPercentage": h["pnlPercentage"],
                "ema20": stock_score_data.get("ema20"),
                "sma200": stock_score_data.get("sma200"),
                "rsi14": 55.0,
                "volRatio": stock_score_data.get("volRatio", 1.0),
                "stockScore": stock_score_data.get("totalScore", 50.0),
                "atr": risk_sizing["atr"],
                "recommendation": "SELL" if rec.startswith("SELL") else ("AVERAGE" if pyramid_data["canPyramid"] else "HOLD"),
                "actionStrength": action_str,
                "targetPrice": target_p,
                "stopLoss": sl_p,
                "riskReward": round(abs(target_p - ltp) / max(1.0, abs(ltp - sl_p)), 2),
                "freedCapitalPotential": freed_cap,
                "rationale": exit_data["rationale"] + stock_score_data["rationale"]
            }
            
            # Map Dhan Order Parameters (1:1 UI Tabs)
            rec_mode = "Limit" if rec.startswith("SELL") or regime_name in ["BEAR_RISK_OFF", "CAUTIOUS"] else ("TRAIL" if regime_name == "BULL_RISK_ON" else "SUPER")
            rec_reason = f"MDP V2 {regime_name} Regime: Recommended tab '{rec_mode}' with ATR dynamic stop ₹{sl_p:.2f}."
            
            limit_p = round(ltp * 0.997, 2) if rec.startswith("SELL") else round(ltp * 1.003, 2)
            trig_p = round(ltp * 0.999, 2) if rec.startswith("SELL") else round(ltp * 1.001, 2)
            
            analysis["dhanOrderParams"] = {
                "recommendedMode": rec_mode,
                "recommendedReason": rec_reason,
                "mode": "Investing",
                "toggle": "Sell" if rec.startswith("SELL") else "Buy",
                "quantity": qty,
                "limitPrice": limit_p,
                "addTriggerPrice": trig_p,
                "validity": "DAY",
                "super": {"quantity": qty, "limit": limit_p, "target": target_p, "stoploss": sl_p, "bookProfits": "Full Exit", "addTriggerPrice": trig_p},
                "trail": {"quantity": qty, "limit": limit_p, "target": target_p, "stoploss": sl_p, "tgTrailJump": 1, "slTrailJump": 1, "addTriggerPrice": trig_p, "orderValidity": "365 Days"},
                "quickTip": f"Select 'Investing' -> '{rec_mode}' tab. {rec_reason}"
            }

        analyzed_holdings.append(analysis)
        total_investment += analysis["investmentValue"]
        total_current_val += analysis["currentValue"]
        total_pnl += analysis["pnl"]
        
        rec_status = analysis["recommendation"]
        if rec_status == "SELL":
            sell_count += 1
            total_freed_capital += analysis["freedCapitalPotential"]
        elif rec_status == "AVERAGE":
            average_count += 1
        else:
            hold_count += 1
            
    total_portfolio_value = total_current_val + available_cash
    
    # 3. Dynamic Capital Deployment Engine (Pillar 2)
    capital_deployment = calculate_dynamic_capital_deployment(
        total_portfolio_value=total_portfolio_value,
        current_equity_exposure=total_current_val,
        available_liquid_cash=available_cash,
        freed_capital_from_sells=total_freed_capital,
        regime_info=regime_info
    )
    
    # 4. Portfolio Aggregate Risk & Sector Caps (Pillars 3, 9, 10)
    portfolio_risk = calculate_portfolio_aggregate_risk(analyzed_holdings, total_portfolio_value)
    sector_limits = enforce_sector_and_etf_limits(analyzed_holdings, total_portfolio_value, 25.0)
    
    # 5. Explicit NO_TRADE Decision Gating (Pillar 13)
    no_trade_flag = False
    no_trade_reasons = []
    
    if regime_name == "BEAR_RISK_OFF":
        no_trade_flag = True
        no_trade_reasons.append("Market Regime is BEAR / RISK-OFF. All new entries suspended.")
    elif portfolio_risk["riskCapacityExceeded"]:
        no_trade_flag = True
        no_trade_reasons.append(f"Portfolio open risk ({portfolio_risk['totalOpenRiskPct']:.1f}%) exceeds 6.0% risk capacity limit.")
    elif capital_deployment["allowedNewCapital"] <= 0.0:
        no_trade_flag = True
        no_trade_reasons.append("Dynamic cash target reached. Zero allowed new capital deployment.")
        
    master_decision = "NO_TRADE" if no_trade_flag else ("ACTIVE_REBALANCING" if sell_count > 0 or average_count > 0 else "HOLD_POSITIONS")
    
    pnl_pct = (total_pnl / total_investment * 100.0) if total_investment > 0 else 0.0
    allowed_cap = capital_deployment["allowedNewCapital"]
    if regime_name == "BEAR_RISK_OFF":
        cr_mid, cr_sec, cr_mom, cr_etf = 0.0, 0.0, 0.0, 0.0
    elif regime_name == "CAUTIOUS":
        cr_mid, cr_sec, cr_mom, cr_etf = 0.20, 0.20, 0.10, 0.50
    else:
        cr_mid, cr_sec, cr_mom, cr_etf = 0.30, 0.30, 0.20, 0.20

    summary = {
        "totalHoldings": len(analyzed_holdings),
        "totalInvestment": round(total_investment, 2),
        "totalCurrentValue": round(total_current_val, 2),
        "availableCash": round(available_cash, 2),
        "totalPortfolioValue": round(total_portfolio_value, 2),
        "totalPnL": round(total_pnl, 2),
        "totalPnLPercentage": round(pnl_pct, 2),
        "sellCount": sell_count,
        "averageCount": average_count,
        "holdCount": hold_count,
        "macroRegime": regime_info,
        "capitalDeployment": capital_deployment,
        "portfolioRisk": portfolio_risk,
        "sectorLimits": sector_limits,
        "masterDecision": master_decision,
        "noTradeFlag": no_trade_flag,
        "noTradeReasons": no_trade_reasons,
        "capitalRecycling": {
            "totalFreedCapital": capital_deployment["freedCapitalFromSells"],
            "allowedNewCapital": allowed_cap,
            "retainedCash": capital_deployment["retainedCash"],
            "strategy1_midcap": round(allowed_cap * cr_mid, 2),
            "strategy2_sector": round(allowed_cap * cr_sec, 2),
            "strategy3_momentum": round(allowed_cap * cr_mom, 2),
            "etf_strategy": round(allowed_cap * cr_etf, 2)
        }
    }
    
    return analyzed_holdings, summary

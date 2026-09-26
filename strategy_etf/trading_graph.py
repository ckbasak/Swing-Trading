import os
import math
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END

# Import backend modules
import screener
import portfolio_manager
import dhan_client
import sentiment_analyzer
import market_regime
import portfolio_risk_engine
import dynamic_sizing
import correlation_sentinel

class TradingState(TypedDict, total=False):
    candidates: List[Dict[str, Any]]
    open_positions: List[Dict[str, Any]]
    portfolio_value: float
    cash_balance: float
    peak_portfolio_value: float
    risk_per_trade: float
    trades_to_execute: List[Dict[str, Any]]
    execute_trades: bool
    macro_sentiment: Dict[str, Any]
    market_regime: Dict[str, Any]
    portfolio_risk_status: Dict[str, Any]
    logs: List[str]

def sync_portfolio_node(state: TradingState) -> Dict[str, Any]:
    """
    Node 1: Syncs current portfolio, processes exits, evaluates macro guardrails,
    computes composite Market Regime & Central Portfolio Risk Status.
    """
    logs = state.get("logs", [])
    logs.append("--- Node: Syncing Portfolio, Market Regime & Portfolio Risk Engine ---")
    
    try:
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        
        # 1. Analyze comprehensive market macro sentiment
        macro_data = sentiment_analyzer.get_comprehensive_market_macro_sentiment()
        
        # 2. Sync open positions with macro guardrail directives
        sync_logs = portfolio_manager.sync_portfolio(sh, macro_data=macro_data)
        logs.extend(sync_logs)
        
        # 3. Get updated account details
        account = portfolio_manager.get_account_details(sh)
        portfolio_value = float(account["Total Portfolio Value"])
        cash_balance = float(account["Cash Balance"])
        risk_pct = float(account.get("Risk Percent", 0.015))
        
        open_positions = portfolio_manager.get_open_positions(sh)
        
        # Track Peak Equity for Drawdown Curve
        peak_equity = float(account.get("Peak Portfolio Value", portfolio_value))
        if portfolio_value > peak_equity:
            peak_equity = portfolio_value
            
        # 4. Calculate V2 Market Regime Score
        regime_data = market_regime.get_market_regime(macro_sentiment_data=macro_data)
        
        # 5. Evaluate Central Portfolio Risk Engine
        risk_engine = portfolio_risk_engine.get_risk_engine()
        risk_status = risk_engine.evaluate_portfolio_risk(
            open_positions=open_positions,
            portfolio_value=portfolio_value,
            cash_balance=cash_balance,
            peak_portfolio_value=peak_equity,
            market_regime=regime_data
        )
        
        logs.append(f"Portfolio Value: INR {portfolio_value:,.2f} | Peak Value: INR {peak_equity:,.2f}")
        logs.append(f"Cash Balance: INR {cash_balance:,.2f} (Actual: {risk_status['actual_cash_pct']}%, Min Required: {risk_status['min_cash_required_pct']}%)")
        logs.append(
            f"Market Regime Score: {regime_data['regime_score']}/100 | "
            f"Classification: {regime_data['color']} {regime_data['classification']} "
            f"(Max Sizing: {regime_data['max_sizing_multiplier']*100:.0f}%)"
        )
        logs.append(
            f"Portfolio Risk Status: Total Risk = {risk_status['current_risk_pct']}% / {risk_status['max_allowed_risk_pct']}% Cap | "
            f"Drawdown = -{risk_status['drawdown_pct']}% (Multiplier: {risk_status['drawdown_multiplier']}x)"
        )
        
        return {
            "open_positions": open_positions,
            "portfolio_value": portfolio_value,
            "cash_balance": cash_balance,
            "peak_portfolio_value": peak_equity,
            "risk_per_trade": portfolio_value * risk_pct,
            "macro_sentiment": macro_data,
            "market_regime": regime_data,
            "portfolio_risk_status": risk_status,
            "logs": logs
        }
    except Exception as e:
        logs.append(f"Error in sync_portfolio_node: {e}")
        return {"logs": logs}

def scan_market_node(state: TradingState) -> Dict[str, Any]:
    """
    Node 2: Runs the Nifty 50 screener to find new breakout candidates with false-breakout filters.
    """
    logs = state.get("logs", [])
    logs.append("--- Node: Scanning Market & Filtering False Breakouts ---")
    
    try:
        tickers = screener.get_nifty_250_tickers()
        logs.append(f"Scanning Nifty {len(tickers)} universe for breakouts...")
        macro_data = state.get("macro_sentiment")
        candidates = screener.screen_stocks(tickers, logs=logs, macro_data=macro_data)
        
        logs.append(f"Found {len(candidates)} breakout candidates.")
        for idx, c in enumerate(candidates):
            logs.append(
                f"Candidate {idx+1}: {c['ticker']} ({c.get('sector', 'Unknown')}) | "
                f"Close: {c['close']:.2f} | Vol Ratio: {c['volume_ratio']:.2f}x | "
                f"RSI(14): {c.get('rsi_14', 0.0):.1f} | ATR(14): {c.get('atr_14', 0.0):.2f} | "
                f"Price Expansion: {c.get('price_expansion', 0.60):.2f}"
            )
            
        return {
            "candidates": candidates,
            "logs": logs
        }
    except Exception as e:
        logs.append(f"Error in scan_market_node: {e}")
        return {"logs": logs}

def calculate_positions_node(state: TradingState) -> Dict[str, Any]:
    """
    Node 3: Central Risk & Dynamic Position Sizing Gate:
    1. Cross-Strategy De-duplication & Correlation Matrix Blocker (rho <= 0.75)
    2. Central Portfolio Risk Engine Validation (6% risk cap, 20% sector cap, 8% stock cap, cash floor)
    3. Dynamic Sizing Formula (Regime + Drawdown + Quality + Volatility)
    4. Genuine NO-TRADE Gate output if capital preservation is warranted.
    """
    logs = state.get("logs", [])
    logs.append("--- Node: Central Portfolio Risk & Dynamic Position Sizing Gate ---")
    
    candidates = state.get("candidates", [])
    open_positions = state.get("open_positions", [])
    portfolio_value = state.get("portfolio_value", 0.0)
    cash_balance = state.get("cash_balance", 0.0)
    regime_data = state.get("market_regime", {})
    risk_status = state.get("portfolio_risk_status", {})
    
    risk_engine = portfolio_risk_engine.get_risk_engine()
    sizer = dynamic_sizing.get_dynamic_sizer()
    corr_sentinel = correlation_sentinel.get_correlation_sentinel()
    
    trades_to_execute = []
    buy_count = 0
    no_trade_reasons = []

    # Check 1: Regime Halt
    if regime_data.get("classification") in ["BEAR_RISK_OFF", "EXTREME_SHOCK"]:
        msg = f"🛑 NO-TRADE DECISION: Market Regime is {regime_data.get('classification')}. All buy entries halted."
        logs.append(msg)
        return {"trades_to_execute": [], "logs": logs}

    # Check 2: Capital Preservation Mode
    if risk_status.get("drawdown_status") == "CAPITAL_PRESERVATION_MODE":
        msg = f"🛑 NO-TRADE DECISION: Portfolio drawdown (-{risk_status.get('drawdown_pct')}%) reached max limit. Capital Preservation Mode active."
        logs.append(msg)
        return {"trades_to_execute": [], "logs": logs}

    # Sort candidates by volume breakout ratio descending
    sorted_candidates = sorted(candidates, key=lambda x: x.get("volume_ratio", 0.0), reverse=True)

    for c in sorted_candidates:
        ticker = c["ticker"]
        sector = c.get("sector") or screener.get_stock_sector(ticker)

        # 1. De-Duplication Check
        dedup_ok, dedup_msg = corr_sentinel.check_deduplication(ticker, open_positions, trades_to_execute)
        if not dedup_ok:
            logs.append(f"Skipping {ticker}: {dedup_msg}")
            no_trade_reasons.append(f"{ticker}: {dedup_msg}")
            continue

        # 2. Daily purchase limit (Max 3 trades)
        if buy_count >= 3:
            logs.append(f"Skipping {ticker}: Daily purchase limit of 3 trades reached.")
            break

        # 3. Dynamic Position Sizing
        size_res = sizer.calculate_position_size(
            candidate=c,
            portfolio_value=portfolio_value,
            market_regime=regime_data,
            portfolio_risk_status=risk_status
        )

        qty = size_res.get("quantity", 0)
        cost = size_res.get("total_cost", 0.0)
        proposed_risk = size_res.get("actual_risk_dollars", 0.0)

        if qty <= 0:
            logs.append(f"Skipping {ticker}: Dynamic sizer returned quantity 0.")
            continue

        # 4. Central Portfolio Risk Engine Validation
        approved, rej_reason = risk_engine.validate_trade_permission(
            candidate_ticker=ticker,
            candidate_sector=sector,
            proposed_cost=cost,
            proposed_risk=proposed_risk,
            portfolio_risk_status=risk_status,
            market_regime=regime_data
        )

        if not approved:
            logs.append(f"Skipping {ticker}: {rej_reason}")
            no_trade_reasons.append(f"{ticker}: {rej_reason}")
            continue

        # 5. Correlation Matrix Blocker (bar_rho <= 0.75)
        corr_ok, avg_rho, corr_msg = corr_sentinel.validate_correlation(ticker, open_positions)
        if not corr_ok:
            logs.append(f"Skipping {ticker}: {corr_msg}")
            no_trade_reasons.append(f"{ticker}: {corr_msg}")
            continue

        trade_obj = {
            "ticker": ticker,
            "entry_price": size_res["entry_price"],
            "quantity": qty,
            "initial_sl": size_res["initial_sl"],
            "target": size_res["target_price"],
            "cost": cost,
            "risk_dollars": proposed_risk,
            "sector": sector,
            "atr_14": c.get("atr_14", 0.0),
            "correlation_rho": avg_rho,
            "multipliers": size_res["multipliers"]
        }
        trades_to_execute.append(trade_obj)
        buy_count += 1

        sl_pct = ((size_res["entry_price"] - size_res["initial_sl"]) / size_res["entry_price"]) * 100.0
        logs.append(
            f"✅ Approved Trade: Buy {qty} shares of {ticker} ({sector}) @ ₹{size_res['entry_price']:.2f} "
            f"(SL: ₹{size_res['initial_sl']:.2f} [-{sl_pct:.2f}%], Target: ₹{size_res['target_price']:.2f}, Cost: ₹{cost:,.2f}, Risk: ₹{proposed_risk:,.2f})"
        )

    if not trades_to_execute and candidates:
        logs.append("🛑 NO-TRADE DECISION: Candidates found, but all entries rejected by Central Portfolio Risk & Correlation Gates.")

    return {
        "trades_to_execute": trades_to_execute,
        "logs": logs
    }

def execute_trades_node(state: TradingState) -> Dict[str, Any]:
    """
    Node 4: Appends buy orders to the Google Sheet holdings if execute_trades is True.
    """
    logs = state.get("logs", [])
    logs.append("--- Node: Executing Trades ---")
    
    if not state.get("execute_trades", True):
        logs.append("Auto-execution skipped (Manual Scan Preview Mode). Trades prepared for user confirmation.")
        return {"logs": logs}
        
    trades = state.get("trades_to_execute", [])
    if not trades:
        logs.append("No new trades to execute.")
        return {"logs": logs}
        
    try:
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        
        for t in trades:
            res = portfolio_manager.add_position(
                sh,
                ticker=t["ticker"],
                entry_price=t["entry_price"],
                qty=t["quantity"],
                initial_sl=t["initial_sl"],
                target=t["target"]
            )
            logs.append(res)
            
    except Exception as e:
        logs.append(f"Error in execute_trades_node: {e}")
        
    return {"logs": logs}

# Define the LangGraph workflow
def build_trading_workflow():
    workflow = StateGraph(TradingState)
    
    # Add nodes
    workflow.add_node("sync_portfolio", sync_portfolio_node)
    workflow.add_node("scan_market", scan_market_node)
    workflow.add_node("calculate_positions", calculate_positions_node)
    workflow.add_node("execute_trades", execute_trades_node)
    
    # Set entry point
    workflow.set_entry_point("sync_portfolio")
    
    # Set transitions
    workflow.add_edge("sync_portfolio", "scan_market")
    workflow.add_edge("scan_market", "calculate_positions")
    workflow.add_edge("calculate_positions", "execute_trades")
    workflow.add_edge("execute_trades", END)
    
    # Compile
    return workflow.compile()

def run_trading_system(execute_trades: bool = True) -> Dict[str, Any]:
    """
    Helper function to execute the compiled LangGraph workflow.
    """
    app = build_trading_workflow()
    initial_state = {
        "candidates": [],
        "open_positions": [],
        "portfolio_value": 0.0,
        "cash_balance": 0.0,
        "risk_per_trade": 0.0,
        "trades_to_execute": [],
        "execute_trades": execute_trades,
        "logs": ["V2 System Execution Started."]
    }
    result = app.invoke(initial_state)
    return result

def format_scan_report(state: Dict[str, Any], is_scheduled: bool = False, is_amo: bool = False) -> str:
    """
    Formats the final state dictionary into a rich, structured report for Telegram.
    Includes V2 Market Regime, Portfolio Risk Budget, Correlation status, and NO-TRADE Telemetry.
    """
    from datetime import datetime
    import pytz
    tz = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(tz)
    date_str = now_ist.strftime("%Y-%m-%d")
    time_str = now_ist.strftime("%I:%M:%S %p IST")
    
    source_badge = "🟢 DhanHQ (Live Broker Feed)" if dhan_client.is_dhan_configured() else "⚪ Yahoo Finance (EOD Fallback)"

    regime = state.get("market_regime", {})
    risk_status = state.get("portfolio_risk_status", {})
    
    report = []
    if is_scheduled:
        report.append("⏰ **Scheduled Daily Scan Report (Auto-Execution) — Strategy #2 V2**")
    else:
        report.append("🔍 **Manual Market Scan Report — Strategy #2 V2**")
            
    report.append(f"📅 *Date: {date_str} | Time: {time_str}*")
    report.append(f"📡 *Data Engine: {source_badge}*")
    report.append("")

    # V2 Market Regime Section
    if regime:
        report.append(f"🚦 **V2 Market Regime Score:** {regime.get('color', '🟡')} **{regime.get('classification', 'NEUTRAL')}** (`{regime.get('regime_score', 0)}/100`)")
        report.append(f"• Sizing Multiplier: `{regime.get('max_sizing_multiplier', 1.0)*100:.0f}%` | Cash Floor: `{regime.get('min_cash_reserve_pct', 0.1)*100:.0f}%`")
        comps = regime.get("components", {})
        report.append(f"• Factors: Trend `{comps.get('trend_score', 0)}` \| Volatility `{comps.get('volatility_score', 0)}` \| Macro `{comps.get('macro_score', 0)}`")
        report.append("")

    # V2 Portfolio Risk & Capital Allocation Section
    if risk_status:
        report.append(f"🛡️ **Central Portfolio Risk Budgeting:**")
        report.append(f"• Portfolio Value: ₹{risk_status.get('portfolio_value', 0.0):,.2f}")
        report.append(f"• Cash Reserves: ₹{risk_status.get('cash_balance', 0.0):,.2f} (`{risk_status.get('actual_cash_pct', 0)}%`)")
        report.append(f"• Total Risk at Stake: ₹{risk_status.get('total_risk_value', 0.0):,.2f} (`{risk_status.get('current_risk_pct', 0)}%` / `6.0%` Cap)")
        report.append(f"• Drawdown State: `-{risk_status.get('drawdown_pct', 0.0)}%` (Sizing Multiplier: `{risk_status.get('drawdown_multiplier', 1.0)}x`)")
        report.append("")
        
    candidates = state.get("candidates", [])
    report.append(f"🔍 **Breakout Candidates Found ({len(candidates)}):**")
    if candidates:
        for idx, c in enumerate(candidates, 1):
            comp_name = screener.get_company_name(c['ticker'])
            sym = c['ticker'].replace(".NS", "")
            sector = c.get('sector') or screener.get_stock_sector(c['ticker'])
            report.append(f"{idx}. 🏢 **{comp_name}** (`{sym}`) — *{sector}*")
            report.append(
                f"   💵 Price: ₹{c['close']:.2f} | 📊 Vol Ratio: {c['volume_ratio']:.2f}x | "
                f"⚡ RSI(14): {c.get('rsi_14', 0.0):.1f} | 📏 ATR(14): ₹{c.get('atr_14', 0.0):.2f}"
            )
    else:
        report.append("• No new breakout candidates found.")
    report.append("")
    
    trades = state.get("trades_to_execute", [])
    if trades:
        report.append(f"🚀 **V2 Approved Trades ({len(trades)}):**")
        for idx, t in enumerate(trades, 1):
            comp_name = screener.get_company_name(t['ticker'])
            sym = t['ticker'].replace(".NS", "")
            sector = t.get('sector') or screener.get_stock_sector(t['ticker'])
            report.append(f"{idx}. 🏢 **{comp_name}** (`{sym}`) — *{sector}*")
            report.append(
                f"   📦 Qty: {t['quantity']} | 🏷️ Entry: ₹{t['entry_price']:.2f} | "
                f"🛡️ SL (2×ATR): ₹{t['initial_sl']:.2f} | 🎯 Target: ₹{t['target']:.2f} | 💳 Cost: ₹{t['cost']:,.2f}"
            )
    else:
        report.append("🛑 **NO-TRADE Decision Gate Active:** No trades executed. Capital preserved.")

    return "\n".join(report)

if __name__ == "__main__":
    print("Running V2 trading system manually...")
    state = run_trading_system(execute_trades=False)
    print("\n--- RAW LOGS ---")
    for l in state.get("logs", []):
        print(l)
    print("\n--- FORMATTED V2 REPORT ---")
    print(format_scan_report(state))

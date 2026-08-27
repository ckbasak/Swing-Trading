import os
import math
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END

# Import backend modules
import screener
import portfolio_manager

class TradingState(TypedDict):
    candidates: List[Dict[str, Any]]
    open_positions: List[Dict[str, Any]]
    portfolio_value: float
    cash_balance: float
    risk_per_trade: float
    trades_to_execute: List[Dict[str, Any]]
    logs: List[str]

def sync_portfolio_node(state: TradingState) -> Dict[str, Any]:
    """
    Node 1: Syncs current portfolio, processes exits, and retrieves latest account details.
    """
    logs = state.get("logs", [])
    logs.append("--- Node: Syncing Portfolio ---")
    
    try:
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        
        # Sync open positions
        sync_logs = portfolio_manager.sync_portfolio(sh)
        logs.extend(sync_logs)
        
        # Get updated account details
        account = portfolio_manager.get_account_details(sh)
        portfolio_value = account["Total Portfolio Value"]
        cash_balance = account["Cash Balance"]
        risk_pct = account["Risk Percent"]
        
        open_positions = portfolio_manager.get_open_positions(sh)
        
        logs.append(f"Portfolio Value: INR {portfolio_value:,.2f}")
        logs.append(f"Cash Balance: INR {cash_balance:,.2f}")
        logs.append(f"Risk per trade: {risk_pct * 100}% (INR {portfolio_value * risk_pct:,.2f})")
        
        return {
            "open_positions": open_positions,
            "portfolio_value": portfolio_value,
            "cash_balance": cash_balance,
            "risk_per_trade": portfolio_value * risk_pct,
            "logs": logs
        }
    except Exception as e:
        logs.append(f"Error in sync_portfolio_node: {e}")
        return {"logs": logs}

def scan_market_node(state: TradingState) -> Dict[str, Any]:
    """
    Node 2: Runs the Nifty 250 screener to find new breakout candidates.
    """
    logs = state.get("logs", [])
    logs.append("--- Node: Scanning Market ---")
    
    try:
        tickers = screener.get_nifty_250_tickers()
        logs.append(f"Scanning Nifty {len(tickers)} universe for breakouts...")
        candidates = screener.screen_stocks(tickers)
        
        logs.append(f"Found {len(candidates)} breakout candidates.")
        for idx, c in enumerate(candidates):
            logs.append(f"Candidate {idx+1}: {c['ticker']} | Close: {c['close']:.2f} | Volume Ratio: {c['volume_ratio']:.2f}x | RSI(14): {c.get('rsi_14', 0.0):.1f}")
            
        return {
            "candidates": candidates,
            "logs": logs
        }
    except Exception as e:
        logs.append(f"Error in scan_market_node: {e}")
        return {"logs": logs}

def calculate_positions_node(state: TradingState) -> Dict[str, Any]:
    """
    Node 3: Enforces 1% risk position sizing and filters against existing holdings.
    """
    logs = state.get("logs", [])
    logs.append("--- Node: Calculating Position Sizing ---")
    
    candidates = state.get("candidates", [])
    open_positions = state.get("open_positions", [])
    cash = state.get("cash_balance", 0.0)
    risk_per_trade = state.get("risk_per_trade", 0.0)
    
    existing_tickers = {p["Ticker"] for p in open_positions}
    trades_to_execute = []
    
    remaining_cash = cash
    
    for c in candidates:
        ticker = c["ticker"]
        
        # Skip if already in holdings
        if ticker in existing_tickers:
            logs.append(f"Skipping {ticker}: Already in holdings.")
            continue
            
        entry_price = c["close"]
        initial_sl = c["sma_20"]
        
        # Calculate Risk Per Share
        risk_per_share = entry_price - initial_sl
        
        # Safe-guard: Minimum 2% risk buffer if 20 SMA is too close to Close price
        min_risk = entry_price * 0.02
        if risk_per_share <= min_risk:
            initial_sl = entry_price * 0.98
            risk_per_share = entry_price - initial_sl
            logs.append(f"SL adjusted to 2% limit for {ticker} (Initial SL was too tight: {c['sma_20']:.2f})")
            
        # 1% Risk Sizing Rule: Quantity = Risk Per Trade / Risk Per Share
        qty = math.floor(risk_per_trade / risk_per_share)
        
        if qty <= 0:
            logs.append(f"Skipping {ticker}: Calculated quantity is 0.")
            continue
            
        total_cost = qty * entry_price
        
        # Cash check
        if total_cost > remaining_cash:
            # Scale down quantity to fit remaining cash
            qty = math.floor(remaining_cash / entry_price)
            total_cost = qty * entry_price
            if qty <= 0:
                logs.append(f"Skipping {ticker}: Insufficient cash to buy even 1 share. Need: {entry_price:.2f}, Available: {remaining_cash:.2f}")
                continue
            logs.append(f"Scaled down quantity for {ticker} to {qty} due to cash limit.")
            
        target = entry_price + (2 * risk_per_share) # 1:2 Risk to Reward
        
        trades_to_execute.append({
            "ticker": ticker,
            "entry_price": entry_price,
            "quantity": qty,
            "initial_sl": initial_sl,
            "target": target,
            "cost": total_cost
        })
        
        remaining_cash -= total_cost
        logs.append(f"Prepared trade: Buy {qty} shares of {ticker} @ {entry_price:.2f} (SL: {initial_sl:.2f}, Target: {target:.2f}, Cost: {total_cost:.2f})")
        
    return {
        "trades_to_execute": trades_to_execute,
        "logs": logs
    }

def execute_trades_node(state: TradingState) -> Dict[str, Any]:
    """
    Node 4: Appends buy orders to the Google Sheet holdings.
    """
    logs = state.get("logs", [])
    logs.append("--- Node: Executing Trades ---")
    
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

def run_trading_system() -> Dict[str, Any]:
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
        "logs": ["System Execution Started."]
    }
    result = app.invoke(initial_state)
    return result

def format_scan_report(state: Dict[str, Any]) -> str:
    """
    Formats the final state dictionary into a clean, human-readable report for Telegram.
    """
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    # Extract portfolio sync updates (exits and SL updates)
    sync_logs = []
    for log in state.get("logs", []):
        if "Closed trade" in log or "Updated Trailing Stop" in log:
            sync_logs.append(log)
            
    report = []
    report.append(f"📊 **NSE Swing Trading Scan Report**")
    report.append(f"📅 *Date: {date_str}*")
    report.append("")
    report.append(f"💰 **Portfolio Summary:**")
    report.append(f"• Total Value: ₹{state.get('portfolio_value', 0.0):,.2f}")
    report.append(f"• Cash Balance: ₹{state.get('cash_balance', 0.0):,.2f}")
    report.append("")
    
    if sync_logs:
        report.append(f"🔄 **Portfolio Updates & Exits:**")
        for slog in sync_logs:
            report.append(f"• {slog}")
        report.append("")
        
    candidates = state.get("candidates", [])
    report.append(f"🔍 **Breakout Candidates Found ({len(candidates)}):**")
    if candidates:
        for idx, c in enumerate(candidates):
            report.append(
                f"{idx+1}. **{c['ticker']}** | Price: ₹{c['close']:.2f} | "
                f"Vol Ratio: {c['volume_ratio']:.2f}x | RSI: {c.get('rsi_14', 0.0):.1f}"
            )
    else:
        report.append("• No new breakout candidates found.")
    report.append("")
    
    trades = state.get("trades_to_execute", [])
    report.append(f"🚀 **Trades Executed:**")
    if trades:
        for t in trades:
            report.append(
                f"✅ Bought **{t['ticker']}** ({t['quantity']} shrs) @ ₹{t['entry_price']:.2f}\n"
                f"   *(SL: ₹{t['initial_sl']:.2f} | Target: ₹{t['target']:.2f} | Cost: ₹{t['cost']:.2f})*"
            )
    else:
        report.append("• No new trades executed.")
    report.append("")
    
    # Gather skips
    skips = []
    for log in state.get("logs", []):
        if "Skipping" in log or "Scaled down" in log:
            skips.append(log.replace("Skipping ", "").replace("Scaled down ", ""))
            
    if skips:
        report.append(f"⚠️ **Sizing & Capital Skips:**")
        for sk in skips:
            report.append(f"• {sk}")
            
    return "\n".join(report)

if __name__ == "__main__":
    print("Running system manually...")
    state = run_trading_system()
    print("--- RAW LOGS ---")
    for l in state.get("logs", []):
        print(l)
    print("\n--- FORMATTED REPORT ---")
    print(format_scan_report(state))

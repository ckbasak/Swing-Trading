import os
import math
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END

# Import backend modules
import screener
import portfolio_manager
import dhan_client

class TradingState(TypedDict, total=False):
    candidates: List[Dict[str, Any]]
    open_positions: List[Dict[str, Any]]
    portfolio_value: float
    cash_balance: float
    risk_per_trade: float
    trades_to_execute: List[Dict[str, Any]]
    execute_trades: bool
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
        risk_pct = account.get("Risk Percent", 0.015)
        # Migrate 1.0% to 1.5% for Strategy v2 if needed
        if risk_pct == 0.01:
            portfolio_manager.update_account_details(sh, {"Risk Percent": 0.015})
            risk_pct = 0.015
        
        open_positions = portfolio_manager.get_open_positions(sh)
        
        logs.append(f"Portfolio Value: INR {portfolio_value:,.2f}")
        logs.append(f"Cash Balance: INR {cash_balance:,.2f}")
        logs.append(f"Risk per trade: {risk_pct * 100:.1f}% (INR {portfolio_value * risk_pct:,.2f})")
        
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
    Node 2: Runs the Nifty 50 screener to find new Strategy v2 breakout candidates.
    """
    logs = state.get("logs", [])
    logs.append("--- Node: Scanning Market ---")
    
    try:
        tickers = screener.get_nifty_250_tickers()
        logs.append(f"Scanning Nifty {len(tickers)} universe for breakouts...")
        candidates = screener.screen_stocks(tickers, logs=logs)
        
        logs.append(f"Found {len(candidates)} breakout candidates.")
        for idx, c in enumerate(candidates):
            logs.append(
                f"Candidate {idx+1}: {c['ticker']} ({c.get('sector', 'Unknown')}) | "
                f"Close: {c['close']:.2f} | Volume Ratio: {c['volume_ratio']:.2f}x | "
                f"RSI(14): {c.get('rsi_14', 0.0):.1f} | ATR(14): {c.get('atr_14', 0.0):.2f}"
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
    Node 3: Enforces Strategy v2 sizing & risk rules:
    - 1.5% portfolio risk per trade
    - Stop Loss sized to 2× ATR(14) below entry (no fixed clamp)
    - Sector Concentration Limit: Max 3 open positions per sector
    - 90% max portfolio exposure guardrail (10% cash buffer)
    - Daily purchase limit of 3 breakouts (strongest volume ratio first)
    """
    logs = state.get("logs", [])
    logs.append("--- Node: Calculating Position Sizing ---")
    
    candidates = state.get("candidates", [])
    open_positions = state.get("open_positions", [])
    cash = state.get("cash_balance", 0.0)
    risk_per_trade = state.get("risk_per_trade", 0.0)
    portfolio_value = state.get("portfolio_value", 0.0)
    
    # Calculate current open holdings value
    open_value = 0.0
    for p in open_positions:
        try:
            qty = int(p.get("Quantity", 0))
            entry = float(p.get("Entry Price", 0.0))
            open_value += qty * entry
        except Exception:
            pass
            
    max_open_value = portfolio_value * 0.90
    
    existing_tickers = {p["Ticker"] for p in open_positions}
    
    # Track existing open positions per sector (v2: Max 3 per sector)
    sector_counts: Dict[str, int] = {}
    for p in open_positions:
        sec = screener.get_stock_sector(p.get("Ticker", ""))
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        
    trades_to_execute = []
    remaining_cash = cash
    buy_count = 0
    
    # Sort candidates by volume ratio descending (strongest breakout first)
    sorted_candidates = sorted(candidates, key=lambda x: x.get("volume_ratio", 0.0), reverse=True)
    
    for c in sorted_candidates:
        ticker = c["ticker"]
        candidate_sector = c.get("sector") or screener.get_stock_sector(ticker)
        
        # Skip if already in holdings (Double Buy Blocker)
        if ticker in existing_tickers:
            logs.append(f"Skipping {ticker}: Already in holdings.")
            continue
            
        # Daily purchase limit guardrail (Max 3 buys per day)
        if buy_count >= 3:
            logs.append(f"Skipping {ticker}: Daily purchase limit of 3 trades reached.")
            continue
            
        # Sector concentration guardrail (v2: Max 3 open positions per sector)
        current_sector_positions = sector_counts.get(candidate_sector, 0)
        if current_sector_positions >= 3:
            logs.append(f"Skipping {ticker}: Sector concentration limit reached (Already 3 open in {candidate_sector}).")
            continue
            
        entry_price = c["close"]
        
        # Strategy v2 Stop-loss: 2x ATR(14) below entry, no fixed clamp
        atr_14 = c.get("atr_14")
        if atr_14 is not None and atr_14 > 0:
            risk_per_share = 2.0 * atr_14
            initial_sl = entry_price - risk_per_share
        else:
            risk_per_share = max(entry_price - c.get("sma_20", entry_price * 0.95), entry_price * 0.03)
            initial_sl = entry_price - risk_per_share
            
        if risk_per_share <= 0:
            logs.append(f"Skipping {ticker}: Risk per share is <= 0.")
            continue
            
        # Sizing Rule (1.5% Risk per trade): Quantity = Risk Per Trade / Risk Per Share
        qty = math.floor(risk_per_trade / risk_per_share)
        
        if qty <= 0:
            logs.append(f"Skipping {ticker}: Calculated quantity is 0.")
            continue
            
        total_cost = qty * entry_price
        
        # Exposure Guardrail: Ensure total open value does not exceed 90% of portfolio
        if open_value + total_cost > max_open_value:
            allowed_cost = max_open_value - open_value
            if allowed_cost <= 0:
                logs.append(f"Skipping {ticker}: Max 90% portfolio exposure allocation reached.")
                continue
            scaled_qty = math.floor(allowed_cost / entry_price)
            if scaled_qty < qty:
                qty = scaled_qty
                total_cost = qty * entry_price
                if qty <= 0:
                    logs.append(f"Skipping {ticker}: Max 90% portfolio exposure allocation reached.")
                    continue
                logs.append(f"Scaled down quantity for {ticker} to {qty} to respect 90% portfolio exposure limit.")
        
        # Cash limit check
        if total_cost > remaining_cash:
            qty = math.floor(remaining_cash / entry_price)
            total_cost = qty * entry_price
            if qty <= 0:
                logs.append(f"Skipping {ticker}: Insufficient cash to buy even 1 share. Need: {entry_price:.2f}, Available: {remaining_cash:.2f}")
                continue
            logs.append(f"Scaled down quantity for {ticker} to {qty} due to cash limit.")
            
        # Profit target: fixed 1:2 risk-to-reward ratio
        target = entry_price + (2.0 * risk_per_share)
        
        trades_to_execute.append({
            "ticker": ticker,
            "entry_price": entry_price,
            "quantity": qty,
            "initial_sl": round(initial_sl, 2),
            "target": round(target, 2),
            "cost": round(total_cost, 2),
            "sector": candidate_sector,
            "atr_14": round(atr_14, 2) if atr_14 else 0.0
        })
        
        # Update trackers
        remaining_cash -= total_cost
        open_value += total_cost
        buy_count += 1
        sector_counts[candidate_sector] = sector_counts.get(candidate_sector, 0) + 1
        
        sl_pct = ((entry_price - initial_sl) / entry_price) * 100.0
        logs.append(
            f"Prepared trade: Buy {qty} shares of {ticker} ({candidate_sector}) @ {entry_price:.2f} "
            f"(SL: {initial_sl:.2f} [-{sl_pct:.2f}%], Target: {target:.2f}, Cost: ₹{total_cost:,.2f})"
        )
        
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
    Set execute_trades=False for manual scans to only preview candidates without adding to portfolio.
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
        "logs": ["System Execution Started."]
    }
    result = app.invoke(initial_state)
    return result

def format_scan_report(state: Dict[str, Any], is_scheduled: bool = False, is_amo: bool = False) -> str:
    """
    Formats the final state dictionary into a clean, human-readable report for Telegram.
    Differentiates between Scheduled Daily Scans and Manual Scans (Live Market vs AMO).
    """
    from datetime import datetime
    import pytz
    tz = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(tz)
    date_str = now_ist.strftime("%Y-%m-%d")
    time_str = now_ist.strftime("%I:%M:%S %p IST")
    
    # Active Market Data Source Badge
    if dhan_client.is_dhan_configured():
        source_badge = "🟢 DhanHQ (Live Broker Feed)"
    else:
        source_badge = "⚪ Yahoo Finance (EOD Fallback)"
    
    # Extract AI Sentiment logs
    sentiment_logs = []
    for log in state.get("logs", []):
        if any(k in log for k in ["Macro Risk Alert", "Macro Market Sentiment", "NEGATIVE NEWS", "Discarded"]):
            sentiment_logs.append(log)
            
    # Extract portfolio sync updates (exits, SL updates, and live quote notices)
    sync_logs = []
    for log in state.get("logs", []):
        if any(k in log for k in ["Closed trade", "Updated Trailing Stop", "Real-time quotes"]):
            sync_logs.append(log)
            
    report = []
    if is_scheduled:
        report.append("⏰ **Scheduled Daily Scan Report (Auto-Execution) — Strategy #2**")
    else:
        if is_amo:
            report.append("🌙 **Manual Market Scan Report (After-Market / AMO Mode) — Strategy #2**")
        else:
            report.append("🔍 **Manual Market Scan Report (Live Market Hours Preview) — Strategy #2**")
            
    report.append(f"📅 *Date: {date_str} | Time: {time_str}*")
    report.append(f"📡 *Data Engine: {source_badge}*")
    report.append("")
    report.append(f"💰 **Portfolio Summary:**")
    report.append(f"• Total Value: ₹{state.get('portfolio_value', 0.0):,.2f}")
    report.append(f"• Cash Balance: ₹{state.get('cash_balance', 0.0):,.2f}")
    report.append("")
    
    if sentiment_logs:
        report.append(f"🧠 **AI News Sentiment Overlay (Gemini):**")
        for sent_log in sentiment_logs:
            report.append(f"• {sent_log}")
        report.append("")
        
    if sync_logs:
        report.append(f"🔄 **Portfolio Updates & Quotes:**")
        for slog in sync_logs:
            report.append(f"• {slog}")
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
    if is_scheduled:
        report.append(f"🚀 **Trades Executed ({len(trades)}):**")
        if trades:
            for idx, t in enumerate(trades, 1):
                comp_name = screener.get_company_name(t['ticker'])
                sym = t['ticker'].replace(".NS", "")
                sector = t.get('sector') or screener.get_stock_sector(t['ticker'])
                report.append(f"{idx}. 🏢 **{comp_name}** (`{sym}`) — *{sector}*")
                report.append(
                    f"   📦 Qty: {t['quantity']} | 🏷️ Entry: ₹{t['entry_price']:.2f} | "
                    f"🛡️ SL (2×ATR): ₹{t['initial_sl']:.2f} | 🎯 Target (1:2): ₹{t['target']:.2f}"
                )
        else:
            report.append("• No new trades executed.")
    else:
        trade_label = "Proposed AMO Trades (Awaiting Confirmation)" if is_amo else "Proposed Market Trades (Awaiting Confirmation)"
        report.append(f"🎯 **{trade_label} ({len(trades)}):**")
        if trades:
            for idx, t in enumerate(trades, 1):
                comp_name = screener.get_company_name(t['ticker'])
                sym = t['ticker'].replace(".NS", "")
                sector = t.get('sector') or screener.get_stock_sector(t['ticker'])
                report.append(f"{idx}. 🏢 **{comp_name}** (`{sym}`) — *{sector}*")
                report.append(
                    f"   📦 Qty: {t['quantity']} | 🏷️ Entry: ₹{t['entry_price']:.2f} | "
                    f"🛡️ SL (2×ATR): ₹{t['initial_sl']:.2f} | 🎯 Target (1:2): ₹{t['target']:.2f} | 💳 Cost: ₹{t.get('cost', t['entry_price'] * t['quantity']):,.2f}"
                )
            action_name = "AMO Order" if is_amo else "Live Market Order"
            report.append(f"\n👉 *No entries have been executed. Tap below to confirm {action_name}.*")
        else:
            report.append("• No trades proposed.")
    report.append("")
    
    # Gather skips and execution notices
    skips = []
    for log in state.get("logs", []):
        if any(k in log for k in ["Skipping", "Scaled down", "Blocked", "Successfully added", "SL adjusted"]):
            clean_log = log.replace("Skipping ", "").replace("Scaled down ", "")
            if clean_log not in skips:
                skips.append(clean_log)
            
    if skips:
        report.append(f"⚠️ **Execution & Sizing Notices:**")
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

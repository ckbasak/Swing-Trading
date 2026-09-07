import os
import math
from typing import TypedDict, List, Dict, Any
import screener
import portfolio_manager
import sentiment_analyzer

class TradingState(TypedDict, total=False):
    candidates: List[Dict[str, Any]]
    open_positions: List[Dict[str, Any]]
    portfolio_value: float
    cash_balance: float
    risk_per_trade: float
    trades_to_execute: List[Dict[str, Any]]
    execute_trades: bool
    macro_sentiment: Dict[str, Any]
    logs: List[str]

def run_trading_system(execute_trades: bool = False, pool_type: str = "top_50") -> Dict[str, Any]:
    logs = []
    logs.append("=== [Strategy 3] Starting Hybrid Optimal Swing Trading Pipeline ===")
    
    # Node 1: Sync Portfolio & Exits
    exit_results = portfolio_manager.update_portfolio_and_exits()
    exited = exit_results.get("exited", [])
    partial_exited = exit_results.get("partial_exited", [])
    
    if partial_exited:
        for p in partial_exited:
            logs.append(f"TARGET 1 HIT: {p['ticker']} sold {p['qty']} shares @ Rs {p['exit_price']:.2f}. Stop moved to Break-Even!")
    if exited:
        for e in exited:
            logs.append(f"POSITION CLOSED: {e['ticker']} sold {e['qty']} shares @ Rs {e['exit_price']:.2f} ({e['reason']})")
            
    acc = portfolio_manager.get_account_summary()
    port_val = acc.get("portfolio_value", 100000.0)
    cash = acc.get("cash", 100000.0)
    risk_pct = acc.get("risk_pct", 6.0)
    open_positions = portfolio_manager.get_holdings()
    
    logs.append(f"Portfolio Value: Rs {port_val:,.2f} | Cash: Rs {cash:,.2f} | Open Positions: {len(open_positions)}/10")
    
    # Node 2: Screen Curated Stock Universe
    tickers = screener.get_curated_tickers(pool_type)
    logs.append(f"Scanning {len(tickers)} stocks from Curated {pool_type.upper()} Pool...")
    candidates = screener.screen_stocks(tickers, check_sentiment=True)
    logs.append(f"Screener returned {len(candidates)} breakout candidate(s).")
    
    # Node 3: Risk Allocation & Sizing
    trades_to_execute = []
    current_sectors = [screener.get_stock_sector(h.get("Ticker", "")) for h in open_positions]
    max_sector = int(os.environ.get("MAX_POSITIONS_PER_SECTOR", "3"))
    max_total = int(os.environ.get("MAX_TOTAL_POSITIONS", "10"))
    
    remaining_cash = cash
    available_slots = max_total - len(open_positions)
    
    for cand in candidates:
        if available_slots <= 0 or remaining_cash < 2000.0:
            break
            
        t = cand["ticker"]
        sec = cand["sector"]
        p = cand["close"]
        atr = cand["atr"]
        
        # Sector check
        sec_count = current_sectors.count(sec)
        if sec_count >= max_sector:
            logs.append(f"Skipping {t}: Sector '{sec}' already has {sec_count}/{max_sector} positions.")
            continue
            
        qty = portfolio_manager.calculate_position_size(p, atr, port_val, remaining_cash)
        if qty >= 2 and (qty * p) <= remaining_cash:
            trade_cost = qty * p
            trades_to_execute.append({
                "ticker": t,
                "company": cand["company"],
                "sector": sec,
                "price": p,
                "qty": qty,
                "cost": trade_cost,
                "atr": atr,
                "sl": cand["stop_loss"],
                "target_1": cand["target_1"],
                "target_2": cand["target_2"]
            })
            current_sectors.append(sec)
            remaining_cash -= trade_cost
            available_slots -= 1
            
    # Node 4: Execute if enabled
    executed = []
    if execute_trades and trades_to_execute:
        logs.append(f"Executing {len(trades_to_execute)} new Strategy 3 trade(s)...")
        for trade in trades_to_execute:
            res = portfolio_manager.add_position(
                trade["ticker"], trade["company"], trade["sector"], trade["price"], trade["atr"]
            )
            if res:
                executed.append(res)
                logs.append(f"ORDER FILLED: {trade['ticker']} x {trade['qty']} @ Rs {trade['price']}")
                
    return {
        "portfolio_value": port_val,
        "cash_balance": cash,
        "open_positions": open_positions,
        "candidates": candidates,
        "trades_to_execute": trades_to_execute,
        "executed_trades": executed,
        "partial_exits": partial_exited,
        "full_exits": exited,
        "logs": logs
    }

def format_scan_report(state: Dict[str, Any]) -> str:
    lines = []
    lines.append("STRATEGY 3: HYBRID OPTIMAL SWING SCAN REPORT")
    lines.append("==================================================")
    lines.append(f"Portfolio Value: Rs {state.get('portfolio_value', 0):,.2f}")
    lines.append(f"Available Cash: Rs {state.get('cash_balance', 0):,.2f}")
    lines.append(f"Open Positions: {len(state.get('open_positions', []))}/10")
    lines.append("")
    
    if state.get("partial_exits"):
        lines.append("Milestone 1 Hit (50% Profit Booked):")
        for p in state["partial_exits"]:
            lines.append(f"  * {p['ticker']}: Sold {p['qty']} shares @ Rs {p['exit_price']:.2f} ({p['pnl_pct']:+.1f}%). SL shifted to Break-Even!")
        lines.append("")
        
    if state.get("full_exits"):
        lines.append("Closed Positions:")
        for e in state["full_exits"]:
            lines.append(f"  * {e['ticker']}: Sold {e['qty']} shares @ Rs {e['exit_price']:.2f} ({e['pnl_pct']:+.1f}%) [{e['reason']}]")
        lines.append("")
        
    cands = state.get("candidates", [])
    if not cands:
        lines.append("Screener: No candidates met the 20-SMA breakout, 2.25x volume, and RSI 50-70 filters today.")
    else:
        lines.append(f"Breakout Candidates Found ({len(cands)}):")
        for c in cands[:5]:
            lines.append(f"  * {c['ticker']} ({c['company']})")
            lines.append(f"    Price: Rs {c['close']} | Vol: {c['volume_ratio']}x | RSI: {c['rsi']}")
            lines.append(f"    T1: Rs {c['target_1']} (50%) | T2: Rs {c['target_2']} (Runner) | SL: Rs {c['stop_loss']}")
            
    execs = state.get("trades_to_execute", [])
    if execs:
        lines.append("")
        lines.append(f"Approved Strategy 3 Orders ({len(execs)}):")
        for ex in execs:
            lines.append(f"  * {ex['ticker']} x {ex['qty']} shares @ Rs {ex['price']:.2f} (Total: Rs {ex['cost']:,.2f})")
            
    lines.append("==================================================")
    sep = "\n"
    return sep.join(lines)

if __name__ == "__main__":
    st = run_trading_system(execute_trades=False)
    print(format_scan_report(st))

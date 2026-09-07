import os
import math
from typing import TypedDict, List, Dict, Any
from datetime import datetime
import pytz

import screener
import portfolio_manager
import sentiment_analyzer
import dhan_client

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
    """
    Executes Strategy 3: Hybrid Optimal Swing Trading Pipeline
    1. Evaluates Global & Indian macro sentiment & guardrails.
    2. Syncs active open holdings & checks trailing stop updates.
    3. Scans high-conviction curated stock pool.
    4. Applies sector limit (max 3/sector) & 6.0% capital risk sizing.
    """
    logs = ["=== [Strategy 3] Starting Hybrid Optimal Swing Trading Pipeline ==="]
    
    # Node 1: Macro Sentiment & Portfolio Sync
    macro_data = None
    try:
        macro_data = sentiment_analyzer.get_comprehensive_market_macro_sentiment()
    except Exception as e:
        logs.append(f"Notice: macro sentiment analysis exception: {e}")

    exit_results = portfolio_manager.update_portfolio_and_exits()
    exited = exit_results.get("exited", [])
    partial_exited = exit_results.get("partial_exited", [])
    
    if partial_exited:
        for p in partial_exited:
            logs.append(f"TARGET 1 HIT: {p['ticker']} sold {p['qty']} shares @ ₹{p['exit_price']:.2f}. Stop moved to Break-Even!")
    if exited:
        for e in exited:
            logs.append(f"POSITION CLOSED: {e['ticker']} sold {e['qty']} shares @ ₹{e['exit_price']:.2f} ({e['reason']})")
            
    acc = portfolio_manager.get_account_summary()
    port_val = float(acc.get("portfolio_value", 100000.0))
    cash = float(acc.get("cash", 100000.0))
    risk_pct = float(acc.get("risk_pct", 6.0)) / 100.0
    risk_per_trade = port_val * risk_pct
    open_positions = portfolio_manager.get_open_positions()
    
    logs.append(f"Portfolio Value: ₹{port_val:,.2f} | Cash: ₹{cash:,.2f} | Open Positions: {len(open_positions)}/10")
    
    # Node 2: Screen Curated Universe
    tickers = screener.get_curated_tickers(pool_type)
    logs.append(f"Scanning {len(tickers)} curated stocks ({pool_type.upper()} Pool)...")
    candidates = screener.screen_stocks(tickers, logs=logs, macro_data=macro_data, check_sentiment=True)
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
        
        sec_count = current_sectors.count(sec)
        if sec_count >= max_sector:
            logs.append(f"Skipping {t}: Sector '{sec}' already has {sec_count}/{max_sector} positions.")
            continue
            
        qty = portfolio_manager.calculate_position_size(p, atr, port_val, remaining_cash)
        if qty >= 2 and (qty * p) <= remaining_cash:
            trade_cost = round(qty * p, 2)
            trades_to_execute.append({
                "ticker": t,
                "company": cand["company"],
                "sector": sec,
                "price": p,
                "qty": qty,
                "quantity": qty,
                "cost": trade_cost,
                "atr": atr,
                "sl": cand["stop_loss"],
                "initial_sl": cand["stop_loss"],
                "target_1": cand["target_1"],
                "target_2": cand["target_2"],
                "target": f"T1: {cand['target_1']:.1f} | T2: {cand['target_2']:.1f}"
            })
            current_sectors.append(sec)
            remaining_cash -= trade_cost
            available_slots -= 1
            
    # Node 4: Execute if enabled
    executed = []
    if execute_trades and trades_to_execute:
        logs.append(f"Auto-executing {len(trades_to_execute)} new Strategy 3 trade(s)...")
        for trade in trades_to_execute:
            res = portfolio_manager.add_position(
                ticker=trade["ticker"],
                entry_price=trade["price"],
                quantity=trade["qty"],
                initial_sl=trade["sl"],
                target_1=trade["target_1"],
                target_2=trade["target_2"]
            )
            if res:
                executed.append(res)
                logs.append(f"ORDER FILLED: {trade['ticker']} x {trade['qty']} @ ₹{trade['price']:.2f}")
                
    return {
        "portfolio_value": port_val,
        "cash_balance": cash,
        "open_positions": open_positions,
        "candidates": candidates,
        "trades_to_execute": trades_to_execute,
        "executed_trades": executed,
        "partial_exits": partial_exited,
        "full_exits": exited,
        "macro_sentiment": macro_data,
        "logs": logs
    }

def format_scan_report(state: Dict[str, Any], is_scheduled: bool = False, is_amo: bool = False) -> str:
    """
    Formats the final state dictionary into a rich, human-readable Telegram markdown report
    matching Projects 1 & 2.
    """
    tz = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(tz)
    date_str = now_ist.strftime("%Y-%m-%d")
    time_str = now_ist.strftime("%I:%M:%S %p IST")
    
    if dhan_client.is_dhan_configured():
        source_badge = "🟢 DhanHQ (Live Broker Feed)"
    else:
        source_badge = "⚪ Yahoo Finance (EOD Fallback)"
        
    report = []
    if is_scheduled:
        report.append("⏰ **Scheduled Daily Scan Report (Auto-Execution) — Strategy #3**")
    else:
        if is_amo:
            report.append("🌙 **Manual Market Scan Report (After-Market / AMO Mode) — Strategy #3**")
        else:
            report.append("🔍 **Manual Market Scan Report (Live Market Hours Preview) — Strategy #3**")
            
    report.append(f"📅 *Date: {date_str} | Time: {time_str}*")
    report.append(f"📡 *Data Engine: {source_badge}*")
    report.append("")
    report.append("💰 **Portfolio Summary:**")
    report.append(f"• Total Value: ₹{state.get('portfolio_value', 0.0):,.2f}")
    report.append(f"• Cash Balance: ₹{state.get('cash_balance', 0.0):,.2f}")
    report.append(f"• Open Holdings: {len(state.get('open_positions', []))}/10 positions")
    report.append("")
    
    macro_data = state.get("macro_sentiment")
    if macro_data:
        snippet_lines = sentiment_analyzer.format_macro_sentiment_snippet(macro_data)
        for line in snippet_lines:
            report.append(line)
        report.append("")
    else:
        sentiment_logs = [l for l in state.get("logs", []) if any(k in l for k in ["Macro", "Sentiment", "NEGATIVE"])]
        if sentiment_logs:
            report.append("🌐 **Global & Indian Market Sentiment & Macro Guardrails:**")
            for sl in sentiment_logs:
                report.append(f"• {sl}")
            report.append("")
            
    partial_exits = state.get("partial_exits", [])
    if partial_exits:
        report.append("🎯 **Milestone 1 Hit (50% Partial Profit Booked):**")
        for p in partial_exits:
            report.append(f"• 🏢 **{p['ticker']}**: Sold {p['qty']} shares @ ₹{p['exit_price']:.2f} ({p.get('pnl_pct', 0.0):+.1f}%). Stop Loss moved to Break-Even!")
        report.append("")
        
    full_exits = state.get("full_exits", [])
    if full_exits:
        report.append("🔄 **Closed Positions:**")
        for e in full_exits:
            report.append(f"• 🏢 **{e['ticker']}**: Sold {e['qty']} shares @ ₹{e['exit_price']:.2f} ({e.get('pnl_pct', 0.0):+.1f}%) [{e['reason']}]")
        report.append("")
        
    candidates = state.get("candidates", [])
    report.append(f"🔍 **Breakout Candidates Found ({len(candidates)}):**")
    if candidates:
        for idx, c in enumerate(candidates, 1):
            comp_name = c.get('company') or screener.get_company_name(c['ticker'])
            sym = c['ticker'].replace(".NS", "")
            sector = c.get('sector') or screener.get_stock_sector(c['ticker'])
            report.append(f"{idx}. 🏢 **{comp_name}** (`{sym}`) — *{sector}*")
            report.append(
                f"   💵 Price: ₹{c['close']:.2f} | 📊 Vol Ratio: {c.get('volume_ratio', 0.0):.2f}x | "
                f"⚡ RSI(14): {c.get('rsi', c.get('rsi_14', 0.0)):.1f} | 📏 ATR(14): ₹{c.get('atr', c.get('atr_14', 0.0)):.2f}"
            )
            report.append(
                f"   🎯 T1 (50%): ₹{c['target_1']:.2f} | 🎯 T2 (Runner): ₹{c['target_2']:.2f} | 🛡️ SL (2×ATR): ₹{c['stop_loss']:.2f}"
            )
    else:
        report.append("• No new breakout candidates found.")
    report.append("")
    
    trades = state.get("trades_to_execute", [])
    if is_scheduled:
        report.append(f"🚀 **Trades Executed ({len(trades)}):**")
        if trades:
            for idx, t in enumerate(trades, 1):
                comp_name = t.get('company') or screener.get_company_name(t['ticker'])
                sym = t['ticker'].replace(".NS", "")
                sector = t.get('sector') or screener.get_stock_sector(t['ticker'])
                report.append(f"{idx}. 🏢 **{comp_name}** (`{sym}`) — *{sector}*")
                report.append(
                    f"   📦 Qty: {t['qty']} | 🏷️ Entry: ₹{t['price']:.2f} | "
                    f"🛡️ SL (2×ATR): ₹{t['sl']:.2f} | 🎯 T1: ₹{t['target_1']:.2f} | 🎯 T2: ₹{t['target_2']:.2f}"
                )
        else:
            report.append("• No new trades executed.")
    else:
        trade_label = "Proposed AMO Trades (Awaiting Confirmation)" if is_amo else "Proposed Market Trades (Awaiting Confirmation)"
        report.append(f"🎯 **{trade_label} ({len(trades)}):**")
        if trades:
            for idx, t in enumerate(trades, 1):
                comp_name = t.get('company') or screener.get_company_name(t['ticker'])
                sym = t['ticker'].replace(".NS", "")
                sector = t.get('sector') or screener.get_stock_sector(t['ticker'])
                report.append(f"{idx}. 🏢 **{comp_name}** (`{sym}`) — *{sector}*")
                report.append(
                    f"   📦 Qty: {t['qty']} | 🏷️ Entry: ₹{t['price']:.2f} | "
                    f"🛡️ SL (2×ATR): ₹{t['sl']:.2f} | 🎯 T1: ₹{t['target_1']:.2f} | 🎯 T2: ₹{t['target_2']:.2f} | 💳 Cost: ₹{t.get('cost', t['price'] * t['qty']):,.2f}"
                )
            action_name = "AMO Order" if is_amo else "Live Market Order"
            report.append(f"\n👉 *No entries have been executed. Tap below to confirm {action_name}.*")
        else:
            report.append("• No trades proposed.")
    report.append("")
    
    skips = []
    for log in state.get("logs", []):
        if any(k in log for k in ["Skipping", "Scaled down", "Blocked"]):
            clean_log = log.replace("Skipping ", "").replace("Scaled down ", "")
            if clean_log not in skips:
                skips.append(clean_log)
    if skips:
        report.append("⚠️ **Execution & Sizing Notices:**")
        for sk in skips:
            report.append(f"• {sk}")
            
    return "\n".join(report)

if __name__ == "__main__":
    st = run_trading_system(execute_trades=False)
    print(format_scan_report(st, is_scheduled=False, is_amo=True))

import sys
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os
import asyncio
import schedule
import time
from datetime import datetime
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

import portfolio_manager
import screener
import trading_graph

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN_3") or os.environ.get("TELEGRAM_BOT_TOKEN")

def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🔍 Run Screener", callback_data="cmd_scan"),
            InlineKeyboardButton("📊 Open Holdings", callback_data="cmd_positions")
        ],
        [
            InlineKeyboardButton("📜 Closed Trades", callback_data="cmd_history"),
            InlineKeyboardButton("🏆 Curated Pool", callback_data="cmd_pool")
        ],
        [
            InlineKeyboardButton("💼 Account Summary", callback_data="cmd_summary")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 *AI SWING TRADE SYSTEM 3 (HYBRID OPTIMAL)*\n"
        "══════════════════════════════════════\n"
        "Welcome! This bot executes **Strategy 3: Hybrid Optimal Swing** across your curated stock pools.\n\n"
        "⚡ *Core Strategy 3 Rules*:\n"
        "• *Universe*: Curated High-Performing Indian Equities\n"
        "• *Volume Conviction*: > 2.25x 20-day Vol SMA\n"
        "• *Target 1 (50% Lock)*: +2.0x ATR (~+6-7% gain)\n"
        "• *Break-Even Guard*: Stop moves to Entry Price after T1!\n"
        "• *Target 2 (Runner)*: 20 EMA Trailing up to +4.5x ATR\n"
        "• *Sector Limit*: Max 3 positions per industry\n\n"
        "Use the buttons below or commands to manage your portfolio:"
    )
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_handle = None
    if update.message:
        msg_handle = await update.message.reply_text("⏳ *Scanning curated stocks with Strategy 3 rules...*", parse_mode="Markdown")
        
    state = trading_graph.run_trading_system(execute_trades=False)
    report = trading_graph.format_scan_report(state)
    
    if msg_handle:
        await msg_handle.edit_text(report, reply_markup=get_main_keyboard())
    elif update.callback_query:
        await update.callback_query.message.reply_text(report, reply_markup=get_main_keyboard())

async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    holdings = portfolio_manager.get_holdings()
    if not holdings:
        txt = "📊 *Current Holdings*: No open positions currently."
    else:
        lines = ["📊 *ACTIVE HOLDINGS (Strategy 3)*:", "══════════════════════════════════════"]
        for h in holdings:
            t = h.get("Ticker")
            qty = h.get("Quantity")
            p = h.get("Entry Price")
            sl = h.get("Current SL")
            t1 = h.get("Target 1")
            t2 = h.get("Target 2")
            partial = str(h.get("Partial Booked", "FALSE")).upper() == "TRUE"
            unreal = h.get("Unrealized PnL %", "0.0%")
            status = "🛡️ FREE RUNNER (Stop @ Break-Even)" if partial else "🎯 Aiming for T1 (50% Lock)"
            lines.append(f"• *{t}* x {qty} @ ₹{p} ({unreal})")
            lines.append(f"  SL: ₹{sl} | T1: ₹{t1} | T2: ₹{t2}")
            lines.append(f"  Status: {status}\n")
        txt = "\n".join(lines)
        
    if update.message:
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=get_main_keyboard())
    elif update.callback_query:
        await update.callback_query.message.reply_text(txt, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    closed = portfolio_manager.get_closed_trades()
    if not closed:
        txt = "📜 *Closed Trades History*: No closed trades recorded yet."
    else:
        lines = ["📜 *RECENT CLOSED TRADES & PARTIAL EXITS*:", "══════════════════════════════════════"]
        for c in closed[-10:]:
            lines.append(f"• *{c.get('Ticker')}* x {c.get('Quantity')} shares | PnL: ₹{c.get('Realized PnL', 0):,.2f} ({c.get('Realized PnL %')})")
            lines.append(f"  Exit: ₹{c.get('Exit Price')} [{c.get('Exit Reason')}]\n")
        txt = "\n".join(lines)
        
    if update.message:
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=get_main_keyboard())
    elif update.callback_query:
        await update.callback_query.message.reply_text(txt, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def pool_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool_setting = os.environ.get("ACTIVE_STOCK_POOL", "curated_pool_top_50.csv")
    tickers = screener.get_curated_tickers("top_50" if "50" in pool_setting else "top_101")
    lines = [
        f"🏆 *CURATED STOCK UNIVERSE*",
        "══════════════════════════════════════",
        f"Active Pool: *{'Top 50 Champions' if '50' in pool_setting else 'Top 101 Winners'}*",
        f"Total Constituents: *{len(tickers)} stocks*",
        "Top Constituents Sample: " + ", ".join(tickers[:12]) + "...",
        "\n*Why Curated Pools?*",
        "Outperformed benchmark NIFTY 50 by over +300% in backtests!"
    ]
    txt = "\n".join(lines)
    if update.message:
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=get_main_keyboard())
    elif update.callback_query:
        await update.callback_query.message.reply_text(txt, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    acc = portfolio_manager.get_account_summary()
    holdings = portfolio_manager.get_holdings()
    lines = [
        "💼 *ACCOUNT & PERFORMANCE SUMMARY*",
        "══════════════════════════════════════",
        f"• *Strategy*: Strategy 3 (Hybrid Optimal Swing)",
        f"• *Initial Capital*: ₹{acc.get('initial_capital', 100000):,.2f}",
        f"• *Portfolio Value*: ₹{acc.get('portfolio_value', 100000):,.2f}",
        f"• *Available Cash*: ₹{acc.get('cash', 100000):,.2f}",
        f"• *Realized PnL*: ₹{acc.get('realized_pnl', 0):,.2f}",
        f"• *Total Return*: {acc.get('total_return_pct', 0):+.2f}%",
        f"• *CAGR*: {acc.get('cagr_pct', 0):+.2f}%",
        f"• *XIRR*: {acc.get('xirr_pct', 0):+.2f}%",
        f"• *Days Active*: {acc.get('days_active', 0)} days",
        f"• *Capital Risk / Trade*: {acc.get('risk_pct', 6.0)}%",
        f"• *Open Holdings*: {len(holdings)}/10 positions",
        "══════════════════════════════════════"
    ]
    txt = "\n".join(lines)
    if update.message:
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=get_main_keyboard())
    elif update.callback_query:
        await update.callback_query.message.reply_text(txt, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cmd_scan":
        await scan_command(update, context)
    elif data == "cmd_positions":
        await positions_command(update, context)
    elif data == "cmd_history":
        await history_command(update, context)
    elif data == "cmd_pool":
        await pool_command(update, context)
    elif data == "cmd_summary":
        await summary_command(update, context)

def main():
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN not configured. Bot will run in background engine mode.")
        return
        
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("positions", positions_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("pool", pool_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("AI-Swing-Trade-3 Telegram Bot starting polling...")
    app.run_polling()

if __name__ == "__main__":
    main()

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
import time
import datetime
import pytz
import logging
from logging.handlers import RotatingFileHandler
import pandas as pd
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, NetworkError, Conflict
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

import portfolio_manager
import screener
import trading_graph
import dhan_client
import sentiment_analyzer

# Configure logging
log_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

try:
    file_handler = RotatingFileHandler("bot.log", maxBytes=2*1024*1024, backupCount=2, encoding="utf-8")
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)
except Exception:
    pass

logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN_3") or os.environ.get("TELEGRAM_BOT_TOKEN")

def register_chat(chat_id: int):
    try:
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        ws = sh.worksheet("TelegramChats")
        values = ws.get_all_values()
        chat_ids = [int(row[0]) for row in values[1:] if row and row[0].isdigit()]
        if chat_id not in chat_ids:
            ws.append_row([str(chat_id)])
            logger.info(f"Registered new Chat ID: {chat_id}")
    except Exception as e:
        logger.error(f"Error registering Chat ID {chat_id}: {e}")

def is_market_hours() -> bool:
    """Returns True if currently within NSE market hours (Mon-Fri, 9:15 AM - 3:30 PM IST)."""
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.datetime.now(tz)
    if now.weekday() > 4:
        return False
    start_time = datetime.time(9, 15)
    end_time = datetime.time(15, 30)
    return start_time <= now.time() <= end_time

def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🔍 Run Market Scan", callback_data="cmd_scan"),
            InlineKeyboardButton("🌐 Market Sentiment", callback_data="cmd_news")
        ],
        [
            InlineKeyboardButton("📈 Open Positions", callback_data="cmd_positions"),
            InlineKeyboardButton("🏦 Portfolio Summary", callback_data="cmd_summary")
        ],
        [
            InlineKeyboardButton("🤝 Trade History", callback_data="cmd_history"),
            InlineKeyboardButton("📅 Scan Schedules", callback_data="cmd_schedules")
        ],
        [
            InlineKeyboardButton("🏆 Curated Pool", callback_data="cmd_pool")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    register_chat(chat_id)
    
    welcome_text = (
        "🤖 **Welcome to AI Swing Trade Bot (System #3 - Hybrid Optimal)!** 🤖\n\n"
        "You are registered for automated daily market breakout scans (**3:25 PM IST**) and intraday exit alerts.\n\n"
        "⚡ **Strategy 3 Key Rules:**\n"
        "• **Universe**: Curated High-Performing Indian Equities\n"
        "• **Volume Conviction**: > 2.25x 20-day Vol SMA\n"
        "• **Target 1 (50% Lock)**: +2.0x ATR (~+6-7% gain)\n"
        "• **Break-Even Guard**: Stop moves to Entry Price after T1!\n"
        "• **Target 2 (Runner)**: 20 EMA Trailing up to +4.5x ATR\n"
        "• **Sector Limit**: Max 3 positions per industry\n\n"
        "**Available Commands:**\n"
        "• `/scan` - Run breakout scan in preview mode\n"
        "• `/news` - Comprehensive Market Sentiment & Macro Guardrails\n"
        "• `/news <TICKER>` - Stock News & Market Sentiment (e.g. `/news RELIANCE`)\n"
        "• `/positions` - View active Strategy #3 holdings & trailing stops\n"
        "• `/summary` - View account balance & risk allocation\n"
        "• `/history` - View closed trades & partial exits\n"
        "• `/schedules` - View Google Sheets scan schedules\n\n"
        "🎛️ **Quick Action Menu:** Tap any button below:"
    )
    await update.message.reply_text(
        welcome_text, 
        reply_markup=get_main_keyboard(), 
        parse_mode="Markdown"
    )

async def scan_action(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    in_market = is_market_hours()
    mode_text = "Live Market Scan" if in_market else "After-Market (AMO) Scan"
    await context.bot.send_message(
        chat_id=chat_id, 
        text=f"🔍 **Executing {mode_text} (Strategy #3)...** Scanning Curated universe (Preview Mode)."
    )
    
    loop = asyncio.get_event_loop()
    try:
        state = await loop.run_in_executor(None, lambda: trading_graph.run_trading_system(execute_trades=False))
        report = trading_graph.format_scan_report(state, is_scheduled=False, is_amo=(not in_market))
        
        trades = state.get("trades_to_execute", [])
        if trades:
            context.bot_data[f"pending_trades_{chat_id}"] = trades
            if in_market:
                confirm_btn = InlineKeyboardButton("🚀 Confirm & Execute Market Entry", callback_data="confirm_market_entry")
            else:
                confirm_btn = InlineKeyboardButton("🌙 Confirm & Execute AMO Entry", callback_data="confirm_amo_entry")
                
            reply_markup = InlineKeyboardMarkup([
                [confirm_btn],
                [InlineKeyboardButton("❌ Discard", callback_data="discard_entry")],
                [InlineKeyboardButton("🎛️ Return to Main Menu", callback_data="cmd_menu")]
            ])
        else:
            reply_markup = get_main_keyboard()
            
        await context.bot.send_message(
            chat_id=chat_id, 
            text=report, 
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error running scan: {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"❌ Error running scan: {e}",
            reply_markup=get_main_keyboard()
        )

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await scan_action(update.effective_chat.id, context)

async def positions_action(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=chat_id, text="📊 **Fetching Open Positions...**")
    
    loop = asyncio.get_event_loop()
    try:
        client = await loop.run_in_executor(None, portfolio_manager.get_gspread_client)
        sh = await loop.run_in_executor(None, portfolio_manager.get_or_create_portfolio_sheet, client)
        open_pos = await loop.run_in_executor(None, portfolio_manager.get_open_positions, sh)
        
        if not open_pos:
            await context.bot.send_message(
                chat_id=chat_id, 
                text="📈 **Current Open Positions:**\n• No active open positions found.",
                reply_markup=get_main_keyboard()
            )
            return
            
        tickers = [p["Ticker"] for p in open_pos]
        dhan_quotes = {}
        quote_source = "Yahoo Finance (EOD Fallback)"
        if dhan_client.is_dhan_configured():
            try:
                dhan_quotes = await loop.run_in_executor(None, dhan_client.get_dhan_ltp, tickers)
                if dhan_quotes:
                    quote_source = "🟢 DhanHQ (Live Broker Feed)"
            except Exception as e:
                logger.error(f"Dhan positions quote error: {e}")

        msg = f"📊 **Current Open Positions ({len(open_pos)}) — Strategy #3:**\n"
        msg += f"📡 *Price Feed: {quote_source}*\n\n"
        
        for idx, p in enumerate(open_pos, 1):
            t = p.get("Ticker")
            comp_name = screener.get_company_name(t)
            qty = p.get("Quantity")
            entry = float(p.get("Entry Price", 0))
            sl = float(p.get("Current SL", 0))
            target = p.get("Target")
            current_p = dhan_quotes.get(t, entry)
            unreal_pnl = (current_p - entry) * int(qty)
            unreal_pct = ((current_p - entry) / entry) * 100.0 if entry > 0 else 0.0
            
            pnl_emoji = "🟢" if unreal_pnl >= 0 else "🔴"
            is_runner = sl >= entry
            status_badge = "🛡️ FREE RUNNER (SL @ Break-Even)" if is_runner else "🎯 Aiming for T1 (50% Lock)"
            
            msg += f"{idx}. 🏢 **{comp_name}** (`{t.replace('.NS', '')}`)\n"
            msg += f"   • Qty: `{qty}` | Entry: `₹{entry:.2f}` | LTP: `₹{current_p:.2f}`\n"
            msg += f"   • SL: `₹{sl:.2f}` | Target: `{target}`\n"
            msg += f"   • Status: {status_badge}\n"
            msg += f"   • Unrealized PnL: {pnl_emoji} `₹{unreal_pnl:+,.2f}` (`{unreal_pct:+.2f}%`)\n\n"
            
        await context.bot.send_message(
            chat_id=chat_id, 
            text=msg, 
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"❌ Error fetching positions: {e}",
            reply_markup=get_main_keyboard()
        )

async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await positions_action(update.effective_chat.id, context)

async def history_action(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    loop = asyncio.get_event_loop()
    try:
        closed_pos = await loop.run_in_executor(None, portfolio_manager.get_closed_trades)
        if not closed_pos:
            await context.bot.send_message(
                chat_id=chat_id, 
                text="📜 **Trade History:**\n• No closed trades recorded yet.",
                reply_markup=get_main_keyboard()
            )
            return
            
        msg = f"📜 **Trade History (Recent Closed Trades & Partial Exits):**\n\n"
        total_pnl = 0.0
        win_count = 0
        
        for idx, p in enumerate(closed_pos[-10:], 1):
            t = p.get("Ticker", "")
            comp_name = screener.get_company_name(t)
            entry = float(p.get("Entry Price", 0))
            exit_p = float(p.get("Exit Price", 0))
            pnl = float(p.get("PnL", 0)) if p.get("PnL") != "" else 0.0
            pnl_pct = ((exit_p - entry) / entry) * 100.0 if entry > 0 else 0.0
            total_pnl += pnl
            if pnl > 0:
                win_count += 1
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            reason = p.get("Exit Reason", "Closed")
            exit_date = p.get("Exit Date", "")
            
            msg += f"{idx}. 🏢 **{comp_name}** (`{t.replace('.NS', '')}`)\n"
            msg += f"   • Entry: `₹{entry:.2f}` | Exit: `₹{exit_p:.2f}`\n"
            msg += f"   • PnL: {pnl_emoji} `₹{pnl:+,.2f}` (`{pnl_pct:+.2f}%`)\n"
            msg += f"   • 🏷️ Reason: {reason} | 📅 Date: {exit_date}\n\n"
            
        win_rate = (win_count / len(closed_pos)) * 100.0 if closed_pos else 0.0
        msg += f"📊 **Total Closed:** {len(closed_pos)} trades | 🏆 **Win Rate:** {win_rate:.1f}%\n"
        msg += f"💰 **Total Realized PnL:** `₹{total_pnl:+,.2f}`"
        
        await context.bot.send_message(
            chat_id=chat_id, 
            text=msg, 
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"❌ Error fetching trade history: {e}",
            reply_markup=get_main_keyboard()
        )

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await history_action(update.effective_chat.id, context)

async def schedules_action(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.datetime.now(tz)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ *Checking Strategy #3 Google Sheets scan schedules as of {now.strftime('%H:%M:%S IST')}...*",
        parse_mode="Markdown"
    )
    
    loop = asyncio.get_event_loop()
    try:
        client = await loop.run_in_executor(None, portfolio_manager.get_gspread_client)
        sh = await loop.run_in_executor(None, lambda: portfolio_manager.get_or_create_portfolio_sheet(client))
        schedules = await loop.run_in_executor(None, lambda: portfolio_manager.get_pending_schedules(sh))
        
        if not schedules:
            await context.bot.send_message(
                chat_id=chat_id,
                text="ℹ️ No pending schedules found in Google Sheets (`Schedules` worksheet).",
                reply_markup=get_main_keyboard()
            )
            return
            
        msg = f"📅 *Google Sheets Scan Schedules ({len(schedules)} Pending):*\n"
        msg += f"⏱️ *Current Cloud Time:* `{now.strftime('%Y-%m-%d %H:%M:%S IST')}`\n\n"
        
        for s in schedules:
            due = portfolio_manager.is_schedule_due(s, now)
            due_str = "🟢 **DUE NOW**" if due else "⏳ Waiting"
            msg += f"• **Row {s['row_idx']}:** `{s['date']}` at `{s['time']} IST`\n"
            msg += f"   Mode: `{s['mode']}` | Status: `{s['status']}`\n"
            if s.get("notes"):
                msg += f"   Notes: `{s['notes']}`\n"
            msg += f"   State: {due_str}\n\n"
            
        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in schedules_action: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Error reading schedules: {e}",
            reply_markup=get_main_keyboard()
        )

async def schedules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await schedules_action(update.effective_chat.id, context)

async def summary_action(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    acc = portfolio_manager.get_account_summary()
    holdings = portfolio_manager.get_open_positions()
    lines = [
        "💼 *ACCOUNT & PERFORMANCE SUMMARY (Strategy #3)*",
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
    await context.bot.send_message(
        chat_id=chat_id, 
        text=txt, 
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await summary_action(update.effective_chat.id, context)

async def pool_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool_setting = os.environ.get("ACTIVE_STOCK_POOL", "curated_pool_top_50.csv")
    tickers = screener.get_curated_tickers("top_50" if "50" in pool_setting else "top_101")
    lines = [
        f"🏆 *CURATED STOCK UNIVERSE (Strategy #3)*",
        "══════════════════════════════════════",
        f"Active Pool: *{'Top 50 Champions' if '50' in pool_setting else 'Top 101 Winners'}*",
        f"Total Constituents: *{len(tickers)} stocks*",
        "Top Constituents Sample: " + ", ".join(tickers[:12]) + "...",
        "\n*Why Curated Pools?*",
        "Outperformed benchmark NIFTY 50 by over +300% in backtests!"
    ]
    txt = "\n".join(lines)
    await context.bot.send_message(
        chat_id=chat_id if hasattr(update, 'effective_chat') and update.effective_chat else update.callback_query.message.chat_id,
        text=txt,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def news_action(chat_id: int, context: ContextTypes.DEFAULT_TYPE, query_arg: str = None):
    loop = asyncio.get_event_loop()
    await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ *Conducting Global & Indian market macro news analysis & guardrails...*",
        parse_mode="Markdown"
    )
    try:
        macro_data = await loop.run_in_executor(
            None,
            sentiment_analyzer.get_comprehensive_market_macro_sentiment
        )
        macro_report = sentiment_analyzer.format_macro_sentiment_report(macro_data)
        await context.bot.send_message(
            chat_id=chat_id,
            text=macro_report,
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error analyzing news: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Error analyzing market sentiment: {e}",
            reply_markup=get_main_keyboard()
        )

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_arg = " ".join(context.args).strip() if context.args else None
    await news_action(update.effective_chat.id, context, query_arg=query_arg)

async def menu_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
        
    chat_id = update.effective_chat.id
    action = query.data
    
    if action == "cmd_scan":
        await scan_action(chat_id, context)
    elif action == "cmd_positions":
        await positions_action(chat_id, context)
    elif action == "cmd_history":
        await history_action(chat_id, context)
    elif action == "cmd_summary":
        await summary_action(chat_id, context)
    elif action == "cmd_schedules":
        await schedules_action(chat_id, context)
    elif action == "cmd_news":
        await news_action(chat_id, context)
    elif action == "cmd_pool":
        pool_setting = os.environ.get("ACTIVE_STOCK_POOL", "curated_pool_top_50.csv")
        tickers = screener.get_curated_tickers("top_50" if "50" in pool_setting else "top_101")
        lines = [
            f"🏆 *CURATED STOCK UNIVERSE (Strategy #3)*",
            "══════════════════════════════════════",
            f"Active Pool: *{'Top 50 Champions' if '50' in pool_setting else 'Top 101 Winners'}*",
            f"Total Constituents: *{len(tickers)} stocks*",
            "Top Constituents Sample: " + ", ".join(tickers[:12]) + "...",
            "\n*Why Curated Pools?*",
            "Outperformed benchmark NIFTY 50 by over +300% in backtests!"
        ]
        await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), reply_markup=get_main_keyboard(), parse_mode="Markdown")
    elif action in ["confirm_market_entry", "confirm_amo_entry"]:
        is_amo_flag = (action == "confirm_amo_entry")
        pending = context.bot_data.pop(f"pending_trades_{chat_id}", None)
        if not pending:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ No pending trades found to execute (order may have expired or already been placed). Run /scan again.",
                reply_markup=get_main_keyboard()
            )
            return
            
        action_name = "AMO Entry" if is_amo_flag else "Market Entry"
        await context.bot.send_message(chat_id=chat_id, text=f"⏳ Executing {len(pending)} {action_name} trade(s)...")
        
        loop = asyncio.get_event_loop()
        try:
            success_logs = []
            for t in pending:
                res = await loop.run_in_executor(
                    None,
                    lambda t=t: portfolio_manager.add_position(
                        ticker=t["ticker"],
                        entry_price=t["price"],
                        quantity=t["qty"],
                        initial_sl=t["sl"],
                        target_1=t["target_1"],
                        target_2=t["target_2"]
                    )
                )
                if res:
                    success_logs.append(f"Successfully added {t['ticker']} x {t['qty']} @ ₹{t['price']:.2f}")
                else:
                    success_logs.append(f"Failed to add {t['ticker']} (cash/risk limit)")
                    
            header = "🌙 **AMO Orders Successfully Placed in Portfolio!**" if is_amo_flag else "🚀 **Live Market Orders Successfully Executed!**"
            msg = f"{header}\n\n" + "\n".join(f"• {log}" for log in success_logs)
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error executing manual entries: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Error executing entries: {e}",
                reply_markup=get_main_keyboard()
            )
    elif action == "discard_entry":
        context.bot_data.pop(f"pending_trades_{chat_id}", None)
        await context.bot.send_message(
            chat_id=chat_id,
            text="🗑️ Proposed trades discarded. No entries were added to your portfolio.",
            reply_markup=get_main_keyboard()
        )
    elif action == "cmd_menu":
        await context.bot.send_message(
            chat_id=chat_id,
            text="🎛️ **Main Control Menu (Strategy #3):**",
            reply_markup=get_main_keyboard()
        )

def main():
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN not configured in .env. Bot will run in standalone engine mode.")
        return
        
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )
    
    app = ApplicationBuilder().token(TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(CommandHandler("menu", start_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("positions", positions_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("schedules", schedules_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler("pool", pool_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CallbackQueryHandler(menu_button_callback))
    
    print("AI-Swing-Trade-3 Telegram Bot starting polling (timeout=20s, pool=30s)...")
    app.run_polling(drop_pending_updates=True, poll_interval=2.0, timeout=20)

def run_forever():
    while True:
        try:
            main()
            time.sleep(5)
        except TimedOut:
            print("⏱️ [Notice] Telegram connection timed out. Reconnecting automatically in 5s...")
            time.sleep(5)
        except NetworkError as e:
            print(f"🌐 [Notice] Network glitch: {e}. Reconnecting in 5s...")
            time.sleep(5)
        except Conflict:
            print("\n" + "="*75)
            print("⚠️  TELEGRAM BOT TOKEN CONFLICT DETECTED")
            print("="*75)
            time.sleep(15)
        except Exception as e:
            err_str = str(e)
            if "Conflict" in err_str or "terminated by other getUpdates" in err_str:
                time.sleep(15)
            elif "Timed out" in err_str or "timeout" in err_str.lower():
                print("⏱️ [Notice] Polling timeout. Reconnecting in 5s...")
                time.sleep(5)
            else:
                print(f"⚠️ [Error] {e}. Reconnecting in 10s...")
                time.sleep(10)

if __name__ == "__main__":
    run_forever()

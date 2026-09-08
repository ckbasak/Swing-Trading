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
import requests
from logging.handlers import RotatingFileHandler
import pandas as pd
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

import portfolio_manager
import screener
import trading_graph
import dhan_client
import sentiment_analyzer
import tax_sentinel

# Configure logging with rotating file handler
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

# Auto-load .env if available
def _load_env():
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except Exception:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() not in os.environ:
                            os.environ[k.strip()] = v.strip().strip("'").strip('"')
_load_env()

TELEGRAM_BOT_TOKEN = (
    os.environ.get("TELEGRAM_BOT_TOKEN_3") or 
    os.environ.get("TELEGRAM_BOT_TOKEN") or 
    os.environ.get("BOT_TOKEN")
)
if TELEGRAM_BOT_TOKEN:
    TELEGRAM_BOT_TOKEN = TELEGRAM_BOT_TOKEN.strip().strip("'").strip('"')

def register_chat(chat_id: int):
    try:
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        try:
            _, _, chats_name = portfolio_manager.get_worksheet_names(sh)
            ws = sh.worksheet(chats_name)
        except Exception:
            ws = sh.add_worksheet(title="TelegramChats", rows="100", cols="1")
            ws.append_row(["ChatID"])
            
        values = ws.get_all_values()
        chat_ids = [int(row[0]) for row in values[1:] if row and row[0].isdigit()]
        if chat_id not in chat_ids:
            ws.append_row([str(chat_id)])
            logger.info(f"Registered new Chat ID: {chat_id}")
    except Exception as e:
        logger.error(f"Error registering Chat ID {chat_id}: {e}")

def get_registered_chats() -> list:
    try:
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        try:
            _, _, chats_name = portfolio_manager.get_worksheet_names(sh)
            ws = sh.worksheet(chats_name)
        except Exception:
            return []
        values = ws.get_all_values()
        return [int(row[0]) for row in values[1:] if row and row[0].isdigit()]
    except Exception as e:
        logger.error(f"Error getting registered chats: {e}")
        return []

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

# Core Commands & Handlers

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

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎛️ **Main Control Menu (Strategy #3):**", 
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
                reply_markup=get_main_menu_keyboard()
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
            reply_markup=get_main_menu_keyboard(),
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

async def checkrates_action(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ *Autonomous Regulatory Sentinel is scanning Indian financial news & regulatory circulars via Gemini AI...*",
        parse_mode="Markdown"
    )
    loop = asyncio.get_event_loop()
    try:
        client = await loop.run_in_executor(None, portfolio_manager.get_gspread_client)
        sh = await loop.run_in_executor(None, lambda: portfolio_manager.get_or_create_portfolio_sheet(client))
        report = await loop.run_in_executor(None, lambda: tax_sentinel.run_sentinel_cycle(sh))
        cfg = await loop.run_in_executor(None, lambda: portfolio_manager.get_fee_and_tax_config(sh, force_refresh=True))
        text = tax_sentinel.format_sentinel_status_message(report, cfg, strategy_num=3)
        
        kb = get_main_keyboard() if "get_main_keyboard" in globals() else get_main_menu_keyboard()
        await status_msg.edit_text(text=text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in checkrates_action: {e}")
        kb = get_main_keyboard() if "get_main_keyboard" in globals() else get_main_menu_keyboard()
        await status_msg.edit_text(text=f"❌ Error scanning regulatory news: {e}", reply_markup=kb)

async def checkrates_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await checkrates_action(update.effective_chat.id, context)

async def rates_action(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    loop = asyncio.get_event_loop()
    try:
        cfg = await loop.run_in_executor(None, lambda: portfolio_manager.get_fee_and_tax_config(force_refresh=True))
        lines = [
            f"🏛️ **Active Regulatory Charges & Tax Schedule (Strategy #3)**",
            "────────────────────────────",
            f"• **STT (Buy Turnover)**: `{cfg['stt_buy_pct']:.3f}%`",
            f"• **STT (Sell Turnover)**: `{cfg['stt_sell_pct']:.3f}%`",
            f"• **Stamp Duty (Buy)**: `{cfg['stamp_duty_pct']:.3f}%`",
            f"• **NSE Turnover Fee**: `{cfg['nse_fee_pct']:.5f}%`",
            f"• **SEBI Turnover Fee**: `₹{cfg['sebi_fee_per_cr']:.0f} / crore`",
            f"• **GST Rate**: `{cfg['gst_pct']:.1f}%` (on NSE+SEBI+Brokerage)",
            f"• **DP Charges (Sell)**: `₹{cfg['dp_charges']:.2f}` flat per scrip/day",
            f"• **Brokerage**: `₹{cfg.get('brokerage_flat', 0.0):.2f}` (Dhan Zero Delivery)",
            f"• **STCG Tax Rate**: `{cfg['stcg_tax_pct']:.1f}%` (Section 111A)",
            "────────────────────────────",
            "💡 **Dynamic Update Policy:**",
            "Rates are dynamically read in real-time from the Google Sheet **Account** tab (or environment variables). Any modification in the sheet immediately updates all trade calculations and portfolio tax accounting."
        ]
        rates_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Scan Regulatory & Tax News Now", callback_data="cmd_checkrates")],
            [InlineKeyboardButton("🎛️ Main Menu", callback_data="cmd_menu")]
        ])
        await context.bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            reply_markup=rates_kb,
            parse_mode="Markdown"
        )
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error reading rates: {e}")

async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rates_action(update.effective_chat.id, context)

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
        f"• *Gross Realized PnL*: ₹{acc.get('realized_pnl', 0):,.2f}",
        f"• *Brokerage & Govt Fees*: ₹{acc.get('total_charges', 0):,.2f}",
        f"• *Net Realized PnL*: ₹{acc.get('net_realized_pnl', 0):,.2f}",
        f"• *Est. STCG Tax (20%)*: ₹{acc.get('est_stcg_tax', 0):,.2f}",
        f"• *Net Take-Home PnL*: ₹{acc.get('net_take_home_pnl', 0):,.2f}",
        f"• *Gross Return*: {acc.get('total_return_pct', 0):+.2f}%",
        f"• *Net Realized Return*: {acc.get('net_return_pct', 0):+.2f}%",
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
    chat_id = update.effective_chat.id if hasattr(update, 'effective_chat') and update.effective_chat else update.callback_query.message.chat_id
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
    elif action == "cmd_rates":
        await rates_action(chat_id, context)
    elif action == "cmd_summary":
        await summary_action(chat_id, context)
    elif action == "cmd_schedules":
        await schedules_action(chat_id, context)
    elif action == "cmd_news":
        await news_action(chat_id, context)
    elif action == "cmd_pool":
        await pool_command(update, context)
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

# ----------------- Automated Background Scheduler Jobs -----------------

def resolve_sentiment_target(notes: str):
    clean = notes.strip() if notes else ""
    if not clean:
        return None
    lower = clean.lower()
    if lower in ("market", "nifty", "nifty 50", "nifty50", "benchmark", "index"):
        return "Nifty 50 Indian stock market"
    if any(k in lower for k in ["holdings", "portfolio", "daily", "morning", "scan", "check", "sentiment", "news", "sample"]):
        words = [w for w in clean.replace(",", " ").split() if w.lower() not in (
            "sentiment", "news", "scan", "check", "daily", "morning", "preview", "mode", "for", "sample", "custom", "briefing"
        )]
        if words:
            w0 = words[0]
            if w0.lower() in ("market", "nifty", "nifty 50", "nifty50", "benchmark", "index"):
                return "Nifty 50 Indian stock market"
            if w0.lower() in ("holdings", "portfolio"):
                return None
            return w0
        return None
    return clean

async def check_google_sheets_schedules_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Polls the 'Schedules' worksheet in Google Sheets every 60 seconds.
    If any pending schedule matches current IST time, executes the scan
    and dispatches report to all registered Telegram chats.
    """
    loop = asyncio.get_event_loop()
    try:
        client = await loop.run_in_executor(None, portfolio_manager.get_gspread_client)
        sh = await loop.run_in_executor(None, lambda: portfolio_manager.get_or_create_portfolio_sheet(client))
        schedules = await loop.run_in_executor(None, lambda: portfolio_manager.get_pending_schedules(sh))
        
        if not schedules:
            return
            
        tz = pytz.timezone("Asia/Kolkata")
        now = datetime.datetime.now(tz)
        
        for item in schedules:
            if portfolio_manager.is_schedule_due(item, now):
                row_idx = item["row_idx"]
                date_val = item["date"]
                time_val = item["time"]
                mode = item["mode"]
                notes = item.get("notes", "").strip()
                logger.info(f"Triggering scheduled scan from Google Sheet (Row {row_idx}: {date_val} {time_val}, Mode={mode}, Notes={notes})...")
                
                # Mark as RUNNING in sheet immediately
                await loop.run_in_executor(
                    None,
                    lambda: portfolio_manager.update_schedule_status(sh, row_idx, "RUNNING")
                )
                
                try:
                    if mode in ("SENTIMENT", "NEWS"):
                        macro_data = await loop.run_in_executor(
                            None,
                            sentiment_analyzer.get_comprehensive_market_macro_sentiment
                        )
                        macro_rep = sentiment_analyzer.format_macro_sentiment_report(macro_data)
                        header = (
                            f"🌐 *Dynamic Scheduled Market Sentiment Briefing (Google Sheets Trigger) — Strategy #3*\n"
                            f"📅 Schedule: `{date_val}` at `{time_val} IST` | Mode: `{mode}`\n\n"
                        )
                        full_report = header + macro_rep
                        chat_ids = await loop.run_in_executor(None, get_registered_chats)
                        for cid in chat_ids:
                            try:
                                await context.bot.send_message(
                                    chat_id=cid,
                                    text=full_report,
                                    reply_markup=get_main_keyboard(),
                                    parse_mode="Markdown"
                                )
                            except Exception as e:
                                logger.error(f"Failed to send scheduled sentiment to {cid}: {e}")
                    else:
                        execute_trades = (mode == "EXECUTE")
                        state = await loop.run_in_executor(
                            None,
                            lambda: trading_graph.run_trading_system(execute_trades=execute_trades)
                        )
                        header = (
                            f"⏰ *Dynamic Scheduled Scan Report (Google Sheets Trigger) — Strategy #3*\n"
                            f"📅 Schedule: `{date_val}` at `{time_val} IST` | Mode: `{mode}`\n"
                        )
                        in_market = is_market_hours()
                        report = trading_graph.format_scan_report(state, is_scheduled=execute_trades, is_amo=(not in_market))
                        full_report = f"{header}\n{report}"
                        
                        chat_ids = await loop.run_in_executor(None, get_registered_chats)
                        for cid in chat_ids:
                            try:
                                await context.bot.send_message(
                                    chat_id=cid,
                                    text=full_report,
                                    reply_markup=get_main_keyboard(),
                                    parse_mode="Markdown"
                                )
                            except Exception as e:
                                logger.error(f"Failed to send scheduled scan to {cid}: {e}")
                                
                    last_run_str = now.strftime("%Y-%m-%d %H:%M:%S IST")
                    is_recurring = str(date_val).strip().upper() in ("DAILY", "WEEKDAYS", "WEEKDAY", "MON-FRI")
                    new_status = "ACTIVE" if is_recurring else "COMPLETED"
                    
                    await loop.run_in_executor(
                        None,
                        lambda: portfolio_manager.update_schedule_status(sh, row_idx, new_status, last_run=last_run_str)
                    )
                    logger.info(f"Schedule row {row_idx} completed successfully (status -> {new_status}).")
                except Exception as ex:
                    logger.error(f"Error executing schedule row {row_idx}: {ex}")
                    await loop.run_in_executor(
                        None,
                        lambda: portfolio_manager.update_schedule_status(sh, row_idx, "ERROR", last_run=f"Error: {ex}")
                    )
    except Exception as e:
        logger.error(f"Error in check_google_sheets_schedules_job: {e}")

async def daily_scan_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Starting scheduled daily scan job (Auto-Execution)...")
    loop = asyncio.get_event_loop()
    try:
        state = await loop.run_in_executor(None, lambda: trading_graph.run_trading_system(execute_trades=True))
        in_market = is_market_hours()
        report = trading_graph.format_scan_report(state, is_scheduled=True, is_amo=(not in_market))
        
        chat_ids = await loop.run_in_executor(None, get_registered_chats)
        for cid in chat_ids:
            try:
                await context.bot.send_message(
                    chat_id=cid, 
                    text=report, 
                    reply_markup=get_main_keyboard(), 
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to send daily scan to {cid}: {e}")
    except Exception as e:
        logger.error(f"Error in daily_scan_job: {e}")

async def market_hours_sync_job(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.datetime.now(tz)
    if now.weekday() > 4:
        return
        
    start_time = datetime.time(9, 15)
    end_time = datetime.time(15, 30)
    current_time = now.time()
    
    if start_time <= current_time <= end_time:
        logger.info("Executing intraday market hours portfolio sync...")
        loop = asyncio.get_event_loop()
        try:
            client = await loop.run_in_executor(None, portfolio_manager.get_gspread_client)
            sh = await loop.run_in_executor(None, portfolio_manager.get_or_create_portfolio_sheet(client))
            logs = await loop.run_in_executor(None, portfolio_manager.sync_portfolio, sh)
            exit_logs = [log for log in logs if any(k in log for k in ["Closed trade", "Target 1 Hit", "Target 2 Hit"])]
            if exit_logs:
                chat_ids = await loop.run_in_executor(None, get_registered_chats)
                for cid in chat_ids:
                    for log in exit_logs:
                        await context.bot.send_message(
                            chat_id=cid, 
                            text=f"🔔 **Intraday Exit Alert (Strategy #3):**\n{log}", 
                            reply_markup=get_main_keyboard(), 
                            parse_mode="Markdown"
                        )
        except Exception as e:
            logger.error(f"Error during intraday market sync: {e}")

async def regulatory_sentinel_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Scheduled background task that scans financial news RSS & regulatory circulars.
    If an official statutory revision is enacted, updates Google Sheets, recalculates taxes,
    and broadcasts an urgent alert to all registered Telegram chats.
    """
    logger.info(f"Starting scheduled Regulatory & Tax Sentinel news check (Strategy #3)...")
    loop = asyncio.get_event_loop()
    try:
        client = await loop.run_in_executor(None, portfolio_manager.get_gspread_client)
        sh = await loop.run_in_executor(None, lambda: portfolio_manager.get_or_create_portfolio_sheet(client))
        report = await loop.run_in_executor(None, lambda: tax_sentinel.run_sentinel_cycle(sh))
        
        if report.get("has_official_change") and report.get("changes_detected"):
            cfg = await loop.run_in_executor(None, lambda: portfolio_manager.get_fee_and_tax_config(sh, force_refresh=True))
            alert_text = tax_sentinel.format_sentinel_status_message(report, cfg, strategy_num=3)
            chat_ids = await loop.run_in_executor(None, get_registered_chats)
            kb = get_main_keyboard() if "get_main_keyboard" in globals() else get_main_menu_keyboard()
            for cid in chat_ids:
                try:
                    await context.bot.send_message(
                        chat_id=cid,
                        text=alert_text,
                        reply_markup=kb,
                        parse_mode="Markdown"
                    )
                except Exception as ex:
                    logger.error(f"Failed sending regulatory alert to {cid}: {ex}")
        else:
            logger.info(f"Regulatory Sentinel scan complete: No statutory changes detected ({report.get('scanned_count', 0)} sources evaluated).")
    except Exception as e:
        logger.error(f"Error in regulatory_sentinel_job: {e}")

async def render_keep_alive_job(context: ContextTypes.DEFAULT_TYPE):
    render_url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("RENDER_SERVICE_URL") or "https://ai-swing-trade-3.onrender.com"
    target = f"{render_url.rstrip('/')}/_stcore/health"
    loop = asyncio.get_running_loop()
    try:
        def _ping():
            return requests.get(target, timeout=25)
        res = await loop.run_in_executor(None, _ping)
        logger.info(f"Render keep-alive ping to {target} -> HTTP {res.status_code}")
    except Exception as e:
        logger.debug(f"Render keep-alive ping error: {e}")

async def post_init_setup(application: Application):
    commands = [
        BotCommand("menu", "🎛️ Show Interactive Button Menu"),
        BotCommand("scan", "🔍 Run Strategy #3 Scan (Preview)"),
        BotCommand("news", "🌐 Market Sentiment & Macro Guardrails"),
        BotCommand("positions", "📈 Strategy #3 Open Holdings"),
        BotCommand("history", "🤝 Strategy #3 Closed Trades"),
        BotCommand("schedules", "📅 View Scan Schedules"),
        BotCommand("summary", "🏦 Strategy #3 Summary"),
        BotCommand("rates", "🏛️ Statutory Fee & Tax Rates"),
        BotCommand("start", "🚀 Start & Register Chat")
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Successfully registered native Telegram Bot Command Menu.")
    except Exception as e:
        logger.error(f"Error setting Telegram Bot commands: {e}")

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("No TELEGRAM_BOT_TOKEN environment variable set. Exiting.")
        return

    # Create Bot Application with post_init hook
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init_setup).build()
    
    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler(["news", "sentiment"], news_command))
    app.add_handler(CommandHandler(["positions", "position"], positions_command))
    app.add_handler(CommandHandler(["history", "closed", "trades"], history_command))
    app.add_handler(CommandHandler(["schedules", "schedule"], schedules_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler(["rates", "fees", "tax"], rates_command))
    app.add_handler(CommandHandler("pool", pool_command))
    app.add_handler(CallbackQueryHandler(menu_button_callback))
    
    # Configure JobQueue
    tz = pytz.timezone("Asia/Kolkata")
        
    # 1. Morning Scan Job at 8:00 AM IST daily
    morning_time = datetime.time(hour=8, minute=0, second=0, tzinfo=tz)
    app.job_queue.run_daily(
        daily_scan_job,
        time=morning_time,
        days=(0, 1, 2, 3, 4, 5, 6),
        name="morning_scan_8am",
        job_kwargs={"misfire_grace_time": 180}
    )
    logger.info("Morning scan job scheduled for 08:00 IST daily.")

    # Autonomous Regulatory Sentinel Jobs (8:15 AM & 4:15 PM IST)
    app.job_queue.run_daily(
        regulatory_sentinel_job,
        time=datetime.time(hour=8, minute=15, second=0, tzinfo=tz),
        days=(0, 1, 2, 3, 4, 5, 6),
        name="sentinel_morning_check",
        job_kwargs={"misfire_grace_time": 180}
    )
    app.job_queue.run_daily(
        regulatory_sentinel_job,
        time=datetime.time(hour=16, minute=15, second=0, tzinfo=tz),
        days=(0, 1, 2, 3, 4),
        name="sentinel_evening_check",
        job_kwargs={"misfire_grace_time": 180}
    )
    logger.info("Autonomous Regulatory Sentinel scheduled (08:15 & 16:15 IST).")

    # 2. Dynamic Google Sheets Scan Scheduler (polls every 60s)
    app.job_queue.run_repeating(
        check_google_sheets_schedules_job,
        interval=60,
        first=15,
        name="dynamic_sheets_scheduler",
        job_kwargs={"misfire_grace_time": 45}
    )
    logger.info("Dynamic Google Sheets Scan Scheduler active (polling every 60s).")

    # 3. Market Close Scan Job at 3:25 PM IST (Mon-Fri)
    time_to_run = datetime.time(hour=15, minute=25, second=0, tzinfo=tz)
    app.job_queue.run_daily(
        daily_scan_job, 
        time=time_to_run,
        days=(0, 1, 2, 3, 4),
        name="closing_scan_325pm",
        job_kwargs={"misfire_grace_time": 120}
    )
    logger.info("Market close scan job scheduled for 15:25 IST (Mon-Fri).")
    
    # 4. Repeating Intraday Sync every 5 minutes during market hours
    app.job_queue.run_repeating(market_hours_sync_job, interval=300, first=10, job_kwargs={"misfire_grace_time": 60})
    logger.info("Intraday market hours sync job scheduled (every 5 minutes).")

    # 5. Render Keep-Alive every 9 minutes
    app.job_queue.run_repeating(render_keep_alive_job, interval=540, first=30, job_kwargs={"misfire_grace_time": 60})
    logger.info("Render keep-alive job scheduled (every 9 minutes).")
    
    # Start bot
    logger.info("Starting Telegram Bot poll with JobQueue enabled...")
    try:
        with open("bot.pid", "w") as f:
            f.write(str(os.getpid()))
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        portfolio_manager.log_cloud_event(sh, "bot.py", f"Bot application online with JobQueue (PID {os.getpid()})")
    except Exception as e:
        logger.debug(f"Startup log notice: {e}")
    app.run_polling(drop_pending_updates=False)

def run_forever():
    while True:
        try:
            logger.info("Starting Telegram bot service...")
            main()
            logger.warning("main() returned. Restarting in 5s...")
            time.sleep(5)
        except Exception as e:
            logger.error(f"Telegram bot exception: {e}. Reconnecting in 10s...", exc_info=True)
            try:
                client = portfolio_manager.get_gspread_client()
                sh = portfolio_manager.get_or_create_portfolio_sheet(client)
                portfolio_manager.log_cloud_event(sh, "bot.py", f"Bot restart event: {e}")
            except Exception:
                pass
            time.sleep(10)

if __name__ == "__main__":
    run_forever()

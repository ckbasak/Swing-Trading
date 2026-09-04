import os
import pytz
import datetime
import logging
import asyncio
import gspread
import yfinance as yf
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Import backend modules
import portfolio_manager
import trading_graph
import dhan_client
import screener

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
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

# Fetch Token from env
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN_2") or os.environ.get("TELEGRAM_BOT_TOKEN")

# Helper functions for dynamic Telegram chat registration in Google Sheets
def register_chat(chat_id: int):
    try:
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        try:
            _, _, chats_name = portfolio_manager.get_worksheet_names(sh)
            ws = sh.worksheet(chats_name)
        except gspread.WorksheetNotFound:
            _, _, chats_name = portfolio_manager.get_worksheet_names(sh)
            ws = sh.add_worksheet(title=chats_name, rows="100", cols="1")
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
        except gspread.WorksheetNotFound:
            return []
        values = ws.get_all_values()
        return [int(row[0]) for row in values[1:] if row and row[0].isdigit()]
    except Exception as e:
        logger.error(f"Error getting registered chats: {e}")
        return []

def get_main_menu_keyboard():
    """Generates the interactive inline menu button matrix."""
    keyboard = [
        [
            InlineKeyboardButton("🔍 Run Market Scan", callback_data="cmd_scan"),
            InlineKeyboardButton("📈 Open Positions", callback_data="cmd_positions")
        ],
        [
            InlineKeyboardButton("🤝 Trade History", callback_data="cmd_history"),
            InlineKeyboardButton("🏦 Portfolio Summary", callback_data="cmd_summary")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Core Actions (Callable from Slash Commands and Inline Buttons)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    register_chat(chat_id)
    
    welcome_text = (
        "🤖 **Welcome to NSE Multi-Agent Swing Trading Bot (System #2 - Strategy v2)!** 🤖\n\n"
        "You are registered for automated daily market breakout scans (**3:25 PM IST**) and intraday exit alerts.\n\n"
        "🎛️ **Quick Action Menu:** Tap any button below or use the chat menu button `[/]`:"
    )
    await update.message.reply_text(
        welcome_text, 
        reply_markup=get_main_menu_keyboard(), 
        parse_mode="Markdown"
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎛️ **NSE Swing Trading Main Menu (System #2 - Strategy v2)**\n\n"
        "Tap an action button below to execute trades or inspect your portfolio:"
    )
    await update.message.reply_text(
        text, 
        reply_markup=get_main_menu_keyboard(), 
        parse_mode="Markdown"
    )

async def scan_action(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=chat_id, text="🔍 **Executing Swing Trading Scan...** This might take 1-2 minutes.")
    
    loop = asyncio.get_event_loop()
    try:
        state = await loop.run_in_executor(None, trading_graph.run_trading_system)
        report = trading_graph.format_scan_report(state)
        await context.bot.send_message(
            chat_id=chat_id, 
            text=report, 
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error running scan: {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"❌ Error running scan: {e}",
            reply_markup=get_main_menu_keyboard()
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
                reply_markup=get_main_menu_keyboard()
            )
            return
            
        tickers = [p["Ticker"] for p in open_pos]
        
        # Check Dhan for real-time quotes first
        dhan_quotes = {}
        quote_source = "Yahoo Finance (EOD Fallback)"
        if dhan_client.is_dhan_configured():
            try:
                dhan_quotes = await loop.run_in_executor(None, dhan_client.get_dhan_ltp, tickers)
                if dhan_quotes:
                    quote_source = "🟢 DhanHQ (Live Broker Feed)"
            except Exception as e:
                logger.error(f"Dhan positions quote error: {e}")
                
        # Fetch fallback quotes if any tickers missing
        prices_df = None
        if len(dhan_quotes) < len(tickers):
            try:
                prices_df = await loop.run_in_executor(
                    None, lambda: yf.download(tickers, period="1d", group_by="ticker", threads=False, progress=False)
                )
            except Exception as e:
                logger.error(f"yfinance fallback download error: {e}")
        
        tz = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.datetime.now(tz).strftime("%Y-%m-%d | %I:%M:%S %p IST")
        
        msg = f"📈 **Current Open Holdings ({len(open_pos)}):**\n"
        msg += f"📅 *As of: {now_ist}*\n"
        msg += f"📡 *Data Source: {quote_source}*\n\n"
        
        total_unrealized_pnl = 0.0
        
        for idx, p in enumerate(open_pos, 1):
            ticker = p["Ticker"]
            comp_name = screener.get_company_name(ticker)
            ticker_clean = ticker.replace(".NS", "")
            entry = float(p["Entry Price"])
            qty = int(p["Quantity"])
            target = float(p["Target"])
            sl = float(p["Current SL"])
            
            # Determine current price (Prioritize Dhan)
            current = dhan_quotes.get(ticker)
            if current is None and prices_df is not None:
                try:
                    if len(tickers) == 1:
                        current = float(prices_df["Close"].iloc[-1])
                    else:
                        current = float(prices_df[ticker]["Close"].iloc[-1])
                except Exception:
                    current = entry
            elif current is None:
                current = entry
                
            pnl_val = (current - entry) * qty
            pnl_pct = ((current - entry) / entry) * 100.0 if entry > 0 else 0.0
            total_unrealized_pnl += pnl_val
            sector = screener.get_stock_sector(ticker)
            msg += f"{idx}. 🏢 **{comp_name}** (`{ticker_clean}`) — *{sector}*\n"
            msg += f"   • Qty: `{qty}` | Entry: `₹{entry:.2f}` | Live: `₹{current:.2f}`\n"
            msg += f"   • PnL: {pnl_emoji} `₹{pnl_val:+,.2f}` (`{pnl_pct:+.2f}%`)\n"
            msg += f"   • 🛡️ SL: `₹{sl:.2f}` | 🎯 Target: `₹{target:.2f}`\n\n"
        
        total_pnl_emoji = "🟢" if total_unrealized_pnl >= 0 else "🔴"
        msg += f"💰 **Total Unrealized PnL:** {total_pnl_emoji} **₹{total_unrealized_pnl:,.2f}**"
        
        await context.bot.send_message(
            chat_id=chat_id, 
            text=msg, 
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"❌ Error fetching positions: {e}",
            reply_markup=get_main_menu_keyboard()
        )

async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await positions_action(update.effective_chat.id, context)

async def summary_action(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    loop = asyncio.get_event_loop()
    try:
        client = await loop.run_in_executor(None, portfolio_manager.get_gspread_client)
        sh = await loop.run_in_executor(None, portfolio_manager.get_or_create_portfolio_sheet, client)
        account = await loop.run_in_executor(None, portfolio_manager.get_account_details, sh)
        holdings = await loop.run_in_executor(None, portfolio_manager.get_all_holdings, sh)
        perf = await loop.run_in_executor(None, portfolio_manager.calculate_performance_metrics, sh)
        
        feed_source = "🟢 DhanHQ (Live Broker Feed)" if dhan_client.is_dhan_configured() else "⚪ Yahoo Finance (EOD Fallback)"
        
        open_pos = [h for h in holdings if h["Status"] == "OPEN"]
        closed_pos = [h for h in holdings if h["Status"] == "CLOSED"]
        
        total_pnl = 0.0
        pnl_pcts = []
        win_count = 0
        for h in closed_pos:
            try:
                pnl = float(h["PnL"]) if h["PnL"] != "" else 0.0
                total_pnl += pnl
                entry = float(h["Entry Price"])
                exit_price = float(h["Exit Price"])
                pct = ((exit_price - entry) / entry) * 100.0 if entry > 0 else 0.0
                pnl_pcts.append(pct)
                if pnl > 0:
                    win_count += 1
            except Exception:
                pass
                
        win_rate_str = f" ({win_count}/{len(closed_pos)} won, {(win_count/len(closed_pos)*100.0):.1f}%)" if closed_pos else ""
        avg_pct_str = f" (Avg: {sum(pnl_pcts)/len(pnl_pcts):+.2f}%)" if pnl_pcts else ""
        
        tz = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.datetime.now(tz).strftime("%Y-%m-%d | %I:%M:%S %p IST")
        
        msg = (
            "🏦 **Portfolio Performance Summary:**\n"
            f"📅 *As of: {now_ist}*\n"
            f"📡 *Data Engine: {feed_source}*\n\n"
            f"💰 **Total Portfolio Value:** ₹{account.get('Total Portfolio Value', 0):,.2f}\n"
            f"💵 **Cash Balance:** ₹{account.get('Cash Balance', 0):,.2f}\n"
            f"📊 **Open Positions:** {len(open_pos)}\n"
            f"🤝 **Closed Trades:** {len(closed_pos)}{win_rate_str}\n"
            f"📈 **Realized PnL (Closed):** ₹{total_pnl:,.2f}{avg_pct_str}\n"
            f"⏱️ **Days Active:** {perf['Days Elapsed']} Days\n"
            f"🎯 **Total Return:** {perf['Total Return (%)']}%\n"
            f"📊 **CAGR (Annualized):** {perf['CAGR (%)']}%\n"
            f"🌀 **XIRR:** {perf['XIRR (%)']}%\n"
        )
        await context.bot.send_message(
            chat_id=chat_id, 
            text=msg, 
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"❌ Error fetching summary: {e}",
            reply_markup=get_main_menu_keyboard()
        )

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await summary_action(update.effective_chat.id, context)

async def history_action(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    loop = asyncio.get_event_loop()
    try:
        client = await loop.run_in_executor(None, portfolio_manager.get_gspread_client)
        sh = await loop.run_in_executor(None, portfolio_manager.get_or_create_portfolio_sheet, client)
        holdings = await loop.run_in_executor(None, portfolio_manager.get_all_holdings, sh)
        
        closed_pos = [h for h in holdings if h["Status"] == "CLOSED"]
        if not closed_pos:
            await context.bot.send_message(
                chat_id=chat_id, 
                text="🤝 **Closed Trade History:**\n• No closed trades recorded yet.",
                reply_markup=get_main_menu_keyboard()
            )
            return
            
        tz = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.datetime.now(tz).strftime("%Y-%m-%d | %I:%M:%S %p IST")
        
        msg = f"🤝 **Closed Trades History ({len(closed_pos)}):**\n"
        msg += f"📅 *As of: {now_ist}*\n\n"
        
        total_pnl = 0.0
        pnl_pcts = []
        win_count = 0
        
        for idx, p in enumerate(closed_pos, 1):
            ticker = p["Ticker"]
            comp_name = screener.get_company_name(ticker)
            ticker_clean = ticker.replace(".NS", "")
            try:
                entry = float(p["Entry Price"])
            except Exception:
                entry = 0.0
            try:
                exit_price = float(p["Exit Price"])
            except Exception:
                exit_price = 0.0
            try:
                pnl = float(p["PnL"]) if p["PnL"] != "" else 0.0
            except Exception:
                pnl = 0.0
                
            pnl_pct = ((exit_price - entry) / entry) * 100.0 if entry > 0 else 0.0
            total_pnl += pnl
            pnl_pcts.append(pnl_pct)
            if pnl > 0:
                win_count += 1
                
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            exit_reason = p.get("Exit Reason", "Closed")
            exit_date = p.get("Exit Date", "")
            
            msg += f"{idx}. 🏢 **{comp_name}** (`{ticker_clean}`)\n"
            msg += f"   • Entry: `₹{entry:.2f}` | Exit: `₹{exit_price:.2f}`\n"
            msg += f"   • PnL: {pnl_emoji} `₹{pnl:+,.2f}` (`{pnl_pct:+.2f}%`)\n"
            msg += f"   • 🏷️ Reason: {exit_reason} | 📅 Date: {exit_date}\n\n"
            
        win_rate = (win_count / len(closed_pos)) * 100.0 if closed_pos else 0.0
        avg_pct = sum(pnl_pcts) / len(pnl_pcts) if pnl_pcts else 0.0
        total_pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
        
        msg += f"📊 **Total Closed:** {len(closed_pos)} trades\n"
        msg += f"🏆 **Win Rate:** {win_rate:.1f}% ({win_count}/{len(closed_pos)} profitable)\n"
        msg += f"📈 **Avg Return / Trade:** {avg_pct:+.2f}%\n"
        msg += f"💰 **Total Realized PnL:** {total_pnl_emoji} **₹{total_pnl:,.2f}**"
        
        await context.bot.send_message(
            chat_id=chat_id, 
            text=msg, 
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"❌ Error fetching trade history: {e}",
            reply_markup=get_main_menu_keyboard()
        )

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await history_action(update.effective_chat.id, context)

# Callback Query Handler for Inline Buttons
async def menu_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer() # Acknowledge button press immediately
    except Exception:
        pass # Ignore expired callback query timeout
    
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

# Post Init Hook: Registers Native Telegram Menu Commands
async def post_init_setup(application: Application):
    commands = [
        BotCommand("menu", "🎛️ Show Interactive Button Menu"),
        BotCommand("scan", "🔍 Run Strategy #2 Scan & Trades"),
        BotCommand("positions", "📈 Strategy #2 Open Holdings"),
        BotCommand("history", "🤝 Strategy #2 Closed Trades"),
        BotCommand("summary", "🏦 Strategy #2 Summary"),
        BotCommand("start", "🚀 Start & Register Chat")
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Successfully registered native Telegram Bot Command Menu.")
    except Exception as e:
        logger.error(f"Error setting Telegram Bot commands: {e}")

# Daily Cron Job
async def daily_scan_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Starting scheduled daily scan job...")
    
    loop = asyncio.get_event_loop()
    try:
        state = await loop.run_in_executor(None, trading_graph.run_trading_system)
        report = trading_graph.format_scan_report(state)
        
        # Notify all registered chats
        chat_ids = await loop.run_in_executor(None, get_registered_chats)
        if not chat_ids:
            logger.warning("No registered chats found to notify.")
            return
            
        for cid in chat_ids:
            try:
                await context.bot.send_message(
                    chat_id=cid, 
                    text=report, 
                    reply_markup=get_main_menu_keyboard(),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to send to {cid}: {e}")
    except Exception as e:
        logger.error(f"Error in daily_scan_job: {e}")

# Intraday Market Hours Sync Job (Exits only)
async def market_hours_sync_job(context: ContextTypes.DEFAULT_TYPE):
    # Get current time in IST
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.datetime.now(tz)
    
    # 0 = Monday, 4 = Friday. Skip weekends.
    if now.weekday() > 4:
        return
        
    start_time = datetime.time(9, 15)
    end_time = datetime.time(15, 30)
    current_time = now.time()
    
    # Only run during NSE market hours
    if start_time <= current_time <= end_time:
        logger.info("Executing intraday market hours portfolio sync...")
        loop = asyncio.get_event_loop()
        try:
            client = await loop.run_in_executor(None, portfolio_manager.get_gspread_client)
            sh = await loop.run_in_executor(None, portfolio_manager.get_or_create_portfolio_sheet, client)
            
            # Sync portfolio checks for exits and returns a log list
            logs = await loop.run_in_executor(None, portfolio_manager.sync_portfolio, sh)
            
            # Extract closed trade logs (exits)
            exit_logs = [log for log in logs if "Closed trade" in log]
            if exit_logs:
                chat_ids = await loop.run_in_executor(None, get_registered_chats)
                for cid in chat_ids:
                    for log in exit_logs:
                        await context.bot.send_message(
                            chat_id=cid, 
                            text=f"🔔 **Intraday Exit Alert:**\n{log}", 
                            reply_markup=get_main_menu_keyboard(),
                            parse_mode="Markdown"
                        )
        except Exception as e:
            logger.error(f"Error during intraday market sync: {e}")

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("No TELEGRAM_BOT_TOKEN environment variable set. Exiting.")
        return

    # Create Bot Application with post_init hook for setting native menu commands
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init_setup).build()
    
    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler(["positions", "position"], positions_command))
    app.add_handler(CommandHandler(["history", "closed", "trades"], history_command))
    app.add_handler(CommandHandler("summary", summary_command))
    
    # Register callback query handler for interactive buttons
    app.add_handler(CallbackQueryHandler(menu_button_callback))
    
    # Configure JobQueue to run daily at 3:25 PM IST (Monday through Friday)
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Kolkata")
    except ImportError:
        tz = pytz.timezone("Asia/Kolkata")
        
    time_to_run = datetime.time(hour=15, minute=25, second=0, tzinfo=tz)
    app.job_queue.run_daily(
        daily_scan_job, 
        time=time_to_run,
        days=(1, 2, 3, 4, 5), # Monday through Friday
        job_kwargs={"misfire_grace_time": 120}
    )
    logger.info("Daily scan job scheduled for 15:25 IST (Mon-Fri).")
    
    # Configure Repeating Job to run every 5 minutes (300 seconds) during market hours
    app.job_queue.run_repeating(market_hours_sync_job, interval=300, first=10, job_kwargs={"misfire_grace_time": 60})
    logger.info("Intraday market hours sync job scheduled (every 5 minutes).")
    
    # Start bot
    logger.info("Starting Telegram Bot poll...")
    app.run_polling()

if __name__ == "__main__":
    main()

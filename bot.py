import os
import pytz
import datetime
import logging
import asyncio
import gspread
import yfinance as yf
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Import backend modules
import portfolio_manager
import trading_graph

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Fetch Token from env
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Helper functions for dynamic Telegram chat registration in Google Sheets
def register_chat(chat_id: int):
    try:
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        try:
            ws = sh.worksheet("TelegramChats")
        except gspread.WorksheetNotFound:
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
            ws = sh.worksheet("TelegramChats")
        except gspread.WorksheetNotFound:
            return []
        values = ws.get_all_values()
        return [int(row[0]) for row in values[1:] if row and row[0].isdigit()]
    except Exception as e:
        logger.error(f"Error getting registered chats: {e}")
        return []

# Bot Commands
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    register_chat(chat_id)
    
    welcome_text = (
        "🤖 **Welcome to the NSE Multi-Agent Swing Trading Bot!** 🤖\n\n"
        "You have been registered for automated daily swing trading updates.\n\n"
        "**Available Commands:**\n"
        "🔹 `/scan` - Manually trigger the market scan and execute trades.\n"
        "🔹 `/positions` - List all currently open holdings and their PnL.\n"
        "🔹 `/summary` - Get portfolio performance & cash balances.\n\n"
        "The automated scan runs daily at **3:25 PM IST** (Monday-Friday)."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 **Executing Swing Trading Scan...** This might take 1-2 minutes.")
    
    loop = asyncio.get_event_loop()
    try:
        state = await loop.run_in_executor(None, trading_graph.run_trading_system)
        report = trading_graph.format_scan_report(state)
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error running scan: {e}")
        await update.message.reply_text(f"❌ Error running scan: {e}")

async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 **Fetching Open Positions...**")
    
    loop = asyncio.get_event_loop()
    try:
        client = await loop.run_in_executor(None, portfolio_manager.get_gspread_client)
        sh = await loop.run_in_executor(None, portfolio_manager.get_or_create_portfolio_sheet, client)
        open_pos = await loop.run_in_executor(None, portfolio_manager.get_open_positions, sh)
        
        if not open_pos:
            await update.message.reply_text("No active open positions found.")
            return
            
        tickers = [p["Ticker"] for p in open_pos]
        # Fetch current prices
        prices_df = await loop.run_in_executor(None, lambda: yf.download(tickers, period="1d", group_by="ticker"))
        
        # Prices and PnL Table
        pnl_header = f"{'Ticker':<9} {'Qty':<4} {'Entry':<7} {'Current':<7} {'PnL%':<6}"
        pnl_lines = [pnl_header, "-" * len(pnl_header)]
        
        # Risk and Targets Table
        risk_header = f"{'Ticker':<9} {'SL':<7} {'Target':<7} {'EntryVal':<8}"
        risk_lines = [risk_header, "-" * len(risk_header)]
        
        total_unrealized_pnl = 0.0
        
        for p in open_pos:
            ticker = p["Ticker"]
            ticker_clean = ticker.replace(".NS", "")
            entry = float(p["Entry Price"])
            qty = int(p["Quantity"])
            target = float(p["Target"])
            sl = float(p["Current SL"])
            
            # Extract current price
            try:
                if len(tickers) == 1:
                    current = float(prices_df["Close"].iloc[-1])
                else:
                    current = float(prices_df[ticker]["Close"].iloc[-1])
            except Exception:
                current = entry
                
            pnl_val = (current - entry) * qty
            pnl_pct = ((current - entry) / entry) * 100
            total_unrealized_pnl += pnl_val
            
            pnl_lines.append(f"{ticker_clean:<9} {qty:<4} {entry:<7.1f} {current:<7.1f} {pnl_pct:>+5.1f}%")
            
            entry_value = entry * qty
            risk_lines.append(f"{ticker_clean:<9} {sl:<7.1f} {target:<7.1f} {entry_value:<8.1f}")
            
        msg = "📈 **Current Open Positions:**\n\n"
        msg += "📊 **Prices & PnL:**\n"
        msg += "```\n" + "\n".join(pnl_lines) + "\n```\n"
        msg += "🛡️ **Risk & Targets:**\n"
        msg += "```\n" + "\n".join(risk_lines) + "\n```\n"
        
        pnl_emoji = "🟢" if total_unrealized_pnl >= 0 else "🔴"
        msg += f"💰 **Total Unrealized PnL:** {pnl_emoji} ₹{total_unrealized_pnl:,.2f}"
        
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        await update.message.reply_text(f"❌ Error fetching positions: {e}")

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loop = asyncio.get_event_loop()
    try:
        client = await loop.run_in_executor(None, portfolio_manager.get_gspread_client)
        sh = await loop.run_in_executor(None, portfolio_manager.get_or_create_portfolio_sheet, client)
        account = await loop.run_in_executor(None, portfolio_manager.get_account_details, sh)
        holdings = await loop.run_in_executor(None, portfolio_manager.get_all_holdings, sh)
        perf = await loop.run_in_executor(None, portfolio_manager.calculate_performance_metrics, sh)
        
        open_pos = [h for h in holdings if h["Status"] == "OPEN"]
        closed_pos = [h for h in holdings if h["Status"] == "CLOSED"]
        
        total_pnl = sum(float(h["PnL"]) for h in closed_pos if h["PnL"] != "")
        
        msg = (
            "🏦 **Portfolio Summary:**\n\n"
            f"💰 **Total Portfolio Value:** ₹{account.get('Total Portfolio Value', 0):,.2f}\n"
            f"💵 **Cash Balance:** ₹{account.get('Cash Balance', 0):,.2f}\n"
            f"📊 **Open Positions:** {len(open_pos)}\n"
            f"🤝 **Closed Trades:** {len(closed_pos)}\n"
            f"📈 **Realized PnL (Closed):** ₹{total_pnl:,.2f}\n"
            f"⏱️ **Days Active:** {perf['Days Elapsed']} Days\n"
            f"🎯 **Total Return:** {perf['Total Return (%)']}%\n"
            f"📊 **CAGR (Annualized):** {perf['CAGR (%)']}%\n"
            f"🌀 **XIRR:** {perf['XIRR (%)']}%\n"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        await update.message.reply_text(f"❌ Error fetching summary: {e}")

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
                await context.bot.send_message(chat_id=cid, text=report, parse_mode="Markdown")
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
                            parse_mode="Markdown"
                        )
        except Exception as e:
            logger.error(f"Error during intraday market sync: {e}")

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("No TELEGRAM_BOT_TOKEN environment variable set. Exiting.")
        return

    # Create Bot Application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler(["positions", "position"], positions_command))
    app.add_handler(CommandHandler("summary", summary_command))
    
    # Configure JobQueue to run daily at 3:25 PM IST (5 minutes before market close)
    tz = pytz.timezone("Asia/Kolkata")
    time_to_run = datetime.time(hour=15, minute=25, second=0, tzinfo=tz)
    app.job_queue.run_daily(daily_scan_job, time=time_to_run)
    logger.info("Daily scan job scheduled for 15:25 IST.")
    
    # Configure Repeating Job to run every 5 minutes (300 seconds) during market hours
    app.job_queue.run_repeating(market_hours_sync_job, interval=300, first=10)
    logger.info("Intraday market hours sync job scheduled (every 5 minutes).")
    
    # Start bot
    logger.info("Starting Telegram Bot poll...")
    app.run_polling()

if __name__ == "__main__":
    main()

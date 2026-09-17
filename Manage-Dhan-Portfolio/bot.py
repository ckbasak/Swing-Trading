import os
import sys
import time
import datetime
import logging
from logging.handlers import RotatingFileHandler
import asyncio
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

import dhan_client
import portfolio_analyzer
import portfolio_manager

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

# Auto-load .env
def _load_env():
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_file):
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
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
    os.environ.get("PORTFOLIO_BOT_TOKEN") or
    os.environ.get("TELEGRAM_BOT_TOKEN_2") or
    os.environ.get("TELEGRAM_BOT_TOKEN") or
    "8821130913:AAHL-oB8ZVAHU95QguFC3I7kxVT5XaaOaWc"
)
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def build_main_keyboard() -> InlineKeyboardMarkup:
    """Creates interactive Telegram inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Holdings Summary", callback_data="btn_holdings"),
            InlineKeyboardButton("🎯 Recommendations", callback_data="btn_recommendations")
        ],
        [
            InlineKeyboardButton("🔄 Capital Recycling", callback_data="btn_recycle"),
            InlineKeyboardButton("📈 Full Scan", callback_data="btn_scan")
        ],
        [
            InlineKeyboardButton("⚙️ System Status", callback_data="btn_status")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start and /menu commands."""
    welcome_text = (
        "📈 *Manage-Dhan-Portfolio Advisor* 🤖\n"
        "--------------------------------------\n"
        "Welcome! I am your autonomous Dhan Portfolio Swing Trade Manager.\n\n"
        "🔒 *Strict Paper Trading Guarantee*: No real trades are executed. All recommendations & recycling plans operate in simulated paper mode.\n\n"
        "Use the buttons below or commands:\n"
        "• /analyze - Run full technical scan\n"
        "• /recommendations - View SELL / AVERAGE / HOLD signals\n"
        "• /recycle - View Capital Recycling Plan\n"
        "• /summary - Executive Portfolio Overview"
    )
    if update.message:
        await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=build_main_keyboard())

async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /summary command."""
    await process_summary_request(update.effective_message)

async def process_summary_request(message):
    holdings, summary = portfolio_analyzer.analyze_full_dhan_portfolio()
    pnl_symbol = "🟢" if summary["totalPnL"] >= 0 else "🔴"
    
    text = (
        "📊 *Dhan Portfolio Summary Overview*\n"
        "--------------------------------------\n"
        f"• *Total Holdings*: `{summary['totalHoldings']}`\n"
        f"• *Total Investment*: `₹{summary['totalInvestment']:,.2f}`\n"
        f"• *Current Value*: `₹{summary['totalCurrentValue']:,.2f}`\n"
        f"• *Total P&L*: {pnl_symbol} `₹{summary['totalPnL']:,.2f}` (`{summary['totalPnLPercentage']:+.2f}%`)\n\n"
        f"🎯 *Recommendation Signals*:\n"
        f"• 🔴 *SELL (Exit)*: `{summary['sellCount']}`\n"
        f"• 🟢 *AVERAGE (Add)*: `{summary['averageCount']}`\n"
        f"• 🟡 *HOLD*: `{summary['holdCount']}`\n\n"
        f"💰 *Freed Capital Potential*: `₹{summary['capitalRecycling']['totalFreedCapital']:,.2f}`"
    )
    await message.reply_text(text, parse_mode="Markdown", reply_markup=build_main_keyboard())

async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /analyze command."""
    await process_scan_request(update.effective_message)

async def process_scan_request(message):
    wait_msg = await message.reply_text("🔄 *Scanning Dhan portfolio technicals... Please wait.*", parse_mode="Markdown")
    holdings, summary = portfolio_analyzer.analyze_full_dhan_portfolio()
    portfolio_manager.sync_analysis_to_sheets(holdings, summary)
    
    msg_lines = [
        "📈 *Technical Analysis Report*",
        "--------------------------------------"
    ]
    for h in holdings:
        rec_emoji = "🔴" if h["recommendation"] == "SELL" else ("🟢" if h["recommendation"] == "AVERAGE" else "🟡")
        msg_lines.append(
            f"{rec_emoji} *{h['tradingSymbol']}* ({h['type']})\n"
            f"   • Qty: `{h['qty']}` | Buy: `₹{h['buyPrice']:,.2f}` | LTP: `₹{h['ltp']:,.2f}`\n"
            f"   • P&L: `₹{h['pnl']:,.2f}` (`{h['pnlPercentage']:+.2f}%`)\n"
            f"   • Signal: *{h['recommendation']}* | RSI: `{h.get('rsi14', 'N/A')}`\n"
            f"   • Target: `₹{h['targetPrice']:,.2f}` | SL: `₹{h['stopLoss']:,.2f}`\n"
            f"   • Rationale: _{' '.join(h['rationale'])}_\n"
        )
        
    full_text = "\n".join(msg_lines)
    if len(full_text) > 4000:
        chunks = [full_text[i:i+3800] for i in range(0, len(full_text), 3800)]
        for chunk in chunks:
            await message.reply_text(chunk, parse_mode="Markdown")
    else:
        await wait_msg.edit_text(full_text, parse_mode="Markdown", reply_markup=build_main_keyboard())

async def cmd_recommendations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /recommendations command."""
    await process_recommendations_request(update.effective_message)

async def process_recommendations_request(message):
    holdings, summary = portfolio_analyzer.analyze_full_dhan_portfolio()
    
    sells = [h for h in holdings if h["recommendation"] == "SELL"]
    averages = [h for h in holdings if h["recommendation"] == "AVERAGE"]
    holds = [h for h in holdings if h["recommendation"] == "HOLD"]
    
    lines = ["🎯 *Actionable Swing Trade Recommendations*\n--------------------------------------"]
    
    if sells:
        lines.append("\n🔴 *SELL RECOMMENDATIONS (Capital Release)*:")
        for s in sells:
            lines.append(
                f"• *{s['tradingSymbol']}*: Sell {s['qty']} @ `₹{s['ltp']:,.2f}` | Value: `₹{s['currentValue']:,.2f}`\n"
                f"  _Reason_: {' '.join(s['rationale'])}"
            )
    else:
        lines.append("\n🔴 *SELL RECOMMENDATIONS*: None (No exit signals).")
        
    if averages:
        lines.append("\n🟢 *AVERAGE / ACCUMULATE RECOMMENDATIONS*:")
        for a in averages:
            lines.append(
                f"• *{a['tradingSymbol']}*: Add position @ `₹{a['ltp']:,.2f}` | Target: `₹{a['targetPrice']:,.2f}` | SL: `₹{a['stopLoss']:,.2f}` (R:R {a['riskReward']})\n"
                f"  _Reason_: {' '.join(a['rationale'])}"
            )
    else:
        lines.append("\n🟢 *AVERAGE RECOMMENDATIONS*: None (No pullback buying setups).")
        
    if holds:
        lines.append(f"\n🟡 *HOLD*: {len(holds)} positions maintaining healthy trend structure.")
        
    full_text = "\n".join(lines)
    await message.reply_text(full_text, parse_mode="Markdown", reply_markup=build_main_keyboard())

async def cmd_recycle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /recycle command."""
    await process_recycle_request(update.effective_message)

async def process_recycle_request(message):
    holdings, summary = portfolio_analyzer.analyze_full_dhan_portfolio()
    cr = summary["capitalRecycling"]
    
    text = (
        "🔄 *Capital Recycling Allocation Plan*\n"
        "--------------------------------------\n"
        f"• *Total Liquid Capital to Release*: `₹{cr['totalFreedCapital']:,.2f}`\n\n"
        "📊 *Recommended Deployment Split*:\n"
        f"1. 🚀 *Strategy 1 (Mid-Cap Swing - 30%)*: `₹{cr['strategy1_midcap']:,.2f}`\n"
        f"2. 🏢 *Strategy 2 (Sector Swing - 30%)*: `₹{cr['strategy2_sector']:,.2f}`\n"
        f"3. ⚡ *Strategy 3 (Momentum Swing - 20%)*: `₹{cr['strategy3_momentum']:,.2f}`\n"
        f"4. 🛡️ *ETF Strategy (Low-Beta - 20%)*: `₹{cr['etf_strategy']:,.2f}`\n\n"
        "ℹ️ *Note*: Rebalancing is tracked in Paper Trading Mode. Once paper exits are executed in the dashboard, funds update dynamically."
    )
    await message.reply_text(text, parse_mode="Markdown", reply_markup=build_main_keyboard())

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline keyboard button clicks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "btn_holdings":
        await process_summary_request(query.message)
    elif data == "btn_recommendations":
        await process_recommendations_request(query.message)
    elif data == "btn_recycle":
        await process_recycle_request(query.message)
    elif data == "btn_scan":
        await process_scan_request(query.message)
    elif data == "btn_status":
        dhan_status = "🟢 Configured" if dhan_client.is_dhan_configured() else "🟡 Offline / Sample Mode"
        sheets_status = "🟢 Active" if portfolio_manager.get_gspread_client() else "🟡 Unconfigured"
        status_text = (
            "⚙️ *System Health & Authentication Status*\n"
            "--------------------------------------\n"
            f"• *Dhan API Connection*: {dhan_status}\n"
            f"• *Google Sheets Sync*: {sheets_status}\n"
            f"• *Mode*: `Paper Trading Only` (Zero execution risk)\n"
            f"• *System Time*: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        await query.message.reply_text(status_text, parse_mode="Markdown", reply_markup=build_main_keyboard())

async def setup_bot_commands(application: Application):
    """Registers bot slash commands menu."""
    commands = [
        BotCommand("start", "Launch main menu"),
        BotCommand("menu", "Launch main menu"),
        BotCommand("analyze", "Run full portfolio scan"),
        BotCommand("recommendations", "View SELL/AVERAGE/HOLD signals"),
        BotCommand("recycle", "View Capital Recycling plan"),
        BotCommand("summary", "Portfolio performance summary")
    ]
    await application.bot.set_my_commands(commands)

def main():
    """Main Telegram bot runner."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("No Telegram Bot Token available. Exiting.")
        sys.exit(1)
        
    logger.info("Starting Manage-Dhan-Portfolio Telegram Bot...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(setup_bot_commands).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_start))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("recommendations", cmd_recommendations))
    app.add_handler(CommandHandler("recycle", cmd_recycle))
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

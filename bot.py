import os
import sys
import time
import datetime
import logging
from logging.handlers import RotatingFileHandler
import asyncio
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

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

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SAVED_CHAT_ID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cached_chat_id.txt")
ALERTED_SIGNALS = {}

def save_chat_id(chat_id: int):
    """Saves active Telegram Chat ID for automated market alert notifications."""
    try:
        with open(SAVED_CHAT_ID_FILE, "w", encoding="utf-8") as f:
            f.write(str(chat_id))
    except Exception as e:
        logger.error(f"Error saving chat ID: {e}")

def get_saved_chat_id() -> Optional[int]:
    """Retrieves saved Telegram Chat ID."""
    env_cid = os.environ.get("TELEGRAM_CHAT_ID")
    if env_cid:
        try:
            return int(env_cid)
        except ValueError:
            pass
    if os.path.exists(SAVED_CHAT_ID_FILE):
        try:
            with open(SAVED_CHAT_ID_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return int(content)
        except Exception:
            pass
    return None

def is_nse_market_hours() -> bool:
    """Checks if current time is within NSE market hours (Mon-Fri 09:15 to 15:30 IST)."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_ist = now_utc.astimezone(ist_tz)
    
    if now_ist.weekday() >= 5:
        return False
        
    start_time = datetime.time(9, 15)
    end_time = datetime.time(15, 30)
    current_time = now_ist.time()
    
    return start_time <= current_time <= end_time

async def market_hours_monitor_task(application: Application):
    """
    Background worker task running every 15 minutes during NSE market hours.
    Scans portfolio, evaluates signals, and sends spontaneous Telegram alerts.
    """
    logger.info("Market hours monitor background task initialized.")
    while True:
        try:
            await asyncio.sleep(900)
            
            if not is_nse_market_hours():
                continue
                
            chat_id = get_saved_chat_id()
            if not chat_id:
                logger.info("Market monitor active, but no chat ID saved yet. Waiting for user interaction.")
                continue
                
            logger.info("NSE Market Hours active. Running 15-minute background portfolio scan...")
            holdings, summary = portfolio_analyzer.analyze_full_dhan_portfolio()
            portfolio_manager.sync_analysis_to_sheets(holdings, summary)
            
            urgent_signals = [h for h in holdings if h["recommendation"] in ["SELL", "AVERAGE"]]
            
            new_alerts = []
            now_ts = time.time()
            
            for s in urgent_signals:
                sym = s["tradingSymbol"]
                rec = s["recommendation"]
                key = f"{sym}_{rec}"
                
                last_alerted = ALERTED_SIGNALS.get(key, 0)
                if now_ts - last_alerted > 14400:
                    ALERTED_SIGNALS[key] = now_ts
                    new_alerts.append(s)
                    
            if new_alerts:
                sells = [h for h in new_alerts if h["recommendation"] == "SELL"]
                averages = [h for h in new_alerts if h["recommendation"] == "AVERAGE"]
                
                lines = [
                    "🔔 *AUTOMATED MARKET HOURS ALERT* 📈",
                    "--------------------------------------",
                    f"⏰ *Scan Time*: `{datetime.datetime.now().strftime('%H:%M IST')}`\n"
                ]
                
                if sells:
                    lines.append(f"🔴 *URGENT SELL EXIT SIGNALS ({len(sells)})*:")
                    for s in sells:
                        lines.append(
                            f"• *{s['tradingSymbol']}*: Sell {s['qty']} @ `₹{s['ltp']:,.2f}`\n"
                            f"  _Reason_: {' '.join(s['rationale'])}\n"
                        )
                        
                if averages:
                    lines.append(f"🟢 *ACCUMULATE / AVERAGE SIGNALS ({len(averages)})*:")
                    for a in averages:
                        lines.append(
                            f"• *{a['tradingSymbol']}*: Add @ `₹{a['ltp']:,.2f}` | Target: `₹{a['targetPrice']:,.2f}`\n"
                            f"  _Reason_: {' '.join(a['rationale'])}\n"
                        )
                        
                full_text = "\n".join(lines)
                
                exec_buttons = []
                for s in sells[:4]:
                    sym = s["tradingSymbol"]
                    qty = int(s["qty"])
                    ltp = s["ltp"]
                    exec_buttons.append([InlineKeyboardButton(f"⚡ Execute SELL {qty} {sym} @ ₹{ltp:,.2f}", callback_data=f"ord_ask|SELL|{sym}|{qty}|{ltp:.2f}")])
                for a in averages[:3]:
                    sym = a["tradingSymbol"]
                    qty = int(a["qty"])
                    ltp = a["ltp"]
                    exec_buttons.append([InlineKeyboardButton(f"⚡ Execute BUY {qty} {sym} @ ₹{ltp:,.2f}", callback_data=f"ord_ask|BUY|{sym}|{qty}|{ltp:.2f}")])
                    
                main_kb = [list(row) for row in build_main_keyboard().inline_keyboard]
                combined_kb = InlineKeyboardMarkup(exec_buttons + main_kb)
                
                try:
                    await application.bot.send_message(
                        chat_id=chat_id,
                        text=full_text,
                        parse_mode="Markdown",
                        reply_markup=combined_kb,
                        disable_web_page_preview=True
                    )
                    logger.info(f"Pushed automated market hours alert for {len(new_alerts)} signals to chat {chat_id}.")
                except Exception as send_err:
                    logger.error(f"Failed to push market alert to Telegram: {send_err}")
                    
        except Exception as e:
            logger.error(f"Error in market hours monitor task: {e}")

def build_main_keyboard() -> InlineKeyboardMarkup:
    """Creates interactive Telegram inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Portfolio Summary", callback_data="btn_holdings"),
            InlineKeyboardButton("⚡ Rebalance Signals", callback_data="btn_recommendations")
        ],
        [
            InlineKeyboardButton("🔄 Capital Recycling", callback_data="btn_recycle"),
            InlineKeyboardButton("📈 Full Technical Scan", callback_data="btn_scan")
        ],
        [
            InlineKeyboardButton("🔑 Renew Dhan Token", callback_data="btn_renew"),
            InlineKeyboardButton("⚙️ System Status", callback_data="btn_status")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def send_chunked_message(message, text: str, reply_markup=None, parse_mode="Markdown"):
    """Safely sends long text messages split into Telegram's <= 4000 character chunks."""
    max_len = 3800
    if len(text) <= max_len:
        try:
            return await message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup, disable_web_page_preview=True)
        except Exception:
            return await message.reply_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
    
    lines = text.split("\n")
    chunks = []
    current_chunk = []
    current_len = 0
    
    for line in lines:
        if current_len + len(line) + 1 > max_len:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_len = len(line) + 1
        else:
            current_chunk.append(line)
            current_len += len(line) + 1
            
    if current_chunk:
        chunks.append("\n".join(current_chunk))
        
    for i, chunk in enumerate(chunks):
        markup = reply_markup if i == len(chunks) - 1 else None
        try:
            await message.reply_text(chunk, parse_mode=parse_mode, reply_markup=markup, disable_web_page_preview=True)
        except Exception:
            await message.reply_text(chunk, reply_markup=markup, disable_web_page_preview=True)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start and /menu commands."""
    if update and update.effective_chat:
        save_chat_id(update.effective_chat.id)
    welcome_text = (
        "📈 *Manage-Dhan-Portfolio Advisor* 🤖\n"
        "--------------------------------------\n"
        "Welcome! I am your autonomous Dhan Portfolio Swing Trade Manager.\n\n"
        "⚡ *1-Click Dhan Order Execution*: Use inline buttons to submit orders directly to Dhan with automatic TOTP authentication.\n"
        "🔔 *Automated Market-Hours Alerts*: Continuously scans live prices (Mon-Fri 09:15-15:30 IST) & pushes instant Telegram alerts!\n\n"
        "Use the menu below or slash commands:\n"
        "• /portfolio - Executive Portfolio Overview\n"
        "• /rebalance - Actionable SELL / AVERAGE signals + 1-Click Order Buttons\n"
        "• /recycle - View Capital Recycling Allocation Plan\n"
        "• /analyze - Run full 30-position technical scan\n"
        "• /renew - Check/Renew Dhan Access Token\n"
        "• /status - System Health & Data Engine Status"
    )
    if update.message:
        await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=build_main_keyboard())

async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /portfolio, /summary, and /holdings commands."""
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
    """Handler for /analyze and /scan commands."""
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
    try:
        await wait_msg.delete()
    except Exception:
        pass
    await send_chunked_message(message, full_text, reply_markup=build_main_keyboard())

async def cmd_recommendations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /rebalance and /recommendations commands."""
    await process_recommendations_request(update.effective_message)

async def process_recommendations_request(message):
    holdings, summary = portfolio_analyzer.analyze_full_dhan_portfolio()
    
    sells = [h for h in holdings if h["recommendation"] == "SELL"]
    averages = [h for h in holdings if h["recommendation"] == "AVERAGE"]
    holds = [h for h in holdings if h["recommendation"] == "HOLD"]
    
    lines = ["🎯 *Actionable Swing Trade Recommendations*\n--------------------------------------"]
    
    if sells:
        lines.append(f"\n🔴 *SELL RECOMMENDATIONS ({len(sells)} Positions - Capital Release)*:")
        for s in sells:
            lines.append(
                f"• *{s['tradingSymbol']}*: Sell {s['qty']} @ `₹{s['ltp']:,.2f}` | Value: `₹{s['currentValue']:,.2f}`\n"
                f"  _Reason_: {' '.join(s['rationale'])}\n"
            )
    else:
        lines.append("\n🔴 *SELL RECOMMENDATIONS*: None (No exit signals).")
        
    if averages:
        lines.append(f"\n🟢 *AVERAGE / ACCUMULATE RECOMMENDATIONS ({len(averages)} Positions)*:")
        for a in averages:
            lines.append(
                f"• *{a['tradingSymbol']}*: Add position @ `₹{a['ltp']:,.2f}` | Target: `₹{a['targetPrice']:,.2f}` | SL: `₹{a['stopLoss']:,.2f}` (R:R {a['riskReward']})\n"
                f"  _Reason_: {' '.join(a['rationale'])}\n"
            )
    else:
        lines.append("\n🟢 *AVERAGE RECOMMENDATIONS*: None (No pullback buying setups).")
        
    if holds:
        lines.append(f"\n🟡 *HOLD*: {len(holds)} positions maintaining healthy trend structure.")
        
    full_text = "\n".join(lines)
    
    # Build inline execution buttons for active signals
    exec_buttons = []
    for s in sells[:6]:
        sym = s["tradingSymbol"]
        qty = int(s["qty"])
        ltp = s["ltp"]
        exec_buttons.append([InlineKeyboardButton(f"⚡ Execute SELL {qty} {sym} @ ₹{ltp:,.2f}", callback_data=f"ord_ask|SELL|{sym}|{qty}|{ltp:.2f}")])
    for a in averages[:4]:
        sym = a["tradingSymbol"]
        qty = int(a["qty"])
        ltp = a["ltp"]
        exec_buttons.append([InlineKeyboardButton(f"⚡ Execute BUY {qty} {sym} @ ₹{ltp:,.2f}", callback_data=f"ord_ask|BUY|{sym}|{qty}|{ltp:.2f}")])
        
    main_kb = [list(row) for row in build_main_keyboard().inline_keyboard]
    combined_kb = InlineKeyboardMarkup(exec_buttons + main_kb)
    
    await send_chunked_message(message, full_text, reply_markup=combined_kb)

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

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /status command."""
    await process_status_request(update.effective_message)

async def process_status_request(message):
    dhan_status = "🟢 DhanHQ (Live Broker Feed)"
    sheets_status = "🟢 Active" if portfolio_manager.get_gspread_client() else "🟡 Unconfigured"
    status_text = (
        "⚙️ *System Health & Data Engine Status*\n"
        "--------------------------------------\n"
        f"📡 *Data Engine*: {dhan_status}\n"
        f"📊 *Google Sheets Sync*: {sheets_status}\n"
        f"🔔 *Market Alert Engine*: 🟢 Active (Mon-Fri 09:15-15:30 IST)\n"
        f"⚡ *Execution Engine*: `1-Click Dhan API (TOTP Auto-Auth)`\n"
        f"🕒 *System Time*: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
    )
    await message.reply_text(status_text, parse_mode="Markdown", reply_markup=build_main_keyboard())

async def cmd_renew(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /renew command."""
    await process_renew_request(update.effective_message)

async def process_renew_request(message):
    wait_msg = await message.reply_text("🔑 *Verifying Dhan API Access Token...*", parse_mode="Markdown")
    
    client = dhan_client.get_dhan_client()
    is_live = False
    holdings = []
    if client:
        try:
            resp = client.get_holdings()
            if isinstance(resp, dict) and resp.get("status") == "success":
                is_live = True
                holdings = dhan_client.get_dhan_holdings()
        except Exception:
            is_live = False
            
    if is_live:
        await wait_msg.edit_text(
            f"🟢 *Dhan API Connection is Active & Verified!*\n"
            f"--------------------------------------\n"
            f"• *Status*: `Active (24-Hour Token Valid)`\n"
            f"• *Live Holdings Retrieved*: `{len(holdings)}` positions\n"
            f"• *Account Client ID*: `1101177354`\n\n"
            f"Your Telegram bot and Streamlit Web Dashboard are actively processing your live Dhan portfolio.",
            parse_mode="Markdown",
            reply_markup=build_main_keyboard()
        )
    else:
        new_token = dhan_client.renew_access_token_via_totp()
        if new_token:
            fresh_holdings = dhan_client.get_dhan_holdings()
            await wait_msg.edit_text(
                f"🟢 *Dhan Access Token Renewed Successfully!*\n"
                f"--------------------------------------\n"
                f"• *Status*: `Active (Valid 24 Hours)`\n"
                f"• *Live Holdings Retrieved*: `{len(fresh_holdings)}` positions\n\n"
                f"Your Telegram bot and Web dashboard are fully synced with live Dhan data.",
                parse_mode="Markdown",
                reply_markup=build_main_keyboard()
            )
        else:
            await wait_msg.edit_text(
                "🔴 *Dhan token is currently expired.* To renew:\n\n"
                "1. Open [web.dhan.co](https://web.dhan.co) → **My Profile** → **DhanHQ Trading API**.\n"
                "2. Click **Generate Access Token** (PIN `2317` + TOTP).\n"
                "3. Send the new token here in chat to refresh instantly.",
                parse_mode="Markdown",
                reply_markup=build_main_keyboard()
            )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline keyboard button clicks."""
    query = update.callback_query
    if query and query.message and query.message.chat:
        save_chat_id(query.message.chat.id)
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
    elif data == "btn_renew":
        await process_renew_request(query.message)
    elif data == "btn_status":
        await process_status_request(query.message)
    elif data.startswith("ord_ask|"):
        _, act, sym, qty, price = data.split("|")
        total_val = float(qty) * float(price)
        confirm_text = (
            f"⚠️ *Confirm Real-Money Dhan Order Execution* ⚠️\n"
            f"--------------------------------------\n"
            f"• *Symbol*: `{sym}`\n"
            f"• *Action*: *{act}*\n"
            f"• *Quantity*: `{qty}` shares\n"
            f"• *Market LTP*: `₹{float(price):,.2f}`\n"
            f"• *Estimated Order Value*: `₹{total_val:,.2f}`\n\n"
            f"Do you want to submit this order directly to your Dhan account now?"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"✅ Confirm {act} {sym}", callback_data=f"ord_exec|{act}|{sym}|{qty}|{price}"),
                InlineKeyboardButton("❌ Cancel", callback_data="ord_cancel")
            ]
        ])
        await query.message.reply_text(confirm_text, parse_mode="Markdown", reply_markup=kb)
    elif data.startswith("ord_exec|"):
        _, act, sym, qty, price = data.split("|")
        await query.edit_message_text(f"⏳ *Submitting {act} order for {qty} {sym} to Dhan HQ API...*", parse_mode="Markdown")
        res = dhan_client.place_dhan_order(sym, act, float(qty), float(price))
        
        status = res.get("status") or res.get("orderStatus") or "COMPLETED"
        order_id = res.get("orderId") or (res.get("data", {}) if isinstance(res.get("data"), dict) else {}).get("orderId") or res.get("data") or "EXECUTED"
        remarks = res.get("remarks") or res.get("data") or "Order placed successfully."
        
        if status in ["success", "SUCCESS", "TRADED", "PENDING"]:
            result_text = (
                f"✅ *Dhan Order Placed Successfully!*\n"
                f"--------------------------------------\n"
                f"• *Symbol*: `{sym}`\n"
                f"• *Action*: `{act}`\n"
                f"• *Quantity*: `{qty}`\n"
                f"• *Order ID*: `{order_id}`\n"
                f"• *Status*: `{status}`\n\n"
                f"Track live order execution in your Dhan App or on [web.dhan.co](https://web.dhan.co)."
            )
        elif "DH-905" in str(res) or "Invalid IP" in str(remarks) or res.get("error_code") == "DH-905":
            result_text = (
                f"⚠️ *Dhan API 7-Day IP Cooldown Active*\n"
                f"--------------------------------------\n"
                f"• *Symbol*: `{sym}` | *Action*: `{act}` | *Qty*: `{qty}`\n\n"
                f"Your Dhan account currently has a 7-day IP reset cooldown.\n"
                f"👉 You can review and place this trade directly on [web.dhan.co](https://web.dhan.co) or in your Dhan Mobile App!"
            )
        else:
            result_text = (
                f"🔴 *Dhan Order Response*\n"
                f"--------------------------------------\n"
                f"• *Symbol*: `{sym}`\n"
                f"• *Status*: `{status}`\n"
                f"• *Details*: `{remarks}`"
            )
        await query.edit_message_text(result_text, parse_mode="Markdown", reply_markup=build_main_keyboard(), disable_web_page_preview=True)
    elif data == "ord_cancel":
        await query.edit_message_text("❌ *Order execution cancelled. No real trades were placed.*", parse_mode="Markdown", reply_markup=build_main_keyboard())

async def setup_bot_commands(application: Application):
    """Registers bot slash commands menu and launches background market monitor."""
    commands = [
        BotCommand("start", "Launch main menu"),
        BotCommand("portfolio", "Executive portfolio overview"),
        BotCommand("rebalance", "Actionable SELL / AVERAGE signals"),
        BotCommand("recycle", "Capital Recycling allocation plan"),
        BotCommand("analyze", "Run 30-position technical scan"),
        BotCommand("renew", "Verify/Renew Dhan access token"),
        BotCommand("status", "System health & engine status"),
    ]
    await application.bot.set_my_commands(commands)
    asyncio.create_task(market_hours_monitor_task(application))

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles pasted token text messages in Telegram chat."""
    text = (update.message.text or "").strip()
    if text.startswith("eyJ") and len(text) > 80:
        wait_msg = await update.message.reply_text("🔑 *Updating Dhan Access Token...*", parse_mode="Markdown")
        dhan_client._update_env_file("DHAN_ACCESS_TOKEN", text)
        os.environ["DHAN_ACCESS_TOKEN"] = text
        dhan_client._DHAN_INSTANCE = None
        
        client = dhan_client.get_dhan_client()
        is_live = False
        if client:
            try:
                resp = client.get_holdings()
                if isinstance(resp, dict) and resp.get("status") == "success":
                    is_live = True
            except Exception:
                is_live = False
                
        if is_live:
            holdings = dhan_client.get_dhan_holdings()
            await wait_msg.edit_text(
                f"🟢 *Dhan Access Token Updated & Verified via Telegram!*\n"
                f"--------------------------------------\n"
                f"• *Status*: `Active (Valid 24 Hours)`\n"
                f"• *Live Holdings Retrieved*: `{len(holdings)}` positions\n\n"
                f"Your Telegram bot and Streamlit Web Dashboard are fully synced with live Dhan data.",
                parse_mode="Markdown",
                reply_markup=build_main_keyboard()
            )
        else:
            await wait_msg.edit_text(
                "🔴 *Token updated, but Dhan API returned error or fallback.* Please check token string.",
                parse_mode="Markdown",
                reply_markup=build_main_keyboard()
            )

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs errors and notifies user gracefully instead of failing silently."""
    logger.error(f"Exception while handling update: {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ *Temporary error processing command.* Please try again or tap /start to refresh menu.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

def main():
    """Main Telegram bot runner."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("No Telegram Bot Token available. Exiting.")
        sys.exit(1)
        
    logger.info("Starting Manage-Dhan-Portfolio Telegram Bot...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(setup_bot_commands).build()
    
    app.add_handler(CommandHandler(["start", "menu"], cmd_start))
    app.add_handler(CommandHandler(["portfolio", "summary", "holdings"], cmd_summary))
    app.add_handler(CommandHandler(["rebalance", "recommendations"], cmd_recommendations))
    app.add_handler(CommandHandler("recycle", cmd_recycle))
    app.add_handler(CommandHandler(["analyze", "scan"], cmd_analyze))
    app.add_handler(CommandHandler("renew", cmd_renew))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    app.add_error_handler(global_error_handler)
    
    app.run_polling(drop_pending_updates=False)

if __name__ == "__main__":
    main()

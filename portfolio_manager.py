import os
import gc
import json
import gspread
import math
import time
import pandas as pd
import yfinance as yf
from datetime import datetime, time, date
import sentiment_analyzer
import dhan_client
import screener
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any, Tuple

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

def retry_gspread(func, *args, **kwargs):
    """
    Executes a gspread operation with automatic 2-second sleep retry on 429 rate limits.
    """
    for i in range(3):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                time.sleep(2)
            else:
                raise e
    return func(*args, **kwargs)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_gspread_client() -> gspread.Client:
    """
    Creates and returns a gspread client using environment variables or a local key file.
    """
    env_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if env_json:
        try:
            s = env_json.strip()
            if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
                s = s[1:-1].strip()
            info = json.loads(s)
            if "private_key" in info and "\\n" in info["private_key"]:
                info["private_key"] = info["private_key"].replace("\\n", "\n")
            print(f"Loaded service account key_id: {info.get('private_key_id')}")
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            print(f"Error parsing GOOGLE_SERVICE_ACCOUNT_JSON from environment: {e}")
            
    local_path = "service_account.json"
    if os.path.exists(local_path):
        try:
            creds = Credentials.from_service_account_file(local_path, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            print(f"Error reading local service_account.json: {e}")
            
    raise ValueError("Google Service Account credentials not found in env var or local file.")

DEFAULT_SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "NSE_Swing_Trading_Portfolio_2")

def get_worksheet_names(sh: gspread.Spreadsheet) -> Tuple[str, str, str]:
    """
    Returns (holdings_tab_name, account_tab_name, chats_tab_name) based on sheet title.
    If using dedicated sheet 'NSE_Swing_Trading_Portfolio_2', uses ('Holdings', 'Account', 'TelegramChats').
    If fallback to shared sheet 'NSE_Swing_Trading_Portfolio', uses ('Holdings_v2', 'Account_v2', 'TelegramChats_v2').
    """
    if "2" in sh.title:
        return ("Holdings", "Account", "TelegramChats")
    return ("Holdings_v2", "Account_v2", "TelegramChats_v2")

def get_or_create_portfolio_sheet(client: gspread.Client, sheet_name: str = None) -> gspread.Spreadsheet:
    """
    Opens the spreadsheet by name, or falls back to the shared portfolio with _v2 tabs.
    """
    target_name = sheet_name or os.environ.get("SPREADSHEET_NAME", DEFAULT_SPREADSHEET_NAME)
    try:
        sh = client.open(target_name)
    except Exception:
        # Fallback to shared main spreadsheet
        try:
            sh = client.open("NSE_Swing_Trading_Portfolio")
            print(f"Notice: Using shared Google Sheet 'NSE_Swing_Trading_Portfolio' with dedicated Strategy #2 worksheets.")
        except Exception as e:
            raise ValueError(f"Could not open Google Sheets database: {e}")
        
    holdings_name, account_name, chats_name = get_worksheet_names(sh)
    
    # Check/Create Holdings sheet
    try:
        holdings_ws = sh.worksheet(holdings_name)
    except gspread.WorksheetNotFound:
        holdings_ws = sh.add_worksheet(title=holdings_name, rows="1000", cols="14")
        headers = [
            "Ticker", "Entry Date", "Entry Price", "Quantity", "Entry Value",
            "Initial SL", "Current SL", "Target", "Status", "Exit Date", 
            "Exit Price", "Exit Value", "PnL", "Exit Reason"
        ]
        holdings_ws.append_row(headers)
        
    # Check/Create Account sheet
    try:
        sh.worksheet(account_name)
    except gspread.WorksheetNotFound:
        account_ws = sh.add_worksheet(title=account_name, rows="100", cols="2")
        account_ws.append_row(["Parameter", "Value"])
        account_ws.append_row(["Total Portfolio Value", "1000000"])
        account_ws.append_row(["Cash Balance", "1000000"])
        account_ws.append_row(["Risk Percent", "0.015"])
        account_ws.append_row(["Initial Capital", "1000000"])
        
    # Check/Create TelegramChats sheet
    try:
        sh.worksheet(chats_name)
    except gspread.WorksheetNotFound:
        chats_ws = sh.add_worksheet(title=chats_name, rows="100", cols="1")
        chats_ws.append_row(["ChatID"])
        
    # Check/Create Schedules sheet
    get_schedules_worksheet(sh)
        
    return sh

def get_schedules_tab_name(sh: gspread.Spreadsheet) -> str:
    """
    Returns the appropriate schedules tab name ('Schedules' or 'Schedules_v2').
    """
    if "2" in sh.title:
        return "Schedules"
    return "Schedules_v2"

def get_schedules_worksheet(sh: gspread.Spreadsheet) -> gspread.Worksheet:
    """
    Returns the 'Schedules' worksheet, creating it with headers and initial templates if not found.
    """
    sched_name = get_schedules_tab_name(sh)
    try:
        ws = sh.worksheet(sched_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sched_name, rows="100", cols="6")
        headers = ["Date", "Time", "Mode", "Status", "Last Run", "Notes"]
        ws.append_row(headers)
        ws.append_row(["DAILY", "08:00", "PREVIEW", "ACTIVE", "", "Morning Pre-Market Scan"])
        ws.append_row(["DAILY", "09:00", "SENTIMENT", "PAUSED", "", "Nifty 50 Market Sentiment Briefing"])
        ws.append_row(["DAILY", "15:25", "EXECUTE", "ACTIVE", "", "Daily Market Close Scan"])
        ws.append_row(["TODAY", "18:00", "EXECUTE", "PAUSED", "", "Sample Custom One-Time Scan"])
    return ws

def get_pending_schedules(sh: gspread.Spreadsheet) -> List[Dict[str, Any]]:
    """
    Fetches all schedules from the 'Schedules' worksheet and returns rows eligible for execution.
    """
    try:
        ws = get_schedules_worksheet(sh)
        records = retry_gspread(ws.get_all_records)
        items = []
        for idx, r in enumerate(records):
            status = str(r.get("Status", "")).strip().upper()
            if status not in ("PENDING", "ACTIVE", "SCHEDULED"):
                continue
            items.append({
                "row_idx": idx + 2,
                "date": str(r.get("Date", "")).strip(),
                "time": str(r.get("Time", "")).strip(),
                "mode": str(r.get("Mode", "EXECUTE")).strip().upper(),
                "status": status,
                "last_run": str(r.get("Last Run", "")).strip(),
                "notes": str(r.get("Notes", "")).strip()
            })
        return items
    except Exception as e:
        print(f"Error fetching pending schedules: {e}")
        return []

def update_schedule_status(sh: gspread.Spreadsheet, row_idx: int, status: str, last_run: str = None):
    """
    Updates the Status (col 4) and optionally Last Run (col 5) in the Schedules worksheet.
    """
    try:
        ws = get_schedules_worksheet(sh)
        retry_gspread(ws.update_cell, row_idx, 4, status)
        if last_run is not None:
            retry_gspread(ws.update_cell, row_idx, 5, last_run)
    except Exception as e:
        print(f"Error updating schedule status row {row_idx}: {e}")

def log_cloud_event(sh: gspread.Spreadsheet, source: str, message: str):
    """
    Records diagnostic cloud runtime events into the 'DebugLogs' worksheet.
    """
    try:
        log_tab = "DebugLogs"
        try:
            ws = sh.worksheet(log_tab)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=log_tab, rows="500", cols="3")
            ws.append_row(["Timestamp IST", "Source", "Message"])
        tz = pytz.timezone("Asia/Kolkata")
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        retry_gspread(ws.append_row, [now_str, source, message])
    except Exception as e:
        print(f"Error writing cloud event log: {e}")

def is_schedule_due(item: Dict[str, Any], now_ist: datetime) -> bool:
    """
    Evaluates whether a schedule item is due to execute given current IST datetime.
    """
    date_val = item.get("date", "").strip().upper()
    time_val = item.get("time", "").strip()
    last_run = item.get("last_run", "").strip()
    today_str = now_ist.strftime("%Y-%m-%d")
    
    if not time_val:
        return False
        
    # Check if already executed today
    if last_run.startswith(today_str):
        return False
        
    # Evaluate Date condition
    date_matches = False
    is_recurring = date_val in ("DAILY", "WEEKDAYS", "WEEKDAY", "MON-FRI")
    if date_val in ("TODAY", ""):
        date_matches = True
    elif date_val == "DAILY":
        date_matches = True
    elif date_val in ("WEEKDAYS", "WEEKDAY", "MON-FRI"):
        date_matches = (now_ist.weekday() < 5)
    else:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                parsed_d = datetime.strptime(date_val, fmt).date()
                if parsed_d == now_ist.date():
                    date_matches = True
                    break
            except ValueError:
                pass
                
    if not date_matches:
        return False
        
    # Evaluate Time condition
    parsed_time = None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            parsed_time = datetime.strptime(time_val, fmt).time()
            break
        except ValueError:
            pass
            
    if not parsed_time:
        return False
        
    target_dt = now_ist.replace(
        hour=parsed_time.hour, 
        minute=parsed_time.minute, 
        second=0, 
        microsecond=0
    )
    diff_seconds = (now_ist - target_dt).total_seconds()
    
    # For one-time schedules (e.g. TODAY or specific date with PENDING status):
    # Due as soon as the target time has arrived (>= -60s), ensuring wake-up delays don't cause missed runs
    if not is_recurring:
        return diff_seconds >= -60
        
    # For recurring schedules (DAILY / WEEKDAYS):
    # Generous 30-minute grace window (-60s to +1800s)
    return -60 <= diff_seconds <= 1800

def get_account_details(sh: gspread.Spreadsheet) -> Dict[str, float]:
    """
    Retrieves the account details (Portfolio Value, Cash, Risk %, Initial Capital) from the Account sheet.
    Dynamically supports parameter aliases ('Risk Percent', 'Risk Percentage', 'Risk %') and formats.
    """
    _, account_name, _ = get_worksheet_names(sh)
    ws = sh.worksheet(account_name)
    records = ws.get_all_records()
    details = {}
    for r in records:
        param = str(r.get("Parameter", "")).strip()
        raw_val = str(r.get("Value", "")).strip().replace("%", "").replace(",", "")
        try:
            val = float(raw_val)
        except (ValueError, TypeError):
            continue
            
        norm_key = param.lower().replace(" ", "").replace("_", "")
        # Convert whole percentage like 5 or 7.5 to decimal 0.05 or 0.075
        if "risk" in norm_key and val > 1.0:
            val = val / 100.0
            
        details[param] = val
        if norm_key in ["riskpercent", "riskpercentage", "riskpct", "risk"]:
            details["Risk Percent"] = val
            details["Risk Percentage"] = val
        elif norm_key in ["totalportfoliovalue", "portfoliovalue"]:
            details["Total Portfolio Value"] = val
        elif norm_key in ["cashbalance", "cash"]:
            details["Cash Balance"] = val
        elif norm_key in ["initialcapital", "startingcapital"]:
            details["Initial Capital"] = val

    if "Initial Capital" not in details:
        details["Initial Capital"] = 100000.0
    if "Risk Percent" not in details:
        details["Risk Percent"] = 0.075
    if "Risk Percentage" not in details:
        details["Risk Percentage"] = details["Risk Percent"]
    return details

def update_account_details(sh: gspread.Spreadsheet, updates: Dict[str, float]):
    """
    Updates specific parameters in the Account worksheet while strictly preserving existing custom values.
    """
    _, account_name, _ = get_worksheet_names(sh)
    ws = sh.worksheet(account_name)
    records = ws.get_all_records()
    
    # Read existing values first so we never overwrite user configurations
    data = {
        "Total Portfolio Value": 100000.0, 
        "Cash Balance": 100000.0, 
        "Risk Percent": 0.075,
        "Initial Capital": 100000.0
    }
    risk_param_label = "Risk Percent"
    for r in records:
        param = str(r.get("Parameter", "")).strip()
        raw_val = str(r.get("Value", "")).strip().replace("%", "").replace(",", "")
        try:
            val = float(raw_val)
            norm_key = param.lower().replace(" ", "").replace("_", "")
            if "risk" in norm_key:
                risk_param_label = param
                if val > 1.0:
                    val = val / 100.0
                data["Risk Percent"] = val
            elif norm_key in ["totalportfoliovalue", "portfoliovalue"]:
                data["Total Portfolio Value"] = val
            elif norm_key in ["cashbalance", "cash"]:
                data["Cash Balance"] = val
            elif norm_key in ["initialcapital", "startingcapital"]:
                data["Initial Capital"] = val
        except Exception:
            pass
            
    for k, v in updates.items():
        norm_k = k.lower().replace(" ", "").replace("_", "")
        if "risk" in norm_k:
            v_float = float(v)
            if v_float > 1.0:
                v_float = v_float / 100.0
            data["Risk Percent"] = v_float
        elif norm_k in ["totalportfoliovalue", "portfoliovalue"]:
            data["Total Portfolio Value"] = float(v)
        elif norm_k in ["cashbalance", "cash"]:
            data["Cash Balance"] = float(v)
        elif norm_k in ["initialcapital", "startingcapital"]:
            data["Initial Capital"] = float(v)
            
    ws.update('A1:B5', [
        ["Parameter", "Value"],
        ["Total Portfolio Value", str(data["Total Portfolio Value"])],
        ["Cash Balance", str(data["Cash Balance"])],
        [risk_param_label, str(data["Risk Percent"])],
        ["Initial Capital", str(data["Initial Capital"])]
    ])

def get_all_holdings(sh: gspread.Spreadsheet) -> List[Dict[str, Any]]:
    """
    Returns all rows in the Holdings worksheet.
    """
    holdings_name, _, _ = get_worksheet_names(sh)
    ws = sh.worksheet(holdings_name)
    return ws.get_all_records()

def get_open_positions(sh: gspread.Spreadsheet) -> List[Dict[str, Any]]:
    """
    Returns only positions with Status == 'OPEN'.
    """
    holdings = get_all_holdings(sh)
    return [h for h in holdings if h["Status"] == "OPEN"]

def add_position(sh: gspread.Spreadsheet, ticker: str, entry_price: float, quantity: int, initial_sl: float, target: float) -> str:
    """
    Adds a new position to the Holdings worksheet and deducts cash.
    Enforces Strategy v2 guardrails: Double Buy Blocker, Sector Concentration (max 3/sector), and valid SL range.
    """
    open_positions = get_open_positions(sh)
    existing_tickers = [p["Ticker"] for p in open_positions]
    if ticker in existing_tickers:
        return f"Blocked duplicate entry for {ticker}: already held as an active open position."

    # Strategy v2 Sector Concentration Guardrail: Max 3 open positions per sector
    sector = screener.get_stock_sector(ticker)
    sector_open_count = sum(1 for p in open_positions if screener.get_stock_sector(p.get("Ticker", "")) == sector)
    if sector_open_count >= 3:
        return f"Blocked {ticker} entry: Sector '{sector}' already has {sector_open_count} open positions (Max 3 allowed in Strategy v2)."

    # Strategy v2: Volatility-based SL (no fixed 3%-15% clamp), validates valid SL below entry
    if initial_sl <= 0 or initial_sl >= entry_price:
        return f"Blocked {ticker} entry: Invalid initial Stop Loss ₹{initial_sl:.2f} for entry ₹{entry_price:.2f}."

    holdings_name, _, _ = get_worksheet_names(sh)
    ws = sh.worksheet(holdings_name)
    account = get_account_details(sh)
    
    cost = entry_price * quantity
    if cost > account["Cash Balance"]:
        return f"Insufficient cash to buy {quantity} of {ticker}. Cost: {cost:.2f}, Cash: {account['Cash Balance']:.2f}"
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    current_sl = initial_sl
    status = "OPEN"
    
    row_data = [
        ticker, date_str, entry_price, quantity, cost,
        initial_sl, current_sl, target, status, "", "", "", "", ""
    ]
    
    retry_gspread(ws.append_row, row_data)
    
    new_cash = account["Cash Balance"] - cost
    update_account_details(sh, {"Cash Balance": new_cash})
    return f"Successfully added {ticker} x {quantity} @ {entry_price:.2f}. New cash: {new_cash:.2f}"

def close_position(sh: gspread.Spreadsheet, row_idx: int, exit_price: float, exit_reason: str) -> str:
    """
    Closes a position in the Holdings worksheet and credits cash.
    """
    holdings_name, _, _ = get_worksheet_names(sh)
    ws = sh.worksheet(holdings_name)
    account = get_account_details(sh)
    
    row_values = ws.row_values(row_idx)
    ticker = row_values[0]
    entry_price = float(row_values[2])
    qty = int(row_values[3])
    entry_val = float(row_values[4])
    
    exit_val = exit_price * qty
    pnl = exit_val - entry_val
    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    update_data = [
        {"range": f"I{row_idx}", "values": [["CLOSED"]]},
        {"range": f"J{row_idx}", "values": [[date_str]]},
        {"range": f"K{row_idx}", "values": [[str(round(exit_price, 2))]]},
        {"range": f"L{row_idx}", "values": [[str(round(exit_val, 2))]]},
        {"range": f"M{row_idx}", "values": [[str(round(pnl, 2))]]},
        {"range": f"N{row_idx}", "values": [[exit_reason]]}
    ]
    retry_gspread(ws.batch_update, update_data)
    
    new_cash = account["Cash Balance"] + exit_val
    update_account_details(sh, {"Cash Balance": new_cash})
    
    pnl_sign = "+" if pnl >= 0 else ""
    return f"Closed trade: {ticker} @ {exit_price:.2f} (Reason: {exit_reason}, PnL: ₹{pnl:,.2f} / {pnl_sign}{pnl_pct:.2f}%)"

def calculate_xirr(cash_flows: List[Tuple[datetime, float]], guess: float = 0.1) -> float:
    """
    Calculates exact annualized XIRR using the Newton-Raphson method.
    """
    if not cash_flows or len(cash_flows) < 2:
        return 0.0
        
    t0 = cash_flows[0][0]
    total_days = max((t - t0).days for t, _ in cash_flows)
    if total_days <= 0:
        return 0.0
        
    def xnpv(rate):
        return sum(cf / ((1.0 + rate) ** ((t - t0).days / 365.25)) for t, cf in cash_flows)
        
    def xnpv_prime(rate):
        return sum(-((t - t0).days / 365.25) * cf / ((1.0 + rate) ** (((t - t0).days / 365.25) + 1.0)) for t, cf in cash_flows)
        
    rate = guess
    for _ in range(100):
        val = xnpv(rate)
        val_prime = xnpv_prime(rate)
        if abs(val_prime) < 1e-7:
            return 0.0
        new_rate = rate - (val / val_prime)
        if abs(new_rate - rate) < 1e-6:
            res = round(new_rate * 100.0, 2)
            if math.isnan(res) or math.isinf(res):
                return 0.0
            return res
        rate = new_rate
        if rate <= -1.0:
            rate = -0.999
    return 0.0

def calculate_performance_metrics(sh: gspread.Spreadsheet) -> Dict[str, Any]:
    """
    Calculates Total Return (%), CAGR (%), XIRR (%), and Days Elapsed.
    Harmonized with robust handling of empty and early-stage portfolios.
    """
    account = get_account_details(sh)
    holdings = get_all_holdings(sh)
    
    initial_capital = float(account.get("Initial Capital", 100000.0))
    current_portfolio_value = float(account.get("Total Portfolio Value", initial_capital))
    
    if initial_capital <= 0:
        initial_capital = 100000.0
        
    total_return_pct = ((current_portfolio_value - initial_capital) / initial_capital) * 100.0
    
    all_dates = []
    if holdings:
        for h in holdings:
            dt_str = h.get("Entry Date")
            if dt_str:
                try:
                    all_dates.append(datetime.strptime(str(dt_str).strip(), "%Y-%m-%d"))
                except (ValueError, TypeError):
                    pass
                    
    # If no trades have ever been opened, portfolio is pristine (0 days active, 0.0% metrics)
    if not all_dates:
        return {
            "Total Return (%)": round(total_return_pct, 2),
            "CAGR (%)": 0.0,
            "XIRR (%)": 0.0,
            "Days Elapsed": 0
        }
        
    start_date = min(all_dates)
    today = datetime.now()
    days_elapsed = (today - start_date).days
    
    if days_elapsed <= 0:
        return {
            "Total Return (%)": round(total_return_pct, 2),
            "CAGR (%)": 0.0,
            "XIRR (%)": 0.0,
            "Days Elapsed": 0
        }
        
    # CAGR calculation:
    # For holding periods < 365 days, annualizing causes extreme compounding distortion.
    # Show simple total return if < 365 days, or annualize when >= 365 days.
    if days_elapsed < 365:
        cagr = total_return_pct
    else:
        years = days_elapsed / 365.25
        try:
            cagr = (((current_portfolio_value / initial_capital) ** (1.0 / years)) - 1.0) * 100.0
        except Exception:
            cagr = total_return_pct
            
    cash_flows = [
        (start_date, -initial_capital),
        (today, current_portfolio_value)
    ]
    
    # For short horizon (< 30 days), annualized XIRR produces distorted percentages.
    if days_elapsed < 30:
        xirr = total_return_pct
    else:
        try:
            xirr = calculate_xirr(cash_flows)
            if math.isnan(xirr) or math.isinf(xirr):
                xirr = cagr
        except Exception:
            xirr = cagr
            
    return {
        "Total Return (%)": round(total_return_pct, 2),
        "CAGR (%)": round(cagr, 2),
        "XIRR (%)": round(xirr, 2),
        "Days Elapsed": days_elapsed
    }

def sync_portfolio(sh: gspread.Spreadsheet, macro_data: Dict[str, Any] = None) -> List[str]:
    """
    Syncs live prices for open positions, checks exit conditions, and updates trailing stops.
    Enforces Macro Guardrails (e.g. TIGHTEN_SL_DAY_LOW) and micro-level stock news sentiment.
    """
    holdings = get_all_holdings(sh)
    open_positions = []
    
    for idx, h in enumerate(holdings):
        if h["Status"] == "OPEN":
            open_positions.append((idx + 2, h))
            
    logs = []
    if not open_positions:
        logs.append("No open positions to sync.")
        return logs
        
    tickers = [h["Ticker"] for _, h in open_positions]
    
    dhan_ltps = {}
    if dhan_client.is_dhan_configured():
        try:
            dhan_ltps = dhan_client.get_dhan_ltp(tickers)
            if dhan_ltps:
                logs.append(f"Real-time quotes received from Dhan for {len(dhan_ltps)} ticker(s).")
        except Exception as e:
            logs.append(f"Dhan LTP fetch warning: {e}")
            
    try:
        # Download historical data for trailing stops and fallback prices
        data = yf.download(tickers, period="60d", interval="1d", group_by="ticker", threads=False, progress=False)
    except Exception as e:
        logs.append(f"Error fetching data from Yahoo Finance: {e}")
        return logs
        
    total_positions_value = 0.0
    holdings_name, _, _ = get_worksheet_names(sh)
    ws = sh.worksheet(holdings_name)
    
    for row_idx, h in open_positions:
        ticker = h["Ticker"]
        qty = int(h["Quantity"])
        target = float(h["Target"])
        current_sl = float(h["Current SL"])
        
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if ticker in data.columns.levels[0]:
                    df = data[ticker].dropna().copy()
                elif ticker in data.columns.levels[1]:
                    df = data.xs(ticker, axis=1, level=1).dropna().copy()
                else:
                    df = pd.DataFrame()
            else:
                df = data.dropna().copy()
                
            if df.empty:
                continue
                
            close_today = float(df['Close'].iloc[-1])
            low_today = float(df['Low'].iloc[-1])
            
            # Calculate 20 EMA for trailing stop
            ema_20_today = float(df['Close'].ewm(span=20, adjust=False).mean().iloc[-1])
            
            # Prioritize Dhan live tick price if available; fallback to close_today
            live_price = dhan_ltps.get(ticker, close_today)
            
            # Check Macro Guardrail for Holdings (e.g. Risk-Off / TIGHTEN_SL_DAY_LOW)
            if macro_data and (macro_data.get("guardrail_holdings") == "TIGHTEN_SL_DAY_LOW" or macro_data.get("color") == "RED"):
                new_sl = max(current_sl, low_today)
                if new_sl > current_sl:
                    retry_gspread(ws.update_cell, row_idx, 7, str(round(new_sl, 2)))
                    logs.append(f"🛡️ 🔴 MACRO GUARDRAIL TRIGGERED for {ticker}: Market Risk-Off. Tightened SL to today's low: ₹{new_sl:.2f}")
                    current_sl = new_sl

            # Check micro-level news sentiment for active position
            clean_sym = ticker.replace(".NS", "")
            stock_sentiment = sentiment_analyzer.get_news_sentiment(f"{clean_sym} stock news NSE")
            
            if stock_sentiment == "NEGATIVE":
                new_sl = max(current_sl, low_today)
                if new_sl > current_sl:
                    retry_gspread(ws.update_cell, row_idx, 7, str(round(new_sl, 2)))
                    logs.append(f"⚠️ NEGATIVE NEWS detected for {ticker}. Tightened Trailing Stop to today's low: ₹{new_sl:.2f}")
                    current_sl = new_sl
            
            # Check Exit Conditions against live_price
            if live_price >= target:
                log = close_position(sh, row_idx, live_price, "Target Hit")
                logs.append(log)
            elif live_price <= current_sl:
                log = close_position(sh, row_idx, live_price, "Stop Loss Hit")
                logs.append(log)
            else:
                # Update Trailing Stop to 20 EMA if 20 EMA is higher than current SL
                new_sl = max(current_sl, ema_20_today)
                if new_sl > current_sl:
                    retry_gspread(ws.update_cell, row_idx, 7, str(round(new_sl, 2)))
                    logs.append(f"Updated Trailing Stop for {ticker} from {current_sl:.2f} to 20 EMA ({new_sl:.2f})")
                total_positions_value += (live_price * qty)
        except Exception as e:
            logs.append(f"Error syncing {ticker}: {e}")
            
    account = get_account_details(sh)
    new_portfolio_val = account["Cash Balance"] + total_positions_value
    update_account_details(sh, {"Total Portfolio Value": new_portfolio_val})
    logs.append(f"Portfolio Sync Complete. Updated Total Portfolio Value: ₹{new_portfolio_val:,.2f}")
    
    return logs

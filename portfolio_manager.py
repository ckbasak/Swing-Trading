import os
import gc
import json
import gspread
import math
import time
import pandas as pd
import yfinance as yf
from datetime import datetime, date
import sentiment_analyzer
import dhan_client
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

def get_or_create_portfolio_sheet(client: gspread.Client, sheet_name: str = None) -> gspread.Spreadsheet:
    """
    Opens the spreadsheet by name, or creates it if it doesn't exist, initializing worksheets.
    """
    target_name = sheet_name or os.environ.get("SPREADSHEET_NAME", "NSE_Swing_Trading_Portfolio_1")
    try:
        sh = client.open(target_name)
    except gspread.SpreadsheetNotFound:
        try:
            sh = client.open("NSE_Swing_Trading_Portfolio")
        except gspread.SpreadsheetNotFound:
            sh = client.create(target_name)
            print(f"Created new Google Sheet: {sh.url}")
        
    # Check/Create Holdings sheet
    try:
        holdings_ws = sh.worksheet("Holdings")
        try:
            first_row = holdings_ws.row_values(1)
            # If old format exists, delete and recreate the worksheet to align columns correctly
            if any(col in first_row for col in ["Traded Value", "Buy Value", "Sell Value"]) or "Entry Value" not in first_row:
                print("Recreating Holdings sheet for the new Entry Value / Exit Value columns...")
                sh.del_worksheet(holdings_ws)
                holdings_ws = sh.add_worksheet(title="Holdings", rows="1000", cols="14")
                headers = [
                    "Ticker", "Entry Date", "Entry Price", "Quantity", "Entry Value",
                    "Initial SL", "Current SL", "Target", "Status", "Exit Date", 
                    "Exit Price", "Exit Value", "PnL", "Exit Reason"
                ]
                holdings_ws.append_row(headers)
        except Exception as ex:
            print(f"Error checking/updating headers: {ex}")
    except gspread.WorksheetNotFound:
        holdings_ws = sh.add_worksheet(title="Holdings", rows="1000", cols="14")
        headers = [
            "Ticker", "Entry Date", "Entry Price", "Quantity", "Entry Value",
            "Initial SL", "Current SL", "Target", "Status", "Exit Date", 
            "Exit Price", "Exit Value", "PnL", "Exit Reason"
        ]
        holdings_ws.append_row(headers)
        # Delete the default Sheet1 if it exists
        try:
            default_ws = sh.worksheet("Sheet1")
            sh.del_worksheet(default_ws)
        except Exception:
            pass
        
    # Check/Create Account sheet
    try:
        sh.worksheet("Account")
    except gspread.WorksheetNotFound:
        account_ws = sh.add_worksheet(title="Account", rows="100", cols="2")
        account_ws.append_row(["Parameter", "Value"])
        account_ws.append_row(["Total Portfolio Value", "1000000"])
        account_ws.append_row(["Cash Balance", "1000000"])
        account_ws.append_row(["Risk Percent", "0.01"])
        account_ws.append_row(["Initial Capital", "1000000"])
        
    # Check/Create Schedules sheet
    get_schedules_worksheet(sh)
    
    return sh

def get_schedules_worksheet(sh: gspread.Spreadsheet) -> gspread.Worksheet:
    """
    Returns the 'Schedules' worksheet, creating it with headers and initial templates if not found.
    """
    try:
        ws = sh.worksheet("Schedules")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Schedules", rows="100", cols="6")
        headers = ["Date", "Time", "Mode", "Status", "Last Run", "Notes"]
        ws.append_row(headers)
        ws.append_row(["DAILY", "08:00", "PREVIEW", "ACTIVE", "", "Morning Pre-Market Scan"])
        ws.append_row(["DAILY", "09:00", "SENTIMENT", "PAUSED", "", "Nifty 50 Market Sentiment Briefing"])
        ws.append_row(["DAILY", "15:25", "EXECUTE", "ACTIVE", "", "Daily Market Close Scan"])
        ws.append_row(["TODAY", "18:00", "EXECUTE", "PAUSED", "", "Sample One-Time Custom Scan"])
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
def _parse_num(val: Any, fallback: float = 0.0) -> float:
    """Safely parse numbers with commas, currency symbols, and percentage signs into float."""
    if val is None or str(val).strip() == "":
        return fallback
    try:
        s = str(val).replace("₹", "").replace("%", "").replace(",", "").strip()
        return float(s)
    except Exception:
        return fallback

def _parse_date(val: Any) -> Optional[datetime]:
    """Safely parse dates across standard Indian & global formats."""
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            pass
    return None

def get_account_details(sh: gspread.Spreadsheet) -> Dict[str, float]:
    """
    Retrieves the account details (Portfolio Value, Cash, Risk %, Initial Capital) from the Account sheet.
    Dynamically supports parameter aliases ('Risk Percent', 'Risk Percentage', 'Risk %') and formats.
    """
    ws = sh.worksheet("Account")
    records = ws.get_all_records()
    details = {}
    for r in records:
        param = str(r.get("Parameter", "")).strip()
        raw_val = str(r.get("Value", "")).strip()
        val = _parse_num(raw_val)
        norm_key = param.lower().replace(" ", "").replace("_", "")
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
        details["Risk Percent"] = 0.05
    if "Risk Percentage" not in details:
        details["Risk Percentage"] = details["Risk Percent"]
    return details

def update_account_details(sh: gspread.Spreadsheet, updates: Dict[str, Any]):
    """Updates parameters in the Account worksheet while strictly preserving all existing rows."""
    try:
        _, account_name, _ = get_worksheet_names(sh)
    except Exception:
        account_name = "Account"
    ws = sh.worksheet(account_name)
    all_rows = ws.get_all_values()
    if not all_rows:
        all_rows = [["Parameter", "Value"]]
        
    param_map = {}
    for idx, row in enumerate(all_rows[1:], start=2):
        if row:
            param_map[row[0].strip().lower().replace(" ", "").replace("_", "")] = idx
            
    for k, v in updates.items():
        norm_k = k.strip().lower().replace(" ", "").replace("_", "")
        formatted_val = str(v)
        if isinstance(v, float):
            formatted_val = f"{v:.2f}"
            
        if norm_k in param_map:
            row_idx = param_map[norm_k]
            retry_gspread(ws.update_cell, row_idx, 2, formatted_val)
        else:
            retry_gspread(ws.append_row, [k, formatted_val])
            param_map[norm_k] = len(all_rows) + 1

def get_all_holdings(sh: gspread.Spreadsheet) -> List[Dict[str, Any]]:
    """
    Returns all rows in the Holdings worksheet as a list of dictionaries.
    """
    ws = sh.worksheet("Holdings")
    return ws.get_all_records()

def get_open_positions(sh: gspread.Spreadsheet) -> List[Dict[str, Any]]:
    """
    Returns only open positions from the Holdings worksheet.
    """
    holdings = get_all_holdings(sh)
    # Return holdings with index (row number is list_index + 2 because of header)
    for idx, h in enumerate(holdings):
        h["row_idx"] = idx + 2
    return [h for h in holdings if h["Status"] == "OPEN"]


# ----------------- Dynamic Regulatory Fee & Tax Configuration -----------------
DEFAULT_FEE_CONFIG: Dict[str, float] = {
    "stt_buy_pct": 0.10,         # 0.10% on buy turnover
    "stt_sell_pct": 0.10,        # 0.10% on sell turnover
    "stamp_duty_pct": 0.015,     # 0.015% on buy turnover only
    "nse_fee_pct": 0.00297,      # 0.00297% on turnover
    "sebi_fee_per_cr": 10.0,     # ₹10 per crore (0.0001%)
    "gst_pct": 18.0,             # 18% on (Brokerage + NSE fee + SEBI fee)
    "dp_charges": 14.75,         # ₹14.75 flat per scrip/day on sell
    "stcg_tax_pct": 20.0,        # 20% on positive net capital gains (Finance Act 2024)
    "brokerage_flat": 0.0        # ₹0 for Dhan equity delivery
}

_fee_config_cache: Dict[str, Any] = {"config": None, "ts": 0.0}

def get_fee_and_tax_config(sh_or_account: Optional[Any] = None, force_refresh: bool = False) -> Dict[str, float]:
    """
    Retrieves active statutory charges and STCG tax rates.
    Priorities:
    1. Values configured in Google Sheet 'Account' tab (dynamic regulatory & user control)
    2. Environment variable overrides (e.g. STCG_TAX_RATE, DP_CHARGES, STT_BUY_RATE)
    3. Default statutory rates (Finance Act 2024 / NSE / SEBI standard schedule)
    """
    global _fee_config_cache
    now = time.time()
    if not force_refresh and _fee_config_cache["config"] is not None and (now - _fee_config_cache["ts"]) < 60:
        return dict(_fee_config_cache["config"])
        
    cfg = dict(DEFAULT_FEE_CONFIG)
    
    # Environment variable overrides
    if os.environ.get("STT_BUY_RATE"):
        try: cfg["stt_buy_pct"] = float(os.environ["STT_BUY_RATE"])
        except Exception: pass
    if os.environ.get("STT_SELL_RATE"):
        try: cfg["stt_sell_pct"] = float(os.environ["STT_SELL_RATE"])
        except Exception: pass
    if os.environ.get("STCG_TAX_RATE"):
        try: cfg["stcg_tax_pct"] = float(os.environ["STCG_TAX_RATE"])
        except Exception: pass
    if os.environ.get("DP_CHARGES"):
        try: cfg["dp_charges"] = float(os.environ["DP_CHARGES"])
        except Exception: pass
    if os.environ.get("GST_RATE"):
        try: cfg["gst_pct"] = float(os.environ["GST_RATE"])
        except Exception: pass

    # Google Sheet 'Account' tab parameters
    acc_details = None
    if isinstance(sh_or_account, dict):
        acc_details = sh_or_account
    elif sh_or_account is not None:
        try:
            acc_details = get_account_details(sh_or_account)
        except Exception:
            pass
    else:
        try:
            acc_details = get_account_details()
        except Exception:
            pass
            
    if acc_details:
        def _parse_f(val, fallback):
            if val is None: return fallback
            try:
                s = str(val).replace("%", "").replace("₹", "").replace(",", "").strip()
                return float(s)
            except Exception:
                return fallback
                
        for k, v in acc_details.items():
            norm = str(k).lower().replace(" ", "").replace("_", "")
            if "sttbuy" in norm:
                cfg["stt_buy_pct"] = _parse_f(v, cfg["stt_buy_pct"])
            elif "sttsell" in norm:
                cfg["stt_sell_pct"] = _parse_f(v, cfg["stt_sell_pct"])
            elif "stamp" in norm:
                cfg["stamp_duty_pct"] = _parse_f(v, cfg["stamp_duty_pct"])
            elif "nse" in norm:
                cfg["nse_fee_pct"] = _parse_f(v, cfg["nse_fee_pct"])
            elif "sebi" in norm:
                cfg["sebi_fee_per_cr"] = _parse_f(v, cfg["sebi_fee_per_cr"])
            elif "gst" in norm:
                cfg["gst_pct"] = _parse_f(v, cfg["gst_pct"])
            elif "dpcharge" in norm or norm == "dp" or "dpchargesflat" in norm:
                cfg["dp_charges"] = _parse_f(v, cfg["dp_charges"])
            elif ("stcgtaxrate" in norm or "taxrate" in norm or norm in ["stcgtax%", "stcgtaxrate%"]) and not norm.startswith("estimated"):
                cfg["stcg_tax_pct"] = _parse_f(v, cfg["stcg_tax_pct"])
            elif "brokerage" in norm:
                cfg["brokerage_flat"] = _parse_f(v, cfg["brokerage_flat"])

    _fee_config_cache = {"config": cfg, "ts": now}
    return dict(cfg)

def calculate_transaction_charges(entry_price: float, exit_price: float, qty: int, is_delivery: bool = True, config: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """
    Computes exact statutory and broker charges for Indian Equity Delivery on NSE via Dhan.
    Dynamically loads rates from Google Sheet 'Account' tab or environment variables.
    """
    if config is None:
        config = get_fee_and_tax_config()
        
    buy_val = round(entry_price * qty, 2)
    sell_val = round(exit_price * qty, 2)
    
    # 1. Buy Side
    buy_stt = round(buy_val * (config["stt_buy_pct"] / 100.0), 2)
    buy_stamp = round(buy_val * (config["stamp_duty_pct"] / 100.0), 2)
    buy_nse = round(buy_val * (config["nse_fee_pct"] / 100.0), 2)
    buy_sebi = round(buy_val * (config["sebi_fee_per_cr"] / 10000000.0), 2)
    buy_brokerage = round(config.get("brokerage_flat", 0.0), 2)
    buy_gst = round((buy_nse + buy_sebi + buy_brokerage) * (config["gst_pct"] / 100.0), 2)
    total_buy_charges = round(buy_stt + buy_stamp + buy_nse + buy_sebi + buy_brokerage + buy_gst, 2)
    
    # 2. Sell Side
    sell_stt = round(sell_val * (config["stt_sell_pct"] / 100.0), 2)
    sell_nse = round(sell_val * (config["nse_fee_pct"] / 100.0), 2)
    sell_sebi = round(sell_val * (config["sebi_fee_per_cr"] / 10000000.0), 2)
    sell_brokerage = round(config.get("brokerage_flat", 0.0), 2)
    sell_gst = round((sell_nse + sell_sebi + sell_brokerage) * (config["gst_pct"] / 100.0), 2)
    dp_charges = config["dp_charges"] if is_delivery else 0.0
    total_sell_charges = round(sell_stt + sell_nse + sell_sebi + sell_brokerage + sell_gst + dp_charges, 2)
    
    total_charges = round(total_buy_charges + total_sell_charges, 2)
    gross_pnl = round(sell_val - buy_val, 2)
    net_pnl = round(gross_pnl - total_charges, 2)
    
    # STCG Tax: using active configurable rate on positive net gains
    stcg_rate = config["stcg_tax_pct"] / 100.0
    est_stcg_tax = round(net_pnl * stcg_rate, 2) if net_pnl > 0 else 0.0
    net_take_home = round(net_pnl - est_stcg_tax, 2)
    
    net_return_pct = round((net_pnl / buy_val) * 100.0, 2) if buy_val > 0 else 0.0
    gross_return_pct = round((gross_pnl / buy_val) * 100.0, 2) if buy_val > 0 else 0.0
    
    return {
        "buy_val": buy_val,
        "sell_val": sell_val,
        "buy_charges": total_buy_charges,
        "sell_charges": total_sell_charges,
        "total_charges": total_charges,
        "gross_pnl": gross_pnl,
        "gross_return_pct": gross_return_pct,
        "net_pnl": net_pnl,
        "net_return_pct": net_return_pct,
        "est_stcg_tax": est_stcg_tax,
        "net_take_home": net_take_home,
        "dp_charges": dp_charges,
        "total_stt": round(buy_stt + sell_stt, 2),
        "rates_used": config
    }

def calculate_true_break_even_price(entry_price: float, qty: int, config: Optional[Dict[str, float]] = None) -> float:
    """Computes exit price required so that Net PnL is >= ₹0.00 after all statutory & DP charges, dynamically adapting to any rate revisions."""
    if qty <= 0 or entry_price <= 0:
        return entry_price
    if config is None:
        config = get_fee_and_tax_config()
        
    buy_fee_pct = (config["stt_buy_pct"] + config["stamp_duty_pct"] + config["nse_fee_pct"]) / 100.0
    buy_fee_pct += (config["sebi_fee_per_cr"] / 10000000.0) + ((config["nse_fee_pct"] / 100.0 + config["sebi_fee_per_cr"] / 10000000.0) * (config["gst_pct"] / 100.0))
    
    sell_fee_pct = (config["stt_sell_pct"] + config["nse_fee_pct"]) / 100.0
    sell_fee_pct += (config["sebi_fee_per_cr"] / 10000000.0) + ((config["nse_fee_pct"] / 100.0 + config["sebi_fee_per_cr"] / 10000000.0) * (config["gst_pct"] / 100.0))
    
    buy_val = entry_price * qty
    buy_cost = buy_val * (1.0 + buy_fee_pct)
    target_sell_val = (buy_cost + config["dp_charges"]) / (1.0 - sell_fee_pct)
    break_even_price = target_sell_val / qty
    return round(break_even_price + 0.05, 2)

def add_position(sh: gspread.Spreadsheet, ticker: str, entry_price: float, qty: int, initial_sl: float, target: float) -> str:
    """
    Adds a new open position to the Holdings sheet and updates the Cash Balance.
    """
    if qty <= 0:
        return f"Blocked {ticker} entry: Quantity must be greater than 0 (got {qty})."
        
    # Check if stock is already open (Double Buy Blocker)
    open_positions = get_open_positions(sh)
    if any(p["Ticker"] == ticker for p in open_positions):
        return f"Blocked duplicate entry for {ticker}: already held as an active open position."
        
    # Validate SL distance percentage
    sl_pct = ((entry_price - initial_sl) / entry_price) * 100.0
    if sl_pct < 3.0:
        return f"Blocked {ticker} entry: Stop loss is too tight ({sl_pct:.2f}% < 3.0%)."
    if sl_pct > 15.0:
        return f"Blocked {ticker} entry: Stop loss is too wide ({sl_pct:.2f}% > 15.0%)."
        
    # Validate target logic
    if target <= entry_price:
        return f"Blocked {ticker} entry: Target must be greater than entry price."
        
    account = get_account_details(sh)
    cash = account["Cash Balance"]
    cost = entry_price * qty
    
    if cost > cash:
        return f"Insufficient cash to buy {qty} shares of {ticker}. Required: {cost:.2f}, Available: {cash:.2f}"
    
    ws = sh.worksheet("Holdings")
    date_str = datetime.now().strftime("%d-%b-%Y")
    row = [
        ticker, date_str, round(entry_price, 2), qty, round(cost, 2),
        round(initial_sl, 2), round(initial_sl, 2), round(target, 2), "OPEN", "", "", "", "", "",
        "", "", "", ""
    ]
    retry_gspread(ws.append_row, row)
    
    # Update cash balance
    new_cash = cash - cost
    update_account_details(sh, {"Cash Balance": new_cash})
    return f"Successfully added position: {qty} shares of {ticker} @ {entry_price:.2f}."

def close_position(sh: gspread.Spreadsheet, row_idx: int, exit_price: float, reason: str) -> str:
    """
    Closes a position in the standard 18-column Holdings worksheet, calculates charges & STCG tax, and credits net proceeds.
    """
    ws = sh.worksheet("Holdings")
    row_values = ws.row_values(row_idx)
    
    ticker = row_values[0]
    entry_price = _parse_num(row_values[2])
    qty = int(_parse_num(row_values[3]))
    
    exit_val = round(exit_price * qty, 2)
    cfg = get_fee_and_tax_config(account)
    charges = calculate_transaction_charges(entry_price, exit_price, qty, config=cfg)
    gross_pnl = charges["gross_pnl"]
    total_charges = charges["total_charges"]
    net_pnl = charges["net_pnl"]
    est_tax = charges["est_stcg_tax"]
    net_return_pct = charges["net_return_pct"]
    exit_date = datetime.now().strftime("%d-%b-%Y")
    
    # Batch update columns 9 (I) to 18 (R)
    update_data = [
        {"range": f"I{row_idx}", "values": [["CLOSED"]]},
        {"range": f"J{row_idx}", "values": [[exit_date]]},
        {"range": f"K{row_idx}", "values": [[round(exit_price, 2)]]},
        {"range": f"L{row_idx}", "values": [[round(exit_val, 2)]]},
        {"range": f"M{row_idx}", "values": [[round(gross_pnl, 2)]]},
        {"range": f"N{row_idx}", "values": [[reason]]},
        {"range": f"O{row_idx}", "values": [[round(total_charges, 2)]]},
        {"range": f"P{row_idx}", "values": [[round(net_pnl, 2)]]},
        {"range": f"Q{row_idx}", "values": [[round(est_tax, 2)]]},
        {"range": f"R{row_idx}", "values": [[round(net_return_pct / 100.0, 4)]]}
    ]
    retry_gspread(ws.batch_update, update_data)
    
    account = get_account_details(sh)
    net_proceeds = round(exit_val - charges["sell_charges"], 2)
    new_cash = round(account.get("Cash Balance", 100000.0) + net_proceeds, 2)
    cur_realized_gross = round(float(account.get("Realized PnL", 0.0)) + gross_pnl, 2)
    cur_charges = round(float(account.get("Total Realized Charges", 0.0)) + total_charges, 2)
    cur_net_pnl = round(float(account.get("Net Realized PnL", 0.0)) + net_pnl, 2)
    stcg_rate = cfg["stcg_tax_pct"] / 100.0
    cur_tax = round(cur_net_pnl * stcg_rate, 2) if cur_net_pnl > 0 else 0.0
    take_home = round(cur_net_pnl - cur_tax, 2)
    init_cap = float(account.get("Initial Capital", 100000.0))
    net_ret = round((cur_net_pnl / init_cap) * 100.0, 2) if init_cap > 0 else 0.0
    
    update_account_details(sh, {
        "Cash Balance": new_cash,
        "Realized PnL": cur_realized_gross,
        "Total Realized Charges": cur_charges,
        "Net Realized PnL": cur_net_pnl,
        "Estimated STCG Tax (20%)": cur_tax,
        "Net Take-Home PnL": take_home,
        "Net Realized Return %": f"{net_ret:+.2f}%"
    })
    
    pnl_sign = "+" if net_pnl >= 0 else ""
    return f"Closed trade for {ticker} @ ₹{exit_price:.2f} (Reason: {reason}, Net PnL: ₹{net_pnl:,.2f} / {pnl_sign}{net_return_pct:.2f}%, Fees: ₹{total_charges:.2f}, Est. Tax: ₹{est_tax:.2f})"

def sync_portfolio(sh: gspread.Spreadsheet, macro_data: Dict[str, Any] = None) -> List[str]:
    """
    Syncs the active portfolio:
    1. Fetches latest prices and 20 EMA for open positions.
    2. Triggers exits if targets or trailing stops are hit.
    3. Updates trailing stop (20 EMA) in Google Sheets if current price is favorable.
    4. Enforces Macro Guardrails (e.g. TIGHTEN_SL_DAY_LOW) and micro-level stock news sentiment.
    """
    open_positions = get_open_positions(sh)
    if not open_positions:
        return ["No open positions to sync."]
        
    tickers = [p["Ticker"] for p in open_positions]
    logs = []
    
    # Try fetching real-time LTP from Dhan first
    dhan_ltps = {}
    if dhan_client.is_dhan_configured():
        try:
            dhan_ltps = dhan_client.get_dhan_ltp(tickers)
            if dhan_ltps:
                logs.append(f"📡 Real-time quotes received from Dhan for {len(dhan_ltps)} ticker(s).")
        except Exception as e:
            logs.append(f"Dhan LTP fetch notice: {e}")
            
    try:
        # Fetch historical EMA data for trailing stop loss calculation
        data = yf.download(tickers, period="60d", interval="1d", group_by="ticker", threads=False)
    except Exception as e:
        return [f"Error fetching sync prices: {e}"]
        
    for p in open_positions:
        ticker = p["Ticker"]
        row_idx = p["row_idx"]
        current_sl = _parse_num(p.get("Current SL", 0))
        target = _parse_num(p.get("Target", 0))
        qty = int(_parse_num(p.get("Quantity", 0)))
        
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if ticker not in data.columns.levels[0]:
                    continue
                df = data[ticker].dropna()
            else:
                if ticker not in data:
                    continue
                df = data[[ticker]].dropna()
                
            if len(df) < 25:
                continue
                
            # Latest Close Price, Low Price, and 20 EMA
            close_today = float(df["Close"].iloc[-1])
            low_today = float(df["Low"].iloc[-1])
            ema_20_today = float(df["Close"].ewm(span=20, adjust=False).mean().iloc[-1])
            
            # Prioritize Dhan live tick price if available; fallback to close_today
            live_price = dhan_ltps.get(ticker, close_today)
            
            # Check Macro Guardrail for Holdings (e.g. Risk-Off / TIGHTEN_SL_DAY_LOW)
            if macro_data and (macro_data.get("guardrail_holdings") == "TIGHTEN_SL_DAY_LOW" or macro_data.get("color") == "RED"):
                new_sl = max(current_sl, low_today)
                if new_sl > current_sl:
                    ws = sh.worksheet("Holdings")
                    retry_gspread(ws.update_cell, row_idx, 7, round(new_sl, 2))
                    logs.append(f"🛡️ 🔴 MACRO GUARDRAIL TRIGGERED for {ticker}: Market Risk-Off. Tightened SL to today's low: ₹{new_sl:.2f}")
                    current_sl = new_sl

            # Check micro-level news sentiment for active position
            clean_sym = ticker.replace(".NS", "")
            stock_sentiment = sentiment_analyzer.get_news_sentiment(f"{clean_sym} stock news NSE")
            
            if stock_sentiment == "NEGATIVE":
                # Tighten Stop Loss to today's low if it is higher than current SL
                new_sl = max(current_sl, low_today)
                if new_sl > current_sl:
                    ws = sh.worksheet("Holdings")
                    retry_gspread(ws.update_cell, row_idx, 7, round(new_sl, 2))
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
                    ws = sh.worksheet("Holdings")
                    retry_gspread(ws.update_cell, row_idx, 7, round(new_sl, 2))
                    logs.append(f"Updated Trailing Stop for {ticker} from {current_sl:.2f} to {new_sl:.2f}")
        except Exception as e:
            logs.append(f"Error syncing {ticker}: {e}")
            
    # Recalculate Total Portfolio Value
    # Total Portfolio Value = Cash Balance + Current Value of Open Positions
    account = get_account_details(sh)
    cash = account["Cash Balance"]
    current_holdings_value = 0.0
    
    # Reload open positions after exits
    remaining_open = get_open_positions(sh)
    for p in remaining_open:
        ticker = p["Ticker"]
        qty = int(p["Quantity"])
        current_price = dhan_ltps.get(ticker)
        if current_price is None:
            try:
                current_price = float(yf.Ticker(ticker).fast_info['last_price'])
            except Exception:
                current_price = float(p["Entry Price"]) # Fallback to entry price
        current_holdings_value += current_price * qty
            
    new_portfolio_value = cash + current_holdings_value
    update_account_details(sh, {"Total Portfolio Value": new_portfolio_value})
    
    gc.collect()
    return logs

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
            dt = _parse_date(h.get("Entry Date"))
            if dt:
                all_dates.append(dt)
                    
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

if __name__ == "__main__":
    print("Testing portfolio manager connection...")
    try:
        client = get_gspread_client()
        sh = get_or_create_portfolio_sheet(client)
        print(f"Spreadsheet opened: {sh.title}")
        print("Account Details:", get_account_details(sh))
    except Exception as e:
        print(f"Error: {e}")

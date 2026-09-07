import os
import sys
import gc
import json
import gspread
import math
import time
import pytz
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, date
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any, Tuple, Optional

# Auto-load .env if available
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(PROJECT_ROOT, "service_account.json")
LOCAL_DB_FILE = os.path.join(PROJECT_ROOT, "local_portfolio_data.json")
DEFAULT_SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "NSE_Swing_Trading_Portfolio_3")
INITIAL_CAPITAL = 100000.0

def _load_env():
    env_file = os.path.join(PROJECT_ROOT, ".env")
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
    """Executes a gspread operation with automatic sleep retry on rate limits or connection drops."""
    for i in range(4):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            err_str = str(e)
            if any(term in err_str for term in ["429", "RESOURCE_EXHAUSTED", "ConnectionResetError", "Connection aborted", "10054"]):
                time.sleep(2 * (i + 1))
            else:
                raise e
    return func(*args, **kwargs)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_gspread_client() -> Optional[gspread.Client]:
    """Creates and returns a gspread client using environment variables or a local key file."""
    env_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if env_json:
        try:
            s = env_json.strip()
            if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
                s = s[1:-1].strip()
            info = json.loads(s)
            if "private_key" in info and "\\n" in info["private_key"]:
                info["private_key"] = info["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            print(f"Error parsing GOOGLE_SERVICE_ACCOUNT_JSON from environment: {e}")
            
    for candidate_path in [
        SERVICE_ACCOUNT_FILE,
        os.path.join(os.path.dirname(PROJECT_ROOT), "AI-Swing-Trade-2", "service_account.json"),
        os.path.join(os.path.dirname(PROJECT_ROOT), "AI-Swing-Trade-1", "service_account.json")
    ]:
        if os.path.exists(candidate_path):
            try:
                creds = Credentials.from_service_account_file(candidate_path, scopes=SCOPES)
                return gspread.authorize(creds)
            except Exception as e:
                print(f"Error reading {candidate_path}: {e}")
                
    return None

def get_worksheet_names(sh: gspread.Spreadsheet) -> Tuple[str, str, str]:
    """Returns standard tab names: ('Holdings', 'Account', 'TelegramChats')."""
    return ("Holdings", "Account", "TelegramChats")

_cached_sh = None

def get_or_create_portfolio_sheet(client: Optional[gspread.Client] = None, sheet_name: Optional[str] = None) -> Optional[gspread.Spreadsheet]:
    """
    Opens the standard 5-tab Google Sheet matching Projects 1 & 2:
    Tabs: 'Account', 'TelegramChats', 'Holdings', 'Schedules', 'DebugLogs'
    Caches spreadsheet handle to prevent Google Sheets 429 rate limit quota exhaustion.
    """
    global _cached_sh
    if _cached_sh is not None and sheet_name is None:
        return _cached_sh

    if client is None:
        client = get_gspread_client()
    if not client:
        return None

    target_name = sheet_name or os.environ.get("SPREADSHEET_NAME", DEFAULT_SPREADSHEET_NAME)
    try:
        sh = retry_gspread(client.open, target_name)
    except Exception:
        try:
            sh = retry_gspread(client.open, DEFAULT_SPREADSHEET_NAME)
        except Exception as e:
            print(f"Could not open Google Sheet {target_name}: {e}")
            return None

    if sheet_name is None:
        _cached_sh = sh
    return sh

# Compatibility alias
def get_or_open_portfolio_sheet(client: gspread.Client) -> Optional[gspread.Spreadsheet]:
    return get_or_create_portfolio_sheet(client)

def get_schedules_tab_name(sh: gspread.Spreadsheet) -> str:
    return "Schedules"

def get_schedules_worksheet(sh: gspread.Spreadsheet) -> gspread.Worksheet:
    """Returns the 'Schedules' worksheet, initializing with standard schedules if not found."""
    sched_name = get_schedules_tab_name(sh)
    try:
        return sh.worksheet(sched_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sched_name, rows=100, cols=6)
        headers = [
            ["Date", "Time", "Mode", "Status", "Last Run", "Notes"],
            ["DAILY", "8:00", "PREVIEW", "ACTIVE", "", "Morning Pre-Market Scan"],
            ["DAILY", "8:30", "SENTIMENT", "ACTIVE", "", "Market Sentiment Scan"],
            ["DAILY", "8:40", "SENTIMENT", "ACTIVE", "", "Market"],
            ["DAILY", "8:50", "SENTIMENT", "ACTIVE", "", "Portfolio"],
            ["WEEKDAYS", "15:25", "EXECUTE", "ACTIVE", "", "Scan and execute"]
        ]
        ws.update(range_name="A1:F6", values=headers)
        return ws

def get_pending_schedules(sh: gspread.Spreadsheet) -> List[Dict[str, Any]]:
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
    try:
        ws = get_schedules_worksheet(sh)
        retry_gspread(ws.update_cell, row_idx, 4, status)
        if last_run is not None:
            retry_gspread(ws.update_cell, row_idx, 5, last_run)
    except Exception as e:
        print(f"Error updating schedule status row {row_idx}: {e}")

def log_cloud_event(sh: gspread.Spreadsheet, source: str, message: str):
    """Records diagnostic cloud runtime events into the standard 'DebugLogs' worksheet."""
    try:
        try:
            ws = sh.worksheet("DebugLogs")
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title="DebugLogs", rows=500, cols=3)
            ws.update(range_name="A1:C1", values=[["Timestamp IST", "Source", "Message"]])
        tz = pytz.timezone("Asia/Kolkata")
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        retry_gspread(ws.append_row, [now_str, source, message])
    except Exception as e:
        print(f"Error writing cloud event log: {e}")

def is_schedule_due(item: Dict[str, Any], now_ist: datetime) -> bool:
    date_val = item.get("date", "").strip().upper()
    time_val = item.get("time", "").strip()
    last_run = item.get("last_run", "").strip()
    today_str = now_ist.strftime("%Y-%m-%d")
    
    if not time_val or last_run.startswith(today_str):
        return False
        
    date_matches = False
    is_recurring = date_val in ("DAILY", "WEEKDAYS", "WEEKDAY", "MON-FRI")
    if date_val in ("TODAY", "", "DAILY"):
        date_matches = True
    elif date_val in ("WEEKDAYS", "WEEKDAY", "MON-FRI"):
        date_matches = (now_ist.weekday() < 5)
    else:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                if datetime.strptime(date_val, fmt).date() == now_ist.date():
                    date_matches = True
                    break
            except ValueError:
                pass
                
    if not date_matches:
        return False
        
    parsed_time = None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            parsed_time = datetime.strptime(time_val, fmt).time()
            break
        except ValueError:
            pass
            
    if not parsed_time:
        return False
        
    target_dt = now_ist.replace(hour=parsed_time.hour, minute=parsed_time.minute, second=0, microsecond=0)
    diff_seconds = (now_ist - target_dt).total_seconds()
    if not is_recurring:
        return diff_seconds >= -60
    return -60 <= diff_seconds <= 1800

# ----------------- Account & Holdings Handlers -----------------

def get_account_details(sh: Optional[gspread.Spreadsheet] = None) -> Dict[str, Any]:
    """Retrieves account details from the standard 2-column Account worksheet."""
    if sh is None:
        client = get_gspread_client()
        sh = get_or_create_portfolio_sheet(client)
    if sh:
        try:
            _, account_name, _ = get_worksheet_names(sh)
            ws = sh.worksheet(account_name)
            records = ws.get_all_records()
            details = {}
            for r in records:
                param = str(r.get("Parameter", "")).strip()
                val_str = str(r.get("Value", "")).strip()
                norm_key = param.lower().replace(" ", "").replace("_", "")
                
                try:
                    num_val = float(val_str.replace("%", "").replace(",", ""))
                    if "risk" in norm_key and num_val > 1.0:
                        num_val = num_val / 100.0
                    details[param] = num_val
                except ValueError:
                    details[param] = val_str

                if norm_key in ["totalportfoliovalue", "portfoliovalue"]:
                    details["Total Portfolio Value"] = float(val_str.replace(",", ""))
                elif norm_key in ["cashbalance", "cash"]:
                    details["Cash Balance"] = float(val_str.replace(",", ""))
                elif norm_key in ["riskpercent", "riskpercentage", "risk"]:
                    details["Risk Percent"] = float(val_str.replace("%", "")) / 100.0 if float(val_str.replace("%", "")) > 1.0 else float(val_str.replace("%", ""))
                elif norm_key in ["initialcapital", "startingcapital"]:
                    details["Initial Capital"] = float(val_str.replace(",", ""))
                    
            if "Initial Capital" not in details:
                details["Initial Capital"] = INITIAL_CAPITAL
            if "Total Portfolio Value" not in details:
                details["Total Portfolio Value"] = INITIAL_CAPITAL
            if "Cash Balance" not in details:
                details["Cash Balance"] = INITIAL_CAPITAL
            if "Risk Percent" not in details:
                details["Risk Percent"] = 0.06
            return details
        except Exception as e:
            print(f"Notice reading Account sheet: {e}")

    # Fallback to local DB
    db = _load_local_db()
    acc = db.get("account", {})
    return {
        "Total Portfolio Value": acc.get("portfolio_value", INITIAL_CAPITAL),
        "Cash Balance": acc.get("cash", INITIAL_CAPITAL),
        "Initial Capital": acc.get("initial_capital", INITIAL_CAPITAL),
        "Risk Percent": acc.get("risk_pct", 6.0) / 100.0,
        "Realized PnL": acc.get("realized_pnl", 0.0),
        "Total Return %": acc.get("total_return_pct", 0.0),
        "Active Pool": acc.get("active_pool", "Top 50 Champions")
    }

def update_account_details(sh: gspread.Spreadsheet, updates: Dict[str, Any]):
    """Updates parameters in the Account worksheet while strictly preserving all existing rows."""
    _, account_name, _ = get_worksheet_names(sh)
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

# Backward compatibility helper
def get_account_summary() -> Dict[str, Any]:
    acc = get_account_details()
    pv = float(acc.get("Total Portfolio Value", INITIAL_CAPITAL))
    cash = float(acc.get("Cash Balance", INITIAL_CAPITAL))
    init_cap = float(acc.get("Initial Capital", INITIAL_CAPITAL))
    risk_p = float(acc.get("Risk Percent", 0.06)) * 100.0 if float(acc.get("Risk Percent", 0.06)) < 1.0 else float(acc.get("Risk Percent", 0.06))
    ret_pct = ((pv - init_cap) / init_cap) * 100.0 if init_cap > 0 else 0.0
    
    return {
        "portfolio_value": pv,
        "cash": cash,
        "initial_capital": init_cap,
        "realized_pnl": float(acc.get("Realized PnL", 0.0)),
        "total_return_pct": ret_pct,
        "cagr_pct": float(str(acc.get("CAGR %", 0.0)).replace("%", "")),
        "xirr_pct": float(str(acc.get("XIRR %", 0.0)).replace("%", "")),
        "days_active": int(acc.get("Days Active", 1)),
        "risk_pct": risk_p,
        "active_pool": str(acc.get("Active Pool", "Top 50 Champions"))
    }

def get_all_holdings(sh: Optional[gspread.Spreadsheet] = None) -> List[Dict[str, Any]]:
    """Returns all records in the Holdings worksheet (both OPEN and CLOSED)."""
    if sh is None:
        client = get_gspread_client()
        sh = get_or_create_portfolio_sheet(client)
    if sh:
        try:
            holdings_name, _, _ = get_worksheet_names(sh)
            ws = sh.worksheet(holdings_name)
            return retry_gspread(ws.get_all_records)
        except Exception:
            pass
    db = _load_local_db()
    return db.get("holdings", [])

def get_open_positions(sh: Optional[gspread.Spreadsheet] = None) -> List[Dict[str, Any]]:
    """Returns only positions with Status == 'OPEN'."""
    all_h = get_all_holdings(sh)
    return [h for h in all_h if str(h.get("Status", "")).strip().upper() == "OPEN"]

# Compatibility alias
def get_holdings() -> List[Dict[str, Any]]:
    return get_open_positions()

def get_closed_trades() -> List[Dict[str, Any]]:
    """Returns positions with Status == 'CLOSED' from the unified Holdings worksheet."""
    all_h = get_all_holdings()
    return [h for h in all_h if str(h.get("Status", "")).strip().upper() == "CLOSED"]

def calculate_position_size(entry_price: float, atr: float, portfolio_value: float, available_cash: float) -> int:
    """
    Position sizing for Strategy 3:
    Risk % = 6.0% per trade (configurable in Account sheet)
    Stop Distance = 2.0x ATR
    """
    risk_pct = 0.06
    try:
        acc = get_account_details()
        risk_pct = float(acc.get("Risk Percent", 0.06))
    except Exception:
        pass
        
    risk_amount = portfolio_value * risk_pct
    risk_per_share = 2.0 * atr if atr > 0 else entry_price * 0.04
    qty_by_risk = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
    qty_by_cash = int(available_cash / entry_price) if entry_price > 0 else 0
    qty = min(qty_by_risk, qty_by_cash)
    return max(2, qty) if (qty >= 2 and (qty * entry_price) <= available_cash) else 0

def add_position(*args, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Adds a new position to the standard 14-column Holdings worksheet and deducts cash.
    Supports both signatures:
      add_position(sh, ticker, entry_price, quantity, initial_sl, target_1, target_2)
      add_position(ticker, company, sector, entry_price, atr)
    """
    client = get_gspread_client()
    sh = get_or_create_portfolio_sheet(client)
    
    if len(args) == 5 and isinstance(args[0], str):
        ticker, company, sector, entry_price, atr = args
        acc = get_account_details(sh)
        port_val = float(acc.get("Total Portfolio Value", INITIAL_CAPITAL))
        cash = float(acc.get("Cash Balance", INITIAL_CAPITAL))
        qty = calculate_position_size(entry_price, atr, port_val, cash)
        initial_sl = round(entry_price - (2.0 * atr), 2)
        target_1 = round(entry_price + (2.0 * atr), 2)
        target_2 = round(entry_price + (4.5 * atr), 2)
    elif len(args) >= 6 and not isinstance(args[0], str):
        sh, ticker, entry_price, qty, initial_sl, target_1 = args[:6]
        target_2 = args[6] if len(args) > 6 else round(entry_price * 1.15, 2)
    else:
        ticker = kwargs.get("ticker")
        entry_price = float(kwargs.get("entry_price", 0))
        atr = float(kwargs.get("atr", entry_price * 0.02))
        acc = get_account_details(sh)
        port_val = float(acc.get("Total Portfolio Value", INITIAL_CAPITAL))
        cash = float(acc.get("Cash Balance", INITIAL_CAPITAL))
        qty = int(kwargs.get("quantity", calculate_position_size(entry_price, atr, port_val, cash)))
        initial_sl = float(kwargs.get("initial_sl", round(entry_price - (2.0 * atr), 2)))
        target_1 = float(kwargs.get("target_1", round(entry_price + (2.0 * atr), 2)))
        target_2 = float(kwargs.get("target_2", round(entry_price + (4.5 * atr), 2)))

    open_pos = get_open_positions(sh)
    if len(open_pos) >= 10:
        print(f"Max portfolio limit (10) reached. Skipping {ticker}.")
        return None
    if any(p.get("Ticker") == ticker for p in open_pos):
        print(f"{ticker} is already open. Skipping duplicate.")
        return None
    if qty < 2:
        print(f"Sized quantity ({qty}) too low for {ticker}. Minimum 2 shares required.")
        return None

    cost = round(qty * entry_price, 2)
    acc = get_account_details(sh)
    cash = float(acc.get("Cash Balance", INITIAL_CAPITAL))
    if cost > cash:
        print(f"Insufficient cash for {ticker}. Cost: ₹{cost}, Cash: ₹{cash}")
        return None

    date_str = datetime.now().strftime("%Y-%m-%d")
    target_str = f"T1: {target_1:.1f} | T2: {target_2:.1f}"

    # Standard 14-column row:
    # Ticker, Entry Date, Entry Price, Quantity, Entry Value, Initial SL, Current SL, Target, Status, Exit Date, Exit Price, Exit Value, PnL, Exit Reason
    row_data = [
        ticker, date_str, round(entry_price, 2), qty, cost,
        initial_sl, initial_sl, target_str, "OPEN", "", "", "", "", ""
    ]

    holdings_name, _, _ = get_worksheet_names(sh)
    ws = sh.worksheet(holdings_name)
    retry_gspread(ws.append_row, row_data)

    new_cash = round(cash - cost, 2)
    update_account_details(sh, {"Cash Balance": new_cash})
    log_cloud_event(sh, "portfolio_manager.py", f"Added position {ticker} x {qty} @ ₹{entry_price:.2f} (Cost: ₹{cost})")

    # Keep local DB synchronized
    db = _load_local_db()
    new_item = {
        "Ticker": ticker, "Entry Date": date_str, "Entry Price": entry_price,
        "Quantity": qty, "Entry Value": cost, "Initial SL": initial_sl,
        "Current SL": initial_sl, "Target": target_str, "Status": "OPEN"
    }
    db["holdings"].append(new_item)
    db["account"]["cash"] = new_cash
    _save_local_db(db)

    print(f"[Strategy 3] Added {ticker} x {qty} @ ₹{entry_price:.2f}. T1: ₹{target_1}, T2: ₹{target_2}, SL: ₹{initial_sl}")
    return new_item

def close_position(sh: gspread.Spreadsheet, row_idx: int, exit_price: float, exit_reason: str) -> str:
    """Closes a position in the standard 14-column Holdings worksheet and credits cash."""
    holdings_name, _, _ = get_worksheet_names(sh)
    ws = sh.worksheet(holdings_name)
    account = get_account_details(sh)
    
    row_values = ws.row_values(row_idx)
    ticker = row_values[0]
    entry_price = float(row_values[2])
    qty = int(row_values[3])
    entry_val = float(row_values[4])
    
    exit_val = round(exit_price * qty, 2)
    pnl = round(exit_val - entry_val, 2)
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
    
    new_cash = round(float(account["Cash Balance"]) + exit_val, 2)
    cur_realized = float(account.get("Realized PnL", 0.0)) + pnl
    update_account_details(sh, {"Cash Balance": new_cash, "Realized PnL": cur_realized})
    log_cloud_event(sh, "portfolio_manager.py", f"Closed {ticker} x {qty} @ ₹{exit_price:.2f} (Reason: {exit_reason}, PnL: ₹{pnl:,.2f})")
    
    pnl_sign = "+" if pnl >= 0 else ""
    return f"Closed trade: {ticker} @ {exit_price:.2f} (Reason: {exit_reason}, PnL: ₹{pnl:,.2f} / {pnl_sign}{pnl_pct:.2f}%)"

def execute_partial_exit(sh: gspread.Spreadsheet, row_idx: int, exit_price: float, current_qty: int, exit_qty: int, target_2_price: float) -> str:
    """
    Strategy 3 Milestone: Target 1 Hit (50% Partial Lock)
    1. Updates row `row_idx` to reflect closed 50% tranche (Quantity = exit_qty, Status = CLOSED, Exit Reason = Target 1 Hit).
    2. Appends new row for remaining 50% runner (Quantity = remaining_qty, Status = OPEN, SL = Entry Price (Break-Even), Target = Target 2).
    3. Credits cash and realized PnL.
    """
    holdings_name, _, _ = get_worksheet_names(sh)
    ws = sh.worksheet(holdings_name)
    account = get_account_details(sh)
    
    row_values = ws.row_values(row_idx)
    ticker = row_values[0]
    entry_date = row_values[1]
    entry_price = float(row_values[2])
    initial_sl = float(row_values[5])
    
    closed_val = round(exit_price * exit_qty, 2)
    closed_entry_val = round(entry_price * exit_qty, 2)
    pnl = round(closed_val - closed_entry_val, 2)
    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Update row_idx to closed 50% tranche
    update_data = [
        {"range": f"D{row_idx}", "values": [[str(exit_qty)]]},
        {"range": f"E{row_idx}", "values": [[str(closed_entry_val)]]},
        {"range": f"I{row_idx}", "values": [["CLOSED"]]},
        {"range": f"J{row_idx}", "values": [[date_str]]},
        {"range": f"K{row_idx}", "values": [[str(round(exit_price, 2))]]},
        {"range": f"L{row_idx}", "values": [[str(closed_val)]]},
        {"range": f"M{row_idx}", "values": [[str(pnl)]]},
        {"range": f"N{row_idx}", "values": [["Target 1 Hit (50% Partial Lock)"]]}
    ]
    retry_gspread(ws.batch_update, update_data)
    
    # 2. Append runner tranche row (Shift SL to Break-Even!)
    remaining_qty = current_qty - exit_qty
    runner_entry_val = round(entry_price * remaining_qty, 2)
    break_even_sl = entry_price
    runner_row = [
        ticker, entry_date, round(entry_price, 2), remaining_qty, runner_entry_val,
        initial_sl, break_even_sl, f"T2: {target_2_price:.1f}", "OPEN", "", "", "", "", ""
    ]
    retry_gspread(ws.append_row, runner_row)
    
    # 3. Credit cash and realized PnL
    new_cash = round(float(account["Cash Balance"]) + closed_val, 2)
    cur_realized = float(account.get("Realized PnL", 0.0)) + pnl
    update_account_details(sh, {"Cash Balance": new_cash, "Realized PnL": cur_realized})
    log_cloud_event(sh, "portfolio_manager.py", f"Target 1 Partial Lock: {ticker} sold {exit_qty} @ ₹{exit_price:.2f} (PnL: ₹{pnl:,.2f}). SL shifted to Break-Even (₹{break_even_sl:.2f}).")
    
    return f"Target 1 Hit: {ticker} sold {exit_qty} shares @ ₹{exit_price:.2f} (+{pnl_pct:.1f}%). Runner {remaining_qty} shares stop moved to Break-Even (₹{break_even_sl:.2f})!"

def sync_portfolio(sh: Optional[gspread.Spreadsheet] = None, macro_data: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Syncs live prices for open positions, checks Strategy 3 exit conditions (T1 50% partial lock, T2 runner, 20 EMA trailing SL),
    and updates Total Portfolio Value.
    """
    if sh is None:
        client = get_gspread_client()
        sh = get_or_create_portfolio_sheet(client)
    if not sh:
        return ["Google Sheet client unavailable."]

    holdings_name, _, _ = get_worksheet_names(sh)
    ws = sh.worksheet(holdings_name)
    all_rows = ws.get_all_values()
    
    open_positions = []
    for idx, r in enumerate(all_rows[1:], start=2):
        if len(r) >= 9 and r[8].strip().upper() == "OPEN":
            try:
                open_positions.append({
                    "row_idx": idx,
                    "Ticker": r[0].strip(),
                    "Entry Date": r[1].strip(),
                    "Entry Price": float(r[2]),
                    "Quantity": int(r[3]),
                    "Entry Value": float(r[4]),
                    "Initial SL": float(r[5]),
                    "Current SL": float(r[6]),
                    "Target": r[7].strip()
                })
            except Exception:
                pass

    logs = []
    if not open_positions:
        acc = get_account_details(sh)
        update_account_details(sh, {"Total Portfolio Value": acc.get("Cash Balance", INITIAL_CAPITAL)})
        logs.append("No open positions to sync.")
        return logs

    tickers = [p["Ticker"] for p in open_positions]
    try:
        data = yf.download(tickers, period="60d", interval="1d", group_by="ticker", threads=False, progress=False)
    except Exception as e:
        logs.append(f"Error downloading market quotes: {e}")
        return logs

    total_positions_val = 0.0
    for p in open_positions:
        t = p["Ticker"]
        qty = p["Quantity"]
        entry_p = p["Entry Price"]
        cur_sl = p["Current SL"]
        target_str = p["Target"]
        row_idx = p["row_idx"]
        
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if t in data.columns.levels[0]:
                    df = data[t].dropna().copy()
                elif t in data.columns.levels[1]:
                    df = data.xs(t, axis=1, level=1).dropna().copy()
                else:
                    df = pd.DataFrame()
            else:
                df = data.dropna().copy()
                
            if df.empty:
                continue
                
            close_today = float(df['Close'].iloc[-1])
            high_today = float(df['High'].iloc[-1])
            low_today = float(df['Low'].iloc[-1])
            ema_20 = float(df['Close'].ewm(span=20, adjust=False).mean().iloc[-1])
            
            t1_val = None
            t2_val = None
            if "T1:" in target_str and "T2:" in target_str:
                parts = target_str.split("|")
                t1_val = float(parts[0].replace("T1:", "").strip())
                t2_val = float(parts[1].replace("T2:", "").strip())
            elif "T2:" in target_str:
                t2_val = float(target_str.replace("T2:", "").strip())
            else:
                try:
                    t1_val = float(target_str)
                except Exception:
                    pass

            # Milestone 1: Target 1 Hit (50% partial profit booking)
            if t1_val and high_today >= t1_val and qty >= 2:
                sell_qty = qty // 2
                exit_p = t1_val
                msg = execute_partial_exit(sh, row_idx, exit_p, qty, sell_qty, t2_val or (entry_p * 1.15))
                logs.append(msg)
                total_positions_val += ((qty - sell_qty) * close_today)
                continue

            # Milestone 2: Target 2 Hit (Runner Extension)
            if t2_val and high_today >= t2_val:
                msg = close_position(sh, row_idx, t2_val, "Target 2 Hit (Runner Extension)")
                logs.append(msg)
                continue

            # Check Stop Loss / Break-Even Stop Hit
            if low_today <= cur_sl:
                reason = "Break-Even Stop Hit" if cur_sl >= entry_p else "Stop Loss Hit"
                msg = close_position(sh, row_idx, cur_sl, reason)
                logs.append(msg)
                continue

            # Trailing Stop: 20 EMA
            if ema_20 > cur_sl:
                new_sl = round(ema_20, 2)
                retry_gspread(ws.update_cell, row_idx, 7, str(new_sl))
                logs.append(f"Updated Trailing Stop for {t} from ₹{cur_sl:.2f} to 20 EMA (₹{new_sl:.2f})")
                cur_sl = new_sl

            total_positions_val += (qty * close_today)
        except Exception as e:
            logs.append(f"Error syncing {t}: {e}")

    acc = get_account_details(sh)
    new_portfolio_val = round(float(acc.get("Cash Balance", INITIAL_CAPITAL)) + total_positions_val, 2)
    update_account_details(sh, {"Total Portfolio Value": new_portfolio_val})
    logs.append(f"Portfolio Sync Complete. Updated Total Portfolio Value: ₹{new_portfolio_val:,.2f}")
    return logs

# Backward compatibility alias
def update_portfolio_and_exits(current_quotes=None):
    client = get_gspread_client()
    sh = get_or_create_portfolio_sheet(client)
    logs = sync_portfolio(sh)
    return {"logs": logs, "exited": [], "partial_exited": []}

def sync_portfolio_to_google_sheets() -> bool:
    try:
        client = get_gspread_client()
        sh = get_or_create_portfolio_sheet(client)
        sync_portfolio(sh)
        return True
    except Exception as e:
        print(f"Error syncing to Google Sheets: {e}")
        return False

# ----------------- Local DB Helpers (Fallback Cache) -----------------

def _load_local_db() -> Dict[str, Any]:
    if os.path.exists(LOCAL_DB_FILE):
        try:
            with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    db = {
        "account": {
            "initial_capital": INITIAL_CAPITAL,
            "cash": INITIAL_CAPITAL,
            "portfolio_value": INITIAL_CAPITAL,
            "realized_pnl": 0.0,
            "total_return_pct": 0.0,
            "risk_pct": 6.0,
            "active_pool": "Top 50 Champions"
        },
        "holdings": []
    }
    _save_local_db(db)
    return db

def _save_local_db(data: Dict[str, Any]):
    try:
        with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving local db: {e}")

if __name__ == "__main__":
    client = get_gspread_client()
    sh = get_or_create_portfolio_sheet(client)
    print("Project 3 Standardized Portfolio Manager Initialized.")
    if sh:
        acc = get_account_details(sh)
        print("Account Details:", acc)
        print("Open Positions:", len(get_open_positions(sh)))
        print("Schedules:", len(get_pending_schedules(sh)))

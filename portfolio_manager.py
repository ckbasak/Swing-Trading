import os
import gc
import json
import gspread
import math
import time
import pandas as pd
import yfinance as yf
from datetime import datetime
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
        
    return sh

def get_account_details(sh: gspread.Spreadsheet) -> Dict[str, float]:
    """
    Retrieves the account details (Portfolio Value, Cash, Risk %, Initial Capital) from the Account sheet.
    """
    _, account_name, _ = get_worksheet_names(sh)
    ws = sh.worksheet(account_name)
    records = ws.get_all_records()
    details = {}
    for r in records:
        param = str(r["Parameter"]).strip()
        val = float(r["Value"])
        details[param] = val
    if "Initial Capital" not in details:
        details["Initial Capital"] = 1000000.0
    if "Risk Percent" not in details:
        details["Risk Percent"] = 0.015
    return details

def update_account_details(sh: gspread.Spreadsheet, updates: Dict[str, float]):
    """
    Updates specific parameters in the Account worksheet.
    """
    _, account_name, _ = get_worksheet_names(sh)
    ws = sh.worksheet(account_name)
    records = ws.get_all_records()
    
    data = {
        "Total Portfolio Value": 1000000.0, 
        "Cash Balance": 1000000.0, 
        "Risk Percent": 0.015,
        "Initial Capital": 1000000.0
    }
    for r in records:
        param = str(r["Parameter"]).strip()
        if param in data:
            data[param] = float(r["Value"])
            
    for k, v in updates.items():
        if k in data:
            data[k] = float(v)
            
    ws.update('A1:B5', [
        ["Parameter", "Value"],
        ["Total Portfolio Value", str(data["Total Portfolio Value"])],
        ["Cash Balance", str(data["Cash Balance"])],
        ["Risk Percent", str(data["Risk Percent"])],
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
    Calculates exact XIRR using the Newton-Raphson method.
    """
    if not cash_flows or len(cash_flows) < 2:
        return 0.0
        
    t0 = cash_flows[0][0]
    def xnpv(rate):
        return sum(cf / ((1.0 + rate) ** ((t - t0).days / 365.25)) for t, cf in cash_flows)
        
    def xnpv_prime(rate):
        return sum(-((t - t0).days / 365.25) * cf / ((1.0 + rate) ** (((t - t0).days / 365.25) + 1.0)) for t, cf in cash_flows)
        
    rate = guess
    for _ in range(100):
        val = xnpv(rate)
        val_prime = xnpv_prime(rate)
        if abs(val_prime) < 1e-7:
            break
        new_rate = rate - (val / val_prime)
        if abs(new_rate - rate) < 1e-6:
            return round(new_rate * 100.0, 2)
        rate = new_rate
        if rate <= -1.0:
            rate = -0.999
    return round(rate * 100.0, 2)

def calculate_performance_metrics(sh: gspread.Spreadsheet) -> Dict[str, Any]:
    """
    Calculates Total Return (%), CAGR (%), and XIRR (%).
    """
    account = get_account_details(sh)
    holdings = get_all_holdings(sh)
    
    initial_capital = account.get("Initial Capital", 1000000.0)
    current_portfolio_value = account.get("Total Portfolio Value", 1000000.0)
    
    total_return_pct = ((current_portfolio_value - initial_capital) / initial_capital) * 100.0
    
    all_dates = []
    for h in holdings:
        if h.get("Entry Date"):
            try:
                all_dates.append(datetime.strptime(h["Entry Date"], "%Y-%m-%d"))
            except Exception:
                pass
                
    if all_dates:
        start_date = min(all_dates)
        days_elapsed = max(1, (datetime.now() - start_date).days)
    else:
        start_date = datetime.now()
        days_elapsed = 1
        
    years = max(days_elapsed / 365.25, 0.0027)
    try:
        cagr = (((current_portfolio_value / initial_capital) ** (1.0 / years)) - 1.0) * 100.0
    except Exception:
        cagr = total_return_pct
        
    cash_flows = [(start_date, -initial_capital)]
    for h in holdings:
        if h.get("Status") == "CLOSED" and h.get("Exit Date") and h.get("Exit Value"):
            try:
                exit_dt = datetime.strptime(h["Exit Date"], "%Y-%m-%d")
                exit_val = float(h["Exit Value"])
                entry_val = float(h["Entry Value"]) if h.get("Entry Value") else float(h["Entry Price"]) * int(h["Quantity"])
                net_pnl = exit_val - entry_val
                cash_flows.append((exit_dt, net_pnl))
            except Exception:
                pass
                
    cash_flows.append((datetime.now(), current_portfolio_value))
    try:
        xirr = calculate_xirr(cash_flows)
    except Exception:
        xirr = cagr
        
    return {
        "Total Return (%)": round(total_return_pct, 2),
        "CAGR (%)": round(cagr, 2),
        "XIRR (%)": round(xirr, 2),
        "Days Elapsed": days_elapsed
    }

def sync_portfolio(sh: gspread.Spreadsheet) -> List[str]:
    """
    Syncs live prices for open positions, checks exit conditions, and updates trailing stops.
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
            
            # Check news sentiment for active position
            clean_sym = ticker.replace(".NS", "")
            stock_sentiment = sentiment_analyzer.get_news_sentiment(f"{clean_sym} stock news NSE")
            
            if stock_sentiment == "NEGATIVE":
                new_sl = max(current_sl, low_today)
                if new_sl > current_sl:
                    retry_gspread(ws.update_cell, row_idx, 7, str(round(new_sl, 2)))
                    logs.append(f"⚠️ NEGATIVE NEWS detected for {ticker}. Tightened Trailing Stop to today's low: {new_sl:.2f}")
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

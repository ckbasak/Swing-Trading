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
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any, Tuple

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
            info = json.loads(env_json)
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

def get_or_create_portfolio_sheet(client: gspread.Client, sheet_name: str = "NSE_Swing_Trading_Portfolio") -> gspread.Spreadsheet:
    """
    Opens the spreadsheet by name, or creates it if it doesn't exist, initializing worksheets.
    """
    try:
        sh = client.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        sh = client.create(sheet_name)
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
        
    return sh

def get_account_details(sh: gspread.Spreadsheet) -> Dict[str, float]:
    """
    Retrieves the account details (Portfolio Value, Cash, Risk %, Initial Capital) from the Account sheet.
    """
    ws = sh.worksheet("Account")
    records = ws.get_all_records()
    details = {}
    for r in records:
        param = r["Parameter"].strip()
        val = float(r["Value"])
        details[param] = val
    if "Initial Capital" not in details:
        details["Initial Capital"] = 1000000.0
    return details

def update_account_details(sh: gspread.Spreadsheet, updates: Dict[str, float]):
    """
    Updates specific parameters in the Account worksheet.
    """
    ws = sh.worksheet("Account")
    records = ws.get_all_records()
    
    # Re-write the table to make sure we don't mess up rows
    data = {
        "Total Portfolio Value": 1000000.0, 
        "Cash Balance": 1000000.0, 
        "Risk Percent": 0.01,
        "Initial Capital": 1000000.0
    }
    for r in records:
        param = r["Parameter"].strip()
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
    date_str = datetime.now().strftime("%Y-%m-%d")
    row = [
        ticker, date_str, entry_price, qty, str(cost),
        initial_sl, initial_sl, target, "OPEN", "", "", "", "", ""
    ]
    retry_gspread(ws.append_row, row)
    
    # Update cash balance
    new_cash = cash - cost
    update_account_details(sh, {"Cash Balance": new_cash})
    return f"Successfully added position: {qty} shares of {ticker} @ {entry_price:.2f}."

def close_position(sh: gspread.Spreadsheet, row_idx: int, exit_price: float, reason: str) -> str:
    """
    Closes a position in the Holdings worksheet, updates Cash Balance, and calculates PnL.
    """
    ws = sh.worksheet("Holdings")
    row_values = ws.row_values(row_idx)
    
    # Row values mapping:
    # 1: Ticker, 2: Entry Date, 3: Entry Price, 4: Quantity, 5: Initial SL, 
    # 6: Current SL, 7: Target, 8: Status, 9: Exit Date, 10: Exit Price, 11: PnL, 12: Exit Reason
    ticker = row_values[0]
    entry_price = float(row_values[2])
    qty = int(row_values[3])
    
    exit_date = datetime.now().strftime("%Y-%m-%d")
    pnl = (exit_price - entry_price) * qty
    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0
    
    sell_value = exit_price * qty
    # Update sheet cells using new 1-based column indexes with rate-limit retry:
    # 9: Status, 10: Exit Date, 11: Exit Price, 12: Sell Value, 13: PnL, 14: Exit Reason
    retry_gspread(ws.update_cell, row_idx, 9, "CLOSED")
    retry_gspread(ws.update_cell, row_idx, 10, exit_date)
    retry_gspread(ws.update_cell, row_idx, 11, str(exit_price))
    retry_gspread(ws.update_cell, row_idx, 12, str(sell_value))
    retry_gspread(ws.update_cell, row_idx, 13, str(pnl))
    retry_gspread(ws.update_cell, row_idx, 14, reason)
    
    # Update account cash and total value
    account = get_account_details(sh)
    new_cash = account["Cash Balance"] + (exit_price * qty)
    update_account_details(sh, {"Cash Balance": new_cash})
    
    pnl_sign = "+" if pnl >= 0 else ""
    return f"Closed trade for {ticker} @ {exit_price:.2f} (Reason: {reason}, PnL: ₹{pnl:,.2f} / {pnl_sign}{pnl_pct:.2f}%)"

def sync_portfolio(sh: gspread.Spreadsheet) -> List[str]:
    """
    Syncs the active portfolio:
    1. Fetches latest prices and 20 EMA for open positions.
    2. Triggers exits if targets or trailing stops are hit.
    3. Updates trailing stop (20 EMA) in Google Sheets if current price is favorable.
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
        current_sl = float(p["Current SL"])
        target = float(p["Target"])
        qty = int(p["Quantity"])
        
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
            
            # Check news sentiment for active position
            clean_sym = ticker.replace(".NS", "")
            stock_sentiment = sentiment_analyzer.get_news_sentiment(f"{clean_sym} stock news NSE")
            
            if stock_sentiment == "NEGATIVE":
                # Tighten Stop Loss to today's low if it is higher than current SL
                new_sl = max(current_sl, low_today)
                if new_sl > current_sl:
                    ws = sh.worksheet("Holdings")
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
                    ws = sh.worksheet("Holdings")
                    retry_gspread(ws.update_cell, row_idx, 7, str(round(new_sl, 2)))
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

def calculate_performance_metrics(sh: gspread.Spreadsheet) -> Dict[str, float]:
    """
    Calculates advanced performance metrics: CAGR and XIRR.
    """
    account = get_account_details(sh)
    initial_cap = account.get("Initial Capital", 1000000.0)
    current_val = account.get("Total Portfolio Value", initial_cap)
    
    # Get all closed and open trades to establish start date
    holdings = get_all_holdings(sh)
    if not holdings:
        return {"Total Return (%)": 0.0, "CAGR (%)": 0.0, "XIRR (%)": 0.0, "Days Elapsed": 0}
        
    dates = []
    for h in holdings:
        dt_str = h.get("Entry Date")
        if dt_str:
            try:
                dates.append(datetime.strptime(str(dt_str).strip(), "%Y-%m-%d"))
            except ValueError:
                pass
                
    if not dates:
        return {"Total Return (%)": 0.0, "CAGR (%)": 0.0, "XIRR (%)": 0.0, "Days Elapsed": 0}
        
    start_date = min(dates)
    today = datetime.now()
    days_elapsed = (today - start_date).days
    
    total_return = ((current_val - initial_cap) / initial_cap) * 100.0
    
    if days_elapsed <= 0:
        cagr = 0.0
    elif days_elapsed < 365:
        cagr = total_return
    else:
        cagr = (((current_val / initial_cap) ** (365.0 / days_elapsed)) - 1) * 100.0
        
    # Calculate simple XIRR
    cashflows = [
        (start_date, -initial_cap),
        (today, current_val)
    ]
    
    xirr_val = 0.0
    if len(cashflows) >= 2:
        t0 = cashflows[0][0]
        def npv(r):
            return sum(cf / ((1 + r) ** ((d - t0).days / 365.0)) for d, cf in cashflows)
            
        def npv_derivative(r):
            return sum(-((d - t0).days / 365.0) * cf * ((1 + r) ** (-((d - t0).days / 365.0) - 1)) for d, cf in cashflows)
            
        r = 0.1
        for _ in range(100):
            try:
                val = npv(r)
                deriv = npv_derivative(r)
                if deriv == 0:
                    break
                new_r = r - val / deriv
                if abs(new_r - r) < 1e-6:
                    xirr_val = new_r * 100.0
                    break
                r = new_r
            except Exception:
                break
                
    if math.isnan(xirr_val) or math.isinf(xirr_val):
        xirr_val = cagr
        
    return {
        "Total Return (%)": round(total_return, 2),
        "CAGR (%)": round(cagr, 2),
        "XIRR (%)": round(xirr_val, 2),
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

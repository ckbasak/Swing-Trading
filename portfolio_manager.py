import os
import json
import gspread
import pandas as pd
import yfinance as yf
from datetime import datetime
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any, Tuple

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
        account_ws.append_row(["Total Portfolio Value", "100000"])
        account_ws.append_row(["Cash Balance", "100000"])
        account_ws.append_row(["Risk Percent", "0.01"])
        
    return sh

def get_account_details(sh: gspread.Spreadsheet) -> Dict[str, float]:
    """
    Retrieves the account details (Portfolio Value, Cash, Risk %) from the Account sheet.
    """
    ws = sh.worksheet("Account")
    records = ws.get_all_records()
    details = {}
    for r in records:
        param = r["Parameter"].strip()
        val = float(r["Value"])
        details[param] = val
    return details

def update_account_details(sh: gspread.Spreadsheet, updates: Dict[str, float]):
    """
    Updates specific parameters in the Account worksheet.
    """
    ws = sh.worksheet("Account")
    cells = ws.range('A2:B10')
    records = ws.get_all_records()
    
    # Re-write the table to make sure we don't mess up rows
    data = {"Total Portfolio Value": 100000.0, "Cash Balance": 100000.0, "Risk Percent": 0.01}
    for r in records:
        param = r["Parameter"].strip()
        if param in data:
            data[param] = float(r["Value"])
            
    for k, v in updates.items():
        if k in data:
            data[k] = float(v)
            
    ws.update('A1:B4', [
        ["Parameter", "Value"],
        ["Total Portfolio Value", str(data["Total Portfolio Value"])],
        ["Cash Balance", str(data["Cash Balance"])],
        ["Risk Percent", str(data["Risk Percent"])]
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
    ws.append_row(row)
    
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
    
    sell_value = exit_price * qty
    # Update sheet cells using new 1-based column indexes:
    # 9: Status, 10: Exit Date, 11: Exit Price, 12: Sell Value, 13: PnL, 14: Exit Reason
    ws.update_cell(row_idx, 9, "CLOSED")
    ws.update_cell(row_idx, 10, exit_date)
    ws.update_cell(row_idx, 11, str(exit_price))
    ws.update_cell(row_idx, 12, str(sell_value))
    ws.update_cell(row_idx, 13, str(pnl))
    ws.update_cell(row_idx, 14, reason)
    
    # Update account cash and total value
    account = get_account_details(sh)
    new_cash = account["Cash Balance"] + (exit_price * qty)
    update_account_details(sh, {"Cash Balance": new_cash})
    
    return f"Closed trade for {ticker} @ {exit_price:.2f} (Reason: {reason}, PnL: {pnl:.2f})"

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
    
    try:
        # Fetch current data for tickers
        data = yf.download(tickers, period="60d", interval="1d", group_by="ticker", threads=True)
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
                
            # Latest Close Price and 20 EMA
            close_today = float(df["Close"].iloc[-1])
            ema_20_today = float(df["Close"].ewm(span=20, adjust=False).mean().iloc[-1])
            
            # Check Exit Conditions
            if close_today >= target:
                log = close_position(sh, row_idx, close_today, "Target Hit")
                logs.append(log)
            elif close_today <= current_sl:
                log = close_position(sh, row_idx, close_today, "Stop Loss Hit")
                logs.append(log)
            else:
                # Update Trailing Stop to 20 EMA if 20 EMA is higher than current SL
                new_sl = max(current_sl, ema_20_today)
                if new_sl > current_sl:
                    ws = sh.worksheet("Holdings")
                    ws.update_cell(row_idx, 7, str(round(new_sl, 2)))
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
        try:
            current_price = float(yf.Ticker(ticker).fast_info['last_price'])
            current_holdings_value += current_price * qty
        except Exception:
            current_holdings_value += float(p["Entry Price"]) * qty # Fallback to entry price
            
    new_portfolio_value = cash + current_holdings_value
    update_account_details(sh, {"Total Portfolio Value": new_portfolio_value})
    
    return logs

if __name__ == "__main__":
    print("Testing portfolio manager connection...")
    try:
        client = get_gspread_client()
        sh = get_or_create_portfolio_sheet(client)
        print(f"Spreadsheet opened: {sh.title}")
        print("Account Details:", get_account_details(sh))
    except Exception as e:
        print(f"Error: {e}")

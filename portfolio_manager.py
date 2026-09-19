import os
import json
import logging
import time
import gspread
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional
from google.oauth2.service_account import Credentials

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

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_NAME = "NSE_Dhan_Portfolio_Manager"

def retry_gspread(func, *args, **kwargs):
    """Executes a gspread operation with exponential backoff on 429 rate limits."""
    delays = [2, 4, 8, 12, 16]
    for attempt, delay in enumerate(delays):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "Quota" in err_str) and attempt < len(delays) - 1:
                time.sleep(delay)
            else:
                raise e
    return func(*args, **kwargs)

def get_gspread_client() -> Optional[gspread.Client]:
    """Creates and returns a gspread client using environment variables or service account JSON."""
    env_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if env_json:
        try:
            cleaned_json = env_json.strip()
            if '""' in cleaned_json and '":"' not in cleaned_json:
                cleaned_json = cleaned_json.replace('""', '"')
            creds_dict = json.loads(cleaned_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            logger.error(f"Failed to authenticate using GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
            
    # Search for service_account.json in directory or parent directory
    possible_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "service_account.json"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "service_account.json")
    ]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                creds = Credentials.from_service_account_file(path, scopes=SCOPES)
                return gspread.authorize(creds)
            except Exception as e:
                logger.error(f"Failed to authenticate using file {path}: {e}")
                
    logger.warning("No valid Google Service Account credentials found.")
    return None

def get_or_create_spreadsheet() -> Optional[gspread.Spreadsheet]:
    """Retrieves or creates the Google Spreadsheet 'NSE_Dhan_Portfolio_Manager'."""
    client = get_gspread_client()
    if not client:
        return None
    try:
        sh = retry_gspread(client.open, SPREADSHEET_NAME)
        return sh
    except gspread.SpreadsheetNotFound:
        try:
            sh = retry_gspread(client.create, SPREADSHEET_NAME)
            logger.info(f"Created new spreadsheet '{SPREADSHEET_NAME}'.")
            return sh
        except Exception as e:
            logger.error(f"Error creating spreadsheet '{SPREADSHEET_NAME}': {e}")
            return None
    except Exception as e:
        logger.error(f"Error opening spreadsheet '{SPREADSHEET_NAME}': {e}")
        return None

def get_or_create_worksheet(sh: gspread.Spreadsheet, title: str, headers: List[str]) -> gspread.Worksheet:
    """Gets an existing worksheet or creates it with default headers."""
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows="200", cols=str(len(headers) + 2))
        retry_gspread(ws.append_row, headers)
        logger.info(f"Created worksheet '{title}' with headers.")
    return ws

def sync_analysis_to_sheets(analyzed_holdings: List[Dict[str, Any]], summary: Dict[str, Any]) -> bool:
    """Syncs full portfolio analysis, recommendations, and capital recycling breakdown to Google Sheets."""
    sh = get_or_create_spreadsheet()
    if not sh:
        logger.warning("Google Sheets sync skipped (client unavailable).")
        return False
        
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # 1. Sync Holdings Analysis Sheet
        holdings_headers = [
            "Timestamp", "Symbol", "Type", "Qty", "Buy Price", "LTP", "Current Value",
            "PnL", "PnL %", "Recommendation", "Strength", "Target", "Stop Loss", "R:R",
            "EMA 20", "SMA 50", "SMA 200", "RSI 14", "Rationale"
        ]
        ws_holdings = get_or_create_worksheet(sh, "Holdings_Analysis", holdings_headers)
        
        rows_holdings = []
        for h in analyzed_holdings:
            rows_holdings.append([
                now_str,
                h["tradingSymbol"],
                h["type"],
                h["qty"],
                h["buyPrice"],
                h["ltp"],
                h["currentValue"],
                h["pnl"],
                h["pnlPercentage"],
                h["recommendation"],
                h["actionStrength"],
                h["targetPrice"],
                h["stopLoss"],
                h["riskReward"],
                h.get("ema20", ""),
                h.get("sma50", ""),
                h.get("sma200", ""),
                h.get("rsi14", ""),
                " | ".join(h.get("rationale", []))
            ])
            
        retry_gspread(ws_holdings.clear)
        retry_gspread(ws_holdings.append_row, holdings_headers)
        if rows_holdings:
            retry_gspread(ws_holdings.append_rows, rows_holdings)
            
        # 2. Sync Recommendations Sheet
        rec_headers = [
            "Timestamp", "Symbol", "Action", "Strength", "Qty", "LTP", "Value",
            "Freed Capital Potential", "Target", "Stop Loss", "Rationale"
        ]
        ws_rec = get_or_create_worksheet(sh, "Recommendations", rec_headers)
        
        rows_rec = []
        for h in analyzed_holdings:
            rows_rec.append([
                now_str,
                h["tradingSymbol"],
                h["recommendation"],
                h["actionStrength"],
                h["qty"],
                h["ltp"],
                h["currentValue"],
                h["freedCapitalPotential"],
                h["targetPrice"],
                h["stopLoss"],
                " | ".join(h.get("rationale", []))
            ])
            
        retry_gspread(ws_rec.clear)
        retry_gspread(ws_rec.append_row, rec_headers)
        if rows_rec:
            retry_gspread(ws_rec.append_rows, rows_rec)
            
        # 3. Sync Capital Recycling Log Sheet
        recycle_headers = [
            "Timestamp", "Total Freed Capital", "Strategy 1 (Mid-Cap 30%)",
            "Strategy 2 (Sector 30%)", "Strategy 3 (Momentum 20%)", "ETF Strategy (Low-Beta 20%)"
        ]
        ws_recycle = get_or_create_worksheet(sh, "Capital_Recycling_Log", recycle_headers)
        cr = summary.get("capitalRecycling", {})
        retry_gspread(ws_recycle.append_row, [
            now_str,
            cr.get("totalFreedCapital", 0.0),
            cr.get("strategy1_midcap", 0.0),
            cr.get("strategy2_sector", 0.0),
            cr.get("strategy3_momentum", 0.0),
            cr.get("etf_strategy", 0.0)
        ])
        
        logger.info(f"Successfully synced {len(analyzed_holdings)} holdings to Google Sheets '{SPREADSHEET_NAME}'.")
        return True
    except Exception as e:
        logger.error(f"Error syncing to Google Sheets: {e}")
        return False

def record_paper_trade(symbol: str, action: str, qty: float, price: float, total_val: float, rationale: str) -> bool:
    """Logs a simulated paper trade to Google Sheets."""
    sh = get_or_create_spreadsheet()
    if not sh:
        return False
    try:
        headers = ["Timestamp", "Symbol", "Action", "Qty", "Execution Price", "Total Value", "Rationale"]
        ws = get_or_create_worksheet(sh, "Paper_Trades", headers)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        retry_gspread(ws.append_row, [now_str, symbol, action, qty, price, total_val, rationale])
        return True
    except Exception as e:
        logger.error(f"Error recording paper trade: {e}")
        return False

def load_paper_trades() -> List[Dict[str, Any]]:
    """Loads recorded paper trades from Google Sheets."""
    sh = get_or_create_spreadsheet()
    if not sh:
        return []
    try:
        headers = ["Timestamp", "Symbol", "Action", "Qty", "Execution Price", "Total Value", "Rationale"]
        ws = get_or_create_worksheet(sh, "Paper_Trades", headers)
        records = retry_gspread(ws.get_all_records)
        return records
    except Exception as e:
        logger.error(f"Error loading paper trades: {e}")
        return []

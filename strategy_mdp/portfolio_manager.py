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

import math

def _sanitize_val(v):
    if v is None:
        return ""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return 0.0
    return v

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
            rows_holdings.append([_sanitize_val(x) for x in [
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
            ]])
            
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
            rows_rec.append([_sanitize_val(x) for x in [
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
            ]])
            
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
        retry_gspread(ws_recycle.append_row, [_sanitize_val(x) for x in [
            now_str,
            cr.get("totalFreedCapital", 0.0),
            cr.get("strategy1_midcap", 0.0),
            cr.get("strategy2_sector", 0.0),
            cr.get("strategy3_momentum", 0.0),
            cr.get("etf_strategy", 0.0)
        ]])
        
        logger.info(f"Successfully synced {len(analyzed_holdings)} holdings to Google Sheets '{SPREADSHEET_NAME}'.")
        return True
    except Exception as e:
        logger.error(f"Error syncing to Google Sheets: {e}")
        return False

PAPER_TRADES_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cached_paper_trades.json")

def record_paper_trade(symbol: str, action: str, qty: float, price: float, total_val: float, rationale: str) -> bool:
    """Logs a simulated paper trade to Google Sheets and local cache file."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade_entry = {
        "Timestamp": now_str,
        "Symbol": symbol,
        "Action": action,
        "Qty": qty,
        "Execution Price": price,
        "Total Value": total_val,
        "Rationale": rationale
    }
    
    # Always save to local cache
    try:
        existing = []
        if os.path.exists(PAPER_TRADES_CACHE_FILE):
            with open(PAPER_TRADES_CACHE_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.append(trade_entry)
        with open(PAPER_TRADES_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
    except Exception as ie:
        logger.error(f"Error saving paper trade to local cache: {ie}")

    # Save to Google Sheets if available
    sh = get_or_create_spreadsheet()
    if not sh:
        return True
    try:
        headers = ["Timestamp", "Symbol", "Action", "Qty", "Execution Price", "Total Value", "Rationale"]
        ws = get_or_create_worksheet(sh, "Paper_Trades", headers)
        retry_gspread(ws.append_row, [now_str, symbol, action, qty, price, total_val, rationale])
        return True
    except Exception as e:
        logger.error(f"Error recording paper trade to Google Sheets: {e}")
        return True

def load_paper_trades() -> List[Dict[str, Any]]:
    """Loads recorded paper trades from Google Sheets or local cache fallback."""
    sh = get_or_create_spreadsheet()
    if sh:
        try:
            headers = ["Timestamp", "Symbol", "Action", "Qty", "Execution Price", "Total Value", "Rationale"]
            ws = get_or_create_worksheet(sh, "Paper_Trades", headers)
            records = retry_gspread(ws.get_all_records)
            if records:
                return records
        except Exception as e:
            logger.error(f"Error loading paper trades from Google Sheets: {e}")

    # Fallback to local cache
    if os.path.exists(PAPER_TRADES_CACHE_FILE):
        try:
            with open(PAPER_TRADES_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading paper trades local cache: {e}")
    return []

def clear_paper_trades() -> bool:
    """Clears all paper trades from local cache and Google Sheets."""
    if os.path.exists(PAPER_TRADES_CACHE_FILE):
        try:
            os.remove(PAPER_TRADES_CACHE_FILE)
        except Exception:
            pass
            
    sh = get_or_create_spreadsheet()
    if sh:
        try:
            headers = ["Timestamp", "Symbol", "Action", "Qty", "Execution Price", "Total Value", "Rationale"]
            ws = get_or_create_worksheet(sh, "Paper_Trades", headers)
            retry_gspread(ws.clear)
            retry_gspread(ws.append_row, headers)
            return True
        except Exception as e:
            logger.error(f"Error clearing paper trades worksheet: {e}")
    return True

def save_app_settings_to_sheets(settings: Dict[str, Any]) -> bool:
    """Saves user optimization presets and indicator thresholds to Google Sheets 'AppSettings' worksheet."""
    sh = get_or_create_spreadsheet()
    if not sh:
        return False
    try:
        headers = ["Key", "Value", "UpdatedAt"]
        ws = get_or_create_worksheet(sh, "AppSettings", headers)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = [
            ["opt_preset", str(settings.get("opt_preset", "")), now_str],
            ["target_pct_val", str(settings.get("target_pct_val", "")), now_str],
            ["stop_loss_pct_val", str(settings.get("stop_loss_pct_val", "")), now_str],
            ["rsi_ob_val", str(settings.get("rsi_ob_val", "")), now_str],
            ["rsi_exit_val", str(settings.get("rsi_exit_val", "")), now_str],
            ["rsi_pb_val", str(settings.get("rsi_pb_val", "")), now_str]
        ]
        retry_gspread(ws.clear)
        retry_gspread(ws.append_row, headers)
        retry_gspread(ws.append_rows, rows)
        logger.info("Successfully saved app settings to Google Sheets 'AppSettings'.")
        return True
    except Exception as e:
        logger.error(f"Error saving app settings to Google Sheets: {e}")
        return False

def load_app_settings_from_sheets() -> Dict[str, Any]:
    """Loads user optimization presets and indicator thresholds from Google Sheets 'AppSettings' worksheet."""
    sh = get_or_create_spreadsheet()
    if not sh:
        return {}
    try:
        headers = ["Key", "Value", "UpdatedAt"]
        ws = get_or_create_worksheet(sh, "AppSettings", headers)
        records = retry_gspread(ws.get_all_records)
        settings = {}
        for r in records:
            k = str(r.get("Key", "")).strip()
            v = r.get("Value")
            if k and v is not None:
                settings[k] = v
        return settings
    except Exception as e:
        logger.error(f"Error loading app settings from Google Sheets: {e}")
        return {}

def _parse_num(val: Any, fallback: float = 0.0) -> float:
    if val is None or str(val).strip() == "":
        return fallback
    try:
        s = str(val).replace("₹", "").replace("%", "").replace(",", "").strip()
        return float(s)
    except Exception:
        return fallback

def get_account_details(sh: Optional[gspread.Spreadsheet] = None) -> Dict[str, Any]:
    """Retrieves account details (Portfolio Value, Cash, Risk %, Execution Mode) from Google Sheets Account worksheet."""
    if not sh:
        sh = get_or_create_spreadsheet()
    if not sh:
        return {
            "Total Portfolio Value": 100000.0,
            "Cash Balance": 100000.0,
            "Initial Capital": 100000.0,
            "Risk Percent": 0.06,
            "Execution Mode": "PAPER_SIMULATED"
        }
    try:
        ws = get_or_create_worksheet(sh, "Account", ["Parameter", "Value"])
        records = retry_gspread(ws.get_all_records)
        details = {}
        for r in records:
            param = str(r.get("Parameter", "")).strip()
            val_str = str(r.get("Value", "")).strip()
            norm_key = param.lower().replace(" ", "").replace("_", "")
            if norm_key in ["totalportfoliovalue", "portfoliovalue"]:
                details["Total Portfolio Value"] = _parse_num(val_str, 100000.0)
            elif norm_key in ["cashbalance", "cash"]:
                details["Cash Balance"] = _parse_num(val_str, 100000.0)
            elif norm_key in ["executionmode", "mode", "tradingmode"]:
                details["Execution Mode"] = val_str.upper()
            elif norm_key in ["initialcapital", "startingcapital"]:
                details["Initial Capital"] = _parse_num(val_str, 100000.0)

        if "Initial Capital" not in details:
            details["Initial Capital"] = 100000.0
        if "Execution Mode" not in details:
            details["Execution Mode"] = "PAPER_SIMULATED"
        return details
    except Exception as e:
        logger.error(f"Error reading Account worksheet: {e}")
        return {
            "Total Portfolio Value": 100000.0,
            "Cash Balance": 100000.0,
            "Initial Capital": 100000.0,
            "Risk Percent": 0.06,
            "Execution Mode": "PAPER_SIMULATED"
        }

def update_account_details(sh: gspread.Spreadsheet, updates: Dict[str, Any]):
    """Updates parameters in the Account worksheet while strictly preserving all existing rows."""
    if not sh:
        return
    try:
        ws = get_or_create_worksheet(sh, "Account", ["Parameter", "Value"])
        all_rows = retry_gspread(ws.get_all_values)
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
    except Exception as e:
        logger.error(f"Error updating Account worksheet: {e}")


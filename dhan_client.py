import os
import io
import csv
import time
import logging
import requests
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Dhan Credentials from Environment
DHAN_CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
DHAN_ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

# Global in-memory cache for Symbol -> Security ID
_SYMBOL_MAP: Dict[str, str] = {}
_LAST_SCRIP_SYNC: float = 0.0
_DHAN_INSTANCE = None

def is_dhan_configured() -> bool:
    """Returns True if Dhan Client ID and Access Token are configured."""
    return bool(os.environ.get("DHAN_CLIENT_ID") and os.environ.get("DHAN_ACCESS_TOKEN"))

def get_dhan_client():
    """
    Initializes and returns a singleton DhanHQ client instance.
    Returns None if credentials are missing.
    """
    global _DHAN_INSTANCE
    client_id = os.environ.get("DHAN_CLIENT_ID")
    access_token = os.environ.get("DHAN_ACCESS_TOKEN")
    
    if not client_id or not access_token:
        return None
        
    if _DHAN_INSTANCE is None:
        try:
            from dhanhq import dhanhq
            _DHAN_INSTANCE = dhanhq(client_id=client_id, access_token=access_token)
            logger.info("DhanHQ client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize DhanHQ client: {e}")
            return None
            
    return _DHAN_INSTANCE

def load_symbol_map(force_refresh: bool = False) -> Dict[str, str]:
    """
    Downloads and caches the Dhan NSE Equity symbol-to-security_id map.
    Cached in-memory and refreshed once per 24 hours.
    """
    global _SYMBOL_MAP, _LAST_SCRIP_SYNC
    now = time.time()
    
    # Use cached map if loaded within the last 24 hours (86400 seconds)
    if _SYMBOL_MAP and not force_refresh and (now - _LAST_SCRIP_SYNC < 86400):
        return _SYMBOL_MAP
        
    try:
        logger.info("Fetching Dhan Scrip Master from CDN...")
        res = requests.get(SCRIP_MASTER_URL, timeout=15)
        if res.status_code != 200:
            logger.error(f"Failed to download Dhan Scrip Master. HTTP {res.status_code}")
            return _SYMBOL_MAP
            
        reader = csv.DictReader(io.StringIO(res.text))
        new_map: Dict[str, str] = {}
        for row in reader:
            if row.get("SEM_EXM_EXCH_ID") == "NSE" and row.get("SEM_SERIES") == "EQ":
                sym = row.get("SEM_TRADING_SYMBOL")
                sec_id = row.get("SEM_SMST_SECURITY_ID")
                if sym and sec_id:
                    new_map[sym.upper()] = str(sec_id)
                    
        if new_map:
            _SYMBOL_MAP = new_map
            _LAST_SCRIP_SYNC = now
            logger.info(f"Loaded {len(_SYMBOL_MAP)} NSE Equity symbols from Dhan Scrip Master.")
    except Exception as e:
        logger.error(f"Error downloading or parsing Dhan Scrip Master: {e}")
        
    return _SYMBOL_MAP

def get_dhan_ltp(tickers: List[str]) -> Dict[str, float]:
    """
    Fetches real-time Last Traded Price (LTP) for a list of tickers (e.g. ['RELIANCE.NS', 'TCS.NS']).
    Returns a dictionary of {ticker: ltp_float}.
    Returns empty dict if Dhan is not configured or on failure.
    """
    client = get_dhan_client()
    if not client:
        return {}
        
    symbol_map = load_symbol_map()
    if not symbol_map:
        return {}
        
    # Map input tickers to (security_id, original_ticker)
    sec_id_to_ticker: Dict[int, str] = {}
    sec_ids_list: List[int] = []
    
    for t in tickers:
        clean_sym = t.replace(".NS", "").upper()
        sec_id_str = symbol_map.get(clean_sym)
        if sec_id_str:
            try:
                sec_id_int = int(sec_id_str)
                sec_id_to_ticker[sec_id_int] = t
                sec_ids_list.append(sec_id_int)
            except ValueError:
                continue
                
    if not sec_ids_list:
        return {}
        
    try:
        # Request batch LTP from Dhan
        payload = {"NSE_EQ": sec_ids_list}
        resp = client.ticker_data(payload)
        
        ltp_results: Dict[str, float] = {}
        if isinstance(resp, dict) and resp.get("status") == "success":
            data = resp.get("data", {}).get("NSE_EQ", {})
            for sec_id_str, quote_info in data.items():
                try:
                    sec_id_int = int(sec_id_str)
                    orig_ticker = sec_id_to_ticker.get(sec_id_int)
                    if orig_ticker and isinstance(quote_info, dict):
                        last_price = quote_info.get("last_price")
                        if last_price is not None:
                            ltp_results[orig_ticker] = float(last_price)
                except Exception:
                    continue
                    
        return ltp_results
    except Exception as e:
        logger.error(f"Error fetching LTP from Dhan: {e}")
        return {}

def get_dhan_funds() -> Optional[Dict[str, float]]:
    """
    Fetches available cash & fund limits from Dhan account.
    Returns dict with 'availabelBalance', 'sodLimit', etc.
    """
    client = get_dhan_client()
    if not client:
        return None
    try:
        funds = client.get_fund_limits()
        if isinstance(funds, dict) and funds.get("status") == "success":
            return funds.get("data", {})
        return None
    except Exception as e:
        logger.error(f"Error fetching Dhan funds: {e}")
        return None

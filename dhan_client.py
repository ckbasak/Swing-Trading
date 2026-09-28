import os
import io
import csv
import time
import logging
import requests
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

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
            try:
                from dhanhq import dhanhq, DhanContext
                _DHAN_INSTANCE = dhanhq(DhanContext(client_id, access_token))
            except TypeError:
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

def is_nse_market_open() -> Tuple[bool, str]:
    """
    Checks if current IST time is within NSE market hours (9:15 AM - 3:30 PM IST, Monday to Friday).
    Returns (is_open, message).
    """
    try:
        import pytz
        tz = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(tz)
    except Exception:
        now_ist = datetime.now()
    
    if now_ist.weekday() >= 5:
        return False, f"NSE Market is CLOSED on weekends ({now_ist.strftime('%A')})."
        
    start_time = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    end_time = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    
    if now_ist < start_time:
        return False, f"NSE Market opens at 09:15 AM IST (Current IST: {now_ist.strftime('%I:%M %p')})."
    elif now_ist > end_time:
        return False, f"NSE Market closed at 03:30 PM IST (Current IST: {now_ist.strftime('%I:%M %p')})."
        
    return True, f"NSE Market is OPEN (Current IST: {now_ist.strftime('%I:%M %p')})."

def validate_live_preflight(ticker: str, quantity: int, price: float) -> Dict[str, Any]:
    """
    Performs comprehensive pre-flight verification before live trade execution.
    Checks:
    1. Dhan configuration & access token status
    2. Ticker security ID mapping in Dhan Scrip Master
    3. Available cash margin in Dhan account
    4. Market hours status (NSE IST window)
    """
    required_amount = round(quantity * price, 2)
    if not is_dhan_configured():
        return {
            "valid": False,
            "reason": "Dhan credentials (Client ID / Access Token) not configured in environment.",
            "sec_id": None,
            "avail_balance": 0.0,
            "required_amount": required_amount
        }
        
    symbol_map = load_symbol_map()
    clean_sym = ticker.replace(".NS", "").upper()
    sec_id = symbol_map.get(clean_sym)
    if not sec_id:
        return {
            "valid": False,
            "reason": f"Symbol '{clean_sym}' not found in Dhan NSE Equity Scrip Master.",
            "sec_id": None,
            "avail_balance": 0.0,
            "required_amount": required_amount
        }
        
    funds = get_dhan_funds()
    avail_balance = 0.0
    if funds:
        avail_balance = float(funds.get("availabelBalance", funds.get("availableCash", funds.get("sodLimit", 0.0))))
        
    if avail_balance > 0 and required_amount > avail_balance:
        return {
            "valid": False,
            "reason": f"Insufficient Dhan cash balance: ₹{avail_balance:,.2f} available, ₹{required_amount:,.2f} required.",
            "sec_id": sec_id,
            "avail_balance": avail_balance,
            "required_amount": required_amount
        }
        
    mkt_open, mkt_msg = is_nse_market_open()
    
    return {
        "valid": True,
        "reason": f"Pre-flight checks PASSED. {mkt_msg}",
        "market_open": mkt_open,
        "market_notice": mkt_msg,
        "sec_id": sec_id,
        "avail_balance": avail_balance,
        "required_amount": required_amount
    }

def place_dhan_order(
    ticker: str,
    quantity: int,
    transaction_type: str = "BUY",
    order_type: str = "MARKET",
    price: float = 0.0,
    stop_loss: float = 0.0,
    target: float = 0.0
) -> Dict[str, Any]:
    """
    Places an exchange delivery order on Dhan broker via DhanHQ API.
    Returns structured result dict with success, order_id, message.
    """
    client = get_dhan_client()
    if not client:
        return {"success": False, "message": "DhanHQ client unavailable or not configured."}
        
    clean_sym = ticker.replace(".NS", "").upper()
    symbol_map = load_symbol_map()
    sec_id = symbol_map.get(clean_sym)
    
    if not sec_id:
        return {"success": False, "message": f"Security ID for '{clean_sym}' missing from Dhan scrip master."}
        
    try:
        txn_flag = getattr(client, "BUY", "BUY") if transaction_type.upper() == "BUY" else getattr(client, "SELL", "SELL")
        ord_flag = getattr(client, "MARKET", "MARKET") if order_type.upper() == "MARKET" else getattr(client, "LIMIT", "LIMIT")
        prod_flag = getattr(client, "CNC", "CNC")
        exch_flag = getattr(client, "NSE", "NSE")
        
        resp = client.place_order(
            security_id=str(sec_id),
            exchange_segment=exch_flag,
            transaction_type=txn_flag,
            quantity=int(quantity),
            order_type=ord_flag,
            product_type=prod_flag,
            price=float(price) if order_type.upper() == "LIMIT" else 0.0
        )
        
        if isinstance(resp, dict) and (resp.get("status") == "success" or resp.get("orderStatus") in ["PENDING", "TRADED", "SUCCESS"]):
            data = resp.get("data", resp)
            order_id = data.get("orderId") or resp.get("orderId") or f"DHAN_{int(time.time())}"
            return {
                "success": True,
                "order_id": str(order_id),
                "message": f"Dhan order placed successfully! Order ID: `{order_id}`",
                "raw_response": resp
            }
        else:
            err_msg = ""
            if isinstance(resp, dict):
                err_msg = resp.get("remarks") or resp.get("message") or resp.get("error") or str(resp)
            else:
                err_msg = str(resp)
            return {"success": False, "message": f"Dhan order error: {err_msg}"}
            
    except Exception as e:
        logger.error(f"Exception placing Dhan order for {ticker}: {e}")
        return {"success": False, "message": f"Dhan order exception: {e}"}

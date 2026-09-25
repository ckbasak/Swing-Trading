import os
import io
import csv
import json
import time
import logging
import requests
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Auto-load .env if available
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

DHAN_CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
DHAN_ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")
SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

_SYMBOL_MAP: Dict[str, str] = {}
_LAST_SCRIP_SYNC: float = 0.0
_DHAN_INSTANCE = None
_HOLDINGS_SOURCE: str = "UNKNOWN"
_LAST_API_ERROR: Optional[str] = None

def get_holdings_source() -> str:
    global _HOLDINGS_SOURCE
    if _HOLDINGS_SOURCE == "UNKNOWN":
        get_dhan_holdings()
    return _HOLDINGS_SOURCE

def get_last_api_error() -> Optional[str]:
    return _LAST_API_ERROR

def set_dhan_access_token(token: str) -> bool:
    """Updates Dhan access token in memory and .env file, resets client instance."""
    token = token.strip()
    if not token:
        return False
    global DHAN_ACCESS_TOKEN, _DHAN_INSTANCE, _HOLDINGS_SOURCE
    DHAN_ACCESS_TOKEN = token
    os.environ["DHAN_ACCESS_TOKEN"] = token
    _update_env_file("DHAN_ACCESS_TOKEN", token)
    _DHAN_INSTANCE = None
    _HOLDINGS_SOURCE = "UNKNOWN"
    get_dhan_holdings()
    return _HOLDINGS_SOURCE == "LIVE"

def _update_env_file(key: str, value: str):
    """Dynamically updates or appends a key-value pair in .env file."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        try:
            lines = []
            found = False
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith(f"{key}="):
                        lines.append(f"{key}={value}\n")
                        found = True
                    else:
                        lines.append(line)
            if not found:
                lines.append(f"{key}={value}\n")
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            logger.error(f"Failed to update .env file: {e}")

def renew_access_token_via_totp() -> Optional[str]:
    """
    Generates a fresh 24-hour Dhan Access Token using pyotp, DHAN_USER_PIN, and DHAN_TOTP_SECRET.
    Updates environment variables and .env file upon success.
    """
    client_id = os.environ.get("DHAN_CLIENT_ID")
    pin = os.environ.get("DHAN_USER_PIN")
    totp_secret = os.environ.get("DHAN_TOTP_SECRET")
    
    if not client_id or not pin or not totp_secret:
        return None
        
    try:
        import pyotp
        import requests
        
        clean_secret = totp_secret.replace(" ", "").upper()
        totp_code = pyotp.TOTP(clean_secret).now()
        
        auth_urls = [
            "https://auth.dhan.co/app/generateAccessToken",
            "https://api.dhan.co/v2/auth/generateAccessToken"
        ]
        
        payloads = [
            {"dhanClientId": client_id, "accessCode": pin, "totp": totp_code},
            {"dhanClientId": client_id, "pin": pin, "totpCode": totp_code},
            {"clientId": client_id, "userPin": pin, "totp": totp_code}
        ]
        
        for url in auth_urls:
            for payload in payloads:
                try:
                    res = requests.post(url, json=payload, timeout=10)
                    if res.status_code == 200:
                        data = res.json()
                        token = data.get("accessToken") or data.get("token") or (data.get("data", {}) if isinstance(data.get("data"), dict) else {}).get("accessToken")
                        if token:
                            logger.info("Successfully auto-generated fresh Dhan Access Token via TOTP!")
                            os.environ["DHAN_ACCESS_TOKEN"] = token
                            _update_env_file("DHAN_ACCESS_TOKEN", token)
                            global _DHAN_INSTANCE
                            _DHAN_INSTANCE = None
                            return token
                except Exception:
                    continue
    except Exception as e:
        logger.error(f"Error during TOTP auto-authentication: {e}")
        
    return None

def is_dhan_configured() -> bool:
    """Returns True if Dhan Client ID and Access Token (or TOTP credentials) are configured."""
    has_token = bool(os.environ.get("DHAN_CLIENT_ID") and os.environ.get("DHAN_ACCESS_TOKEN"))
    has_totp = bool(os.environ.get("DHAN_CLIENT_ID") and os.environ.get("DHAN_USER_PIN") and os.environ.get("DHAN_TOTP_SECRET"))
    return has_token or has_totp

def get_dhan_client():
    """Initializes and returns a singleton DhanHQ client instance."""
    global _DHAN_INSTANCE
    client_id = os.environ.get("DHAN_CLIENT_ID")
    access_token = os.environ.get("DHAN_ACCESS_TOKEN")
    
    if not client_id and (os.environ.get("DHAN_USER_PIN") and os.environ.get("DHAN_TOTP_SECRET")):
        renew_access_token_via_totp()
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
    """Downloads and caches the Dhan NSE Equity symbol-to-security_id map."""
    global _SYMBOL_MAP, _LAST_SCRIP_SYNC
    now = time.time()
    
    if _SYMBOL_MAP and not force_refresh and (now - _LAST_SCRIP_SYNC < 86400):
        return _SYMBOL_MAP
        
    try:
        res = requests.get(SCRIP_MASTER_URL, timeout=15)
        if res.status_code == 200:
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
    except Exception as e:
        logger.error(f"Error loading Dhan Scrip Master: {e}")
        
    return _SYMBOL_MAP

def get_sample_holdings() -> List[Dict[str, Any]]:
    """Provides realistic sample holdings data when Dhan API is unauthenticated or token is expired."""
    return [
        {
            "tradingSymbol": "RELIANCE",
            "securityId": "2885",
            "exchange": "NSE",
            "isin": "INE002A01018",
            "totalQty": 50,
            "dpQty": 50,
            "t1Qty": 0,
            "avgCostPrice": 2450.0,
            "buyPrice": 2450.0,
            "lastPrice": 2740.0,
            "currentValue": 137000.0,
            "investmentValue": 122500.0,
            "pnl": 14500.0,
            "pnlPercentage": 11.84,
            "type": "STOCK"
        },
        {
            "tradingSymbol": "TCS",
            "securityId": "11536",
            "exchange": "NSE",
            "isin": "INE467B01029",
            "totalQty": 30,
            "dpQty": 30,
            "t1Qty": 0,
            "avgCostPrice": 3820.0,
            "buyPrice": 3820.0,
            "lastPrice": 3610.0,
            "currentValue": 108300.0,
            "investmentValue": 114600.0,
            "pnl": -6300.0,
            "pnlPercentage": -5.50,
            "type": "STOCK"
        },
        {
            "tradingSymbol": "INFY",
            "securityId": "1594",
            "exchange": "NSE",
            "isin": "INE009A01021",
            "totalQty": 65,
            "dpQty": 65,
            "t1Qty": 0,
            "avgCostPrice": 1420.0,
            "buyPrice": 1420.0,
            "lastPrice": 1580.0,
            "currentValue": 102700.0,
            "investmentValue": 92300.0,
            "pnl": 10400.0,
            "pnlPercentage": 11.27,
            "type": "STOCK"
        },
        {
            "tradingSymbol": "HDFCBANK",
            "securityId": "1333",
            "exchange": "NSE",
            "isin": "INE040A01034",
            "totalQty": 75,
            "dpQty": 75,
            "t1Qty": 0,
            "avgCostPrice": 1680.0,
            "buyPrice": 1680.0,
            "lastPrice": 1520.0,
            "currentValue": 114000.0,
            "investmentValue": 126000.0,
            "pnl": -12000.0,
            "pnlPercentage": -9.52,
            "type": "STOCK"
        },
        {
            "tradingSymbol": "TATAPOWER",
            "securityId": "3456",
            "exchange": "NSE",
            "isin": "INE155A01022",
            "totalQty": 200,
            "dpQty": 200,
            "t1Qty": 0,
            "avgCostPrice": 380.0,
            "buyPrice": 380.0,
            "lastPrice": 420.0,
            "currentValue": 84000.0,
            "investmentValue": 76000.0,
            "pnl": 8000.0,
            "pnlPercentage": 10.53,
            "type": "STOCK"
        },
        {
            "tradingSymbol": "NIFTYBEES",
            "securityId": "10576",
            "exchange": "NSE",
            "isin": "INF204KB1016",
            "totalQty": 400,
            "dpQty": 400,
            "t1Qty": 0,
            "avgCostPrice": 235.0,
            "buyPrice": 235.0,
            "lastPrice": 262.0,
            "currentValue": 104800.0,
            "investmentValue": 94000.0,
            "pnl": 10800.0,
            "pnlPercentage": 11.49,
            "type": "ETF"
        },
        {
            "tradingSymbol": "GOLDBEES",
            "securityId": "10579",
            "exchange": "NSE",
            "isin": "INF204KB1081",
            "totalQty": 1500,
            "dpQty": 1500,
            "t1Qty": 0,
            "avgCostPrice": 58.0,
            "buyPrice": 58.0,
            "lastPrice": 66.5,
            "currentValue": 99750.0,
            "investmentValue": 87000.0,
            "pnl": 12750.0,
            "pnlPercentage": 14.66,
            "type": "ETF"
        },
        {
            "tradingSymbol": "BANKBEES",
            "securityId": "10577",
            "exchange": "NSE",
            "isin": "INF204KB1024",
            "totalQty": 200,
            "dpQty": 200,
            "t1Qty": 0,
            "avgCostPrice": 485.0,
            "buyPrice": 485.0,
            "lastPrice": 530.0,
            "currentValue": 106000.0,
            "investmentValue": 97000.0,
            "pnl": 9000.0,
            "pnlPercentage": 9.28,
            "type": "ETF"
        },
        {
            "tradingSymbol": "ICICIBANK",
            "securityId": "4963",
            "exchange": "NSE",
            "isin": "INE090A01021",
            "totalQty": 80,
            "dpQty": 80,
            "t1Qty": 0,
            "avgCostPrice": 1050.0,
            "buyPrice": 1050.0,
            "lastPrice": 1210.0,
            "currentValue": 96800.0,
            "investmentValue": 84000.0,
            "pnl": 12800.0,
            "pnlPercentage": 15.24,
            "type": "STOCK"
        },
        {
            "tradingSymbol": "LT",
            "securityId": "11483",
            "exchange": "NSE",
            "isin": "INE018A01030",
            "totalQty": 25,
            "dpQty": 25,
            "t1Qty": 0,
            "avgCostPrice": 3650.0,
            "buyPrice": 3650.0,
            "lastPrice": 3480.0,
            "currentValue": 87000.0,
            "investmentValue": 91250.0,
            "pnl": -4250.0,
            "pnlPercentage": -4.66,
            "type": "STOCK"
        }
    ]

def save_cached_holdings(data: List[Dict[str, Any]]):
    """Saves real holdings to local JSON file for persistent offline analysis."""
    try:
        cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cached_holdings.json")
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving cached holdings: {e}")

def load_cached_holdings() -> List[Dict[str, Any]]:
    """Loads previously saved user holdings or falls back to sample holdings."""
    cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cached_holdings.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    return [
                        item for item in data 
                        if float(item.get("totalQty") or item.get("holdingQty") or item.get("dpQty") or 0) > 0
                    ]
        except Exception as e:
            logger.error(f"Error loading cached holdings: {e}")
    return get_sample_holdings()

def get_dhan_holdings() -> List[Dict[str, Any]]:
    """
    Fetches real-time holdings from Dhan account.
    If Dhan API token is expired, returns cached real holdings combined with live yfinance feeds
    so technical analysis operates continuously without requiring daily token renewals.
    """
    global _HOLDINGS_SOURCE, _LAST_API_ERROR
    client = get_dhan_client()
    if not client:
        logger.info("Dhan client unavailable. Returning cached holdings data.")
        _HOLDINGS_SOURCE = "CACHED"
        return load_cached_holdings()
        
    try:
        resp = client.get_holdings()
        if isinstance(resp, dict) and resp.get("status") == "success":
            holdings_data = resp.get("data", [])
            if holdings_data:
                formatted = []
                for item in holdings_data:
                    sym = item.get("tradingSymbol", "").upper()
                    qty = float(item.get("totalQty") or item.get("holdingQty") or 0)
                    if qty <= 0:
                        continue
                    avg_cost = float(item.get("avgCostPrice") or item.get("costPrice") or 0)
                    last_price = float(item.get("lastPrice") or item.get("closePrice") or avg_cost)
                    inv_val = qty * avg_cost
                    curr_val = qty * last_price
                    pnl = curr_val - inv_val
                    pnl_pct = (pnl / inv_val * 100) if inv_val > 0 else 0.0
                    
                    is_etf = sym.endswith("BEES") or "ETF" in sym or sym in ["NIFTYBEES", "BANKBEES", "GOLDBEES", "ITBEES", "JUNIORBEES", "PHARMABEES", "AUTOBEES", "CPSEETF", "MON100"]
                    
                    formatted.append({
                        "tradingSymbol": sym,
                        "securityId": str(item.get("securityId", "")),
                        "exchange": item.get("exchange", "NSE"),
                        "isin": item.get("isin", ""),
                        "totalQty": qty,
                        "dpQty": qty,
                        "t1Qty": float(item.get("t1Qty") or 0),
                        "avgCostPrice": avg_cost,
                        "buyPrice": avg_cost,
                        "lastPrice": last_price,
                        "currentValue": curr_val,
                        "investmentValue": inv_val,
                        "pnl": pnl,
                        "pnlPercentage": pnl_pct,
                        "type": "ETF" if is_etf else "STOCK"
                    })
                save_cached_holdings(formatted)
                _HOLDINGS_SOURCE = "LIVE"
                _LAST_API_ERROR = None
                return formatted
        _LAST_API_ERROR = str(resp) if resp else "Empty response from Dhan get_holdings"
        logger.warning(f"Dhan get_holdings status error: {resp}.")
        if isinstance(resp, dict) and "DH-901" in str(resp):
            logger.info("Attempting TOTP auto-authentication renewal...")
            new_token = renew_access_token_via_totp()
            if new_token:
                new_client = get_dhan_client()
                if new_client:
                    retry_resp = new_client.get_holdings()
                    if isinstance(retry_resp, dict) and retry_resp.get("status") == "success":
                        holdings_data = retry_resp.get("data", [])
                        if holdings_data:
                            formatted = []
                            for item in holdings_data:
                                sym = item.get("tradingSymbol", "").upper()
                                qty = float(item.get("totalQty") or item.get("holdingQty") or 0)
                                if qty <= 0:
                                    continue
                                avg_cost = float(item.get("avgCostPrice") or item.get("costPrice") or 0)
                                last_price = float(item.get("lastPrice") or item.get("closePrice") or avg_cost)
                                inv_val = qty * avg_cost
                                curr_val = qty * last_price
                                pnl = curr_val - inv_val
                                pnl_pct = (pnl / inv_val * 100) if inv_val > 0 else 0.0
                                is_etf = sym.endswith("BEES") or "ETF" in sym or sym in ["NIFTYBEES", "BANKBEES", "GOLDBEES", "ITBEES", "JUNIORBEES", "PHARMABEES", "AUTOBEES", "CPSEETF", "MON100"]
                                formatted.append({
                                    "tradingSymbol": sym,
                                    "securityId": str(item.get("securityId", "")),
                                    "exchange": item.get("exchange", "NSE"),
                                    "isin": item.get("isin", ""),
                                    "totalQty": qty,
                                    "dpQty": qty,
                                    "t1Qty": float(item.get("t1Qty") or 0),
                                    "avgCostPrice": avg_cost,
                                    "buyPrice": avg_cost,
                                    "lastPrice": last_price,
                                    "currentValue": curr_val,
                                    "investmentValue": inv_val,
                                    "pnl": pnl,
                                    "pnlPercentage": pnl_pct,
                                    "type": "ETF" if is_etf else "STOCK"
                                })
                            save_cached_holdings(formatted)
                            _HOLDINGS_SOURCE = "LIVE"
                            _LAST_API_ERROR = None
                            return formatted
        logger.warning("Falling back to cached holdings.")
    except Exception as e:
        _LAST_API_ERROR = str(e)
        logger.error(f"Error fetching Dhan holdings: {e}. Falling back to cached holdings.")
        
    _HOLDINGS_SOURCE = "CACHED"
    return load_cached_holdings()

def get_dhan_positions() -> List[Dict[str, Any]]:
    """Fetches real-time open positions from Dhan account."""
    client = get_dhan_client()
    if not client:
        return []
    try:
        resp = client.get_positions()
        if isinstance(resp, dict) and resp.get("status") == "success":
            return resp.get("data", [])
        return []
    except Exception as e:
        logger.error(f"Error fetching Dhan positions: {e}")
        return []

def get_dhan_funds() -> Dict[str, float]:
    """Fetches available cash & fund limits from Dhan account."""
    client = get_dhan_client()
    if not client:
        return {"availableBalance": 50000.0, "sodLimit": 50000.0, "collateralAmount": 0.0}
    try:
        funds = client.get_fund_limits()
        if isinstance(funds, dict) and funds.get("status") == "success":
            data = funds.get("data", {})
            return {
                "availableBalance": float(data.get("availabelBalance") or data.get("availableBalance") or 50000.0),
                "sodLimit": float(data.get("sodLimit") or 50000.0),
                "collateralAmount": float(data.get("collateralAmount") or 0.0)
            }
    except Exception as e:
        logger.error(f"Error fetching Dhan funds: {e}")
    return {"availableBalance": 50000.0, "sodLimit": 50000.0, "collateralAmount": 0.0}

def get_dhan_ltp(tickers: List[str]) -> Dict[str, float]:
    """Fetches real-time Last Traded Price (LTP) for a list of tickers."""
    client = get_dhan_client()
    if not client:
        return {}
    symbol_map = load_symbol_map()
    if not symbol_map:
        return {}
        
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

def place_dhan_order(
    trading_symbol: str,
    transaction_type: str,
    quantity: float,
    price: float = 0.0,
    order_type: str = "MARKET",
    product_type: str = "CNC"
) -> Dict[str, Any]:
    """
    Executes a real buy/sell order on Dhan via DhanHQ API.
    Auto-renews access token via TOTP if expired.
    """
    client = get_dhan_client()
    if not client:
        token = renew_access_token_via_totp()
        if token:
            client = get_dhan_client()
            
    if not client:
        return {"status": "failure", "remarks": "Dhan client unavailable. Check API credentials."}
        
    symbol_map = load_symbol_map()
    clean_sym = trading_symbol.replace(".NS", "").upper()
    sec_id = symbol_map.get(clean_sym)
    
    if not sec_id:
        return {"status": "failure", "remarks": f"Security ID not found for symbol {clean_sym}."}
        
    try:
        ex_seg = getattr(client, "NSE", "NSE_EQ")
        txn_type = getattr(client, transaction_type.upper(), transaction_type.upper())
        ord_type = getattr(client, order_type.upper(), order_type.upper())
        prod_type = getattr(client, product_type.upper(), product_type.upper())
        
        qty_int = int(max(1, quantity))
        p_val = float(price) if order_type.upper() == "LIMIT" else 0.0
        
        res = client.place_order(
            security_id=sec_id,
            exchange_segment=ex_seg,
            transaction_type=txn_type,
            quantity=qty_int,
            order_type=ord_type,
            product_type=prod_type,
            price=p_val
        )
        
        logger.info(f"Dhan Order Response for {clean_sym} ({transaction_type}): {res}")
        if isinstance(res, dict):
            if "DH-905" in str(res) or "Invalid IP" in str(res):
                return {
                    "status": "failure",
                    "error_code": "DH-905",
                    "remarks": "Invalid IP (DH-905). Your current Public IP is 103.59.72.46. Please whitelist 103.59.72.46 on web.dhan.co -> Profile -> DhanHQ Trading API (or disable IP Whitelisting) and generate a fresh Access Token."
                }
            if "DH-901" in str(res):
                logger.info("Token expired during place_order. Auto-renewing via TOTP...")
                new_token = renew_access_token_via_totp()
                if new_token:
                    new_client = get_dhan_client()
                    if new_client:
                        res = new_client.place_order(
                            security_id=sec_id,
                            exchange_segment=ex_seg,
                            transaction_type=txn_type,
                            quantity=qty_int,
                            order_type=ord_type,
                            product_type=prod_type,
                            price=p_val
                        )
                        if isinstance(res, dict) and ("DH-905" in str(res) or "Invalid IP" in str(res)):
                            return {
                                "status": "failure",
                                "error_code": "DH-905",
                                "remarks": "Invalid IP (DH-905). Your current Public IP is 103.59.72.46. Please whitelist 103.59.72.46 on web.dhan.co -> Profile -> DhanHQ Trading API (or disable IP Whitelisting) and generate a fresh Access Token."
                            }
        return res if isinstance(res, dict) else {"status": "success", "data": str(res)}
    except Exception as e:
        logger.error(f"Error placing Dhan order for {clean_sym}: {e}")
        return {"status": "failure", "remarks": str(e)}


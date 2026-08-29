import os
import io
import zipfile
import requests
import pyotp
import logging
import pandas as pd
from NorenRestApiPy.NorenApi import NorenApi

logger = logging.getLogger(__name__)

class ShoonyaApiPy(NorenApi):
    def __init__(self):
        # Initialize NorenApi with endpoints
        NorenApi.__init__(
            self, 
            host='https://api.shoonya.com/NorenWnS/', 
            websocket='wss://api.shoonya.com/NorenWnS/', 
            eodhost='https://api.shoonya.com/NorenWnS/'
        )

# Token Master cache settings
TOKEN_MASTER_FILE = "NSE_symbols.txt"
TOKEN_MASTER_URL = "https://api.shoonya.com/NSE_symbols.txt.zip"
_token_cache = {}

def download_token_master():
    """Downloads and unzips Shoonya's official NSE security master file if not present."""
    if os.path.exists(TOKEN_MASTER_FILE):
        return
        
    logger.info("Downloading Shoonya NSE security master token file...")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(TOKEN_MASTER_URL, headers=headers, timeout=30)
        if r.status_code == 200:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            z.extractall()
            logger.info("NSE Security Master unzipped successfully.")
        else:
            logger.error(f"Failed to download Security Master: HTTP {r.status_code}")
    except Exception as e:
        logger.error(f"Error downloading Security Master file: {e}")

def load_token_cache():
    """Loads NSE_symbols.txt file into a symbol-to-token memory cache dictionary."""
    global _token_cache
    if _token_cache:
        return
        
    download_token_master()
    if not os.path.exists(TOKEN_MASTER_FILE):
        logger.warning("NSE_symbols.txt not found. Symbol-to-token mappings will fail.")
        return
        
    logger.info("Loading NSE security master into memory...")
    try:
        # File contains: Exch,Token,Symbol,TradingSymbol,Expiry,Instrument,LotSize...
        df = pd.read_csv(TOKEN_MASTER_FILE)
        # Filter for Equity EQ segment
        df_eq = df[df['Instrument'] == 'EQ']
        for _, row in df_eq.iterrows():
            sym = str(row['Symbol']).strip()
            token = str(row['Token']).strip()
            _token_cache[sym] = token
        logger.info(f"Loaded {len(_token_cache)} equity tokens into cache.")
    except Exception as e:
        logger.error(f"Error parsing security master file: {e}")

def get_shoonya_token(symbol: str) -> str:
    """
    Translates yfinance suffix NSE symbols to Shoonya numeric tokens.
    E.g. 'SBIN.NS' -> 'SBIN' -> '3045'.
    """
    load_token_cache()
    base_sym = symbol.replace(".NS", "").replace(".NSE", "").strip()
    return _token_cache.get(base_sym, "")

def get_shoonya_client():
    """Performs login handshake and returns an authenticated Shoonya API client."""
    user = os.environ.get("SHOONYA_USER_ID")
    password = os.environ.get("SHOONYA_PASSWORD")
    totp_key = os.environ.get("SHOONYA_TOTP_KEY")
    vendor_code = os.environ.get("SHOONYA_VENDOR_CODE")
    api_key = os.environ.get("SHOONYA_API_KEY")
    
    if not all([user, password, totp_key, vendor_code, api_key]):
        logger.warning("Missing Shoonya credentials environment variables. Shoonya integration disabled.")
        return None
        
    try:
        # Generate current TOTP code using pyotp
        totp = pyotp.TOTP(totp_key.replace(" ", ""))
        twoFA = totp.now()
        
        api = ShoonyaApiPy()
        imei = "dummy_imei"
        
        logger.info(f"Attempting Shoonya login for User: {user}...")
        ret = api.login(
            userid=user, 
            password=password, 
            twoFA=twoFA, 
            vendor_code=vendor_code, 
            api_key=api_key, 
            imei=imei
        )
        if ret and ret.get("stat") == "Ok":
            logger.info("Shoonya API Login successful!")
            return api
        else:
            logger.error(f"Shoonya Login failed response: {ret}")
            return None
    except Exception as e:
        logger.error(f"Exception during Shoonya Login handshake: {e}")
        return None

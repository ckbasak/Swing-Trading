import sys
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os
import gc
import io
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from typing import List, Dict, Any
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
import sentiment_analyzer

# Nifty 250 List URL (Updated to Nifty 50)
NIFTY_250_URL = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"

# Comprehensive Cache for Nifty 50 Company Names
COMPANY_NAME_CACHE: Dict[str, str] = {
    "ADANIENT.NS": "Adani Enterprises Ltd.",
    "ADANIPORTS.NS": "Adani Ports & SEZ Ltd.",
    "APOLLOHOSP.NS": "Apollo Hospitals Enterprise Ltd.",
    "ASIANPAINT.NS": "Asian Paints Ltd.",
    "AXISBANK.NS": "Axis Bank Ltd.",
    "BAJAJ-AUTO.NS": "Bajaj Auto Ltd.",
    "BAJFINANCE.NS": "Bajaj Finance Ltd.",
    "BAJAJFINSV.NS": "Bajaj Finserv Ltd.",
    "BEL.NS": "Bharat Electronics Ltd.",
    "BHARTIARTL.NS": "Bharti Airtel Ltd.",
    "CIPLA.NS": "Cipla Ltd.",
    "COALINDIA.NS": "Coal India Ltd.",
    "DRREDDY.NS": "Dr. Reddy's Laboratories Ltd.",
    "EICHERMOT.NS": "Eicher Motors Ltd.",
    "ETERNAL.NS": "Eternal Capital Ltd.",
    "GRASIM.NS": "Grasim Industries Ltd.",
    "HCLTECH.NS": "HCL Technologies Ltd.",
    "HDFCBANK.NS": "HDFC Bank Ltd.",
    "HDFCLIFE.NS": "HDFC Life Insurance Co. Ltd.",
    "HINDALCO.NS": "Hindalco Industries Ltd.",
    "HINDUNILVR.NS": "Hindustan Unilever Ltd.",
    "ICICIBANK.NS": "ICICI Bank Ltd.",
    "INDIGO.NS": "InterGlobe Aviation Ltd.",
    "INDUSINDBK.NS": "IndusInd Bank Ltd.",
    "INFY.NS": "Infosys Ltd.",
    "ITC.NS": "ITC Ltd.",
    "JIOFIN.NS": "Jio Financial Services Ltd.",
    "JSWSTEEL.NS": "JSW Steel Ltd.",
    "KOTAKBANK.NS": "Kotak Mahindra Bank Ltd.",
    "LICI.NS": "Life Insurance Corp of India",
    "LT.NS": "Larsen & Toubro Ltd.",
    "LTIM.NS": "LTIMindtree Ltd.",
    "M&M.NS": "Mahindra & Mahindra Ltd.",
    "MARUTI.NS": "Maruti Suzuki India Ltd.",
    "MAXHEALTH.NS": "Max Healthcare Institute Ltd.",
    "NESTLEIND.NS": "Nestle India Ltd.",
    "NTPC.NS": "NTPC Ltd.",
    "ONGC.NS": "Oil & Natural Gas Corp Ltd.",
    "POWERGRID.NS": "Power Grid Corp of India Ltd.",
    "RELIANCE.NS": "Reliance Industries Ltd.",
    "SBILIFE.NS": "SBI Life Insurance Co. Ltd.",
    "SBIN.NS": "State Bank of India",
    "SHRIRAMFIN.NS": "Shriram Finance Ltd.",
    "SUNPHARMA.NS": "Sun Pharmaceutical Industries Ltd.",
    "TATACONSUM.NS": "Tata Consumer Products Ltd.",
    "TATAMOTORS.NS": "Tata Motors Ltd.",
    "TATASTEEL.NS": "Tata Steel Ltd.",
    "TCS.NS": "Tata Consultancy Services Ltd.",
    "TECHM.NS": "Tech Mahindra Ltd.",
    "TITAN.NS": "Titan Company Ltd.",
    "TMPV.NS": "Tata Motors PV Ltd.",
    "TRENT.NS": "Trent Ltd.",
    "ULTRACEMCO.NS": "UltraTech Cement Ltd.",
    "WIPRO.NS": "Wipro Ltd."
}

# Comprehensive Cache for Nifty 50 Sectors / Industries
SECTOR_CACHE: Dict[str, str] = {
    "ADANIENT.NS": "Metals & Mining",
    "ADANIPORTS.NS": "Services",
    "APOLLOHOSP.NS": "Healthcare",
    "ASIANPAINT.NS": "Consumer Durables",
    "AXISBANK.NS": "Financial Services",
    "BAJAJ-AUTO.NS": "Automobile and Auto Components",
    "BAJFINANCE.NS": "Financial Services",
    "BAJAJFINSV.NS": "Financial Services",
    "BEL.NS": "Capital Goods",
    "BHARTIARTL.NS": "Telecommunication",
    "CIPLA.NS": "Healthcare",
    "COALINDIA.NS": "Oil Gas & Consumable Fuels",
    "DRREDDY.NS": "Healthcare",
    "EICHERMOT.NS": "Automobile and Auto Components",
    "ETERNAL.NS": "Consumer Services",
    "GRASIM.NS": "Construction Materials",
    "HCLTECH.NS": "Information Technology",
    "HDFCBANK.NS": "Financial Services",
    "HDFCLIFE.NS": "Financial Services",
    "HINDALCO.NS": "Metals & Mining",
    "HINDUNILVR.NS": "Fast Moving Consumer Goods",
    "ICICIBANK.NS": "Financial Services",
    "INDIGO.NS": "Services",
    "INDUSINDBK.NS": "Financial Services",
    "INFY.NS": "Information Technology",
    "ITC.NS": "Fast Moving Consumer Goods",
    "JIOFIN.NS": "Financial Services",
    "JSWSTEEL.NS": "Metals & Mining",
    "KOTAKBANK.NS": "Financial Services",
    "LICI.NS": "Financial Services",
    "LT.NS": "Construction",
    "LTIM.NS": "Information Technology",
    "M&M.NS": "Automobile and Auto Components",
    "MARUTI.NS": "Automobile and Auto Components",
    "MAXHEALTH.NS": "Healthcare",
    "NESTLEIND.NS": "Fast Moving Consumer Goods",
    "NTPC.NS": "Power",
    "ONGC.NS": "Oil Gas & Consumable Fuels",
    "POWERGRID.NS": "Power",
    "RELIANCE.NS": "Oil Gas & Consumable Fuels",
    "SBILIFE.NS": "Financial Services",
    "SBIN.NS": "Financial Services",
    "SHRIRAMFIN.NS": "Financial Services",
    "SUNPHARMA.NS": "Healthcare",
    "TATACONSUM.NS": "Fast Moving Consumer Goods",
    "TATAMOTORS.NS": "Automobile and Auto Components",
    "TATASTEEL.NS": "Metals & Mining",
    "TCS.NS": "Information Technology",
    "TECHM.NS": "Information Technology",
    "TITAN.NS": "Consumer Durables",
    "TMPV.NS": "Automobile and Auto Components",
    "TRENT.NS": "Consumer Services",
    "ULTRACEMCO.NS": "Construction Materials",
    "WIPRO.NS": "Information Technology"
}

def get_company_name(ticker: str) -> str:
    """
    Returns the official company name for an NSE ticker symbol.
    """
    sym = ticker.strip().upper()
    if not sym.endswith(".NS"):
        sym = f"{sym}.NS"
    return COMPANY_NAME_CACHE.get(sym, sym.replace(".NS", ""))

def get_stock_sector(ticker: str) -> str:
    """
    Returns the official industry/sector classification for an NSE ticker symbol.
    """
    sym = ticker.strip().upper()
    if not sym.endswith(".NS"):
        sym = f"{sym}.NS"
    return SECTOR_CACHE.get(sym, "Diversified")

def get_nifty_250_tickers() -> List[str]:
    """
    Fetches the list of Nifty 50 symbols from the NSE archive and formats them for yfinance (.NS).
    Includes a robust fallback list of major NSE tickers in case of network issues.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(NIFTY_250_URL, headers=headers, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            if 'Symbol' in df.columns:
                for _, row in df.iterrows():
                    s = str(row['Symbol']).strip().upper()
                    c = str(row['Company Name']).strip() if 'Company Name' in df.columns else ""
                    ind = str(row['Industry']).strip() if 'Industry' in df.columns else ""
                    if s:
                        ticker_ns = f"{s}.NS"
                        if c:
                            COMPANY_NAME_CACHE[ticker_ns] = c
                        if ind:
                            SECTOR_CACHE[ticker_ns] = ind
                            
                symbols = df['Symbol'].tolist()
                # Format for yfinance
                tickers = [f"{sym.strip()}.NS" for sym in symbols if isinstance(sym, str)]
                return tickers
    except Exception as e:
        print(f"Error fetching Nifty 50 from NSE: {e}. Using fallback tickers.")
    
    # Fallback to major NSE liquid tickers if download fails
    fallback = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
        "BHARTIARTL.NS", "ITC.NS", "SBIN.NS", "LICI.NS", "LTIM.NS",
        "LT.NS", "HCLTECH.NS", "ASIANPAINT.NS", "AXISBANK.NS", "MARUTI.NS",
        "SUNPHARMA.NS", "KOTAKBANK.NS", "ULTRACEMCO.NS", "NTPC.NS", "TATAMOTORS.NS",
        "TITAN.NS", "POWERGRID.NS", "ADANIENT.NS", "BAJFINANCE.NS", "ADANIPORTS.NS",
        "COALINDIA.NS", "TATASTEEL.NS", "INDUSINDBK.NS", "JIOFIN.NS", "GRASIM.NS",
        "JSWSTEEL.NS", "HINDALCO.NS", "NESTLEIND.NS", "ADANIPOWER.NS", "HINDUNILVR.NS"
    ]
    return fallback

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculates the Relative Strength Index (RSI) using Wilder's smoothing technique.
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # Standard Wilder's smoothing using EWM
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculates the Average True Range (ATR) using Wilder's smoothing technique.
    """
    high = df['High']
    low = df['Low']
    prev_close = df['Close'].shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    return atr

def screen_stocks(tickers: List[str], logs: List[str] = None) -> List[Dict[str, Any]]:
    """
    Screens the list of tickers for Strategy v2:
    1. Today's close > Today's 20 DMA
    2. Yesterday's close <= Yesterday's 20 DMA
    3. Today's volume > 2.5 * 20-day average volume (> 250% breakout threshold)
    4. 14-day RSI is between 50 and 70 (bullish momentum but not overbought)
    5. Initial SL sized to 2 * ATR(14) below entry (no fixed clamp)
    6. Sector mapped for portfolio concentration limits (Max 3/sector)
    """
    if logs is None:
        logs = []
        
    # 1. Macro Sentiment Check: Skip entries if Nifty index news is negative
    nifty_sentiment = sentiment_analyzer.get_news_sentiment("Nifty 50 Index India")
    if nifty_sentiment == "NEGATIVE":
        msg = "[!] Macro Risk Alert: Nifty 50 News Sentiment is NEGATIVE. New breakout entries are paused to protect capital against broad market selling."
        print(msg)
        logs.append(msg)
        return []
    else:
        logs.append(f"[i] Macro Market Sentiment: {nifty_sentiment} (Trading active).")

    breakout_candidates = []
    
    # Download data in batches to be fast
    # Period 60d is sufficient to calculate 20 DMA (and 20 EMA), 14-day RSI, and 14-day ATR
    print(f"Downloading historical data for {len(tickers)} tickers...")
    try:
        data = yf.download(
            tickers, 
            period="60d", 
            interval="1d", 
            group_by="ticker", 
            threads=True,
            progress=False
        )
    except Exception as e:
        print(f"Error during batch download: {e}")
        return []
    
    for ticker in tickers:
        try:
            # Handle single vs multi-index dataframes from yfinance
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
            
            # Calculate daily moving averages, RSI, and ATR(14)
            df['20_SMA'] = df['Close'].rolling(window=20).mean()
            df['20_EMA'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['Vol_SMA_20'] = df['Volume'].rolling(window=20).mean()
            df['RSI_14'] = calculate_rsi(df['Close'], 14)
            df['ATR_14'] = calculate_atr(df, 14)
            
            # Check for NaN in indicators
            if (df['20_SMA'].isna().iloc[-1] or 
                df['Vol_SMA_20'].isna().iloc[-1] or 
                df['RSI_14'].isna().iloc[-1] or 
                df['ATR_14'].isna().iloc[-1]):
                continue
                
            # Current values (last row)
            close_today = df['Close'].iloc[-1]
            vol_today = df['Volume'].iloc[-1]
            sma_today = df['20_SMA'].iloc[-1]
            ema_today = df['20_EMA'].iloc[-1]
            vol_sma_today = df['Vol_SMA_20'].iloc[-1]
            rsi_today = df['RSI_14'].iloc[-1]
            atr_today = df['ATR_14'].iloc[-1]
            
            # Data validation guardrails: block penny stocks (< Rs 20) and low volume (< 50,000 shares)
            if close_today < 20.0:
                continue
            if vol_sma_today < 50000.0:
                continue
            # Previous values (second last row)
            close_yesterday = df['Close'].iloc[-2]
            sma_yesterday = df['20_SMA'].iloc[-2]
            
            # Conditions for Strategy v2:
            # 1. Price Breakout over 20 SMA
            price_breakout = (close_yesterday <= sma_yesterday) and (close_today > sma_today)
            # 2. Volume threshold upgraded to > 2.5x (250%) of 20-day avg volume
            volume_confirmed = vol_today > (2.5 * vol_sma_today)
            # 3. 14-period RSI between 50 and 70
            rsi_confirmed = 50 <= rsi_today <= 70
            
            if price_breakout and volume_confirmed and rsi_confirmed:
                # Check stock-specific news sentiment
                clean_sym = ticker.replace(".NS", "")
                stock_sentiment = sentiment_analyzer.get_news_sentiment(f"{clean_sym} stock news NSE")
                if stock_sentiment == "NEGATIVE":
                    msg = f"[!] Discarded {ticker}: Stock News Sentiment is NEGATIVE."
                    print(msg)
                    logs.append(msg)
                    continue
                    
                # v2 Stop-loss: 2x ATR(14) below entry, no fixed clamp
                initial_sl = float(close_today - (2.0 * atr_today))
                risk_per_share = float(2.0 * atr_today)
                target = float(close_today + (2.0 * risk_per_share)) # 1:2 Risk to Reward
                sector = get_stock_sector(ticker)
                
                breakout_candidates.append({
                    "ticker": ticker,
                    "close": float(close_today),
                    "volume": int(vol_today),
                    "avg_volume_20": float(vol_sma_today),
                    "sma_20": float(sma_today),
                    "ema_20": float(ema_today),
                    "volume_ratio": float(vol_today / vol_sma_today),
                    "rsi_14": float(rsi_today),
                    "atr_14": float(atr_today),
                    "initial_sl": initial_sl,
                    "target": target,
                    "sector": sector
                })
        except Exception as e:
            # Silently catch individual ticker errors
            continue
            
    # Sort candidates by volume breakout strength (volume_ratio) descending
    breakout_candidates.sort(key=lambda x: x['volume_ratio'], reverse=True)
    gc.collect()
    return breakout_candidates

if __name__ == "__main__":
    print("Testing screener...")
    tickers = get_nifty_250_tickers()
    print(f"Fetched {len(tickers)} tickers.")
    candidates = screen_stocks(tickers[:20]) # Test with a small batch
    print(f"Found {len(candidates)} candidates:")
    for c in candidates:
        print(c)

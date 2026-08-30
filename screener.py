import os
import io
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from typing import List, Dict, Any

# Nifty 250 List URL (Updated to Nifty 50)
NIFTY_250_URL = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"

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

def screen_stocks(tickers: List[str]) -> List[Dict[str, Any]]:
    """
    Screens the list of tickers for a 20 DMA Breakout with Volume and RSI confirmation:
    1. Today's close > Today's 20 DMA
    2. Yesterday's close <= Yesterday's 20 DMA
    3. Today's volume > 1.5 * 20-day average volume
    4. 14-day RSI is between 50 and 70 (bullish momentum but not overbought)
    """
    breakout_candidates = []
    
    # Download data in batches to be fast
    # Period 60d is sufficient to calculate 20 DMA (and 20 EMA) and 14-day RSI
    print(f"Downloading historical data for {len(tickers)} tickers...")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    })
    
    try:
        data = yf.download(
            tickers, 
            period="60d", 
            interval="1d", 
            group_by="ticker", 
            session=session,
            threads=True,
            timeout=15
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
            
            # Calculate daily moving averages & RSI
            df['20_SMA'] = df['Close'].rolling(window=20).mean()
            df['20_EMA'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['Vol_SMA_20'] = df['Volume'].rolling(window=20).mean()
            df['RSI_14'] = calculate_rsi(df['Close'], 14)
            
            # Check for NaN in indicators
            if df['20_SMA'].isna().iloc[-1] or df['Vol_SMA_20'].isna().iloc[-1] or df['RSI_14'].isna().iloc[-1]:
                continue
                
            # Current values (last row)
            close_today = df['Close'].iloc[-1]
            vol_today = df['Volume'].iloc[-1]
            sma_today = df['20_SMA'].iloc[-1]
            ema_today = df['20_EMA'].iloc[-1]
            vol_sma_today = df['Vol_SMA_20'].iloc[-1]
            rsi_today = df['RSI_14'].iloc[-1]
            
            # Previous values (second last row)
            close_yesterday = df['Close'].iloc[-2]
            sma_yesterday = df['20_SMA'].iloc[-2]
            
            # Conditions
            price_breakout = (close_yesterday <= sma_yesterday) and (close_today > sma_today)
            volume_confirmed = vol_today > (2.0 * vol_sma_today)
            rsi_confirmed = 50 <= rsi_today <= 70
            
            if price_breakout and volume_confirmed and rsi_confirmed:
                breakout_candidates.append({
                    "ticker": ticker,
                    "close": float(close_today),
                    "volume": int(vol_today),
                    "avg_volume_20": float(vol_sma_today),
                    "sma_20": float(sma_today),
                    "ema_20": float(ema_today),
                    "volume_ratio": float(vol_today / vol_sma_today),
                    "rsi_14": float(rsi_today)
                })
        except Exception as e:
            # Silently catch individual ticker errors
            continue
            
    # Sort candidates by volume breakout strength (volume_ratio) descending
    breakout_candidates.sort(key=lambda x: x['volume_ratio'], reverse=True)
    return breakout_candidates

if __name__ == "__main__":
    print("Testing screener...")
    tickers = get_nifty_250_tickers()
    print(f"Fetched {len(tickers)} tickers.")
    candidates = screen_stocks(tickers[:20]) # Test with a small batch
    print(f"Found {len(candidates)} candidates:")
    for c in candidates:
        print(c)

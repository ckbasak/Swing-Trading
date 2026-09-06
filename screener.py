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
import json
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from typing import List, Dict, Any, Optional
import sentiment_analyzer

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOP_50_PATH = os.path.join(PROJECT_ROOT, "curated_pool_top_50.csv")
TOP_101_PATH = os.path.join(PROJECT_ROOT, "curated_pool_top_101.csv")

def load_curated_metadata() -> Dict[str, Dict[str, str]]:
    meta = {}
    for path in [TOP_101_PATH, TOP_50_PATH]:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                for _, row in df.iterrows():
                    ticker = str(row.get("ticker", "")).strip()
                    if ticker:
                        meta[ticker] = {
                            "company": str(row.get("company", ticker)),
                            "sector": str(row.get("sector", "Diversified"))
                        }
            except Exception:
                pass
    return meta

COMPANY_METADATA = load_curated_metadata()

def get_curated_tickers(pool_type: str = "top_50") -> List[str]:
    csv_file = TOP_50_PATH if pool_type.lower() == "top_50" else TOP_101_PATH
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            return df["ticker"].dropna().tolist()
        except Exception as e:
            print(f"Error loading curated pool {csv_file}: {e}")
    # Fallback to defaults
    return list(COMPANY_METADATA.keys())[:50]

def get_nifty_250_tickers() -> List[str]:
    # Backward compatibility alias - returns default active curated pool
    pool_setting = os.environ.get("ACTIVE_STOCK_POOL", "curated_pool_top_50.csv")
    pool_type = "top_101" if "101" in pool_setting else "top_50"
    return get_curated_tickers(pool_type)

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df['High']
    low = df['Low']
    prev_close = df['Close'].shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def screen_stocks(tickers: Optional[List[str]] = None, check_sentiment: bool = True) -> List[Dict[str, Any]]:
    """
    Strategy 3: Hybrid Optimal Swing Screener
    - Universe: Curated High-Performing Stock Pool
    - Breakout: Close crosses above 20-day SMA
    - Volume Conviction: Volume > 2.25x 20-day Vol SMA (Sweet Spot)
    - Momentum: RSI 14 between 50 and 70
    - Targets: Target 1 at +2.0x ATR (50% partial), Target 2 at +4.5x ATR (runner)
    - Stop Loss: Dynamic 2.0x ATR below entry
    """
    if tickers is None:
        tickers = get_nifty_250_tickers()

    print(f"=== [Strategy 3] Scanning {len(tickers)} Curated Stocks ===")

    # Check macro sentiment
    macro_sentiment = "NEUTRAL"
    if check_sentiment:
        try:
            macro_res = sentiment_analyzer.get_news_sentiment("Nifty 50 Index India")
            macro_sentiment = macro_res.get("verdict", "NEUTRAL") if isinstance(macro_res, dict) else str(macro_res)
            print(f"Macro Sentiment for Nifty 50: {macro_sentiment}")
            if macro_sentiment.upper() == "NEGATIVE":
                print("Macro sentiment is NEGATIVE. Strategy 3 market guardrail active: skipping new entries.")
                return []
        except Exception as e:
            print(f"Macro sentiment check skipped: {e}")

    try:
        raw_data = yf.download(
            tickers,
            period="60d",
            interval="1d",
            group_by="ticker",
            threads=True,
            progress=False,
            timeout=20
        )
    except Exception as e:
        print(f"Error downloading batch data: {e}")
        return []

    vol_multiplier = float(os.environ.get("VOLUME_MULTIPLIER", "2.25"))
    candidates = []

    for ticker in tickers:
        try:
            if isinstance(raw_data.columns, pd.MultiIndex):
                if ticker not in raw_data.columns.levels[0]:
                    continue
                df = raw_data[ticker].dropna().copy()
            else:
                if ticker not in raw_data:
                    continue
                df = raw_data[[ticker]].dropna().copy()

            if len(df) < 25:
                continue

            df['SMA_20'] = df['Close'].rolling(window=20).mean()
            df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['Vol_SMA_20'] = df['Volume'].rolling(window=20).mean()
            df['RSI_14'] = calculate_rsi(df['Close'], 14)
            df['ATR_14'] = calculate_atr(df, 14)

            close_today = float(df['Close'].iloc[-1])
            close_yesterday = float(df['Close'].iloc[-2])
            sma_today = float(df['SMA_20'].iloc[-1])
            sma_yesterday = float(df['SMA_20'].iloc[-2])
            vol_today = float(df['Volume'].iloc[-1])
            vol_sma_today = float(df['Vol_SMA_20'].iloc[-1])
            rsi_today = float(df['RSI_14'].iloc[-1])
            atr_today = float(df['ATR_14'].iloc[-1])

            # Guardrails: price & liquidity
            if close_today < 20.0 or vol_sma_today < 25000.0:
                continue
            if np.isnan(sma_today) or np.isnan(vol_sma_today) or np.isnan(rsi_today) or np.isnan(atr_today):
                continue

            # Technical Conditions
            price_breakout = (close_yesterday <= sma_yesterday) and (close_today > sma_today)
            vol_confirmed = vol_today > (vol_multiplier * vol_sma_today)
            rsi_confirmed = 50.0 <= rsi_today <= 70.0

            if price_breakout and vol_confirmed and rsi_confirmed:
                # Dynamic ATR Levels
                if atr_today <= 0.01:
                    atr_today = close_today * 0.02

                sl_price = round(close_today - (2.0 * atr_today), 2)
                target_1 = round(close_today + (2.0 * atr_today), 2)
                target_2 = round(close_today + (4.5 * atr_today), 2)
                vol_ratio = round(vol_today / vol_sma_today, 2)

                meta = COMPANY_METADATA.get(ticker, {})
                company_name = meta.get("company", ticker)
                sector = meta.get("sector", "Diversified")

                # Individual stock news sentiment
                stock_sentiment = "NEUTRAL"
                if check_sentiment:
                    try:
                        query = f"{company_name} stock news NSE"
                        sent_res = sentiment_analyzer.get_news_sentiment(query)
                        stock_sentiment = sent_res.get("verdict", "NEUTRAL") if isinstance(sent_res, dict) else str(sent_res)
                        if stock_sentiment.upper() == "NEGATIVE":
                            print(f"Skipping {ticker} due to NEGATIVE news sentiment.")
                            continue
                    except Exception as e:
                        print(f"Sentiment check failed for {ticker}: {e}")

                candidates.append({
                    "ticker": ticker,
                    "company": company_name,
                    "sector": sector,
                    "close": round(close_today, 2),
                    "volume": int(vol_today),
                    "volume_ratio": vol_ratio,
                    "rsi": round(rsi_today, 2),
                    "atr": round(atr_today, 2),
                    "stop_loss": sl_price,
                    "target_1": target_1,
                    "target_2": target_2,
                    "sentiment": stock_sentiment
                })
        except Exception:
            continue

    # Clean memory
    del raw_data
    gc.collect()

    candidates.sort(key=lambda x: x['volume_ratio'], reverse=True)
    print(f"Found {len(candidates)} qualified Strategy 3 candidate(s).")
    return candidates

if __name__ == "__main__":
    cands = screen_stocks(check_sentiment=False)
    for c in cands[:10]:
        print(f"{c['ticker']} ({c['company']}) | P: Rs {c['close']} | Vol: {c['volume_ratio']}x | RSI: {c['rsi']} | T1: {c['target_1']} | T2: {c['target_2']} | SL: {c['stop_loss']}")

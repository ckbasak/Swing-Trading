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
ETF_POOL_PATH = os.path.join(PROJECT_ROOT, "curated_etf_pool.csv")

# Load Curated ETF Metadata
def load_etf_metadata() -> Dict[str, Dict[str, Any]]:
    meta = {}
    if os.path.exists(ETF_POOL_PATH):
        try:
            df = pd.read_csv(ETF_POOL_PATH)
            for _, row in df.iterrows():
                ticker = str(row.get("ticker", "")).strip().upper()
                if ticker:
                    meta[ticker] = {
                        "name": str(row.get("Company Name", ticker)),
                        "category": str(row.get("category", "Broad Market")),
                        "source_index": str(row.get("source_index", "NIFTY")),
                        "win_rate": float(row.get("win_rate", 70.0)),
                        "profit_factor": float(row.get("profit_factor", 3.5))
                    }
        except Exception as e:
            print(f"Error reading ETF pool: {e}")
    return meta

ETF_METADATA = load_etf_metadata()

def get_etf_tickers() -> List[str]:
    """Returns the list of 20 liquid NSE ETFs."""
    if ETF_METADATA:
        return list(ETF_METADATA.keys())
    return [
        "NIFTYBEES.NS", "BANKBEES.NS", "JUNIORBEES.NS", "MID150BEES.NS", "SETFNIF50.NS",
        "SETFNIFBK.NS", "NV20BEES.NS", "ALPHA.NS", "ICICIB22.NS", "CPSEETF.NS",
        "ITBEES.NS", "PSUBNKBEES.NS", "AUTOBEES.NS", "PHARMABEES.NS", "CONSUMBEES.NS",
        "GOLDBEES.NS", "HDFCGOLD.NS", "SILVERBEES.NS", "MON100.NS", "MAFANG.NS"
    ]

def get_curated_tickers(pool_type: str = "etf") -> List[str]:
    """Compatibility alias for ETF Strategy 1 runner."""
    return get_etf_tickers()

def get_stock_sector(ticker: str) -> str:
    """Returns asset category (Broad Market, Sectoral, Commodities, International)."""
    sym = ticker.strip().upper()
    if not sym.endswith(".NS"):
        sym = f"{sym}.NS"
    return ETF_METADATA.get(sym, {}).get("category", "Broad Market")

def get_company_name(ticker: str) -> str:
    """Returns ETF official fund name."""
    sym = str(ticker).strip().upper()
    clean_sym = sym.replace(".NS", "")
    with_ns = f"{clean_sym}.NS"
    return ETF_METADATA.get(with_ns, {}).get("name", ETF_METADATA.get(clean_sym, {}).get("name", clean_sym))

def get_stock_company(ticker: str) -> str:
    return get_company_name(ticker)

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

def screen_stocks(
    tickers: Optional[List[str]] = None, 
    logs: Optional[List[str]] = None,
    macro_data: Optional[Dict[str, Any]] = None,
    check_sentiment: bool = True
) -> List[Dict[str, Any]]:
    """
    ETF Strategy 1: Systematic Dual-Target Swing Screener
    - Universe: 20 Liquid NSE ETFs (Indices, Sectoral, Commodities, Global Tech)
    - Breakout: Close crosses above 20-day SMA
    - Volume Surge: Volume > 1.15x 20-day Vol SMA (Optimized for ETF AP/MM flow)
    - Momentum: RSI 14 between 50 and 70
    - Targets: Target 1 at +2.0x ATR (50% partial), Target 2 at +4.5x ATR (runner)
    - Stop Loss: Dynamic 2.0x ATR below entry
    """
    if logs is None:
        logs = []
    if tickers is None:
        tickers = get_etf_tickers()

    print(f"=== [ETF Strategy 1] Scanning {len(tickers)} Liquid NSE ETFs ===")

    # 1. Macro Guardrails
    if macro_data is None and check_sentiment:
        try:
            macro_data = sentiment_analyzer.get_comprehensive_market_macro_sentiment()
        except Exception as e:
            print(f"Notice: macro sentiment check failed: {e}")

    if macro_data:
        breakout_guard = macro_data.get("guardrail_breakouts", "ALLOW")
        regime = macro_data.get("market_regime", "RISK-ON")
        badge = macro_data.get("color_badge", "🟢")
        color = macro_data.get("color", "GREEN")
        
        if breakout_guard == "HALT" or color == "RED":
            msg = f"{badge} Macro Alert: Regime is {regime} (Breakouts: HALT). High market volatility."
            print(msg)
            logs.append(msg)
        elif breakout_guard == "SELECTIVE" or color == "YELLOW":
            msg = f"{badge} Macro Caution: Regime is {regime} (Breakouts: SELECTIVE). Prioritizing high-liquidity ETFs."
            print(msg)
            logs.append(msg)
        else:
            msg = f"{badge} Macro Sentiment: {regime} (Breakouts: ALLOW). ETF Swing trading active."
            print(msg)
            logs.append(msg)

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
        print(f"Error downloading ETF batch data: {e}")
        logs.append(f"Error downloading ETF batch data: {e}")
        return []

    vol_multiplier = float(os.environ.get("VOLUME_MULTIPLIER", "1.15"))
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

            # Turnover / Liquidity filter: Daily average turnover >= Rs 5 Lakhs
            daily_turnover = vol_sma_today * close_today
            if daily_turnover < 500000.0:
                continue
            if np.isnan(sma_today) or np.isnan(vol_sma_today) or np.isnan(rsi_today) or np.isnan(atr_today):
                continue

            # Technical Conditions: SMA Breakout, ETF Volume Multiplier (1.15x), Bullish RSI (50-70)
            price_breakout = (close_yesterday <= sma_yesterday) and (close_today > sma_today)
            vol_confirmed = vol_today > (vol_multiplier * vol_sma_today)
            rsi_confirmed = 50.0 <= rsi_today <= 70.0

            if price_breakout and vol_confirmed and rsi_confirmed:
                if atr_today <= 0.01:
                    atr_today = close_today * 0.015

                sl_price = round(close_today - (2.0 * atr_today), 2)
                target_1 = round(close_today + (2.0 * atr_today), 2)
                target_2 = round(close_today + (4.5 * atr_today), 2)
                vol_ratio = round(vol_today / vol_sma_today, 2)

                fund_name = get_company_name(ticker)
                category = get_stock_sector(ticker)

                candidates.append({
                    "ticker": ticker,
                    "company": fund_name,
                    "sector": category,
                    "close": round(close_today, 2),
                    "volume": int(vol_today),
                    "volume_ratio": vol_ratio,
                    "rsi": round(rsi_today, 2),
                    "rsi_14": round(rsi_today, 2),
                    "atr": round(atr_today, 2),
                    "atr_14": round(atr_today, 2),
                    "stop_loss": sl_price,
                    "target_1": target_1,
                    "target_2": target_2,
                    "sentiment": "BULLISH"
                })
        except Exception:
            continue

    del raw_data
    gc.collect()

    candidates.sort(key=lambda x: x['volume_ratio'], reverse=True)
    print(f"Found {len(candidates)} qualified ETF Strategy 1 candidate(s).")
    return candidates

if __name__ == "__main__":
    cands = screen_stocks(check_sentiment=False)
    for c in cands[:10]:
        print(f"{c['ticker']} ({c['company']}) | Cat: {c['sector']} | P: Rs {c['close']} | Vol: {c['volume_ratio']}x | RSI: {c['rsi']} | T1: {c['target_1']} | T2: {c['target_2']} | SL: {c['stop_loss']}")
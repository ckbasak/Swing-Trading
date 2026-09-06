import os
import gc
import json
import gspread
import math
import time
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, date
from typing import List, Dict, Any, Tuple, Optional
from google.oauth2.service_account import Credentials

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(PROJECT_ROOT, "service_account.json")
LOCAL_DB_FILE = os.path.join(PROJECT_ROOT, "local_portfolio_data.json")
DEFAULT_SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "NSE_Swing_Trading_Portfolio_3")
INITIAL_CAPITAL = 100000.0

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def _load_env():
    env_file = os.path.join(PROJECT_ROOT, ".env")
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

def get_gspread_client() -> Optional[gspread.Client]:
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        return None
    try:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"Notice: gspread auth failed: {e}")
        return None

def _load_local_db() -> Dict[str, Any]:
    if os.path.exists(LOCAL_DB_FILE):
        try:
            with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    db = {
        "account": {
            "initial_capital": INITIAL_CAPITAL,
            "cash": INITIAL_CAPITAL,
            "portfolio_value": INITIAL_CAPITAL,
            "realized_pnl": 0.0,
            "total_return_pct": 0.0,
            "cagr_pct": 0.0,
            "xirr_pct": 0.0,
            "days_active": 0,
            "risk_pct": 6.0,
            "active_pool": "Top 50 Champions"
        },
        "holdings": [],
        "closed_trades": [],
        "telegram_chats": []
    }
    _save_local_db(db)
    return db

def _save_local_db(data: Dict[str, Any]):
    try:
        with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving local db: {e}")

def get_or_open_portfolio_sheet(client: gspread.Client) -> Optional[gspread.Spreadsheet]:
    target_name = os.environ.get("SPREADSHEET_NAME", DEFAULT_SPREADSHEET_NAME)
    try:
        return client.open(target_name)
    except Exception:
        return None

def calculate_xirr(cash_flows: List[Tuple[datetime, float]], guess: float = 0.1) -> float:
    if not cash_flows or len(cash_flows) < 2:
        return 0.0
    t0 = cash_flows[0][0]
    total_days = max((t - t0).days for t, _ in cash_flows)
    if total_days <= 0:
        return 0.0
    def xnpv(rate):
        return sum(cf / ((1.0 + rate) ** ((t - t0).days / 365.25)) for t, cf in cash_flows)
    def xnpv_prime(rate):
        return sum(-((t - t0).days / 365.25) * cf / ((1.0 + rate) ** (((t - t0).days / 365.25) + 1.0)) for t, cf in cash_flows)
    rate = guess
    for _ in range(100):
        val = xnpv(rate)
        val_prime = xnpv_prime(rate)
        if abs(val_prime) < 1e-7:
            return 0.0
        new_rate = rate - (val / val_prime)
        if abs(new_rate - rate) < 1e-6:
            res = round(new_rate * 100.0, 2)
            if np.isnan(res) or np.isinf(res):
                return 0.0
            return res
        rate = new_rate
        if rate <= -1.0:
            rate = -0.999
    return 0.0

def get_account_summary() -> Dict[str, Any]:
    client = get_gspread_client()
    if client:
        sh = get_or_open_portfolio_sheet(client)
        if sh:
            try:
                ws = sh.worksheet("Account")
                vals = ws.row_values(2)
                if vals:
                    return {
                        "initial_capital": float(vals[0]),
                        "cash": float(vals[1]),
                        "portfolio_value": float(vals[2]),
                        "realized_pnl": float(vals[3]),
                        "total_return_pct": float(str(vals[4]).replace("%", "")),
                        "cagr_pct": float(str(vals[5]).replace("%", "")),
                        "xirr_pct": float(str(vals[6]).replace("%", "")),
                        "days_active": int(vals[7]) if len(vals) > 7 else 0,
                        "risk_pct": float(str(vals[8]).replace("%", "")) if len(vals) > 8 else 6.0,
                        "active_pool": str(vals[9]) if len(vals) > 9 else "Top 50 Champions"
                    }
            except Exception:
                pass
    db = _load_local_db()
    return db.get("account", {})

def get_holdings() -> List[Dict[str, Any]]:
    client = get_gspread_client()
    if client:
        sh = get_or_open_portfolio_sheet(client)
        if sh:
            try:
                ws = sh.worksheet("Holdings")
                return ws.get_all_records()
            except Exception:
                pass
    db = _load_local_db()
    return db.get("holdings", [])

def get_closed_trades() -> List[Dict[str, Any]]:
    client = get_gspread_client()
    if client:
        sh = get_or_open_portfolio_sheet(client)
        if sh:
            try:
                ws = sh.worksheet("ClosedTrades")
                return ws.get_all_records()
            except Exception:
                pass
    db = _load_local_db()
    return db.get("closed_trades", [])

def calculate_position_size(entry_price: float, atr: float, portfolio_value: float, available_cash: float) -> int:
    risk_pct = float(os.environ.get("RISK_PERCENT", "6.0")) / 100.0
    risk_amount = portfolio_value * risk_pct
    risk_per_share = 2.0 * atr if atr > 0 else entry_price * 0.04
    qty_by_risk = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
    qty_by_cash = int(available_cash / entry_price) if entry_price > 0 else 0
    qty = min(qty_by_risk, qty_by_cash)
    return max(2, qty) if (qty >= 2 and (qty * entry_price) <= available_cash) else 0

def add_position(ticker: str, company: str, sector: str, entry_price: float, atr: float) -> Optional[Dict[str, Any]]:
    holdings = get_holdings()
    max_total = int(os.environ.get("MAX_TOTAL_POSITIONS", "10"))
    max_sector = int(os.environ.get("MAX_POSITIONS_PER_SECTOR", "3"))
    
    if len(holdings) >= max_total:
        print(f"Max positions ({max_total}) reached. Skipping {ticker}.")
        return None
        
    sector_count = sum(1 for h in holdings if str(h.get("Sector", "")).strip().lower() == sector.strip().lower())
    if sector_count >= max_sector:
        print(f"Sector '{sector}' cap ({max_sector}) reached. Skipping {ticker}.")
        return None
        
    if any(h.get("Ticker") == ticker for h in holdings):
        print(f"{ticker} is already in portfolio. Skipping.")
        return None
        
    acc = get_account_summary()
    cash = acc.get("cash", INITIAL_CAPITAL)
    port_val = acc.get("portfolio_value", INITIAL_CAPITAL)
    
    qty = calculate_position_size(entry_price, atr, port_val, cash)
    if qty < 2:
        print(f"Insufficient cash or risk size for {ticker}. Sized qty: {qty}")
        return None
        
    entry_val = round(qty * entry_price, 2)
    initial_sl = round(entry_price - (2.0 * atr), 2)
    target_1 = round(entry_price + (2.0 * atr), 2)
    target_2 = round(entry_price + (4.5 * atr), 2)
    entry_date = datetime.now().strftime("%Y-%m-%d")
    
    new_pos = {
        "Ticker": ticker, "Company": company, "Sector": sector, "Quantity": qty,
        "Entry Price": round(entry_price, 2), "Entry Value": entry_val,
        "Initial SL": initial_sl, "Current SL": initial_sl, "Target 1": target_1, "Target 2": target_2,
        "Partial Booked": "FALSE", "Entry Date": entry_date,
        "Current Price": round(entry_price, 2), "Current Value": entry_val,
        "Unrealized PnL": 0.0, "Unrealized PnL %": "0.0%"
    }
    
    # Update local DB
    db = _load_local_db()
    db["holdings"].append(new_pos)
    db["account"]["cash"] = round(cash - entry_val, 2)
    _save_local_db(db)
    
    # Try Google Sheets
    client = get_gspread_client()
    if client:
        sh = get_or_open_portfolio_sheet(client)
        if sh:
            try:
                h_ws = sh.worksheet("Holdings")
                h_ws.append_row(list(new_pos.values()))
                a_ws = sh.worksheet("Account")
                a_ws.update_cell(2, 2, round(cash - entry_val, 2))
            except Exception as e:
                print(f"Google sheet update error: {e}")
                
    print(f"[Strategy 3] Added {ticker} x {qty} @ Rs {entry_price}. T1: Rs {target_1}, T2: Rs {target_2}, SL: Rs {initial_sl}")
    return new_pos

def update_portfolio_and_exits(current_quotes: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    holdings = get_holdings()
    if not holdings:
        return {"exited": [], "partial_exited": []}
        
    tickers = [h["Ticker"] for h in holdings]
    if current_quotes is None:
        current_quotes = {}
        try:
            raw = yf.download(tickers, period="5d", interval="1d", group_by="ticker", threads=True, progress=False)
            for t in tickers:
                df = raw[t].dropna() if isinstance(raw.columns, pd.MultiIndex) else raw[[t]].dropna()
                if not df.empty:
                    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
                    current_quotes[t] = {
                        "high": float(df['High'].iloc[-1]),
                        "low": float(df['Low'].iloc[-1]),
                        "close": float(df['Close'].iloc[-1]),
                        "open": float(df['Open'].iloc[-1]),
                        "ema_20": float(df['EMA_20'].iloc[-1])
                    }
        except Exception as e:
            print(f"Error fetching exit quotes: {e}")
            
    db = _load_local_db()
    cash = db["account"]["cash"]
    realized_pnl = db["account"]["realized_pnl"]
    
    rows_to_keep = []
    exited_trades = []
    partial_exited = []
    total_open_val = 0.0
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for h in holdings:
        t = h["Ticker"]
        qty = int(h["Quantity"])
        entry_p = float(h["Entry Price"])
        cur_sl = float(h["Current SL"])
        init_sl = float(h["Initial SL"])
        target_1 = float(h["Target 1"])
        target_2 = float(h["Target 2"])
        partial_booked = str(h.get("Partial Booked", "FALSE")).strip().upper() == "TRUE"
        sector = h.get("Sector", "Diversified")
        company = h.get("Company", t)
        entry_date_str = str(h.get("Entry Date", today_str))
        
        bar = current_quotes.get(t, {"close": entry_p, "high": entry_p, "low": entry_p, "open": entry_p, "ema_20": cur_sl})
        high_p = bar["high"]
        low_p = bar["low"]
        close_p = bar["close"]
        open_p = bar["open"]
        ema_20 = bar["ema_20"]
        
        try:
            h_days = (datetime.now() - datetime.strptime(entry_date_str, "%Y-%m-%d")).days
        except Exception:
            h_days = 1
            
        # Target 1 (50% partial profit booking)
        if not partial_booked and high_p >= target_1:
            sell_qty = max(1, qty // 2)
            exit_p = max(open_p, target_1) if open_p >= target_1 else target_1
            pnl = (exit_p - entry_p) * sell_qty
            pnl_pct = ((exit_p - entry_p) / entry_p) * 100.0
            
            trade_rec = {
                "Ticker": t, "Company": company, "Sector": sector, "Quantity": sell_qty,
                "Entry Price": round(entry_p, 2), "Entry Value": round(sell_qty * entry_p, 2),
                "Exit Price": round(exit_p, 2), "Exit Value": round(sell_qty * exit_p, 2),
                "Realized PnL": round(pnl, 2), "Realized PnL %": f"{pnl_pct:+.2f}%",
                "Holding Days": h_days, "Entry Date": entry_date_str, "Exit Date": today_str,
                "Exit Reason": "Target 1 Hit (50% Partial Lock)"
            }
            db["closed_trades"].append(trade_rec)
            cash += exit_p * sell_qty
            realized_pnl += pnl
            qty -= sell_qty
            partial_booked = True
            
            # Shift Stop Loss to Break-Even (Entry Price)
            cur_sl = max(cur_sl, entry_p)
            partial_exited.append({
                "ticker": t, "company": company, "qty": sell_qty, "exit_price": exit_p, "pnl": pnl, "pnl_pct": pnl_pct
            })
            print(f"[Strategy 3] Target 1 Hit for {t}: Sold {sell_qty} shares @ Rs {exit_p}. Stop Loss shifted to Break-Even (Rs {entry_p}).")
            
        # Check Exits on remaining quantity
        fully_exited = False
        full_exit_price = 0.0
        full_exit_reason = ""
        
        if high_p >= target_2:
            full_exit_price = max(open_p, target_2) if open_p >= target_2 else target_2
            full_exit_reason = "Target 2 Hit (Full Extension)"
            fully_exited = True
        elif low_p <= cur_sl:
            full_exit_price = min(open_p, cur_sl) if open_p <= cur_sl else cur_sl
            full_exit_reason = "Break-Even / Trailing Stop Hit (Runner)" if partial_booked else "Stop Loss Hit"
            fully_exited = True
            
        if fully_exited:
            pnl = (full_exit_price - entry_p) * qty
            pnl_pct = ((full_exit_price - entry_p) / entry_p) * 100.0
            trade_rec = {
                "Ticker": t, "Company": company, "Sector": sector, "Quantity": qty,
                "Entry Price": round(entry_p, 2), "Entry Value": round(qty * entry_p, 2),
                "Exit Price": round(full_exit_price, 2), "Exit Value": round(qty * full_exit_price, 2),
                "Realized PnL": round(pnl, 2), "Realized PnL %": f"{pnl_pct:+.2f}%",
                "Holding Days": h_days, "Entry Date": entry_date_str, "Exit Date": today_str,
                "Exit Reason": full_exit_reason
            }
            db["closed_trades"].append(trade_rec)
            cash += full_exit_price * qty
            realized_pnl += pnl
            exited_trades.append({
                "ticker": t, "company": company, "qty": qty, "exit_price": full_exit_price, "pnl": pnl, "pnl_pct": pnl_pct, "reason": full_exit_reason
            })
            print(f"[Strategy 3] Exited {t} x {qty} @ Rs {full_exit_price} ({full_exit_reason}).")
        else:
            if ema_20 > cur_sl:
                cur_sl = round(ema_20, 2)
            cur_val = round(qty * close_p, 2)
            unreal_pnl = round(cur_val - (qty * entry_p), 2)
            unreal_pnl_pct = round(((close_p - entry_p) / entry_p) * 100.0, 2)
            total_open_val += cur_val
            
            rows_to_keep.append({
                "Ticker": t, "Company": company, "Sector": sector, "Quantity": qty,
                "Entry Price": round(entry_p, 2), "Entry Value": round(qty * entry_p, 2),
                "Initial SL": init_sl, "Current SL": cur_sl, "Target 1": target_1, "Target 2": target_2,
                "Partial Booked": "TRUE" if partial_booked else "FALSE", "Entry Date": entry_date_str,
                "Current Price": round(close_p, 2), "Current Value": cur_val,
                "Unrealized PnL": unreal_pnl, "Unrealized PnL %": f"{unreal_pnl_pct:+.2f}%"
            })
            
    # Update local DB state
    db["holdings"] = rows_to_keep
    new_portfolio_val = round(cash + total_open_val, 2)
    net_pnl = round(new_portfolio_val - INITIAL_CAPITAL, 2)
    ret_pct = round((net_pnl / INITIAL_CAPITAL) * 100.0, 2)
    
    db["account"]["cash"] = round(cash, 2)
    db["account"]["portfolio_value"] = new_portfolio_val
    db["account"]["realized_pnl"] = round(realized_pnl, 2)
    db["account"]["total_return_pct"] = ret_pct
    _save_local_db(db)
    
    # Try updating Google Sheets if accessible
    client = get_gspread_client()
    if client:
        sh = get_or_open_portfolio_sheet(client)
        if sh:
            try:
                h_ws = sh.worksheet("Holdings")
                h_ws.clear()
                headers = [
                    "Ticker", "Company", "Sector", "Quantity", "Entry Price", "Entry Value",
                    "Initial SL", "Current SL", "Target 1", "Target 2", "Partial Booked",
                    "Entry Date", "Current Price", "Current Value", "Unrealized PnL", "Unrealized PnL %"
                ]
                h_ws.append_row(headers)
                for r in rows_to_keep:
                    h_ws.append_row(list(r.values()))
                a_ws = sh.worksheet("Account")
                a_ws.update_cell(2, 2, round(cash, 2))
                a_ws.update_cell(2, 3, new_portfolio_val)
                a_ws.update_cell(2, 4, round(realized_pnl, 2))
                a_ws.update_cell(2, 5, f"{ret_pct:+.2f}%")
            except Exception as e:
                print(f"Google Sheet sync notice: {e}")
                
    return {"exited": exited_trades, "partial_exited": partial_exited}

if __name__ == "__main__":
    acc = get_account_summary()
    print("Strategy 3 Portfolio Manager Active.")
    print(f"Account: Portfolio Value=Rs {acc['portfolio_value']:.2f}, Cash=Rs {acc['cash']:.2f}, Risk={acc.get('risk_pct', 6.0)}%")
    print(f"Open Holdings: {len(get_holdings())}")

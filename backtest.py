import os
import io
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# Nifty 250 URL
NIFTY_250_URL = "https://archives.nseindia.com/content/indices/ind_niftylargemidcap250list.csv"

def get_tickers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(NIFTY_250_URL, headers=headers, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            if 'Symbol' in df.columns:
                return [f"{sym.strip()}.NS" for sym in df['Symbol'].tolist() if isinstance(sym, str)]
    except Exception as e:
        print(f"Error downloading Nifty 250 tickers: {e}. Using fallbacks.")
    return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS"]

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def run_backtest():
    print("Initializing Backtest...")
    print("Step 1: Fetching Nifty 250 Ticker List...")
    tickers = get_tickers()
    # Remove duplicates
    tickers = list(set(tickers))
    print(f"Total Tickers discovered: {len(tickers)}")
    
    # Download 3 years of data
    print("Step 2: Downloading 3 years of daily historical data from Yahoo Finance...")
    try:
        data = yf.download(tickers, period="3y", interval="1d", group_by="ticker", threads=True, timeout=30)
    except Exception as e:
        print(f"Failed to download data: {e}")
        return
        
    print("Step 3: Pre-calculating indicators for each ticker...")
    ticker_dfs = {}
    for t in tickers:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if t not in data.columns.levels[0]:
                    continue
                df = data[t].dropna(subset=["Close"])
            else:
                if t not in data:
                    continue
                df = data[[t]].dropna()
            
            if len(df) < 50:
                continue
                
            df['20_SMA'] = df['Close'].rolling(window=20).mean()
            df['20_EMA'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['Vol_SMA_20'] = df['Volume'].rolling(window=20).mean()
            df['RSI_14'] = calculate_rsi(df['Close'], 14)
            df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA_20']
            
            # Store clean, drop initial NaNs
            ticker_dfs[t] = df.dropna(subset=['20_SMA', 'Vol_SMA_20', 'RSI_14'])
        except Exception:
            continue
            
    print(f"Successfully processed {len(ticker_dfs)} tickers.")
    
    # Download Nifty 50 Index for comparison
    print("Downloading Nifty 50 Index (^NSEI) for comparison...")
    nifty_df = yf.download("^NSEI", period="3y", interval="1d")
    if isinstance(nifty_df.columns, pd.MultiIndex):
        nifty_df.columns = nifty_df.columns.droplevel(1)
    nifty_df = nifty_df.dropna(subset=["Close"])
    
    # Get sorted trading dates from Nifty index (avoiding new-listing intersection limitations)
    trading_dates = sorted(list(nifty_df.index))
    
    # Filter for recent bull phase (Aug 1, 2025 to Jan 1, 2026)
    start_date_str = "2025-08-01"
    end_date_str = "2026-01-01"
    start_dt = pd.to_datetime(start_date_str)
    end_dt = pd.to_datetime(end_date_str)
    if nifty_df.index.tz is not None:
        start_dt = start_dt.tz_localize(nifty_df.index.tz)
        end_dt = end_dt.tz_localize(nifty_df.index.tz)
        
    trading_dates = [d for d in trading_dates if start_dt <= d <= end_dt]
    print(f"Total trading days to simulate in bull phase ({start_date_str} to {end_date_str}): {len(trading_dates)}")
    
    # Backtest Parameters
    initial_capital = 1000000.0 # 10 Lacs
    cash = initial_capital
    portfolio_value = initial_capital
    
    open_positions = [] # list of dicts
    closed_trades = []  # list of dicts
    equity_curve = []   # list of tuples (date, portfolio_value, nifty_value)
    
    initial_nifty = float(nifty_df.loc[trading_dates[0], "Close"])
    
    print("Step 4: Running Chronological Simulation...")
    for idx, date in enumerate(trading_dates):
        # A. SYNC PORTFOLIO / CHECK EXITS
        active_positions = []
        for p in open_positions:
            t = p["ticker"]
            df = ticker_dfs[t]
            
            # Skip if ticker has no data for today
            if date not in df.index:
                active_positions.append(p)
                continue
                
            today_row = df.loc[date]
            high = float(today_row["High"])
            low = float(today_row["Low"])
            close = float(today_row["Close"])
            open_p = float(today_row["Open"])
            ema_20 = float(today_row["20_EMA"])
            
            target = p["target"]
            sl = p["current_sl"]
            qty = p["qty"]
            entry_val = p["entry_val"]
            
            # Check Stop Loss hit (low is below or equal to SL)
            if low <= sl:
                # Conservative exit: exit at stop loss or today's open if open is lower (gap down)
                exit_price = min(open_p, sl)
                exit_val = qty * exit_price
                pnl = exit_val - entry_val
                closed_trades.append({
                    "ticker": t,
                    "entry_date": p["entry_date"],
                    "entry_price": p["entry_price"],
                    "qty": qty,
                    "entry_val": entry_val,
                    "exit_date": date.strftime("%Y-%m-%d"),
                    "exit_price": exit_price,
                    "exit_val": exit_val,
                    "pnl": pnl,
                    "pnl_pct": (pnl / entry_val) * 100,
                    "reason": "Stop Loss Hit"
                })
                cash += exit_val
            # Check Target hit (high is above or equal to Target)
            elif high >= target:
                exit_price = target
                exit_val = qty * exit_price
                pnl = exit_val - entry_val
                closed_trades.append({
                    "ticker": t,
                    "entry_date": p["entry_date"],
                    "entry_price": p["entry_price"],
                    "qty": qty,
                    "entry_val": entry_val,
                    "exit_date": date.strftime("%Y-%m-%d"),
                    "exit_price": exit_price,
                    "exit_val": exit_val,
                    "pnl": pnl,
                    "pnl_pct": (pnl / entry_val) * 100,
                    "reason": "Target Hit"
                })
                cash += exit_val
            else:
                # Update Trailing Stop (EMA 20)
                new_sl = max(sl, ema_20)
                p["current_sl"] = new_sl
                active_positions.append(p)
                
        open_positions = active_positions
        
        # B. CALCULATE PORTFOLIO VALUE
        holdings_value = 0.0
        for p in open_positions:
            t = p["ticker"]
            df = ticker_dfs[t]
            if date in df.index:
                holdings_value += p["qty"] * float(df.loc[date, "Close"])
            else:
                holdings_value += p["qty"] * p["entry_price"] # Fallback
                
        portfolio_value = cash + holdings_value
        
        # C. SCAN MARKET FOR NEW ENTRIES
        # Sizing risk amount: 1% of total portfolio value
        risk_per_trade = portfolio_value * 0.01
        
        # Find candidates today (excluding stocks already in holdings)
        candidates = []
        open_tickers = {p["ticker"] for p in open_positions}
        
        for t, df in ticker_dfs.items():
            if t in open_tickers:
                continue
                
            # Need today and yesterday rows
            if date not in df.index:
                continue
                
            loc_idx = df.index.get_loc(date)
            if loc_idx < 1:
                continue
                
            today_row = df.iloc[loc_idx]
            yesterday_row = df.iloc[loc_idx - 1]
            
            close_today = float(today_row["Close"])
            sma_today = float(today_row["20_SMA"])
            vol_today = float(today_row["Volume"])
            vol_sma_today = float(today_row["Vol_SMA_20"])
            rsi_today = float(today_row["RSI_14"])
            
            close_yesterday = float(yesterday_row["Close"])
            sma_yesterday = float(yesterday_row["20_SMA"])
            
            # Conditions
            price_breakout = (close_yesterday <= sma_yesterday) and (close_today > sma_today)
            volume_confirmed = vol_today > (1.5 * vol_sma_today)
            rsi_confirmed = 50 <= rsi_today <= 70
            
            if price_breakout and volume_confirmed and rsi_confirmed:
                candidates.append({
                    "ticker": t,
                    "close": close_today,
                    "sma_20": sma_today,
                    "vol_ratio": float(today_row["Vol_Ratio"])
                })
                
        # Sort candidates by volume breakout ratio descending
        candidates.sort(key=lambda x: x["vol_ratio"], reverse=True)
        
        # E. EXECUTE BUYS
        for c in candidates:
            t = c["ticker"]
            entry_price = c["close"]
            initial_sl = c["sma_20"]
            
            risk_per_share = entry_price - initial_sl
            if risk_per_share <= 0:
                continue
                
            # Quantity based on 1% risk
            qty = int(risk_per_trade // risk_per_share)
            if qty <= 0:
                continue
                
            cost = qty * entry_price
            
            # Scale down if cost exceeds cash
            if cost > cash:
                qty = int(cash // entry_price)
                cost = qty * entry_price
                
            if qty > 0 and cost <= cash:
                cash -= cost
                target = entry_price + 2 * (entry_price - initial_sl)
                open_positions.append({
                    "ticker": t,
                    "entry_date": date.strftime("%Y-%m-%d"),
                    "entry_price": entry_price,
                    "qty": qty,
                    "entry_val": cost,
                    "initial_sl": initial_sl,
                    "current_sl": initial_sl,
                    "target": target
                })
                
        # Record equity curve
        current_nifty = float(nifty_df.loc[date, "Close"])
        nifty_return = ((current_nifty - initial_nifty) / initial_nifty) * 100
        strategy_return = ((portfolio_value - initial_capital) / initial_capital) * 100
        equity_curve.append((date.strftime("%Y-%m-%d"), portfolio_value, strategy_return, nifty_return))
        
    print("Step 5: Compiling Performance Metrics...")
    # Calculate Metrics
    df_equity = pd.DataFrame(equity_curve, columns=["Date", "Portfolio Value", "Strategy Return (%)", "Nifty Return (%)"])
    df_trades = pd.DataFrame(closed_trades)
    
    total_trades = len(df_trades)
    if total_trades > 0:
        wins = df_trades[df_trades["pnl"] > 0]
        win_rate = (len(wins) / total_trades) * 100
        avg_win = wins["pnl"].mean() if len(wins) > 0 else 0
        losses = df_trades[df_trades["pnl"] <= 0]
        avg_loss = losses["pnl"].mean() if len(losses) > 0 else 0
        profit_factor = (wins["pnl"].sum() / abs(losses["pnl"].sum())) if len(losses) > 0 and losses["pnl"].sum() != 0 else float('inf')
    else:
        win_rate = 0.0
        avg_win = 0.0
        avg_loss = 0.0
        profit_factor = 0.0
        
    final_value = portfolio_value
    net_profit = final_value - initial_capital
    total_return_pct = (net_profit / initial_capital) * 100
    
    # Calculate Max Drawdown
    df_equity["Peak"] = df_equity["Portfolio Value"].cummax()
    df_equity["Drawdown (%)"] = ((df_equity["Portfolio Value"] - df_equity["Peak"]) / df_equity["Peak"]) * 100
    max_dd = df_equity["Drawdown (%)"].min()
    
    # Compare index return
    final_nifty_close = float(nifty_df.loc[trading_dates[-1], "Close"])
    nifty_final_return = ((final_nifty_close - initial_nifty) / initial_nifty) * 100
    
    # Save reports
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    df_trades.to_csv(os.path.join(workspace_dir, "backtest_trades_history.csv"), index=False)
    df_equity.to_csv(os.path.join(workspace_dir, "backtest_equity_curve.csv"), index=False)
    
    print("\n=======================================================")
    print("BACKTESTING PERFORMANCE SUMMARY REPORT")
    print("=======================================================")
    print(f"Period Simulated:   {trading_dates[0].strftime('%d-%b-%Y')} to {trading_dates[-1].strftime('%d-%b-%Y')} (3 Years)")
    print(f"Initial Capital:    INR {initial_capital:,.2f}")
    print(f"Final Account Value:INR {final_value:,.2f}")
    print(f"Net Profit:         INR {net_profit:,.2f}")
    print(f"Strategy Return:    {total_return_pct:+.2f}%")
    print(f"Nifty 50 Return:    {nifty_final_return:+.2f}%")
    print(f"Outperformance:     {total_return_pct - nifty_final_return:+.2f}%")
    print("-------------------------------------------------------")
    print(f"Total Trades:       {total_trades}")
    print(f"Winning Trades:     {len(wins) if total_trades > 0 else 0}")
    print(f"Losing Trades:      {len(losses) if total_trades > 0 else 0}")
    print(f"Win Rate:           {win_rate:.2f}%")
    print(f"Average Win:        INR {avg_win:,.2f}")
    print(f"Average Loss:       INR {avg_loss:,.2f}")
    print(f"Profit Factor:      {profit_factor:.2f}")
    print(f"Maximum Drawdown:   {max_dd:.2f}%")
    print("=======================================================")
    print(f"Reports saved in workspace:")
    print(f" - Trades History: backtest_trades_history.csv")
    print(f" - Equity Curve:   backtest_equity_curve.csv\n")

if __name__ == "__main__":
    run_backtest()

import os
import io
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import screener

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

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

def run_backtest():
    print("=======================================================")
    print("INITIALIZING STRATEGY V2 QUANTITATIVE BACKTEST")
    print("=======================================================")
    print("Step 1: Fetching Nifty 50 Ticker List...")
    tickers = screener.get_nifty_250_tickers()
    tickers = list(dict.fromkeys(tickers))
    print(f"Total Tickers discovered: {len(tickers)}")
    
    # Download 3 years of data
    print("Step 2: Downloading 3 years of daily historical data from Yahoo Finance...")
    try:
        data = yf.download(tickers, period="3y", interval="1d", group_by="ticker", threads=True, timeout=30)
    except Exception as e:
        print(f"Failed to download data: {e}")
        return
        
    print("Step 3: Pre-calculating indicators (20 SMA, 20 EMA, 14 RSI, 14 ATR) for each ticker...")
    ticker_dfs = {}
    ticker_sectors = {}
    for t in tickers:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if t not in data.columns.levels[0]:
                    continue
                df = data[t].dropna(subset=["Close", "High", "Low", "Volume"])
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
            df['ATR_14'] = calculate_atr(df, 14)
            df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA_20']
            
            # Store clean, drop initial NaNs
            ticker_dfs[t] = df.dropna(subset=['20_SMA', '20_EMA', 'Vol_SMA_20', 'RSI_14', 'ATR_14'])
            ticker_sectors[t] = screener.get_stock_sector(t)
        except Exception:
            continue
            
    print(f"Successfully processed {len(ticker_dfs)} tickers.")
    
    # Download Nifty 50 Index for comparison
    print("Downloading Nifty 50 Index (^NSEI) for comparison...")
    nifty_df = yf.download("^NSEI", period="3y", interval="1d")
    if isinstance(nifty_df.columns, pd.MultiIndex):
        nifty_df.columns = nifty_df.columns.droplevel(1)
    nifty_df = nifty_df.dropna(subset=["Close"])
    
    # Get sorted trading dates from Nifty index (skip initial 30 days warmup)
    trading_dates = sorted(list(nifty_df.index))
    if len(trading_dates) > 30:
        trading_dates = trading_dates[30:]
        
    print(f"Total trading days to simulate: {len(trading_dates)} ({trading_dates[0].strftime('%Y-%m-%d')} to {trading_dates[-1].strftime('%Y-%m-%d')})")
    
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
            sec = p.get("sector", "Diversified")
            
            # Check Stop Loss hit (low is below or equal to SL)
            if low <= sl:
                # Conservative exit: exit at stop loss or today's open if open is lower (gap down)
                exit_price = min(open_p, sl)
                exit_val = qty * exit_price
                pnl = exit_val - entry_val
                closed_trades.append({
                    "ticker": t,
                    "sector": sec,
                    "entry_date": p["entry_date"],
                    "entry_price": p["entry_price"],
                    "qty": qty,
                    "entry_val": entry_val,
                    "exit_date": date.strftime("%Y-%m-%d"),
                    "exit_price": exit_price,
                    "exit_val": exit_val,
                    "pnl": pnl,
                    "pnl_pct": (pnl / entry_val) * 100 if entry_val > 0 else 0.0,
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
                    "sector": sec,
                    "entry_date": p["entry_date"],
                    "entry_price": p["entry_price"],
                    "qty": qty,
                    "entry_val": entry_val,
                    "exit_date": date.strftime("%Y-%m-%d"),
                    "exit_price": exit_price,
                    "exit_val": exit_val,
                    "pnl": pnl,
                    "pnl_pct": (pnl / entry_val) * 100 if entry_val > 0 else 0.0,
                    "reason": "Target Hit"
                })
                cash += exit_val
            else:
                # Update Trailing Stop (20 EMA - stop only moves up, never down)
                new_sl = max(sl, ema_20)
                p["current_sl"] = new_sl
                active_positions.append(p)
                
        open_positions = active_positions
        
        # B. CALCULATE PORTFOLIO VALUE & SECTOR CONCENTRATION
        holdings_value = 0.0
        open_value = 0.0
        sector_counts = {}
        for p in open_positions:
            t = p["ticker"]
            sec = p.get("sector", "Diversified")
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            open_value += p["entry_val"]
            
            df = ticker_dfs.get(t)
            if df is not None and date in df.index:
                holdings_value += p["qty"] * float(df.loc[date, "Close"])
            else:
                holdings_value += p["qty"] * p["entry_price"]
                
        portfolio_value = cash + holdings_value
        max_open_value = portfolio_value * 0.90 # 90% allocation limit (10% cash buffer)
        
        # C. SCAN MARKET FOR NEW ENTRIES (Strategy v2)
        # Sizing risk amount: 1.5% of total portfolio value
        risk_per_trade = portfolio_value * 0.015
        
        candidates = []
        open_tickers = {p["ticker"] for p in open_positions}
        
        for t, df in ticker_dfs.items():
            if t in open_tickers:
                continue
                
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
            atr_today = float(today_row["ATR_14"])
            
            if close_today < 20.0 or vol_sma_today < 50000.0:
                continue
                
            close_yesterday = float(yesterday_row["Close"])
            sma_yesterday = float(yesterday_row["20_SMA"])
            
            # Strategy v2 Conditions:
            # 1. Price Breakout: Close > 20 SMA today, Close <= 20 SMA yesterday
            price_breakout = (close_yesterday <= sma_yesterday) and (close_today > sma_today)
            # 2. Volume threshold: > 2.5x (250%) of 20-day Volume SMA
            volume_confirmed = vol_today > (2.5 * vol_sma_today)
            # 3. 14-period RSI between 50 and 70
            rsi_confirmed = 50 <= rsi_today <= 70
            
            if price_breakout and volume_confirmed and rsi_confirmed and atr_today > 0:
                candidates.append({
                    "ticker": t,
                    "close": close_today,
                    "vol_ratio": float(today_row["Vol_Ratio"]),
                    "atr_14": atr_today,
                    "sector": ticker_sectors.get(t, "Diversified")
                })
                
        # Sort candidates by volume breakout ratio descending
        candidates.sort(key=lambda x: x["vol_ratio"], reverse=True)
        
        # D. EXECUTE BUYS (Max 3 buys/day, Max 3/sector, 90% exposure limit)
        daily_buys = 0
        for c in candidates:
            if daily_buys >= 3:
                break
                
            t = c["ticker"]
            sec = c["sector"]
            
            # Sector concentration check: Max 3 open positions per sector
            if sector_counts.get(sec, 0) >= 3:
                continue
                
            entry_price = c["close"]
            atr = c["atr_14"]
            
            # v2 Stop-loss: 2x ATR(14) below entry, no fixed clamp
            risk_per_share = 2.0 * atr
            initial_sl = entry_price - risk_per_share
            
            if risk_per_share <= 0:
                continue
                
            # Quantity based on 1.5% risk
            qty = int(risk_per_trade // risk_per_share)
            if qty <= 0:
                continue
                
            cost = qty * entry_price
            
            # 90% Max Portfolio Allocation Guardrail
            if open_value + cost > max_open_value:
                allowed_cost = max_open_value - open_value
                if allowed_cost <= 0:
                    continue
                qty = int(allowed_cost // entry_price)
                cost = qty * entry_price
                if qty <= 0:
                    continue
                    
            # Cash limit check
            if cost > cash:
                qty = int(cash // entry_price)
                cost = qty * entry_price
                if qty <= 0:
                    continue
                    
            cash -= cost
            open_value += cost
            daily_buys += 1
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            
            target = entry_price + (2.0 * risk_per_share) # 1:2 Risk to Reward
            open_positions.append({
                "ticker": t,
                "sector": sec,
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
    df_equity = pd.DataFrame(equity_curve, columns=["Date", "Portfolio Value", "Strategy Return (%)", "Nifty Return (%)"])
    df_trades = pd.DataFrame(closed_trades)
    
    total_trades = len(df_trades)
    if total_trades > 0:
        wins = df_trades[df_trades["pnl"] > 0]
        win_rate = (len(wins) / total_trades) * 100
        avg_win = wins["pnl"].mean() if len(wins) > 0 else 0.0
        losses = df_trades[df_trades["pnl"] <= 0]
        avg_loss = losses["pnl"].mean() if len(losses) > 0 else 0.0
        profit_factor = (wins["pnl"].sum() / abs(losses["pnl"].sum())) if len(losses) > 0 and losses["pnl"].sum() != 0 else float('inf')
    else:
        wins = []
        losses = []
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
    
    # Save reports in workspace directory
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    df_trades.to_csv(os.path.join(workspace_dir, "backtest_trades_history.csv"), index=False)
    df_equity.to_csv(os.path.join(workspace_dir, "backtest_equity_curve.csv"), index=False)
    
    print("\n=======================================================")
    print("STRATEGY V2 BACKTESTING PERFORMANCE SUMMARY REPORT")
    print("=======================================================")
    print(f"Period Simulated:   {trading_dates[0].strftime('%d-%b-%Y')} to {trading_dates[-1].strftime('%d-%b-%Y')}")
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
    print(f" - Trades History: {os.path.join(workspace_dir, 'backtest_trades_history.csv')}")
    print(f" - Equity Curve:   {os.path.join(workspace_dir, 'backtest_equity_curve.csv')}\n")

if __name__ == "__main__":
    run_backtest()

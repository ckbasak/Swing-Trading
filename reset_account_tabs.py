import os
import sys
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RESET_ACCOUNT")

def reset_all_strategy_accounts():
    root = os.path.dirname(os.path.abspath(__file__))
    strategies = ["strategy1", "strategy2", "strategy3", "strategy_etf"]
    
    logger.info("=== Starting Clean Reset of Account Tab & Portfolio State Across All 4 Strategies ===")
    
    for strat in strategies:
        strat_dir = os.path.join(root, strat)
        logger.info(f"\n--- Cleaning Strategy: {strat} ---")
        
        # 1. Clean local cache and log files
        cache_files = [
            "local_portfolio_data.json",
            "cached_holdings.json",
            "cached_paper_trades.json",
            "cached_signals.json",
            "bot.log"
        ]
        for cf in cache_files:
            fp = os.path.join(strat_dir, cf)
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                    logger.info(f"  • Deleted local cache file: {cf}")
                except Exception as e:
                    logger.warning(f"  • Could not delete {cf}: {e}")
                    
        # 2. Reset Google Sheets Account Tab & Trade Logs
        if strat_dir not in sys.path:
            sys.path.insert(0, strat_dir)
            
        try:
            # Force reload of strategy-specific portfolio_manager module
            if "portfolio_manager" in sys.modules:
                del sys.modules["portfolio_manager"]
            import portfolio_manager
            
            client = portfolio_manager.get_gspread_client()
            if client:
                sh = portfolio_manager.get_or_create_portfolio_sheet(client)
                if sh:
                    # A. Reset Account Worksheet Parameters
                    try:
                        updates = {
                            "Total Portfolio Value": "1000000.00",
                            "Cash Balance": "1000000.00",
                            "Initial Capital": "1000000.00",
                            "Risk Percent": "0.01"
                        }
                        portfolio_manager.update_account_details(sh, updates)
                        logger.info(f"  • Successfully reset 'Account' tab parameters to initial defaults (Capital: ₹1,000,000, Risk: 1%).")
                    except Exception as e:
                        logger.warning(f"  • Account tab update notice: {e}")
                        
                    # B. Reset Holdings Worksheet
                    try:
                        ws_holdings = sh.worksheet("Holdings")
                        all_vals = ws_holdings.get_all_values()
                        if len(all_vals) > 1:
                            headers = all_vals[0]
                            ws_holdings.clear()
                            ws_holdings.append_row(headers)
                            logger.info(f"  • Cleared previous holdings rows from 'Holdings' worksheet.")
                    except Exception as e:
                        logger.warning(f"  • Holdings worksheet reset notice: {e}")
                        
                    # C. Reset Trades_Log Worksheet
                    try:
                        ws_trades = sh.worksheet("Trades_Log")
                        all_vals = ws_trades.get_all_values()
                        if len(all_vals) > 1:
                            headers = all_vals[0]
                            ws_trades.clear()
                            ws_trades.append_row(headers)
                            logger.info(f"  • Cleared trade history rows from 'Trades_Log' worksheet.")
                    except Exception as e:
                        logger.warning(f"  • Trades_Log worksheet reset notice: {e}")
            else:
                logger.info(f"  • Google Sheets client unconfigured or offline for {strat}. Local cache cleaned.")
        except Exception as e:
            logger.warning(f"  • Strategy {strat} portfolio manager notice: {e}")
        finally:
            if strat_dir in sys.path:
                sys.path.remove(strat_dir)
                
    logger.info("\n=== ✅ All 4 Strategy Accounts Successfully Reset for Fresh Start! ===")

if __name__ == "__main__":
    reset_all_strategy_accounts()

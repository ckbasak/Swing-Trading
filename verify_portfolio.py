import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VERIFY")

def run_verification():
    logger.info("--- Starting Manage-Dhan-Portfolio Verification ---")
    
    # 1. Test dhan_client
    import dhan_client
    logger.info(f"Is Dhan Configured: {dhan_client.is_dhan_configured()}")
    holdings = dhan_client.get_dhan_holdings()
    logger.info(f"Fetched Holdings Count: {len(holdings)}")
    assert len(holdings) > 0, "Holdings list should not be empty!"
    
    funds = dhan_client.get_dhan_funds()
    logger.info(f"Fetched Funds: {funds}")
    
    # 2. Test portfolio_analyzer
    import portfolio_analyzer
    analyzed_holdings, summary = portfolio_analyzer.analyze_full_dhan_portfolio()
    logger.info(f"Analyzed Holdings Count: {len(analyzed_holdings)}")
    logger.info(f"Total Investment: ₹{summary['totalInvestment']:,.2f}")
    logger.info(f"Total Current Value: ₹{summary['totalCurrentValue']:,.2f}")
    logger.info(f"Total P&L: ₹{summary['totalPnL']:,.2f} ({summary['totalPnLPercentage']:+.2f}%)")
    logger.info(f"Signals - SELL: {summary['sellCount']}, AVERAGE: {summary['averageCount']}, HOLD: {summary['holdCount']}")
    
    cr = summary["capitalRecycling"]
    logger.info(f"Capital Recycling - Total Freed: ₹{cr['totalFreedCapital']:,.2f}")
    logger.info(f"  Strategy 1 (Mid-Cap 30%): ₹{cr['strategy1_midcap']:,.2f}")
    logger.info(f"  Strategy 2 (Sector 30%): ₹{cr['strategy2_sector']:,.2f}")
    logger.info(f"  Strategy 3 (Momentum 20%): ₹{cr['strategy3_momentum']:,.2f}")
    logger.info(f"  ETF Strategy (Low-Beta 20%): ₹{cr['etf_strategy']:,.2f}")
    
    assert summary["totalInvestment"] > 0, "Total investment must be positive"
    assert summary["sellCount"] + summary["averageCount"] + summary["holdCount"] == len(analyzed_holdings), "Signal count total must match holdings count"
    
    # 3. Test portfolio_manager
    import portfolio_manager
    sync_res = portfolio_manager.sync_analysis_to_sheets(analyzed_holdings, summary)
    logger.info(f"Google Sheets Sync Result: {sync_res}")
    
    paper_res = portfolio_manager.record_paper_trade(
        symbol="RELIANCE",
        action="SELL",
        qty=50,
        price=2740.0,
        total_val=137000.0,
        rationale="Verification test paper trade"
    )
    logger.info(f"Paper Trade Logging Result: {paper_res}")
    
    # 4. Test bot module imports
    import bot
    logger.info("bot.py imported successfully!")
    
    logger.info("=== All Manage-Dhan-Portfolio Verification Checks PASSED Successfully! ===")

if __name__ == "__main__":
    run_verification()

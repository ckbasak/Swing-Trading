import yfinance as yf
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CorrelationSentinel")

class CorrelationSentinel:
    """
    V2 Cross-Strategy De-Duplication & Correlation Sentinel.
    1. Blocks duplicate execution of the same stock across Strategy 1, 2, 3 & ETF.
    2. Calculates 30-day return correlation matrix between candidate and active portfolio holdings.
    3. Rejects trades with average correlation bar_rho > 0.75 to prevent sector/asset clustering.
    """

    def __init__(self, max_correlation_threshold: float = 0.75):
        self.max_correlation_threshold = max_correlation_threshold

    def check_deduplication(
        self,
        candidate_ticker: str,
        open_positions: List[Dict[str, Any]],
        trades_already_queued: List[Dict[str, Any]]
    ) -> Tuple[bool, str]:
        """
        Checks if candidate ticker is already in active holdings or already queued today.
        """
        holding_tickers = {p.get("Ticker", "").upper().replace(".NS", "") for p in open_positions}
        queued_tickers = {t.get("ticker", "").upper().replace(".NS", "") for t.get in trades_already_queued if isinstance(t, dict) and "ticker" in t}

        clean_cand = candidate_ticker.upper().replace(".NS", "")

        if clean_cand in holding_tickers:
            return False, f"De-Duplication Gate: '{candidate_ticker}' is already an active holding."

        if clean_cand in queued_tickers:
            return False, f"De-Duplication Gate: '{candidate_ticker}' is already queued for execution by another strategy today."

        return True, "PASSED"

    def calculate_correlation_with_portfolio(
        self,
        candidate_ticker: str,
        open_positions: List[Dict[str, Any]]
    ) -> Tuple[float, List[str]]:
        """
        Calculates average 30-day daily return correlation between candidate and open positions.
        Returns (avg_correlation, warning_logs).
        """
        if not open_positions:
            return 0.0, []

        holding_tickers = [p.get("Ticker", "") for p in open_positions if p.get("Ticker")]
        if not holding_tickers:
            return 0.0, []

        all_tickers = list(set([candidate_ticker] + holding_tickers))
        if len(all_tickers) < 2:
            return 0.0, []

        try:
            df = yf.download(all_tickers, period="2mo", interval="1d", progress=False)
            if df.empty or "Close" not in df:
                return 0.0, ["Insufficient price history for correlation calculation."]

            close_df = df["Close"]
            if isinstance(close_df, pd.Series):
                return 0.0, []

            # Compute daily returns
            returns_df = close_df.pct_change().dropna()
            if returns_df.empty or candidate_ticker not in returns_df.columns:
                return 0.0, []

            cand_returns = returns_df[candidate_ticker]
            correlations = []
            warnings = []

            for pos_ticker in holding_tickers:
                if pos_ticker != candidate_ticker and pos_ticker in returns_df.columns:
                    rho = cand_returns.corr(returns_df[pos_ticker])
                    if not np.isnan(rho):
                        correlations.append(rho)
                        if rho > 0.80:
                            warnings.append(f"High correlation ({rho:.2f}) between {candidate_ticker} and active holding {pos_ticker}.")

            avg_rho = float(np.mean(correlations)) if correlations else 0.0
            return round(avg_rho, 2), warnings
        except Exception as e:
            logger.error(f"Error computing correlation matrix: {e}")
            return 0.0, [f"Correlation matrix error: {e}"]

    def validate_correlation(
        self,
        candidate_ticker: str,
        open_positions: List[Dict[str, Any]]
    ) -> Tuple[bool, float, str]:
        """
        Enforces correlation limit. Rejects trade if avg_rho > 0.75.
        """
        avg_rho, warnings = self.calculate_correlation_with_portfolio(candidate_ticker, open_positions)

        if avg_rho > self.max_correlation_threshold:
            return False, avg_rho, f"NO-TRADE Gate: Average correlation (bar_rho = {avg_rho:.2f}) with active holdings exceeds {self.max_correlation_threshold:.2f} cap."

        return True, avg_rho, "PASSED"

_sentinel_instance = None

def get_correlation_sentinel() -> CorrelationSentinel:
    global _sentinel_instance
    if _sentinel_instance is None:
        _sentinel_instance = CorrelationSentinel()
    return _sentinel_instance

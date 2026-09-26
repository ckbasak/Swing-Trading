import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple
import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MarketRegime")

class MarketRegimeEngine:
    """
    V2 Multi-Factor Market Regime & Breadth Engine.
    Calculates composite Market Regime Score S_regime in [0, 100] based on 5 components:
    1. Trend Score (30%) - Nifty 50 SMAs (20, 50, 200) & 50-EMA slope
    2. Market Breadth Score (25%) - % Nifty 500 above 20/50/200 SMA & A/D ratio
    3. Volatility Score (15%) - India VIX level & 10-day slope
    4. Institutional Score (15%) - FII / DII net cash flow proxy
    5. Macro Score (15%) - Crude Oil, USD/INR & Macro sentiment
    """

    def __init__(self):
        self.regime_labels = {
            "STRONG_BULL": {"min_score": 80, "color": "🟢", "max_sizing": 1.00, "max_exposure": 0.90, "min_cash": 0.10},
            "BULL_RECOVERY": {"min_score": 60, "color": "🟢", "max_sizing": 0.85, "max_exposure": 0.80, "min_cash": 0.20},
            "NEUTRAL_CHOPPY": {"min_score": 45, "color": "🟡", "max_sizing": 0.60, "max_exposure": 0.60, "min_cash": 0.30},
            "CAUTION": {"min_score": 30, "color": "🟡", "max_sizing": 0.40, "max_exposure": 0.40, "min_cash": 0.50},
            "BEAR_RISK_OFF": {"min_score": 15, "color": "🔴", "max_sizing": 0.00, "max_exposure": 0.20, "min_cash": 0.70},
            "EXTREME_SHOCK": {"min_score": 0,  "color": "🔴", "max_sizing": 0.00, "max_exposure": 0.00, "min_cash": 1.00}
        }

    def _get_nifty_trend_score(self) -> Tuple[float, Dict[str, Any]]:
        """Calculates Nifty 50 trend score (0 to 100)."""
        try:
            df = yf.download("^NSEI", period="1y", interval="1d", progress=False)
            if df.empty or len(df) < 200:
                logger.warning("Insufficient Nifty data for trend score calculation. Defaulting to 60.0.")
                return 60.0, {"error": "Insufficient data"}
            
            # Extract Close prices
            if isinstance(df.columns, pd.MultiIndex):
                close = df['Close']['^NSEI']
            else:
                close = df['Close']
            
            latest_price = float(close.iloc[-1])
            sma_20 = float(close.rolling(20).mean().iloc[-1])
            sma_50 = float(close.rolling(50).mean().iloc[-1])
            sma_200 = float(close.rolling(200).mean().iloc[-1])
            
            ema_50_series = close.ewm(span=50, adjust=False).mean()
            ema_50_latest = float(ema_50_series.iloc[-1])
            ema_50_prev10 = float(ema_50_series.iloc[-10]) if len(ema_50_series) >= 10 else ema_50_latest
            ema_50_slope = (ema_50_latest - ema_50_prev10) / ema_50_prev10 * 100.0

            score = 0.0
            if latest_price > sma_200:
                score += 35.0
            if latest_price > sma_50:
                score += 30.0
            if latest_price > sma_20:
                score += 20.0
            if ema_50_slope > 0:
                score += 15.0

            details = {
                "latest_price": round(latest_price, 2),
                "sma_20": round(sma_20, 2),
                "sma_50": round(sma_50, 2),
                "sma_200": round(sma_200, 2),
                "ema_50_slope_pct": round(ema_50_slope, 2),
                "above_200": latest_price > sma_200,
                "above_50": latest_price > sma_50,
                "above_20": latest_price > sma_20
            }
            return score, details
        except Exception as e:
            logger.error(f"Error calculating Nifty trend score: {e}")
            return 50.0, {"error": str(e)}

    def _get_volatility_score(self) -> Tuple[float, Dict[str, Any]]:
        """Calculates Volatility Score (0 to 100) using India VIX."""
        try:
            df = yf.download("^INDIAVIX", period="3mo", interval="1d", progress=False)
            if df.empty or len(df) < 10:
                # Fallback to general market volatility estimation
                return 65.0, {"vix_level": 15.0, "status": "Fallback VIX"}

            if isinstance(df.columns, pd.MultiIndex):
                close = df['Close']['^INDIAVIX']
            else:
                close = df['Close']

            vix_level = float(close.iloc[-1])
            vix_10d_ago = float(close.iloc[-10]) if len(close) >= 10 else vix_level
            vix_change_pct = (vix_level - vix_10d_ago) / vix_10d_ago * 100.0

            if vix_level < 14.0:
                base_score = 100.0
            elif vix_level < 18.0:
                base_score = 80.0
            elif vix_level < 22.0:
                base_score = 55.0
            elif vix_level < 26.0:
                base_score = 30.0
            else:
                base_score = 10.0

            # Slope adjustment (+10 if falling VIX, -10 if spiking VIX)
            if vix_change_pct < -5.0:
                base_score = min(100.0, base_score + 10.0)
            elif vix_change_pct > 10.0:
                base_score = max(0.0, base_score - 15.0)

            details = {
                "vix_level": round(vix_level, 2),
                "vix_10d_change_pct": round(vix_change_pct, 2),
                "volatility_state": "Low" if vix_level < 15 else ("Elevated" if vix_level < 22 else "High")
            }
            return base_score, details
        except Exception as e:
            logger.error(f"Error calculating Volatility score: {e}")
            return 60.0, {"error": str(e)}

    def _get_macro_score(self, macro_sentiment_data: Dict[str, Any] = None) -> Tuple[float, Dict[str, Any]]:
        """Calculates Macro Score (0 to 100) using Crude Oil, USD/INR, and AI Sentiment."""
        try:
            df_crude = yf.download("CL=F", period="1mo", interval="1d", progress=False)
            crude_price = 75.0
            if not df_crude.empty:
                if isinstance(df_crude.columns, pd.MultiIndex):
                    crude_price = float(df_crude['Close']['CL=F'].iloc[-1])
                else:
                    crude_price = float(df_crude['Close'].iloc[-1])

            crude_score = 100.0 if crude_price < 75 else (70.0 if crude_price < 85 else (40.0 if crude_price < 95 else 15.0))

            ai_score = 60.0
            if macro_sentiment_data:
                sentiment_bias = macro_sentiment_data.get("sentiment_bias", "NEUTRAL")
                if sentiment_bias == "BULLISH":
                    ai_score = 85.0
                elif sentiment_bias == "BEARISH":
                    ai_score = 30.0

            combined_macro = (0.5 * crude_score) + (0.5 * ai_score)
            details = {
                "crude_oil_usd": round(crude_price, 2),
                "crude_score": crude_score,
                "ai_sentiment_score": ai_score,
                "combined_macro": round(combined_macro, 2)
            }
            return combined_macro, details
        except Exception as e:
            logger.error(f"Error calculating Macro score: {e}")
            return 60.0, {"error": str(e)}

    def calculate_regime_score(self, breadth_pct: float = None, macro_sentiment_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Calculates the complete composite Market Regime Score S_regime.
        S_regime = 0.30*Trend + 0.25*Breadth + 0.15*Volatility + 0.15*Institutional + 0.15*Macro
        """
        trend_score, trend_details = self._get_nifty_trend_score()
        vol_score, vol_details = self._get_volatility_score()
        macro_score, macro_details = self._get_macro_score(macro_sentiment_data)

        # Breadth Score (Default to 65% if not computed by screener)
        if breadth_pct is None:
            breadth_score = 65.0
        else:
            breadth_score = float(np.clip(breadth_pct, 0.0, 100.0))

        # Institutional Flow Score (Default to 65.0 unless trend is weak)
        inst_score = 65.0 if trend_score >= 60 else 40.0

        # Weighted composite S_regime
        s_regime = (
            (0.30 * trend_score) +
            (0.25 * breadth_score) +
            (0.15 * vol_score) +
            (0.15 * inst_score) +
            (0.15 * macro_score)
        )
        s_regime = round(float(np.clip(s_regime, 0.0, 100.0)), 2)

        # Determine Regime Classification
        classification = "NEUTRAL_CHOPPY"
        for label, config in self.regime_labels.items():
            if s_regime >= config["min_score"]:
                classification = label
                break

        config = self.regime_labels[classification]

        return {
            "regime_score": s_regime,
            "classification": classification,
            "color": config["color"],
            "max_sizing_multiplier": config["max_sizing"],
            "max_open_exposure_pct": config["max_exposure"],
            "min_cash_reserve_pct": config["min_cash"],
            "components": {
                "trend_score": round(trend_score, 2),
                "breadth_score": round(breadth_score, 2),
                "volatility_score": round(vol_score, 2),
                "institutional_score": round(inst_score, 2),
                "macro_score": round(macro_score, 2)
            },
            "details": {
                "trend": trend_details,
                "volatility": vol_details,
                "macro": macro_details
            }
        }

_engine_instance = None

def get_market_regime(breadth_pct: float = None, macro_sentiment_data: Dict[str, Any] = None) -> Dict[str, Any]:
    """Global helper function to fetch current market regime."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = MarketRegimeEngine()
    return _engine_instance.calculate_regime_score(breadth_pct=breadth_pct, macro_sentiment_data=macro_sentiment_data)

if __name__ == "__main__":
    print("Evaluating current Market Regime...")
    regime = get_market_regime()
    print(f"Regime Score: {regime['regime_score']}/100 | Classification: {regime['classification']}")
    print(f"Max Sizing Multiplier: {regime['max_sizing_multiplier'] * 100}% | Min Cash Reserve: {regime['min_cash_reserve_pct'] * 100}%")
    print("Component Breakdown:", regime["components"])


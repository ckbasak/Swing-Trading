import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Sector Mapping Lookup Table for Indian Equities & Sector ETFs
SECTOR_MAP = {
    # Banking & Financials
    "HDFCBANK": "FINANCIALS", "ICICIBANK": "FINANCIALS", "SBIN": "FINANCIALS",
    "AXISBANK": "FINANCIALS", "KOTAKBANK": "FINANCIALS", "BANKBEES": "FINANCIALS",
    "PSUBNKIETF": "FINANCIALS", "PVTBANIETF": "FINANCIALS", "BANKNIFTY1": "FINANCIALS",
    "PSUBANK": "FINANCIALS", "BAJFINANCE": "FINANCIALS",
    
    # Defence & Capital Goods
    "BDL": "DEFENCE", "BEL": "DEFENCE", "HAL": "DEFENCE", "MAZDOCK": "DEFENCE", "BEML": "DEFENCE",
    
    # Railways & Infra
    "TITAGARH": "RAILWAYS_INFRA", "INFRABEES": "RAILWAYS_INFRA", "ADANIPORTS": "RAILWAYS_INFRA",
    
    # IT & Tech
    "TCS": "TECHNOLOGY", "INFY": "TECHNOLOGY", "HCLTECH": "TECHNOLOGY", "LTIM": "TECHNOLOGY",
    
    # Metals & Energy
    "JSWSTEEL": "METALS", "GAIL": "ENERGY", "PETRONET": "ENERGY", "NTPC": "ENERGY", "ONGC": "ENERGY",
    
    # Auto & Auto Ancillaries
    "ZFCVINDIA": "AUTO", "AUTOBEES": "AUTO", "TATAMOTORS": "AUTO", "M&M": "AUTO",
    
    # Pharma & Healthcare
    "PHARMABEES": "PHARMA", "HEALTHIETF": "PHARMA", "HEALTHY": "PHARMA", "SUNPHARMA": "PHARMA",
    
    # Defensive Safe-Haven Asset ETFs (Exempt from Sector Cap)
    "GOLDBEES": "DEFENSIVE_GOLD", "SILVERBEES": "DEFENSIVE_SILVER",
    "LIQUIDCASE": "DEFENSIVE_CASH", "LIQUIDBEES": "DEFENSIVE_CASH",
    
    # Broad Equity Market ETFs
    "SETFNIF50": "BROAD_EQUITY_ETF", "JUNIORBEES": "BROAD_EQUITY_ETF",
    "MOM100": "BROAD_EQUITY_ETF", "MON100": "BROAD_EQUITY_ETF",
    "NETF": "BROAD_EQUITY_ETF", "CPSEETF": "BROAD_EQUITY_ETF", "ICICIB22": "BROAD_EQUITY_ETF"
}

def get_symbol_sector(symbol: str) -> str:
    """Returns sector classification for stock or ETF."""
    clean_sym = symbol.replace(".NS", "").upper()
    return SECTOR_MAP.get(clean_sym, "OTHERS")

def enforce_sector_and_etf_limits(
    analyzed_holdings: List[Dict[str, Any]],
    total_portfolio_value: float,
    max_sector_cap_pct: float = 25.0
) -> Dict[str, Any]:
    """
    Enforces maximum 25% sector exposure limits and categorizes ETF risk profiles.
    """
    sector_totals: Dict[str, float] = {}
    sector_counts: Dict[str, int] = {}
    
    for h in analyzed_holdings:
        sym = h.get("tradingSymbol", "")
        val = h.get("currentValue", 0.0)
        sector = get_symbol_sector(sym)
        
        sector_totals[sector] = sector_totals.get(sector, 0.0) + val
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        
    sector_exposure_pct: Dict[str, float] = {}
    exceeded_sectors: List[str] = []
    
    for sector, val in sector_totals.items():
        pct = round((val / total_portfolio_value * 100.0), 2) if total_portfolio_value > 0 else 0.0
        sector_exposure_pct[sector] = pct
        
        # Enforce 25% cap on non-defensive sectors
        if not sector.startswith("DEFENSIVE_") and not sector.startswith("BROAD_EQUITY_") and pct > max_sector_cap_pct:
            exceeded_sectors.append(f"{sector} ({pct:.1f}% > {max_sector_cap_pct:.0f}%)")
            
    return {
        "sectorTotals": sector_totals,
        "sectorCounts": sector_counts,
        "sectorExposurePct": sector_exposure_pct,
        "maxSectorCapPct": max_sector_cap_pct,
        "exceededSectors": exceeded_sectors,
        "isSectorCapExceeded": len(exceeded_sectors) > 0
    }

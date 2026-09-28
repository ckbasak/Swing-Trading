"""
Gateway Client SDK for Inter-Service REST Communication
-------------------------------------------------------
Allows Strategy 1, Strategy 2, Strategy 3, ETF, and Master Hub modules (Service Alpha)
to query Service Beta (MDP Broker Gateway API) over lightweight HTTP REST protocols.
Falls back safely to local in-process calls if the external gateway is unreachable.
"""

import os
import sys
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger("GatewayClient")

# Reads MDP_GATEWAY_URL from env or defaults to local server on port 8085
GATEWAY_URL = os.environ.get("MDP_GATEWAY_URL", "http://127.0.0.1:8085").rstrip("/")

def _http_get(endpoint: str, timeout: int = 5) -> Optional[Dict[str, Any]]:
    url = f"{GATEWAY_URL}{endpoint}"
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug(f"Gateway HTTP GET failed for '{url}': {e}")
    return None

def _http_post(endpoint: str, payload: Dict[str, Any], timeout: int = 8) -> Optional[Dict[str, Any]]:
    url = f"{GATEWAY_URL}{endpoint}"
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code in [200, 201]:
            return r.json()
        elif r.status_code >= 400:
            return r.json()
    except Exception as e:
        logger.debug(f"Gateway HTTP POST failed for '{url}': {e}")
    return None

def check_gateway_health() -> Dict[str, Any]:
    """Queries MDP Gateway health endpoint."""
    res = _http_get("/api/v1/health", timeout=3)
    if res and res.get("status") == "healthy":
        return res
    return {
        "status": "offline",
        "service": "Service Beta - MDP Broker Gateway",
        "message": f"Gateway unreachable at {GATEWAY_URL}"
    }

def get_account_funds() -> Dict[str, Any]:
    """Queries Gateway for cash balance, total portfolio value, and execution mode."""
    res = _http_get("/api/v1/funds")
    if res and res.get("status") == "success":
        return res
    
    # In-process local fallback if Gateway REST service is offline
    try:
        import portfolio_manager
        sh = portfolio_manager.get_or_create_portfolio_sheet()
        acc = portfolio_manager.get_account_details(sh) if sh else {}
        return {
            "status": "success_fallback",
            "cash_balance": acc.get("Cash Balance", 100000.0),
            "total_portfolio_value": acc.get("Total Portfolio Value", 100000.0),
            "initial_capital": acc.get("Initial Capital", 100000.0),
            "execution_mode": acc.get("Execution Mode", "PAPER_SIMULATED")
        }
    except Exception as e:
        return {
            "status": "error",
            "cash_balance": 100000.0,
            "total_portfolio_value": 100000.0,
            "initial_capital": 100000.0,
            "execution_mode": "PAPER_SIMULATED",
            "error": str(e)
        }

def get_analyzed_portfolio() -> Dict[str, Any]:
    """Queries Gateway for full analyzed holdings matrix and recommendations."""
    res = _http_get("/api/v1/portfolio", timeout=10)
    if res and res.get("status") == "success":
        return res
    return {"status": "error", "analyzed_holdings": [], "summary": {}}

def get_capital_recycling() -> Dict[str, Any]:
    """Queries Gateway for freed capital breakdown across strategy allocations."""
    res = _http_get("/api/v1/recycling_log")
    if res and res.get("status") == "success":
        return res
    return {
        "status": "error",
        "total_freed_capital": 0.0,
        "strategy1_midcap_allocation": 0.0,
        "strategy2_sector_allocation": 0.0,
        "strategy3_momentum_allocation": 0.0,
        "etf_strategy_allocation": 0.0
    }

def dispatch_trade_order(
    symbol: str,
    action: str,
    qty: float,
    price: float,
    strategy_name: str,
    is_live: bool = False,
    rationale: str = "Strategy execution"
) -> Dict[str, Any]:
    """Dispatches trade order payload to Service Beta Gateway for validation and execution."""
    payload = {
        "symbol": symbol,
        "action": action,
        "qty": qty,
        "price": price,
        "strategy": strategy_name,
        "is_live": is_live,
        "rationale": rationale
    }
    res = _http_post("/api/v1/place_order", payload)
    if res:
        return res

    # Fallback to local paper trade logging if gateway HTTP POST unreachable
    try:
        import portfolio_manager
        total_val = round(qty * price, 2)
        portfolio_manager.record_paper_trade(
            symbol=symbol,
            action=action,
            qty=qty,
            price=price,
            total_val=total_val,
            rationale=f"[{strategy_name} Local Fallback] {rationale}"
        )
        return {
            "status": "success_fallback",
            "mode": "PAPER_SIMULATED",
            "message": f"Logged simulated paper trade locally for {qty} shares of {symbol}."
        }
    except Exception as e:
        return {"status": "error", "message": f"Order dispatch failed: {e}"}

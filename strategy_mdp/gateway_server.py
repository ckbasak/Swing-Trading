"""
Service Beta: MDP Broker Gateway REST API Server
------------------------------------------------
Provides high-performance, cached JSON endpoints for Dhan broker portfolio holdings,
fund margins, open positions, order placement, and capital recycling telemetry.

Runs as a lightweight, zero-dependency Threaded HTTP REST Server.
"""

import os
import sys
import json
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse
from typing import Dict, Any, Optional

# Ensure strategy_mdp directory is on Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dhan_client
import portfolio_analyzer
import portfolio_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] (MDP-Gateway) %(message)s")
logger = logging.getLogger("MDP-Gateway")

# In-Memory Response Caching (RAM cache with 30s TTL)
_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL_SECONDS = 30

def get_cached_response(key: str) -> Optional[Any]:
    with _CACHE_LOCK:
        if key in _CACHE:
            entry = _CACHE[key]
            if time.time() - entry["timestamp"] < CACHE_TTL_SECONDS:
                return entry["data"]
    return None

def set_cached_response(key: str, data: Any):
    with _CACHE_LOCK:
        _CACHE[key] = {
            "timestamp": time.time(),
            "data": data
        }

def clear_cache():
    with _CACHE_LOCK:
        _CACHE.clear()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server allowing concurrent request handling."""
    daemon_threads = True

class MDPGatewayRequestHandler(BaseHTTPRequestHandler):

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

    def _send_json_response(self, status_code: int, data: Dict[str, Any]):
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        force_refresh = "refresh" in query and query["refresh"][0].lower() in ["true", "1"]

        try:
            if path in ["", "/api/v1/health", "/health"]:
                self.handle_health()
            elif path == "/api/v1/funds":
                self.handle_funds(force_refresh)
            elif path == "/api/v1/portfolio":
                self.handle_portfolio(force_refresh)
            elif path == "/api/v1/positions":
                self.handle_positions(force_refresh)
            elif path == "/api/v1/recycling_log":
                self.handle_recycling_log(force_refresh)
            else:
                self._send_json_response(404, {"status": "error", "message": f"Endpoint '{path}' not found."})
        except Exception as e:
            logger.error(f"Error handling GET '{path}': {e}", exc_info=True)
            self._send_json_response(500, {"status": "error", "message": str(e)})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        
        try:
            payload = json.loads(post_body)
        except Exception:
            payload = {}

        try:
            if path == "/api/v1/place_order":
                self.handle_place_order(payload)
            elif path == "/api/v1/update_mode":
                self.handle_update_mode(payload)
            elif path == "/api/v1/clear_cache":
                clear_cache()
                self._send_json_response(200, {"status": "success", "message": "RAM cache cleared."})
            else:
                self._send_json_response(404, {"status": "error", "message": f"Endpoint '{path}' not found."})
        except Exception as e:
            logger.error(f"Error handling POST '{path}': {e}", exc_info=True)
            self._send_json_response(500, {"status": "error", "message": str(e)})

    # ---- Endpoint Handlers ----

    def handle_health(self):
        source = dhan_client.get_holdings_source()
        is_configured = dhan_client.is_dhan_configured()
        sh = portfolio_manager.get_or_create_spreadsheet()
        sheets_active = sh is not None

        data = {
            "status": "healthy",
            "service": "Service Beta - MDP Broker Gateway",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "dhan_configured": is_configured,
            "dhan_holdings_source": source,
            "google_sheets_active": sheets_active,
            "last_dhan_error": dhan_client.get_last_api_error()
        }
        self._send_json_response(200, data)

    def handle_funds(self, force_refresh: bool = False):
        cache_key = "funds"
        if not force_refresh:
            cached = get_cached_response(cache_key)
            if cached:
                return self._send_json_response(200, cached)

        sh = portfolio_manager.get_or_create_spreadsheet()
        acc = portfolio_manager.get_account_details(sh) if sh else {}

        # Fetch live funds limit if Dhan HQ is connected
        dhan_funds = {}
        if dhan_client.get_holdings_source() == "LIVE":
            try:
                res = dhan_client.get_dhan_fund_limits()
                if res and isinstance(res, dict):
                    dhan_funds = res
            except Exception:
                pass

        avail_cash = float(dhan_funds.get("availMargin", acc.get("Cash Balance", 100000.0)))
        total_val = float(acc.get("Total Portfolio Value", 100000.0))
        exec_mode = acc.get("Execution Mode", "PAPER_SIMULATED")

        result = {
            "status": "success",
            "cash_balance": avail_cash,
            "total_portfolio_value": total_val,
            "initial_capital": acc.get("Initial Capital", 100000.0),
            "execution_mode": exec_mode,
            "dhan_fund_limits": dhan_funds,
            "cached_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        set_cached_response(cache_key, result)
        self._send_json_response(200, result)

    def handle_portfolio(self, force_refresh: bool = False):
        cache_key = "portfolio"
        if not force_refresh:
            cached = get_cached_response(cache_key)
            if cached:
                return self._send_json_response(200, cached)

        holdings = dhan_client.get_dhan_holdings()
        settings = portfolio_manager.load_app_settings_from_sheets()

        target_pct = float(settings.get("target_pct_val", 10.0))
        stop_pct = float(settings.get("stop_loss_pct_val", -7.0))
        rsi_ob = float(settings.get("rsi_ob_val", 70.0))
        rsi_exit = float(settings.get("rsi_exit_val", 38.0))
        rsi_pb = float(settings.get("rsi_pb_val", 46.0))

        analyzed, summary = portfolio_analyzer.analyze_portfolio(
            raw_holdings=holdings,
            target_pct=target_pct,
            stop_loss_pct=stop_pct,
            rsi_ob=rsi_ob,
            rsi_exit=rsi_exit,
            rsi_pb=rsi_pb
        )

        result = {
            "status": "success",
            "summary": summary,
            "holdings_count": len(analyzed),
            "analyzed_holdings": analyzed,
            "cached_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        set_cached_response(cache_key, result)
        self._send_json_response(200, result)

    def handle_positions(self, force_refresh: bool = False):
        cache_key = "positions"
        if not force_refresh:
            cached = get_cached_response(cache_key)
            if cached:
                return self._send_json_response(200, cached)

        positions = dhan_client.get_dhan_positions() if hasattr(dhan_client, "get_dhan_positions") else []
        paper_trades = portfolio_manager.load_paper_trades()

        result = {
            "status": "success",
            "open_positions": positions,
            "recent_paper_trades": paper_trades[-10:] if paper_trades else [],
            "cached_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        set_cached_response(cache_key, result)
        self._send_json_response(200, result)

    def handle_recycling_log(self, force_refresh: bool = False):
        cache_key = "recycling_log"
        if not force_refresh:
            cached = get_cached_response(cache_key)
            if cached:
                return self._send_json_response(200, cached)

        sh = portfolio_manager.get_or_create_spreadsheet()
        acc = portfolio_manager.get_account_details(sh) if sh else {}
        holdings = dhan_client.get_dhan_holdings()
        _, summary = portfolio_analyzer.analyze_portfolio(holdings)

        cr = summary.get("capitalRecycling", {})
        result = {
            "status": "success",
            "total_freed_capital": cr.get("totalFreedCapital", 0.0),
            "strategy1_midcap_allocation": cr.get("strategy1_midcap", 0.0),
            "strategy2_sector_allocation": cr.get("strategy2_sector", 0.0),
            "strategy3_momentum_allocation": cr.get("strategy3_momentum", 0.0),
            "etf_strategy_allocation": cr.get("etf_strategy", 0.0),
            "cached_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        set_cached_response(cache_key, result)
        self._send_json_response(200, result)

    def handle_place_order(self, payload: Dict[str, Any]):
        symbol = str(payload.get("symbol", "")).strip().upper()
        action = str(payload.get("action", "BUY")).strip().upper()
        qty = float(payload.get("qty", 1))
        price = float(payload.get("price", 0.0))
        strategy_name = str(payload.get("strategy", "Strategy #5 MDP"))
        is_live = bool(payload.get("is_live", False))
        rationale = str(payload.get("rationale", "API Gateway Order Execution"))

        if not symbol or qty <= 0:
            return self._send_json_response(400, {"status": "error", "message": "Invalid symbol or quantity."})

        total_val = round(qty * price, 2)

        if is_live:
            # Validate Dhan live pre-flight
            dhan_ok = dhan_client.is_dhan_configured()
            if not dhan_ok:
                return self._send_json_response(400, {
                    "status": "error", 
                    "message": "Live Dhan API client is not configured or token is invalid."
                })
            # Place live Dhan order via dhan_client
            try:
                if hasattr(dhan_client, "place_order"):
                    res = dhan_client.place_order(symbol=symbol, action=action, qty=int(qty), price=price)
                    clear_cache()
                    return self._send_json_response(200, {
                        "status": "success",
                        "mode": "LIVE_DHAN",
                        "order_response": res,
                        "message": f"Live order placed for {qty} shares of {symbol} via Dhan API."
                    })
                else:
                    return self._send_json_response(501, {
                        "status": "error",
                        "message": "Dhan place_order interface not implemented in dhan_client module."
                    })
            except Exception as e:
                return self._send_json_response(500, {"status": "error", "message": f"Dhan order error: {e}"})
        else:
            # Record simulated paper trade
            success = portfolio_manager.record_paper_trade(
                symbol=symbol,
                action=action,
                qty=qty,
                price=price,
                total_val=total_val,
                rationale=f"[{strategy_name}] {rationale}"
            )
            clear_cache()
            return self._send_json_response(200, {
                "status": "success",
                "mode": "PAPER_SIMULATED",
                "message": f"Simulated paper trade logged for {qty} shares of {symbol} at ₹{price:.2f}.",
                "trade": {
                    "symbol": symbol,
                    "action": action,
                    "qty": qty,
                    "price": price,
                    "total_value": total_val,
                    "strategy": strategy_name
                }
            })

    def handle_update_mode(self, payload: Dict[str, Any]):
        new_mode = str(payload.get("execution_mode", "PAPER_SIMULATED")).upper()
        if new_mode not in ["PAPER_SIMULATED", "LIVE_DHAN"]:
            return self._send_json_response(400, {"status": "error", "message": "Invalid mode. Use 'PAPER_SIMULATED' or 'LIVE_DHAN'."})

        sh = portfolio_manager.get_or_create_spreadsheet()
        if sh:
            portfolio_manager.update_account_details(sh, {"Execution Mode": new_mode})
            clear_cache()
            return self._send_json_response(200, {
                "status": "success", 
                "execution_mode": new_mode,
                "message": f"Execution mode updated to '{new_mode}' in Google Sheets Account worksheet."
            })
        else:
            return self._send_json_response(500, {"status": "error", "message": "Could not connect to Google Sheets spreadsheet."})

def run_gateway_server(host: str = "0.0.0.0", port: int = 8085):
    """Starts the MDP Gateway REST API server."""
    env_port = os.environ.get("GATEWAY_PORT") or os.environ.get("PORT")
    if env_port and env_port.isdigit():
        port = int(env_port)

    server_address = (host, port)
    httpd = ThreadedHTTPServer(server_address, MDPGatewayRequestHandler)
    logger.info(f"🚀 Service Beta MDP Gateway Server running on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping MDP Gateway Server...")
        httpd.server_close()

if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8085
    run_gateway_server(port=port_arg)

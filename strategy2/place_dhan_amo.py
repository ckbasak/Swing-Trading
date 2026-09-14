"""
place_dhan_amo.py
Script to place After Market Orders (AMO) on Dhan as per portfolio restructuring recommendations.
"""

import os
import sys
import logging
from typing import Dict, Any, List
import dhan_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RECOMMENDED_ORDERS: List[Dict[str, Any]] = [
    # --- COMPLETE EXITS (SELL CNC) ---
    {
        "symbol": "ONGC",
        "security_id": "2475",
        "action": "SELL",
        "quantity": 35,
        "price": 237.00,
        "order_type": "LIMIT",
        "reason": "Complete exit - cyclical drag"
    },
    {
        "symbol": "PETRONET",
        "security_id": "11351",
        "action": "SELL",
        "quantity": 25,
        "price": 288.50,
        "order_type": "LIMIT",
        "reason": "Complete exit - overlap with GAIL"
    },
    {
        "symbol": "LICI",
        "security_id": "9480",
        "action": "SELL",
        "quantity": 22,
        "price": 405.00,
        "order_type": "LIMIT",
        "reason": "Complete exit - lagging performance"
    },
    # --- PROFIT BOOKING / TRIMS (SELL CNC) ---
    {
        "symbol": "BEML",
        "security_id": "395",
        "action": "SELL",
        "quantity": 9,
        "price": 2025.00,
        "order_type": "LIMIT",
        "reason": "Trim 43% - derisk 17.7% single-stock concentration"
    },
    {
        "symbol": "BDL",
        "security_id": "2144",
        "action": "SELL",
        "quantity": 8,
        "price": 1195.00,
        "order_type": "LIMIT",
        "reason": "Trim 50% - reduce defence overweight"
    },
    # --- ACCUMULATION (BUY CNC) ---
    {
        "symbol": "BEL",
        "security_id": "383",
        "action": "BUY",
        "quantity": 25,
        "price": 405.00,
        "order_type": "LIMIT",
        "reason": "Accumulate - consolidate defence exposure into BEL (~Rs 10,125)"
    }
]

def place_amos(dry_run: bool = True):
    """
    Places the AMOs through DhanHQ API.
    If dry_run=True, only prints the planned orders without submitting.
    """
    client = dhan_client.get_dhan_client()
    if not dry_run and not client:
        logger.error("DhanHQ client is not configured or failed to initialize.")
        return

    print("=" * 65)
    print(f"DHAN AFTER MARKET ORDER (AMO) EXECUTION {'[DRY RUN]' if dry_run else '[LIVE]'}")
    print("=" * 65)

    for item in RECOMMENDED_ORDERS:
        sym = item["symbol"]
        sec_id = item["security_id"]
        action = item["action"]
        qty = item["quantity"]
        px = item["price"]
        ord_type = item["order_type"]
        reason = item["reason"]

        print(f"\nScrip: {sym} (ID: {sec_id})")
        print(f"  -> Action: {action} | Qty: {qty} | Type: {ord_type} @ Rs. {px:.2f}")
        print(f"  -> Note: {reason}")

        if dry_run:
            print("  -> [DRY RUN] Order preview only. Pass --live to execute.")
            continue

        try:
            exchange_seg = client.NSE
            txn_type = client.SELL if action == "SELL" else client.BUY
            prod_type = client.CNC
            order_type_val = client.LIMIT if ord_type == "LIMIT" else client.MARKET

            resp = client.place_order(
                security_id=sec_id,
                exchange_segment=exchange_seg,
                transaction_type=txn_type,
                quantity=qty,
                order_type=order_type_val,
                product_type=prod_type,
                price=px,
                after_market_order=True,
                amo_time="OPEN"
            )
            print(f"  -> Dhan Response: {resp}")
        except Exception as e:
            print(f"  -> Error placing order: {e}")

    print("\n" + "=" * 65)

if __name__ == "__main__":
    is_live = "--live" in sys.argv
    place_amos(dry_run=not is_live)

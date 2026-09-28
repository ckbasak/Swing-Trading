import os
import streamlit as st
import dhan_client
import portfolio_manager
from typing import Optional, Dict, Any

def render_dual_execution_panel(
    sh,
    ticker: str,
    entry_price: float,
    quantity: int,
    initial_sl: float,
    target: float,
    strategy_name: str = "Strategy",
    key_prefix: str = "trade"
) -> None:
    """
    Renders dual manual execution controls in Streamlit:
    1. 🧪 Execute Paper Trade (simulated log to Google Sheets)
    2. 🚀 Execute Live Dhan Trade (with Pre-Flight checks & Confirmation Modal)
    """
    clean_sym = ticker.replace(".NS", "").upper()
    comp_name = portfolio_manager.get_company_name(ticker)
    total_cost = round(entry_price * quantity, 2)
    
    st.markdown(f"### ⚙️ Trade Execution Control: **{clean_sym}** ({comp_name})")
    st.markdown(f"• **Qty**: `{quantity} shares` | **Price**: `₹{entry_price:,.2f}` | **Total Val**: `₹{total_cost:,.2f}` | **SL**: `₹{initial_sl:,.2f}` | **Target**: `₹{target:,.2f}`")
    
    col_paper, col_live = st.columns(2)
    
    # 1. Paper Trade Execution Button
    with col_paper:
        if st.button(f"🧪 Execute Paper Trade ({clean_sym})", key=f"btn_paper_{key_prefix}", use_container_width=True, type="secondary"):
            res = portfolio_manager.add_position(
                sh, ticker, entry_price, quantity, initial_sl, target,
                execution_type="PAPER_SIMULATED"
            )
            if "Successfully" in res:
                st.success(f"🧪 **Paper Trade Executed!** {res}")
                st.toast(f"Paper trade logged for {clean_sym} x {quantity}", icon="🧪")
            else:
                st.warning(res)
                
    # 2. Live Dhan Execution Button & Confirmation Modal
    with col_live:
        confirm_key = f"show_confirm_live_{key_prefix}"
        if st.button(f"🚀 Execute Live Dhan Trade ({clean_sym})", key=f"btn_live_{key_prefix}", use_container_width=True, type="primary"):
            st.session_state[confirm_key] = True
            
        if st.session_state.get(confirm_key, False):
            st.markdown("---")
            st.warning("⚠️ **LIVE REAL-MONEY TRADE CONFIRMATION REQUIRED**")
            
            # Perform Live Pre-flight verification
            preflight = dhan_client.validate_live_preflight(ticker, quantity, entry_price)
            
            st.markdown(f"""
            #### 📋 Order Summary before Exchange Dispatch:
            - **Stock Symbol**: `{clean_sym}` ({comp_name})
            - **Exchange / Segment**: `NSE Equity (Delivery / CNC)`
            - **Transaction Type**: `BUY`
            - **Order Type**: `MARKET`
            - **Quantity**: `{quantity} shares`
            - **Estimated Order Value**: `₹{total_cost:,.2f}`
            - **Stop Loss**: `₹{initial_sl:,.2f}` | **Target**: `₹{target:,.2f}`
            - **Pre-Flight Check**: `{'🟢 PASSED' if preflight['valid'] else '🔴 FAILED'}`
            - **Pre-Flight Notice**: `{preflight['reason']}`
            """)
            
            if not preflight["valid"]:
                st.error(f"Cannot proceed with Live Order: {preflight['reason']}")
                if st.button("Close Notice", key=f"btn_close_err_{key_prefix}"):
                    st.session_state[confirm_key] = False
                    st.rerun()
            else:
                if not preflight.get("market_open", True):
                    st.info(f"ℹ️ {preflight.get('market_notice')}. Order will be placed as delivery order on Dhan.")
                    
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("🟢 CONFIRM & SEND REAL ORDER TO DHAN", key=f"btn_confirm_dhan_{key_prefix}", type="primary", use_container_width=True):
                        dhan_res = dhan_client.place_dhan_order(
                            ticker, quantity, transaction_type="BUY", order_type="MARKET",
                            price=entry_price, stop_loss=initial_sl, target=target
                        )
                        if dhan_res.get("success"):
                            order_id = dhan_res.get("order_id", "")
                            log_res = portfolio_manager.add_position(
                                sh, ticker, entry_price, quantity, initial_sl, target,
                                execution_type="LIVE_DHAN", order_id=order_id
                            )
                            st.balloons()
                            st.success(f"🚀 **LIVE ORDER DISPATCHED TO DHAN!** Order ID: `{order_id}`. {log_res}")
                            st.session_state[confirm_key] = False
                        else:
                            st.error(f"Dhan Exchange Order Failed: {dhan_res.get('message')}")
                            
                with col_no:
                    if st.button("🛑 Cancel & Close", key=f"btn_cancel_live_{key_prefix}", use_container_width=True):
                        st.session_state[confirm_key] = False
                        st.rerun()

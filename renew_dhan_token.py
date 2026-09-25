import os
import sys
import logging
import dhan_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def renew_active_token():
    """Attempts automatic 24h extension using the active unexpired Dhan Access Token."""
    logger.info("Attempting automatic token renewal via GET https://api.dhan.co/v2/RenewToken...")
    new_token = dhan_client.renew_dhan_token_via_api()
    if new_token:
        print("SUCCESS: Token renewed automatically! Valid for another 24 hours.")
        return True
    else:
        print("NOTICE: Automatic API renewal failed (likely because current token is already expired or invalid).")
        return False

def update_manual_token(new_token: str):
    """Updates token manually from user input or argument."""
    success = dhan_client.set_dhan_access_token(new_token)
    if success:
        print("SUCCESS: Connected to live Dhan account!")
    else:
        print("ERROR: Token verification failed. Please check your Dhan Access Token from web.dhan.co.")
    return success

if __name__ == "__main__":
    dhan_client._load_env()
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        renew_active_token()
    elif len(sys.argv) > 1:
        update_manual_token(sys.argv[1])
    else:
        print("1. Automatic 24h Token Renewal (Requires currently active token)")
        print("2. Manual Token Update")
        choice = input("Select option (1 or 2): ").strip()
        if choice == "1":
            renew_active_token()
        else:
            token_arg = input("Enter new Dhan Access Token: ").strip()
            update_manual_token(token_arg)

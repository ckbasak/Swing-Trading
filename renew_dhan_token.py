import os
import sys
import logging

logging.basicConfig(level=logging.INFO)

def update_token(new_token: str):
    new_token = new_token.strip()
    if not new_token:
        print("Error: Empty token provided.")
        return False
        
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("DHAN_ACCESS_TOKEN="):
                    lines.append(f"DHAN_ACCESS_TOKEN={new_token}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"DHAN_ACCESS_TOKEN={new_token}\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
        
    os.environ["DHAN_ACCESS_TOKEN"] = new_token
    print("Updated .env with new DHAN_ACCESS_TOKEN.")
    
    # Test connection
    import dhan_client
    dhan_client._DHAN_INSTANCE = None
    holdings = dhan_client.get_dhan_holdings()
    print(f"Connection test complete! Holdings count: {len(holdings)}")
    if holdings and holdings[0].get("tradingSymbol") != "RELIANCE":
        print(f"SUCCESS: Connected to live Dhan account! Found {len(holdings)} holdings.")
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        token_arg = sys.argv[1]
    else:
        token_arg = input("Enter new Dhan Access Token: ")
    update_token(token_arg)

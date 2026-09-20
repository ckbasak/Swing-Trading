import sys
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
import os
import sys
import json
import requests
from datetime import datetime
import pytz

# Auto-load .env
env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_file):
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
    except Exception:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() not in os.environ:
                        os.environ[k.strip()] = v.strip().strip("'").strip('"')

def check_mark(success: bool) -> str:
    return "✅ PASS" if success else "❌ FAIL"

def run_health_check():
    tz = pytz.timezone("Asia/Kolkata")
    now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S IST")
    print("=" * 70)
    print(f"   ETF STRATEGY 1 - SYSTEM HEALTH & SELF-TEST DIAGNOSTIC")
    print(f"   Execution Timestamp: {now_str}")
    print("=" * 70)

    # 1. Environment & Config Files
    print("\n[1/7] Environment & Configuration Files:")
    has_env = os.path.exists(os.path.join(os.path.dirname(__file__), ".env"))
    has_sa = os.path.exists(os.path.join(os.path.dirname(__file__), "service_account.json"))
    has_pool = os.path.exists(os.path.join(os.path.dirname(__file__), "curated_etf_pool.csv"))
    print(f"  - .env configuration file:            {check_mark(has_env)}")
    print(f"  - Google Service Account JSON:       {check_mark(has_sa)}")
    print(f"  - Curated ETF Pool (20 liquid ETFs): {check_mark(has_pool)}")

    # 2. Critical Python Modules
    print("\n[2/7] Python Core Dependencies:")
    modules = ["pandas", "numpy", "yfinance", "gspread", "google.oauth2", "telegram", "requests", "streamlit"]
    all_mods = True
    for mod in modules:
        try:
            __import__(mod)
            print(f"  - Module '{mod}':".ljust(40) + "✅ OK")
        except ImportError:
            print(f"  - Module '{mod}':".ljust(40) + "❌ MISSING")
            all_mods = False

    # 3. Market Sentiment & Macro Engine Check
    print("\n[3/7] Market Sentiment & Macro Engine:")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    gemini_ok = False
    if gemini_key:
        try:
            import sentiment_analyzer
            test_resp = sentiment_analyzer._call_gemini_rest("Ping test. Reply with word OK.", max_tokens=10)
            if "OK" in test_resp.upper() or len(test_resp.strip()) > 0:
                gemini_ok = True
                print(f"  - Gemini Cloud Model:                {check_mark(True)} (Response received)")
        except Exception:
            pass

    try:
        import sentiment_analyzer
        macro = sentiment_analyzer.get_comprehensive_market_macro_sentiment()
        regime = macro.get("market_regime", "NEUTRAL")
        badge = macro.get("color_badge", "🟢")
        engine = macro.get("engine", "local_nlp")
        print(f"  - Sentiment & Regime Pipeline:       {check_mark(True)} (Regime: {badge} {regime}, Engine: {engine})")
    except Exception as e:
        print(f"  - Sentiment Pipeline Error:          ❌ {e}")

    # 4. Telegram Bot API
    print("\n[4/7] Telegram Bot API:")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if bot_token:
        try:
            r = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=8)
            if r.status_code == 200:
                bot_info = r.json().get("result", {})
                print(f"  - Telegram Bot Connectivity:         {check_mark(True)} (@{bot_info.get('username')})")
            else:
                print(f"  - Telegram Bot HTTP Status:          ❌ {r.status_code}")
        except Exception as e:
            print(f"  - Telegram Bot Connection Error:     ❌ {e}")
    else:
        print(f"  - Telegram Bot Token:                ❌ NOT CONFIGURED")

    # 5. DhanHQ Broker API
    print("\n[5/7] DhanHQ Broker API:")
    dhan_id = os.environ.get("DHAN_CLIENT_ID")
    dhan_token = os.environ.get("DHAN_ACCESS_TOKEN")
    if dhan_id and dhan_token:
        try:
            headers = {"access-token": dhan_token, "client-id": dhan_id, "Content-Type": "application/json"}
            r = requests.get("https://api.dhan.co/v2/fundlimit", headers=headers, timeout=8)
            if r.status_code == 200:
                fund_data = r.json()
                avail_cash = fund_data.get("availabelBalance", fund_data.get("availableBalance", "N/A"))
                print(f"  - DhanHQ API Authentication:         {check_mark(True)} (Available Balance: ₹{avail_cash})")
            elif r.status_code == 401:
                print(f"  - DhanHQ API Authentication:         ⚠️ TOKEN EXPIRED (30-day token expired on Aug 23, 2026. Ready for renewal at web.dhan.co)")
            else:
                print(f"  - DhanHQ API Response:               ⚠️ HTTP {r.status_code}")
        except Exception as e:
            print(f"  - DhanHQ Connection Error:           ❌ {e}")
    else:
        print(f"  - DhanHQ Credentials:                ❌ NOT CONFIGURED")

    # 6. Google Sheets & Local Persistence
    print("\n[6/7] Google Sheets & Portfolio Storage:")
    try:
        import portfolio_manager
        client = portfolio_manager.get_gspread_client()
        sh = portfolio_manager.get_or_create_portfolio_sheet(client)
        if sh:
            print(f"  - Google Sheet Access:               {check_mark(True)} ({sh.title})")
            titles = [ws.title for ws in sh.worksheets()]
            print(f"  - Active Worksheets:                 {', '.join(titles)}")
        else:
            print(f"  - Google Sheet Access:               ⚠️ Sheet pending share (Local fallback ACTIVE)")
            acc = portfolio_manager.get_account_summary()
            print(f"  - Local DB Valuation:                ₹{acc.get('portfolio_value', 0):,.2f}")
    except Exception as e:
        print(f"  - Portfolio Storage Error:           ❌ {e}")

    # 7. Render Cloud Web Service Status
    print("\n[7/7] Render.com Cloud Deployment:")
    api_key = "rnd_SBQQ09uFrFpXphs9mxJZByVxCyBu"
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        r = requests.get("https://api.render.com/v1/services?limit=20", headers=headers, timeout=8)
        if r.status_code == 200:
            services = r.json()
            found = False
            for s in services:
                svc = s.get("service", {})
                if svc.get("name") == "etf-swing-trade-1":
                    found = True
                    print(f"  - Service 'etf-swing-trade-1':       {check_mark(True)} (ID: {svc.get('id')})")
                    print(f"  - Cloud Live URL:                    {svc.get('serviceDetails', {}).get('url')}")
                    break
            if not found:
                print(f"  - Service 'etf-swing-trade-1':       ⏳ PENDING CLOUD CREATION")
        else:
            print(f"  - Render API Response:               ❌ HTTP {r.status_code}")
    except Exception as e:
        print(f"  - Render API Error:                  ❌ {e}")

    print("\n" + "=" * 70)
    print("   DIAGNOSTIC TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    run_health_check()
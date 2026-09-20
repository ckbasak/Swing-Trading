#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unified System Health Check & Disaster Recovery Verification Script
Tests all 3 strategies, Google Sheets, Telegram Bots, Render Cloud Services, and Dhan Broker.
"""
import os
import sys
import json
import requests
from datetime import datetime
import pytz

sys.stdout.reconfigure(encoding='utf-8')

def print_header(title):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)

def check_python_environment():
    print_header("1. Python Environment & Dependencies")
    print(f"Python Executable: {sys.executable}")
    print(f"Python Version   : {sys.version.split()[0]}")
    
    required_packages = [
        "streamlit", "telegram", "gspread", "google.auth",
        "yfinance", "pandas", "numpy", "langgraph", "pytz",
        "plotly", "requests", "google.generativeai", "dhanhq"
    ]
    missing = []
    for pkg in required_packages:
        try:
            __import__(pkg)
            print(f"  [OK] {pkg}")
        except ImportError:
            print(f"  [MISSING] {pkg}")
            missing.append(pkg)
            
    if missing:
        print(f"\n⚠️ Warning: Missing packages: {missing}. Run: pip install -r requirements.txt")
    else:
        print("\nAll 13 core packages installed successfully.")

def check_google_sheets():
    print_header("2. Google Sheets Connections")
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("gspread or google-auth not installed.")
        return

    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    base_dir = r"c:\Users\ckbas\Documents\antigravity"
    
    portfolios = [
        ("Strategy 1", "AI-Swing-Trade-1", "NSE_Swing_Trading_Portfolio_1"),
        ("Strategy 2", "AI-Swing-Trade-2", "NSE_Swing_Trading_Portfolio_2"),
        ("Strategy 3", "AI-Swing-Trade-3", "NSE_Swing_Trading_Portfolio_3"),
    ]
    
    for label, folder, sheet_name in portfolios:
        sa_path = os.path.join(base_dir, folder, "service_account.json")
        if not os.path.exists(sa_path):
            sa_path = os.path.join(base_dir, "AI-Swing-Trade", "service_account.json")
        if not os.path.exists(sa_path):
            print(f"  [FAIL] {label}: service_account.json missing at {sa_path}")
            continue
            
        try:
            creds = Credentials.from_service_account_file(sa_path, scopes=scopes)
            client = gspread.authorize(creds)
            sh = client.open(sheet_name)
            tabs = [ws.title for ws in sh.worksheets()]
            print(f"  [OK] {label} ('{sheet_name}') opened successfully. Tabs: {tabs}")
        except Exception as e:
            print(f"  [FAIL] {label} ('{sheet_name}'): {e}")

def check_telegram_bots():
    print_header("3. Telegram Bots Status")
    bots = [
        ("Strategy 1", "8804741632:AAGQh-8oEMP25MupgadwikXcWpFWTNPwjUw"),
        ("Strategy 2", "8776408528:AAGexszfsf0DmRHFtS5CrPo_QmsN06QXc_A"),
        ("Strategy 3", "8821130913:AAHL-oB8ZVAHU95QguFC3I7kxVT5XaaOaWc"),
    ]
    for label, token in bots:
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
            if r.status_code == 200:
                data = r.json().get("result", {})
                print(f"  [OK] {label}: @{data.get('username')} ('{data.get('first_name')}') is online! ID: {data.get('id')}")
            else:
                print(f"  [FAIL] {label}: HTTP {r.status_code} - {r.text}")
        except Exception as e:
            print(f"  [FAIL] {label}: {e}")

def check_render_cloud():
    print_header("4. Render Cloud Services")
    api_key = "rnd_SBQQ09uFrFpXphs9mxJZByVxCyBu"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    
    services = [
        ("Strategy 1 (ai-swing-trade-1)", "srv-dadtqevqj5pc739g956g"),
        ("Strategy 2 (ai-swing-trade-2)", "srv-dadibjmq1p3s73dpvnt0"),
        ("Strategy 3 (ai-swing-trade-3)", "srv-daethr1t0dsc73bn2btg"),
    ]
    
    for label, s_id in services:
        try:
            r = requests.get(f"https://api.render.com/v1/services/{s_id}", headers=headers, timeout=10)
            if r.status_code == 200:
                s = r.json().get("service", r.json())
                details = s.get("serviceDetails", {})
                status = s.get("suspended", "active")
                print(f"  [OK] {label}: Status={status} | URL={details.get('url')} | Plan={details.get('plan')}")
            else:
                print(f"  [FAIL] {label}: HTTP {r.status_code}")
        except Exception as e:
            print(f"  [FAIL] {label}: {e}")

def check_dhan_broker():
    print_header("5. DhanHQ Broker Configuration")
    try:
        import dhan_client
        configured = dhan_client.is_dhan_configured()
        print(f"  Dhan Configured: {'[OK] True' if configured else '[WARN] False (Missing credentials)'}")
        if configured:
            print(f"  Dhan Client ID : {dhan_client.DHAN_CLIENT_ID}")
            print("  Testing symbol map sync from Dhan CDN...")
            try:
                smap = dhan_client.load_symbol_map()
                print(f"  [OK] Dhan Scrip Master loaded: {len(smap)} symbols.")
            except Exception as e:
                print(f"  [WARN] Dhan scrip master fetch: {e}")
    except Exception as e:
        print(f"  [FAIL] Error loading dhan_client: {e}")

if __name__ == "__main__":
    tz = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S IST")
    print(f"=================================================================")
    print(f"  AI SWING TRADING SYSTEM - UNIFIED HEALTH CHECK")
    print(f"  Verification Timestamp: {now_ist}")
    print(f"=================================================================")
    
    check_python_environment()
    check_google_sheets()
    check_telegram_bots()
    check_render_cloud()
    check_dhan_broker()
    
    print("\n" + "=" * 65)
    print("  DIAGNOSTIC HEALTH CHECK COMPLETE")
    print("=" * 65 + "\n")

# 📘 ETF Strategy 1: System Operation & Rebuild Guide

This guide details the complete configuration, operation, and disaster recovery procedures for **ETF Strategy 1**.

---

## 1. Master Credentials & Vault

| Parameter | Configuration / Value |
| :--- | :--- |
| **Project Directory** | `c:\Users\ckbas\Documents\antigravity\ETF-Swing-Trade-1` |
| **GitHub Repository** | `https://github.com/ckbasak/Swing-Trading.git` |
| **Git Branch** | `etf-strategy-1` |
| **Render Service Name** | `etf-swing-trade-1` |
| **Render Cloud URL** | `https://etf-swing-trade-1.onrender.com` |
| **Google Sheet Name** | `NSE_ETF_Swing_Trading_Portfolio_1` |
| **Google Service Account** | `sheets-editor@swing-trade-system-506815.iam.gserviceaccount.com` |
| **DhanHQ Client ID** | `1100223344` |
| **Telegram Admin ID** | `6493910665` |
| **Local Web Port** | `8504` |
| **Cloud Web Port** | `10000` |

---

## 2. Google Sheet Setup & Auto-Initialization

### Step 1: Create Google Sheet in Your Google Drive
1. Open Google Drive with your Google account (`ckbasak@gmail.com`).
2. Click **+ New ➔ Google Sheets**.
3. Rename the sheet exactly to:
   ```text
   NSE_ETF_Swing_Trading_Portfolio_1
   ```
4. Click **Share** (top right) ➔ Add:
   ```text
   sheets-editor@swing-trade-system-506815.iam.gserviceaccount.com
   ```
   Role: **Editor**, Uncheck "Notify people", Click **Share**.

### Step 2: Run Auto-Initialization Command
Run this command from your terminal to automatically build all 5 worksheets and columns:
```powershell
cd c:\Users\ckbas\Documents\antigravity\ETF-Swing-Trade-1
python -c "import portfolio_manager; client=portfolio_manager.get_gspread_client(); sh=client.open('NSE_ETF_Swing_Trading_Portfolio_1'); portfolio_manager.initialize_portfolio_sheet(sh); print('Google Sheet initialized successfully!')"
```

---

## 3. Render.com Cloud Deployment
The web service runs automatically 24/7 on Render.com via:
- Build Command: `pip install -r requirements.txt`
- Start Command: `sh start.sh`
- The `start.sh` script launches `bot.py` in the background and `streamlit run app.py` on `$PORT`.
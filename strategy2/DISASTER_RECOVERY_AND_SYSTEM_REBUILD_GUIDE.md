# 🛡️ Master Disaster Recovery & System Rebuild Guide
## AI Swing Trading System (Strategy 1, Strategy 2 & Strategy 3)

> **Document Version:** 1.0  
> **Last Verified:** September 2026  
> **Applicable Strategies:**  
> - **Strategy 1:** `AI-Swing-Trade-1` (Branch: `main`) — Multi-Timeframe Momentum & Breakout  
> - **Strategy 2:** `AI-Swing-Trade-2` (Branch: `strategy-2`) — Volume Contraction Pattern (VCP) & Stage 2 Growth  
> - **Strategy 3:** `AI-Swing-Trade-3` (Branch: `strategy-3`) — Pullback & 20 EMA Dynamic Trend Follower  

---

## 📑 Table of Contents
1. [Master Credential Vault & Configuration](#1-master-credential-vault--configuration)
2. [Disaster Scenario A: Complete Laptop / Local Machine Crash](#2-disaster-scenario-a-complete-laptop--local-machine-crash)
3. [Disaster Scenario B: Google Sheets Corruption or Accidental Deletion](#3-disaster-scenario-b-google-sheets-corruption-or-accidental-deletion)
4. [Disaster Scenario C: Render.com Cloud Crash or Migration](#4-disaster-scenario-c-rendercom-cloud-crash-or-migration)
5. [Disaster Scenario D: Telegram Bot Compromise or Deletion](#5-disaster-scenario-d-telegram-bot-compromise-or-deletion)
6. [Disaster Scenario E: Dhan Broker API Token Expiry & PIN Renewal](#6-disaster-scenario-e-dhan-broker-api-token-expiry--pin-renewal)
7. [Disaster Scenario F: Gemini AI API Key Renewal](#7-disaster-scenario-f-gemini-ai-api-key-renewal)
8. [Automated System Health & Self-Test Script](#8-automated-system-health--self-test-script)

---

## 1. Master Credential Vault & Configuration

> [!CAUTION]
> Treat all credentials in this section with the highest level of security. Store an offline copy in an encrypted password vault (e.g., Bitwarden, 1Password, or a password-protected USB drive).

### 1.1 Git & GitHub Repository
- **Remote Repository URL:** `https://github.com/ckbasak/Swing-Trading.git`
- **GitHub Username:** `ckbasak`
- **Registered Email:** `ckbasak@gmail.com`
- **Personal Access Token (PAT):** `<YOUR_GITHUB_TOKEN>`
- **Branch Topology:**
  - `main` ➔ Strategy 1 (`AI-Swing-Trade-1`)
  - `strategy-2` ➔ Strategy 2 (`AI-Swing-Trade-2`)
  - `strategy-3` ➔ Strategy 3 (`AI-Swing-Trade-3`)

---

### 1.2 Google Sheets & Google Cloud Platform (GCP)
- **GCP Project ID:** `swing-trade-system-506815`
- **Service Account Client Email:** `sheets-editor@swing-trade-system-506815.iam.gserviceaccount.com`
- **Service Account Client ID:** `113545457566185715433`
- **Service Account Key ID:** `<YOUR_KEY_ID>`
- **Required GCP Scopes:**
  1. `https://www.googleapis.com/auth/spreadsheets`
  2. `https://www.googleapis.com/auth/drive`
- **Spreadsheets:**
  | Portfolio | Spreadsheet Name | Spreadsheet ID | Direct URL |
  | :--- | :--- | :--- | :--- |
  | **Strategy 1** | `NSE_Swing_Trading_Portfolio_1` | `1SGGgkcVqef04xHMxCpb__qFgrUGyVtsJjgvysapbb6c` | [Open Sheet 1](https://docs.google.com/spreadsheets/d/1SGGgkcVqef04xHMxCpb__qFgrUGyVtsJjgvysapbb6c/edit) |
  | **Strategy 2** | `NSE_Swing_Trading_Portfolio_2` | `1kBLrVqC8JLNY_n_ktVKyQs9CaE6u69_3Zq6vXriLcCc` | [Open Sheet 2](https://docs.google.com/spreadsheets/d/1kBLrVqC8JLNY_n_ktVKyQs9CaE6u69_3Zq6vXriLcCc/edit) |
  | **Strategy 3** | `NSE_Swing_Trading_Portfolio_3` | `1dWGjtTejuhAH2iA987BLgbYmKean_j1e7CW7moG8NMY` | [Open Sheet 3](https://docs.google.com/spreadsheets/d/1dWGjtTejuhAH2iA987BLgbYmKean_j1e7CW7moG8NMY/edit) |

#### Full `service_account.json` Content:
Save this exact JSON as `service_account.json` in each strategy folder:
```json
{
  "type": "service_account",
  "project_id": "swing-trade-system-506815",
  "private_key_id": "<YOUR_KEY_ID>",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDJ/9QF/M8Pwh4v\nRcxoPQClS+usds8lgmjggeXDW1Jay7hchaZtdgUXWqEl2bKs3kqwU6Vc88+lOajA\nN9hpUGm4YGE/MZjlrOoEZHeZy5rxE+6w4WtHjQNP1vnm8InGjpQ2Dd6Q5HVw/x1A\nuL216WTNCsoA6bkxyIL4aciSjoDakeaqTuE0ZUHia4uqK2rEX5ognUr26gY6v6eY\nHtLp/rNFCIv2CtDs4Epg3XaX17QzwzSpy4pSDAO7lKaFFCBWJeHWVvrb9V+KXgT0\naAX87G5aljbKSzIhvtRZAnkwbQWBsGF4+iNArDIX08CFal+GTkVpTWxhOBJ9ITsB\nvy9Y/sWDAgMBAAECggEAGppFmxBDWMjw3rrrg6LdDefkvs7a0w7MrxyMXOEPBIQl\n4JF9bJcJbpzx8iEshdW0smohsg8t/o2Matwv9RaxBaYzyHXItB7EpxVwJuIIos1E\nNylIzqCEmiQuvzpYerzWShQjhqN/0ATZHmf2HBoDu3k7R0mAqUzF6t9LmfmIgMBQ\nKmcKwIgS//vsBWVonD/AUhtWIbCIMC2Op19nf6R35tHcno9Z+he2EjUr4545rsuk\nukb+NFXHSJbUI+d9Uxan3ZOkgV2tMYz7CeSyN3hirYi3d5gosS7C8YHUwfC0hQJZ\nXIA7lfTS53ivgugPsHHNMLXBNGTcZahKc0ETBkN9qQKBgQD3lTqkBJASxjXaFEEY\nG0YOG5mzXUv94pVLFsux72Seki/cQgiTG5v9Ls+h+EIpdzgzotOlzT+YrrB6Fcmt\nsAp08CR2z/G3z8n++FBWyoee3HOLR6WaqHUT+FzF/hPgSqrj5KqAl1xHa49efLMW\nL8mRzFghPWHt8Nu+b9BeJDh8BQKBgQDQ3d/py0npfsYj6uFGt66alk0sQgKV3QXD\n52KGxb9v3dTgc9qZXccor5H3H/OWJ7n4hFoGaTb4V5pTrvuiDxOJfCzv7AjrDS14\nLnbF0qlSaqqap2hGXyxiQbfQkT+I4f0V65WaHRCnqTlouEJ3NTHuDxBYsMBv/Sss\nrZcxFq755wKBgEB3qipVSdKprBIaHg0R5P79bttGmugEHQ3NZMLzbAbiV/YJd8Qe\nd1LI4qXxSAEWGxtO9b+Bn2K5chiIHdjNMxvaABSz9uP/BkEPFZRT7laOXsPQpy2L\nWdkWXcnsa+6GYtMukrsjLpMmTdGztMo9LUZ6qCQXoK1df0qqQN6SnealAoGASPt+\nZj82kHRP3/UOypscU7/5L2HRbXRRs2aCsv0eK4SkAdn5pGV0Ve8jXeq4PtuazA/T\nNTJGlvhlYKBgJPyHox7UxPEBHMD6BmiV8AHwUHAdNPUSJqTS6XJ1PFfEj5wHx0UO\nfU9ypmMnQERCVU0tKTXyTEtWsssP7wipL+nxMjkCgYB23RyT1YWIX95qbba9Dsqu\nTjd8tKqsMdBVx1QpEU/t6gXD/A0G/LASEJZjupHeKi8Oz33YlFkXVQc+2yd5mQ1r\njTFVu9wAVSIZ+3woy9gQSVZmRxuIQa2q8KP1nWW2Jzl1VgcjXV7Q5EnMQ6GvkNMF\nJJCcX/JKRpKGI6BJrOEdsw==\n-----END PRIVATE KEY-----\n",
  "client_email": "sheets-editor@swing-trade-system-506815.iam.gserviceaccount.com",
  "client_id": "113545457566185715433",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/sheets-editor%40swing-trade-system-506815.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}
```

---

### 1.3 Telegram Bots & Admin Chat
- **Registered Admin Chat ID:** `6493910665` (Your Telegram Account)
- **Telegram Bots:**
  | Bot | Name | Username | Bot ID | Bot Token |
  | :--- | :--- | :--- | :---: | :--- |
  | **Strategy 1** | `AI Swing Trade 1` | `@ai_swing_trade_1_bot` | `8804741632` | `<YOUR_TELEGRAM_BOT_TOKEN>` |
  | **Strategy 2** | `AI Swing Trade 2` | `@ai_swing_trade_2_bot` | `8776408528` | `<YOUR_TELEGRAM_BOT_TOKEN>` |
  | **Strategy 3** | `AI Swing Trade 3` | `@ai_swing_trade_3_bot` | `8821130913` | `<YOUR_TELEGRAM_BOT_TOKEN>` |

---

### 1.4 Render.com Cloud Web Services
- **Render Account:** `ckbasak@gmail.com`
- **Render API Key:** `rnd_SBQQ09uFrFpXphs9mxJZByVxCyBu`
- **Deployed Services:**
  | Service Name | Strategy | Service ID | Region | Live Webhook / Dashboard URL |
  | :--- | :--- | :--- | :---: | :--- |
  | `ai-swing-trade-1` | Strategy 1 | `srv-dadtqevqj5pc739g956g` | Oregon | `https://ai-swing-trade-1.onrender.com` |
  | `ai-swing-trade-2` | Strategy 2 | `srv-dadibjmq1p3s73dpvnt0` | Oregon | `https://ai-swing-trade-2.onrender.com` |
  | `ai-swing-trade-3` | Strategy 3 | `srv-daethr1t0dsc73bn2btg` | Oregon | `https://ai-swing-trade-3.onrender.com` |

---

### 1.5 DhanHQ Broker API & Authentication
- **Broker:** Dhan (https://web.dhan.co)
- **Dhan Client ID:** `1100223344` (Account / Dhan User ID: `1101177354`)
- **Dhan Access Token (JWT):**
  ```text
  <YOUR_DHAN_ACCESS_TOKEN>
  ```
- **Login PIN / Authentication:**
  - Dhan Web portal uses **Mobile OTP + Password + 6-digit MPIN** (or Authenticator TOTP).
  - API token does **not** require daily browser login; it is valid continuously until expired or revoked.

---

### 1.6 Google Gemini AI API
- **Gemini API Key:** `<YOUR_GEMINI_API_KEY>`
- **Model Used:** `gemini-2.5-flash` (via `google-generativeai`)
- **Management Console:** https://aistudio.google.com/

---

## 2. Disaster Scenario A: Complete Laptop / Local Machine Crash

If your laptop dies, hard drive is corrupted, or you get a brand new computer:

### Step 1: Install Prerequisites
1. Download and install **Python 3.10+** (Python 3.11 or 3.12 recommended) from [python.org](https://www.python.org/downloads/).
   - ⚠️ Check the box: **"Add Python to PATH"**.
2. Download and install **Git** from [git-scm.com](https://git-scm.com/download/win).

### Step 2: Clone the Repositories
Open PowerShell or Terminal and create your base folder:
```powershell
mkdir C:\Users\ckbas\Documents\antigravity
cd C:\Users\ckbas\Documents\antigravity

# Clone Strategy 1 (main branch)
git clone -b main https://<YOUR_GITHUB_TOKEN>@github.com/ckbasak/Swing-Trading.git AI-Swing-Trade-1

# Clone Strategy 2 (strategy-2 branch)
git clone -b strategy-2 https://<YOUR_GITHUB_TOKEN>@github.com/ckbasak/Swing-Trading.git AI-Swing-Trade-2

# Clone Strategy 3 (strategy-3 branch)
git clone -b strategy-3 https://<YOUR_GITHUB_TOKEN>@github.com/ckbasak/Swing-Trading.git AI-Swing-Trade-3
```

### Step 3: Install Python Dependencies
Run this command in any strategy folder (all 3 share the identical dependencies):
```powershell
cd C:\Users\ckbas\Documents\antigravity\AI-Swing-Trade-2
pip install -r requirements.txt
```

*Required packages installed:*
`streamlit`, `python-telegram-bot[all]`, `gspread`, `google-auth`, `yfinance`, `pandas`, `numpy`, `langgraph`, `pytz`, `plotly`, `requests`, `google-generativeai`, `dhanhq`

### Step 4: Recreate `.env` and `service_account.json`
In each strategy folder, recreate the two configuration files:

#### 1. In `AI-Swing-Trade-1/.env`:
```env
TELEGRAM_BOT_TOKEN=<YOUR_TELEGRAM_BOT_TOKEN>
GEMINI_API_KEY=<YOUR_GEMINI_API_KEY>
DHAN_CLIENT_ID=1100223344
DHAN_ACCESS_TOKEN=<YOUR_DHAN_ACCESS_TOKEN>
SPREADSHEET_NAME=NSE_Swing_Trading_Portfolio_1
PORT=8501
```

#### 2. In `AI-Swing-Trade-2/.env`:
```env
TELEGRAM_BOT_TOKEN=<YOUR_TELEGRAM_BOT_TOKEN>
GEMINI_API_KEY=<YOUR_GEMINI_API_KEY>
DHAN_CLIENT_ID=1100223344
DHAN_ACCESS_TOKEN=<YOUR_DHAN_ACCESS_TOKEN>
SPREADSHEET_NAME=NSE_Swing_Trading_Portfolio_2
PORT=8502
```

#### 3. In `AI-Swing-Trade-3/.env`:
```env
TELEGRAM_BOT_TOKEN=<YOUR_TELEGRAM_BOT_TOKEN>
GEMINI_API_KEY=<YOUR_GEMINI_API_KEY>
DHAN_CLIENT_ID=1100223344
DHAN_ACCESS_TOKEN=<YOUR_DHAN_ACCESS_TOKEN>
SPREADSHEET_NAME=NSE_Swing_Trading_Portfolio_3
PORT=8503
ACTIVE_STOCK_POOL=curated_pool_top_50.csv
RISK_PERCENT=6.0
VOLUME_MULTIPLIER=2.25
ATR_STOP_MULTIPLIER=2.0
TARGET_1_MULTIPLIER=2.0
TARGET_2_MULTIPLIER=4.5
MAX_POSITIONS_PER_SECTOR=3
MAX_TOTAL_POSITIONS=10
```

#### 4. Save `service_account.json`:
Place the JSON content from Section 1.2 into:
- `C:\Users\ckbas\Documents\antigravity\AI-Swing-Trade-1\service_account.json`
- `C:\Users\ckbas\Documents\antigravity\AI-Swing-Trade-2\service_account.json`
- `C:\Users\ckbas\Documents\antigravity\AI-Swing-Trade-3\service_account.json`

### Step 5: Test Execution
To run locally:
```powershell
# Launch Streamlit dashboard
streamlit run app.py

# Or launch Telegram bot
python bot.py
```

---

## 3. Disaster Scenario B: Google Sheets Corruption or Accidental Deletion

If any of the 3 Google Sheets is deleted or corrupted:

### Step 1: Create a New Google Sheet
1. Go to [Google Drive](https://drive.google.com).
2. Click **+ New ➔ Google Sheets**.
3. Rename the sheet exactly to match:
   - `NSE_Swing_Trading_Portfolio_1` (for Strategy 1)
   - `NSE_Swing_Trading_Portfolio_2` (for Strategy 2)
   - `NSE_Swing_Trading_Portfolio_3` (for Strategy 3)

### Step 2: Grant Editor Access to Service Account
1. Click the **Share** button in the top right.
2. In the "Add people" field, paste:
   ```text
   sheets-editor@swing-trade-system-506815.iam.gserviceaccount.com
   ```
3. Set role to **Editor** and uncheck "Notify people", then click **Share**.

### Step 3: Run the Auto-Initialize Command
The codebase is built to self-heal and automatically initialize all worksheets, column headers, and baseline account records! Run this one-liner:
```powershell
cd C:\Users\ckbas\Documents\antigravity\AI-Swing-Trade-2
python -c "import portfolio_manager; client=portfolio_manager.get_gspread_client(); portfolio_manager.get_or_create_portfolio_sheet(client, 'NSE_Swing_Trading_Portfolio_2'); print('Spreadsheet successfully initialized!')"
```

### Worksheet Architecture Reference:
- **`Account` (2 Columns):**
  `['Parameter', 'Value']`
  Rows: `Initial Capital` (100,000.00), `Cash Balance` (100,000.00), `Total Portfolio Value` (100,000.00), `Capital Risk %` (1.5%), `Risk Per Trade` (1,500.00), `Max Open Positions` (10), `Max Positions Per Sector` (3).
- **`Holdings` (19 Columns):**
  `['Ticker', 'Company Name', 'Entry Date', 'Entry Price', 'Quantity', 'Entry Value', 'Initial SL', 'Current SL', 'Target', 'Status', 'Exit Date', 'Exit Price', 'Exit Value', 'Gross PnL', 'Exit Reason', 'Total Charges', 'Net PnL', 'Est. Tax (20%)', 'Net Return %']`
- **`TelegramChats` (1 Column):**
  `['ChatID']`  
  Row 2: `6493910665`
- **`Schedules` (6 Columns):**
  `['Date', 'Time', 'Mode', 'Status', 'Last Run', 'Notes']`
  Default active automated schedule rows:
  1. `['WEEKDAYS', '8:00', 'PREVIEW', 'ACTIVE', '', 'Morning Pre-Market Scan']`
  2. `['WEEKDAYS', '8:30', 'SENTIMENT', 'ACTIVE', '', 'Market Sentiment Scan']`
  3. `['WEEKDAYS', '9:00', 'SENTIMENT', 'ACTIVE', '', 'Portfolio']`
  4. `['WEEKDAYS', '15:25', 'EXECUTE', 'ACTIVE', '', 'Scan and execute']`
  5. `['WEEKDAYS', '18:00', 'NEWS', 'ACTIVE', '', 'Portfolio']`
- **`DebugLogs` (3 Columns):**
  `['Timestamp IST', 'Source', 'Message']`

---

## 4. Disaster Scenario C: Render.com Cloud Crash or Migration

If Render experiences an outage, account suspension, or services need to be recreated from scratch:

### Option 1: Automatic Re-creation via Render API (Instant)
You can deploy all three services programmatically using the Render API key:
```python
import requests, json

api_key = "rnd_SBQQ09uFrFpXphs9mxJZByVxCyBu"
headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

# Query your Render Owner / Team ID
r = requests.get("https://api.render.com/v1/owners", headers=headers)
owner_id = r.json()[0]["owner"]["id"]

# Deploy Service Payload Template
services_to_deploy = [
    ("ai-swing-trade-1", "main", "NSE_Swing_Trading_Portfolio_1", "<YOUR_TELEGRAM_BOT_TOKEN>"),
    ("ai-swing-trade-2", "strategy-2", "NSE_Swing_Trading_Portfolio_2", "<YOUR_TELEGRAM_BOT_TOKEN>"),
    ("ai-swing-trade-3", "strategy-3", "NSE_Swing_Trading_Portfolio_3", "<YOUR_TELEGRAM_BOT_TOKEN>")
]
```

### Option 2: Manual Web Dashboard Deployment
1. Log into [dashboard.render.com](https://dashboard.render.com).
2. Click **New + ➔ Web Service**.
3. Connect your GitHub repository: `https://github.com/ckbasak/Swing-Trading`.
4. Configure service settings:
   - **Name:** `ai-swing-trade-1` (or 2 / 3)
   - **Branch:** `main` (Strategy 1), `strategy-2` (Strategy 2), `strategy-3` (Strategy 3)
   - **Region:** `Oregon (US West)` or `Singapore`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `sh start.sh`
   - **Instance Type:** `Free`
5. Under **Environment Variables**, add the 6 variables:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` = *(paste full JSON from Section 1.2 on a single line or as multiline)*
   - `TELEGRAM_BOT_TOKEN` = *(from Section 1.3)*
   - `GEMINI_API_KEY` = `<YOUR_GEMINI_API_KEY>`
   - `DHAN_CLIENT_ID` = `1100223344`
   - `DHAN_ACCESS_TOKEN` = `<YOUR_DHAN_ACCESS_TOKEN>`
   - `SPREADSHEET_NAME` = `NSE_Swing_Trading_Portfolio_1` (or 2 / 3)
6. Click **Deploy Web Service**.
7. Render runs `start.sh`, which automatically spins up the `bot.py` background daemon and the Streamlit web app!

---

## 5. Disaster Scenario D: Telegram Bot Compromise or Deletion

If a Telegram bot token is compromised or a bot is deleted:

### Step 1: Create a New Bot with BotFather
1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`.
3. Give it a Name (e.g., `AI Swing Trade 2`) and a Username (e.g., `ai_swing_trade_2_custom_bot`).
4. `@BotFather` will reply with the HTTP API Token (format: `1234567890:ABCdef...`).

### Step 2: Configure Menu & Bot Commands
Send `@BotFather` `/setcommands`, select your new bot, and paste:
```text
start - 🚀 Start bot & register notifications
menu - 📱 Open interactive main dashboard menu
scan - 🔍 Run real-time market scan
news - 🌐 Market sentiment & holding news briefing
positions - 📈 View live open positions & SL
summary - 🏦 Portfolio capital & risk summary
history - 🤝 Completed trade log & PnL
schedules - 📅 View & manage automated scan schedules
```

### Step 3: Update Token in System
1. Update `TELEGRAM_BOT_TOKEN` in your local `.env`.
2. Update `TELEGRAM_BOT_TOKEN` in Render Dashboard ➔ Service ➔ **Environment**. Render will auto-redeploy.
3. Open Telegram, open the new bot, and click `/start`. The bot will automatically register your `ChatID` (`6493910665`) into the Google Sheet.

---

## 6. Disaster Scenario E: Dhan Broker API Token Expiry & PIN Renewal

DhanHQ Access Tokens expire periodically (typically every 30 days depending on Dhan policy).

### Step 1: Generate New DhanHQ Access Token
1. Go to [web.dhan.co](https://web.dhan.co) and login using:
   - Registered Mobile Number
   - Password
   - 6-digit MPIN / Authenticator TOTP
2. Click on your **Profile Avatar** (top right) ➔ **Access DhanHQ APIs** (or direct URL: https://web.dhan.co/dhanhq).
3. Under the **API Access** tab:
   - Click **Generate New Token**.
   - Set validity (select max duration, typically 30 days).
   - Check all permissions (Orders, Portfolio, Market Quotes).
   - Click **Generate**.
4. Copy:
   - **Client ID** (e.g. `1100223344` or your 10-digit ID)
   - **Access Token** (starts with `eyJ0...`)

### Step 2: Update Across System
1. Replace `DHAN_ACCESS_TOKEN` in `.env` across `AI-Swing-Trade-1`, `AI-Swing-Trade-2`, and `AI-Swing-Trade-3`.
2. Update `DHAN_ACCESS_TOKEN` in Render.com under Environment Variables for all 3 services.
3. Verify connection locally:
   ```powershell
   python -c "import dhan_client; print('Dhan Configured:', dhan_client.is_dhan_configured()); print('LTP Test:', dhan_client.get_dhan_ltp(['RELIANCE.NS']))"
   ```

---

## 7. Disaster Scenario F: Gemini AI API Key Renewal

If Gemini returns `API_KEY_INVALID` or rate limits:
1. Visit [Google AI Studio](https://aistudio.google.com/).
2. Click **Get API key** ➔ **Create API key in new project**.
3. Copy the key (starts with `AQ...` or `AIza...`).
4. Update `GEMINI_API_KEY` in local `.env` and in Render.com environment variables.

---

## 8. Automated System Health & Self-Test Script

We have bundled a complete diagnostic script that you can run anytime to verify that all 3 strategies, Google Sheets, Telegram bots, Dhan, and Render are in 100% operational condition.

Run this command from your terminal:
```powershell
python "C:\Users\ckbas\Documents\antigravity\AI-Swing-Trade-2\system_health_check.py"
```

*(Script definition provided in the next section).*

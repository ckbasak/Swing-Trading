# Manage-Dhan-Portfolio | Credentials, Authentication & Security Reference 🔐

This document provides a complete technical specification of the authentication parameters, security PINs, TOTP secrets, API tokens, service account credentials, and automated renewal mechanisms implemented in **Manage-Dhan-Portfolio**.

---

## 🔑 Environment Credentials Reference (`.env`)

The project reads its environment parameters from `.env` (local development) or cloud environment variables (Render web service).

```env
# Telegram Bot Integration
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE

# Gemini AI Integration (Optional)
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE

# Dhan API Credentials & TOTP Authentication
DHAN_CLIENT_ID=1101177354
DHAN_USER_PIN=2317
DHAN_TOTP_SECRET=CHDBD3GAY7TTXLKJZH4RJCQ33GMJNW3M
DHAN_ACCESS_TOKEN=YOUR_DHAN_ACCESS_TOKEN_HERE

# Google Sheets Synchronization
SPREADSHEET_NAME=NSE_Dhan_Portfolio_Manager

# Streamlit Port Configuration
PORT=8502
```

---

## 🛡️ Detailed Breakdown of Credentials & Security Parameters

### 1. Dhan Client ID (`DHAN_CLIENT_ID`)
- **Value**: `1101177354`
- **Purpose**: The 10-digit primary account identification number issued by Dhan.
- **Usage**:
  - Sent as the `dhanClientId` HTTP header in all DhanHQ API v2 endpoints (`/v2/holdings`, `/v2/fundlimit`, `/v2/RenewToken`).
  - Required for initializing the official `dhanhq` Python client library (`dhanhq(client_id, access_token)`).

### 2. Dhan User PIN (`DHAN_USER_PIN`)
- **Value**: `2317`
- **Purpose**: The 4-digit numeric security PIN assigned to your Dhan trading account.
- **Usage**:
  - Used by the TOTP Auto-Authentication Failsafe module (`renew_access_token_via_totp()`) in `dhan_client.py`.
  - Passed in payload requests when generating fresh access tokens via Dhan's authentication API.

### 3. Dhan TOTP Secret (`DHAN_TOTP_SECRET`)
- **Value**: `CHDBD3GAY7TTXLKJZH4RJCQ33GMJNW3M`
- **Purpose**: The 32-character Base32 secret key linked to your Dhan 2-Factor Authentication (2FA).
- **Usage**:
  - Processed by the Python `pyotp` library (`pyotp.TOTP(totp_secret).now()`) to generate real-time, time-synchronized 6-digit one-time passcodes without manual authenticator app intervention.
  - Formats: Strips spaces automatically and normalizes to uppercase prior to TOTP calculation.

### 4. Dhan Access Token (`DHAN_ACCESS_TOKEN`)
- **Value**: 24-Hour JWT Access Token starting with `eyJ0eXAiOiJKV1QiLCJhbGci...`
- **Validity**: 24 Hours from issuance.
- **Header Key**: `access-token`
- **Auto-Renewal Mechanism**:
  - **12-Hour Background Thread**: `dhan_client.py` runs a background daemon that sends a `GET` request to `https://api.dhan.co/v2/RenewToken` every 12 hours.
  - **30-Minute Retry Loop**: If network instability prevents renewal, retries up to 6 times at 30-minute intervals.
  - **TOTP Auto-Auth Failsafe**: If token expires completely, automatically generates a new token via `DHAN_USER_PIN` + `DHAN_TOTP_SECRET`.
  - **Persistence**: Upon successful renewal, updates memory (`os.environ`), `.env` on disk, and [cached_settings.json](file:///c:/Users/ckbas/Documents/antigravity/Manage-Dhan-Portfolio/cached_settings.json) across Render container restarts.

### 5. Telegram Bot Token (`TELEGRAM_BOT_TOKEN`)
- **Value**: `8846086245:AAHeM2s85bmfHpOy1MZ_f45l3myND4C3z3Y`
- **Purpose**: Unique token authorizing the Telegram bot daemon (`bot.py`) for `@manage_dhan_portfolio_bot`.
- **Usage**: Receives Telegram webhook / polling updates and sends portfolio advisory messages, rebalancing inline keyboards, and alerts.

### 6. Google Service Account (`service_account.json` / `GOOGLE_SERVICE_ACCOUNT_JSON`)
- **File**: `service_account.json`
- **Cloud Env**: `GOOGLE_SERVICE_ACCOUNT_JSON`
- **Purpose**: Google Cloud IAM Service Account credentials formatted as a JSON object.
- **Usage**:
  - Authorizes `gspread` with `spreadsheets` and `drive` scopes to read, create, and update spreadsheet `NSE_Dhan_Portfolio_Manager`.

---

## 🔄 Authentication Flow & Failsafe Sequence

```
                         [ App Initialization ]
                                   │
                                   ▼
                      [ Check DHAN_ACCESS_TOKEN ]
                                   │
              ┌────────────────────┴────────────────────┐
       [ Token Active ]                          [ Token Expired ]
              │                                         │
              ▼                                         ▼
   [ Execute API Calls ]                    [ Trigger TOTP Auto-Auth ]
              │                                         │
              ▼                                         ▼
   [ 12-Hour Renewal Loop ]                  [ Compute pyotp(TOTP_SECRET) ]
   (GET /v2/RenewToken)                                 │
              │                                         ▼
              │                             [ POST AccessToken Request ]
              │                             (ClientId + PIN + TOTP)
              │                                         │
              └────────────────────┬────────────────────┘
                                   │
                                   ▼
                      [ Persist New Token to: ]
                      1. os.environ
                      2. .env file
                      3. cached_settings.json
```

---

## 🔒 Security Best Practices

1. **Git Exclusions**: `.env` and `service_account.json` are strictly added to [.gitignore](file:///c:/Users/ckbas/Documents/antigravity/Manage-Dhan-Portfolio/.gitignore) and excluded from remote git repositories.
2. **Cloud Environment Variables**: On Render (`render.com`), store secrets (`DHAN_CLIENT_ID`, `DHAN_USER_PIN`, `DHAN_TOTP_SECRET`, `DHAN_ACCESS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `GOOGLE_SERVICE_ACCOUNT_JSON`) as masked Environment Variables in the service settings dashboard.
3. **Offline Fallback Resilience**: If API endpoints are unreachable, `dhan_client.py` gracefully falls back to [cached_holdings.json](file:///c:/Users/ckbas/Documents/antigravity/Manage-Dhan-Portfolio/cached_holdings.json) so analysis engines and Telegram bot commands operate seamlessly without crashing.

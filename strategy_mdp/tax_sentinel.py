"""
tax_sentinel.py - Autonomous Statutory Fee & Tax Regulatory Sentinel.

Periodically monitors official Indian financial news (Google News RSS / Regulatory circulars)
for changes in:
- STCG Tax Rates (Section 111A)
- STT (Securities Transaction Tax on Buy / Sell)
- Stamp Duty rates
- NSE / BSE Exchange Turnover charges
- SEBI turnover fees
- GST rates on brokerage & transaction charges
- CDSL / NSDL Depository Participant (DP) debit charges

Uses Gemini API REST integration to analyze whether any official/enacted revision
has occurred (filtering out rumors, pre-budget speculations, and opinions).
When an official change is confirmed, the sentinel:
1. Automatically updates the 'Account' sheet in Google Sheets.
2. Refreshes the local in-memory config and recalculates portfolio tax provisions.
3. Logs an audit entry to the 'DebugLogs' cloud sheet.
4. Returns an alert payload for Telegram broadcast.
"""

import os
import sys
import json
import logging
from typing import Dict, Any, List, Optional
import datetime
import pytz

try:
    import portfolio_manager
except ImportError:
    from . import portfolio_manager

try:
    import sentiment_analyzer
except ImportError:
    from . import sentiment_analyzer

logger = logging.getLogger(__name__)

REGULATORY_QUERIES = [
    "STT securities transaction tax rate equity delivery India",
    "STCG short term capital gains tax equity rate India Budget Section 111A",
    "NSE SEBI transaction charges fee equity cash delivery revision",
    "CDSL DP charges depository participant revision fee cut",
    "stamp duty rate equity delivery transfer shares India"
]

PARAM_NAME_MAPPING = {
    "stcg_tax_pct": "STCG Tax Rate %",
    "stt_buy_pct": "STT Buy Rate %",
    "stt_sell_pct": "STT Sell Rate %",
    "stamp_duty_pct": "Stamp Duty Rate %",
    "nse_fee_pct": "NSE Fee Rate %",
    "sebi_fee_per_cr": "SEBI Fee Per Cr",
    "gst_pct": "GST Rate %",
    "dp_charges": "DP Charges Flat",
    "brokerage_flat": "Brokerage Flat"
}

def scan_regulatory_news(max_per_query: int = 2) -> List[Dict[str, str]]:
    """Fetches recent financial regulatory news articles via Google News RSS."""
    articles = []
    seen_titles = set()
    for q in REGULATORY_QUERIES:
        try:
            fetched = sentiment_analyzer._fetch_rss_articles(q, limit=max_per_query)
            for item in fetched:
                title_clean = item.get("title", "").strip().lower()
                if title_clean and title_clean not in seen_titles:
                    seen_titles.add(title_clean)
                    articles.append(item)
        except Exception as e:
            logger.debug(f"Error fetching regulatory news for '{q}': {e}")
    return articles

def check_for_rate_revisions(articles: Optional[List[Dict[str, str]]] = None, current_cfg: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """
    Analyzes regulatory news articles using Gemini API to identify enacted/official statutory changes.
    """
    if current_cfg is None:
        current_cfg = portfolio_manager.get_fee_and_tax_config()
        
    if articles is None:
        articles = scan_regulatory_news()
        
    if not articles:
        return {
            "has_official_change": False,
            "changes_detected": [],
            "news_summary": "No recent regulatory articles retrieved from news feeds.",
            "scanned_count": 0,
            "timestamp": datetime.datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S IST")
        }
        
    headlines_text = "\n".join([
        f"- Title: {a.get('title', '')} | Source: {a.get('source', '')} | Date: {a.get('pub_date', '')}"
        for a in articles[:12]
    ])
    
    prompt = f"""
You are an expert Indian regulatory compliance and tax analysis engine for NSE Equity Delivery swing trading.
Current active statutory rates in the trading system:
- STCG Tax Rate: {current_cfg.get('stcg_tax_pct', 20.0)}% (Section 111A of Income Tax Act)
- STT Buy Rate: {current_cfg.get('stt_buy_pct', 0.10)}%
- STT Sell Rate: {current_cfg.get('stt_sell_pct', 0.10)}%
- Stamp Duty: {current_cfg.get('stamp_duty_pct', 0.015)}%
- NSE Turnover Fee: {current_cfg.get('nse_fee_pct', 0.00297)}%
- SEBI Turnover Fee: ₹{current_cfg.get('sebi_fee_per_cr', 10.0)} / crore
- GST: {current_cfg.get('gst_pct', 18.0)}%
- DP Charges (Sell): ₹{current_cfg.get('dp_charges', 14.75)} flat per scrip

Review the following recent Indian financial news headlines:
{headlines_text}

TASK:
1. Determine if there is any ENROLLED, ENACTED, or OFFICIALLY NOTIFIED change by the Government of India, Ministry of Finance (CBDT), SEBI, NSE, or CDSL to any of these statutory rates for Equity Cash/Delivery (CNC) or Capital Gains Tax.
2. CRITICAL: Differentiate strictly between:
   - Official notified circulars or enacted Finance Bill changes -> FLAG AS OFFICIAL CHANGE.
   - Pre-budget wishes, rumors, media speculations, or industry demands -> DO NOT FLAG (has_official_change must be false).
3. If an official change has occurred for any parameter, identify the parameter, the new numeric rate, and summary.

You MUST respond ONLY with valid JSON in this schema:
{{
    "has_official_change": false,
    "changes_detected": [
        {{
            "parameter_key": "stcg_tax_pct",
            "account_label": "STCG Tax Rate %",
            "old_value": 20.0,
            "new_value": 22.0,
            "effective_date": "2026-04-01",
            "headline": "...",
            "source": "...",
            "summary": "..."
        }}
    ],
    "news_summary": "1-2 sentence objective summary of the current regulatory and tax environment based on the headlines."
}}
"""
    raw_res = sentiment_analyzer._call_gemini_rest(prompt, max_tokens=500, timeout=12.0)
    
    parsed_result = {
        "has_official_change": False,
        "changes_detected": [],
        "news_summary": "Regulatory news scan completed without parsing issues.",
        "scanned_count": len(articles),
        "timestamp": datetime.datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S IST")
    }
    
    if raw_res:
        clean_json = raw_res.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()
        try:
            parsed = json.loads(clean_json)
            parsed_result["has_official_change"] = bool(parsed.get("has_official_change", False))
            parsed_result["changes_detected"] = parsed.get("changes_detected", [])
            parsed_result["news_summary"] = parsed.get("news_summary", parsed_result["news_summary"])
        except Exception as e:
            logger.error(f"Error parsing Gemini regulatory response JSON: {e}")
            parsed_result["news_summary"] = f"Raw LLM output parsed with error: {e}"
            
    return parsed_result

def apply_regulatory_revision(change: Dict[str, Any], sh: Optional[Any] = None) -> bool:
    """
    Applies a detected regulatory revision to Google Sheets Account tab and recalculates.
    """
    try:
        if sh is None:
            client = portfolio_manager.get_gspread_client()
            sh = portfolio_manager.get_or_create_portfolio_sheet(client)
            
        param_label = change.get("account_label")
        param_key = change.get("parameter_key")
        if not param_label and param_key:
            param_label = PARAM_NAME_MAPPING.get(param_key, param_key)
            
        new_val = change.get("new_value")
        if param_label and new_val is not None:
            # Format value
            if "tax" in param_label.lower() or "rate" in param_label.lower() or "%" in param_label:
                formatted_val = f"{float(new_val):.2f}%" if not str(new_val).endswith("%") else str(new_val)
            elif "per cr" in param_label.lower() or "flat" in param_label.lower():
                formatted_val = f"₹{float(new_val):.2f}" if not str(new_val).startswith("₹") else str(new_val)
            else:
                formatted_val = str(new_val)
                
            portfolio_manager.update_account_details(sh, {param_label: formatted_val})
            portfolio_manager.get_fee_and_tax_config(sh, force_refresh=True)
            
            # Recalculate portfolio accounting under new rate
            portfolio_manager.sync_portfolio(sh)
            
            # Cloud log event
            headline = change.get("headline", "Regulatory notification")
            portfolio_manager.log_cloud_event(
                sh, 
                "tax_sentinel.py", 
                f"Statutory revision applied: {param_label} updated to {formatted_val} (Notice: {headline})"
            )
            logger.info(f"Successfully applied statutory revision: {param_label} -> {formatted_val}")
            return True
    except Exception as e:
        logger.error(f"Failed to apply regulatory revision {change}: {e}")
        return False

def run_sentinel_cycle(sh: Optional[Any] = None) -> Dict[str, Any]:
    """
    Runs the complete sentinel workflow:
    1. Scans regulatory news RSS.
    2. Uses Gemini to determine official enacted revisions.
    3. If revisions exist, automatically updates Google Sheets & recalculates portfolio.
    4. Returns comprehensive status report.
    """
    articles = scan_regulatory_news()
    current_cfg = portfolio_manager.get_fee_and_tax_config(sh, force_refresh=True)
    report = check_for_rate_revisions(articles, current_cfg)
    
    applied_changes = []
    if report.get("has_official_change") and report.get("changes_detected"):
        for chg in report["changes_detected"]:
            success = apply_regulatory_revision(chg, sh)
            if success:
                applied_changes.append(chg)
        report["applied_changes"] = applied_changes
        
    return report

def format_sentinel_status_message(report: Dict[str, Any], current_cfg: Dict[str, float], strategy_num: int = 3) -> str:
    """Formats a user-friendly Markdown message for Telegram."""
    ts = report.get("timestamp", datetime.datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%H:%M:%S IST"))
    lines = [
        f"🏛️ **Autonomous Tax & Regulatory Sentinel (Strategy #{strategy_num})**",
        f"📅 *Timestamp*: `{ts}`",
        "────────────────────────────"
    ]
    
    if report.get("has_official_change") and report.get("changes_detected"):
        lines.append("🚨 **OFFICIAL STATUTORY RATE REVISION DETECTED!**\n")
        for chg in report.get("changes_detected", []):
            label = chg.get("account_label", chg.get("parameter_key", "Parameter"))
            old_v = chg.get("old_value", "N/A")
            new_v = chg.get("new_value", "N/A")
            eff = chg.get("effective_date", "Immediate")
            summary = chg.get("summary", "")
            lines.append(f"• **{label}**: `{old_v}` ➔ **`{new_v}`**")
            lines.append(f"  _Effective_: `{eff}`")
            if summary:
                lines.append(f"  _Details_: {summary}")
        lines.append("\n✅ **Autonomous Actions Executed:**")
        lines.append("1. Updated active rates in Google Sheets (`Account` tab).")
        lines.append("2. Recalculated portfolio tax provisions and take-home yield.")
        lines.append("3. All subsequent trades will automatically adopt the new rate.")
        lines.append("────────────────────────────")
    else:
        lines.append("✅ **Statutory Rates Verified & Up-To-Date**")
        lines.append(f"Scanned `{report.get('scanned_count', 0)}` recent regulatory & exchange news sources.")
        lines.append(f"💡 *AI Sentinel Assessment*: {report.get('news_summary', 'No statutory revisions found.')}")
        lines.append("────────────────────────────")
        
    lines.extend([
        "📊 **Current System Rates:**",
        f"• STCG Tax (Sec 111A): `{current_cfg.get('stcg_tax_pct', 20.0):.1f}%`",
        f"• STT (Buy / Sell): `{current_cfg.get('stt_buy_pct', 0.10):.3f}%` / `{current_cfg.get('stt_sell_pct', 0.10):.3f}%`",
        f"• Stamp Duty (Buy): `{current_cfg.get('stamp_duty_pct', 0.015):.3f}%`",
        f"• NSE Turnover Fee: `{current_cfg.get('nse_fee_pct', 0.00297):.5f}%`",
        f"• SEBI Fee: `₹{current_cfg.get('sebi_fee_per_cr', 10.0):.0f} / Cr`",
        f"• GST: `{current_cfg.get('gst_pct', 18.0):.1f}%` | DP Charge: `₹{current_cfg.get('dp_charges', 14.75):.2f}`",
        f"• Delivery Brokerage: `₹{current_cfg.get('brokerage_flat', 0.0):.2f}` (Dhan Zero Delivery)"
    ])
    return "\n".join(lines)

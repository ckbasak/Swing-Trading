import sys
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os
import requests
import xml.etree.ElementTree as ET
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Auto-load .env if available
def _load_env():
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
_load_env()

api_key = os.environ.get("GEMINI_API_KEY")

def _fetch_rss_articles(query: str, hl: str = "en-IN", gl: str = "IN", ceid: str = "IN:en", limit: int = 5) -> List[Dict[str, str]]:
    """
    Generic Google News RSS scraper with configurable locale/region.
    """
    formatted_query = query.replace(" ", "+")
    rss_url = f"https://news.google.com/rss/search?q={formatted_query}&hl={hl}&gl={gl}&ceid={ceid}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    
    articles = []
    try:
        r = requests.get(rss_url, headers=headers, timeout=10)
        if r.status_code != 200:
            logger.warning(f"Google News RSS returned status code {r.status_code} for: {query}")
            return []
            
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        for item in items[:limit]:
            title_elem = item.find("title")
            source_elem = item.find("source")
            pub_date_elem = item.find("pubDate")
            link_elem = item.find("link")
            
            raw_title = title_elem.text if title_elem is not None and title_elem.text else ""
            source = source_elem.text if source_elem is not None and source_elem.text else ""
            if not source and " - " in raw_title:
                source = raw_title.rsplit(" - ", 1)[1].strip()
                
            title = raw_title.rsplit(" - ", 1)[0].strip() if " - " in raw_title else raw_title
            pub_date = pub_date_elem.text if pub_date_elem is not None and pub_date_elem.text else ""
            link = link_elem.text if link_elem is not None and link_elem.text else ""
            
            if title:
                articles.append({
                    "title": title,
                    "source": source,
                    "pub_date": pub_date,
                    "link": link
                })
        return articles
    except Exception as e:
        logger.error(f"Error scraping news for {query}: {e}")
        return []

def fetch_news_articles(query: str, limit: int = 5) -> List[Dict[str, str]]:
    """Scrapes Google News RSS for Indian market/equity queries."""
    return _fetch_rss_articles(query, hl="en-IN", gl="IN", ceid="IN:en", limit=limit)

def fetch_global_market_news(limit: int = 5) -> List[Dict[str, str]]:
    """Scrapes Google News RSS for macro cues (US Wall Street, Fed, crude oil, dollar index DXY)."""
    return _fetch_rss_articles(
        "global stock markets US Fed crude oil dollar index inflation",
        hl="en-US",
        gl="US",
        ceid="US:en",
        limit=limit
    )

def fetch_indian_market_news(limit: int = 5) -> List[Dict[str, str]]:
    """Scrapes Google News RSS for Indian domestic cues (Nifty 50, Bank Nifty, FII DII flows, RBI)."""
    return _fetch_rss_articles(
        "Nifty 50 Indian stock market Bank Nifty FII DII flows",
        hl="en-IN",
        gl="IN",
        ceid="IN:en",
        limit=limit
    )

def fetch_news_headlines(query: str) -> List[str]:
    """Scrapes Google News RSS for top headlines (string list for backward compatibility)."""
    articles = fetch_news_articles(query, limit=5)
    return [a["title"] for a in articles]

def _call_gemini_rest(prompt: str, max_tokens: int = 900, timeout: float = 8.0) -> str:
    """
    Direct HTTPS REST invocation to Google Gemini API.
    Bypasses gRPC channel timeouts on Windows for snappy, predictable execution.
    """
    if not api_key:
        return ""
        
    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_tokens
            }
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if r.status_code == 200:
                res = r.json()
                text = res['candidates'][0]['content']['parts'][0]['text']
                return text.strip()
            elif r.status_code in (401, 403):
                logger.debug(f"Gemini API key unauthorized (HTTP {r.status_code}). Using local NLP fallback.")
                return ""
            else:
                logger.debug(f"Gemini REST {model} returned status {r.status_code}: {r.text[:100]}")
        except Exception as e:
            logger.debug(f"Gemini REST {model} exception: {e}")
            continue
            
    return ""

def analyze_headlines_polarity(headlines: List[str]) -> str:
    """Fast, local keyword polarity engine as fallback or fast path."""
    positive_words = {
        "surge", "surges", "surged", "rally", "rallies", "gain", "gains", "jump", "jumps", 
        "profit", "growth", "high", "record", "beat", "beats", "bull", "bullish", "up", 
        "rise", "rises", "strong", "outperform", "inflows", "stimulus", "recovery", "dovish",
        "partnership", "expansion", "dividend"
    }
    negative_words = {
        "fall", "falls", "fell", "drop", "drops", "plunge", "plunges", "slump", "slumps", 
        "loss", "losses", "crash", "crashes", "down", "low", "weak", "bear", "bearish", 
        "decline", "declines", "selloff", "outflows", "dump", "hawkish", "tensions", "panic",
        "fraud", "probe", "penalty", "default", "scam"
    }
    pos_score = 0
    neg_score = 0
    for h in headlines:
        words = set(h.lower().replace("-", " ").replace(".", " ").replace(",", " ").split())
        pos_score += len(words.intersection(positive_words))
        neg_score += len(words.intersection(negative_words))
    if neg_score > pos_score and neg_score >= 2:
        return "BEARISH"
    elif pos_score > neg_score and pos_score >= 2:
        return "BULLISH"
    return "NEUTRAL"

def get_news_sentiment(query: str) -> str:
    """
    Scrapes recent headlines and determines sentiment with sub-second execution.
    Used for screening/filtering breakout candidates and position management.
    Returns: 'POSITIVE', 'NEUTRAL', or 'NEGATIVE'
    """
    headlines = fetch_news_headlines(query)
    if not headlines:
        return "NEUTRAL"
        
    prompt = (
        f"Analyze these news headlines related to '{query}' and return ONE single word: POSITIVE, NEUTRAL, or NEGATIVE.\n"
        + "\n".join(f"- {h}" for h in headlines)
    )
    raw = _call_gemini_rest(prompt, max_tokens=10, timeout=4.0)
    if raw:
        upper = raw.upper()
        if "POSITIVE" in upper or "BULLISH" in upper:
            return "POSITIVE"
        elif "NEGATIVE" in upper or "BEARISH" in upper:
            return "NEGATIVE"
        elif "NEUTRAL" in upper:
            return "NEUTRAL"
            
    pol = analyze_headlines_polarity(headlines)
    if pol == "BULLISH":
        return "POSITIVE"
    elif pol == "BEARISH":
        return "NEGATIVE"
    return "NEUTRAL"

def _fallback_comprehensive_macro(global_articles: List[Dict[str, str]], domestic_articles: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Bulletproof local NLP fallback engine for macro market sentiment & guardrails.
    Evaluates global & domestic news polarity, assigns color code and actionable guardrails.
    """
    g_pol = analyze_headlines_polarity([a["title"] for a in global_articles])
    d_pol = analyze_headlines_polarity([a["title"] for a in domestic_articles])
    
    if d_pol == "BEARISH" or (g_pol == "BEARISH" and d_pol != "BULLISH"):
        regime = "RISK-OFF"
        color = "RED"
        badge = "🔴"
        guard_breakouts = "HALT"
        guard_holdings = "TIGHTEN_SL_DAY_LOW"
        action_sum = "Market in Risk-Off mode. Pause all new breakout entries and tighten trailing stops on active holdings to today's Low."
    elif d_pol == "BULLISH" and g_pol != "BEARISH":
        regime = "RISK-ON"
        color = "GREEN"
        badge = "🟢"
        guard_breakouts = "ALLOW"
        guard_holdings = "STANDARD_TRAIL"
        action_sum = "Favorable risk-on market conditions. Standard breakout entries permitted with standard 20 EMA trailing stops."
    else:
        regime = "CAUTION"
        color = "YELLOW"
        badge = "🟡"
        guard_breakouts = "SELECTIVE"
        guard_holdings = "DEFENSIVE_TRAIL"
        action_sum = "Mixed market conditions. High-conviction volume breakouts only; monitor holding momentum closely."

    g_titles = [a["title"] for a in global_articles[:2]]
    d_titles = [a["title"] for a in domestic_articles[:2]]
    
    g_summary = f"Global news flow reflects {g_pol.lower()} cues across US markets, rate expectations, and commodities."
    d_summary = f"Indian domestic equities show {d_pol.lower()} cues amid ongoing institutional flow trends and technical consolidation."
    
    drivers = (g_titles + d_titles)[:3]
    if not drivers:
        drivers = ["Macro uncertainty and institutional rebalancing across global and domestic markets."]
        
    return {
        "market_regime": regime,
        "color": color,
        "color_badge": badge,
        "guardrail_breakouts": guard_breakouts,
        "guardrail_holdings": guard_holdings,
        "global_sentiment": g_pol,
        "domestic_sentiment": d_pol,
        "global_summary": g_summary,
        "domestic_summary": d_summary,
        "key_drivers": drivers,
        "action_summary": action_sum,
        "global_articles": global_articles,
        "domestic_articles": domestic_articles,
        "engine": "local_nlp"
    }

def get_comprehensive_market_macro_sentiment() -> Dict[str, Any]:
    """
    Performs dual-scope Global & Indian market news analysis.
    Evaluates:
    - Global cues (Wall St, Fed, crude oil, DXY)
    - Indian domestic cues (Nifty 50, Bank Nifty, FII/DII flows, RBI)
    Determines actionable guardrail directives:
    - Breakout entries: ALLOW (Green), SELECTIVE (Yellow), or HALT (Red)
    - Active holdings: STANDARD_TRAIL (Green), DEFENSIVE_TRAIL (Yellow), or TIGHTEN_SL_DAY_LOW (Red)
    """
    global_articles = fetch_global_market_news(limit=5)
    domestic_articles = fetch_indian_market_news(limit=5)
    
    if not global_articles and not domestic_articles:
        return _fallback_comprehensive_macro([], [])
        
    g_text = "\n".join([f"- {a['title']} ({a['source']})" for a in global_articles])
    d_text = "\n".join([f"- {a['title']} ({a['source']})" for a in domestic_articles])
    
    prompt = f"""You are a senior macro strategist and quantitative swing trading risk manager.
Analyze the following live financial news headlines across Global markets and Indian domestic equities:

[GLOBAL MARKET CUES (Wall St, US Fed, Crude Oil, DXY)]
{g_text}

[INDIAN DOMESTIC CUES (Nifty 50, Bank Nifty, FII/DII Flows, RBI)]
{d_text}

Synthesize both streams and provide an assessment in the EXACT structured format below:

REGIME: [Choose one: RISK-ON, CAUTION, or RISK-OFF]
COLOR: [Choose one: GREEN, YELLOW, or RED]
BREAKOUT_GUARDRAIL: [Choose one: ALLOW, SELECTIVE, or HALT]
HOLDINGS_GUARDRAIL: [Choose one: STANDARD_TRAIL, DEFENSIVE_TRAIL, or TIGHTEN_SL_DAY_LOW]
GLOBAL_SENTIMENT: [Choose one: BULLISH, NEUTRAL, or BEARISH]
DOMESTIC_SENTIMENT: [Choose one: BULLISH, NEUTRAL, or BEARISH]
GLOBAL_SUMMARY: [1-2 sentences summarizing global cues (US markets, Fed rate outlook, crude oil, dollar index)]
DOMESTIC_SUMMARY: [1-2 sentences summarizing Indian market cues (Nifty 50 trend, institutional flows, domestic macro)]
KEY_DRIVERS:
- [Driver 1: Key global or domestic catalyst/risk]
- [Driver 2: Key global or domestic catalyst/risk]
- [Driver 3: Key catalyst or risk]
ACTION_SUMMARY: [1 sentence summarizing guardrail rules for breakout entries and active holdings]
"""
    raw_response = _call_gemini_rest(prompt, max_tokens=900, timeout=8.0)
    if not raw_response:
        logger.info("Gemini REST unavailable or timed out; utilizing bulletproof local NLP fallback.")
        return _fallback_comprehensive_macro(global_articles, domestic_articles)
        
    # Parse structured output
    regime = "CAUTION"
    color = "YELLOW"
    breakout_guard = "SELECTIVE"
    holdings_guard = "DEFENSIVE_TRAIL"
    global_sent = "NEUTRAL"
    domestic_sent = "NEUTRAL"
    global_sum = ""
    domestic_sum = ""
    key_drivers = []
    action_sum = ""
    
    current_sec = None
    for line in raw_response.split("\n"):
        cleaned = line.strip()
        if not cleaned:
            continue
        upper = cleaned.upper()
        if upper.startswith("REGIME:"):
            v = cleaned.split(":", 1)[1].strip().upper()
            if "RISK-ON" in v or "BULLISH" in v:
                regime = "RISK-ON"
            elif "RISK-OFF" in v or "BEARISH" in v:
                regime = "RISK-OFF"
            else:
                regime = "CAUTION"
            current_sec = None
        elif upper.startswith("COLOR:"):
            v = cleaned.split(":", 1)[1].strip().upper()
            if "GREEN" in v:
                color = "GREEN"
            elif "RED" in v:
                color = "RED"
            else:
                color = "YELLOW"
            current_sec = None
        elif upper.startswith("BREAKOUT_GUARDRAIL:") or upper.startswith("BREAKOUT GUARDRAIL:"):
            v = cleaned.split(":", 1)[1].strip().upper()
            if "ALLOW" in v:
                breakout_guard = "ALLOW"
            elif "HALT" in v:
                breakout_guard = "HALT"
            else:
                breakout_guard = "SELECTIVE"
            current_sec = None
        elif upper.startswith("HOLDINGS_GUARDRAIL:") or upper.startswith("HOLDINGS GUARDRAIL:"):
            v = cleaned.split(":", 1)[1].strip().upper()
            if "TIGHTEN" in v:
                holdings_guard = "TIGHTEN_SL_DAY_LOW"
            elif "STANDARD" in v:
                holdings_guard = "STANDARD_TRAIL"
            else:
                holdings_guard = "DEFENSIVE_TRAIL"
            current_sec = None
        elif upper.startswith("GLOBAL_SENTIMENT:") or upper.startswith("GLOBAL SENTIMENT:"):
            v = cleaned.split(":", 1)[1].strip().upper()
            if "BULLISH" in v:
                global_sent = "BULLISH"
            elif "BEARISH" in v:
                global_sent = "BEARISH"
            else:
                global_sent = "NEUTRAL"
            current_sec = None
        elif upper.startswith("DOMESTIC_SENTIMENT:") or upper.startswith("DOMESTIC SENTIMENT:"):
            v = cleaned.split(":", 1)[1].strip().upper()
            if "BULLISH" in v:
                domestic_sent = "BULLISH"
            elif "BEARISH" in v:
                domestic_sent = "BEARISH"
            else:
                domestic_sent = "NEUTRAL"
            current_sec = None
        elif upper.startswith("GLOBAL_SUMMARY:") or upper.startswith("GLOBAL SUMMARY:"):
            global_sum = cleaned.split(":", 1)[1].strip()
            current_sec = "g_sum"
        elif upper.startswith("DOMESTIC_SUMMARY:") or upper.startswith("DOMESTIC SUMMARY:"):
            domestic_sum = cleaned.split(":", 1)[1].strip()
            current_sec = "d_sum"
        elif upper.startswith("KEY_DRIVERS:") or upper.startswith("KEY DRIVERS:"):
            current_sec = "drivers"
        elif upper.startswith("ACTION_SUMMARY:") or upper.startswith("ACTION SUMMARY:"):
            action_sum = cleaned.split(":", 1)[1].strip()
            current_sec = "action"
        else:
            if current_sec == "g_sum":
                global_sum += (" " + cleaned)
            elif current_sec == "d_sum":
                domestic_sum += (" " + cleaned)
            elif current_sec == "drivers":
                d = cleaned.lstrip("*-•0123456789. ")
                if d:
                    key_drivers.append(d)
            elif current_sec == "action":
                action_sum += (" " + cleaned)

    badge = "🟢" if color == "GREEN" else ("🔴" if color == "RED" else "🟡")
    
    return {
        "market_regime": regime,
        "color": color,
        "color_badge": badge,
        "guardrail_breakouts": breakout_guard,
        "guardrail_holdings": holdings_guard,
        "global_sentiment": global_sent,
        "domestic_sentiment": domestic_sent,
        "global_summary": global_sum.strip(),
        "domestic_summary": domestic_sum.strip(),
        "key_drivers": key_drivers,
        "action_summary": action_sum.strip(),
        "global_articles": global_articles,
        "domestic_articles": domestic_articles,
        "engine": "gemini_3.5_flash"
    }

def get_detailed_news_sentiment(query: str, ticker: str = "") -> Dict[str, Any]:
    """
    Performs an in-depth market and stock sentiment evaluation for an individual equity.
    Returns structured dictionary with verdict, confidence, summary, drivers, outlook, articles.
    """
    articles = fetch_news_articles(query, limit=5)
    if not articles:
        return {
            "query": query,
            "ticker": ticker,
            "verdict": "NEUTRAL",
            "confidence": "Low",
            "summary": f"No recent news headlines found for '{query}'. Sentiment is neutral by default.",
            "key_drivers": ["No prominent media coverage or corporate announcements in the last 72 hours."],
            "swing_outlook": "Trade purely on price action, volume breakout confirmation, and predefined stop-loss levels.",
            "articles": []
        }

    headlines_text = "\n".join(
        f"{idx}. {a['title']} (Source: {a['source']})" for idx, a in enumerate(articles, 1)
    )

    prompt = f"""You are a senior equity research and swing trading analyst for Indian NSE equities.
Analyze the following recent news headlines for '{query}' ({ticker}):

{headlines_text}

Provide your structured assessment in the exact format below:
VERDICT: [Choose one: POSITIVE, NEUTRAL, or NEGATIVE]
CONFIDENCE: [Choose one: High, Medium, or Low]
SUMMARY: [2-3 sentences explaining the overarching market sentiment and institutional narrative]
KEY_DRIVERS:
- [Driver 1: Key positive catalyst or risk]
- [Driver 2: Key positive catalyst or risk]
- [Driver 3: Optional additional driver]
SWING_OUTLOOK: [1-2 sentences with actionable implications for short-term swing traders]"""

    raw_text = _call_gemini_rest(prompt, max_tokens=700, timeout=7.0)
    if raw_text:
        verdict = "NEUTRAL"
        confidence = "Medium"
        summary = ""
        key_drivers = []
        swing_outlook = ""
        current_section = None
        
        for line in raw_text.split("\n"):
            cleaned = line.strip()
            if not cleaned:
                continue
            upper = cleaned.upper()
            if upper.startswith("VERDICT:"):
                val = cleaned.split(":", 1)[1].strip().upper()
                if "POSITIVE" in val or "BULLISH" in val:
                    verdict = "POSITIVE"
                elif "NEGATIVE" in val or "BEARISH" in val:
                    verdict = "NEGATIVE"
                else:
                    verdict = "NEUTRAL"
                current_section = None
            elif upper.startswith("CONFIDENCE:"):
                val = cleaned.split(":", 1)[1].strip().title()
                for c in ["High", "Medium", "Low"]:
                    if c.lower() in val.lower():
                        confidence = c
                        break
                current_section = None
            elif upper.startswith("SUMMARY:"):
                summary = cleaned.split(":", 1)[1].strip()
                current_section = "summary"
            elif upper.startswith("KEY_DRIVERS:") or upper.startswith("KEY DRIVERS:"):
                current_section = "drivers"
            elif upper.startswith("SWING_OUTLOOK:") or upper.startswith("SWING OUTLOOK:") or upper.startswith("SWING_IMPACT:"):
                swing_outlook = cleaned.split(":", 1)[1].strip()
                current_section = "outlook"
            else:
                if current_section == "summary":
                    summary += (" " + cleaned)
                elif current_section == "drivers":
                    d = cleaned.lstrip("*-•0123456789. ")
                    if d:
                        key_drivers.append(d)
                elif current_section == "outlook":
                    swing_outlook += (" " + cleaned)
                    
        return {
            "query": query,
            "ticker": ticker,
            "verdict": verdict,
            "confidence": confidence,
            "summary": summary.strip(),
            "key_drivers": key_drivers,
            "swing_outlook": swing_outlook.strip(),
            "articles": articles
        }

    # Fallback to local keyword polarity analysis
    polarity = analyze_headlines_polarity([a["title"] for a in articles])
    verdict_val = "POSITIVE" if polarity == "BULLISH" else ("NEGATIVE" if polarity == "BEARISH" else "NEUTRAL")
    summary = f"Analyzed {len(articles)} recent headlines via local NLP engine. News flow exhibits an overall {verdict_val.lower()} tone."
    drivers = [a["title"] for a in articles[:3]]
    outlook = "Review price action, support/resistance levels, and follow strict stop-loss rules."

    return {
        "query": query,
        "ticker": ticker,
        "verdict": verdict_val,
        "confidence": "Medium" if len(articles) >= 3 else "Low",
        "summary": summary,
        "key_drivers": drivers,
        "swing_outlook": outlook,
        "articles": articles
    }

def format_detailed_sentiment_report(data: Dict[str, Any]) -> str:
    """Formats the detailed individual stock sentiment dictionary into Telegram Markdown."""
    verdict = data.get("verdict", "NEUTRAL")
    confidence = data.get("confidence", "Medium")
    query = data.get("query", "")
    ticker = data.get("ticker", "")
    summary = data.get("summary", "")
    key_drivers = data.get("key_drivers", [])
    swing_outlook = data.get("swing_outlook", "")
    articles = data.get("articles", [])

    if verdict == "POSITIVE":
        verdict_badge = "🟢 POSITIVE (Bullish)"
    elif verdict == "NEGATIVE":
        verdict_badge = "🔴 NEGATIVE (Bearish / Caution)"
    else:
        verdict_badge = "⚪ NEUTRAL (Balanced)"

    sym_str = f" (`{ticker.replace('.NS', '')}`)" if ticker else ""

    lines = []
    lines.append("🌐 **Market & Stock Sentiment Analysis**")
    lines.append(f"🏢 **{query}**{sym_str}")
    lines.append("")
    lines.append(f"⚖️ **AI Verdict:** {verdict_badge}")
    lines.append(f"🎯 **Confidence:** `{confidence}`")
    lines.append("")
    
    if summary:
        lines.append("📝 **Executive Summary:**")
        lines.append(summary)
        lines.append("")
        
    if key_drivers:
        lines.append("🔑 **Key Catalysts & Risk Drivers:**")
        for d in key_drivers:
            lines.append(f"• {d}")
        lines.append("")
        
    if swing_outlook:
        lines.append("📈 **Swing Trading Outlook:**")
        lines.append(swing_outlook)
        lines.append("")
        
    if articles:
        lines.append(f"🗞️ **Top Recent Headlines Analyzed ({len(articles)}):**")
        for idx, a in enumerate(articles, 1):
            src = f" — *{a['source']}*" if a.get("source") else ""
            date_clean = a.get("pub_date", "")[:16]
            date_str = f" (`{date_clean}`)" if date_clean else ""
            lines.append(f"{idx}. {a['title']}{src}{date_str}")
    else:
        lines.append("• No recent news headlines found.")

    return "\n".join(lines)

def format_macro_sentiment_report(data: Dict[str, Any]) -> str:
    """
    Formats the comprehensive Global & Indian Market Sentiment & Macro Guardrail Briefing
    into a rich, color-coded Telegram Markdown report.
    """
    regime = data.get("market_regime", "CAUTION")
    color = data.get("color", "YELLOW")
    badge = data.get("color_badge", "🟡")
    b_guard = data.get("guardrail_breakouts", "SELECTIVE")
    h_guard = data.get("guardrail_holdings", "DEFENSIVE_TRAIL")
    g_sent = data.get("global_sentiment", "NEUTRAL")
    d_sent = data.get("domestic_sentiment", "NEUTRAL")
    g_sum = data.get("global_summary", "")
    d_sum = data.get("domestic_summary", "")
    drivers = data.get("key_drivers", [])
    action = data.get("action_summary", "")
    g_articles = data.get("global_articles", [])
    d_articles = data.get("domestic_articles", [])
    
    if color == "GREEN":
        banner = "🟢 **GUARDRAIL STATUS: RISK-ON (Favorable)**"
        b_desc = "Normal full-capacity breakout entries active"
        h_desc = "Standard 20 EMA trailing stop active"
    elif color == "RED":
        banner = "🔴 **GUARDRAIL STATUS: RISK-OFF (Capital Preservation)**"
        b_desc = "All new breakout entries PAUSED to prevent losses"
        h_desc = "Tighten trailing stops on all holdings to today's Low"
    else:
        banner = "🟡 **GUARDRAIL STATUS: CAUTION (Selective)**"
        b_desc = "High-conviction volume breakouts only; strict stops"
        h_desc = "Defensive trailing stop; tighten on momentum stall"
        
    g_badge = "🟢" if g_sent == "BULLISH" else ("🔴" if g_sent == "BEARISH" else "⚪")
    d_badge = "🟢" if d_sent == "BULLISH" else ("🔴" if d_sent == "BEARISH" else "⚪")
    
    lines = []
    lines.append("🌐 **Global & Indian Market News Analysis & Guardrails**")
    lines.append(banner)
    lines.append(f"🚦 **Market Regime:** `{regime}` | **Colour Code:** {badge} `{color}`")
    lines.append("")
    lines.append("🛡️ **Macro Guardrail Action Directives:**")
    lines.append(f"• 🛒 **Breakout Entries (New Buys):** {badge} `{b_guard}`")
    lines.append(f"  ↳ _{b_desc}_")
    lines.append(f"• 💼 **Holding Stocks (Existing):** {badge} `{h_guard}`")
    lines.append(f"  ↳ _{h_desc}_")
    lines.append("")
    if action:
        lines.append(f"📋 **Action Summary:** {action}")
        lines.append("")
    if g_sum:
        lines.append(f"🌍 **Global Market Cues (Wall St, Fed, Crude, DXY):**")
        lines.append(f"⚖️ Sentiment: {g_badge} `{g_sent}`")
        lines.append(g_sum)
        lines.append("")
    if d_sum:
        lines.append(f"🇮🇳 **Indian Domestic Cues (Nifty 50, FII/DII Flows, RBI):**")
        lines.append(f"⚖️ Sentiment: {d_badge} `{d_sent}`")
        lines.append(d_sum)
        lines.append("")
    if drivers:
        lines.append("🔑 **Key Catalysts & Risk Drivers:**")
        for dr in drivers:
            lines.append(f"• {dr}")
        lines.append("")
    if g_articles:
        lines.append("🗞️ **Top Global Headlines Analyzed:**")
        for idx, a in enumerate(g_articles[:3], 1):
            src = f" — *{a['source']}*" if a.get("source") else ""
            lines.append(f"{idx}. {a['title']}{src}")
        lines.append("")
    if d_articles:
        lines.append("🗞️ **Top Indian Headlines Analyzed:**")
        for idx, a in enumerate(d_articles[:3], 1):
            src = f" — *{a['source']}*" if a.get("source") else ""
            lines.append(f"{idx}. {a['title']}{src}")
            
    return "\n".join(lines)

def format_macro_sentiment_snippet(data: Dict[str, Any]) -> List[str]:
    """
    Compact list of lines for embedding inside scan reports in trading_graph.py.
    """
    if not data:
        return []
    regime = data.get("market_regime", "CAUTION")
    color = data.get("color", "YELLOW")
    badge = data.get("color_badge", "🟡")
    b_guard = data.get("guardrail_breakouts", "SELECTIVE")
    h_guard = data.get("guardrail_holdings", "DEFENSIVE_TRAIL")
    g_sent = data.get("global_sentiment", "NEUTRAL")
    d_sent = data.get("domestic_sentiment", "NEUTRAL")
    g_sum = data.get("global_summary", "")
    d_sum = data.get("domestic_summary", "")
    
    return [
        "🌐 **Global & Indian Market Sentiment & Macro Guardrails:**",
        f"• 🚦 Regime & Colour: {badge} **{regime}** (`{color}`)",
        f"• 🛒 Breakout Entries: {badge} `{b_guard}`",
        f"• 💼 Active Holdings: {badge} `{h_guard}`",
        f"• 🌍 Global Cues ({g_sent}): {g_sum}",
        f"• 🇮🇳 Indian Cues ({d_sent}): {d_sum}"
    ]

def render_streamlit_sentiment_card(strategy_key: str = "master"):
    """
    Renders an interactive Streamlit card displaying the specific strategy summary,
    its core rules/specifications, and its live effectiveness alignment with the current market macro sentiment.
    """
    import streamlit as st

    @st.cache_data(ttl=300)
    def _get_cached_macro():
        return get_comprehensive_market_macro_sentiment()

    try:
        macro = _get_cached_macro()
    except Exception as e:
        logger.error(f"Error fetching macro sentiment for Streamlit card: {e}")
        macro = _fallback_comprehensive_macro([], [])

    regime = macro.get("market_regime", "CAUTION")
    color = macro.get("color", "YELLOW")
    badge = macro.get("color_badge", "🟡")
    breakout_guard = macro.get("guardrail_breakouts", "SELECTIVE")
    holdings_guard = macro.get("guardrail_holdings", "DEFENSIVE_TRAIL")
    global_sent = macro.get("global_sentiment", "NEUTRAL")
    domestic_sent = macro.get("domestic_sentiment", "NEUTRAL")
    global_sum = macro.get("global_summary", "")
    domestic_sum = macro.get("domestic_summary", "")
    drivers = macro.get("key_drivers", [])
    action_sum = macro.get("action_summary", "")

    # Map effectiveness level based on market regime
    if regime == "RISK-ON":
        eff_title = "🟢 HIGH EFFECTIVENESS (Optimal Market Environment)"
        eff_desc = "Breakout momentum setups have maximum institutional follow-through. Full position allocation enabled."
        eff_color = "success"
    elif regime == "RISK-OFF":
        eff_title = "🔴 SUSPENDED / CAUTION (Adverse Market Environment)"
        eff_desc = "Broad market selling pressure increases false breakout risk. New buys paused; trail stops aggressively."
        eff_color = "error"
    else:
        eff_title = "🟡 MODERATE / SELECTIVE EFFECTIVENESS (Choppy / Mixed Market)"
        eff_desc = "Selective trade execution required. High-volume conviction entries only; strict risk parameters active."
        eff_color = "warning"

    # Strategy specifications mapping
    specs = {
        "strategy1": {
            "title": "📈 Strategy #1: Classic Breakout (Nifty 50)",
            "universe": "Nifty 50 Index Equities (Blue-Chip Liquidity)",
            "trigger": "Close > 20-period SMA + Volume > 2.0x 20-day Average",
            "exit": "Trailing 20-period EMA or Stop Loss (Recent 5-day Low)",
            "risk": "1.0% Capital Risk per Trade",
            "metrics": "Net Return +231.48% | Win Rate 49.0% | Profit Factor 2.45x | Max DD -12.80%"
        },
        "strategy2": {
            "title": "🎯 Strategy #2: Dynamic ATR & Sector Concentration Limits",
            "universe": "Nifty 50 Index Equities",
            "trigger": "Multi-period Breakout + Volume Surge (>2.5x SMA)",
            "exit": "Dynamic Trailing Stop at 2.0x Average True Range (ATR)",
            "risk": "1.5% Capital Risk per Trade | Max 3 Positions per Sector",
            "metrics": "Net Return +184.18% | Win Rate 44.4% | Profit Factor 2.09x | Max DD -20.23%"
        },
        "strategy3": {
            "title": "🥇 Strategy #3: Hybrid Optimal Swing (Curated Champions)",
            "universe": "Top 50 / Top 101 Curated Champions Pool",
            "trigger": "Multi-factor Momentum Spike & RSI Relative Strength Confirmation",
            "exit": "50% Lock at Target 1 (+2.0x ATR), 50% Runner trailing 20-EMA",
            "risk": "6.0% Position Allocation | Max 3 per Industry",
            "metrics": "Net Return +148.22% | Win Rate 59.2% | Profit Factor 2.39x | Max DD -11.33%"
        },
        "strategy_etf": {
            "title": "📊 ETF Strategy #1: Systematic Liquid ETF Swing",
            "universe": "20 Most Liquid Indian Index, Sectoral & Commodity ETFs",
            "trigger": "Mean Reversion / Momentum Breakout (>1.15x Vol SMA)",
            "exit": "50% Lock at T1 (+2.0x ATR), 50% Runner trailing 20-EMA",
            "risk": "1.5% Risk per Trade | 0% STT Buy + Zero DP Charges",
            "metrics": "Net Return +144.38% | Win Rate 71.1% | Profit Factor 3.71x | Max DD -14.90%"
        },
        "master": {
            "title": "🏆 Master Multi-System Unified Hub (4 Strategy Engines)",
            "universe": "Nifty 50 Equities, Curated Champions Pool & 20 Liquid ETFs",
            "trigger": "Concurrent Multi-Agent Scanners & Telegram Signal Dispatchers",
            "exit": "Multi-Strategy Trailing EMA & Volatility ATR Stop Sentinel",
            "risk": "Statutory Tax Sentinel & Autonomous Fee Budgeting Active",
            "metrics": "Combined Portfolio Net Take-Home > 150%+ Net Alpha over Nifty 50"
        }
    }

    curr_spec = specs.get(strategy_key, specs["master"])

    with st.expander(f"⚡ Strategy Specs & Market Sentiment Alignment ({badge} Regime: {regime})", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📌 Strategy Core Specifications")
            st.markdown(f"**Strategy Name**: {curr_spec['title']}")
            st.markdown(f"• 🎯 **Target Universe**: {curr_spec['universe']}")
            st.markdown(f"• ⚡ **Entry Trigger**: {curr_spec['trigger']}")
            st.markdown(f"• 🛑 **Exit & Stop Rule**: {curr_spec['exit']}")
            st.markdown(f"• 🛡️ **Risk Sizing**: {curr_spec['risk']}")
            st.markdown(f"• 📊 **Historical Benchmark**: `{curr_spec['metrics']}`")

        with col2:
            st.subheader("🌐 Market Macro Sentiment & Alignment")
            
            if eff_color == "success":
                st.success(f"**{eff_title}**\n\n{eff_desc}")
            elif eff_color == "error":
                st.error(f"**{eff_title}**\n\n{eff_desc}")
            else:
                st.warning(f"**{eff_title}**\n\n{eff_desc}")

            m1, m2 = st.columns(2)
            m1.metric("🛒 New Breakouts", f"{badge} {breakout_guard}")
            m2.metric("💼 Active Holdings", f"{badge} {holdings_guard}")

            st.markdown(f"**🌍 Global Cues ({global_sent})**: {global_sum or 'Analyzing international markets...'}")
            st.markdown(f"**🇮🇳 Indian Domestic Cues ({domestic_sent})**: {domestic_sum or 'Analyzing domestic news flow...'}")
            
            if drivers:
                st.markdown("**🔑 Key Market Drivers & Catalysts:**")
                for d in drivers[:3]:
                    st.markdown(f"• {d}")


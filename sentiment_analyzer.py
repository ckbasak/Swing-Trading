import os
import requests
import xml.etree.ElementTree as ET
import google.generativeai as genai
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

# Initialize Gemini API
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def fetch_news_articles(query: str, limit: int = 5) -> List[Dict[str, str]]:
    """
    Scrapes the Google News RSS feed for recent financial articles matching the query.
    Returns a list of dicts with title, source, pub_date, and link.
    """
    formatted_query = query.replace(" ", "+")
    rss_url = f"https://news.google.com/rss/search?q={formatted_query}&hl=en-IN&gl=IN&ceid=IN:en"
    
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

def fetch_news_headlines(query: str) -> List[str]:
    """
    Scrapes Google News RSS for the top headlines (string list for backward compatibility).
    """
    articles = fetch_news_articles(query, limit=5)
    return [a["title"] for a in articles]

def analyze_headlines_polarity(headlines: List[str]) -> str:
    """Fast, local keyword polarity engine as fallback or fast path."""
    positive_words = {
        "surge", "surges", "surged", "rally", "rallies", "gain", "gains", "jump", "jumps", 
        "profit", "growth", "high", "record", "beat", "beats", "bull", "bullish", "up", 
        "rise", "rises", "strong", "outperform", "partnership", "expansion", "dividend"
    }
    negative_words = {
        "fall", "falls", "fell", "drop", "drops", "plunge", "plunges", "slump", "slumps", 
        "loss", "losses", "crash", "crashes", "down", "low", "weak", "bear", "bearish", 
        "decline", "declines", "fraud", "probe", "selloff", "penalty", "default", "scam"
    }
    pos_score = 0
    neg_score = 0
    for h in headlines:
        words = set(h.lower().replace("-", " ").replace(".", " ").replace(",", " ").split())
        pos_score += len(words.intersection(positive_words))
        neg_score += len(words.intersection(negative_words))
    if neg_score > pos_score and neg_score >= 2:
        return "NEGATIVE"
    elif pos_score > neg_score and pos_score >= 2:
        return "POSITIVE"
    return "NEUTRAL"

def get_news_sentiment(query: str) -> str:
    """
    Scrapes recent headlines and determines sentiment with sub-second execution.
    Used for screening/filtering breakout candidates.
    Returns: 'POSITIVE', 'NEUTRAL', or 'NEGATIVE'
    """
    headlines = fetch_news_headlines(query)
    if not headlines:
        logger.info(f"No news headlines found for: {query}. Defaulted sentiment to NEUTRAL.")
        return "NEUTRAL"
        
    if api_key:
        prompt = (
            f"Analyze these news headlines related to '{query}' and return single word: POSITIVE, NEUTRAL, or NEGATIVE.\n"
            + "\n".join(f"- {h}" for h in headlines)
        )
        try:
            model = genai.GenerativeModel("gemini-3.6-flash")
            response = model.generate_content(prompt, request_options={"timeout": 3.5})
            sentiment = response.text.strip().upper()
            for val in ["POSITIVE", "NEUTRAL", "NEGATIVE"]:
                if val in sentiment:
                    logger.info(f"Gemini classified sentiment for '{query}' as: {val}")
                    return val
        except Exception as e:
            logger.debug(f"Gemini sentiment fallback for {query}: {e}")
            pass # Fallback instantly to local NLP engine
            
    sentiment = analyze_headlines_polarity(headlines)
    logger.info(f"Headline polarity sentiment for '{query}': {sentiment}")
    return sentiment

def get_detailed_news_sentiment(query: str, ticker: str = "") -> Dict[str, Any]:
    """
    Performs an in-depth AI news sentiment evaluation using Gemini 3.6-flash.
    Returns a comprehensive structured dictionary with verdict, confidence,
    executive summary, key drivers, swing trading outlook, and raw articles.
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

    if api_key:
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

        try:
            model = genai.GenerativeModel("gemini-3.6-flash")
            response = model.generate_content(prompt, request_options={"timeout": 12.0})
            raw_text = response.text.strip()
            
            # Parse structured response
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
        except Exception as e:
            logger.warning(f"Gemini detailed analysis failed for {query}: {e}. Using local NLP engine.")

    # Fallback to local keyword polarity analysis
    polarity = analyze_headlines_polarity([a["title"] for a in articles])
    summary = f"Analyzed {len(articles)} recent headlines via local NLP engine. News flow exhibits an overall {polarity.lower()} tone."
    drivers = [a["title"] for a in articles[:3]]
    outlook = "Review price action, support/resistance levels, and follow strict stop-loss rules."

    return {
        "query": query,
        "ticker": ticker,
        "verdict": polarity,
        "confidence": "Medium" if len(articles) >= 3 else "Low",
        "summary": summary,
        "key_drivers": drivers,
        "swing_outlook": outlook,
        "articles": articles
    }

def format_detailed_sentiment_report(data: Dict[str, Any]) -> str:
    """
    Formats the detailed sentiment dictionary into an elegant Telegram Markdown message.
    """
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
    lines.append("📰 **AI News Sentiment Analysis**")
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


import os
import requests
import xml.etree.ElementTree as ET
import google.generativeai as genai
import logging

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

def fetch_news_headlines(query: str) -> list:
    """
    Scrapes the Google News RSS feed for the top 5 recent financial headlines for a query.
    """
    # Clean the query (url encode spaces as +)
    formatted_query = query.replace(" ", "+")
    # Search India financial news specifically
    rss_url = f"https://news.google.com/rss/search?q={formatted_query}&hl=en-IN&gl=IN&ceid=IN:en"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    
    try:
        r = requests.get(rss_url, headers=headers, timeout=10)
        if r.status_code != 200:
            logger.warning(f"Google News RSS returned status code {r.status_code} for: {query}")
            return []
            
        root = ET.fromstring(r.content)
        headlines = []
        
        # Look for <item> elements and extract their <title>
        items = root.findall(".//item")
        for item in items[:5]: # Top 5 headlines
            title = item.find("title")
            if title is not None and title.text:
                # Strip source suffix (e.g. " - Moneycontrol")
                headline = title.text
                if " - " in headline:
                    headline = headline.rsplit(" - ", 1)[0]
                headlines.append(headline.strip())
                
        return headlines
    except Exception as e:
        logger.error(f"Error scraping news for {query}: {e}")
        return []

def analyze_headlines_polarity(headlines: list) -> str:
    """Fast, local keyword polarity engine to prevent latency/blocking."""
    positive_words = {"surge", "surges", "surged", "rally", "rallies", "gain", "gains", "jump", "jumps", "profit", "growth", "high", "record", "beat", "beats", "bull", "bullish", "up", "rise", "rises", "strong", "outperform"}
    negative_words = {"fall", "falls", "fell", "drop", "drops", "plunge", "plunges", "slump", "slumps", "loss", "losses", "crash", "crashes", "down", "low", "weak", "bear", "bearish", "decline", "declines", "fraud", "probe", "selloff"}
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
            model = genai.GenerativeModel("gemini-2.5-flash-lite")
            response = model.generate_content(prompt, request_options={"timeout": 2.5})
            sentiment = response.text.strip().upper()
            for val in ["POSITIVE", "NEUTRAL", "NEGATIVE"]:
                if val in sentiment:
                    logger.info(f"Gemini classified sentiment for '{query}' as: {val}")
                    return val
        except Exception:
            pass # Fallback instantly to local NLP engine
            
    sentiment = analyze_headlines_polarity(headlines)
    logger.info(f"Headline polarity sentiment for '{query}': {sentiment}")
    return sentiment

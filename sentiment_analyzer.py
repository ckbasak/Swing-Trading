import os
import requests
import xml.etree.ElementTree as ET
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

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

def get_news_sentiment(query: str) -> str:
    """
    Scrapes recent headlines and uses Gemini to classify overall sentiment.
    Returns: 'POSITIVE', 'NEUTRAL', or 'NEGATIVE'
    """
    if not api_key:
        logger.warning("GEMINI_API_KEY environment variable not configured. Sentiment analysis defaulted to NEUTRAL.")
        return "NEUTRAL"
        
    headlines = fetch_news_headlines(query)
    if not headlines:
        logger.info(f"No news headlines found for: {query}. Defaulted sentiment to NEUTRAL.")
        return "NEUTRAL"
        
    prompt = (
        f"You are a professional financial analyst. Analyze the following news headlines related to '{query}' "
        "and determine the overall prevailing sentiment. \n\n"
        "Headlines:\n"
        + "\n".join(f"- {h}" for h in headlines)
        + "\n\n"
        "Classify the sentiment into exactly one of these categories: POSITIVE, NEUTRAL, or NEGATIVE.\n"
        "Return ONLY the category name as a single word in uppercase, without any formatting, quotes, or explanations."
    )
    
    try:
        model = genai.GenerativeModel("gemini-3.6-flash")
        response = model.generate_content(prompt)
        sentiment = response.text.strip().upper()
        
        if sentiment in ["POSITIVE", "NEUTRAL", "NEGATIVE"]:
            logger.info(f"Gemini classified sentiment for '{query}' as: {sentiment}")
            return sentiment
        else:
            # Fallback in case of conversational response
            for val in ["POSITIVE", "NEUTRAL", "NEGATIVE"]:
                if val in sentiment:
                    logger.info(f"Extracted sentiment '{val}' from response: {sentiment}")
                    return val
            logger.warning(f"Unexpected sentiment response: {sentiment}. Defaulted to NEUTRAL.")
            return "NEUTRAL"
    except Exception as e:
        logger.error(f"Error communicating with Gemini API: {e}")
        return "NEUTRAL"

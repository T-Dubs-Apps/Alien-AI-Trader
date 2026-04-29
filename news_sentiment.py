# news_sentiment.py — News & Sentiment Analysis for Alien AI Trader
# This module fetches recent news headlines and computes a simple sentiment score for a given symbol.
# Uses the free NewsAPI (https://newsapi.org/) or can be extended for other providers.

import os
import requests

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")

# Simple sentiment keywords (expand for more accuracy)
POSITIVE_WORDS = ["beats", "surge", "record", "growth", "profit", "upgrade", "strong", "outperform"]
NEGATIVE_WORDS = ["miss", "drop", "loss", "downgrade", "weak", "lawsuit", "recall", "scandal", "fraud"]

def fetch_news_headlines(symbol, max_headlines=10):
    if not NEWSAPI_KEY:
        return []
    url = f"https://newsapi.org/v2/everything?q={symbol}&sortBy=publishedAt&language=en&pageSize={max_headlines}&apiKey={NEWSAPI_KEY}"
    try:
        r = requests.get(url, timeout=5)
        data = r.json()
        return [a['title'] for a in data.get('articles', [])]
    except Exception:
        return []

def compute_sentiment_score(headlines):
    score = 0
    for h in headlines:
        h_lower = h.lower()
        if any(w in h_lower for w in POSITIVE_WORDS):
            score += 1
        if any(w in h_lower for w in NEGATIVE_WORDS):
            score -= 1
    return score

def get_symbol_sentiment(symbol):
    headlines = fetch_news_headlines(symbol)
    score = compute_sentiment_score(headlines)
    return {"symbol": symbol, "sentiment_score": score, "headlines": headlines}

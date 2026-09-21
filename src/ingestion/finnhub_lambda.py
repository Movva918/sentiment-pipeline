"""Finnhub ingestion Lambda — fetches ticker-tagged financial news.

Trigger: EventBridge schedule (every 15 minutes)
Rate limit: 60 calls/min on free tier
"""

import os
import logging
from datetime import datetime, timezone, timedelta

import requests

from utils import process_article

logger = logging.getLogger()
logger.setLevel(logging.INFO)

FINNHUB_API_KEY = os.environ["FINNHUB_API_KEY"]
TICKERS = os.environ["TICKERS"].split(",")  # e.g. "AAPL,MSFT,GOOGL,..."
BASE_URL = "https://finnhub.io/api/v1/company-news"


def lambda_handler(event, context):
    """Fetch recent news for each ticker from Finnhub."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    total_new = 0
    total_dupes = 0

    for ticker in TICKERS:
        logger.info(f"Fetching Finnhub news for {ticker}")

        try:
            response = requests.get(
                BASE_URL,
                params={
                    "symbol": ticker,
                    "from": yesterday,
                    "to": today,
                    "token": FINNHUB_API_KEY,
                },
                timeout=10,
            )
            response.raise_for_status()
            articles = response.json()

        except requests.RequestException as e:
            logger.error(f"Finnhub API error for {ticker}: {e}")
            continue  # Graceful degradation (FR-8): skip ticker, keep going

        for article in articles:
            headline = article.get("headline", "")
            body = article.get("summary", "")
            source_url = article.get("url", "")
            published_at = datetime.fromtimestamp(
                article.get("datetime", 0), tz=timezone.utc
            ).isoformat()

            if not headline or not source_url:
                continue

            was_new = process_article(
                source="finnhub",
                ticker=ticker,
                headline=headline,
                body=body,
                source_url=source_url,
                published_at=published_at,
            )

            if was_new:
                total_new += 1
            else:
                total_dupes += 1

    logger.info(
        f"Finnhub ingestion complete: {total_new} new, {total_dupes} duplicates"
    )

    return {
        "statusCode": 200,
        "body": {"new_articles": total_new, "duplicates": total_dupes},
    }

"""Alpha Vantage ingestion Lambda — secondary validation source.

Trigger: EventBridge schedule (every 60 minutes)
Rate limit: ~25 requests/day on free tier (strict — one ticker per invocation)
"""

import os
import logging
from datetime import datetime, timezone

import requests

from utils import process_article

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ALPHA_VANTAGE_API_KEY = os.environ["ALPHA_VANTAGE_API_KEY"]
TICKERS = os.environ["TICKERS"].split(",")
BASE_URL = "https://www.alphavantage.co/query"

# Alpha Vantage free tier is very limited (~25 req/day).
# We rotate through tickers, processing a few per invocation.
TICKERS_PER_RUN = 2


def get_ticker_index(context) -> int:
    """Use the invocation time to rotate through tickers.
    Each run picks up where the last one left off."""
    now = datetime.now(timezone.utc)
    # Simple rotation: use the hour to determine which tickers to process
    return (now.hour % (len(TICKERS) // TICKERS_PER_RUN)) * TICKERS_PER_RUN


def lambda_handler(event, context):
    """Fetch news sentiment from Alpha Vantage for a subset of tickers."""
    start_idx = get_ticker_index(context)
    run_tickers = TICKERS[start_idx:start_idx + TICKERS_PER_RUN]

    total_new = 0
    total_dupes = 0

    for ticker in run_tickers:
        logger.info(f"Fetching Alpha Vantage news for {ticker}")

        try:
            response = requests.get(
                BASE_URL,
                params={
                    "function": "NEWS_SENTIMENT",
                    "tickers": ticker,
                    "apikey": ALPHA_VANTAGE_API_KEY,
                    "limit": 10,
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

        except requests.RequestException as e:
            logger.error(f"Alpha Vantage API error for {ticker}: {e}")
            continue

        # Check for rate limit or error responses
        if "Note" in data or "Error Message" in data:
            logger.warning(
                f"Alpha Vantage limit/error: {data.get('Note', data.get('Error Message'))}"
            )
            break  # Stop processing — we've hit the rate limit

        articles = data.get("feed", [])
        logger.info(f"Got {len(articles)} articles for {ticker}")

        for article in articles:
            headline = article.get("title", "")
            body = article.get("summary", "")
            source_url = article.get("url", "")
            published_at = article.get("time_published", "")

            # Parse Alpha Vantage date format: "20260920T143000"
            if published_at:
                try:
                    dt = datetime.strptime(published_at, "%Y%m%dT%H%M%S")
                    published_at = dt.replace(tzinfo=timezone.utc).isoformat()
                except ValueError:
                    published_at = datetime.now(timezone.utc).isoformat()

            if not headline or not source_url:
                continue

            was_new = process_article(
                source="alpha_vantage",
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
        f"Alpha Vantage ingestion complete: {total_new} new, "
        f"{total_dupes} duplicates (tickers: {run_tickers})"
    )

    return {
        "statusCode": 200,
        "body": {
            "new_articles": total_new,
            "duplicates": total_dupes,
            "tickers_processed": run_tickers,
        },
    }

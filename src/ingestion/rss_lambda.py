"""Yahoo/Reuters RSS ingestion Lambda — parses RSS feeds for financial headlines.

Trigger: EventBridge schedule (every 15 minutes)
Rate limit: Unlimited (public RSS feeds)
"""

import os
import re
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from utils import process_article

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TICKERS = os.environ["TICKERS"].split(",")

# RSS feed URLs for financial news
RSS_FEEDS = [
    {
        "name": "yahoo_finance",
        "url": "https://finance.yahoo.com/news/rssindex",
    },
    {
        "name": "reuters_business",
        "url": "https://www.reutersagency.com/feed/?best-topics=business-finance",
    },
    {
        "name": "reuters_markets",
        "url": "https://www.reutersagency.com/feed/?best-topics=markets",
    },
]


def parse_rss_feed(feed_url: str, feed_name: str) -> list:
    """Parse an RSS feed and return a list of articles."""
    articles = []

    try:
        response = requests.get(feed_url, timeout=10)
        response.raise_for_status()

        root = ET.fromstring(response.content)

        # Handle both RSS 2.0 and Atom formats
        items = root.findall(".//item") or root.findall(
            ".//{http://www.w3.org/2005/Atom}entry"
        )

        for item in items:
            title = (
                item.findtext("title")
                or item.findtext("{http://www.w3.org/2005/Atom}title")
                or ""
            )
            description = (
                item.findtext("description")
                or item.findtext("{http://www.w3.org/2005/Atom}summary")
                or ""
            )
            link = (
                item.findtext("link")
                or item.findtext("{http://www.w3.org/2005/Atom}link")
                or ""
            )
            pub_date = (
                item.findtext("pubDate")
                or item.findtext("{http://www.w3.org/2005/Atom}published")
                or ""
            )

            # Strip HTML tags from description
            description = re.sub(r"<[^>]+>", "", description).strip()

            # Parse publication date
            published_at = None
            if pub_date:
                try:
                    published_at = parsedate_to_datetime(pub_date).isoformat()
                except (ValueError, TypeError):
                    published_at = datetime.now(timezone.utc).isoformat()
            else:
                published_at = datetime.now(timezone.utc).isoformat()

            if title and link:
                articles.append({
                    "headline": title,
                    "body": description,
                    "url": link,
                    "published_at": published_at,
                    "feed": feed_name,
                })

    except requests.RequestException as e:
        logger.error(f"RSS feed error for {feed_name}: {e}")
    except ET.ParseError as e:
        logger.error(f"RSS parse error for {feed_name}: {e}")

    return articles


def match_tickers(text: str, tickers: list) -> list:
    """Find which tickers are mentioned in the text.
    Uses word boundary matching to avoid false positives."""
    text_upper = text.upper()
    matched = []
    for ticker in tickers:
        # Match ticker as a whole word (e.g. "AAPL" but not "AAPLE")
        if re.search(rf"\b{re.escape(ticker)}\b", text_upper):
            matched.append(ticker)
    return matched


# Also match company names to tickers
COMPANY_NAMES = {
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "AMAZON": "AMZN",
    "NVIDIA": "NVDA",
    "TESLA": "TSLA",
    "META": "META",
    "FACEBOOK": "META",
    "JPMORGAN": "JPM",
    "JP MORGAN": "JPM",
    "EXXON": "XOM",
    "EXXONMOBIL": "XOM",
    "JOHNSON & JOHNSON": "JNJ",
    "JOHNSON AND JOHNSON": "JNJ",
}


def match_company_names(text: str) -> list:
    """Find tickers by matching company names in text."""
    text_upper = text.upper()
    matched = []
    for name, ticker in COMPANY_NAMES.items():
        if name in text_upper and ticker not in matched:
            matched.append(ticker)
    return matched


def lambda_handler(event, context):
    """Fetch articles from RSS feeds and match them to tracked tickers."""
    total_new = 0
    total_dupes = 0
    total_unmatched = 0

    for feed in RSS_FEEDS:
        logger.info(f"Fetching RSS feed: {feed['name']}")
        articles = parse_rss_feed(feed["url"], feed["name"])
        logger.info(f"Got {len(articles)} articles from {feed['name']}")

        for article in articles:
            combined_text = f"{article['headline']} {article['body']}"

            # Match by ticker symbol and company name
            matched_tickers = match_tickers(combined_text, TICKERS)
            matched_tickers += match_company_names(combined_text)
            matched_tickers = list(set(matched_tickers))  # Deduplicate

            if not matched_tickers:
                total_unmatched += 1
                continue

            # Process once per matched ticker
            for ticker in matched_tickers:
                was_new = process_article(
                    source=f"rss_{feed['name']}",
                    ticker=ticker,
                    headline=article["headline"],
                    body=article["body"],
                    source_url=article["url"],
                    published_at=article["published_at"],
                )

                if was_new:
                    total_new += 1
                else:
                    total_dupes += 1

    logger.info(
        f"RSS ingestion complete: {total_new} new, {total_dupes} duplicates, "
        f"{total_unmatched} unmatched"
    )

    return {
        "statusCode": 200,
        "body": {
            "new_articles": total_new,
            "duplicates": total_dupes,
            "unmatched": total_unmatched,
        },
    }

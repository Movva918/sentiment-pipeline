"""SEC EDGAR ingestion Lambda — fetches official filings.

Trigger: EventBridge schedule (every 30 minutes)
Rate limit: Unlimited with fair use (10 req/sec max, User-Agent required)
"""

import os
import logging
from datetime import datetime, timezone

import requests

from utils import process_article

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TICKERS = os.environ["TICKERS"].split(",")
USER_AGENT = os.environ.get("EDGAR_USER_AGENT", "SentimentPipeline bot@example.com")
BASE_URL = "https://efts.sec.gov/LATEST/search-index"

# Map tickers to CIK numbers (SEC's company identifier)
# These are looked up once from SEC and stored here
TICKER_TO_CIK = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "NVDA": "0001045810",
    "TSLA": "0001318605",
    "META": "0001326801",
    "JPM": "0000019617",
    "XOM": "0000034088",
    "JNJ": "0000200406",
}

# Filing types to track
FILING_TYPES = ["10-K", "10-Q", "8-K"]


def fetch_filings(ticker: str, cik: str) -> list:
    """Fetch recent filings for a company from EDGAR."""
    filings = []

    try:
        # Use EDGAR company filings endpoint
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        descriptions = recent.get("primaryDocDescription", [])

        for i in range(min(len(forms), 20)):  # Check last 20 filings
            if forms[i] in FILING_TYPES:
                accession_clean = accessions[i].replace("-", "")
                filing_url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{cik.lstrip('0')}/{accession_clean}/{accessions[i]}-index.htm"
                )

                filings.append({
                    "form_type": forms[i],
                    "filing_date": dates[i],
                    "accession": accessions[i],
                    "description": descriptions[i] if i < len(descriptions) else "",
                    "url": filing_url,
                })

    except requests.RequestException as e:
        logger.error(f"EDGAR API error for {ticker} (CIK {cik}): {e}")

    return filings


def lambda_handler(event, context):
    """Fetch recent filings for each ticker from SEC EDGAR."""
    total_new = 0
    total_dupes = 0

    for ticker in TICKERS:
        cik = TICKER_TO_CIK.get(ticker)
        if not cik:
            logger.warning(f"No CIK mapping for {ticker}, skipping")
            continue

        logger.info(f"Fetching EDGAR filings for {ticker} (CIK {cik})")
        filings = fetch_filings(ticker, cik)

        for filing in filings:
            headline = f"{ticker} {filing['form_type']}: {filing['description']}"
            body = (
                f"{ticker} filed a {filing['form_type']} with the SEC "
                f"on {filing['filing_date']}. {filing['description']}"
            )

            was_new = process_article(
                source="sec_edgar",
                ticker=ticker,
                headline=headline,
                body=body,
                source_url=filing["url"],
                published_at=datetime.strptime(
                    filing["filing_date"], "%Y-%m-%d"
                ).replace(tzinfo=timezone.utc).isoformat(),
            )

            if was_new:
                total_new += 1
            else:
                total_dupes += 1

    logger.info(
        f"EDGAR ingestion complete: {total_new} new, {total_dupes} duplicates"
    )

    return {
        "statusCode": 200,
        "body": {"new_articles": total_new, "duplicates": total_dupes},
    }

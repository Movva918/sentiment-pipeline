"""Shared utilities for ingestion Lambda functions."""

import json
import hashlib
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients once (reused across warm invocations)
s3 = boto3.client("s3")
sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")

# Environment variables are set in the Lambda configuration
import os

RAW_BUCKET = os.environ["RAW_BUCKET"]
SQS_QUEUE_URL = os.environ["SQS_QUEUE_URL"]
DEDUP_TABLE = os.environ["DEDUP_TABLE"]

dedup_table = dynamodb.Table(DEDUP_TABLE)


def generate_article_id(source: str, url: str) -> str:
    """Create a deterministic article ID from source + URL."""
    raw = f"{source}:{url}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def is_duplicate(article_id: str) -> bool:
    """Check if article already exists using DynamoDB conditional write.
    Returns True if duplicate, False if new (and marks it as seen)."""
    try:
        dedup_table.put_item(
            Item={
                "dedup_key": article_id,
                "first_seen_at": datetime.now(timezone.utc).isoformat(),
            },
            ConditionExpression="attribute_not_exists(dedup_key)",
        )
        return False  # New article
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return True  # Duplicate
        raise


def store_raw_article(source: str, ticker: str, article_id: str, article_data: dict):
    """Write raw article JSON to S3, partitioned by source/ticker/date."""
    now = datetime.now(timezone.utc)
    key = (
        f"{source}/{ticker}/{now.year}/{now.month:02d}/{now.day:02d}"
        f"/{article_id}.json"
    )
    s3.put_object(
        Bucket=RAW_BUCKET,
        Key=key,
        Body=json.dumps(article_data, default=str),
        ContentType="application/json",
    )
    logger.info(f"Stored article {article_id} to s3://{RAW_BUCKET}/{key}")


def send_to_scoring(article_id: str, ticker: str, headline: str, body: str,
                    source: str, source_url: str, published_at: str):
    """Push article to SQS for sentiment scoring."""
    # Truncate body to roughly 512 tokens (~2000 chars) for FinBERT
    truncated_body = body[:2000] if body else headline

    message = {
        "article_id": article_id,
        "ticker": ticker,
        "headline": headline,
        "body": truncated_body,
        "source": source,
        "source_url": source_url,
        "published_at": published_at,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }

    sqs.send_message(
        QueueUrl=SQS_QUEUE_URL,
        MessageBody=json.dumps(message, default=str),
    )
    logger.info(f"Sent article {article_id} ({ticker}) to scoring queue")


def process_article(source: str, ticker: str, headline: str, body: str,
                    source_url: str, published_at: str):
    """Full ingestion flow for one article: dedup → S3 → SQS."""
    article_id = generate_article_id(source, source_url)

    if is_duplicate(article_id):
        logger.info(f"Skipping duplicate: {article_id} ({headline[:60]})")
        return False

    article_data = {
        "article_id": article_id,
        "ticker": ticker,
        "headline": headline,
        "body": body,
        "source": source,
        "source_url": source_url,
        "published_at": published_at,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }

    store_raw_article(source, ticker, article_id, article_data)
    send_to_scoring(article_id, ticker, headline, body, source, source_url, published_at)

    logger.info(f"Ingested new article: {article_id} ({headline[:60]})")
    return True

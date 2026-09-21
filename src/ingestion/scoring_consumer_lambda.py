"""Scoring consumer Lambda — pulls articles from SQS, scores via FinBERT,
stores results in DynamoDB + S3, and checks alert thresholds.

Trigger: SQS (scoring queue)
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")
s3 = boto3.client("s3")

# Environment variables
SCORES_TABLE = os.environ["SCORES_TABLE"]
RAW_BUCKET = os.environ["RAW_BUCKET"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
FINBERT_URL = os.environ["FINBERT_URL"]
ALERT_THRESHOLD = float(os.environ.get("ALERT_THRESHOLD", "0.7"))
COOLDOWN_MINUTES = int(os.environ.get("COOLDOWN_MINUTES", "30"))

scores_table = dynamodb.Table(SCORES_TABLE)

# Track last alert time per ticker (in-memory, resets on cold start)
last_alert = {}


def score_article(text: str) -> dict:
    """Call FinBERT Cloud Run endpoint to score text."""
    try:
        response = requests.post(
            f"{FINBERT_URL}/score",
            json={"text": text},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"FinBERT scoring error: {e}")
        return None


def store_score(article: dict, score_result: dict):
    """Write sentiment score to DynamoDB and S3 (for Athena)."""
    scored_at = datetime.now(timezone.utc).isoformat()

    # DynamoDB write
    scores_table.put_item(
        Item={
            "ticker": article["ticker"],
            "published_at": article["published_at"],
            "article_id": article["article_id"],
            "headline": article["headline"],
            "source": article["source"],
            "source_url": article["source_url"],
            "sentiment": score_result["label"],
            "confidence": Decimal(str(score_result["confidence"])),
            "prob_positive": Decimal(str(score_result["probabilities"]["positive"])),
            "prob_negative": Decimal(str(score_result["probabilities"]["negative"])),
            "prob_neutral": Decimal(str(score_result["probabilities"]["neutral"])),
            "low_confidence": score_result["low_confidence"],
            "scored_at": scored_at,
        }
    )

    # S3 write (partitioned for Athena: scores/ticker=X/date=YYYY-MM-DD/)
    try:
        pub_date = article["published_at"][:10]  # YYYY-MM-DD
        s3_key = (
            f"scores/ticker={article['ticker']}/date={pub_date}/"
            f"{article['article_id']}.json"
        )

        score_record = {
            "ticker": article["ticker"],
            "published_at": article["published_at"],
            "article_id": article["article_id"],
            "headline": article["headline"],
            "source": article["source"],
            "source_url": article["source_url"],
            "sentiment": score_result["label"],
            "confidence": score_result["confidence"],
            "prob_positive": score_result["probabilities"]["positive"],
            "prob_negative": score_result["probabilities"]["negative"],
            "prob_neutral": score_result["probabilities"]["neutral"],
            "low_confidence": score_result["low_confidence"],
            "scored_at": scored_at,
        }

        s3.put_object(
            Bucket=RAW_BUCKET,
            Key=s3_key,
            Body=json.dumps(score_record),
            ContentType="application/json",
        )
        logger.info(f"Stored score to S3: {s3_key}")

    except Exception as e:
        # Don't fail the whole scoring if S3 write fails
        logger.error(f"S3 score write failed (non-fatal): {e}")


def check_alert_threshold(ticker: str):
    """Check if ticker's recent sentiment crosses alert threshold.
    Uses weighted average of last 10 articles. Sends SNS alert with cooldown."""
    # Query last 10 scores for this ticker
    response = scores_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("ticker").eq(ticker),
        ScanIndexForward=False,  # newest first
        Limit=10,
    )

    items = response.get("Items", [])
    if len(items) < 3:
        return  # Not enough data to alert

    # Calculate weighted average (more recent = higher weight)
    total_weight = 0
    weighted_sum = 0
    for i, item in enumerate(items):
        weight = len(items) - i  # Newest gets highest weight
        sentiment_val = float(item.get("prob_negative", 0))
        weighted_sum += sentiment_val * weight
        total_weight += weight

    avg_negative = weighted_sum / total_weight if total_weight > 0 else 0

    if avg_negative >= ALERT_THRESHOLD:
        # Check cooldown
        now = datetime.now(timezone.utc)
        last = last_alert.get(ticker)
        if last and (now - last) < timedelta(minutes=COOLDOWN_MINUTES):
            logger.info(f"Alert cooldown active for {ticker}, skipping")
            return

        # Send alert
        message = (
            f"SENTIMENT ALERT: {ticker}\n"
            f"Weighted negative sentiment: {avg_negative:.2%}\n"
            f"Threshold: {ALERT_THRESHOLD:.0%}\n"
            f"Based on last {len(items)} articles\n\n"
            f"Most recent headlines:\n"
        )
        for item in items[:5]:
            message += f"  - [{item.get('sentiment')}] {item.get('headline', 'N/A')}\n"

        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=f"Sentiment Alert: {ticker} ({avg_negative:.0%} negative)",
                Message=message,
            )
            last_alert[ticker] = now
            logger.info(f"Alert sent for {ticker}: {avg_negative:.2%} negative")
        except Exception as e:
            logger.error(f"Failed to send alert for {ticker}: {e}")


def lambda_handler(event, context):
    """Process SQS messages: score each article and store results."""
    records = event.get("Records", [])
    scored = 0
    failed = 0

    for record in records:
        try:
            article = json.loads(record["body"])
            logger.info(
                f"Scoring: {article.get('article_id')} "
                f"({article.get('ticker')}) - {article.get('headline', '')[:60]}"
            )

            # Use body for scoring, fall back to headline
            text = article.get("body") or article.get("headline", "")
            if not text:
                logger.warning(f"Empty text for {article.get('article_id')}, skipping")
                failed += 1
                continue

            # Score via FinBERT
            score_result = score_article(text)
            if not score_result:
                failed += 1
                continue

            # Store in DynamoDB + S3
            store_score(article, score_result)

            # Check alert threshold
            check_alert_threshold(article["ticker"])

            scored += 1
            logger.info(
                f"Scored {article['article_id']}: "
                f"{score_result['label']} ({score_result['confidence']})"
            )

        except Exception as e:
            logger.error(f"Error processing record: {e}")
            failed += 1

    logger.info(f"Scoring complete: {scored} scored, {failed} failed")

    return {
        "statusCode": 200,
        "body": {"scored": scored, "failed": failed},
    }

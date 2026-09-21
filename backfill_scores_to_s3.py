"""
Backfill script: copies all existing scores from DynamoDB to S3
so Athena has the full historical dataset.

Run once: python3 backfill_scores_to_s3.py
"""

import boto3
import json

SCORES_TABLE = "sentiment-pipeline-scores"
BUCKET = "sentiment-pipeline-raw-articles"
REGION = "us-east-1"

dynamodb = boto3.resource("dynamodb", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
table = dynamodb.Table(SCORES_TABLE)

def backfill():
    written = 0
    skipped = 0
    last_key = None

    while True:
        scan_params = {}
        if last_key:
            scan_params["ExclusiveStartKey"] = last_key

        result = table.scan(**scan_params)
        items = result.get("Items", [])

        for item in items:
            try:
                pub_date = item.get("published_at", "")[:10]
                ticker = item.get("ticker", "UNKNOWN")
                article_id = item.get("article_id", "unknown")

                if not pub_date or not ticker:
                    skipped += 1
                    continue

                s3_key = f"scores/ticker={ticker}/date={pub_date}/{article_id}.json"

                # Convert Decimals to floats for JSON
                record = {
                    "ticker": ticker,
                    "published_at": item.get("published_at", ""),
                    "article_id": article_id,
                    "headline": item.get("headline", ""),
                    "source": item.get("source", ""),
                    "source_url": item.get("source_url", ""),
                    "sentiment": item.get("sentiment", ""),
                    "confidence": float(item.get("confidence", 0)),
                    "prob_positive": float(item.get("prob_positive", 0)),
                    "prob_negative": float(item.get("prob_negative", 0)),
                    "prob_neutral": float(item.get("prob_neutral", 0)),
                    "low_confidence": item.get("low_confidence", False),
                    "scored_at": item.get("scored_at", ""),
                }

                s3.put_object(
                    Bucket=BUCKET,
                    Key=s3_key,
                    Body=json.dumps(record),
                    ContentType="application/json",
                )
                written += 1

                if written % 50 == 0:
                    print(f"  Written {written} records...")

            except Exception as e:
                print(f"  Error on {item.get('article_id')}: {e}")
                skipped += 1

        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break

    print(f"\nBackfill complete: {written} written, {skipped} skipped")


if __name__ == "__main__":
    print("Backfilling DynamoDB scores to S3...")
    backfill()

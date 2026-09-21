"""
Unit tests for the sentiment pipeline.
Uses moto to mock AWS services.
"""

import json
import pytest
import boto3
from moto import mock_aws
from decimal import Decimal


# ── Test API Lambda routing ─────────────────────────────

@mock_aws
def test_api_health_endpoint():
    """Health endpoint should return status without auth."""
    # Set up mock DynamoDB
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    dynamodb.create_table(
        TableName="sentiment-pipeline-scores",
        KeySchema=[
            {"AttributeName": "ticker", "KeyType": "HASH"},
            {"AttributeName": "published_at", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "ticker", "AttributeType": "S"},
            {"AttributeName": "published_at", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    import os
    os.environ["SCORES_TABLE"] = "sentiment-pipeline-scores"
    os.environ["ATHENA_DATABASE"] = "sentiment_pipeline"
    os.environ["ATHENA_OUTPUT"] = "s3://test-bucket/"
    os.environ["CLOUD_RUN_URL"] = "http://localhost:8080"

    from src.api.api_lambda import lambda_handler

    event = {"routeKey": "GET /health", "pathParameters": None}
    result = lambda_handler(event, None)

    assert result["statusCode"] in [200, 503]
    body = json.loads(result["body"])
    assert "components" in body
    assert "dynamodb" in body["components"]


@mock_aws
def test_api_unknown_route():
    """Unknown route should return 404."""
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    dynamodb.create_table(
        TableName="sentiment-pipeline-scores",
        KeySchema=[
            {"AttributeName": "ticker", "KeyType": "HASH"},
            {"AttributeName": "published_at", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "ticker", "AttributeType": "S"},
            {"AttributeName": "published_at", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    import os
    os.environ["SCORES_TABLE"] = "sentiment-pipeline-scores"

    from src.api.api_lambda import lambda_handler

    event = {"routeKey": "GET /nonexistent", "pathParameters": None}
    result = lambda_handler(event, None)

    assert result["statusCode"] == 404


@mock_aws
def test_api_invalid_ticker():
    """Invalid ticker should return 400."""
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    dynamodb.create_table(
        TableName="sentiment-pipeline-scores",
        KeySchema=[
            {"AttributeName": "ticker", "KeyType": "HASH"},
            {"AttributeName": "published_at", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "ticker", "AttributeType": "S"},
            {"AttributeName": "published_at", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    import os
    os.environ["SCORES_TABLE"] = "sentiment-pipeline-scores"

    from src.api.api_lambda import lambda_handler

    event = {
        "routeKey": "GET /sentiment/{ticker}",
        "pathParameters": {"ticker": "INVALID"},
    }
    result = lambda_handler(event, None)

    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert "Unsupported ticker" in body["error"]


@mock_aws
def test_api_ticker_with_data():
    """Valid ticker should return aggregate + articles."""
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.create_table(
        TableName="sentiment-pipeline-scores",
        KeySchema=[
            {"AttributeName": "ticker", "KeyType": "HASH"},
            {"AttributeName": "published_at", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "ticker", "AttributeType": "S"},
            {"AttributeName": "published_at", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Insert test data
    table.put_item(Item={
        "ticker": "AAPL",
        "published_at": "2026-09-21T10:00:00+00:00",
        "article_id": "test-001",
        "headline": "Apple releases new iPhone",
        "source": "test",
        "source_url": "https://example.com",
        "sentiment": "positive",
        "confidence": Decimal("0.95"),
    })

    import os
    os.environ["SCORES_TABLE"] = "sentiment-pipeline-scores"

    from src.api.api_lambda import lambda_handler

    event = {
        "routeKey": "GET /sentiment/{ticker}",
        "pathParameters": {"ticker": "AAPL"},
    }
    result = lambda_handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["ticker"] == "AAPL"
    assert body["aggregate"]["article_count"] == 1
    assert body["aggregate"]["positive_pct"] == 100.0
    assert len(body["recent_articles"]) == 1


# ── Test Utils ───────────────────────────────────────────

def test_generate_article_id():
    """Article IDs should be deterministic."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'ingestion'))
    from utils import generate_article_id

    id1 = generate_article_id("finnhub", "https://example.com/article1")
    id2 = generate_article_id("finnhub", "https://example.com/article1")
    id3 = generate_article_id("finnhub", "https://example.com/article2")

    assert id1 == id2, "Same source+URL should produce same ID"
    assert id1 != id3, "Different URLs should produce different IDs"
    assert len(id1) == 16, "Article ID should be 16 hex chars"


# ── Test Compute Aggregate ───────────────────────────────

def test_compute_aggregate_empty():
    """Empty items should return neutral aggregate."""
    import os
    os.environ.setdefault("SCORES_TABLE", "sentiment-pipeline-scores")
    os.environ.setdefault("ATHENA_DATABASE", "sentiment_pipeline")
    os.environ.setdefault("ATHENA_OUTPUT", "s3://test/")
    os.environ.setdefault("CLOUD_RUN_URL", "http://localhost:8080")

    from src.api.api_lambda import compute_aggregate

    result = compute_aggregate([])
    assert result["label"] == "neutral"
    assert result["article_count"] == 0


def test_compute_aggregate_mixed():
    """Mixed sentiment should return correct percentages."""
    import os
    os.environ.setdefault("SCORES_TABLE", "sentiment-pipeline-scores")
    os.environ.setdefault("ATHENA_DATABASE", "sentiment_pipeline")
    os.environ.setdefault("ATHENA_OUTPUT", "s3://test/")
    os.environ.setdefault("CLOUD_RUN_URL", "http://localhost:8080")

    from src.api.api_lambda import compute_aggregate

    items = [
        {"sentiment": "positive", "confidence": Decimal("0.9")},
        {"sentiment": "positive", "confidence": Decimal("0.8")},
        {"sentiment": "negative", "confidence": Decimal("0.7")},
        {"sentiment": "neutral", "confidence": Decimal("0.6")},
    ]

    result = compute_aggregate(items)
    assert result["label"] == "positive"
    assert result["article_count"] == 4
    assert result["positive_pct"] == 50.0
    assert result["negative_pct"] == 25.0
    assert result["neutral_pct"] == 25.0

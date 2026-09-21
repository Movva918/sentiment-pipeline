"""
Sentiment Pipeline API Lambda Handler
Serves 4 endpoints via API Gateway HTTP API:
  GET /sentiment/{ticker}          - aggregate + recent articles for one ticker
  GET /sentiment                   - summary for all 10 tickers
  GET /sentiment/{ticker}/history  - time-series from Athena
  GET /health                      - component status check
"""

import json
import os
import time
import boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal

# ── Clients ──────────────────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb")
athena = boto3.client("athena")
scores_table = dynamodb.Table(os.environ["SCORES_TABLE"])

TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "JPM", "XOM", "JNJ"]
ATHENA_DATABASE = os.environ.get("ATHENA_DATABASE", "sentiment_pipeline")
ATHENA_OUTPUT = os.environ.get("ATHENA_OUTPUT", "s3://sentiment-pipeline-athena-results/")
CLOUD_RUN_URL = os.environ.get("CLOUD_RUN_URL", "https://finbert-scoring-6fobbyqkta-uc.a.run.app")


# ── Helpers ──────────────────────────────────────────────────────────────────

class DecimalEncoder(json.JSONEncoder):
    """Handle DynamoDB Decimal types in JSON serialization."""
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
        },
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def get_recent_scores(ticker, limit=20):
    """Query DynamoDB for recent scores for a ticker, sorted by published_at descending."""
    result = scores_table.query(
        KeyConditionExpression=Key("ticker").eq(ticker.upper()),
        ScanIndexForward=False,  # newest first
        Limit=limit,
    )
    return result.get("Items", [])


def compute_aggregate(items):
    """Compute weighted-average sentiment from a list of score items."""
    if not items:
        return {"label": "neutral", "avg_confidence": 0, "article_count": 0,
                "positive_pct": 0, "negative_pct": 0, "neutral_pct": 0}

    total = len(items)
    pos = sum(1 for i in items if i.get("sentiment") == "positive")
    neg = sum(1 for i in items if i.get("sentiment") == "negative")
    neu = sum(1 for i in items if i.get("sentiment") == "neutral")
    avg_conf = sum(float(i.get("confidence", 0)) for i in items) / total

    # Determine dominant label
    counts = {"positive": pos, "negative": neg, "neutral": neu}
    dominant = max(counts, key=counts.get)

    return {
        "label": dominant,
        "avg_confidence": round(avg_conf, 4),
        "article_count": total,
        "positive_pct": round(pos / total * 100, 1),
        "negative_pct": round(neg / total * 100, 1),
        "neutral_pct": round(neu / total * 100, 1),
    }


# ── Endpoint handlers ────────────────────────────────────────────────────────

def handle_get_ticker(ticker):
    """GET /sentiment/{ticker} — aggregate + recent articles for one ticker."""
    ticker = ticker.upper()
    if ticker not in TICKERS:
        return response(400, {"error": f"Unsupported ticker: {ticker}. Supported: {TICKERS}"})

    items = get_recent_scores(ticker, limit=20)
    aggregate = compute_aggregate(items)

    # Slim down articles for the response
    articles = []
    for item in items:
        articles.append({
            "headline": item.get("headline", ""),
            "source": item.get("source", ""),
            "published_at": item.get("published_at", ""),
            "sentiment": item.get("sentiment", ""),
            "confidence": float(item.get("confidence", 0)),
        })

    return response(200, {
        "ticker": ticker,
        "aggregate": aggregate,
        "recent_articles": articles,
        "updated_at": int(time.time()),
    })


def handle_get_all_tickers():
    """GET /sentiment — summary for all 10 tickers."""
    summaries = []
    for ticker in TICKERS:
        items = get_recent_scores(ticker, limit=20)
        agg = compute_aggregate(items)
        summaries.append({
            "ticker": ticker,
            "aggregate": agg,
        })

    return response(200, {
        "tickers": summaries,
        "updated_at": int(time.time()),
    })


def handle_get_history(ticker):
    """GET /sentiment/{ticker}/history — daily sentiment time-series.
    Uses Athena (S3) if the Glue table has data, falls back to DynamoDB."""
    ticker = ticker.upper()
    if ticker not in TICKERS:
        return response(400, {"error": f"Unsupported ticker: {ticker}. Supported: {TICKERS}"})

    # Try Athena first
    history = _history_from_athena(ticker)
    if history is None:
        # Fallback to DynamoDB
        history = _history_from_dynamodb(ticker)

    return response(200, {
        "ticker": ticker,
        "history": history,
        "source": "athena" if history and _athena_available else "dynamodb",
    })


_athena_available = False  # set by _history_from_athena


def _history_from_athena(ticker):
    """Query Athena for daily sentiment aggregates. Returns list or None on failure."""
    global _athena_available

    query = f"""
        SELECT
            date,
            sentiment,
            COUNT(*) AS count,
            AVG(confidence) AS avg_confidence
        FROM scores
        WHERE ticker = '{ticker}'
        GROUP BY date, sentiment
        ORDER BY date DESC
    """

    try:
        execution = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": ATHENA_DATABASE},
            ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
        )
        execution_id = execution["QueryExecutionId"]

        # Poll for completion
        for _ in range(25):
            status = athena.get_query_execution(QueryExecutionId=execution_id)
            state = status["QueryExecution"]["Status"]["State"]
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            time.sleep(1)

        if state != "SUCCEEDED":
            return None

        results = athena.get_query_results(QueryExecutionId=execution_id)
        rows = results["ResultSet"]["Rows"]

        if len(rows) <= 1:
            return None  # No data in Athena yet, fall back

        # Parse and group by date
        from collections import defaultdict
        daily = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0,
                                      "total_conf": 0.0, "count": 0})

        for row in rows[1:]:
            cols = [c.get("VarCharValue", "") for c in row["Data"]]
            day = cols[0]
            sentiment = cols[1]
            count = int(cols[2]) if cols[2] else 0
            avg_conf = float(cols[3]) if cols[3] else 0

            daily[day][sentiment] += count
            daily[day]["total_conf"] += avg_conf * count
            daily[day]["count"] += count

        history = []
        for day in sorted(daily.keys(), reverse=True):
            d = daily[day]
            c = d["count"]
            history.append({
                "day": day,
                "article_count": c,
                "positive": d["positive"],
                "negative": d["negative"],
                "neutral": d["neutral"],
                "avg_confidence": round(d["total_conf"] / c, 4) if c else 0,
            })

        _athena_available = True
        return history

    except Exception:
        return None


def _history_from_dynamodb(ticker):
    """Fallback: query DynamoDB for daily sentiment aggregates."""
    from collections import defaultdict

    all_items = []
    last_key = None
    while True:
        query_params = {
            "KeyConditionExpression": Key("ticker").eq(ticker),
            "ScanIndexForward": False,
        }
        if last_key:
            query_params["ExclusiveStartKey"] = last_key
        result = scores_table.query(**query_params)
        all_items.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key or len(all_items) >= 2000:
            break

    daily = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0,
                                  "total_conf": 0.0, "count": 0})

    for item in all_items:
        pub = item.get("published_at", "")
        day = pub[:10]
        if not day:
            continue
        sentiment = item.get("sentiment", "neutral")
        conf = float(item.get("confidence", 0))
        daily[day][sentiment] += 1
        daily[day]["total_conf"] += conf
        daily[day]["count"] += 1

    history = []
    for day in sorted(daily.keys(), reverse=True):
        d = daily[day]
        c = d["count"]
        history.append({
            "day": day,
            "article_count": c,
            "positive": d["positive"],
            "negative": d["negative"],
            "neutral": d["neutral"],
            "avg_confidence": round(d["total_conf"] / c, 4) if c else 0,
        })

    return history


def handle_health():
    """GET /health — component status check."""
    components = {}

    # Check DynamoDB
    try:
        scores_table.scan(Limit=1)
        components["dynamodb"] = "healthy"
    except Exception as e:
        components["dynamodb"] = f"unhealthy: {str(e)}"

    # Check Cloud Run (FinBERT)
    try:
        import urllib.request
        req = urllib.request.Request(f"{CLOUD_RUN_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                components["finbert_cloud_run"] = "healthy"
            else:
                components["finbert_cloud_run"] = f"unhealthy: status {resp.status}"
    except Exception as e:
        components["finbert_cloud_run"] = f"unhealthy: {str(e)}"

    all_healthy = all(v == "healthy" for v in components.values())

    return response(200 if all_healthy else 503, {
        "status": "healthy" if all_healthy else "degraded",
        "components": components,
        "timestamp": int(time.time()),
    })


# ── Router ────────────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    """Route API Gateway HTTP API events to the correct handler."""
    route_key = event.get("routeKey", "")
    path_params = event.get("pathParameters") or {}

    if route_key == "GET /health":
        return handle_health()

    elif route_key == "GET /sentiment":
        return handle_get_all_tickers()

    elif route_key == "GET /sentiment/{ticker}":
        ticker = path_params.get("ticker", "")
        return handle_get_ticker(ticker)

    elif route_key == "GET /sentiment/{ticker}/history":
        ticker = path_params.get("ticker", "")
        return handle_get_history(ticker)

    else:
        return response(404, {"error": f"Not found: {route_key}"})

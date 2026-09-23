"""
Pytest configuration — fixes import paths and sets required environment variables.
"""

import os
import sys

# Add src directories to Python path so imports work without 'src.' prefix
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'api'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'ingestion'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'scoring'))

# Set required environment variables before any Lambda modules are imported
os.environ.setdefault("SCORES_TABLE", "sentiment-pipeline-scores")
os.environ.setdefault("ATHENA_DATABASE", "sentiment_pipeline")
os.environ.setdefault("ATHENA_OUTPUT", "s3://test-bucket/")
os.environ.setdefault("CLOUD_RUN_URL", "http://localhost:8080")
os.environ.setdefault("RAW_BUCKET", "test-raw-bucket")
os.environ.setdefault("SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123456789/test-queue")
os.environ.setdefault("DEDUP_TABLE", "sentiment-pipeline-dedup")
os.environ.setdefault("TICKERS", "AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,JPM,XOM,JNJ")

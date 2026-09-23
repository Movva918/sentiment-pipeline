# Financial News Sentiment Pipeline

A serverless, event-driven pipeline that ingests financial news from 4 sources, scores sentiment using FinBERT, and serves results via HTTP API Gateway and an interactive Streamlit dashboard — built across AWS and GCP on free tier.

**Builder:** Kshonija Movva

## Live Links

| Resource | URL |
|---|---|
| Dashboard | [sentiment-pipeline.streamlit.app](https://sentiment-pipeline.streamlit.app) |
| Demo Login | Email: `demo@sentiment-pipeline.com` · Password: `SentimentDemo@2026` |
| API Endpoint | `cwf1zzg2o9.execute-api.us-east-1.amazonaws.com` |

## Architecture

```
Data Sources                    AWS                                    GCP
─────────────                  ─────                                  ─────
Finnhub (2 min)  ─┐
SEC EDGAR (10 min) ┼→ Lambda → DynamoDB (dedup)
RSS Feeds (5 min)  ┤           → S3 (raw storage)
Alpha Vantage (1h)─┘           → SQS Queue
                                    │
                                    ▼
                               Lambda (scoring consumer)  ──→  Cloud Run (FinBERT)
                                    │
                                    ├→ DynamoDB (hot scores)
                                    ├→ S3 (cold scores)
                                    └→ SNS (alerts if negative > 70%)
                                    
                               API Gateway + Cognito JWT
                                    │
                                    ▼
                               Lambda (API) → DynamoDB / Athena
                                    │
                                    ▼
                               Streamlit Dashboard (Plotly charts)
```

## Key Stats

| Metric | Value |
|---|---|
| Cloud resources | ~40 (AWS + GCP) |
| Terraform-managed | ~35 |
| Lambda functions | 6 |
| Data sources | 4 |
| Articles scored | 892+ |
| API endpoints | 4 |
| CloudWatch alarms | 5 |
| Unit tests | 6 |
| Lines of Python | ~1,200 |
| Lines of Terraform | ~600 |
| Monthly cost | $0–5 |

## Tickers Tracked

AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA, META, JPM, XOM, JNJ

## Data Sources

| Source | Schedule | What It Provides |
|---|---|---|
| Finnhub | Every 2 min | Ticker-tagged financial news articles |
| SEC EDGAR | Every 10 min | 10-K, 10-Q, 8-K filings |
| Yahoo/Reuters RSS | Every 5 min | News articles (manual ticker matching) |
| Alpha Vantage | Every 60 min | News with sentiment metadata (2 tickers/run rotation) |

## Project Structure

```
sentiment-pipeline/
├── .github/workflows/       # CI/CD pipeline (GitHub Actions)
├── src/
│   ├── ingestion/           # 4 Lambda functions (one per data source)
│   ├── scoring/             # Scoring consumer Lambda + FinBERT container
│   ├── api/                 # API Lambda (4 endpoints)
│   └── dashboard/           # Streamlit dashboard
├── infra/                   # Terraform (AWS + GCP infrastructure)
├── tests/                   # Unit tests (pytest + moto)
└── backfill_scores_to_s3.py # Utility script
```

## Infrastructure

### AWS Resources (~30)

| Category | Resources | Purpose |
|---|---|---|
| Storage | 2 S3 buckets | Raw articles + Athena results |
| Data Layer | 2 DynamoDB tables | Scores + deduplication |
| Messaging | SQS queue + dead letter queue | Decouple ingestion from scoring |
| Compute | 6 Lambda functions | Ingestion, scoring, API |
| API | HTTP API Gateway + 4 routes | REST API with JWT auth |
| Auth | Cognito user pool + client | Dashboard/API authentication |
| Scheduling | 4 EventBridge rules | Trigger Lambdas per source |
| Analytics | Athena workgroup + Glue DB + table | Historical queries on S3 |
| Monitoring | CloudWatch dashboard + 5 alarms | Observability |
| Alerts | SNS topic + email subscription | Threshold alerts |

### GCP Resources (9)

| Resource | Purpose |
|---|---|
| Cloud Run service | FinBERT inference (scale to zero) |
| Artifact Registry | Docker image storage |
| Service account | Least-privilege identity |
| 3 API enablements | Cloud Run, Artifact Registry, IAM |
| 2 IAM bindings | Invoker + registry reader |

## ML Model

**ProsusAI/finbert** — BERT fine-tuned on financial text. Unlike general sentiment models, FinBERT correctly interprets domain-specific language:

- "volatile" → neutral (not negative)
- "bearish" → negative
- "aggressive growth" → positive (not negative)

| Attribute | Detail |
|---|---|
| Cold start | ~8.2 seconds |
| Warm inference | ~588ms |
| Confidence threshold | 0.3 (below = flagged) |
| Container | python:3.11-slim + FastAPI + PyTorch (CPU) |

## API Endpoints

| Endpoint | Auth | Description |
|---|---|---|
| `GET /health` | None | Component status (DynamoDB + FinBERT) |
| `GET /sentiment` | JWT | Aggregate sentiment for all 10 tickers |
| `GET /sentiment/{ticker}` | JWT | Aggregate + 20 recent articles for one ticker |
| `GET /sentiment/{ticker}/history` | JWT | Daily breakdown (Athena → DynamoDB fallback) |

## Key Design Decisions

- **Hybrid Cloud** — FinBERT on GCP Cloud Run (generous free tier, scale-to-zero). Everything else on AWS (tighter service integration).
- **Tiered Storage** — DynamoDB for fast real-time queries. S3 + Athena for cheap historical analytics.
- **SQS Decoupling** — Ingestion and scoring run independently. Dead letter queue catches persistent failures.
- **FinBERT over general models** — Domain-specific accuracy for financial text.
- **HTTP API over REST API** — 3x cheaper, native JWT support, lower latency.

## CI/CD

GitHub Actions pipeline:
- Lint (flake8) and unit tests (pytest + moto) on every push/PR
- Auto-deploy all 6 Lambda functions on merge to main
- FinBERT container only rebuilds when `src/scoring/` changes
- Post-deploy health check verification

## Monitoring

CloudWatch dashboard with 7 panels + 5 alarms:
- Scoring consumer errors > 5 in 10 min
- API errors > 10 in 10 min
- API P95 latency > 5 seconds
- DynamoDB throttling detected
- Messages appearing in dead letter queue

All alarms notify via SNS email.

## Cost

| Service | Free Tier | Usage | Cost |
|---|---|---|---|
| Lambda | 1M req/month | ~50K/month | $0 |
| DynamoDB | 25 GB + 25 WCU/RCU | < 1 GB | $0 |
| S3 | 5 GB | < 100 MB | $0 |
| SQS | 1M req/month | ~50K/month | $0 |
| API Gateway | 1M req/month | < 10K/month | $0 |
| Cloud Run | 2M req/month | < 5K/month | $0 |
| Athena | $5/TB scanned | < 10 MB/month | $0 |
| Streamlit Cloud | 1 free app | 1 app | $0 |
| **Total** | | | **$0–5/mo** |

## Setup

### Prerequisites
- AWS CLI configured with appropriate credentials
- GCP CLI (`gcloud`) authenticated
- Terraform >= 1.5.0
- Python 3.11
- Docker

### Deploy Infrastructure
```bash
cd infra
terraform init
terraform plan
terraform apply
```

### Deploy Lambdas
```bash
# Handled automatically by GitHub Actions on merge to main
# Or manually:
cd src/ingestion
zip -j finnhub.zip lambda_function.py utils.py
aws lambda update-function-code --function-name sentiment-finnhub-ingestion --zip-file fileb://finnhub.zip
```

### Deploy FinBERT Container
```bash
cd src/scoring
docker build -t finbert-scoring .
docker tag finbert-scoring us-central1-docker.pkg.dev/PROJECT_ID/sentiment-repo/finbert-scoring:latest
docker push us-central1-docker.pkg.dev/PROJECT_ID/sentiment-repo/finbert-scoring:latest
gcloud run deploy finbert-scoring --image us-central1-docker.pkg.dev/PROJECT_ID/sentiment-repo/finbert-scoring:latest --region us-central1
```

## License

This project is for portfolio/educational purposes.

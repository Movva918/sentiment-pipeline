# ============================================================
# PROVIDER
# Tells Terraform to use AWS and which region to deploy into.
# ============================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ============================================================
# S3 BUCKET — Raw article storage + Athena query source
# This is where every ingested article lands as a JSON file.
# Athena queries this bucket for historical trend analysis.
# ============================================================

resource "aws_s3_bucket" "raw_articles" {
  bucket = "${var.project_name}-raw-articles"

  tags = {
    Project = var.project_name
  }
}

# Block all public access — this data is internal only
resource "aws_s3_bucket_public_access_block" "raw_articles" {
  bucket = aws_s3_bucket.raw_articles.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Auto-delete articles older than 90 days (supports NFR-8)
resource "aws_s3_bucket_lifecycle_configuration" "raw_articles" {
  bucket = aws_s3_bucket.raw_articles.id

  rule {
    id     = "expire-old-articles"
    status = "Enabled"
    filter {}

    expiration {
      days = 90
    }
  }
}

# ============================================================
# DYNAMODB TABLE — Live sentiment scores
# Partition key = ticker, Sort key = published_at
# This is what the API reads from for current sentiment.
# On-demand billing = pay per request, free tier covers it.
# ============================================================

resource "aws_dynamodb_table" "sentiment_scores" {
  name         = "${var.project_name}-scores"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ticker"
  range_key    = "published_at"

  attribute {
    name = "ticker"
    type = "S"
  }

  attribute {
    name = "published_at"
    type = "S"
  }

  tags = {
    Project = var.project_name
  }
}

# ============================================================
# DYNAMODB TABLE — Deduplication tracking
# Used by ingestion Lambdas to detect duplicate articles.
# TTL auto-deletes entries after 24 hours so the table
# stays small and free.
# ============================================================

resource "aws_dynamodb_table" "dedup" {
  name         = "${var.project_name}-dedup"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "dedup_key"

  attribute {
    name = "dedup_key"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = {
    Project = var.project_name
  }
}

# ============================================================
# SQS QUEUE — Buffer between ingestion and scoring
# Ingestion Lambdas push articles here.
# The scoring Lambda pulls from here and calls Cloud Run.
# Dead letter queue catches articles that fail 3 times.
# ============================================================

resource "aws_sqs_queue" "scoring_dlq" {
  name = "${var.project_name}-scoring-dlq"

  # Keep failed messages for 7 days so you can inspect them
  message_retention_seconds = 604800

  tags = {
    Project = var.project_name
  }
}

resource "aws_sqs_queue" "scoring_queue" {
  name = "${var.project_name}-scoring-queue"

  # 120 seconds — enough for Cloud Run cold start + inference
  visibility_timeout_seconds = 120

  # Keep messages up to 4 days if the consumer is down
  message_retention_seconds = 345600

  # After 3 failures, move to the dead letter queue
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.scoring_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Project = var.project_name
  }
}

# ============================================================
# SNS TOPIC — Sentiment alerts (supports FR-9)
# When a ticker's sentiment crosses a threshold,
# a notification is published here and delivered via email.
# ============================================================

resource "aws_sns_topic" "sentiment_alerts" {
  name = "${var.project_name}-alerts"

  tags = {
    Project = var.project_name
  }
}

resource "aws_sns_topic_subscription" "alert_email" {
  topic_arn = aws_sns_topic.sentiment_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ============================================================
# IAM ROLE — Shared role for all Lambda functions
# Allows Lambda to: read/write DynamoDB, read/write S3,
# send/receive SQS messages, publish to SNS, write logs.
# ============================================================

resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project = var.project_name
  }
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "${var.project_name}-lambda-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDB"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:DeleteItem"
        ]
        Resource = [
          aws_dynamodb_table.sentiment_scores.arn,
          aws_dynamodb_table.dedup.arn
        ]
      },
      {
        Sid    = "S3"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.raw_articles.arn,
          "${aws_s3_bucket.raw_articles.arn}/*"
        ]
      },
      {
        Sid    = "SQS"
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = [
          aws_sqs_queue.scoring_queue.arn,
          aws_sqs_queue.scoring_dlq.arn
        ]
      },
      {
        Sid    = "SNS"
        Effect = "Allow"
        Action = "sns:Publish"
        Resource = aws_sns_topic.sentiment_alerts.arn
      },
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Sid    = "SecretsManager"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "*"
      }
    ]
  })
}

# ============================================================
# COGNITO — User authentication (supports FR-11)
# Creates a user pool (the user database) and an app client
# (the dashboard's identity to Cognito).
# ============================================================

resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-users"

  # Simple email-based signup
  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_cognito_user_pool_client" "dashboard" {
  name         = "${var.project_name}-dashboard"
  user_pool_id = aws_cognito_user_pool.main.id

  # No client secret — this is a public client (browser-based dashboard)
  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]
}

# ============================================================
# EVENTBRIDGE RULES — Scheduled triggers for ingestion Lambdas
# Each source has its own schedule based on its rate limits.
# The actual Lambda functions will be created in Build Step 5.
# For now these rules exist but have no targets.
# ============================================================

resource "aws_cloudwatch_event_rule" "finnhub_schedule" {
  name                = "${var.project_name}-finnhub-poller"
  description         = "Poll Finnhub for news every 2 minutes"
  schedule_expression = "rate(2 minutes)"

  tags = {
    Project = var.project_name
  }
}

resource "aws_cloudwatch_event_rule" "sec_edgar_schedule" {
  name                = "${var.project_name}-sec-edgar-poller"
  description         = "Poll SEC EDGAR for filings every 10 minutes"
  schedule_expression = "rate(10 minutes)"

  tags = {
    Project = var.project_name
  }
}

resource "aws_cloudwatch_event_rule" "rss_schedule" {
  name                = "${var.project_name}-rss-poller"
  description         = "Poll RSS feeds every 5 minutes"
  schedule_expression = "rate(5 minutes)"

  tags = {
    Project = var.project_name
  }
}

resource "aws_cloudwatch_event_rule" "alpha_vantage_schedule" {
  name                = "${var.project_name}-alpha-vantage-poller"
  description         = "Poll Alpha Vantage every 60 minutes (25/day limit)"
  schedule_expression = "rate(60 minutes)"

  tags = {
    Project = var.project_name
  }
}

# ============================================================
# ATHENA — Query engine for historical analysis (supports FR-10)
# Creates the Glue database and table that Athena uses to
# query raw articles in S3.
# ============================================================

resource "aws_s3_bucket" "athena_results" {
  bucket = "${var.project_name}-athena-results"

  tags = {
    Project = var.project_name
  }
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_glue_catalog_database" "sentiment" {
  name = replace(var.project_name, "-", "_")
}

resource "aws_athena_workgroup" "main" {
  name = var.project_name

  configuration {
    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.bucket}/results/"
    }

    # Cap query cost — 10MB scanned per query max
    bytes_scanned_cutoff_per_query = 10485760
  }

  tags = {
    Project = var.project_name
  }
}

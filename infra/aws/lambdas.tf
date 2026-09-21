# ──────────────────────────────────────────────
# Lambda Layer — shared dependencies (requests)
# ──────────────────────────────────────────────

resource "aws_lambda_layer_version" "ingestion_deps" {
  filename            = "${path.module}/../../build/lambda_layer.zip"
  layer_name          = "ingestion-dependencies"
  compatible_runtimes = ["python3.11"]
  source_code_hash    = filebase64sha256("${path.module}/../../build/lambda_layer.zip")
}

# ──────────────────────────────────────────────
# Shared config
# ──────────────────────────────────────────────

locals {
  tickers     = "AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,JPM,XOM,JNJ"
  common_env = {
    TICKERS       = local.tickers
    RAW_BUCKET    = aws_s3_bucket.raw_articles.id
    SQS_QUEUE_URL = aws_sqs_queue.scoring_queue.url
    DEDUP_TABLE   = aws_dynamodb_table.dedup.name
  }
}

# ──────────────────────────────────────────────
# Finnhub Lambda
# ──────────────────────────────────────────────

resource "aws_lambda_function" "finnhub_ingestion" {
  filename         = "${path.module}/../../build/finnhub_lambda.zip"
  function_name    = "sentiment-finnhub-ingestion"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 256
  source_code_hash = filebase64sha256("${path.module}/../../build/finnhub_lambda.zip")
  description      = "Ingests ticker-tagged news from Finnhub API"
  layers           = [aws_lambda_layer_version.ingestion_deps.arn]

  environment {
    variables = merge(local.common_env, {
      FINNHUB_API_KEY = var.finnhub_api_key
    })
  }
}

resource "aws_lambda_permission" "finnhub_eventbridge" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.finnhub_ingestion.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.finnhub_schedule.arn
}

resource "aws_cloudwatch_event_target" "finnhub_target" {
  rule = aws_cloudwatch_event_rule.finnhub_schedule.name
  arn  = aws_lambda_function.finnhub_ingestion.arn
}

# ──────────────────────────────────────────────
# SEC EDGAR Lambda
# ──────────────────────────────────────────────

resource "aws_lambda_function" "sec_edgar_ingestion" {
  filename         = "${path.module}/../../build/sec_edgar_lambda.zip"
  function_name    = "sentiment-sec-edgar-ingestion"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.11"
  timeout          = 90
  memory_size      = 256
  source_code_hash = filebase64sha256("${path.module}/../../build/sec_edgar_lambda.zip")
  description      = "Ingests official filings from SEC EDGAR"
  layers           = [aws_lambda_layer_version.ingestion_deps.arn]

  environment {
    variables = merge(local.common_env, {
      EDGAR_USER_AGENT = var.edgar_user_agent
    })
  }
}

resource "aws_lambda_permission" "sec_edgar_eventbridge" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sec_edgar_ingestion.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sec_edgar_schedule.arn
}

resource "aws_cloudwatch_event_target" "sec_edgar_target" {
  rule = aws_cloudwatch_event_rule.sec_edgar_schedule.name
  arn  = aws_lambda_function.sec_edgar_ingestion.arn
}

# ──────────────────────────────────────────────
# RSS Lambda
# ──────────────────────────────────────────────

resource "aws_lambda_function" "rss_ingestion" {
  filename         = "${path.module}/../../build/rss_lambda.zip"
  function_name    = "sentiment-rss-ingestion"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 256
  source_code_hash = filebase64sha256("${path.module}/../../build/rss_lambda.zip")
  description      = "Ingests financial headlines from Yahoo/Reuters RSS"
  layers           = [aws_lambda_layer_version.ingestion_deps.arn]

  environment {
    variables = local.common_env
  }
}

resource "aws_lambda_permission" "rss_eventbridge" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rss_ingestion.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.rss_schedule.arn
}

resource "aws_cloudwatch_event_target" "rss_target" {
  rule = aws_cloudwatch_event_rule.rss_schedule.name
  arn  = aws_lambda_function.rss_ingestion.arn
}

# ──────────────────────────────────────────────
# Alpha Vantage Lambda
# ──────────────────────────────────────────────

resource "aws_lambda_function" "alpha_vantage_ingestion" {
  filename         = "${path.module}/../../build/alpha_vantage_lambda.zip"
  function_name    = "sentiment-alpha-vantage-ingestion"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 256
  source_code_hash = filebase64sha256("${path.module}/../../build/alpha_vantage_lambda.zip")
  description      = "Ingests news from Alpha Vantage (validation source)"
  layers           = [aws_lambda_layer_version.ingestion_deps.arn]

  environment {
    variables = merge(local.common_env, {
      ALPHA_VANTAGE_API_KEY = var.alpha_vantage_api_key
    })
  }
}

resource "aws_lambda_permission" "alpha_vantage_eventbridge" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.alpha_vantage_ingestion.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.alpha_vantage_schedule.arn
}

resource "aws_cloudwatch_event_target" "alpha_vantage_target" {
  rule = aws_cloudwatch_event_rule.alpha_vantage_schedule.name
  arn  = aws_lambda_function.alpha_vantage_ingestion.arn
}

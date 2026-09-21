# ──────────────────────────────────────────────
# Scoring Consumer Lambda — reads SQS, calls FinBERT, stores results
# ──────────────────────────────────────────────

resource "aws_lambda_function" "scoring_consumer" {
  filename         = "${path.module}/../../build/scoring_consumer_lambda.zip"
  function_name    = "sentiment-scoring-consumer"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 256
  source_code_hash = filebase64sha256("${path.module}/../../build/scoring_consumer_lambda.zip")
  description      = "Scores articles via FinBERT and stores sentiment results"
  layers           = [aws_lambda_layer_version.ingestion_deps.arn]

  environment {
    variables = {
      SCORES_TABLE  = aws_dynamodb_table.sentiment_scores.name
      RAW_BUCKET    = aws_s3_bucket.raw_articles.id
      SNS_TOPIC_ARN = aws_sns_topic.sentiment_alerts.arn
      FINBERT_URL   = var.finbert_url
    }
  }
}

# SQS trigger — Lambda automatically pulls messages from the scoring queue
resource "aws_lambda_event_source_mapping" "sqs_to_scorer" {
  event_source_arn                   = aws_sqs_queue.scoring_queue.arn
  function_name                      = aws_lambda_function.scoring_consumer.arn
  batch_size                         = 5
  maximum_batching_window_in_seconds = 10
  enabled                            = true
}

variable "finbert_url" {
  description = "Cloud Run FinBERT endpoint URL"
  type        = string
  default     = "https://finbert-scoring-6fobbyqkta-uc.a.run.app"
}

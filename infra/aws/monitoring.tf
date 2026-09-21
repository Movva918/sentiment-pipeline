# ─────────────────────────────────────────────────────────────────────────────
# Step 9 — CloudWatch Monitoring: Dashboard + Alarms
# Place this file in infra/aws/ alongside your existing .tf files
# ─────────────────────────────────────────────────────────────────────────────

# ── Alarms ───────────────────────────────────────────────────────────────────

# Scoring consumer errors
resource "aws_cloudwatch_metric_alarm" "scoring_errors" {
  alarm_name          = "sentiment-scoring-consumer-errors"
  alarm_description   = "Scoring consumer Lambda errors exceed threshold"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = "sentiment-scoring-consumer"
  }

  alarm_actions = [aws_sns_topic.sentiment_alerts.arn]
  ok_actions    = [aws_sns_topic.sentiment_alerts.arn]
}

# API Lambda errors
resource "aws_cloudwatch_metric_alarm" "api_errors" {
  alarm_name          = "sentiment-api-errors"
  alarm_description   = "API Lambda errors exceed threshold"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = "sentiment-pipeline-api"
  }

  alarm_actions = [aws_sns_topic.sentiment_alerts.arn]
  ok_actions    = [aws_sns_topic.sentiment_alerts.arn]
}

# API latency (P95 > 5 seconds)
resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name          = "sentiment-api-high-latency"
  alarm_description   = "API P95 latency exceeds 5 seconds"
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 3
  threshold           = 5000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = "sentiment-pipeline-api"
  }

  alarm_actions = [aws_sns_topic.sentiment_alerts.arn]
}

# DynamoDB throttling
resource "aws_cloudwatch_metric_alarm" "dynamo_throttles" {
  alarm_name          = "sentiment-dynamodb-throttles"
  alarm_description   = "DynamoDB read/write throttling detected"
  namespace           = "AWS/DynamoDB"
  metric_name         = "ThrottledRequests"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = "sentiment-pipeline-scores"
  }

  alarm_actions = [aws_sns_topic.sentiment_alerts.arn]
}

# SQS dead letter queue messages
resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "sentiment-scoring-dlq-messages"
  alarm_description   = "Messages landing in scoring dead letter queue"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.scoring_dlq.name
  }

  alarm_actions = [aws_sns_topic.sentiment_alerts.arn]
}

# ── CloudWatch Dashboard ─────────────────────────────────────────────────────

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "sentiment-pipeline"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Lambda Invocations"
          region  = "us-east-1"
          view    = "timeSeries"
          stacked = false
          period  = 300
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", "sentiment-finnhub-ingestion", { label = "Finnhub" }],
            ["AWS/Lambda", "Invocations", "FunctionName", "sentiment-sec-edgar-ingestion", { label = "SEC EDGAR" }],
            ["AWS/Lambda", "Invocations", "FunctionName", "sentiment-rss-ingestion", { label = "RSS" }],
            ["AWS/Lambda", "Invocations", "FunctionName", "sentiment-alpha-vantage-ingestion", { label = "Alpha Vantage" }],
            ["AWS/Lambda", "Invocations", "FunctionName", "sentiment-scoring-consumer", { label = "Scoring" }],
            ["AWS/Lambda", "Invocations", "FunctionName", "sentiment-pipeline-api", { label = "API" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Lambda Errors"
          region  = "us-east-1"
          view    = "timeSeries"
          stacked = true
          period  = 300
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", "sentiment-finnhub-ingestion", { label = "Finnhub", color = "#d13212" }],
            ["AWS/Lambda", "Errors", "FunctionName", "sentiment-sec-edgar-ingestion", { label = "SEC EDGAR" }],
            ["AWS/Lambda", "Errors", "FunctionName", "sentiment-rss-ingestion", { label = "RSS" }],
            ["AWS/Lambda", "Errors", "FunctionName", "sentiment-alpha-vantage-ingestion", { label = "Alpha Vantage" }],
            ["AWS/Lambda", "Errors", "FunctionName", "sentiment-scoring-consumer", { label = "Scoring" }],
            ["AWS/Lambda", "Errors", "FunctionName", "sentiment-pipeline-api", { label = "API" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "Scoring Consumer Duration (ms)"
          region  = "us-east-1"
          view    = "timeSeries"
          period  = 300
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", "sentiment-scoring-consumer", { label = "Avg", stat = "Average" }],
            ["AWS/Lambda", "Duration", "FunctionName", "sentiment-scoring-consumer", { label = "P95", stat = "p95" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "API Latency (ms)"
          region  = "us-east-1"
          view    = "timeSeries"
          period  = 300
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", "sentiment-pipeline-api", { label = "Avg", stat = "Average" }],
            ["AWS/Lambda", "Duration", "FunctionName", "sentiment-pipeline-api", { label = "P95", stat = "p95" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 6
        width  = 8
        height = 6
        properties = {
          title  = "SQS Queue Depth"
          region = "us-east-1"
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", "sentiment-pipeline-scoring-queue", { label = "Scoring Queue" }],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", "sentiment-pipeline-scoring-dlq", { label = "Dead Letter Queue", color = "#d13212" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title   = "DynamoDB Read/Write Capacity"
          region  = "us-east-1"
          view    = "timeSeries"
          period  = 300
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", "sentiment-pipeline-scores", { label = "Reads" }],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", "sentiment-pipeline-scores", { label = "Writes" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          title   = "API Gateway Requests"
          region  = "us-east-1"
          view    = "timeSeries"
          period  = 300
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiId", aws_apigatewayv2_api.sentiment_api.id, { label = "Requests", stat = "Sum" }],
            ["AWS/ApiGateway", "4xx", "ApiId", aws_apigatewayv2_api.sentiment_api.id, { label = "4xx Errors", stat = "Sum", color = "#ff9900" }],
            ["AWS/ApiGateway", "5xx", "ApiId", aws_apigatewayv2_api.sentiment_api.id, { label = "5xx Errors", stat = "Sum", color = "#d13212" }],
          ]
        }
      },
    ]
  })
}

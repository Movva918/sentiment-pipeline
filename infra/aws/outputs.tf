# ============================================================
# OUTPUTS
# These values are printed after terraform apply so you can
# reference them when building the Lambda functions and dashboard.
# ============================================================

output "s3_raw_bucket" {
  description = "S3 bucket for raw article storage"
  value       = aws_s3_bucket.raw_articles.bucket
}

output "dynamodb_scores_table" {
  description = "DynamoDB table for sentiment scores"
  value       = aws_dynamodb_table.sentiment_scores.name
}

output "dynamodb_dedup_table" {
  description = "DynamoDB table for deduplication"
  value       = aws_dynamodb_table.dedup.name
}

output "sqs_scoring_queue_url" {
  description = "SQS queue URL for scoring pipeline"
  value       = aws_sqs_queue.scoring_queue.url
}

output "sns_alerts_topic_arn" {
  description = "SNS topic ARN for sentiment alerts"
  value       = aws_sns_topic.sentiment_alerts.arn
}

output "cognito_user_pool_id" {
  description = "Cognito user pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  description = "Cognito app client ID for the dashboard"
  value       = aws_cognito_user_pool_client.dashboard.id
}

output "lambda_role_arn" {
  description = "IAM role ARN for Lambda functions"
  value       = aws_iam_role.lambda_role.arn
}

output "athena_workgroup" {
  description = "Athena workgroup name"
  value       = aws_athena_workgroup.main.name
}

output "glue_database" {
  description = "Glue catalog database for Athena queries"
  value       = aws_glue_catalog_database.sentiment.name
}

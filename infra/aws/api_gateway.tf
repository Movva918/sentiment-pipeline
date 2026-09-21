# ─────────────────────────────────────────────────────────────────────────────
# Step 7 — API Layer: HTTP API Gateway + Lambda
# Place this file in infra/aws/ alongside your existing .tf files
# ─────────────────────────────────────────────────────────────────────────────

# ── Variables (add to your existing variables.tf or keep here) ───────────────

variable "cognito_user_pool_id" {
  default = "us-east-1_mzD7kQbXm"
}

variable "cognito_client_id" {
  default = "6a37hlq5pkgjmem95ldvpj3v7u"
}

# ── Package the Lambda ───────────────────────────────────────────────────────

data "archive_file" "api_lambda_zip" {
  type        = "zip"
  source_file = "../../src/api/api_lambda.py"
  output_path = "../../build/api_lambda.zip"
}

# ── Lambda Function ──────────────────────────────────────────────────────────

resource "aws_lambda_function" "api_handler" {
  function_name    = "sentiment-pipeline-api"
  role             = aws_iam_role.lambda_role.arn  # reuse existing role
  handler          = "api_lambda.lambda_handler"
  runtime          = "python3.11"
  timeout          = 29  # API Gateway has 30s max
  memory_size      = 256
  filename         = data.archive_file.api_lambda_zip.output_path
  source_code_hash = data.archive_file.api_lambda_zip.output_base64sha256

  environment {
    variables = {
      SCORES_TABLE   = aws_dynamodb_table.sentiment_scores.id
      ATHENA_DATABASE = aws_glue_catalog_database.sentiment.name
      ATHENA_OUTPUT   = "s3://${aws_s3_bucket.athena_results.id}/"
      CLOUD_RUN_URL   = "https://finbert-scoring-6fobbyqkta-uc.a.run.app"
    }
  }
}

# ── HTTP API Gateway ─────────────────────────────────────────────────────────

resource "aws_apigatewayv2_api" "sentiment_api" {
  name          = "sentiment-pipeline-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 3600
  }
}

# ── Cognito JWT Authorizer ───────────────────────────────────────────────────

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.sentiment_api.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito-jwt"

  jwt_configuration {
    audience = [var.cognito_client_id]
    issuer   = "https://cognito-idp.us-east-1.amazonaws.com/${var.cognito_user_pool_id}"
  }
}

# ── Lambda Integration ───────────────────────────────────────────────────────

resource "aws_apigatewayv2_integration" "api_lambda" {
  api_id                 = aws_apigatewayv2_api.sentiment_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api_handler.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# ── Routes ───────────────────────────────────────────────────────────────────

# Health check — no auth (useful for monitoring)
resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.sentiment_api.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
}

# All tickers — requires auth
resource "aws_apigatewayv2_route" "sentiment_all" {
  api_id             = aws_apigatewayv2_api.sentiment_api.id
  route_key          = "GET /sentiment"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

# Single ticker — requires auth
resource "aws_apigatewayv2_route" "sentiment_ticker" {
  api_id             = aws_apigatewayv2_api.sentiment_api.id
  route_key          = "GET /sentiment/{ticker}"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

# Ticker history — requires auth
resource "aws_apigatewayv2_route" "sentiment_history" {
  api_id             = aws_apigatewayv2_api.sentiment_api.id
  route_key          = "GET /sentiment/{ticker}/history"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

# ── Stage (auto-deploy) ─────────────────────────────────────────────────────

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.sentiment_api.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 10
    throttling_rate_limit  = 5
  }
}

# ── Lambda Permission (let API Gateway invoke the function) ──────────────────

resource "aws_lambda_permission" "api_gw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.sentiment_api.execution_arn}/*/*"
}

# ── IAM Policy Additions ────────────────────────────────────────────────────
# If your existing Lambda role doesn't already have Athena + Glue + S3 read,
# attach this additional policy.

resource "aws_iam_role_policy" "api_lambda_extras" {
  name = "api-lambda-athena-access"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetPartitions",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:GetBucketLocation",
          "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.athena_results.arn,
          "${aws_s3_bucket.athena_results.arn}/*",
          aws_s3_bucket.raw_articles.arn,
          "${aws_s3_bucket.raw_articles.arn}/*",
        ]
      }
    ]
  })
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "api_endpoint" {
  value       = aws_apigatewayv2_api.sentiment_api.api_endpoint
  description = "Base URL for the sentiment API"
}

output "api_id" {
  value = aws_apigatewayv2_api.sentiment_api.id
}

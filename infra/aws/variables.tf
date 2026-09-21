# ============================================================
# VARIABLES
# These are configurable inputs to the Terraform config.
# You can override them without changing the main code.
# ============================================================

variable "aws_region" {
  description = "AWS region to deploy into"
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name prefix for all resources"
  default     = "sentiment-pipeline"
}

variable "tracked_tickers" {
  description = "List of stock tickers to track"
  type        = list(string)
  default     = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "JPM", "XOM", "JNJ"]
}

variable "alert_email" {
  description = "Email address for SNS sentiment alerts"
  type        = string
}

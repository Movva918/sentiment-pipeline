variable "finnhub_api_key" {
  description = "Finnhub API key (free tier)"
  type        = string
  sensitive   = true
}

variable "alpha_vantage_api_key" {
  description = "Alpha Vantage API key (free tier)"
  type        = string
  sensitive   = true
}

variable "edgar_user_agent" {
  description = "User-Agent string for SEC EDGAR (required: name + email)"
  type        = string
  default     = "SentimentPipeline bot@example.com"
}

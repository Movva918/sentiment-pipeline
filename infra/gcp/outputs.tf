output "artifact_registry_url" {
  description = "Docker registry URL for pushing images"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.finbert.repository_id}"
}

output "cloud_run_url" {
  description = "FinBERT scoring endpoint URL"
  value       = google_cloud_run_v2_service.finbert.uri
}

output "service_account_email" {
  description = "Service account used by Cloud Run"
  value       = google_service_account.finbert_runner.email
}

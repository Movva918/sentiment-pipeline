# ──────────────────────────────────────────────
# Enable required GCP APIs
# ──────────────────────────────────────────────

resource "google_project_service" "cloud_run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifact_registry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iam" {
  service            = "iam.googleapis.com"
  disable_on_destroy = false
}

# ──────────────────────────────────────────────
# Artifact Registry — stores the FinBERT Docker image
# ──────────────────────────────────────────────

resource "google_artifact_registry_repository" "finbert" {
  location      = var.region
  repository_id = "sentiment-pipeline"
  format        = "DOCKER"
  description   = "Docker images for the sentiment scoring pipeline"

  depends_on = [google_project_service.artifact_registry]
}

# ──────────────────────────────────────────────
# Service Account — least-privilege identity for Cloud Run
# ──────────────────────────────────────────────

resource "google_service_account" "finbert_runner" {
  account_id   = "finbert-runner"
  display_name = "FinBERT Cloud Run Service Account"
  description  = "Least-privilege SA for the FinBERT scoring container"
}

# Grant only Cloud Run Invoker role (can receive requests)
resource "google_project_iam_member" "finbert_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.finbert_runner.email}"
}

# Grant Artifact Registry Reader role (can pull images)
resource "google_project_iam_member" "finbert_ar_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.finbert_runner.email}"
}

# ──────────────────────────────────────────────
# Cloud Run Service — FinBERT inference endpoint
# ──────────────────────────────────────────────
# NOTE: This uses a placeholder image. After you build and push
# your FinBERT container (Step 4), update the image field to:
#   ${var.region}-docker.pkg.dev/${var.project_id}/sentiment-pipeline/finbert:latest
# ──────────────────────────────────────────────

resource "google_cloud_run_v2_service" "finbert" {
  name     = "finbert-scoring"
  location = var.region

  template {
    service_account = google_service_account.finbert_runner.email

    # Scale to zero — no cost when idle (supports NFR-4)
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      # Placeholder — swap with your FinBERT image after Step 4
      
image = "us-central1-docker.pkg.dev/project-53a12d85-1293-4733-a2b/sentiment-pipeline/finbert-scoring:latest"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
      }
    }
  }

  depends_on = [google_project_service.cloud_run]
}

# Allow unauthenticated access from your AWS Lambda scorer
# (Your Lambda authenticates via its own IAM role; Cloud Run
#  serves as an internal endpoint called by the scoring Lambda)
resource "google_cloud_run_v2_service_iam_member" "allow_unauthenticated" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.finbert.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

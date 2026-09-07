# Deploying to GCP Cloud Run

This guide deploys the QA Command Center (Dashboard + Worker) to Google Cloud Run as two services with a shared Cloud Storage FUSE mount for reports.

## Prerequisites

- GCP project with billing enabled
- `gcloud` CLI installed and authenticated
- Docker installed locally
- Artifact Registry repository created

## 1. Set Variables

```bash
export PROJECT_ID=your-gcp-project
export REGION=us-central1
export REPO=qa-command-center
export DASHBOARD_IMAGE=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/dashboard
export WORKER_IMAGE=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/worker
```

## 2. Create Artifact Registry

```bash
gcloud artifacts repositories create ${REPO} \
  --repository-format=docker \
  --location=${REGION}
```

## 3. Build and Push Images

```bash
# Authenticate Docker
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# Build from project root
docker build -f qa_agent/dashboard/Dockerfile -t ${DASHBOARD_IMAGE}:latest .
docker build -f qa_agent/dashboard/Dockerfile.worker -t ${WORKER_IMAGE}:latest .

# Push
docker push ${DASHBOARD_IMAGE}:latest
docker push ${WORKER_IMAGE}:latest
```

## 4. Create Secrets

```bash
# Store API key in Secret Manager
echo -n "sk-ant-..." | gcloud secrets create ANTHROPIC_API_KEY --data-file=-

# Grant worker service account access
gcloud secrets add-iam-policy-binding ANTHROPIC_API_KEY \
  --member="serviceAccount:${PROJECT_ID}@appspot.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## 5. Deploy Worker (First)

```bash
gcloud run deploy qa-worker \
  --image=${WORKER_IMAGE}:latest \
  --region=${REGION} \
  --port=8081 \
  --memory=2Gi \
  --cpu=2 \
  --timeout=600 \
  --min-instances=1 \
  --max-instances=3 \
  --set-secrets="ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="DASHBOARD_URL=https://qa-dashboard-HASH-uc.a.run.app" \
  --no-allow-unauthenticated
```

> **Note:** `min-instances=1` avoids cold start delays (30-60s). Set to 0 to save costs at the expense of latency.

## 6. Deploy Dashboard

```bash
# Get worker URL
WORKER_URL=$(gcloud run services describe qa-worker --region=${REGION} --format='value(status.url)')

gcloud run deploy qa-dashboard \
  --image=${DASHBOARD_IMAGE}:latest \
  --region=${REGION} \
  --port=8080 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=5 \
  --set-env-vars="WORKER_URL=${WORKER_URL},DATA_DIR=/data" \
  --allow-unauthenticated
```

## 7. Update Worker with Dashboard URL

```bash
DASHBOARD_URL=$(gcloud run services describe qa-dashboard --region=${REGION} --format='value(status.url)')

gcloud run services update qa-worker \
  --region=${REGION} \
  --set-env-vars="DASHBOARD_URL=${DASHBOARD_URL}"
```

## 8. Shared Storage (Cloud Storage FUSE)

For persistent reports across container restarts, mount a GCS bucket:

```bash
# Create bucket
gsutil mb -l ${REGION} gs://${PROJECT_ID}-qa-reports

# Add volume mount to both services
gcloud run services update qa-dashboard \
  --region=${REGION} \
  --add-volume=name=reports,type=cloud-storage,bucket=${PROJECT_ID}-qa-reports \
  --add-volume-mount=volume=reports,mount-path=/data

gcloud run services update qa-worker \
  --region=${REGION} \
  --add-volume=name=reports,type=cloud-storage,bucket=${PROJECT_ID}-qa-reports \
  --add-volume-mount=volume=reports,mount-path=/data
```

## 9. Service-to-Service Authentication

Since the worker is not publicly accessible, the dashboard needs to authenticate:

```bash
# Grant dashboard's service account permission to invoke worker
gcloud run services add-iam-policy-binding qa-worker \
  --region=${REGION} \
  --member="serviceAccount:${PROJECT_ID}@appspot.gserviceaccount.com" \
  --role="roles/run.invoker"
```

The dashboard proxy code already uses httpx; for Cloud Run auth, set `WORKER_AUTH=gcp` and the proxy will add an identity token header automatically.

## 10. Verify

```bash
# Check dashboard
curl $(gcloud run services describe qa-dashboard --region=${REGION} --format='value(status.url)')/health

# Check worker (requires auth token)
TOKEN=$(gcloud auth print-identity-token)
curl -H "Authorization: Bearer ${TOKEN}" \
  $(gcloud run services describe qa-worker --region=${REGION} --format='value(status.url)')/health
```

## Cost Estimate

| Component | Spec | Monthly Cost (est.) |
|-----------|------|-------------------|
| Dashboard | 512MB, 1 vCPU, 0-5 instances | ~$5-15 |
| Worker | 2GB, 2 vCPU, 1 min instance | ~$30-50 |
| Artifact Registry | 2 images (~2GB) | ~$0.50 |
| Secret Manager | 1 secret | ~$0.06 |
| Cloud Storage | Reports bucket | ~$1-5 |
| **Total** | | **~$37-71/month** |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Worker cold start (30-60s) | Set `min-instances=1` |
| Worker timeout on long evals | Increase `--timeout=600` (max 3600) |
| Dashboard can't reach worker | Check service-to-service IAM binding |
| Reports not persisting | Verify Cloud Storage FUSE mount |
| API key not found | Check Secret Manager binding |

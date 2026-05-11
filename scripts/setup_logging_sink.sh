#!/usr/bin/env bash
# Setup BigQuery logging sink for agent traces and eval results
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
DATASET_NAME="${BQ_DATASET:-geap_workshop_logs}"
SINK_NAME="${SINK_NAME:-geap-agent-traces}"

echo "=== Setting up Logging Sink → BigQuery ==="
echo "Project: $PROJECT_ID"
echo "Dataset: $DATASET_NAME"

# Enable required APIs
echo "[1/3] Enabling APIs..."
gcloud services enable \
    logging.googleapis.com \
    bigquery.googleapis.com \
    --project="$PROJECT_ID"

# Create BigQuery dataset
echo "[2/3] Creating BigQuery dataset..."
bq mk --dataset \
    --project_id="$PROJECT_ID" \
    --description="GEAP Workshop agent traces and eval results" \
    "$DATASET_NAME" \
    2>/dev/null || echo "  Dataset already exists, skipping."

# Create logging sink for agent traces
echo "[3/3] Creating logging sink..."
gcloud logging sinks create "$SINK_NAME" \
    "bigquery.googleapis.com/projects/${PROJECT_ID}/datasets/${DATASET_NAME}" \
    --project="$PROJECT_ID" \
    --log-filter='resource.type="aiplatform.googleapis.com/AgentEngine"' \
    --description="Sink agent traces to BigQuery for evaluation" \
    2>/dev/null || echo "  Sink already exists, skipping."

# Grant the sink writer access to BigQuery
WRITER_IDENTITY=$(gcloud logging sinks describe "$SINK_NAME" \
    --project="$PROJECT_ID" \
    --format="value(writerIdentity)" 2>/dev/null)

if [[ -n "$WRITER_IDENTITY" ]]; then
    bq add-iam-policy-binding \
        --member="$WRITER_IDENTITY" \
        --role="roles/bigquery.dataEditor" \
        "$PROJECT_ID:$DATASET_NAME" \
        2>/dev/null || true
fi

echo ""
echo "✓ Logging sink setup complete"
echo "  Agent traces → BigQuery: ${PROJECT_ID}.${DATASET_NAME}"

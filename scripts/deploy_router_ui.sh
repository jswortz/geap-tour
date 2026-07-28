#!/usr/bin/env bash
# Deploy the GEAP Router Cost Visualizer as an A2A/A2UI service on Cloud Run and register it
# in Gemini Enterprise (pointing GE at the Cloud Run URL).
#
# GE cannot invoke A2A agents on Vertex Agent Runtime — the working GE + A2UI path is Cloud Run.
# Mirrors party-store-ge-a2ui/scripts/deploy_to_ge.sh. The app/ package is staged with the lean
# deploy/router_ui manifest so the image doesn't drag in geap-tour's full (ADK/MCP) deps.
set -euo pipefail

PROJECT_ID="${GEMINI_ENTERPRISE_PROJECT:-wortz-project-352116}"
REGION="${ROUTER_UI_REGION:-us-east1}"
SERVICE="${ROUTER_UI_SERVICE:-geap-router-cost-ui}"
PROJ_NUM="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
APP_URL="${ROUTER_UI_APP_URL:-https://${SERVICE}-${PROJ_NUM}.${REGION}.run.app}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Live routing config (real classification + real tier-model execution on Vertex).
CLASSIFIER_MODEL="${CLASSIFIER_MODEL:-gemini-3.5-flash}"
CLASSIFIER_LOCATION="${CLASSIFIER_LOCATION:-global}"
LITE_MODEL="${LITE_MODEL:-gemini-3.1-flash-lite}"
FLASH_MODEL="${FLASH_MODEL:-gemini-3.5-flash}"
PRO_MODEL="${PRO_MODEL:-gemini-2.5-pro}"
SONNET_MODEL="${SONNET_MODEL:-claude-sonnet-4-5}"
OPUS_MODEL="${OPUS_MODEL:-claude-opus-4-6}"
# GE agent to update IN PLACE (the A2A backend for the GE routing agent). Set empty to create a new one.
GEMINI_ENTERPRISE_AGENT_ID="${GEMINI_ENTERPRISE_AGENT_ID:-14432326554756478249}"

echo "=== 1. Enable APIs ==="
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com discoveryengine.googleapis.com \
  --project="$PROJECT_ID"

echo "=== 2. Stage lean app + deploy to Cloud Run (${SERVICE}) ==="
# Note: Claude tiers require Anthropic models enabled in Vertex Model Garden for $PROJECT_ID and the
# runtime service account to have roles/aiplatform.user. Pinned to one instance so in-memory per-session
# accrual (keyed by GE contextId) is stable within a chat; --timeout is generous for Opus latency.
STAGE="$(mktemp -d)"
cp -r "$REPO_ROOT/app" "$STAGE/app"
cp "$REPO_ROOT/deploy/router_ui/Procfile" "$REPO_ROOT/deploy/router_ui/requirements.txt" \
   "$REPO_ROOT/deploy/router_ui/.python-version" "$STAGE/"
gcloud run deploy "$SERVICE" \
  --source "$STAGE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --timeout=300 --cpu=2 --memory=2Gi \
  --min-instances=1 --max-instances=1 --concurrency=8 \
  --update-env-vars "APP_URL=${APP_URL},GCP_PROJECT_ID=${PROJECT_ID},CLASSIFIER_MODEL=${CLASSIFIER_MODEL},CLASSIFIER_LOCATION=${CLASSIFIER_LOCATION},LITE_MODEL=${LITE_MODEL},FLASH_MODEL=${FLASH_MODEL},PRO_MODEL=${PRO_MODEL},SONNET_MODEL=${SONNET_MODEL},OPUS_MODEL=${OPUS_MODEL}" \
  --quiet
rm -rf "$STAGE"

echo "=== 3. Register/patch the Cloud Run card as the GE routing agent ==="
# PATCHes agent $GEMINI_ENTERPRISE_AGENT_ID in place (no duplicate); creates a new one if empty.
ROUTER_UI_APP_URL="$APP_URL" GEMINI_ENTERPRISE_PROJECT="$PROJECT_ID" \
  GEMINI_ENTERPRISE_AGENT_ID="$GEMINI_ENTERPRISE_AGENT_ID" \
  uv run python "$REPO_ROOT/scripts/register_router_ui_agent.py" || {
    echo "Registration via API failed — add the agent in the GE console (see script output)."; }

echo "=== Done. Card: ${APP_URL}/a2a/app/.well-known/agent-card.json ==="

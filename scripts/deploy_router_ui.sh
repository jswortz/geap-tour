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

echo "=== 1. Enable APIs ==="
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com discoveryengine.googleapis.com \
  --project="$PROJECT_ID"

echo "=== 2. Render the branded dashboard PNG (GE canvas shows this via native Image) ==="
# GE does not render inline WebFrameSrcdoc HTML, so the canvas displays app/assets/router_cost.png.
# Re-render it so the deployed image reflects the current dashboard/cost model.
uv run --with playwright python "$REPO_ROOT/scripts/render_router_panel.py" || \
  echo "  (render skipped — keeping the committed app/assets/router_cost.png)"

echo "=== 3. Stage lean app + deploy to Cloud Run (${SERVICE}) ==="
STAGE="$(mktemp -d)"
cp -r "$REPO_ROOT/app" "$STAGE/app"
cp "$REPO_ROOT/deploy/router_ui/Procfile" "$REPO_ROOT/deploy/router_ui/requirements.txt" \
   "$REPO_ROOT/deploy/router_ui/.python-version" "$STAGE/"
gcloud run deploy "$SERVICE" \
  --source "$STAGE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --update-env-vars "APP_URL=${APP_URL}" \
  --quiet
rm -rf "$STAGE"

echo "=== 4. Register the Cloud Run card in Gemini Enterprise ==="
ROUTER_UI_APP_URL="$APP_URL" GEMINI_ENTERPRISE_PROJECT="$PROJECT_ID" \
  uv run python "$REPO_ROOT/scripts/register_router_ui_agent.py" || {
    echo "Registration via API failed — add the agent in the GE console (see script output)."; }

echo "=== Done. Card: ${APP_URL}/a2a/app/.well-known/agent-card.json ==="

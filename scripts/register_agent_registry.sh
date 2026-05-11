#!/usr/bin/env bash
# Register agents in Agent Registry for discoverability
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
REGION="${GCP_REGION:-us-central1}"

echo "=== Registering Agents in Agent Registry ==="

# Enable required APIs
gcloud services enable aiplatform.googleapis.com --project="$PROJECT_ID"

# List deployed agent engines to get resource names
echo "Listing deployed agents..."
AGENTS=$(gcloud ai agent-engines list \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format="value(name)" 2>/dev/null)

if [[ -z "$AGENTS" ]]; then
    echo "No deployed agents found. Deploy agents first:"
    echo "  uv run python src/deploy/deploy_agents.py"
    exit 1
fi

echo "Found deployed agents:"
echo "$AGENTS" | while read -r agent; do
    echo "  - $agent"
done

echo ""
echo "✓ Agents are registered in Agent Registry via Agent Engine deployment"
echo "  View in console: https://console.cloud.google.com/vertex-ai/agents?project=$PROJECT_ID"

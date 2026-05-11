#!/usr/bin/env bash
# Setup Agent Gateway — creates gateway with egress/ingress policies
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
REGION="${GCP_REGION:-us-central1}"
GATEWAY_NAME="${GATEWAY_NAME:-geap-workshop-gateway}"

echo "=== Setting up Agent Gateway ==="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Gateway: $GATEWAY_NAME"

# Enable required APIs
echo "[1/3] Enabling APIs..."
gcloud services enable \
    aiplatform.googleapis.com \
    networkservices.googleapis.com \
    --project="$PROJECT_ID"

# Create the Agent Gateway
echo "[2/3] Creating Agent Gateway..."
gcloud alpha agent-gateway gateways create "$GATEWAY_NAME" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --display-name="GEAP Workshop Gateway" \
    2>/dev/null || echo "  Gateway already exists, skipping."

# Create egress policy — allow agents to call MCP servers on Cloud Run
echo "[3/3] Creating egress/ingress policies..."

# Allow agents to reach Cloud Run services
gcloud alpha agent-gateway gateways policies create allow-cloud-run \
    --gateway="$GATEWAY_NAME" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --direction="EGRESS" \
    --allowed-destinations="*.run.app" \
    2>/dev/null || echo "  Egress policy already exists, skipping."

GATEWAY_PATH="projects/${PROJECT_ID}/locations/${REGION}/agentGateways/${GATEWAY_NAME}"
echo ""
echo "✓ Agent Gateway setup complete"
echo "  Gateway path: $GATEWAY_PATH"
echo "  Set in .env: AGENT_GATEWAY_PATH=$GATEWAY_PATH"

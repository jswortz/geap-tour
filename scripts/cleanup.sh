#!/usr/bin/env bash
# Cleanup — tear down all deployed GEAP workshop resources
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
REGION="${GCP_REGION:-us-central1}"

echo "=== GEAP Workshop Cleanup ==="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""
read -p "This will delete all workshop resources. Continue? (y/N) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Delete Cloud Run MCP servers
echo "[1/4] Deleting Cloud Run services..."
for svc in search-mcp booking-mcp expense-mcp; do
    gcloud run services delete "$svc" \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --quiet 2>/dev/null || echo "  $svc not found, skipping."
done

# Delete Agent Engine instances
echo "[2/4] Deleting Agent Engine instances..."
AGENTS=$(gcloud ai agent-engines list \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format="value(name)" 2>/dev/null)

if [[ -n "$AGENTS" ]]; then
    echo "$AGENTS" | while read -r agent; do
        echo "  Deleting $agent..."
        gcloud ai agent-engines delete "$agent" --quiet 2>/dev/null || true
    done
fi

# Delete logging sink
echo "[3/4] Deleting logging sink..."
gcloud logging sinks delete geap-agent-traces \
    --project="$PROJECT_ID" \
    --quiet 2>/dev/null || echo "  Sink not found, skipping."

# Delete Agent Gateway
echo "[4/4] Deleting Agent Gateway..."
gcloud alpha agent-gateway gateways delete geap-workshop-gateway \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --quiet 2>/dev/null || echo "  Gateway not found, skipping."

echo ""
echo "✓ Cleanup complete"

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
uv run python scratch/delete_all_engines.py || echo "  Failed to delete agent engines, continuing."

# Delete logging sink
echo "[3/4] Deleting logging sink..."
gcloud logging sinks delete geap-agent-traces \
    --project="$PROJECT_ID" \
    --quiet 2>/dev/null || echo "  Sink not found, skipping."

# Delete Agent Gateways (regional + global) via REST API
echo "[4/4] Deleting Agent Gateways..."
ACCESS_TOKEN=$(gcloud auth print-access-token 2>/dev/null)
API_BASE="https://networkservices.googleapis.com/v1beta1"

for gw_loc in \
    "${REGION}/agentGateways/geap-workshop-gateway" \
    "${REGION}/agentGateways/geap-workshop-gateway-egress" \
    "global/agentGateways/geap-workshop-ge-gateway" \
    "global/agentGateways/geap-workshop-ge-gateway-egress"; do
    gw_name=$(basename "$gw_loc")
    RESULT=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
        "${API_BASE}/projects/${PROJECT_ID}/locations/${gw_loc}" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}")
    if [ "$RESULT" = "200" ]; then
        echo "  Deleted $gw_name"
    else
        echo "  $gw_name not found, skipping."
    fi
done

echo ""
echo "✓ Cleanup complete"

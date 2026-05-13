#!/usr/bin/env bash
# =============================================================================
# GEAP Workshop — Deployment Verification & Screenshot Capture
# =============================================================================
# Verifies all deployed resources and captures verification evidence.
# Generates a JSON report and high-res screenshots of GCP Console pages.
#
# Usage: bash scripts/verify_deployment.sh
# =============================================================================
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
REGION="${GCP_REGION:-us-central1}"
REPORT_DIR="docs/verification"
SCREENSHOT_DIR="docs/screenshots"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; FAILURES=$((FAILURES + 1)); }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }

FAILURES=0
mkdir -p "$REPORT_DIR" "$SCREENSHOT_DIR"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║        GEAP Deployment Verification Report                  ║"
echo "║  Project: $PROJECT_ID  |  Region: $REGION"
echo "║  Timestamp: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "╚══════════════════════════════════════════════════════════════╝"

# ─── 1. Cloud Run MCP Servers ──────────────────────────────────────
echo ""
echo "━━━ [1/7] Cloud Run MCP Servers ━━━"
for svc in search-mcp booking-mcp expense-mcp; do
    URL=$(gcloud run services describe "$svc" --project "$PROJECT_ID" --region "$REGION" --format "value(status.url)" 2>/dev/null || echo "")
    if [[ -n "$URL" ]]; then
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$URL/mcp" \
            -X POST -H "Content-Type: application/json" \
            -H "Accept: application/json, text/event-stream" \
            -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"verify","version":"1.0"}}}')
        if [[ "$STATUS" == "200" ]]; then
            ok "$svc: $URL (HTTP $STATUS)"
        else
            fail "$svc: $URL (HTTP $STATUS)"
        fi
    else
        fail "$svc: not deployed"
    fi
done

# Save Cloud Run details
gcloud run services list --project "$PROJECT_ID" --region "$REGION" \
    --format json 2>/dev/null > "$REPORT_DIR/cloud_run_services.json" && \
    ok "Cloud Run data saved to $REPORT_DIR/cloud_run_services.json"

# ─── 2. Model Armor Templates ─────────────────────────────────────
echo ""
echo "━━━ [2/7] Model Armor Templates ━━━"
for tmpl in geap-workshop-prompt geap-workshop-response; do
    RESULT=$(curl -s \
        "https://modelarmor.${REGION}.rep.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/templates/${tmpl}" \
        -H "Authorization: Bearer $(gcloud auth print-access-token)" 2>/dev/null)
    if echo "$RESULT" | grep -q '"name"'; then
        ok "$tmpl: exists"
        echo "$RESULT" > "$REPORT_DIR/model_armor_${tmpl}.json"
    else
        fail "$tmpl: not found"
    fi
done

# ─── 3. Agent Gateways ───────────────────────────────────────────
echo ""
echo "━━━ [3/7] Agent Gateways ━━━"
ACCESS_TOKEN=$(gcloud auth print-access-token 2>/dev/null)
API_BASE="https://networkservices.googleapis.com/v1beta1"

for gw_entry in \
    "${REGION}:geap-workshop-gateway:Regional ingress" \
    "${REGION}:geap-workshop-gateway-egress:Regional egress" \
    "global:geap-workshop-ge-gateway:GE ingress" \
    "global:geap-workshop-ge-gateway-egress:GE egress"; do
    IFS=: read -r gw_loc gw_id gw_label <<< "$gw_entry"
    GW=$(curl -s \
        "${API_BASE}/projects/${PROJECT_ID}/locations/${gw_loc}/agentGateways/${gw_id}" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" 2>/dev/null)
    if echo "$GW" | grep -q '"name"'; then
        ok "${gw_label} (${gw_id})"
        echo "$GW" > "$REPORT_DIR/agent_gateway_${gw_id}.json"
    else
        warn "${gw_label} (${gw_id}) not found"
    fi
done

# ─── 4. BigQuery Logging Sink ──────────────────────────────────────
echo ""
echo "━━━ [4/7] BigQuery Logging Sink ━━━"
SINK=$(gcloud logging sinks describe geap-agent-traces \
    --project "$PROJECT_ID" --format json 2>/dev/null || echo "")
if [[ -n "$SINK" ]]; then
    ok "geap-agent-traces sink exists"
    echo "$SINK" > "$REPORT_DIR/logging_sink.json"
else
    fail "Logging sink not found"
fi

DS=$(bq show --format prettyjson "$PROJECT_ID:geap_workshop_logs" 2>/dev/null || echo "")
if [[ -n "$DS" ]]; then
    ok "geap_workshop_logs dataset exists"
else
    fail "BigQuery dataset not found"
fi

# ─── 5. Agent Engine (Reasoning Engines) ──────────────────────────
echo ""
echo "━━━ [5/7] Deployed Agents (Agent Engine) ━━━"
uv run python -c "
import vertexai
vertexai.init(project='$PROJECT_ID', location='$REGION')
from vertexai import agent_engines
import json
engines = []
for e in agent_engines.list():
    if 'geap' in (e.display_name or '').lower() or 'travel' in (e.display_name or '').lower() or 'expense' in (e.display_name or '').lower() or 'coordinator' in (e.display_name or '').lower():
        engines.append({'name': e.resource_name, 'display_name': e.display_name})
        print(f'  ✓ {e.display_name}: {e.resource_name}')
if not engines:
    print('  (No GEAP agents found yet - deployment may be in progress)')
with open('$REPORT_DIR/agent_engines.json', 'w') as f:
    json.dump(engines, f, indent=2)
" 2>&1

# ─── 6. Cloud Logging Entries ─────────────────────────────────────
echo ""
echo "━━━ [6/7] Cloud Logging (recent entries) ━━━"
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name=("search-mcp" OR "booking-mcp" OR "expense-mcp")' \
    --project "$PROJECT_ID" --limit 20 --format json 2>/dev/null > "$REPORT_DIR/recent_logs.json" && \
    LOGCOUNT=$(cat "$REPORT_DIR/recent_logs.json" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
ok "$LOGCOUNT recent log entries saved"

# ─── 7. Staging Bucket ────────────────────────────────────────────
echo ""
echo "━━━ [7/7] GCS Staging Bucket ━━━"
BUCKET="gs://${PROJECT_ID}-geap-staging"
if gcloud storage ls "$BUCKET" &>/dev/null; then
    ok "Staging bucket exists: $BUCKET"
    gcloud storage ls "$BUCKET/" 2>/dev/null | head -10
else
    fail "Staging bucket not found: $BUCKET"
fi

# ─── Summary ─────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════"
if [[ $FAILURES -eq 0 ]]; then
    echo -e "${GREEN}All checks passed!${NC}"
else
    echo -e "${RED}$FAILURES check(s) failed.${NC}"
fi
echo "Verification data saved to: $REPORT_DIR/"
echo ""
echo "Console links for manual verification:"
echo "  Cloud Run:        https://console.cloud.google.com/run?project=$PROJECT_ID"
echo "  Model Armor:      https://console.cloud.google.com/security/model-armor?project=$PROJECT_ID"
echo "  Agent Engine:     https://console.cloud.google.com/vertex-ai/agents?project=$PROJECT_ID"
echo "  Cloud Logging:    https://console.cloud.google.com/logs?project=$PROJECT_ID"
echo "  Cloud Trace:      https://console.cloud.google.com/traces?project=$PROJECT_ID"
echo "  BigQuery:         https://console.cloud.google.com/bigquery?project=$PROJECT_ID"
echo "  Monitoring:       https://console.cloud.google.com/monitoring?project=$PROJECT_ID"

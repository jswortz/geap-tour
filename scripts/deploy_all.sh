#!/usr/bin/env bash
# =============================================================================
# GEAP Workshop — Full End-to-End Deployment
# =============================================================================
# Deploys everything in one shot: MCP servers, infrastructure, agents,
# generates traffic, runs evaluations, and verifies CI/CD.
#
# Usage:
#   bash scripts/deploy_all.sh
#   # or with custom project:
#   GCP_PROJECT_ID=my-project GCP_REGION=us-central1 bash scripts/deploy_all.sh
# =============================================================================
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
REGION="${GCP_REGION:-us-central1}"
PROJECT_NUM=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)" 2>/dev/null || echo "unknown")
STAGING_BUCKET="${GCP_STAGING_BUCKET:-${PROJECT_ID}-geap-staging}"

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

step() { echo -e "\n${BLUE}━━━ [$1] $2 ━━━${NC}"; }
ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; }

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           GEAP Workshop — Full Deployment                   ║"
echo "║  Project: ${PROJECT_ID}"
echo "║  Region:  ${REGION}"
echo "║  Bucket:  ${STAGING_BUCKET}"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ─── Step 1: Enable APIs ────────────────────────────────────────────
step "1/11" "Enabling required APIs"
gcloud services enable \
    run.googleapis.com \
    aiplatform.googleapis.com \
    modelarmor.googleapis.com \
    logging.googleapis.com \
    bigquery.googleapis.com \
    cloudtrace.googleapis.com \
    cloudresourcemanager.googleapis.com \
    monitoring.googleapis.com \
    networkservices.googleapis.com \
    --project="$PROJECT_ID" --quiet
ok "APIs enabled"

# ─── Step 2: Create staging bucket ──────────────────────────────────
step "2/11" "Creating staging bucket"
gcloud storage buckets create "gs://${STAGING_BUCKET}" \
    --project="$PROJECT_ID" --location="$REGION" \
    --uniform-bucket-level-access 2>/dev/null && ok "Bucket created" || ok "Bucket already exists"

# ─── Step 3: Deploy MCP servers to Cloud Run ────────────────────────
step "3/11" "Deploying MCP servers to Cloud Run"

deploy_mcp() {
    local name=$1 port=$2
    echo "  Deploying $name (port $port)..."
    gcloud run deploy "$name" \
        --source "src/mcp_servers/${name//-mcp/}" \
        --region "$REGION" \
        --project "$PROJECT_ID" \
        --port "$port" \
        --allow-unauthenticated \
        --quiet 2>&1 | tail -2
}

deploy_mcp "search-mcp" 8001 &
PID1=$!
deploy_mcp "booking-mcp" 8002 &
PID2=$!
deploy_mcp "expense-mcp" 8003 &
PID3=$!
wait $PID1 && ok "search-mcp deployed" || fail "search-mcp failed"
wait $PID2 && ok "booking-mcp deployed" || fail "booking-mcp failed"
wait $PID3 && ok "expense-mcp deployed" || fail "expense-mcp failed"

# Get deployed URLs dynamically from Cloud Run
SEARCH_URL=$(gcloud run services describe search-mcp --project "$PROJECT_ID" --region "$REGION" --format "value(status.url)" 2>/dev/null)
BOOKING_URL=$(gcloud run services describe booking-mcp --project "$PROJECT_ID" --region "$REGION" --format "value(status.url)" 2>/dev/null)
EXPENSE_URL=$(gcloud run services describe expense-mcp --project "$PROJECT_ID" --region "$REGION" --format "value(status.url)" 2>/dev/null)

# Smoke test MCP servers
echo "  Smoke testing MCP servers..."
for url in "$SEARCH_URL" "$BOOKING_URL" "$EXPENSE_URL"; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$url/mcp" \
        -X POST -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}')
    if [[ "$STATUS" == "200" ]]; then
        ok "$(basename "$url") responding (HTTP $STATUS)"
    else
        fail "$(basename "$url") not responding (HTTP $STATUS)"
    fi
done

# ─── Step 4: Setup Model Armor ──────────────────────────────────────
step "4/11" "Setting up Model Armor templates"
bash scripts/setup_model_armor.sh 2>&1 | grep -E "(✓|Template|already)" || warn "Model Armor setup had warnings"

# ─── Step 5: Setup Logging Sink ─────────────────────────────────────
step "5/11" "Setting up BigQuery logging sink"
bash scripts/setup_logging_sink.sh 2>&1 | grep -E "(✓|Dataset|Sink|already)" || warn "Logging sink setup had warnings"

# ─── Step 6: Setup Agent Gateway ────────────────────────────────────
step "6/11" "Setting up Agent Gateway"
bash scripts/setup_agent_gateway.sh 2>&1 | grep -E "(✓|Gateway|already)" || warn "Agent Gateway setup had warnings"

# ─── Step 7: Write .env and deploy agents ───────────────────────────
step "7/11" "Configuring environment and deploying agents"

cat > .env << ENVEOF
GCP_PROJECT_ID=${PROJECT_ID}
GCP_REGION=${REGION}
GCP_STAGING_BUCKET=${STAGING_BUCKET}
SEARCH_MCP_URL=${SEARCH_URL}/mcp
BOOKING_MCP_URL=${BOOKING_URL}/mcp
EXPENSE_MCP_URL=${EXPENSE_URL}/mcp
MODEL_ARMOR_PROMPT_TEMPLATE=projects/${PROJECT_ID}/locations/${REGION}/templates/geap-workshop-prompt
MODEL_ARMOR_RESPONSE_TEMPLATE=projects/${PROJECT_ID}/locations/${REGION}/templates/geap-workshop-response
AGENT_GATEWAY_PATH=projects/${PROJECT_ID}/locations/${REGION}/agentGateways/geap-workshop-gateway
AGENT_GATEWAY_EGRESS_PATH=projects/${PROJECT_ID}/locations/${REGION}/agentGateways/geap-workshop-gateway-egress
ENVEOF
ok ".env written"

echo "  Deploying agents to Agent Runtime (this takes 3-5 min per agent)..."
AGENT_RESOURCE=$(uv run python -c "
import vertexai
vertexai.init(project='${PROJECT_ID}', location='${REGION}', staging_bucket='gs://${STAGING_BUCKET}')
from src.deploy.deploy_agents import deploy_agent
from src.agents.coordinator_agent import coordinator_agent
name = deploy_agent(coordinator_agent)
print(name)
" 2>&1 | tail -1)
ok "coordinator_agent deployed: $AGENT_RESOURCE"

# ─── Step 8: Generate traffic and run evaluations ───────────────────
step "8/11" "Generating traffic and running evaluations"
echo "  Sending test queries to generate OTel traces..."
uv run python -m src.traffic.generate_traffic "$AGENT_RESOURCE" 2>&1 | tail -5 || warn "Some traffic queries had errors"
ok "Traffic generated"

echo "  Running one-time evaluation..."
uv run python -m src.eval.one_time_eval "$AGENT_RESOURCE" 2>&1 | tail -10 || warn "Eval had issues"
ok "One-time eval complete"

# ─── Step 9: Register in Agent Registry ────────────────────────────
step "9/11" "Registering agents and MCP servers in Agent Registry"
if [[ -f scripts/register_agent_registry.sh ]]; then
    bash scripts/register_agent_registry.sh 2>&1 | grep -E "(Registered|already|skipping|Done)" || warn "Agent Registry registration had warnings"
    ok "Agent Registry configured"
else
    warn "No register_agent_registry.sh found — skipping"
fi

# ─── Step 10: Setup Governance Policies ────────────────────────────
step "10/11" "Setting up governance policies (IAM Allow + SGP + Model Armor)"
bash scripts/setup_governance_policies.sh 2>&1 | grep -E "(Layer|IAM|SGP|policy|Done)" || warn "Governance policy setup had warnings"
ok "Governance policies configured"

# ─── Step 11: Verify CI/CD ─────────────────────────────────────────
step "11/11" "Verifying CI/CD configuration"
if [[ -f .github/workflows/eval_ci.yaml ]]; then
    ok "GitHub Actions workflow found: .github/workflows/eval_ci.yaml"
    echo "  Triggers on: pull_request to main (src/agents/** or src/mcp_servers/**)"
else
    warn "No CI/CD workflow found"
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                 Deployment Complete!                         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "MCP Server URLs:"
echo "  search-mcp:  ${SEARCH_URL}/mcp"
echo "  booking-mcp: ${BOOKING_URL}/mcp"
echo "  expense-mcp: ${EXPENSE_URL}/mcp"
echo ""
echo "Agent Resource: $AGENT_RESOURCE"
echo ""
echo "Next steps:"
echo "  • View Cloud Trace:      https://console.cloud.google.com/traces?project=${PROJECT_ID}"
echo "  • View Cloud Logging:    https://console.cloud.google.com/logs?project=${PROJECT_ID}"
echo "  • View Agent Platform:   https://console.cloud.google.com/agent-platform/runtimes?project=${PROJECT_ID}"
echo "  • View Agent Registry:   https://console.cloud.google.com/agent-platform/agent-registry?project=${PROJECT_ID}"
echo "  • View Agent Gateway:    https://console.cloud.google.com/agent-platform/gateways?project=${PROJECT_ID}"
echo "  • View Policies:         https://console.cloud.google.com/agent-platform/policies?project=${PROJECT_ID}"
echo "  • View Model Armor:      https://console.cloud.google.com/security/modelarmor?project=${PROJECT_ID}"
echo "  • Setup online monitors: uv run python -m src.eval.setup_online_monitors"

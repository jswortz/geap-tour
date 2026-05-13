#!/usr/bin/env bash
# =============================================================================
# GEAP Workshop — Full End-to-End Deployment
# =============================================================================
# Deploys everything in one shot: MCP servers, infrastructure, Agent Registry,
# agents, generates traffic, runs evaluations, and verifies CI/CD.
#
# Step ordering matters:
#   1-6: Infrastructure (APIs, bucket, Cloud Run, Model Armor, logging, gateway)
#   7:   Register MCP servers in Agent Registry (must happen before agent deploy
#        because config.py requires SEARCH_MCP_SERVER etc. env vars)
#   8:   Write .env with all config and deploy agents
#   9:   Generate traffic and run evaluations
#   10:  Setup governance policies
#   11:  Verify CI/CD
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
echo "║  Project: ${PROJECT_ID} (${PROJECT_NUM})"
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
    monitoring.googleapis.com \
    --project="$PROJECT_ID" --quiet
ok "APIs enabled"

# ─── Step 2: Create staging bucket ──────────────────────────────────
step "2/11" "Creating staging bucket"
gcloud storage buckets create "gs://${STAGING_BUCKET}" \
    --project="$PROJECT_ID" --location="$REGION" \
    --uniform-bucket-level-access 2>/dev/null && ok "Bucket created" || ok "Bucket already exists"

# ─── Step 3: Deploy MCP servers to Cloud Run ────────────────────────
step "3/11" "Deploying MCP servers to Cloud Run (min-instances=1)"

deploy_mcp() {
    local name=$1 port=$2
    echo "  Deploying $name (port $port)..."
    gcloud run deploy "$name" \
        --source "src/mcp_servers/${name//-mcp/}" \
        --region "$REGION" \
        --project "$PROJECT_ID" \
        --port "$port" \
        --min-instances 1 \
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

# ─── Step 7: Register MCP servers in Agent Registry ─────────────────
# This must happen BEFORE agent deployment because config.py requires
# SEARCH_MCP_SERVER, BOOKING_MCP_SERVER, EXPENSE_MCP_SERVER env vars
# which point to Agent Registry resource names.
step "7/11" "Registering MCP servers in Agent Registry"

register_mcp_in_registry() {
    local name=$1 url=$2 toolspec=$3
    echo "  Registering $name in Agent Registry (${REGION})..."

    # Write tool spec to temp file
    echo "$toolspec" > "/tmp/${name}-toolspec.json"

    # Check if already registered
    if gcloud alpha agent-registry services describe "$name" \
        --project="$PROJECT_ID" --location="$REGION" &>/dev/null; then
        ok "$name already registered"
        return
    fi

    gcloud alpha agent-registry services create "$name" \
        --project="$PROJECT_ID" \
        --location="$REGION" \
        --display-name="$name" \
        --mcp-server-spec-type=tool-spec \
        --mcp-server-spec-content="/tmp/${name}-toolspec.json" \
        --interfaces=url="${url}",protocolBinding=JSONRPC \
        2>&1 | grep -E "(Created|error)" || true
    ok "$name registered"
}

SEARCH_TOOLSPEC='{"tools":[{"name":"search_flights","description":"Search for available flights by origin, destination, and date","inputSchema":{"type":"object","properties":{"origin":{"type":"string","description":"Origin airport code"},"destination":{"type":"string","description":"Destination airport code"},"date":{"type":"string","description":"Travel date (YYYY-MM-DD)"}},"required":["origin","destination"]},"annotations":{"readOnlyHint":true,"idempotentHint":true}},{"name":"search_hotels","description":"Search for available hotels by city and optional max price","inputSchema":{"type":"object","properties":{"city":{"type":"string","description":"City name"},"max_price":{"type":"number","description":"Maximum price per night"}},"required":["city"]},"annotations":{"readOnlyHint":true,"idempotentHint":true}}]}'

BOOKING_TOOLSPEC='{"tools":[{"name":"book_flight","description":"Book a flight for a passenger","inputSchema":{"type":"object","properties":{"flight_id":{"type":"string"},"passenger_name":{"type":"string"}},"required":["flight_id","passenger_name"]}},{"name":"book_hotel","description":"Book a hotel for a guest","inputSchema":{"type":"object","properties":{"hotel_id":{"type":"string"},"guest_name":{"type":"string"},"check_in":{"type":"string"},"check_out":{"type":"string"}},"required":["hotel_id","guest_name"]}},{"name":"cancel_booking","description":"Cancel an existing booking","inputSchema":{"type":"object","properties":{"booking_id":{"type":"string"}},"required":["booking_id"]}},{"name":"get_booking","description":"Get details of a booking by ID","inputSchema":{"type":"object","properties":{"booking_id":{"type":"string"}},"required":["booking_id"]},"annotations":{"readOnlyHint":true}},{"name":"list_bookings","description":"List all bookings for a user","inputSchema":{"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]},"annotations":{"readOnlyHint":true}}]}'

EXPENSE_TOOLSPEC='{"tools":[{"name":"check_expense_policy","description":"Check if an expense amount is within corporate policy for a category","inputSchema":{"type":"object","properties":{"category":{"type":"string"},"amount":{"type":"number"}},"required":["category","amount"]},"annotations":{"readOnlyHint":true}},{"name":"submit_expense","description":"Submit an expense report for a user","inputSchema":{"type":"object","properties":{"user_id":{"type":"string"},"category":{"type":"string"},"amount":{"type":"number"},"description":{"type":"string"}},"required":["user_id","category","amount","description"]}},{"name":"get_user_expenses","description":"Get all expenses for a user","inputSchema":{"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]},"annotations":{"readOnlyHint":true}}]}'

register_mcp_in_registry "search-mcp" "${SEARCH_URL}/mcp" "$SEARCH_TOOLSPEC"
register_mcp_in_registry "booking-mcp" "${BOOKING_URL}/mcp" "$BOOKING_TOOLSPEC"
register_mcp_in_registry "expense-mcp" "${EXPENSE_URL}/mcp" "$EXPENSE_TOOLSPEC"

# Look up the registered MCP server resource names from Agent Registry
echo "  Looking up registered MCP server resource names..."
SEARCH_MCP_SERVER=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    "https://agentregistry.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/${REGION}/mcpServers" \
    | python3 -c "import json,sys; [print(s['name']) for s in json.load(sys.stdin).get('mcpServers',[]) if s.get('displayName')=='search-mcp']" 2>/dev/null | head -1)
BOOKING_MCP_SERVER=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    "https://agentregistry.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/${REGION}/mcpServers" \
    | python3 -c "import json,sys; [print(s['name']) for s in json.load(sys.stdin).get('mcpServers',[]) if s.get('displayName')=='booking-mcp']" 2>/dev/null | head -1)
EXPENSE_MCP_SERVER=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    "https://agentregistry.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/${REGION}/mcpServers" \
    | python3 -c "import json,sys; [print(s['name']) for s in json.load(sys.stdin).get('mcpServers',[]) if s.get('displayName')=='expense-mcp']" 2>/dev/null | head -1)

ok "search-mcp:  ${SEARCH_MCP_SERVER}"
ok "booking-mcp: ${BOOKING_MCP_SERVER}"
ok "expense-mcp: ${EXPENSE_MCP_SERVER}"

# ─── Step 8: Write .env and deploy agents ───────────────────────────
step "8/11" "Configuring environment and deploying agents"

cat > .env << ENVEOF
GCP_PROJECT_ID=${PROJECT_ID}
PROJECT_NUMBER=${PROJECT_NUM}
GCP_REGION=${REGION}
GCP_STAGING_BUCKET=${STAGING_BUCKET}
SEARCH_MCP_URL=${SEARCH_URL}/mcp
BOOKING_MCP_URL=${BOOKING_URL}/mcp
EXPENSE_MCP_URL=${EXPENSE_URL}/mcp
MODEL_ARMOR_PROMPT_TEMPLATE=projects/${PROJECT_ID}/locations/${REGION}/templates/geap-workshop-prompt
MODEL_ARMOR_RESPONSE_TEMPLATE=projects/${PROJECT_ID}/locations/${REGION}/templates/geap-workshop-response
AGENT_GATEWAY_PATH=projects/${PROJECT_ID}/locations/${REGION}/agentGateways/geap-workshop-gateway
AGENT_GATEWAY_EGRESS_PATH=projects/${PROJECT_ID}/locations/${REGION}/agentGateways/geap-workshop-gateway-egress

# Agent Registry MCP server resource names (${REGION})
SEARCH_MCP_SERVER=${SEARCH_MCP_SERVER}
BOOKING_MCP_SERVER=${BOOKING_MCP_SERVER}
EXPENSE_MCP_SERVER=${EXPENSE_MCP_SERVER}

# Vertex AI SDK config
GOOGLE_CLOUD_PROJECT=${PROJECT_ID}
GOOGLE_CLOUD_LOCATION=${REGION}
GOOGLE_GENAI_USE_VERTEXAI=1
ENVEOF
ok ".env written"

# Source .env so deploy script picks up all config
set -a && source .env && set +a

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

# Extract engine ID and add to .env
AGENT_ENGINE_ID=$(echo "$AGENT_RESOURCE" | grep -oP '\d+$')
echo "" >> .env
echo "# Agent Engine IDs" >> .env
echo "AGENT_ENGINE_ID=${AGENT_ENGINE_ID}" >> .env
ok "AGENT_ENGINE_ID=${AGENT_ENGINE_ID} added to .env"

# ─── Step 9: Generate traffic and run evaluations ───────────────────
step "9/11" "Generating traffic and running evaluations"
echo "  Sending test queries to generate OTel traces..."
set -a && source .env && set +a
uv run python -m src.traffic.generate_traffic "$AGENT_RESOURCE" 2>&1 | tail -5 || warn "Some traffic queries had errors"
ok "Traffic generated"

echo "  Running local evaluation..."
uv run python -m src.eval.one_time_eval coordinator 1 2>&1 | tail -10 || warn "Eval had issues"
ok "Local eval complete"

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
echo "Agent Registry MCP Servers:"
echo "  search-mcp:  ${SEARCH_MCP_SERVER}"
echo "  booking-mcp: ${BOOKING_MCP_SERVER}"
echo "  expense-mcp: ${EXPENSE_MCP_SERVER}"
echo ""
echo "Agent Resource: $AGENT_RESOURCE"
echo "Agent Engine ID: $AGENT_ENGINE_ID"
echo ""
echo "Next steps:"
echo "  • View Cloud Trace:      https://console.cloud.google.com/traces?project=${PROJECT_ID}"
echo "  • View Cloud Logging:    https://console.cloud.google.com/logs?project=${PROJECT_ID}"
echo "  • View Agent Platform:   https://console.cloud.google.com/agent-platform/runtimes?project=${PROJECT_ID}"
echo "  • View Agent Registry:   https://console.cloud.google.com/agent-platform/agent-registry?project=${PROJECT_ID}"
echo "  • View Agent Gateway:    https://console.cloud.google.com/agent-platform/gateways?project=${PROJECT_ID}"
echo "  • View Policies:         https://console.cloud.google.com/agent-platform/policies?project=${PROJECT_ID}"
echo "  • View Model Armor:      https://console.cloud.google.com/security/modelarmor?project=${PROJECT_ID}"
echo "  • Setup online monitors: uv run python -m src.eval.setup_online_monitors ${AGENT_ENGINE_ID}"
echo "  • Setup online evals:    uv run python -m src.eval.setup_online_evaluators create"

#!/usr/bin/env bash
# Setup Agent Gateways via REST API (v1beta1)
#
# Creates four gateways:
#   Regional (Agent Runtime):
#     - geap-workshop-gateway           CLIENT_TO_AGENT  (ingress)
#     - geap-workshop-gateway-egress    AGENT_TO_ANYWHERE (egress) + regional registry
#   Global (Gemini Enterprise):
#     - geap-workshop-ge-gateway        CLIENT_TO_AGENT  (ingress)
#     - geap-workshop-ge-gateway-egress AGENT_TO_ANYWHERE (egress) + global registry
#
# IMPORTANT: A single gateway cannot support both GE and Agent Runtime.
# - Regional gateway (+ regional registry) = required for Agent Runtime
# - Global gateway (+ global registry)     = required for Gemini Enterprise
# These are mutually exclusive — you must deploy separate gateways for each.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
REGION="${GCP_REGION:-us-central1}"

# Regional gateways (Agent Runtime)
GATEWAY_NAME="${GATEWAY_NAME:-geap-workshop-gateway}"
GATEWAY_EGRESS_NAME="${GATEWAY_EGRESS_NAME:-geap-workshop-gateway-egress}"
# Global gateways (Gemini Enterprise)
GE_GATEWAY_NAME="${GE_GATEWAY_NAME:-geap-workshop-ge-gateway}"
GE_GATEWAY_EGRESS_NAME="${GE_GATEWAY_EGRESS_NAME:-geap-workshop-ge-gateway-egress}"

API_BASE="https://networkservices.googleapis.com/v1beta1"

echo "=== Setting up Agent Gateways ==="
echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo ""
echo "Regional (Agent Runtime):"
echo "  Ingress: $GATEWAY_NAME"
echo "  Egress:  $GATEWAY_EGRESS_NAME"
echo "Global (Gemini Enterprise):"
echo "  Ingress: $GE_GATEWAY_NAME"
echo "  Egress:  $GE_GATEWAY_EGRESS_NAME"
echo ""

# Enable required APIs
echo "[1/7] Enabling APIs..."
gcloud services enable \
    aiplatform.googleapis.com \
    networkservices.googleapis.com \
    cloudresourcemanager.googleapis.com \
    cloudtrace.googleapis.com \
    --project="$PROJECT_ID"

ACCESS_TOKEN=$(gcloud auth print-access-token)

# Helper: create a gateway and wait for the LRO
create_gateway() {
    local label="$1"
    local location="$2"
    local gw_id="$3"
    local body="$4"

    local url="${API_BASE}/projects/${PROJECT_ID}/locations/${location}/agentGateways"

    local existing
    existing=$(curl -s -o /dev/null -w "%{http_code}" \
        "${url}/${gw_id}" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}")

    if [ "$existing" = "200" ]; then
        echo "  ${label} already exists."
        # If body includes registries, ensure the existing gateway has them
        if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if 'registries' in d else 1)" 2>/dev/null; then
            local current
            current=$(curl -s "${url}/${gw_id}" -H "Authorization: Bearer ${ACCESS_TOKEN}")
            if ! echo "$current" | grep -q '"registries"'; then
                echo "  Patching ${label} to add registries..."
                local registries
                registries=$(echo "$body" | python3 -c "import sys,json; print(json.dumps({'registries': json.load(sys.stdin)['registries']}))")
                curl -s -X PATCH \
                    "${url}/${gw_id}?updateMask=registries" \
                    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
                    -H "Content-Type: application/json" \
                    -d "$registries" > /dev/null
                echo "  Registries added to ${label}."
            fi
        fi
        return 0
    fi

    local result
    result=$(curl -s -X POST \
        "${url}?agentGatewayId=${gw_id}" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$body")

    local op_name
    op_name=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('name',''))" 2>/dev/null)
    if [ -z "$op_name" ]; then
        echo "  ERROR creating ${label}: $result"
        return 1
    fi

    echo "  Waiting for ${label}..."
    local done_status="pending"
    for i in $(seq 1 24); do
        sleep 5
        done_status=$(curl -s "${API_BASE}/${op_name}" \
            -H "Authorization: Bearer ${ACCESS_TOKEN}" | \
            python3 -c "import sys,json; print(json.load(sys.stdin).get('done', False))" 2>/dev/null)
        if [ "$done_status" = "True" ]; then
            echo "  ${label} created."
            return 0
        fi
    done
    echo "  ERROR: ${label} creation timed out."
    return 1
}

# ── Regional gateways (Agent Runtime) ──

echo "[2/7] Creating regional ingress gateway (CLIENT_TO_AGENT)..."
create_gateway "Regional ingress" "$REGION" "$GATEWAY_NAME" '{
    "protocols": ["MCP"],
    "googleManaged": {
        "governedAccessPath": "CLIENT_TO_AGENT"
    }
}'

echo "[3/7] Creating regional egress gateway (AGENT_TO_ANYWHERE + regional registry)..."
create_gateway "Regional egress" "$REGION" "$GATEWAY_EGRESS_NAME" "{
    \"protocols\": [\"MCP\"],
    \"googleManaged\": {
        \"governedAccessPath\": \"AGENT_TO_ANYWHERE\"
    },
    \"registries\": [
        \"//agentregistry.googleapis.com/projects/${PROJECT_ID}/locations/${REGION}\"
    ]
}"

# ── Global gateways (Gemini Enterprise) ──

echo "[4/7] Creating global ingress gateway for Gemini Enterprise..."
create_gateway "GE ingress" "global" "$GE_GATEWAY_NAME" '{
    "protocols": ["MCP"],
    "googleManaged": {
        "governedAccessPath": "CLIENT_TO_AGENT"
    }
}'

echo "[5/7] Creating global egress gateway for Gemini Enterprise (+ global registry)..."
create_gateway "GE egress" "global" "$GE_GATEWAY_EGRESS_NAME" "{
    \"protocols\": [\"MCP\"],
    \"googleManaged\": {
        \"governedAccessPath\": \"AGENT_TO_ANYWHERE\"
    },
    \"registries\": [
        \"//agentregistry.googleapis.com/projects/${PROJECT_ID}/locations/global\"
    ]
}"

# Grant Reasoning Engine service account permissions to use gateways
echo "[6/7] Granting gateway permissions to Agent Engine service account..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
SA="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="$SA" \
    --role="roles/networkservices.viewer" \
    --condition=None \
    --quiet 2>/dev/null || echo "  networkservices.viewer already granted."

echo "[7/7] Granting agentGatewayUser role..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="$SA" \
    --role="roles/networkservices.agentGatewayUser" \
    --condition=None \
    --quiet 2>/dev/null || echo "  agentGatewayUser already granted."

GATEWAY_PATH="projects/${PROJECT_ID}/locations/${REGION}/agentGateways/${GATEWAY_NAME}"
GATEWAY_EGRESS_PATH="projects/${PROJECT_ID}/locations/${REGION}/agentGateways/${GATEWAY_EGRESS_NAME}"
GE_GATEWAY_PATH="projects/${PROJECT_ID}/locations/global/agentGateways/${GE_GATEWAY_NAME}"
GE_GATEWAY_EGRESS_PATH="projects/${PROJECT_ID}/locations/global/agentGateways/${GE_GATEWAY_EGRESS_NAME}"

echo ""
echo "=== Agent Gateway setup complete ==="
echo ""
echo "  Regional (Agent Runtime):"
echo "    Ingress: $GATEWAY_PATH"
echo "    Egress:  $GATEWAY_EGRESS_PATH  (registry: regional)"
echo ""
echo "  Global (Gemini Enterprise):"
echo "    Ingress: $GE_GATEWAY_PATH"
echo "    Egress:  $GE_GATEWAY_EGRESS_PATH  (registry: global)"
echo ""
echo "  Console: https://console.cloud.google.com/agent-platform/gateways?project=${PROJECT_ID}"
echo ""
echo "  Set in .env (Agent Runtime):"
echo "    AGENT_GATEWAY_PATH=$GATEWAY_PATH"
echo "    AGENT_GATEWAY_EGRESS_PATH=$GATEWAY_EGRESS_PATH"

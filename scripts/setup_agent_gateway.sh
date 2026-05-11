#!/usr/bin/env bash
# Setup Agent Gateway via REST API (v1alpha1)
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
REGION="${GCP_REGION:-us-central1}"
GATEWAY_NAME="${GATEWAY_NAME:-geap-workshop-gateway}"
GATEWAY_EGRESS_NAME="${GATEWAY_EGRESS_NAME:-geap-workshop-gateway-egress}"

echo "=== Setting up Agent Gateways (Ingress + Egress) ==="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Ingress Gateway: $GATEWAY_NAME"
echo "Egress Gateway:  $GATEWAY_EGRESS_NAME"

# Enable required APIs
echo "[1/5] Enabling APIs..."
gcloud services enable \
    aiplatform.googleapis.com \
    networkservices.googleapis.com \
    --project="$PROJECT_ID"

ACCESS_TOKEN=$(gcloud auth print-access-token)

# --- Ingress: Client-to-Agent gateway ---
echo "[2/5] Creating Client-to-Agent (ingress) gateway..."
EXISTING=$(curl -s -o /dev/null -w "%{http_code}" \
    "https://networkservices.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${REGION}/agentGateways/${GATEWAY_NAME}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")

if [ "$EXISTING" = "200" ]; then
    echo "  Ingress gateway already exists, skipping."
else
    # Create Client-to-Agent gateway via REST API
    RESULT=$(curl -s -X POST \
        "https://networkservices.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${REGION}/agentGateways?agentGatewayId=${GATEWAY_NAME}" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "protocols": ["MCP"],
            "googleManaged": {
                "governedAccessPath": "CLIENT_TO_AGENT"
            }
        }')

    # Wait for operation to complete
    OP_NAME=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('name',''))")
    if [ -n "$OP_NAME" ]; then
        echo "  Waiting for operation to complete..."
        for i in $(seq 1 12); do
            sleep 5
            DONE=$(curl -s "https://networkservices.googleapis.com/v1alpha1/${OP_NAME}" \
                -H "Authorization: Bearer ${ACCESS_TOKEN}" | \
                python3 -c "import sys,json; print(json.load(sys.stdin).get('done', False))")
            if [ "$DONE" = "True" ]; then
                echo "  Ingress gateway created successfully."
                break
            fi
        done
    else
        echo "  Error creating ingress gateway: $RESULT"
        exit 1
    fi
fi

# --- Egress: Agent-to-Anywhere gateway ---
echo "[3/5] Creating Agent-to-Anywhere (egress) gateway..."
EXISTING_EGRESS=$(curl -s -o /dev/null -w "%{http_code}" \
    "https://networkservices.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${REGION}/agentGateways/${GATEWAY_EGRESS_NAME}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")

if [ "$EXISTING_EGRESS" = "200" ]; then
    echo "  Egress gateway already exists, skipping."
else
    # Create Agent-to-Anywhere gateway via REST API
    RESULT_EGRESS=$(curl -s -X POST \
        "https://networkservices.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${REGION}/agentGateways?agentGatewayId=${GATEWAY_EGRESS_NAME}" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "protocols": ["MCP"],
            "googleManaged": {
                "governedAccessPath": "AGENT_TO_ANYWHERE"
            }
        }')

    # Wait for operation to complete
    OP_NAME_EGRESS=$(echo "$RESULT_EGRESS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('name',''))")
    if [ -n "$OP_NAME_EGRESS" ]; then
        echo "  Waiting for operation to complete..."
        for i in $(seq 1 12); do
            sleep 5
            DONE=$(curl -s "https://networkservices.googleapis.com/v1alpha1/${OP_NAME_EGRESS}" \
                -H "Authorization: Bearer ${ACCESS_TOKEN}" | \
                python3 -c "import sys,json; print(json.load(sys.stdin).get('done', False))")
            if [ "$DONE" = "True" ]; then
                echo "  Egress gateway created successfully."
                break
            fi
        done
    else
        echo "  Error creating egress gateway: $RESULT_EGRESS"
        exit 1
    fi
fi

# Grant Reasoning Engine service account permissions to use gateways
echo "[4/5] Granting gateway permissions to Agent Engine service account..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
SA="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="$SA" \
    --role="roles/networkservices.viewer" \
    --condition=None \
    --quiet 2>/dev/null || echo "  networkservices.viewer already granted."

echo "[5/5] Granting agentGatewayUser role..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="$SA" \
    --role="roles/networkservices.agentGatewayUser" \
    --condition=None \
    --quiet 2>/dev/null || echo "  agentGatewayUser already granted."

GATEWAY_PATH="projects/${PROJECT_ID}/locations/${REGION}/agentGateways/${GATEWAY_NAME}"
GATEWAY_EGRESS_PATH="projects/${PROJECT_ID}/locations/${REGION}/agentGateways/${GATEWAY_EGRESS_NAME}"
echo ""
echo "=== Agent Gateway setup complete ==="
echo "  Ingress gateway path: $GATEWAY_PATH"
echo "  Egress gateway path:  $GATEWAY_EGRESS_PATH"
echo "  Console: https://console.cloud.google.com/agent-platform/gateways?project=${PROJECT_ID}"
echo ""
echo "  Set in .env:"
echo "    AGENT_GATEWAY_PATH=$GATEWAY_PATH"
echo "    AGENT_GATEWAY_EGRESS_PATH=$GATEWAY_EGRESS_PATH"

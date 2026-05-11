#!/usr/bin/env bash
# Setup Agent Gateway via REST API (v1alpha1)
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

ACCESS_TOKEN=$(gcloud auth print-access-token)

# Check if gateway already exists
echo "[2/3] Creating Agent Gateway..."
EXISTING=$(curl -s -o /dev/null -w "%{http_code}" \
    "https://networkservices.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${REGION}/agentGateways/${GATEWAY_NAME}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")

if [ "$EXISTING" = "200" ]; then
    echo "  Gateway already exists, skipping."
else
    # Create Agent Gateway via REST API
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
                echo "  Gateway created successfully."
                break
            fi
        done
    else
        echo "  Error creating gateway: $RESULT"
        exit 1
    fi
fi

# Grant Reasoning Engine service account permissions to use gateway
echo "[3/3] Granting gateway permissions to Agent Engine service account..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
    --role="roles/networkservices.viewer" \
    --condition=None \
    --quiet 2>/dev/null || echo "  Permission already granted."

GATEWAY_PATH="projects/${PROJECT_ID}/locations/${REGION}/agentGateways/${GATEWAY_NAME}"
echo ""
echo "=== Agent Gateway setup complete ==="
echo "  Gateway path: $GATEWAY_PATH"
echo "  Console: https://console.cloud.google.com/agent-platform/gateways?project=${PROJECT_ID}"
echo ""
echo "  Set in .env: AGENT_GATEWAY_PATH=$GATEWAY_PATH"

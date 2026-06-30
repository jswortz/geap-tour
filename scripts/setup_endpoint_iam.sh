#!/usr/bin/env bash
# Grant roles/iap.egressor to the agent principal on all registered endpoints
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../.env" ]]; then
    set -a
    source "${SCRIPT_DIR}/../.env"
    set +a
fi

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
REGION="${GCP_REGION:-us-central1}"
AGENT_ENGINE_ID="${AGENT_ENGINE_ID:-7918285269789310976}"
ROUTER_ENGINE_ID="${ROUTER_ENGINE_ID:-}"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")

echo "=== Setting up IAM Policies on Registry Endpoints ==="
echo "Project: $PROJECT_ID ($PROJECT_NUMBER)"
echo "Region:  $REGION"
echo ""

ACCESS_TOKEN=$(gcloud auth print-access-token)
API_BASE="https://${REGION}-aiplatform.googleapis.com/v1beta1"

get_effective_identity() {
    local engine_id="$1"
    if [[ -z "$engine_id" ]]; then
        return
    fi
    curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" \
      "${API_BASE}/projects/${PROJECT_ID}/locations/${REGION}/reasoningEngines/${engine_id}" \
      | python3 -c "import sys,json; print(json.load(sys.stdin).get('spec',{}).get('effectiveIdentity',''))" 2>/dev/null
}

COORDINATOR_IDENTITY=$(get_effective_identity "$AGENT_ENGINE_ID")
ROUTER_IDENTITY=$(get_effective_identity "$ROUTER_ENGINE_ID")

MEMBERS=()
if [[ -n "$COORDINATOR_IDENTITY" ]]; then
    echo "Found Coordinator identity: $COORDINATOR_IDENTITY"
    MEMBERS+=("principal://${COORDINATOR_IDENTITY}")
fi
if [[ -n "$ROUTER_IDENTITY" ]]; then
    echo "Found Router identity: $ROUTER_IDENTITY"
    MEMBERS+=("principal://${ROUTER_IDENTITY}")
fi

if [ ${#MEMBERS[@]} -eq 0 ]; then
    ORG_ID=$(gcloud projects get-ancestors "$PROJECT_ID" --format="value(id)" 2>/dev/null | tail -n 1)
    if [[ -n "$ORG_ID" && "$ORG_ID" =~ ^[0-9]+$ ]]; then
        echo "Fallback to Org-wide principal Set: org-$ORG_ID"
        MEMBERS+=("principalSet://agents.global.org-${ORG_ID}.system.id.goog/attribute.platformContainer/aiplatform/projects/${PROJECT_NUMBER}")
    else
        echo "Fallback to Project-wide principal Set: project-$PROJECT_NUMBER"
        MEMBERS+=("principalSet://agents.global.project-${PROJECT_NUMBER}.system.id.goog/attribute.platformContainer/aiplatform/projects/${PROJECT_NUMBER}")
    fi
fi

# Build IAM policy JSON
MEMBERS_JSON=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1:]))" "${MEMBERS[@]}")
cat > /tmp/iam-policy-endpoint-egress.json <<POLICY
{
  "bindings": [
    {
      "role": "roles/iap.egressor",
      "members": ${MEMBERS_JSON}
    }
  ]
}
POLICY

# Get all endpoints from agent registry
ENDPOINTS=$(gcloud alpha agent-registry endpoints list --project="${PROJECT_ID}" --location="${REGION}" --format="value(name)" 2>/dev/null || echo "")

if [[ -z "$ENDPOINTS" ]]; then
    echo "No registered endpoints found in agent registry."
else
    for ep_path in $ENDPOINTS; do
        ep_id=$(basename "$ep_path")
        echo "Applying IAM policy on endpoint: $ep_id"
        gcloud beta iap web set-iam-policy /tmp/iam-policy-endpoint-egress.json \
            --project="${PROJECT_ID}" --region="${REGION}" --resource-type=agent-registry --endpoint="$ep_id" --quiet
    done
    echo "Done setting IAM policies on endpoints."
fi

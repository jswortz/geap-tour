#!/usr/bin/env bash
# Grant roles/iap.egressor to the agent principal on all registered endpoints
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
REGION="${GCP_REGION:-us-central1}"
AGENT_ENGINE_ID="${AGENT_ENGINE_ID:-7918285269789310976}"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")

AGENT_PRINCIPAL="principal://agents.global.org-1060412978793.system.id.goog/resources/aiplatform/projects/${PROJECT_NUMBER}/locations/${REGION}/reasoningEngines/${AGENT_ENGINE_ID}"

echo "Using Agent Principal: ${AGENT_PRINCIPAL}"

# Write IAM policy JSON
cat > /tmp/iam-policy-endpoint-egress.json <<POLICY
{
  "bindings": [
    {
      "role": "roles/iap.egressor",
      "members": [
        "${AGENT_PRINCIPAL}"
      ]
    }
  ]
}
POLICY

# Get all endpoints
ENDPOINTS=$(gcloud alpha agent-registry endpoints list --project="${PROJECT_ID}" --location="${REGION}" --format="value(name)")

for ep_path in $ENDPOINTS; do
    ep_id=$(basename "$ep_path")
    echo "Applying IAM policy on endpoint: $ep_id"
    gcloud beta iap web set-iam-policy /tmp/iam-policy-endpoint-egress.json \
        --project="${PROJECT_ID}" --region="${REGION}" --resource-type=agent-registry --endpoint="$ep_id" --quiet
done

echo "Done setting IAM policies on endpoints."

#!/usr/bin/env bash
# Setup Model Armor templates for Agent Armor — input and output screening
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
REGION="${GCP_REGION:-us-central1}"
PROMPT_TEMPLATE_NAME="geap-workshop-prompt"
RESPONSE_TEMPLATE_NAME="geap-workshop-response"

echo "=== Setting up Model Armor Templates ==="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"

# Enable Model Armor API
echo "[1/4] Enabling Model Armor API..."
gcloud services enable modelarmor.googleapis.com --project="$PROJECT_ID"

# Create prompt screening template (input guardrails)
echo "[2/4] Creating prompt screening template..."
PROMPT_FILTER='{
    "filterConfig": {
        "raiSettings": {
            "raiFilters": [
                {"filterType": "DANGEROUS", "confidenceLevel": "MEDIUM_AND_ABOVE"},
                {"filterType": "HARASSMENT", "confidenceLevel": "MEDIUM_AND_ABOVE"},
                {"filterType": "HATE_SPEECH", "confidenceLevel": "MEDIUM_AND_ABOVE"},
                {"filterType": "SEXUALLY_EXPLICIT", "confidenceLevel": "HIGH"}
            ]
        },
        "piAndJailbreakFilterSettings": {
            "filterEnforcement": "ENABLED",
            "confidenceLevel": "MEDIUM_AND_ABOVE"
        },
        "maliciousUriFilterSettings": {
            "filterEnforcement": "ENABLED"
        }
    }
}'

curl -s -X POST \
    "https://modelarmor.${REGION}.rep.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/templates?template_id=${PROMPT_TEMPLATE_NAME}" \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    -d "$PROMPT_FILTER" && echo "  ✓ Prompt template created" || echo "  Template may already exist"

# Create response screening template (output guardrails)
echo "[3/4] Creating response screening template..."
RESPONSE_FILTER='{
    "filterConfig": {
        "raiSettings": {
            "raiFilters": [
                {"filterType": "DANGEROUS", "confidenceLevel": "MEDIUM_AND_ABOVE"},
                {"filterType": "HARASSMENT", "confidenceLevel": "MEDIUM_AND_ABOVE"},
                {"filterType": "HATE_SPEECH", "confidenceLevel": "MEDIUM_AND_ABOVE"},
                {"filterType": "SEXUALLY_EXPLICIT", "confidenceLevel": "HIGH"}
            ]
        },
        "maliciousUriFilterSettings": {
            "filterEnforcement": "ENABLED"
        }
    }
}'

curl -s -X POST \
    "https://modelarmor.${REGION}.rep.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/templates?template_id=${RESPONSE_TEMPLATE_NAME}" \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    -d "$RESPONSE_FILTER" && echo "  ✓ Response template created" || echo "  Template may already exist"

# Grant the agent service account Model Armor roles
echo "[4/4] Granting IAM roles..."
SA_EMAIL="${PROJECT_ID}@appspot.gserviceaccount.com"
for role in roles/modelarmor.user roles/modelarmor.calloutUser; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="$role" \
        --condition=None \
        --quiet 2>/dev/null || true
done

PROMPT_TEMPLATE="projects/${PROJECT_ID}/locations/${REGION}/templates/${PROMPT_TEMPLATE_NAME}"
RESPONSE_TEMPLATE="projects/${PROJECT_ID}/locations/${REGION}/templates/${RESPONSE_TEMPLATE_NAME}"

echo ""
echo "✓ Model Armor setup complete"
echo ""
echo "Templates:"
echo "  Prompt:   $PROMPT_TEMPLATE"
echo "  Response: $RESPONSE_TEMPLATE"
echo ""
echo "Add to .env:"
echo "  MODEL_ARMOR_PROMPT_TEMPLATE=$PROMPT_TEMPLATE"
echo "  MODEL_ARMOR_RESPONSE_TEMPLATE=$RESPONSE_TEMPLATE"

#!/usr/bin/env bash
# Setup Agent Identity — creates Workload Identity Pool and binds SPIFFE principals
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
ORG_ID="${GCP_ORG_ID}"
REGION="${GCP_REGION:-us-central1}"

if [[ -z "${ORG_ID:-}" ]]; then
    echo "ERROR: GCP_ORG_ID must be set"
    exit 1
fi

echo "=== Setting up Agent Identity ==="
echo "Project: $PROJECT_ID"
echo "Org: $ORG_ID"

# Enable required APIs
echo "[1/4] Enabling APIs..."
gcloud services enable \
    aiplatform.googleapis.com \
    iam.googleapis.com \
    --project="$PROJECT_ID"

# Create Workload Identity Pool for agents (if not exists)
echo "[2/4] Creating Workload Identity Pool..."
gcloud iam workload-identity-pools create agent-pool \
    --project="$PROJECT_ID" \
    --location="global" \
    --display-name="Agent Identity Pool" \
    --description="Workload Identity Pool for GEAP workshop agents" \
    2>/dev/null || echo "  Pool already exists, skipping."

# Create OIDC provider for Agent Engine
echo "[3/4] Creating OIDC provider..."
gcloud iam workload-identity-pools providers create-oidc agent-engine-provider \
    --project="$PROJECT_ID" \
    --location="global" \
    --workload-identity-pool="agent-pool" \
    --issuer-uri="https://agents.global.org-${ORG_ID}.system.id.goog" \
    --attribute-mapping="google.subject=assertion.sub" \
    2>/dev/null || echo "  Provider already exists, skipping."

# Grant the agent principal access to resources
echo "[4/4] Binding IAM roles..."

# Agent principal format: principal://agents.global.org-{ORG_ID}.system.id.goog/agent/{AGENT_ID}
# For workshop, grant broad access to all agents in the pool
AGENT_PRINCIPAL="principalSet://iam.googleapis.com/projects/${PROJECT_ID}/locations/global/workloadIdentityPools/agent-pool/*"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="$AGENT_PRINCIPAL" \
    --role="roles/aiplatform.user" \
    --condition=None \
    --quiet

echo ""
echo "✓ Agent Identity setup complete"
echo "  Agents deployed with identity_type=AGENT_IDENTITY will get SPIFFE-based principals"
echo "  Principal format: principal://agents.global.org-${ORG_ID}.system.id.goog/agent/{AGENT_ID}"

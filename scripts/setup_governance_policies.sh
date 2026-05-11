#!/usr/bin/env bash
# Setup Agent Gateway governance policies — IAM Allow + SGP (Semantic Governance)
#
# Three policy layers demonstrated:
#   1. IAM Allow Policies  — static egress control (which agents can call which MCP servers)
#   2. Semantic Governance — natural-language business rules evaluated at runtime by SGP engine
#   3. Model Armor         — prompt/response content screening (separate setup in setup_model_armor.sh)
#
# Prerequisites:
#   - Agent Gateway "geap-workshop-gateway" exists (run setup_agent_gateway.sh first)
#   - Agents and MCP servers registered in Agent Registry (run register_agent_registry.sh first)
#   - gcloud beta components installed
#
# Usage: bash scripts/setup_governance_policies.sh

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
REGION="${GCP_REGION:-us-central1}"
GATEWAY_NAME="geap-workshop-gateway"

echo "=== GEAP Governance Policies Setup ==="
echo "Project:  ${PROJECT_ID}"
echo "Region:   ${REGION}"
echo "Gateway:  ${GATEWAY_NAME}"
echo ""

# ─────────────────────────────────────────────────────────────
# Layer 1: IAM Allow Policies (egress control via IAP)
# ─────────────────────────────────────────────────────────────
#
# IAM Allow policies control WHICH agents can access WHICH MCP servers/tools.
# Enforced by Identity-Aware Proxy (IAP) at the Agent Gateway boundary.
#
# Policy types:
#   - Agent → Registry     (agent can access all resources in registry)
#   - Agent → Agent        (agent can call another agent)
#   - Agent → MCP Server   (agent can access a specific MCP server)
#   - Agent → Endpoint     (agent can access a specific endpoint)
#
# Conditions (CEL expressions) can restrict:
#   - Tool name        api.getAttribute('iap.googleapis.com/mcp.toolName', '')
#   - Read-only        api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false)
#   - Destructive      api.getAttribute('iap.googleapis.com/mcp.tool.isDestructive', false)
#   - Idempotent       api.getAttribute('iap.googleapis.com/mcp.tool.isIdempotent', false)
#   - Open world       api.getAttribute('iap.googleapis.com/mcp.tool.isOpenWorld', false)
#   - Auth type        api.getAttribute('iap.googleapis.com/request.auth.type', '')

echo "── Layer 1: IAM Allow Policies ──"
echo ""

# Example 1: Allow coordinator agent read-only access to the Search MCP server
cat > /tmp/iam-policy-coordinator-search.json <<'POLICY'
{
  "policy": {
    "bindings": [
      {
        "role": "roles/iap.egressor",
        "members": [
          "principal://service-679926387543@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
        ],
        "condition": {
          "title": "Coordinator read-only search access",
          "description": "GEAP Coordinator can only perform read-only operations on Search MCP",
          "expression": "api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false) == true"
        }
      }
    ]
  }
}
POLICY
echo "  [1/3] IAM policy: Coordinator → Search MCP (read-only)"
echo "        File: /tmp/iam-policy-coordinator-search.json"
echo "        Apply with: gcloud beta iap web set-iam-policy /tmp/iam-policy-coordinator-search.json \\"
echo "            --project=${PROJECT_ID} --mcpServer=search-mcp --region=${REGION}"
echo ""

# Example 2: Allow travel agent full access to Booking MCP but deny destructive operations
cat > /tmp/iam-policy-travel-booking.json <<'POLICY'
{
  "policy": {
    "bindings": [
      {
        "role": "roles/iap.egressor",
        "members": [
          "principal://service-679926387543@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
        ],
        "condition": {
          "title": "Travel agent booking access - no destructive ops",
          "description": "Travel agent can use Booking MCP tools but cannot perform destructive operations",
          "expression": "api.getAttribute('iap.googleapis.com/mcp.tool.isDestructive', false) == false"
        }
      }
    ]
  }
}
POLICY
echo "  [2/3] IAM policy: Travel Agent → Booking MCP (non-destructive)"
echo "        File: /tmp/iam-policy-travel-booking.json"
echo ""

# Example 3: Allow expense agent access only to specific tools by name
cat > /tmp/iam-policy-expense-tools.json <<'POLICY'
{
  "policy": {
    "bindings": [
      {
        "role": "roles/iap.egressor",
        "members": [
          "principal://service-679926387543@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
        ],
        "condition": {
          "title": "Expense agent tool-level access",
          "description": "Expense agent can only use submit_expense, check_policy, and get_expenses tools",
          "expression": "api.getAttribute('iap.googleapis.com/mcp.toolName', '') in ['submit_expense', 'check_expense_policy', 'get_expenses'] && api.getAttribute('iap.googleapis.com/request.auth.type', '') == 'MCP'"
        }
      }
    ]
  }
}
POLICY
echo "  [3/3] IAM policy: Expense Agent → Expense MCP (specific tools only)"
echo "        File: /tmp/iam-policy-expense-tools.json"
echo ""

echo "  NOTE: IAM policies require Agent Gateway Private Preview enrollment."
echo "        Apply policies with: gcloud beta iap web set-iam-policy <file.json> \\"
echo "            --project=${PROJECT_ID} --mcpServer=<server> --region=${REGION}"
echo ""

# ─────────────────────────────────────────────────────────────
# Layer 2: Semantic Governance Policies (SGP)
# ─────────────────────────────────────────────────────────────
#
# SGP provides runtime evaluation of tool calls against natural language
# business rules. Unlike IAM (static), SGP evaluates the CONTEXT of each
# request — the user prompt, chat history, and proposed tool parameters.
#
# SGP verdicts:
#   ALLOW              — action proceeds
#   DENY               — action blocked, user sees rationale
#   ALLOW_IF_CONFIRMED — action paused for human confirmation
#
# Setup requires (Private Preview):
#   1. VPC network + subnet
#   2. Private DNS zone
#   3. SGP engine provisioning (~15-20 min)
#   4. Authorization extension + policy on Agent Gateway

echo "── Layer 2: Semantic Governance Policies (SGP) ──"
echo ""

# Step 1: Network prerequisites (skip if already exists)
NETWORK_NAME="geap-agent-network"
SUBNET_NAME="geap-agent-subnet"
DNS_ZONE_NAME="geap-private-zone"

echo "  Step 1: VPC Network Setup"
if gcloud compute networks describe "${NETWORK_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "    VPC network '${NETWORK_NAME}' already exists — skipping"
else
    echo "    Creating VPC network '${NETWORK_NAME}'..."
    gcloud compute networks create "${NETWORK_NAME}" \
        --subnet-mode=auto \
        --project="${PROJECT_ID}" 2>/dev/null || echo "    (network creation requires compute.networks.create permission)"
fi

echo ""
echo "  Step 2: Subnet"
if gcloud compute networks subnets describe "${SUBNET_NAME}" --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "    Subnet '${SUBNET_NAME}' already exists — skipping"
else
    echo "    Creating subnet '${SUBNET_NAME}'..."
    gcloud compute networks subnets create "${SUBNET_NAME}" \
        --network="${NETWORK_NAME}" \
        --region="${REGION}" \
        --range=10.11.12.0/24 \
        --project="${PROJECT_ID}" 2>/dev/null || echo "    (subnet creation requires the VPC network to exist)"
fi

echo ""
echo "  Step 3: Private DNS Zone"
if gcloud dns managed-zones describe "${DNS_ZONE_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "    DNS zone '${DNS_ZONE_NAME}' already exists — skipping"
else
    echo "    Creating DNS zone '${DNS_ZONE_NAME}'..."
    gcloud dns managed-zones create "${DNS_ZONE_NAME}" \
        --description="Private zone for GEAP agent governance" \
        --dns-name="geap-internal.example.com." \
        --visibility=private \
        --networks="${NETWORK_NAME}" \
        --project="${PROJECT_ID}" 2>/dev/null || echo "    (DNS zone creation requires dns.managedZones.create permission)"
fi

echo ""
echo "  Step 4: Provision SGP Engine (~15-20 min)"
echo "    Command:"
echo "    gcloud beta ai semantic-governance-policy-engine update \\"
echo "        --location=${REGION} \\"
echo "        --gateway-config=\"dns-zone-name=${DNS_ZONE_NAME},network=${NETWORK_NAME},subnetwork=${SUBNET_NAME}\" \\"
echo "        --project=${PROJECT_ID}"
echo ""
echo "    Check status:"
echo "    gcloud beta ai semantic-governance-policy-engine describe \\"
echo "        --location=${REGION} --project=${PROJECT_ID}"
echo ""

# Step 5: Create example SGP policies
echo "  Step 5: Example SGP Policies (Natural Language Constraints)"
echo ""

# Set API endpoint for regional SGP commands
echo "  Setting regional API endpoint..."
gcloud config set api_endpoint_overrides/aiplatform \
    "https://${REGION}-aiplatform.googleapis.com/" 2>/dev/null || true

# SGP Policy 1: Agent-scope — business hours restriction
echo "  [SGP-1] Agent-scope: Business hours restriction"
echo "    gcloud beta ai semantic-governance-policies create geap-business-hours \\"
echo "        --location=${REGION} \\"
echo "        --display-name='Business Hours Enforcement' \\"
echo "        --description='Restrict booking and expense operations to business hours' \\"
echo "        --agent=geap-coordinator-agent \\"
echo "        --natural-language-constraint='The agent must not perform booking or expense submission operations outside of business hours (9 AM to 6 PM Pacific Time, Monday through Friday). Read-only searches are allowed at any time.' \\"
echo "        --project=${PROJECT_ID}"
echo ""

# SGP Policy 2: Tool-scope — expense amount limit
echo "  [SGP-2] Tool-scope: Expense amount limit"
echo "    gcloud beta ai semantic-governance-policies create geap-expense-limit \\"
echo "        --location=${REGION} \\"
echo "        --display-name='Expense Amount Guardrail' \\"
echo "        --description='Enforce expense policy limits at the governance layer' \\"
echo "        --agent=geap-coordinator-agent \\"
echo "        --mcp-tools='mcp-server=expense-mcp,tools=submit_expense' \\"
echo "        --natural-language-constraint='Disallow expense submissions exceeding \$200 for the meals category. Disallow expense submissions exceeding \$500 for the entertainment category. Any expense over \$1000 in any category must be denied with a message to contact their manager for approval.' \\"
echo "        --project=${PROJECT_ID}"
echo ""

# SGP Policy 3: Tool-scope — booking confirmation required
echo "  [SGP-3] Tool-scope: Booking confirmation"
echo "    gcloud beta ai semantic-governance-policies create geap-booking-confirm \\"
echo "        --location=${REGION} \\"
echo "        --display-name='Booking Confirmation Required' \\"
echo "        --description='Require user confirmation before finalizing bookings' \\"
echo "        --agent=geap-coordinator-agent \\"
echo "        --mcp-tools='mcp-server=booking-mcp,tools=book_flight' \\"
echo "        --natural-language-constraint='Always require explicit user confirmation before booking any flight. The agent must present the flight details including price, departure time, and airline to the user and receive a clear confirmation such as yes, confirm, or book it before calling the book_flight tool. If the user has not explicitly confirmed, the verdict should be ALLOW_IF_CONFIRMED.' \\"
echo "        --project=${PROJECT_ID}"
echo ""

# SGP Policy 4: Agent-scope — prevent data exfiltration
echo "  [SGP-4] Agent-scope: Anti-exfiltration"
echo "    gcloud beta ai semantic-governance-policies create geap-anti-exfil \\"
echo "        --location=${REGION} \\"
echo "        --display-name='Anti-Exfiltration Guard' \\"
echo "        --description='Prevent agents from leaking user data to unrelated tools' \\"
echo "        --agent=geap-coordinator-agent \\"
echo "        --natural-language-constraint='The agent must never use search or booking tools to transmit personal information such as employee IDs, email addresses, or expense details that were obtained from the expense system. If the proposed tool call contains personal data from a different tool context, deny the action.' \\"
echo "        --project=${PROJECT_ID}"
echo ""

# ─────────────────────────────────────────────────────────────
# Layer 3: Connect SGP to Agent Gateway
# ─────────────────────────────────────────────────────────────

echo "── Layer 3: Connect SGP Engine to Agent Gateway ──"
echo ""
echo "  After SGP engine is ACTIVE, create the authorization extension and policy:"
echo ""

ACCESS_TOKEN=$(gcloud auth print-access-token 2>/dev/null || echo "TOKEN")
SGP_DNS_HOSTNAME="${REGION}.geap-internal.example.com"

echo "  [1/2] Create Authorization Extension:"
echo "    curl -X POST \\"
echo "      'https://networkservices.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${REGION}/authzExtensions?authzExtensionId=geap-sgp-extension' \\"
echo "      -H 'Authorization: Bearer \$(gcloud auth print-access-token)' \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"service\": \"${SGP_DNS_HOSTNAME}\", \"authority\": \"${SGP_DNS_HOSTNAME}\", \"failOpen\": false, \"loadBalancingScheme\": \"LOAD_BALANCING_SCHEME_UNSPECIFIED\"}'"
echo ""

echo "  [2/2] Create Authorization Policy:"
echo "    curl -X POST \\"
echo "      'https://networksecurity.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${REGION}/authzPolicies?authzPolicyId=geap-sgp-policy' \\"
echo "      -H 'Authorization: Bearer \$(gcloud auth print-access-token)' \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"target\": {\"loadBalancingScheme\": \"LOAD_BALANCING_SCHEME_UNSPECIFIED\", \"resources\": [\"projects/${PROJECT_ID}/locations/${REGION}/agentGateways/${GATEWAY_NAME}\"]}, \"httpRules\": [{\"to\": {\"operations\": [{\"paths\": [{\"prefix\": \"/\"}]}]}, \"when\": \"!request.headers['\\\"'\\\"'content-type'\\\"'\\\"'].startsWith('\\\"'\\\"'application/grpc'\\\"'\\\"')\"}], \"action\": \"CUSTOM\", \"policyProfile\": \"CONTENT_AUTHZ\", \"customProvider\": {\"authzExtension\": {\"resources\": [\"projects/${PROJECT_ID}/locations/${REGION}/authzExtensions/geap-sgp-extension\"]}}}'"
echo ""

echo "  Optional: Enable dry-run mode for testing:"
echo "    curl -X PATCH \\"
echo "      'https://networkservices.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${REGION}/authzExtensions/geap-sgp-extension?updateMask=metadata' \\"
echo "      -H 'Authorization: Bearer \$(gcloud auth print-access-token)' \\"
echo "      -d '{\"metadata\": {\"sgpEnforcementMode\": \"DRY_RUN\"}}'"
echo ""

# ─────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────

echo "═══════════════════════════════════════════════════"
echo "  GEAP Governance Policy Summary"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Layer 1 — IAM Allow Policies (static egress control)"
echo "    - Coordinator → Search MCP (read-only)"
echo "    - Travel → Booking MCP (non-destructive)"
echo "    - Expense → Expense MCP (specific tools)"
echo ""
echo "  Layer 2 — Semantic Governance (runtime business rules)"
echo "    - SGP-1: Business hours restriction"
echo "    - SGP-2: Expense amount limits (\$200 meals, \$500 entertainment)"
echo "    - SGP-3: Booking confirmation required"
echo "    - SGP-4: Anti-exfiltration guard"
echo ""
echo "  Layer 3 — Model Armor (content screening)"
echo "    - See: scripts/setup_model_armor.sh"
echo "    - Template: geap-workshop-prompt"
echo "    - Detections: prompt injection, malicious URLs, Responsible AI"
echo ""
echo "  NOTE: Agent Gateway features require Private Preview enrollment."
echo "  Request access: https://forms.gle/ZLNYKUDW7j2B4a8K7"
echo ""
echo "  Done."

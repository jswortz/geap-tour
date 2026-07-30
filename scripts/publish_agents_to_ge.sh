#!/usr/bin/env bash
# Publish the two ADK agents (coordinator + router) directly to Gemini Enterprise using the
# official `agents-cli publish gemini-enterprise --registration-type adk` command.
#
# This is the CLI equivalent of scripts/publish_agents_to_ge.py: it registers each agent's
# reasoning engine to the GE app (adkAgentDefinition -> provisionedReasoningEngine). Both are
# idempotent — re-running updates the existing registration in place.
#
# Requires: agents-cli (google-agents-cli) on PATH, and gcloud auth for the reasoning-engine lookup.
set -euo pipefail

# --- Config (env overridable; sensible defaults for this workshop project) ---
[ -f .env ] && { set -a; source .env; set +a; }
PROJECT_ID="${GEMINI_ENTERPRISE_PROJECT:-${GCP_PROJECT_ID:-wortz-project-352116}}"
GE_LOCATION="${GEMINI_ENTERPRISE_LOCATION:-global}"
ENGINE_ID="${GEMINI_ENTERPRISE_ENGINE_ID:-gemini-enterprise-17634901_1763490144996}"
RE_REGION="${GCP_REGION:-us-central1}"

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
GE_APP_ID="projects/${PROJECT_NUMBER}/locations/${GE_LOCATION}/collections/default_collection/engines/${ENGINE_ID}"

# Resolve a reasoning engine ID live by displayName (env override wins).
resolve_engine() {
  local display="$1" override="$2"
  if [ -n "$override" ]; then echo "${override##*/}"; return; fi
  local token; token="$(gcloud auth print-access-token)"
  curl -s -H "Authorization: Bearer ${token}" -H "X-Goog-User-Project: ${PROJECT_ID}" \
    "https://${RE_REGION}-aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${RE_REGION}/reasoningEngines?pageSize=100" \
  | python3 -c "
import sys, json
disp = '${display}'
engines = json.load(sys.stdin).get('reasoningEngines', [])
m = sorted([e for e in engines if e.get('displayName') == disp],
           key=lambda e: e.get('updateTime', ''), reverse=True)
if not m:
    sys.exit(f'No reasoning engine named {disp}')
print(m[0]['name'].split('/')[-1])
"
}

COORDINATOR_ID="$(resolve_engine coordinator_agent "${COORDINATOR_ENGINE_ID:-}")"
ROUTER_ID="$(resolve_engine router_agent "${ROUTER_ENGINE_ID:-}")"

echo "GE app:      ${GE_APP_ID}"
echo "coordinator: reasoningEngines/${COORDINATOR_ID}"
echo "router:      reasoningEngines/${ROUTER_ID}"
echo

publish() {
  local runtime_id="$1" name="$2" desc="$3" tool="$4"
  echo "=== publishing: ${name} ==="
  agents-cli publish gemini-enterprise \
    --registration-type adk \
    --agent-runtime-id "projects/${PROJECT_ID}/locations/${RE_REGION}/reasoningEngines/${runtime_id}" \
    --gemini-enterprise-app-id "${GE_APP_ID}" \
    --project-id "${PROJECT_ID}" \
    --display-name "${name}" \
    --description "${desc}" \
    --tool-description "${tool}"
  echo
}

publish "${COORDINATOR_ID}" \
  "GEAP Corporate Travel & Expense Assistant" \
  "Coordinator agent for corporate travel and expense: flight/hotel search, expense-policy checks, and delegated booking/expense submission via MCP tools, with Memory Bank personalization and Model Armor guardrails." \
  "Use for corporate travel booking, flight/hotel search, and expense-policy questions and submissions."

publish "${ROUTER_ID}" \
  "GEAP Multi-Model Cost Router" \
  "Multi-model complexity router: classifies each prompt and routes it to the cheapest capable model tier (Flash-Lite → Flash → Pro → Sonnet → Opus) to optimize cost while preserving quality." \
  "Use for general questions; automatically routes each request to the most cost-effective model tier for its complexity."

echo "Done. View both agents in the GE console:"
echo "  https://console.cloud.google.com/gemini-enterprise/locations/${GE_LOCATION}/engines/${ENGINE_ID}/overview/dashboard?project=${PROJECT_ID}"

#!/usr/bin/env bash
# Register Agent Engine deployments in App Hub for topology visualization.
#
# App Hub provides the Topology tab in the Agent Engine console by
# tracking relationships between services and workloads. Reasoning
# Engines are auto-discovered as workloads but must be explicitly
# registered to an App Hub application.
#
# Steps:
#   1. Create an App Hub application (idempotent)
#   2. List discovered workloads to find Reasoning Engines
#   3. Register each agent as a workload in the application
#
# Usage:
#   bash scripts/setup_apphub.sh
#   bash scripts/setup_apphub.sh --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -f "${REPO_ROOT}/.env" ]; then
    set -a
    source "${REPO_ROOT}/.env"
    set +a
fi

PROJECT_ID="${GCP_PROJECT_ID:-hybrid-vertex}"
PROJECT_NUMBER="${PROJECT_NUMBER:-934903580331}"
REGION="${GCP_REGION:-us-central1}"
APP_NAME="${APPHUB_APP_NAME:-geap-workshop}"
COORDINATOR_ID="${COORINDATOR_AGENT_ID:-8296365537139621888}"
ROUTER_ID="${ROUTER_ENGINE_ID:-${AGENT_ENGINE_ID:-4709107696450666496}}"

DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
    esac
done

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${BLUE}  $1${NC}"; }
ok()    { echo -e "${GREEN}  ✓ $1${NC}"; }
warn()  { echo -e "${YELLOW}  ⚠ $1${NC}"; }
fail()  { echo -e "${RED}  ✗ $1${NC}"; }

run_cmd() {
    if $DRY_RUN; then
        echo -e "${YELLOW}  [dry-run] $*${NC}"
    else
        "$@"
    fi
}

echo "=============================================="
echo " App Hub Registration"
echo "=============================================="
echo "  Project:      $PROJECT_ID"
echo "  Region:       $REGION"
echo "  Application:  $APP_NAME"
echo "  Coordinator:  $COORDINATOR_ID"
echo "  Router:       $ROUTER_ID"
echo ""

# --- Step 1: Create App Hub application ---
echo "--- Step 1: Create App Hub application ---"

existing=$(gcloud apphub applications describe "$APP_NAME" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --format="value(name)" 2>/dev/null || true)

if [ -n "$existing" ]; then
    ok "Application '$APP_NAME' already exists"
else
    info "Creating application '$APP_NAME'..."
    run_cmd gcloud apphub applications create "$APP_NAME" \
        --project="$PROJECT_ID" \
        --location="$REGION" \
        --scope-type=REGIONAL \
        --display-name="GEAP Workshop Agents"
    ok "Application created"
fi
echo ""

# --- Step 2: List discovered workloads ---
echo "--- Step 2: List discovered workloads ---"

info "Searching for Reasoning Engine workloads..."
discovered=$(gcloud apphub discovered-workloads list \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --format="table(name,workloadReference.uri)" 2>/dev/null || true)

echo "$discovered"
echo ""

# Find discovered workload IDs for our agents
find_discovered_workload() {
    local engine_id="$1"
    local uri_pattern="reasoningEngines/${engine_id}"
    gcloud apphub discovered-workloads list \
        --project="$PROJECT_ID" \
        --location="$REGION" \
        --format="value(name)" \
        --filter="workloadReference.uri~'${uri_pattern}'" 2>/dev/null || true
}

COORDINATOR_DISCOVERED=$(find_discovered_workload "$COORDINATOR_ID")
ROUTER_DISCOVERED=$(find_discovered_workload "$ROUTER_ID")

if [ -z "$COORDINATOR_DISCOVERED" ]; then
    warn "Coordinator agent ($COORDINATOR_ID) not found in discovered workloads"
    warn "App Hub may need a few minutes to discover newly deployed agents"
else
    ok "Found coordinator: $COORDINATOR_DISCOVERED"
fi

if [ -z "$ROUTER_DISCOVERED" ]; then
    warn "Router agent ($ROUTER_ID) not found in discovered workloads"
    warn "App Hub may need a few minutes to discover newly deployed agents"
else
    ok "Found router: $ROUTER_DISCOVERED"
fi
echo ""

# --- Step 3: Register workloads ---
echo "--- Step 3: Register workloads to application ---"

register_workload() {
    local workload_name="$1"
    local display_name="$2"
    local discovered_workload="$3"

    if [ -z "$discovered_workload" ]; then
        warn "Skipping '$display_name' — not discovered yet"
        return
    fi

    existing_workload=$(gcloud apphub applications workloads describe "$workload_name" \
        --application="$APP_NAME" \
        --project="$PROJECT_ID" \
        --location="$REGION" \
        --format="value(name)" 2>/dev/null || true)

    if [ -n "$existing_workload" ]; then
        ok "'$display_name' already registered"
    else
        info "Registering '$display_name'..."
        run_cmd gcloud apphub applications workloads create "$workload_name" \
            --application="$APP_NAME" \
            --project="$PROJECT_ID" \
            --location="$REGION" \
            --discovered-workload="$discovered_workload" \
            --display-name="$display_name"
        ok "'$display_name' registered"
    fi
}

register_workload "coordinator-agent" "Coordinator Agent" "$COORDINATOR_DISCOVERED"
register_workload "router-agent" "Router Agent" "$ROUTER_DISCOVERED"
echo ""

# --- Step 3b: Register MCP servers as services ---
echo "--- Step 3b: Register MCP services to application ---"

find_discovered_service() {
    local service_pattern="$1"
    gcloud apphub discovered-services list \
        --project="$PROJECT_ID" \
        --location="$REGION" \
        --format="value(name)" \
        --filter="serviceReference.uri~'run.googleapis.com.*${service_pattern}'" 2>/dev/null | head -1 || true
}

register_service() {
    local service_name="$1"
    local display_name="$2"
    local discovered_service="$3"

    if [ -z "$discovered_service" ]; then
        warn "Skipping '$display_name' — not discovered yet"
        return
    fi

    existing_service=$(gcloud apphub applications services describe "$service_name" \
        --application="$APP_NAME" \
        --project="$PROJECT_ID" \
        --location="$REGION" \
        --format="value(name)" 2>/dev/null || true)

    if [ -n "$existing_service" ]; then
        ok "'$display_name' already registered"
    else
        info "Registering '$display_name'..."
        run_cmd gcloud apphub applications services create "$service_name" \
            --application="$APP_NAME" \
            --project="$PROJECT_ID" \
            --location="$REGION" \
            --discovered-service="$discovered_service" \
            --display-name="$display_name"
        ok "'$display_name' registered"
    fi
}

SEARCH_MCP_DISCOVERED=$(find_discovered_service "search-mcp")
BOOKING_MCP_DISCOVERED=$(find_discovered_service "booking-mcp")
EXPENSE_MCP_DISCOVERED=$(find_discovered_service "expense-mcp")

[ -n "$SEARCH_MCP_DISCOVERED" ] && ok "Found search-mcp: $SEARCH_MCP_DISCOVERED" || warn "search-mcp not found"
[ -n "$BOOKING_MCP_DISCOVERED" ] && ok "Found booking-mcp: $BOOKING_MCP_DISCOVERED" || warn "booking-mcp not found"
[ -n "$EXPENSE_MCP_DISCOVERED" ] && ok "Found expense-mcp: $EXPENSE_MCP_DISCOVERED" || warn "expense-mcp not found"

register_service "search-mcp" "Search MCP Server" "$SEARCH_MCP_DISCOVERED"
register_service "booking-mcp" "Booking MCP Server" "$BOOKING_MCP_DISCOVERED"
register_service "expense-mcp" "Expense MCP Server" "$EXPENSE_MCP_DISCOVERED"
echo ""

# --- Step 4: Verify ---
echo "--- Step 4: Verify registration ---"

echo "Workloads:"
gcloud apphub applications workloads list \
    --application="$APP_NAME" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --format="table(name.basename(),displayName,workloadReference.uri)" 2>/dev/null || true

echo ""
echo "Services:"
gcloud apphub applications services list \
    --application="$APP_NAME" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --format="table(name.basename(),displayName,serviceReference.uri)" 2>/dev/null || true

echo ""
ok "Topology data should appear in the Agent Engine console within a few minutes"

echo ""
echo "=============================================="
echo " Done"
echo "=============================================="

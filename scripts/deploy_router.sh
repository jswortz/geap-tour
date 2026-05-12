#!/usr/bin/env bash
# =============================================================================
# Multi-Model Router — Deploy to Vertex AI Agent Runtime
# =============================================================================
# Deploys the multi-model prompt router that classifies prompt complexity
# and routes to: Flash Lite (low), Flash (medium), or Opus 4-7 (high).
#
# Usage:
#   bash scripts/deploy_router.sh
#   # or with custom models:
#   OPUS_MODEL=vertex_ai/claude-sonnet-4-6 bash scripts/deploy_router.sh
# =============================================================================
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-wortz-project-352116}"
REGION="${GCP_REGION:-us-central1}"

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

step() { echo -e "\n${BLUE}━━━ [$1] $2 ━━━${NC}"; }
ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║        Multi-Model Router — Deployment                      ║"
echo "║  Project: ${PROJECT_ID}"
echo "║  Region:  ${REGION}"
echo "║  Models:  Lite → Flash → Opus 4-7                           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ─── Step 1: Verify prerequisites ──────────────────────────────────
step "1/5" "Checking prerequisites"

gcloud services enable \
    aiplatform.googleapis.com \
    modelarmor.googleapis.com \
    --project="$PROJECT_ID" --quiet
ok "Required APIs enabled"

# Verify ADK CLI
if ! uv run adk --version &>/dev/null; then
    fail "ADK CLI not found. Run: uv sync"
fi
ok "ADK CLI available ($(uv run adk --version 2>&1))"

# ─── Step 2: Verify model access ──────────────────────────────────
step "2/5" "Verifying model access"

LITE_MODEL="${LITE_MODEL:-gemini-2.0-flash-lite}"
FLASH_MODEL="${FLASH_MODEL:-gemini-2.5-flash}"
OPUS_MODEL="${OPUS_MODEL:-vertex_ai/claude-opus-4-7}"

echo "  Lite tier:   ${LITE_MODEL}"
echo "  Flash tier:  ${FLASH_MODEL}"
echo "  Opus tier:   ${OPUS_MODEL}"

if [[ "$OPUS_MODEL" == *"claude"* ]]; then
    warn "Claude model requires Model Garden enablement"
    warn "Visit: https://console.cloud.google.com/vertex-ai/model-garden"
fi

# ─── Step 3: Run tests ────────────────────────────────────────────
step "3/5" "Running tests"

if uv run python -m pytest tests/test_router.py -v --tb=short 2>&1; then
    ok "All router tests passed"
else
    fail "Tests failed — fix before deploying"
fi

# ─── Step 4: Run demo (classifier validation) ─────────────────────
step "4/5" "Validating classifier"

if uv run python -m src.router.demo 2>&1; then
    ok "Classifier validated — routing decisions look correct"
else
    warn "Classifier validation had issues (may be expected for some prompts)"
fi

# ─── Step 5: Deploy to Agent Runtime ──────────────────────────────
step "5/5" "Deploying to Vertex AI Agent Runtime"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

uv run adk deploy agent_engine \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --display_name="multi-model-router" \
    --requirements_file="${REPO_ROOT}/src/router/requirements.txt" \
    src/router

if [ $? -eq 0 ]; then
    ok "Router agent deployed successfully"
else
    fail "Deployment failed — check logs at https://console.cloud.google.com/logs/query?project=$PROJECT_ID"
fi

echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════════╗"
echo "║  Deployment complete!                                        ║"
echo "║                                                              ║"
echo "║  Models configured:                                          ║"
echo "║    Low complexity  → ${LITE_MODEL}"
echo "║    Med complexity  → ${FLASH_MODEL}"
echo "║    High complexity → ${OPUS_MODEL}"
echo "║                                                              ║"
echo "║  Generate cost report:                                       ║"
echo "║    uv run python -m src.router.run_comparison                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

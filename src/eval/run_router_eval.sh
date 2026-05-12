#!/usr/bin/env bash
# Router Agent — ADK User Simulator Evaluation
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIOS_DIR="${SCRIPT_DIR}/scenarios"
AGENT_MODULE="src/router"
EVAL_SET_NAME="router_eval_set"

echo "--- Router ADK User Simulator Eval ---"
echo "[1/3] Creating eval set..."
uv run adk eval_set create "${AGENT_MODULE}" "${EVAL_SET_NAME}" 2>/dev/null || true
echo "[2/3] Adding conversation scenarios..."
uv run adk eval_set add_eval_case \
    "${AGENT_MODULE}" "${EVAL_SET_NAME}" \
    --scenarios_file "${SCENARIOS_DIR}/router_scenarios.json" \
    --session_input_file "${SCENARIOS_DIR}/session_input.json"
echo "[3/3] Running evaluation..."
uv run adk eval "${AGENT_MODULE}" \
    --config_file_path "${SCENARIOS_DIR}/router_eval_config.json" \
    "${EVAL_SET_NAME}" "$@"
echo "--- Evaluation complete ---"

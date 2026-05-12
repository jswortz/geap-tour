#!/usr/bin/env bash
# Run ADK user simulator evaluations for each agent.
# Usage: ./src/eval/run_user_sim.sh [agent_module] [scenario_file]
# Default: runs all agents.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCENARIO_DIR="$SCRIPT_DIR/scenarios"
EVAL_CONFIG="$SCENARIO_DIR/eval_config.json"
SESSION_INPUT="$SCENARIO_DIR/session_input.json"
USER_SIM_CONFIG="$SCENARIO_DIR/user_sim_config.json"

AGENTS=(
    "src/agents/coordinator:coordinator_scenarios.json"
    "src/agents/travel_agent:travel_scenarios.json"
    "src/agents/expense_agent:expense_scenarios.json"
    "src/agents/router:router_scenarios.json"
)

run_agent_eval() {
    local agent_module="$1"
    local scenario_file="$2"
    local agent_name
    agent_name=$(basename "$agent_module")
    local eval_set_id="eval_set_${agent_name}_sim"

    echo ""
    echo "================================================================"
    echo "  User Simulator Eval: $agent_name"
    echo "================================================================"

    # Step 1: Create evalset from scenario file
    echo "[1/4] Creating evalset: $eval_set_id"
    adk eval_set create "$agent_module" "$eval_set_id" 2>/dev/null || true

    echo "[2/4] Adding conversation scenarios from $scenario_file"
    adk eval_set add_eval_case "$agent_module" "$eval_set_id" \
        --scenarios_file "$SCENARIO_DIR/$scenario_file" \
        --session_input_file "$SESSION_INPUT"

    # Step 2: Generate additional synthetic scenarios
    echo "[3/4] Generating synthetic scenarios"
    adk eval_set generate_eval_cases "$agent_module" "$eval_set_id" \
        --user_simulation_config_file="$USER_SIM_CONFIG" || echo "  (generation skipped)"

    # Step 3: Run evaluation
    echo "[4/4] Running evaluation with multi-turn metrics"
    adk eval "$agent_module" \
        --config_file_path "$EVAL_CONFIG" \
        "$eval_set_id" \
        --print_detailed_results

    echo ""
    echo "  Done: $agent_name"
}

if [ $# -ge 2 ]; then
    run_agent_eval "$1" "$2"
elif [ $# -eq 1 ]; then
    echo "Usage: $0 [agent_module] [scenario_file]"
    echo "   or: $0  (runs all agents)"
    exit 1
else
    echo "Running user simulator evaluations for all agents..."
    for entry in "${AGENTS[@]}"; do
        IFS=: read -r module scenario <<< "$entry"
        run_agent_eval "$module" "$scenario" || echo "  WARNING: $module eval failed, continuing..."
    done

    echo ""
    echo "================================================================"
    echo "  All user simulator evaluations complete."
    echo "================================================================"
fi

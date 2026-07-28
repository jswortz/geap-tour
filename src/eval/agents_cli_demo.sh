#!/usr/bin/env bash
#
# agents_cli_demo.sh — a safe, live walkthrough of the REAL `agents-cli eval`
# subcommands against the coordinator agent. It demonstrates the Quality
# Flywheel (Evaluate -> Analyze -> Optimize) end to end:
#
#   https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/optimize-agent
#
# Flow:
#   metric list          -> discover out-of-the-box (OOTB) metrics
#   dataset synthesize   -> generate synthetic multi-turn eval scenarios
#   generate             -> run agent inference over eval cases -> traces
#   grade                -> score traces against metrics
#   compare              -> diff two eval result JSON files
#   optimize             -> auto-tune the agent's prompts (GEPA)
#
# Every step is guarded with `|| true` so the whole walkthrough completes even
# when a step needs cloud auth (`agents-cli login`) or a live GCP project.
#
# By default the cloud/long-running steps only print their `--help` (so the
# script is 100% safe to run as a demo). Set RUN_LIVE=1 to actually execute
# them against your project:
#
#   RUN_LIVE=1 bash src/eval/agents_cli_demo.sh src/agents/coordinator
#
# `set -e` is intentionally omitted: this script is tolerant and always runs to
# the end.
set -uo pipefail

AGENT_DIR="${1:-src/agents/coordinator}"
RUN_LIVE="${RUN_LIVE:-0}"          # set to 1 to actually execute cloud/long steps
ARTIFACTS="artifacts/agents_cli_demo"
mkdir -p "$ARTIFACTS" 2>/dev/null || true

DOC_OPTIMIZE="https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/optimize-agent"

# Chained artifact paths for the flywheel.
SYNTH_OUT="$ARTIFACTS/synth_traces.json"        # dataset synthesize -> traces
TRACES_OUT="$ARTIFACTS/traces.json"             # generate -> populated traces
GRADE_DIR="$ARTIFACTS/graded"                   # grade -> eval result JSON(s)
EVAL_RESULT="$GRADE_DIR/eval_result.json"       # analyze/compare input (illustrative)
BASELINE="$ARTIFACTS/baseline_result.json"      # compare BASELINE ...
CANDIDATE="$ARTIFACTS/candidate_result.json"    # compare ... CANDIDATE
# Default dataset scaffolded by `agents-cli create`; override as needed.
DATASET="tests/eval/datasets/basic-dataset.json"

hdr() {
  echo
  echo "================================================================================"
  echo "# $1"
  echo "#   doc: $DOC_OPTIMIZE"
  echo "================================================================================"
}

# run_or_help <label> -- <full command...>
#   Prints the header + the exact real invocation. Executes it when RUN_LIVE=1,
#   otherwise shows the command's `--help` so the demo stays cheap/offline-safe.
#   Always guarded with `|| true`.
run_or_help() {
  local label="$1"; shift
  [ "${1:-}" = "--" ] && shift
  hdr "$label"
  echo "\$ $*"
  if [ "$RUN_LIVE" = "1" ]; then
    "$@" || true
  else
    echo "(RUN_LIVE!=1 -> showing --help instead of executing; set RUN_LIVE=1 to run it live)"
    # Build the subcommand path from the leading non-flag tokens, then show its
    # --help (safe + offline). Works for both 3- and 4-token subcommands.
    local help_cmd=()
    local tok
    for tok in "$@"; do
      case "$tok" in
        -*) break ;;
        *) help_cmd+=("$tok") ;;
      esac
    done
    "${help_cmd[@]}" --help 2>/dev/null || true
  fi
}

# ---------------------------------------------------------------------------
# 0. Preflight — is agents-cli installed?
# ---------------------------------------------------------------------------
if ! command -v agents-cli >/dev/null 2>&1; then
  echo "agents-cli not found on PATH."
  echo
  echo "Install the eval skill/CLI with:"
  echo "  npx skills add https://github.com/google/agents-cli --skill google-agents-cli-eval"
  echo "or install the CLI directly:"
  echo "  uv tool install google-agents-cli   #   or:  pipx install google-agents-cli"
  exit 0
fi

echo "agents-cli: $(command -v agents-cli)"
echo "agent dir:  $AGENT_DIR"
echo "artifacts:  $ARTIFACTS"
echo "RUN_LIVE:   $RUN_LIVE  (set RUN_LIVE=1 to execute cloud/long-running steps)"

# ---------------------------------------------------------------------------
# 1. metric list — discover the out-of-the-box (OOTB) evaluation metrics.
#    Cheap + offline-safe, so we always run it live.
# ---------------------------------------------------------------------------
hdr "agents-cli eval metric list  (discover OOTB metrics)"
echo "\$ agents-cli eval metric list"
agents-cli eval metric list || true

# ---------------------------------------------------------------------------
# 2. dataset synthesize — generate synthetic MULTI-TURN eval scenarios by
#    running the local ADK agent with a model-based user simulator.
#    Needs a local agents-cli-manifest.yaml + `agents-cli login`.
#    Real invocation:
#      agents-cli eval dataset synthesize -n 3 --max-turns 5 \
#        --instruction "Multi-turn travel booking; user changes destination mid-trip" \
#        -o "$SYNTH_OUT"
# ---------------------------------------------------------------------------
run_or_help "agents-cli eval dataset synthesize  (synthesize multi-turn scenarios)" -- \
  agents-cli eval dataset synthesize \
    -n 3 --max-turns 5 \
    --instruction "Multi-turn travel booking where the user changes destination mid-trip" \
    -o "$SYNTH_OUT"

# ---------------------------------------------------------------------------
# 3. generate — run the local ADK agent's inference over eval cases to produce
#    populated traces (agent responses + tool calls) for downstream grading.
#    Real invocation:
#      agents-cli eval generate --dataset "$DATASET" -o "$TRACES_OUT"
# ---------------------------------------------------------------------------
run_or_help "agents-cli eval generate  (run inference over eval cases -> traces)" -- \
  agents-cli eval generate \
    --dataset "$DATASET" \
    -o "$TRACES_OUT"

# ---------------------------------------------------------------------------
# 4. grade — score the populated traces against one or more metrics
#    (LLM-as-judge autoraters run in the Vertex eval service).
#    Real invocation:
#      agents-cli eval grade --traces "$TRACES_OUT" \
#        --metrics final_response_quality,tool_use_quality,safety \
#        --output "$GRADE_DIR"
# ---------------------------------------------------------------------------
run_or_help "agents-cli eval grade  (grade traces against metrics)" -- \
  agents-cli eval grade \
    --traces "$TRACES_OUT" \
    --metrics "final_response_quality,tool_use_quality,safety" \
    --output "$GRADE_DIR"

# ---------------------------------------------------------------------------
# 5. compare — diff two eval result JSON files (BASELINE vs CANDIDATE). This is
#    purely in-process (no cloud), but needs two existing result files.
#    Real invocation:
#      agents-cli eval compare "$BASELINE" "$CANDIDATE"
#    We attempt it live (guarded) only when both files exist; otherwise --help.
# ---------------------------------------------------------------------------
hdr "agents-cli eval compare  (compare two result files: BASELINE vs CANDIDATE)"
if [ -f "$BASELINE" ] && [ -f "$CANDIDATE" ]; then
  echo "\$ agents-cli eval compare $BASELINE $CANDIDATE"
  agents-cli eval compare "$BASELINE" "$CANDIDATE" || true
else
  echo "(baseline/candidate result files not present; showing --help)"
  echo "\$ agents-cli eval compare BASELINE CANDIDATE   # e.g. $BASELINE $CANDIDATE"
  agents-cli eval compare --help 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 7. optimize — auto-tune the agent's instructions with the GEPA framework
#    (runs `adk optimize` under the hood; can take 10-20 minutes).
#    We show --help by default to avoid launching a long optimization run.
#    Real invocation:
#      agents-cli eval optimize --dataset "$DATASET" \
#        --target-metric final_response_quality \
#        --config tests/eval/optimization_config.json
#    (Only executed when RUN_LIVE=1.)
# ---------------------------------------------------------------------------
run_or_help "agents-cli eval optimize  (auto-tune prompts via GEPA)" -- \
  agents-cli eval optimize \
    --dataset "$DATASET" \
    --target-metric final_response_quality \
    --config tests/eval/optimization_config.json

echo
echo "================================================================================"
echo "# Walkthrough complete. Artifacts (if any) under: $ARTIFACTS"
echo "# Re-run with RUN_LIVE=1 (and \`agents-cli login\`) to execute the cloud steps."
echo "================================================================================"

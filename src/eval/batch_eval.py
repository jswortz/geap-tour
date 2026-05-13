"""Offline batch evaluation pipeline for the GEAP coordinator agent.

Runs a comprehensive evaluation against the deployed ADK agent on Vertex AI
Agent Engine using the Gen AI evaluation service. Uses both built-in adaptive
rubric metrics (FINAL_RESPONSE_QUALITY, TOOL_USE_QUALITY, HALLUCINATION, SAFETY)
and a custom policy-compliance metric.

Usage:
    uv run python -m src.eval.batch_eval
    uv run python -m src.eval.batch_eval --agent-id 2479350891879071744
    uv run python -m src.eval.batch_eval --threshold 3.0 --output results.json
"""

import argparse
import json
import sys
import time
from datetime import datetime

import pandas as pd
import vertexai
from vertexai import Client, types

from src.config import GCP_PROJECT_ID, GCP_REGION, GCP_STAGING_BUCKET

# ---------------------------------------------------------------------------
# Default agent reasoning-engine ID (deployed coordinator agent)
# ---------------------------------------------------------------------------
DEFAULT_AGENT_ENGINE_ID = "2479350891879071744"

# ---------------------------------------------------------------------------
# GCS destination for persisted evaluation artifacts
# ---------------------------------------------------------------------------
GCS_EVAL_DEST = f"gs://{GCP_STAGING_BUCKET}/eval-results/"

# ---------------------------------------------------------------------------
# Evaluation dataset — simulated test cases
# ---------------------------------------------------------------------------
# Each test case has a prompt, the category being tested, and expected
# behavioral signals (what tools should fire, what the answer should contain).

EVAL_CASES = [
    # ── Travel: Flight search (happy path) ────────────────────────────────
    {
        "prompt": "Find flights from SFO to JFK on June 15",
        "category": "travel_search",
        "expected_tool": "search_flights",
        "expected_signals": ["SFO", "JFK", "FL001", "FL002"],
        "description": "Basic flight search with known routes in mock DB",
    },
    {
        "prompt": "Search for flights from LAX to Chicago on June 16",
        "category": "travel_search",
        "expected_tool": "search_flights",
        "expected_signals": ["LAX", "ORD", "FL003", "American"],
        "description": "Flight search with city name (should map to ORD)",
    },
    {
        "prompt": "Are there any flights from SFO to Los Angeles on June 15?",
        "category": "travel_search",
        "expected_tool": "search_flights",
        "expected_signals": ["SFO", "LAX", "Southwest", "FL005"],
        "description": "Short-haul domestic flight search",
    },
    # ── Travel: Hotel search (happy path) ──────────────────────────────────
    {
        "prompt": "Search for hotels in New York under $350 per night",
        "category": "travel_search",
        "expected_tool": "search_hotels",
        "expected_signals": ["Grand Hyatt", "Budget Inn"],
        "description": "Hotel search with price filter",
    },
    {
        "prompt": "Find me a hotel in Miami",
        "category": "travel_search",
        "expected_tool": "search_hotels",
        "expected_signals": ["Fontainebleau", "Miami"],
        "description": "Hotel search without price constraint",
    },
    # ── Travel: Booking ────────────────────────────────────────────────────
    {
        "prompt": "Book flight FL001 for Alice Johnson",
        "category": "travel_booking",
        "expected_tool": "book_flight",
        "expected_signals": ["FL001", "Alice Johnson", "confirmed"],
        "description": "Flight booking with valid flight ID",
    },
    {
        "prompt": "Book hotel HT002 for Bob Smith, checkin June 15, checkout June 18",
        "category": "travel_booking",
        "expected_tool": "book_hotel",
        "expected_signals": ["HT002", "Bob Smith"],
        "description": "Hotel booking with dates",
    },
    # ── Travel: Edge cases ─────────────────────────────────────────────────
    {
        "prompt": "Find flights from XYZ to ABC tomorrow",
        "category": "travel_edge",
        "expected_tool": "search_flights",
        "expected_signals": [],
        "description": "Flight search with non-existent airport codes",
    },
    {
        "prompt": "Search hotels in Atlantis under $100",
        "category": "travel_edge",
        "expected_tool": "search_hotels",
        "expected_signals": [],
        "description": "Hotel search for non-existent city",
    },
    # ── Expense: Policy check (within limits) ──────────────────────────────
    {
        "prompt": "Check if a $50 meal expense is within policy",
        "category": "expense_policy",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["within", "75"],
        "description": "Policy check for meal under $75 limit",
    },
    {
        "prompt": "Is a $180 transport expense within corporate policy?",
        "category": "expense_policy",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["within", "200"],
        "description": "Policy check for transport under $200 limit",
    },
    # ── Expense: Policy check (over limit) ─────────────────────────────────
    {
        "prompt": "Check policy for a $500 entertainment expense",
        "category": "expense_over_limit",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["exceeds", "150", "entertainment"],
        "description": "Entertainment expense over $150 limit should be flagged",
    },
    {
        "prompt": "Is a $100 meal expense allowed?",
        "category": "expense_over_limit",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["exceeds", "75", "meal"],
        "description": "Meal expense over $75 limit should be flagged",
    },
    # ── Expense: Submission ────────────────────────────────────────────────
    {
        "prompt": "Submit a $45 meals expense for lunch meeting, user ID EMP001",
        "category": "expense_submit",
        "expected_tool": "submit_expense",
        "expected_signals": ["EMP001", "45", "approved"],
        "description": "Expense submission within policy — should auto-approve",
    },
    {
        "prompt": "Submit a $500 entertainment expense for team event, user ID EMP002",
        "category": "expense_submit_over",
        "expected_tool": "submit_expense",
        "expected_signals": ["EMP002", "pending_review", "exceeds"],
        "description": "Over-limit submission — should flag pending_review",
    },
    # ── Expense: History ───────────────────────────────────────────────────
    {
        "prompt": "Show all expenses for user EMP001",
        "category": "expense_history",
        "expected_tool": "get_user_expenses",
        "expected_signals": ["EMP001"],
        "description": "Expense history retrieval",
    },
    # ── Routing: Multi-intent ──────────────────────────────────────────────
    {
        "prompt": "I need to book a trip to Chicago and submit my last meal receipt for $30",
        "category": "routing_multi",
        "expected_tool": "multiple",
        "expected_signals": ["travel", "expense"],
        "description": "Multi-intent query spanning both sub-agents",
    },
    {
        "prompt": "What hotels are available in London?",
        "category": "routing_travel",
        "expected_tool": "search_hotels",
        "expected_signals": ["London", "Claridge"],
        "description": "Implicit routing to travel sub-agent",
    },
    {
        "prompt": "Can you help me with an expense report?",
        "category": "routing_expense",
        "expected_tool": "none",
        "expected_signals": ["expense"],
        "description": "Routing to expense sub-agent for general inquiry",
    },
    # ── Edge: Unknown category ─────────────────────────────────────────────
    {
        "prompt": "Check policy for $1000 in the 'unknown' category",
        "category": "expense_invalid_category",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["unknown", "valid"],
        "description": "Invalid expense category should return helpful error",
    },
]


# ---------------------------------------------------------------------------
# Custom metric: corporate policy compliance
# ---------------------------------------------------------------------------
POLICY_COMPLIANCE_METRIC = types.LLMMetric(
    name="policy_compliance",
    prompt_template=types.MetricPromptBuilder(
        instruction=(
            "Evaluate whether the agent correctly enforces corporate expense "
            "policies. The policy limits are: meals ($75), transport ($200), "
            "lodging ($400), supplies ($100), entertainment ($150). "
            "If the query is not about expenses, rate based on whether the "
            "agent correctly routes the request."
        ),
        criteria={
            "Policy awareness": "Does the agent mention or check policy limits before taking action?",
            "Accuracy": "Are the policy limits correctly stated and applied?",
            "User guidance": "Does the agent clearly inform the user about policy implications?",
        },
        rating_scores={
            "5": "Proactively checks policy, states correct limits, and provides clear guidance.",
            "4": "Correctly applies policy and informs the user.",
            "3": "Applies policy but explanation is incomplete.",
            "2": "Mentions policy but applies it incorrectly.",
            "1": "Ignores policy entirely or gets limits wrong.",
        },
    ),
)


def _resolve_agent_resource_name(agent_id: str) -> str:
    """Convert a bare engine ID to the full Vertex AI resource name."""
    if agent_id.startswith("projects/"):
        return agent_id
    return (
        f"projects/{GCP_PROJECT_ID}"
        f"/locations/{GCP_REGION}"
        f"/reasoningEngines/{agent_id}"
    )


def _build_agent_info() -> types.evals.AgentInfo:
    """Build AgentInfo manually from known agent structure.

    We construct this directly rather than using AgentInfo.load_from_agent()
    because that method requires an instantiated ADK LlmAgent object, which
    would attempt to connect to the MCP tool servers. For offline evaluation
    we only need the structural metadata.
    """
    return types.evals.AgentInfo(
        name="coordinator_agent",
        root_agent_id="coordinator_agent",
        agents={
            "coordinator_agent": types.evals.AgentConfig(
                agent_id="coordinator_agent",
                agent_type="LlmAgent",
                description="Corporate assistant coordinator that routes requests to travel or expense specialists.",
                instruction=(
                    "You are a corporate assistant coordinator. Route requests to the right specialist: "
                    "flight/hotel search and booking to travel_agent, expense submission and policy checks "
                    "to expense_agent, general travel info via search tools directly."
                ),
                sub_agents=["travel_agent", "expense_agent"],
            ),
            "travel_agent": types.evals.AgentConfig(
                agent_id="travel_agent",
                agent_type="LlmAgent",
                description="Corporate travel assistant for searching and booking flights and hotels.",
                instruction=(
                    "You are a corporate travel assistant. Search for and book flights and hotels. "
                    "Use search tools to find options, present them clearly, and use booking tools to confirm."
                ),
                sub_agents=[],
            ),
            "expense_agent": types.evals.AgentConfig(
                agent_id="expense_agent",
                agent_type="LlmAgent",
                description="Corporate expense management assistant for submitting expenses and checking policies.",
                instruction=(
                    "You are a corporate expense management assistant. Policy limits: "
                    "meals ($75), transport ($200), lodging ($400), supplies ($100), entertainment ($150). "
                    "Check policy first, submit expenses, and view history."
                ),
                sub_agents=[],
            ),
        },
    )


def build_eval_dataset() -> pd.DataFrame:
    """Build the evaluation dataset as a Pandas DataFrame."""
    session_inputs = types.evals.SessionInput(
        user_id="eval-batch-user",
        state={},
    )

    rows = []
    for case in EVAL_CASES:
        rows.append({
            "prompt": case["prompt"],
            "session_inputs": session_inputs,
            # Metadata columns for post-hoc analysis (not used by the eval API)
            "eval_category": case["category"],
            "expected_tool": case["expected_tool"],
            "expected_signals": json.dumps(case["expected_signals"]),
            "case_description": case["description"],
        })

    return pd.DataFrame(rows)


def run_batch_eval(
    agent_id: str = DEFAULT_AGENT_ENGINE_ID,
    score_threshold: float = 3.0,
    output_path: str | None = None,
) -> dict:
    """Run the full offline batch evaluation pipeline.

    Steps:
        1. Initialize Vertex AI and GenAI client
        2. Build evaluation dataset from simulated test cases
        3. Run inference against the deployed agent
        4. Evaluate with adaptive rubric metrics + custom metric
        5. Output structured results

    Returns:
        dict with summary metrics and per-item scores.
    """
    run_id = f"batch_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    agent_resource_name = _resolve_agent_resource_name(agent_id)

    print(f"{'=' * 60}")
    print(f"GEAP Batch Evaluation Pipeline")
    print(f"{'=' * 60}")
    print(f"  Run ID:      {run_id}")
    print(f"  Agent:       {agent_resource_name}")
    print(f"  Test cases:  {len(EVAL_CASES)}")
    print(f"  Threshold:   {score_threshold}")
    print(f"  GCS output:  {GCS_EVAL_DEST}")
    print()

    # --- Step 1: Initialize ---
    print("[1/4] Initializing Vertex AI and GenAI client...")
    vertexai.init(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
        staging_bucket=f"gs://{GCP_STAGING_BUCKET}",
    )
    client = Client(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )
    print("  Done.")

    # --- Step 2: Build dataset ---
    print(f"[2/4] Building evaluation dataset ({len(EVAL_CASES)} test cases)...")
    eval_df = build_eval_dataset()

    categories = eval_df["eval_category"].value_counts()
    for cat, count in categories.items():
        print(f"  {cat}: {count} cases")
    print()

    # --- Step 3: Run inference ---
    print("[3/4] Running agent inference (this may take several minutes)...")
    t0 = time.time()
    inference_result = client.evals.run_inference(
        agent=agent_resource_name,
        src=eval_df,
    )
    elapsed = time.time() - t0
    print(f"  Inference complete in {elapsed:.1f}s")
    print()

    # --- Step 4: Evaluate ---
    print("[4/4] Running evaluation with metrics...")
    print("  Metrics:")
    print("    - FINAL_RESPONSE_QUALITY (adaptive rubric)")
    print("    - TOOL_USE_QUALITY      (adaptive rubric)")
    print("    - HALLUCINATION         (adaptive rubric)")
    print("    - SAFETY                (static rubric)")
    print("    - policy_compliance     (custom LLM metric)")

    # Build agent_info from known structure (avoids needing MCP connections)
    agent_info = _build_agent_info()

    evaluation_run = client.evals.create_evaluation_run(
        dataset=inference_result,
        agent_info=agent_info,
        agent=agent_resource_name,
        metrics=[
            types.RubricMetric.FINAL_RESPONSE_QUALITY,
            types.RubricMetric.TOOL_USE_QUALITY,
            types.RubricMetric.HALLUCINATION,
            types.RubricMetric.SAFETY,
            POLICY_COMPLIANCE_METRIC,
        ],
        dest=GCS_EVAL_DEST,
    )

    print(f"  Eval run: {evaluation_run.name}")
    print("  Waiting for evaluation to complete", end="", flush=True)
    while True:
        evaluation_run = client.evals.get_evaluation_run(
            name=evaluation_run.name,
        )
        state = str(getattr(evaluation_run, "state", ""))
        if "SUCCEEDED" in state or "FAILED" in state or "CANCELLED" in state:
            break
        print(".", end="", flush=True)
        time.sleep(15)
    print(f" {state}")

    if "FAILED" in state:
        err = getattr(evaluation_run, "error", None)
        print(f"  ERROR: Evaluation failed: {err}")
        sys.exit(2)

    # Retrieve full results with per-item scores
    evaluation_run = client.evals.get_evaluation_run(
        name=evaluation_run.name,
        include_evaluation_items=True,
    )

    # --- Build structured output ---
    results = _build_results(
        run_id=run_id,
        agent_resource_name=agent_resource_name,
        evaluation_run=evaluation_run,
        score_threshold=score_threshold,
        elapsed_seconds=elapsed,
    )

    # --- Print summary ---
    _print_summary(results)

    # --- Write output ---
    if output_path is None:
        output_path = f"eval_results_{run_id}.json"

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {output_path}")

    return results


def _build_results(
    run_id: str,
    agent_resource_name: str,
    evaluation_run,
    score_threshold: float,
    elapsed_seconds: float,
) -> dict:
    """Extract structured results from the EvaluationRun object."""
    raw_metrics: dict = {}
    total_items = 0
    failed_items = 0

    try:
        run_results = getattr(evaluation_run, "evaluation_run_results", None)
        if run_results:
            sm = getattr(run_results, "summary_metrics", None)
            if sm:
                total_items = getattr(sm, "total_items", 0) or 0
                failed_items = getattr(sm, "failed_items", 0) or 0
                nested = getattr(sm, "metrics", None)
                if nested:
                    raw_metrics = dict(nested) if not isinstance(nested, dict) else nested
    except Exception:
        pass

    # Group per-metric AVERAGE scores (e.g. "coordinator_agent/safety_v1/AVERAGE")
    metric_averages: dict[str, float] = {}
    for key, value in raw_metrics.items():
        if "/AVERAGE" in key:
            metric_name = key.rsplit("/AVERAGE", 1)[0]
            metric_averages[metric_name] = float(value)

    # Safety uses binary 0/1 scale; rubric metrics use 1-5 scale
    BINARY_METRICS = {"safety_v1"}

    all_pass = True
    metric_results = {}
    for metric_name, avg in metric_averages.items():
        is_binary = any(bm in metric_name for bm in BINARY_METRICS)
        thresh = 0.5 if is_binary else score_threshold
        passed = avg >= thresh
        if not passed:
            all_pass = False
        metric_results[metric_name] = {
            "score": avg,
            "threshold": thresh,
            "passed": passed,
        }

    return {
        "run_id": run_id,
        "agent": agent_resource_name,
        "timestamp": datetime.now().isoformat(),
        "inference_seconds": round(elapsed_seconds, 1),
        "test_case_count": len(EVAL_CASES),
        "score_threshold": score_threshold,
        "all_passed": all_pass,
        "total_items": total_items,
        "failed_items": failed_items,
        "metrics": metric_results,
        "summary_raw": raw_metrics,
        "evaluation_run_name": getattr(evaluation_run, "name", None),
    }


def _print_summary(results: dict) -> None:
    """Print a human-readable summary of the evaluation results."""
    print()
    print(f"{'=' * 60}")
    print("EVALUATION RESULTS")
    print(f"{'=' * 60}")
    print(f"  Run:         {results['run_id']}")
    print(f"  Agent:       {results['agent']}")
    print(f"  Test cases:  {results['test_case_count']}")
    print(f"  Inference:   {results['inference_seconds']}s")
    print(f"  Items OK:    {results['total_items'] - results['failed_items']}/{results['total_items']}")
    print()

    if not results["metrics"]:
        print("  No metric averages found in summary.")
    else:
        print("  Metric Scores (AVERAGE):")
        for metric, detail in sorted(results["metrics"].items()):
            status = "PASS" if detail["passed"] else "FAIL"
            score = detail["score"]
            thresh = detail["threshold"]
            marker = "" if detail["passed"] else "  <<<"
            print(f"    {metric:50s} {score:5.2f} / {thresh:.1f}  [{status}]{marker}")

    overall = "PASS" if results["all_passed"] else "FAIL"
    print()
    print(f"  Overall: {overall}")
    print(f"  Eval run: {results.get('evaluation_run_name', 'N/A')}")
    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(
        description="Run offline batch evaluation against the deployed GEAP coordinator agent.",
    )
    parser.add_argument(
        "--agent-id",
        default=DEFAULT_AGENT_ENGINE_ID,
        help=(
            "Agent Engine reasoning engine ID or full resource name. "
            f"Default: {DEFAULT_AGENT_ENGINE_ID}"
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=3.0,
        help="Minimum average score to pass (1-5 scale). Default: 3.0",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path. Default: eval_results_<run_id>.json",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="Print the evaluation dataset and exit without running.",
    )
    args = parser.parse_args()

    if args.list_cases:
        print(f"Evaluation Dataset ({len(EVAL_CASES)} test cases):")
        print(f"{'─' * 80}")
        for i, case in enumerate(EVAL_CASES, 1):
            print(f"  [{i:2d}] {case['category']:25s} | {case['prompt']}")
            print(f"       Expected tool: {case['expected_tool']}")
            print(f"       Signals: {case['expected_signals']}")
            print()
        return

    results = run_batch_eval(
        agent_id=args.agent_id,
        score_threshold=args.threshold,
        output_path=args.output,
    )

    # Exit with non-zero if any metric failed threshold
    if not results["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

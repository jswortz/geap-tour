"""Simulated evaluation — generate synthetic scenarios and run agent inference for CI/CD.

Supports per-agent evaluation with conversation scenarios,
ADK user simulator with configurable max turns, and multi-turn metrics.

Usage:
    uv run python -m src.eval.simulated_eval --agent-id 8296365537139621888 --agent-name coordinator_agent
    uv run python -m src.eval.simulated_eval --agent-id 4709107696450666496 --agent-name router_agent --scenario-count 10
"""

def _patch_evals_extra_fields():
    """Patch ConversationTurn to accept extra fields from agent engine responses.

    The Vertex AI API returns turn data with fields (model_version, content,
    id, timestamp, author, actions, invocation_id, etc.) not defined in the
    SDK's ConversationTurn pydantic model. The base class sets extra='forbid',
    causing ValidationError. Fix: set extra='ignore' so unknown fields are
    accepted during parsing but excluded from model_dump().

    Note: turn_index injection (Bug 2) was fixed in SDK 1.153.0.
    Tracked upstream: https://github.com/googleapis/python-aiplatform/issues/6785
    """
    from vertexai._genai.types import evals as evals_types

    ct = evals_types.ConversationTurn
    ct.model_config["extra"] = "ignore"
    ct.__pydantic_complete__ = False
    ct.model_rebuild(force=True)
    evals_types.AgentData.__pydantic_complete__ = False
    evals_types.AgentData.model_rebuild(force=True)


GENERATION_INSTRUCTIONS = {
    "coordinator_agent": (
        "Generate diverse scenarios covering: flight search, hotel booking, "
        "expense submission within policy, over-limit expenses, booking cancellation, "
        "and multi-step travel planning with expense management."
    ),
    "travel_agent": (
        "Generate diverse scenarios covering: flight search by route and date, "
        "hotel search with price filters, booking confirmation flows, "
        "comparison shopping between options, and edge cases with invalid airports."
    ),
    "expense_agent": (
        "Generate diverse scenarios covering: expense policy checks for all categories, "
        "within-limit and over-limit submissions, expense history review, "
        "invalid category handling, and multi-expense submission flows."
    ),
    "router_agent": (
        "Generate scenarios with varying complexity levels: "
        "simple single-intent lookups (low complexity), moderate reasoning and "
        "multi-step queries (medium complexity), and complex cross-domain "
        "planning tasks requiring deep analysis (high complexity)."
    ),
}


def run_simulated_eval(
    agent_resource_name: str,
    agent_name: str = "coordinator_agent",
    scenario_count: int = 10,
    max_turns: int = 5,
    score_threshold: float = 3.0,
) -> bool:
    """Run simulated evaluation. Returns True if all metrics pass threshold."""
    _patch_evals_extra_fields()

    import vertexai
    from vertexai import Client, types
    from src.config import GCP_PROJECT_ID, GCP_REGION, SIMULATOR_MODEL
    from src.eval.agent_eval_configs import build_agent_info

    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
    client = Client(project=GCP_PROJECT_ID, location=GCP_REGION)
    from src.config import disable_pyopenssl
    disable_pyopenssl()

    eval_metrics = [
        types.RubricMetric.MULTI_TURN_TRAJECTORY_QUALITY,
    ]

    agent_info = build_agent_info(agent_name)

    generation_instruction = GENERATION_INSTRUCTIONS.get(
        agent_name, GENERATION_INSTRUCTIONS["coordinator_agent"]
    )

    print(f"[1/3] Generating {scenario_count} conversation scenarios for {agent_name}...")
    eval_dataset = client.evals.generate_conversation_scenarios(
        agent_info=agent_info,
        config={
            "count": scenario_count,
            "generation_instruction": generation_instruction,
        },
        allow_cross_region_model=True,
    )
    print("  Generated scenarios")

    print(f"[2/3] Running inference (max {max_turns} turns per scenario)...")
    eval_dataset_with_traces = client.evals.run_inference(
        agent=agent_resource_name,
        src=eval_dataset,
        config={
            "user_simulator_config": {
                "max_turn": max_turns,
                "model_name": SIMULATOR_MODEL,
            },
        },
    )
    print("  Inference complete")

    import time
    from src.config import GCP_STAGING_BUCKET
    GCS_EVAL_DEST = f"gs://{GCP_STAGING_BUCKET}/eval-results/"
    MAX_POLL_SECONDS = 600

    print("[3/3] Creating evaluation run...")
    evaluation_run = client.evals.create_evaluation_run(
        dataset=eval_dataset_with_traces,
        agent=agent_resource_name,
        metrics=eval_metrics,
        dest=GCS_EVAL_DEST,
    )

    print(f"  Eval run: {evaluation_run.name}")
    print(f"  Polling", end="", flush=True)
    poll_start = time.time()
    while time.time() - poll_start < MAX_POLL_SECONDS:
        evaluation_run = client.evals.get_evaluation_run(name=evaluation_run.name)
        state = str(getattr(evaluation_run, "state", ""))
        if "SUCCEEDED" in state or "FAILED" in state or "CANCELLED" in state:
            break
        print(".", end="", flush=True)
        time.sleep(15)
    print(f" {state}")

    if "FAILED" in state:
        err = getattr(evaluation_run, "error", None)
        print(f"  ERROR: {err}")
        return False

    evaluation_run = client.evals.get_evaluation_run(
        name=evaluation_run.name,
        include_evaluation_items=True,
    )

    raw_metrics: dict = {}
    try:
        run_results = getattr(evaluation_run, "evaluation_run_results", None)
        if run_results:
            sm = getattr(run_results, "summary_metrics", None)
            if sm:
                nested = getattr(sm, "metrics", None)
                if nested:
                    raw_metrics = dict(nested) if not isinstance(nested, dict) else nested
    except Exception as e:
        print(f"  Warning: could not extract summary metrics: {e}")

    normalized_threshold = score_threshold / 5.0
    all_pass = True
    metric_results = {}

    print(f"\n=== Simulated Evaluation Results ({agent_name}) ===")
    for key, value in sorted(raw_metrics.items()):
        if "/AVERAGE" in key:
            avg = float(value)
            passed = avg >= normalized_threshold
            if not passed:
                all_pass = False
            status = "PASS" if passed else "FAIL"
            metric_name = key.rsplit("/AVERAGE", 1)[0]
            metric_results[metric_name] = {"score": avg, "threshold": normalized_threshold, "passed": passed}
            print(f"  {metric_name:50s} {avg:.2f} / {normalized_threshold:.2f}  [{status}]")

    if not raw_metrics:
        print("  (no metrics returned — check console for results)")
        print(f"  Eval run: {getattr(evaluation_run, 'name', 'N/A')}")

    import json
    from datetime import datetime
    from pathlib import Path
    from src.config import EVAL_OUTPUT_DIR

    results = {
        "type": "simulated_eval",
        "agent_name": agent_name,
        "agent_engine": agent_resource_name,
        "evaluation_run": getattr(evaluation_run, "name", None),
        "timestamp": datetime.now().isoformat(),
        "scenario_count": scenario_count,
        "max_turns": max_turns,
        "score_threshold": score_threshold,
        "all_passed": all_pass,
        "metrics": metric_results,
    }

    output_dir = Path(EVAL_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"simulated_eval_{agent_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {output_path}")

    return all_pass


if __name__ == "__main__":
    import argparse
    import sys

    from src.config import AGENT_ENGINE_ID

    parser = argparse.ArgumentParser(
        description="Run simulated multi-turn evaluation with LLM-backed user simulator.",
    )
    parser.add_argument(
        "--agent-id",
        default=AGENT_ENGINE_ID,
        help=f"Agent Engine ID or full resource name. Default: {AGENT_ENGINE_ID}",
    )
    parser.add_argument(
        "--agent-name",
        default="coordinator_agent",
        help="Agent config to use (coordinator_agent, travel_agent, expense_agent, router_agent). Default: coordinator_agent",
    )
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=5,
        help="Number of conversation scenarios to generate. Default: 5",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=5,
        help="Max conversation turns per scenario. Default: 5",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=3.0,
        help="Minimum score to pass (1-5). Default: 3.0",
    )
    args = parser.parse_args()

    resource = args.agent_id
    if not resource.startswith("projects/"):
        from src.config import GCP_PROJECT_ID, GCP_REGION
        resource = f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/reasoningEngines/{resource}"

    passed = run_simulated_eval(
        resource,
        agent_name=args.agent_name,
        scenario_count=args.scenario_count,
        max_turns=args.max_turns,
        score_threshold=args.threshold,
    )
    sys.exit(0 if passed else 1)

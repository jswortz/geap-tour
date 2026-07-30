"""Multi-agent batch evaluation — runs batch evals per agent with consolidated output.

Extends the single-agent batch_eval.py pattern to evaluate coordinator, travel,
expense, and router agents independently with agent-appropriate metrics.

Usage:
    uv run python -m src.eval.multi_agent_batch_eval
    uv run python -m src.eval.multi_agent_batch_eval --agents coordinator_agent,travel_agent
    uv run python -m src.eval.multi_agent_batch_eval --list-cases
    uv run python -m src.eval.multi_agent_batch_eval --threshold 3.5
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import vertexai
from vertexai import Client, types
from google.genai import types as g_types

from src.config import (
    GCP_PROJECT_ID,
    GCP_REGION,
    GCP_STAGING_BUCKET,
    AGENT_ENGINE_ID,
    EVAL_OUTPUT_DIR,
)
from src.eval.agent_eval_configs import (
    ALL_AGENTS,
    get_eval_cases,
)

def _resolve_agent_resource_name(agent_id: str) -> str:
    if agent_id.startswith("projects/"):
        return agent_id
    return f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/reasoningEngines/{agent_id}"


def _run_single_agent_eval(
    client: Client,
    agent_name: str,
    agent_resource_name: str,
    score_threshold: float,
) -> dict:
    """Run batch (regression) evaluation for a single agent.

    Inference is run explicitly (``agent_engines.stream_query``) and scored with
    ``client.evals.evaluate`` using prebuilt ``RubricMetric`` autoraters. This avoids two
    google-cloud-aiplatform 1.162 bugs that otherwise make this eval report FAILED even when the
    agent answers correctly: ``run_inference`` rejects Agent Engine event fields
    (``AgentData`` is ``extra="forbid"``), and the managed ``create_evaluation_run`` result can't be
    loaded client-side (``EvaluationItemResult`` validation errors). See ``src/eval/one_time_eval.py``.
    No monkeypatching.
    """
    from vertexai import agent_engines
    from src.eval.one_time_eval import METRICS, _agent_response_text

    cases = get_eval_cases(agent_name)
    print(f"\n{'─' * 60}")
    print(f"  Agent: {agent_name} ({len(cases)} test cases)")
    print(f"  Metrics: {', '.join(getattr(m, 'name', str(m)) for m in METRICS)}")
    print(f"{'─' * 60}")

    print("  Running inference (querying the deployed agent)...")
    t0 = time.time()
    agent_engine = agent_engines.get(agent_resource_name)
    eval_cases = []
    for case in cases:
        prompt = case["prompt"]
        try:
            answer = _agent_response_text(agent_engine, prompt) or "(agent returned no text)"
        except Exception as e:  # noqa: BLE001
            answer = f"(inference error: {e})"
        eval_cases.append(types.EvalCase(
            prompt=g_types.Content(parts=[g_types.Part.from_text(text=prompt)], role="user"),
            responses=[types.ResponseCandidate(
                response=g_types.Content(parts=[g_types.Part.from_text(text=answer)], role="model"))],
        ))
    elapsed = time.time() - t0
    print(f"  Inference complete in {elapsed:.1f}s")

    print("  Running evaluation...")
    eval_result = client.evals.evaluate(
        dataset=types.EvaluationDataset(eval_cases=eval_cases),
        metrics=METRICS,
    )

    metric_results = {}
    all_pass = True
    for r in (eval_result.summary_metrics or []):
        avg = r.mean_score if r.mean_score is not None else 0.0
        avg_scaled = avg * 5.0 if avg <= 1.0 else avg  # SDK returns 0-1; rescale to the 1-5 threshold
        passed = avg_scaled >= score_threshold
        if not passed:
            all_pass = False
        metric_results[r.metric_name] = {
            "score": round(avg_scaled, 3),
            "threshold": score_threshold,
            "passed": passed,
            "errors": getattr(r, "num_cases_error", 0),
        }

    print(f"\n  Results for {agent_name} ({len(cases)} items):")
    for mname, detail in sorted(metric_results.items()):
        status = "PASS" if detail["passed"] else "FAIL"
        marker = "" if detail["passed"] else "  <<<"
        print(f"    {mname:40s} {detail['score']:.2f} / {detail['threshold']:.2f}  [{status}]{marker}")
    if not metric_results:
        print("    (no metrics returned)")

    return {
        "agent": agent_name,
        "status": "PASSED" if all_pass else "FAILED",
        "test_cases": len(cases),
        "inference_seconds": round(elapsed, 1),
        "metrics": metric_results,
    }


def run_multi_agent_batch_eval(
    agents: list[str] | None = None,
    agent_id: str = AGENT_ENGINE_ID,
    score_threshold: float = 3.0,
    output_path: str | None = None,
) -> dict:
    """Run batch evaluations for multiple agents."""
    if agents is None:
        agents = ALL_AGENTS

    run_id = f"multi_agent_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    agent_resource_name = _resolve_agent_resource_name(agent_id)

    print(f"{'=' * 60}")
    print("MULTI-AGENT BATCH EVALUATION")
    print(f"{'=' * 60}")
    print(f"  Run ID:    {run_id}")
    print(f"  Agent:     {agent_resource_name}")
    print(f"  Agents:    {', '.join(agents)}")
    print(f"  Threshold: {score_threshold}")

    # Initialize
    vertexai.init(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
        staging_bucket=f"gs://{GCP_STAGING_BUCKET}",
    )
    client = Client(project=GCP_PROJECT_ID, location=GCP_REGION)

    # Run evals per agent
    agent_results = {}
    for agent_name in agents:
        try:
            result = _run_single_agent_eval(
                client=client,
                agent_name=agent_name,
                agent_resource_name=agent_resource_name,
                score_threshold=score_threshold,
            )
            agent_results[agent_name] = result
        except Exception as e:
            print(f"\n  ERROR evaluating {agent_name}: {e}")
            agent_results[agent_name] = {
                "agent": agent_name,
                "status": "ERROR",
                "error": str(e),
            }

    # Cross-agent summary
    total_cases = sum(r.get("test_cases", 0) for r in agent_results.values())
    agents_passed = sum(1 for r in agent_results.values() if r.get("status") == "PASSED")
    all_passed = agents_passed == len(agents)

    results = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "agent_engine": agent_resource_name,
        "score_threshold": score_threshold,
        "total_agents": len(agents),
        "agents_passed": agents_passed,
        "all_passed": all_passed,
        "total_test_cases": total_cases,
        "agents": agent_results,
    }

    # Print overall summary
    print(f"\n{'=' * 60}")
    print("OVERALL RESULTS")
    print(f"{'=' * 60}")
    for name, r in agent_results.items():
        status = r.get("status", "UNKNOWN")
        cases = r.get("test_cases", 0)
        metrics_count = len(r.get("metrics", {}))
        print(f"  {name:25s} {status:8s}  ({cases} cases, {metrics_count} metrics)")
    print(f"\n  Overall: {'PASS' if all_passed else 'FAIL'} ({agents_passed}/{len(agents)} agents)")
    print(f"{'=' * 60}")

    # Save results
    output_dir = Path(EVAL_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = str(output_dir / f"batch_results_{run_id}.json")

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {output_path}")

    return results


def list_all_cases():
    """Print all test cases organized by agent."""
    for agent_name in ALL_AGENTS:
        cases = get_eval_cases(agent_name)
        print(f"\n{'═' * 60}")
        print(f" {agent_name} ({len(cases)} test cases)")
        print(f"{'═' * 60}")
        for i, case in enumerate(cases, 1):
            print(f"  [{i:2d}] {case['category']:25s} | {case['prompt'][:70]}")
            print(f"       Tool: {case['expected_tool']}  Signals: {case['expected_signals']}")
            if "expected_complexity" in case:
                print(f"       Complexity: {case['expected_complexity']}")


def main():
    parser = argparse.ArgumentParser(
        description="Run batch evaluations across multiple agents.",
    )
    parser.add_argument(
        "--agents",
        type=str,
        default=None,
        help=f"Comma-separated agent names. Default: all ({','.join(ALL_AGENTS)})",
    )
    parser.add_argument(
        "--agent-id",
        default=AGENT_ENGINE_ID,
        help=f"Agent Engine ID. Default: {AGENT_ENGINE_ID}",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=3.0,
        help="Minimum score to pass (1-5). Default: 3.0",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path.",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="Print all test cases and exit.",
    )
    args = parser.parse_args()

    if args.list_cases:
        list_all_cases()
        return

    agents = args.agents.split(",") if args.agents else None

    results = run_multi_agent_batch_eval(
        agents=agents,
        agent_id=args.agent_id,
        score_threshold=args.threshold,
        output_path=args.output,
    )

    if not results["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

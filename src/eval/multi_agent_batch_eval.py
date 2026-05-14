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

import pandas as pd
import vertexai
from vertexai import Client, types

from src.config import (
    GCP_PROJECT_ID,
    GCP_REGION,
    GCP_STAGING_BUCKET,
    AGENT_ENGINE_ID,
    EVAL_OUTPUT_DIR,
)
from src.eval.agent_eval_configs import (
    ALL_AGENTS,
    build_agent_info,
    get_eval_cases,
    get_metrics,
)

GCS_EVAL_DEST = f"gs://{GCP_STAGING_BUCKET}/eval-results/"
MAX_POLL_SECONDS = 600


def _resolve_agent_resource_name(agent_id: str) -> str:
    if agent_id.startswith("projects/"):
        return agent_id
    return f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/reasoningEngines/{agent_id}"


def _build_eval_dataset(cases: list[dict]) -> pd.DataFrame:
    session_inputs = types.evals.SessionInput(user_id="eval-batch-user", state={})
    rows = []
    for case in cases:
        rows.append({
            "prompt": case["prompt"],
            "session_inputs": session_inputs,
            "eval_category": case["category"],
            "expected_tool": case["expected_tool"],
            "expected_signals": json.dumps(case["expected_signals"]),
            "case_description": case["description"],
        })
    return pd.DataFrame(rows)


def _run_single_agent_eval(
    client: Client,
    agent_name: str,
    agent_resource_name: str,
    score_threshold: float,
) -> dict:
    """Run batch evaluation for a single agent."""
    cases = get_eval_cases(agent_name)
    agent_info = build_agent_info(agent_name)
    metrics = get_metrics(agent_name)

    print(f"\n{'─' * 60}")
    print(f"  Agent: {agent_name} ({len(cases)} test cases)")
    print(f"  Metrics: {', '.join(getattr(m, 'name', str(m)) for m in metrics)}")
    print(f"{'─' * 60}")

    eval_df = _build_eval_dataset(cases)

    # Run inference
    print(f"  Running inference...")
    t0 = time.time()
    inference_result = client.evals.run_inference(
        agent=agent_resource_name,
        src=eval_df,
    )
    elapsed = time.time() - t0
    print(f"  Inference complete in {elapsed:.1f}s")

    # Run evaluation
    print(f"  Running evaluation...")
    evaluation_run = client.evals.create_evaluation_run(
        dataset=inference_result,
        agent=agent_resource_name,
        metrics=metrics,
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
        return {
            "agent": agent_name,
            "status": "FAILED",
            "error": str(err),
            "test_cases": len(cases),
        }

    # Retrieve full results
    evaluation_run = client.evals.get_evaluation_run(
        name=evaluation_run.name,
        include_evaluation_items=True,
    )

    # Extract metrics
    summary = {}
    try:
        run_results = getattr(evaluation_run, "evaluation_run_results", None)
        if run_results:
            raw_summary = getattr(run_results, "summary_metrics", None)
            if raw_summary:
                summary = dict(raw_summary) if not isinstance(raw_summary, dict) else raw_summary
    except Exception as e:
        print(f"  Warning: could not extract summary metrics: {e}")
        print(f"  Raw evaluation_run attrs: {[a for a in dir(evaluation_run) if not a.startswith('_')]}")

    # Per-metric pass/fail
    metric_results = {}
    all_pass = True
    for metric_name, value in summary.items():
        if isinstance(value, dict):
            avg = value.get("mean", value.get("average", 0))
        elif isinstance(value, (int, float)):
            avg = value
        else:
            avg = 0
        passed = avg >= score_threshold
        if not passed:
            all_pass = False
        metric_results[metric_name] = {
            "score": avg,
            "threshold": score_threshold,
            "passed": passed,
        }

    # Per-item details
    items = []
    try:
        if hasattr(evaluation_run, "evaluation_items"):
            for item in evaluation_run.evaluation_items or []:
                items.append(dict(item) if not isinstance(item, dict) else item)
    except Exception:
        pass

    # Print agent summary
    print(f"\n  Results for {agent_name}:")
    for mname, detail in metric_results.items():
        status = "PASS" if detail["passed"] else "FAIL"
        print(f"    {mname:35s} {detail['score']:5.2f} / {score_threshold:.1f}  [{status}]")
    if not metric_results:
        print(f"    (no metrics returned — check eval run: {getattr(evaluation_run, 'name', 'N/A')})")

    return {
        "agent": agent_name,
        "status": "PASSED" if all_pass else "FAILED",
        "test_cases": len(cases),
        "inference_seconds": round(elapsed, 1),
        "metrics": metric_results,
        "summary_raw": summary,
        "evaluation_run_name": getattr(evaluation_run, "name", None),
        "item_count": len(items),
        "items": items,
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
    print(f"MULTI-AGENT BATCH EVALUATION")
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
    print(f"OVERALL RESULTS")
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

"""Cross-model complexity experiment — test all models on all complexity tiers.

Runs 5 models × 3 tiers = 15 eval runs to measure how each model handles
queries above and below its intended complexity level.

Usage:
    uv run python -m src.eval.cross_model_experiment
    uv run python -m src.eval.cross_model_experiment --tier low
    uv run python -m src.eval.cross_model_experiment --agent lite_agent
    uv run python -m src.eval.cross_model_experiment --tier high --agent opus_agent
"""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import vertexai
from vertexai import Client, types

from src.config import GCP_PROJECT_ID, GCP_REGION, GCP_STAGING_BUCKET, EVAL_OUTPUT_DIR
from src.eval.agent_eval_configs import (
    TIER_EVAL_CASES,
    STANDALONE_AGENTS,
    build_agent_info,
    get_metrics,
)

GCS_EVAL_DEST = f"gs://{GCP_STAGING_BUCKET}/eval-results/"
MAX_POLL_SECONDS = 1200

EXPERIMENT_AGENTS = {
    "lite_agent": os.environ.get("LITE_ENGINE_ID", ""),
    "flash_agent": os.environ.get("FLASH_ENGINE_ID", ""),
    "pro_agent": os.environ.get("PRO_ENGINE_ID", ""),
    "sonnet_agent": os.environ.get("SONNET_ENGINE_ID", ""),
    "opus_agent": os.environ.get("OPUS_ENGINE_ID", ""),
}

TIERS = ["low", "medium", "high"]


def _resolve_agent_resource(engine_id: str) -> str:
    if engine_id.startswith("projects/"):
        return engine_id
    return f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/reasoningEngines/{engine_id}"


def _build_eval_dataset(cases: list[dict]) -> pd.DataFrame:
    session_inputs = types.evals.SessionInput(user_id="experiment-user", state={})
    rows = []
    for case in cases:
        row = {
            "prompt": case["prompt"],
            "session_inputs": session_inputs,
            "eval_category": case["category"],
            "expected_tool": case["expected_tool"],
            "expected_signals": json.dumps(case["expected_signals"]),
            "case_description": case["description"],
        }
        if "reference" in case:
            row["reference"] = case["reference"]
        rows.append(row)
    return pd.DataFrame(rows)


def run_single_eval(
    client: Client,
    agent_name: str,
    engine_id: str,
    tier: str,
    cases: list[dict],
    metrics: list,
) -> dict:
    """Run eval for one agent on one tier. Returns results dict."""
    agent_resource = _resolve_agent_resource(engine_id)
    eval_df = _build_eval_dataset(cases)

    print(f"  [{agent_name} × {tier}] Inference ({len(cases)} cases)...", end="", flush=True)
    t0 = time.time()
    inference_result = client.evals.run_inference(
        agent=agent_resource,
        src=eval_df,
    )
    elapsed = time.time() - t0
    print(f" {elapsed:.0f}s")

    print(f"  [{agent_name} × {tier}] Evaluating...", end="", flush=True)
    evaluation_run = client.evals.create_evaluation_run(
        dataset=inference_result,
        agent=agent_resource,
        metrics=metrics,
        dest=GCS_EVAL_DEST,
    )

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
        return {"agent": agent_name, "tier": tier, "status": "FAILED", "metrics": {}}

    evaluation_run = client.evals.get_evaluation_run(
        name=evaluation_run.name, include_evaluation_items=True,
    )

    raw_metrics = {}
    try:
        run_results = getattr(evaluation_run, "evaluation_run_results", None)
        if run_results:
            sm = getattr(run_results, "summary_metrics", None)
            if sm:
                nested = getattr(sm, "metrics", None)
                if nested:
                    raw_metrics = dict(nested) if not isinstance(nested, dict) else nested
    except Exception as e:
        print(f"    Warning: {e}")

    normalized_threshold = 0.10
    metric_results = {}
    for key, value in raw_metrics.items():
        if "/AVERAGE" in key:
            avg = float(value)
            metric_name = key.rsplit("/AVERAGE", 1)[0]
            metric_results[metric_name] = avg

    return {
        "agent": agent_name,
        "tier": tier,
        "status": "SUCCEEDED",
        "metrics": metric_results,
        "inference_seconds": round(elapsed, 1),
        "test_cases": len(cases),
        "evaluation_run": getattr(evaluation_run, "name", None),
    }


def run_experiment(
    tiers: list[str] | None = None,
    agents: list[str] | None = None,
) -> dict:
    """Run cross-model experiment. Returns consolidated results."""
    if tiers is None:
        tiers = TIERS
    if agents is None:
        agents = list(EXPERIMENT_AGENTS.keys())

    run_id = f"cross_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION, staging_bucket=f"gs://{GCP_STAGING_BUCKET}")
    client = Client(project=GCP_PROJECT_ID, location=GCP_REGION)
    metrics = get_metrics("lite_agent")

    total_runs = len(tiers) * len(agents)
    print(f"{'=' * 60}")
    print(f"CROSS-MODEL COMPLEXITY EXPERIMENT")
    print(f"{'=' * 60}")
    print(f"  Run ID:  {run_id}")
    print(f"  Tiers:   {', '.join(tiers)}")
    print(f"  Agents:  {', '.join(agents)}")
    print(f"  Total:   {total_runs} eval runs")
    print(f"  Metrics: {len(metrics)}")
    print()

    results = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "tiers": tiers,
        "agents": agents,
        "runs": {},
    }

    run_num = 0
    for tier in tiers:
        cases = TIER_EVAL_CASES.get(tier, [])
        if not cases:
            print(f"  No cases for tier '{tier}', skipping")
            continue

        print(f"\n--- Tier: {tier.upper()} ({len(cases)} cases) ---")

        for agent_name in agents:
            engine_id = EXPERIMENT_AGENTS.get(agent_name, "")
            if not engine_id:
                print(f"  {agent_name}: no engine ID, skipping")
                continue

            run_num += 1
            print(f"\n[{run_num}/{total_runs}]")

            try:
                result = run_single_eval(client, agent_name, engine_id, tier, cases, metrics)
                key = f"{agent_name}_{tier}"
                results["runs"][key] = result

                if result["metrics"]:
                    for mname, score in sorted(result["metrics"].items()):
                        short = mname.split("/")[-1] if "/" in mname else mname
                        print(f"    {short:40s} {score:.2f}")
            except Exception as e:
                print(f"  ERROR: {e}")
                results["runs"][f"{agent_name}_{tier}"] = {
                    "agent": agent_name, "tier": tier, "status": "ERROR", "error": str(e),
                }

    # Summary
    print(f"\n{'=' * 60}")
    print(f"EXPERIMENT SUMMARY")
    print(f"{'=' * 60}")

    for tier in tiers:
        print(f"\n  {tier.upper()}:")
        for agent_name in agents:
            key = f"{agent_name}_{tier}"
            r = results["runs"].get(key, {})
            status = r.get("status", "MISSING")
            metrics_dict = r.get("metrics", {})
            avg = 0
            if metrics_dict:
                vals = [v for v in metrics_dict.values() if v > 0]
                avg = sum(vals) / len(vals) if vals else 0
            print(f"    {agent_name:20s} {status:10s} avg={avg:.2f}")

    # Save results
    output_dir = Path(EVAL_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"cross_model_{run_id}.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {output_path}")

    return results


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Cross-model complexity experiment")
    parser.add_argument("--tier", type=str, default=None, help="Run specific tier (low, medium, high)")
    parser.add_argument("--agent", type=str, default=None, help="Run specific agent only")
    args = parser.parse_args()

    tiers = [args.tier] if args.tier else None
    agents = [args.agent] if args.agent else None

    run_experiment(tiers=tiers, agents=agents)

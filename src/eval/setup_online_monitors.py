"""Online evaluation against deployed Agent Engine.

Runs a quick evaluation dataset against the deployed agent using the
Vertex AI Evals API. Results are visible in the GCP console.

Usage:
    uv run python -m src.eval.setup_online_monitors <agent-engine-id>
    uv run python -m src.eval.setup_online_monitors 2762936930915057664
"""

import json
import sys
import time
from datetime import datetime

import vertexai
from vertexai import Client, types

from src.config import GCP_PROJECT_ID, GCP_REGION, GCP_STAGING_BUCKET

QUICK_EVAL_CASES = [
    "Find me a hotel in Miami",
    "Search for hotels in New York under $350",
    "Check if a $50 meal expense is within policy",
    "Check policy for a $500 entertainment expense",
    "Submit a $45 meals expense for lunch meeting, user ID EMP001",
]

EVAL_METRICS = [
    types.RubricMetric.FINAL_RESPONSE_QUALITY,
    types.RubricMetric.SAFETY,
]


def _resolve_agent_resource_name(agent_id: str) -> str:
    if agent_id.startswith("projects/"):
        return agent_id
    return f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/reasoningEngines/{agent_id}"


def run_quick_eval(agent_id: str) -> dict:
    """Run a quick evaluation against the deployed agent."""
    agent_resource = _resolve_agent_resource_name(agent_id)
    run_id = f"quick_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    print(f"Online evaluation: {agent_resource}")
    print(f"  Run ID: {run_id}")
    print(f"  Cases:  {len(QUICK_EVAL_CASES)}")

    vertexai.init(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
        staging_bucket=f"gs://{GCP_STAGING_BUCKET}",
    )
    client = Client(project=GCP_PROJECT_ID, location=GCP_REGION)

    import pandas as pd

    rows = [
        {
            "prompt": case,
            "session_inputs": types.evals.SessionInput(user_id="monitor-user"),
        }
        for case in QUICK_EVAL_CASES
    ]
    eval_df = pd.DataFrame(rows)

    print("  Running inference...", flush=True)
    t0 = time.time()
    inference_result = client.evals.run_inference(agent=agent_resource, src=eval_df)
    elapsed = time.time() - t0
    print(f"  Inference done in {elapsed:.1f}s")

    print("  Running evaluation...", flush=True)
    from src.eval.batch_eval import _build_agent_info

    evaluation_run = client.evals.create_evaluation_run(
        dataset=inference_result,
        agent_info=_build_agent_info(),
        agent=agent_resource,
        metrics=EVAL_METRICS,
        dest=f"gs://{GCP_STAGING_BUCKET}/eval-results/monitors",
    )

    print("  Waiting for evaluation", end="", flush=True)
    eval_run_name = evaluation_run.name
    while True:
        evaluation_run = client.evals.get_evaluation_run(name=eval_run_name)
        state = str(getattr(evaluation_run, "state", ""))
        if "SUCCEEDED" in state or "FAILED" in state or "CANCELLED" in state:
            break
        print(".", end="", flush=True)
        time.sleep(10)
    print(f" {state}")

    if "FAILED" in state:
        error = getattr(evaluation_run, "error", None)
        print(f"  Evaluation failed: {error}")
        return {"run_id": run_id, "state": state, "error": str(error)}

    run_results = getattr(evaluation_run, "evaluation_run_results", None)
    sm = getattr(run_results, "summary_metrics", None) if run_results else None
    total = (sm.total_items or 0) if sm else 0
    failed = (sm.failed_items or 0) if sm else 0

    metrics = {}
    if sm and sm.metrics:
        metrics = dict(sm.metrics)

    result = {
        "run_id": run_id,
        "agent": agent_resource,
        "timestamp": datetime.now().isoformat(),
        "inference_seconds": round(elapsed, 1),
        "total_items": total,
        "failed_items": failed,
        "metrics": metrics,
        "evaluation_run_name": eval_run_name,
    }

    print()
    print("  Results:")
    if metrics:
        for k, v in sorted(metrics.items()):
            print(f"    {k}: {v}")
    else:
        print("    (no summary metrics — check GCS output or console)")
    print(f"  Items: {total} total, {failed} failed")

    output_path = f"eval_results_{run_id}.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  Saved: {output_path}")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.setup_online_monitors <agent-engine-id>")
        print()
        print("Runs a quick evaluation against the deployed agent.")
        print("Results are visible in the GCP console under Vertex AI > Evaluation.")
        sys.exit(1)
    run_quick_eval(sys.argv[1])

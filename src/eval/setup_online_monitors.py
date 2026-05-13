"""Setup continuous evaluation for Agent Engine deployments.

Model Monitoring v2 requires registered Vertex AI models, so for Agent Engine
(reasoning engines) we use a scheduled batch evaluation approach: run a compact
evaluation dataset against the deployed agent periodically.

Usage:
    uv run python -m src.eval.setup_online_monitors <agent-engine-id> [agent-name]
    uv run python -m src.eval.setup_online_monitors 443583122819252224

For a true scheduled monitor, deploy this as a Cloud Function + Cloud Scheduler
on a 10-minute cron. See docs/workshop_guide.md Section 2.6 for details.
"""

import json
import sys
import time
from datetime import datetime

import vertexai
from vertexai import Client, types

from src.config import GCP_PROJECT_ID, GCP_REGION, GCP_STAGING_BUCKET

QUICK_EVAL_CASES = [
    "Find flights from SFO to JFK on June 15",
    "Search hotels in New York under $300",
    "Check if a $50 meal expense is within policy",
    "Submit a $100 meal expense for user EMP001",
    "Book flight FL001 for Jane Doe",
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
    """Run a quick 5-case evaluation against the deployed agent."""
    agent_resource = _resolve_agent_resource_name(agent_id)
    run_id = f"quick_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    print(f"Quick evaluation: {agent_resource}")
    print(f"  Run ID: {run_id}")
    print(f"  Cases: {len(QUICK_EVAL_CASES)}")

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
            "session_inputs": types.evals.SessionInput(user_id="monitor-user", state={}),
        }
        for case in QUICK_EVAL_CASES
    ]
    eval_df = pd.DataFrame(rows)

    print("  Running inference...")
    t0 = time.time()
    inference_result = client.evals.run_inference(agent=agent_resource, src=eval_df)
    elapsed = time.time() - t0
    print(f"  Inference done in {elapsed:.1f}s")

    print("  Running evaluation...")
    from src.eval.batch_eval import _build_agent_info

    evaluation_run = client.evals.create_evaluation_run(
        dataset=inference_result,
        agent_info=_build_agent_info(),
        agent=agent_resource,
        metrics=EVAL_METRICS,
        dest=f"gs://{GCP_STAGING_BUCKET}/eval-results/monitors/",
    )

    print("  Waiting for evaluation", end="", flush=True)
    while True:
        evaluation_run = client.evals.get_evaluation_run(name=evaluation_run.name)
        state = str(getattr(evaluation_run, "state", ""))
        if "SUCCEEDED" in state or "FAILED" in state or "CANCELLED" in state:
            break
        print(".", end="", flush=True)
        time.sleep(10)
    print(f" {state}")

    sm = evaluation_run.evaluation_run_results.summary_metrics
    raw_metrics = dict(sm.metrics) if sm.metrics else {}
    total = sm.total_items or 0
    failed = sm.failed_items or 0
    averages = {
        k.rsplit("/AVERAGE", 1)[0]: float(v)
        for k, v in raw_metrics.items()
        if "/AVERAGE" in k
    }

    result = {
        "run_id": run_id,
        "agent": agent_resource,
        "timestamp": datetime.now().isoformat(),
        "inference_seconds": round(elapsed, 1),
        "total_items": total,
        "failed_items": failed,
        "metrics": averages,
        "evaluation_run_name": evaluation_run.name,
    }

    print()
    print("  Results:")
    for k, v in sorted(averages.items()):
        print(f"    {k}: {v:.2f}")
    print(f"  Items OK: {total - failed}/{total}")

    output_path = f"eval_results_{run_id}.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  Saved: {output_path}")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.setup_online_monitors <agent-engine-id>")
        print()
        print("Runs a quick 5-case evaluation against the deployed agent.")
        print("For scheduled monitoring, deploy as Cloud Function + Cloud Scheduler.")
        sys.exit(1)
    run_quick_eval(sys.argv[1])

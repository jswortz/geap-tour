"""Failure cluster analysis — group failure patterns from evaluation results.

Runs a quick evaluation against the deployed agent, then analyzes the
results with generate_loss_clusters() to identify systemic failure patterns.

Usage:
    uv run python -m src.eval.failure_clusters <agent-engine-id>
    uv run python -m src.eval.failure_clusters 4709107696450666496
"""

import sys
import time

import vertexai
from vertexai import Client, types

from src.config import GCP_PROJECT_ID, GCP_REGION, GCP_STAGING_BUCKET
from src.eval.setup_online_monitors import QUICK_EVAL_CASES

EVAL_METRICS = [
    types.RubricMetric.FINAL_RESPONSE_QUALITY,
    types.RubricMetric.SAFETY,
]


def _resolve_agent_resource_name(agent_id: str) -> str:
    if agent_id.startswith("projects/"):
        return agent_id
    return f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/reasoningEngines/{agent_id}"


def analyze_failure_clusters(agent_id: str):
    """Run evaluation and analyze failure clusters."""
    agent_resource = _resolve_agent_resource_name(agent_id)

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
            "session_inputs": types.evals.SessionInput(user_id="cluster-analysis-user"),
        }
        for case in QUICK_EVAL_CASES
    ]
    eval_df = pd.DataFrame(rows)

    print(f"[1/3] Running inference against {agent_resource}...")
    t0 = time.time()
    inference_result = client.evals.run_inference(agent=agent_resource, src=eval_df)
    print(f"  Inference done in {time.time() - t0:.1f}s")

    print("[2/3] Evaluating with metrics...")
    eval_result = client.evals.evaluate(
        dataset=inference_result,
        metrics=EVAL_METRICS,
    )
    print("  Evaluation complete")

    print("[3/3] Analyzing failure clusters...")
    for metric in EVAL_METRICS:
        metric_name = str(metric.value) if hasattr(metric, "value") else str(metric)
        print(f"\n--- Clusters for {metric_name} ---")
        try:
            clusters = client.evals.generate_loss_clusters(
                eval_result=eval_result,
                metric=metric,
            )
            if not clusters:
                print("  No failure clusters found (all cases passed)")
                continue
            for i, cluster in enumerate(clusters, 1):
                title = getattr(cluster, "title", "Untitled")
                description = getattr(cluster, "description", "")
                count = getattr(cluster, "sample_count", 0)
                score = getattr(cluster, "avg_score", None)
                print(f"  Cluster {i}: {title}")
                print(f"    Description: {description}")
                print(f"    Samples: {count}")
                if score is not None:
                    print(f"    Avg score: {score:.2f}")
        except Exception as e:
            print(f"  Error: {e}")

    return eval_result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.failure_clusters <agent-engine-id>")
        sys.exit(1)
    analyze_failure_clusters(sys.argv[1])

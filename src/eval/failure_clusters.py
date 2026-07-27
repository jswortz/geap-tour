"""Failure cluster analysis — group failure patterns from evaluation results.

Runs a quick evaluation against the deployed agent, then analyzes the
results with generate_loss_clusters() to identify systemic failure patterns.

Usage:
    uv run python -m src.eval.failure_clusters <agent-engine-id>
    uv run python -m src.eval.failure_clusters 4709107696450666496
"""

import json
import os
import sys
import time

import vertexai
from vertexai import Client, types

from src.config import EVAL_OUTPUT_DIR, GCP_PROJECT_ID, GCP_REGION, GCP_STAGING_BUCKET
from src.eval.loss_taxonomy import map_cluster_to_taxonomy
from src.eval.setup_online_monitors import QUICK_EVAL_CASES

EVAL_METRICS = [
    types.RubricMetric.FINAL_RESPONSE_QUALITY,
    types.RubricMetric.SAFETY,
]


def _resolve_agent_resource_name(agent_id: str) -> str:
    if agent_id.startswith("projects/"):
        return agent_id
    return f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/reasoningEngines/{agent_id}"


def three_level_triage(eval_result, clusters_by_metric: dict | None = None) -> dict:
    """Build the doc's 3-level triage view of an evaluation result.

    Implements the triage model from "Analyze evaluation results and failure
    clusters":
    https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/view-results

    - Level 1 ("summary_metrics"): aggregate mean scores / pass rates.
    - Level 2 ("failure_clusters"): per-cluster loss patterns mapped onto the
      predefined loss taxonomy.
    - Level 3 ("trace_drilldown_hint"): where to inspect individual traces.

    Returns a JSON-serializable dict.
    """
    # --- Level 1: aggregate summary metrics (handle dict or list shapes) ---
    summary: dict[str, float] = {}
    sm = getattr(eval_result, "summary_metrics", None)
    if isinstance(sm, dict):
        for metric_name, scores in sm.items():
            if isinstance(scores, dict):
                summary[str(metric_name)] = float(scores.get("mean", 0))
            else:
                try:
                    summary[str(metric_name)] = float(scores)
                except (TypeError, ValueError):
                    summary[str(metric_name)] = 0.0
    elif isinstance(sm, list):
        for item in sm:
            if isinstance(item, dict):
                metric_name = item.get("metric", item.get("name", "unknown"))
                try:
                    summary[str(metric_name)] = float(
                        item.get("score", item.get("mean", 0))
                    )
                except (TypeError, ValueError):
                    summary[str(metric_name)] = 0.0

    # --- Level 2: failure clusters mapped onto the loss taxonomy ---
    failure_clusters: list[dict] = []
    for metric_name, clusters in (clusters_by_metric or {}).items():
        for cluster in clusters or []:
            taxonomy = map_cluster_to_taxonomy(cluster)
            failure_clusters.append(
                {
                    "metric": metric_name,
                    "title": getattr(cluster, "title", "Untitled"),
                    "description": getattr(cluster, "description", ""),
                    "sample_count": getattr(cluster, "sample_count", 0),
                    "taxonomy_category": taxonomy["category"],
                    "taxonomy_pattern": taxonomy["pattern"],
                }
            )

    return {
        "summary_metrics": summary,
        "failure_clusters": failure_clusters,
        "trace_drilldown_hint": (
            "Inspect individual traces in the Google Cloud Console: "
            "Deployments > <agent> > Traces tab. Drill into a failing trace to "
            "see the full turn-by-turn tool calls, parameters, and model "
            "responses behind each failure cluster."
        ),
    }


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
    clusters_by_metric: dict[str, list] = {}
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
            clusters_by_metric[metric_name] = list(clusters)
            for i, cluster in enumerate(clusters, 1):
                title = getattr(cluster, "title", "Untitled")
                description = getattr(cluster, "description", "")
                count = getattr(cluster, "sample_count", 0)
                score = getattr(cluster, "avg_score", None)
                taxonomy = map_cluster_to_taxonomy(cluster)
                print(f"  Cluster {i}: {title}")
                print(f"    Description: {description}")
                print(f"    Samples: {count}")
                if score is not None:
                    print(f"    Avg score: {score:.2f}")
                print(f"    Taxonomy: {taxonomy['category']} / {taxonomy['pattern']}")
        except Exception as e:
            print(f"  Error: {e}")

    triage = three_level_triage(eval_result, clusters_by_metric)
    os.makedirs(EVAL_OUTPUT_DIR, exist_ok=True)
    triage_path = os.path.join(EVAL_OUTPUT_DIR, "failure_triage.json")
    with open(triage_path, "w") as fh:
        json.dump(triage, fh, indent=2)
    print(f"\nTriage report written to {triage_path}")

    return eval_result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.failure_clusters <agent-engine-id>")
        sys.exit(1)
    analyze_failure_clusters(sys.argv[1])

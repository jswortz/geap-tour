"""Failure cluster analysis — group failure patterns from evaluation results.

Auto-loss analysis (``generate_loss_clusters``) requires a **multi-turn**
evaluation result — one that carries ``AgentData`` with conversation turns — so
this module runs the *simulated* (user-simulator) pipeline against the deployed
agent, then clusters the failures on the multi-turn metrics that support loss
analysis (Task Success, Tool Use Quality) and maps each cluster onto the
predefined loss taxonomy.

    generate_conversation_scenarios → run_inference (user simulator) →
    evaluate (multi-turn rubric metrics) → generate_loss_clusters

Note: a single-turn batch result (prompt→response) is rejected by the API with
"EvaluationResult must contain AgentData with conversation turns", which is why
we use the multi-turn path here.

Doc: https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/view-results

Usage:
    uv run python -m src.eval.failure_clusters <agent-engine-id> [agent_name]
    uv run python -m src.eval.failure_clusters 5598638991600517120 coordinator_agent
"""

import json
import os
import sys
import time

import vertexai
from vertexai import Client, types

from src.config import EVAL_OUTPUT_DIR, GCP_PROJECT_ID, GCP_REGION, GCP_STAGING_BUCKET
from src.eval.loss_taxonomy import map_cluster_to_taxonomy

# Multi-turn metrics that support auto-loss analysis (each maps to a loss taxonomy).
_CLUSTER_METRIC_NAMES = ["MULTI_TURN_TASK_SUCCESS", "MULTI_TURN_TOOL_USE_QUALITY"]


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
    # --- Level 1: aggregate summary metrics (handle dict, list, or SDK shapes) ---
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
            name = getattr(item, "metric_name", None)
            mean = getattr(item, "mean_score", None)
            if name is not None:
                try:
                    summary[str(name)] = float(mean) if mean is not None else 0.0
                except (TypeError, ValueError):
                    summary[str(name)] = 0.0
            elif isinstance(item, dict):
                metric_name = item.get("metric", item.get("name", "unknown"))
                try:
                    summary[str(metric_name)] = float(item.get("score", item.get("mean", 0)))
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


def analyze_failure_clusters(
    agent_id: str,
    agent_name: str = "coordinator_agent",
    scenario_count: int = 6,
    max_turns: int = 4,
):
    """Run a multi-turn simulated eval and analyze its failure (loss) clusters."""
    agent_resource = _resolve_agent_resource_name(agent_id)

    vertexai.init(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
        staging_bucket=f"gs://{GCP_STAGING_BUCKET}",
    )
    client = Client(project=GCP_PROJECT_ID, location=GCP_REGION)

    from src.config import FLASH_MODEL
    from src.eval.agent_eval_configs import build_agent_info, get_multi_turn_metrics
    from src.eval.simulated_eval import ENVIRONMENT_CONTEXTS, GENERATION_INSTRUCTIONS

    agent_info = build_agent_info(agent_name)

    print(f"[1/4] Generating {scenario_count} multi-turn scenarios for {agent_name}...")
    eval_dataset = client.evals.generate_conversation_scenarios(
        agent_info=agent_info,
        config={
            "count": scenario_count,
            "generation_instruction": GENERATION_INSTRUCTIONS.get(
                agent_name, GENERATION_INSTRUCTIONS["coordinator_agent"]
            ),
            "environment_context": ENVIRONMENT_CONTEXTS.get(
                agent_name, ENVIRONMENT_CONTEXTS["coordinator_agent"]
            ),
        },
        allow_cross_region_model=True,
    )

    print(f"[2/4] Running multi-turn inference (user simulator, max {max_turns} turns)...")
    t0 = time.time()
    traces = client.evals.run_inference(
        agent=agent_resource,
        src=eval_dataset,
        config={
            "user_simulator_config": {"max_turn": max_turns, "model_name": FLASH_MODEL},
            # FLASH_MODEL (the user-simulator model) is global-only; allow routing
            # outside the request region so multi-turn inference can run.
            "allow_cross_region_model": True,
        },
    )
    print(f"  Inference done in {time.time() - t0:.1f}s")

    print("[3/4] Evaluating with multi-turn metrics...")
    eval_result = client.evals.evaluate(
        dataset=traces,
        metrics=get_multi_turn_metrics(agent_name),
    )
    print("  Evaluation complete")

    cluster_metrics = [
        m for name in _CLUSTER_METRIC_NAMES
        if (m := getattr(types.RubricMetric, name, None)) is not None
    ]

    print("[4/4] Analyzing failure clusters (auto-loss analysis)...")
    clusters_by_metric: dict[str, list] = {}
    for metric in cluster_metrics:
        metric_name = str(metric.value) if hasattr(metric, "value") else str(metric)
        print(f"\n--- Clusters for {metric_name} ---")
        try:
            clusters = client.evals.generate_loss_clusters(eval_result=eval_result, metric=metric)
            if not clusters:
                print("  No failure clusters found (no failing turns for this metric)")
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
        except Exception as e:  # noqa: BLE001
            print(f"  Error: {e}")

    triage = three_level_triage(eval_result, clusters_by_metric)
    os.makedirs(EVAL_OUTPUT_DIR, exist_ok=True)
    triage_path = os.path.join(EVAL_OUTPUT_DIR, "failure_triage.json")
    with open(triage_path, "w") as fh:
        json.dump(triage, fh, indent=2)
    print(f"\nTriage report written to {triage_path}")
    total = sum(len(v) for v in clusters_by_metric.values())
    print(f"Total failure clusters: {total}")

    return eval_result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.failure_clusters <agent-engine-id> [agent_name]")
        sys.exit(1)
    agent_name = sys.argv[2] if len(sys.argv) > 2 else "coordinator_agent"
    analyze_failure_clusters(sys.argv[1], agent_name=agent_name)

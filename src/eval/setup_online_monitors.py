"""Setup online evaluators — continuous 10-minute cycle monitors using Cloud Trace telemetry."""

from google import genai

from src.config import GCP_PROJECT_ID, GCP_REGION
from src.eval.one_time_eval import HELPFULNESS_METRIC, TOOL_USE_METRIC, POLICY_COMPLIANCE_METRIC


def setup_online_monitors(
    agent_resource_name: str,
    agent_name: str = "coordinator_agent",
) -> dict[str, str]:
    """Create online evaluators on a 10-minute cycle.

    Returns dict of {metric_name: monitor_resource_name}.
    """
    client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )

    monitors = {}
    metrics_to_create = [
        ("helpfulness", HELPFULNESS_METRIC),
        ("tool_use_accuracy", TOOL_USE_METRIC),
        ("policy_compliance", POLICY_COMPLIANCE_METRIC),
    ]

    if agent_name == "router_agent":
        from src.eval.complexity_metrics import COMPLEXITY_ROUTING_METRIC
        metrics_to_create.append(("complexity_routing", COMPLEXITY_ROUTING_METRIC))

    print(f"Setting up online monitors for {agent_resource_name} ({agent_name})...")

    for metric_name, metric in metrics_to_create:
        print(f"  Creating {metric_name} monitor...")
        try:
            monitor = client.evals.create_online_eval(
                agent=agent_resource_name,
                config={
                    "metrics": [metric],
                    "schedule": {"interval_minutes": 10},
                    "sample_rate": 1.0,
                },
            )
            monitors[metric_name] = monitor.name
            print(f"    {monitor.name}")
        except Exception as e:
            print(f"    Failed: {e}")

    print(f"\n  {len(monitors)} monitors active — eval results will flow to BigQuery")
    print("  Verify: uv run python -m src.eval.verify_monitors")

    return monitors


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.setup_online_monitors <agent-resource-name> [agent-name]")
        sys.exit(1)
    agent_name = sys.argv[2] if len(sys.argv) > 2 else "coordinator_agent"
    setup_online_monitors(sys.argv[1], agent_name=agent_name)

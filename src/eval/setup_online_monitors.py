"""Setup online evaluators — continuous 10-minute cycle monitors using Cloud Trace telemetry."""

from google import genai
from google.genai import types

from src.config import GCP_PROJECT_ID, GCP_REGION
from src.eval.one_time_eval import HELPFULNESS_METRIC, TOOL_USE_METRIC


def setup_online_monitors(agent_resource_name: str):
    """Create online evaluators that run on a 10-minute cycle."""
    client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )

    print(f"Setting up online monitors for {agent_resource_name}...")

    # Helpfulness monitor
    print("  Creating helpfulness monitor...")
    helpfulness_monitor = client.evals.create_online_eval(
        agent=agent_resource_name,
        config={
            "metrics": [HELPFULNESS_METRIC],
            "schedule": {"interval_minutes": 10},
            "sample_rate": 1.0,
        },
    )
    print(f"  ✓ Helpfulness monitor: {helpfulness_monitor.name}")

    # Tool use accuracy monitor
    print("  Creating tool_use_accuracy monitor...")
    tool_use_monitor = client.evals.create_online_eval(
        agent=agent_resource_name,
        config={
            "metrics": [TOOL_USE_METRIC],
            "schedule": {"interval_minutes": 10},
            "sample_rate": 1.0,
        },
    )
    print(f"  ✓ Tool use monitor: {tool_use_monitor.name}")

    print("\n✓ Online monitors active — eval results will flow to BigQuery")
    print("  Verify: uv run python src/eval/verify_monitors.py")

    return [helpfulness_monitor, tool_use_monitor]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.setup_online_monitors <agent-resource-name>")
        sys.exit(1)
    setup_online_monitors(sys.argv[1])

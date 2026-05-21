"""Quality alerts — Cloud Monitoring alert policies for evaluation score thresholds."""

from google.cloud import monitoring_v3
from google.protobuf import duration_pb2

from src.config import GCP_PROJECT_ID


def create_quality_alert(
    metric_name: str = "helpfulness",
    threshold: float = 3.0,
    notification_channel: str | None = None,
):
    """Create a Cloud Monitoring alert policy for eval score drops."""
    client = monitoring_v3.AlertPolicyServiceClient()
    project_name = f"projects/{GCP_PROJECT_ID}"

    condition = monitoring_v3.AlertPolicy.Condition(
        display_name=f"Agent {metric_name} score below {threshold}",
        condition_threshold=monitoring_v3.AlertPolicy.Condition.MetricThreshold(
            filter=f'metric.type="custom.googleapis.com/agent_eval/{metric_name}" AND resource.type="global"',
            comparison=monitoring_v3.ComparisonType.COMPARISON_LT,
            threshold_value=threshold,
            duration=duration_pb2.Duration(seconds=600),
            aggregations=[
                monitoring_v3.Aggregation(
                    alignment_period=duration_pb2.Duration(seconds=600),
                    per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_MEAN,
                )
            ],
        ),
    )

    channels = [notification_channel] if notification_channel else []

    policy = monitoring_v3.AlertPolicy(
        display_name=f"GEAP Workshop: {metric_name} quality alert",
        documentation=monitoring_v3.AlertPolicy.Documentation(
            content=f"Agent evaluation score for '{metric_name}' dropped below {threshold}. "
                    "Check recent eval results and agent behavior.",
            mime_type="text/markdown",
        ),
        conditions=[condition],
        combiner=monitoring_v3.AlertPolicy.ConditionCombinerType.OR,
        notification_channels=channels,
        enabled=True,
    )

    result = client.create_alert_policy(name=project_name, alert_policy=policy)
    print(f"✓ Alert policy created: {result.name}")
    print(f"  Metric: {metric_name} < {threshold}")
    print("  Window: 10 minutes")
    return result


def list_quality_alerts():
    """List all GEAP workshop alert policies."""
    client = monitoring_v3.AlertPolicyServiceClient()
    project_name = f"projects/{GCP_PROJECT_ID}"

    policies = client.list_alert_policies(name=project_name)
    workshop_policies = [p for p in policies if "GEAP Workshop" in p.display_name]

    if not workshop_policies:
        print("No GEAP workshop alert policies found.")
        return

    print(f"Found {len(workshop_policies)} alert policies:")
    for p in workshop_policies:
        status = "enabled" if p.enabled else "disabled"
        print(f"  - {p.display_name} [{status}]")
        print(f"    {p.name}")


ALL_MONITORED_METRICS = [
    ("helpfulness", 3.0),
    ("tool_use_accuracy", 3.0),
    ("policy_compliance", 3.0),
    ("complexity_routing_accuracy", 3.0),
]


def setup_all_alerts(notification_channel: str | None = None) -> list:
    """Create alert policies for all monitored metrics."""
    results = []
    print("Setting up quality alerts for all metrics...")
    for metric_name, threshold in ALL_MONITORED_METRICS:
        try:
            result = create_quality_alert(
                metric_name=metric_name,
                threshold=threshold,
                notification_channel=notification_channel,
            )
            results.append(result)
        except Exception as e:
            print(f"  Warning: failed to create alert for {metric_name}: {e}")
    print(f"\n  {len(results)} alert policies created")
    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        list_quality_alerts()
    elif len(sys.argv) > 1 and sys.argv[1] == "all":
        setup_all_alerts()
    else:
        metric = sys.argv[1] if len(sys.argv) > 1 else "helpfulness"
        threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
        create_quality_alert(metric_name=metric, threshold=threshold)

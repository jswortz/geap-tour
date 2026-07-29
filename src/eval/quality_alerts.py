"""Quality alerts — Cloud Monitoring alert policies for evaluation score thresholds.

Two families of alert are supported:

1. Custom offline/batch metrics published to
   ``custom.googleapis.com/agent_eval/*`` (see ``create_quality_alert`` and
   ``setup_all_alerts``).
2. Native GEAP Online Monitor scores. Configuring an Online Monitor
   auto-exports numeric evaluation scores to the Cloud Monitoring metric type
   ``aiplatform.googleapis.com/online_evaluator/scores``, labelled by
   ``evaluation_metric_name``. The metric is a DELTA DISTRIBUTION on the
   ``aiplatform.googleapis.com/OnlineEvaluator`` resource, so alert conditions
   restrict ``resource.type`` and align it with a percentile aligner
   (``ALIGN_PERCENTILE_50`` = median). A sustained drop in the median score is a
   signal of *quality drift*.

Google documents three ways to turn those online-evaluator scores into an
alerting policy:

  (1) Per-monitor "Create alerting policy" in the Cloud console.
  (2) The metrics dashboard "Recommended Alerts" flow.
  (3) Programmatically — either
      ``gcloud monitoring policies create --policy-from-file=policy.yaml``
      (see ``export_policy_yaml`` for generating that YAML artifact) or the
      ``monitoring_v3.AlertPolicyServiceClient`` API (see
      ``create_drift_alert_from_online_evaluator``).

See: https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/quality-alerts
"""

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


def _get_notification_channel() -> str | None:
    """Find the first active email notification channel in the project."""
    client = monitoring_v3.NotificationChannelServiceClient()
    project_name = f"projects/{GCP_PROJECT_ID}"
    try:
        channels = client.list_notification_channels(name=project_name)
        for c in channels:
            if c.type_ == "email" and c.enabled:
                return c.name
    except Exception as e:
        print(f"Warning: failed to list notification channels: {e}")
    return None


def _drift_documentation(metric_name: str, threshold: float) -> str:
    """Markdown runbook shared by the YAML artifact and the live API policy."""
    return (
        "## GEAP Agent Quality Drift\n\n"
        f"The agent's `{metric_name}` online-evaluation score has dropped below "
        f"{threshold}. Configuring an Online Monitor auto-exports numeric "
        "evaluation scores to the Cloud Monitoring metric type "
        "`aiplatform.googleapis.com/online_evaluator/scores`, labelled by "
        "`evaluation_metric_name`. A sustained drop in the median score is a "
        "signal of quality drift — the deployed agent is regressing relative "
        "to its evaluated baseline.\n\n"
        "**What to check:** recent online-evaluation traces for failing "
        "sessions, model/prompt/tool changes deployed in the alert window, and "
        "upstream data or MCP tool availability."
    )


def _build_drift_policy_dict(
    metric_name: str,
    threshold: float,
    metric_type: str,
    duration_seconds: int = 1800,
) -> dict:
    """Build the alert-policy resource as a plain dict (gcloud/REST camelCase).

    This mirrors the ``monitoring_v3.AlertPolicy`` constructed by
    ``create_drift_alert_from_online_evaluator`` but in the shape accepted by
    ``gcloud monitoring policies create --policy-from-file=``.
    """
    return {
        "displayName": "GEAP Agent Quality Drift - Low Task Success"
        if metric_name == "task_success"
        else f"GEAP Agent Quality Drift - Low {metric_name}",
        "documentation": {
            "mimeType": "text/markdown",
            "content": _drift_documentation(metric_name, threshold),
        },
        "conditions": [
            {
                "displayName": f"{metric_name} online_evaluator median score below {threshold}",
                "conditionThreshold": {
                    # DELTA DISTRIBUTION on the OnlineEvaluator resource: restrict
                    # resource.type and use a percentile aligner (ALIGN_MEAN is invalid
                    # for a distribution) — P50 gives the median score in the window.
                    "filter": (
                        'resource.type="aiplatform.googleapis.com/OnlineEvaluator" '
                        f'AND metric.type="{metric_type}" '
                        f'AND metric.labels.evaluation_metric_name="{metric_name}"'
                    ),
                    "comparison": "COMPARISON_LT",
                    "thresholdValue": threshold,
                    "duration": f"{duration_seconds}s",
                    "aggregations": [
                        {
                            "alignmentPeriod": f"{duration_seconds}s",
                            "perSeriesAligner": "ALIGN_PERCENTILE_50",
                        }
                    ],
                },
            }
        ],
        "combiner": "OR",
        "enabled": True,
        # Attach notification channels to be paged on drift. Uncomment and
        # replace with your channel resource name(s):
        # "notificationChannels": [
        #     "projects/YOUR_PROJECT_ID/notificationChannels/CHANNEL_ID"
        # ],
    }


def _yaml_dump_fallback(data) -> str:
    """Minimal block-style YAML serializer used when PyYAML is unavailable."""
    lines: list[str] = []

    def scalar(value) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, float):
            return repr(value)
        if isinstance(value, int):
            return str(value)
        text = str(value)
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def emit_mapping(mapping: dict, indent: int) -> None:
        pad = "  " * indent
        for key, value in mapping.items():
            if isinstance(value, dict):
                lines.append(f"{pad}{key}:")
                emit_mapping(value, indent + 1)
            elif isinstance(value, list):
                lines.append(f"{pad}{key}:")
                emit_list(value, indent + 1)
            elif isinstance(value, str) and "\n" in value:
                lines.append(f"{pad}{key}: |-")
                for text_line in value.split("\n"):
                    lines.append(f"{pad}  {text_line}" if text_line else "")
            else:
                lines.append(f"{pad}{key}: {scalar(value)}")

    def emit_list(items: list, indent: int) -> None:
        pad = "  " * indent
        for item in items:
            if isinstance(item, dict):
                entries = list(item.items())
                first_key, first_val = entries[0]
                simple_first = not (
                    isinstance(first_val, (dict, list))
                    or (isinstance(first_val, str) and "\n" in first_val)
                )
                if simple_first:
                    lines.append(f"{pad}- {first_key}: {scalar(first_val)}")
                    if len(entries) > 1:
                        emit_mapping(dict(entries[1:]), indent + 1)
                else:
                    lines.append(f"{pad}-")
                    emit_mapping(item, indent + 1)
            else:
                lines.append(f"{pad}- {scalar(item)}")

    emit_mapping(data, 0)
    return "\n".join(lines) + "\n"


def export_policy_yaml(
    path: str = "src/eval/policies/quality_drift_policy.yaml",
    metric_name: str = "task_success",
    threshold: float = 0.8,
    metric_type: str = "aiplatform.googleapis.com/online_evaluator/scores",
) -> str:
    """Write a Cloud Monitoring alert-policy YAML for online-evaluator drift.

    The output is consumable by::

        gcloud monitoring policies create --policy-from-file=<path>

    Uses ``yaml.safe_dump`` when PyYAML is importable and falls back to a small
    hand-rolled serializer otherwise (PyYAML is not a hard import dependency).
    Returns the written path.
    """
    import os

    policy = _build_drift_policy_dict(
        metric_name=metric_name,
        threshold=threshold,
        metric_type=metric_type,
        duration_seconds=1800,
    )

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    try:
        import yaml  # type: ignore

        content = yaml.safe_dump(policy, sort_keys=False, default_flow_style=False)
    except ImportError:
        content = _yaml_dump_fallback(policy)

    header = (
        "# GEAP Agent Quality Drift alert policy (generated by "
        "export_policy_yaml).\n"
        "# Create it with:\n"
        f"#   gcloud monitoring policies create --policy-from-file={path}\n"
        "# See: https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/quality-alerts\n"
    )
    with open(path, "w") as f:
        f.write(header + content)

    print(f"✓ Alert policy YAML written: {path}")
    print(f"  Metric: {metric_type} (evaluation_metric_name={metric_name}) < {threshold}")
    print(f"  Apply: gcloud monitoring policies create --policy-from-file={path}")
    return path


def create_drift_alert_from_online_evaluator(
    metric_name: str = "task_success",
    threshold: float = 0.8,
    notification_channel: str | None = None,
) -> str | None:
    """Create a live Cloud Monitoring alert on native Online Monitor scores.

    Targets ``aiplatform.googleapis.com/online_evaluator/scores`` filtered by
    ``evaluation_metric_name="{metric_name}"``. Safe to call without a live
    monitor: any failure is caught, printed, and ``None`` is returned.
    """
    try:
        client = monitoring_v3.AlertPolicyServiceClient()
        project_name = f"projects/{GCP_PROJECT_ID}"

        condition = monitoring_v3.AlertPolicy.Condition(
            display_name=f"{metric_name} online_evaluator median score below {threshold}",
            condition_threshold=monitoring_v3.AlertPolicy.Condition.MetricThreshold(
                # online_evaluator/scores is a DELTA DISTRIBUTION on the
                # aiplatform.googleapis.com/OnlineEvaluator resource; the filter MUST
                # restrict resource.type, and a distribution needs a percentile aligner
                # (ALIGN_MEAN is rejected for DISTRIBUTION) — P50 is the median score.
                filter=(
                    'resource.type="aiplatform.googleapis.com/OnlineEvaluator" '
                    'AND metric.type="aiplatform.googleapis.com/online_evaluator/scores" '
                    f'AND metric.labels.evaluation_metric_name="{metric_name}"'
                ),
                comparison=monitoring_v3.ComparisonType.COMPARISON_LT,
                threshold_value=threshold,
                duration=duration_pb2.Duration(seconds=3600),
                aggregations=[
                    monitoring_v3.Aggregation(
                        alignment_period=duration_pb2.Duration(seconds=3600),
                        per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_PERCENTILE_50,
                    )
                ],
            ),
        )

        channels = [notification_channel] if notification_channel else []

        policy = monitoring_v3.AlertPolicy(
            display_name="GEAP Agent Quality Drift - Low Task Success"
            if metric_name == "task_success"
            else f"GEAP Agent Quality Drift - Low {metric_name}",
            documentation=monitoring_v3.AlertPolicy.Documentation(
                content=_drift_documentation(metric_name, threshold),
                mime_type="text/markdown",
            ),
            conditions=[condition],
            combiner=monitoring_v3.AlertPolicy.ConditionCombinerType.OR,
            notification_channels=channels,
            enabled=True,
        )

        result = client.create_alert_policy(name=project_name, alert_policy=policy)
        print(f"✓ Drift alert policy created: {result.name}")
        print(f"  Metric: online_evaluator/scores[{metric_name}] < {threshold}")
        print("  Window: 60 minutes")
        return result.name
    except Exception as e:
        print(f"✗ Failed to create drift alert for '{metric_name}': {e}")
        return None


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd == "list":
        list_quality_alerts()
    elif cmd == "all":
        channel = _get_notification_channel()
        if channel:
            print(f"Using notification channel: {channel}")
        else:
            print("Warning: no active email notification channel found.")
        setup_all_alerts(notification_channel=channel)
    elif cmd == "export-yaml":
        path = sys.argv[2] if len(sys.argv) > 2 else "src/eval/policies/quality_drift_policy.yaml"
        export_policy_yaml(path=path)
    elif cmd == "drift":
        metric = sys.argv[2] if len(sys.argv) > 2 else "task_success"
        threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 0.8
        channel = _get_notification_channel()
        create_drift_alert_from_online_evaluator(
            metric_name=metric, threshold=threshold, notification_channel=channel
        )
    else:
        metric = cmd if cmd else "helpfulness"
        threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
        channel = _get_notification_channel()
        create_quality_alert(metric_name=metric, threshold=threshold, notification_channel=channel)

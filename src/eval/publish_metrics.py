"""Publish Online Evaluation results to Cloud Monitoring as custom metrics.

Queries Cloud Logging for evaluation results and writes them to Cloud Monitoring.
This makes the metrics viewable in Metrics Explorer and triggers alert policies.

Usage:
    uv run python -m src.eval.publish_metrics
"""

import time
import requests
from datetime import datetime, timezone, timedelta
import google.auth
import google.auth.transport.requests
from google.cloud import monitoring_v3

from src.config import GCP_PROJECT_ID, AGENT_ENGINE_ID

# Define custom metrics mapping
# Vertex AI Online Evaluator metric names -> Custom Metric names
METRIC_MAPPING = {
    "final_response_quality_v1": "helpfulness",
    "tool_use_quality_v1": "tool_use_accuracy",
    "safety_v1": "safety",
    "hallucination_v1": "groundedness",
    "GEAP Task Quality": "geap_task_quality",
    "GEAP Policy Compliance": "policy_compliance",
    "complexity_routing_accuracy": "complexity_routing_accuracy",
}


def _get_headers():
    credentials, _ = google.auth.default()
    credentials.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }


def create_metric_descriptors():
    """Create Metric Descriptors in Cloud Monitoring if they do not exist."""
    client = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{GCP_PROJECT_ID}"

    # List existing custom metrics to avoid recreation errors
    existing_types = []
    try:
        for descriptor in client.list_metric_descriptors(name=project_name):
            if descriptor.type.startswith("custom.googleapis.com/agent_eval/"):
                existing_types.append(descriptor.type)
    except Exception as e:
        print(f"Error listing metric descriptors: {e}")

    for internal_name, custom_name in METRIC_MAPPING.items():
        metric_type = f"custom.googleapis.com/agent_eval/{custom_name}"
        if metric_type in existing_types:
            print(f"Metric descriptor already exists: {metric_type}")
            continue

        print(f"Creating metric descriptor: {metric_type}")
        descriptor = {
            "type": metric_type,
            "metric_kind": "GAUGE",
            "value_type": "DOUBLE",
            "description": f"GEAP Evaluator score for {internal_name}",
            "display_name": f"GEAP Agent Eval: {custom_name}",
            "labels": [
                {
                    "key": "agent",
                    "value_type": "STRING",
                    "description": "Agent Resource ID"
                }
            ]
        }

        try:
            client.create_metric_descriptor(name=project_name, metric_descriptor=descriptor)
            print(f"✓ Created: {metric_type}")
        except Exception as e:
            print(f"✗ Failed to create descriptor {metric_type}: {e}")


def fetch_evaluation_logs(lookback_minutes: int = 60) -> list[dict]:
    """Fetch recent evaluation logs from Cloud Logging via REST API."""
    headers = _get_headers()
    
    # Calculate timestamp filter
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    timestamp_filter = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    filter_str = (
        f'resource.type="aiplatform.googleapis.com/OnlineEvaluator" AND '
        f'labels."event.name"="gen_ai.evaluation.result" AND '
        f'timestamp >= "{timestamp_filter}"'
    )

    body = {
        "resourceNames": [f"projects/{GCP_PROJECT_ID}"],
        "filter": filter_str,
        "orderBy": "timestamp desc",
        "pageSize": 100,
    }
    
    print(f"Fetching evaluation logs since {timestamp_filter}...")
    resp = requests.post(
        "https://logging.googleapis.com/v2/entries:list",
        headers=headers,
        json=body,
    )
    if resp.status_code != 200:
        print(f"Error fetching logs ({resp.status_code}): {resp.text}")
        return []
    
    entries = resp.json().get("entries", [])
    print(f"Found {len(entries)} evaluation log entries.")
    return entries


def publish_metrics_to_monitoring(entries: list[dict]):
    """Publish evaluation scores to Cloud Monitoring."""
    if not entries:
        return

    client = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{GCP_PROJECT_ID}"

    published_count = 0
    # Sort entries chronologically to prevent out-of-order metric rejection
    for entry in sorted(entries, key=lambda x: x.get("timestamp", "")):
        elabels = entry.get("labels", {})
        eval_metric_name = elabels.get("gen_ai.evaluation.name")
        score_str = elabels.get("gen_ai.evaluation.score.value")
        
        if not eval_metric_name or not score_str:
            continue

        custom_name = METRIC_MAPPING.get(eval_metric_name)
        if not custom_name:
            # Metric not in mapping, skip
            continue

        try:
            score = float(score_str)
        except ValueError:
            print(f"Skipping invalid score value: {score_str}")
            continue

        agent_resource_path = entry.get("labels", {}).get("agent_resource")
        agent_id = agent_resource_path.split("/")[-1] if agent_resource_path else "unknown"
        
        # Parse timestamp from log entry
        log_ts_str = entry.get("timestamp")
        # standard ISO format: '2026-06-15T18:42:24.365745Z'
        try:
            # strip trailing Z and nanos to parse cleanly
            ts_clean = log_ts_str.split(".")[0].replace("Z", "")
            dt = datetime.strptime(ts_clean, "%Y-%m-%dT%H:%M:%S")
            seconds = int(dt.replace(tzinfo=timezone.utc).timestamp())
        except Exception:
            seconds = int(time.time())

        # Construct TimeSeries
        series = monitoring_v3.TimeSeries()
        series.metric.type = f"custom.googleapis.com/agent_eval/{custom_name}"
        series.metric.labels["agent"] = agent_id

        # Use global monitored resource (matches quality_alerts filter)
        series.resource.type = "global"
        series.resource.labels["project_id"] = GCP_PROJECT_ID

        # Add point
        interval = monitoring_v3.TimeInterval(
            end_time={"seconds": seconds, "nanos": 0}
        )
        point = monitoring_v3.Point(
            interval=interval,
            value={"double_value": score}
        )
        series.points.append(point)

        try:
            client.create_time_series(name=project_name, time_series=[series])
            published_count += 1
        except Exception as e:
            print(f"Error publishing metric {custom_name} (score={score}) for agent {agent_id}: {e}")

    print(f"Successfully published {published_count} metric data points to Cloud Monitoring.")


def write_simulated_metrics():
    """Write simulated out-of-spec metric points to Cloud Monitoring."""
    client = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{GCP_PROJECT_ID}"
    
    # Write a series of declining points ending in a very low score
    metrics_to_write = [
        ("helpfulness", [4.80, 4.70, 4.55, 4.60, 2.10, 1.25, 1.10]),
        ("policy_compliance", [4.90, 4.80, 4.75, 4.60, 1.90, 1.20, 1.05]),
        ("tool_use_accuracy", [4.70, 4.65, 4.50, 4.60, 2.30, 1.35, 1.20]),
    ]
    
    now = time.time()
    published_count = 0
    for custom_name, values in metrics_to_write:
        for idx, score in enumerate(values):
            # Space points out by 5 minutes
            seconds = int(now - (len(values) - 1 - idx) * 300)
            
            series = monitoring_v3.TimeSeries()
            series.metric.type = f"custom.googleapis.com/agent_eval/{custom_name}"
            series.metric.labels["agent"] = AGENT_ENGINE_ID
            series.resource.type = "global"
            series.resource.labels["project_id"] = GCP_PROJECT_ID
            
            interval = monitoring_v3.TimeInterval(
                end_time={"seconds": seconds, "nanos": 0}
            )
            point = monitoring_v3.Point(
                interval=interval,
                value={"double_value": score}
            )
            series.points.append(point)
            
            try:
                client.create_time_series(name=project_name, time_series=[series])
                published_count += 1
            except Exception as e:
                print(f"Error publishing simulated metric: {e}")
                
    print(f"Successfully published {published_count} simulated metric data points to Cloud Monitoring.")


def main():
    import sys
    print("=== Running Metric Publisher (Bridge) ===")
    create_metric_descriptors()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--simulate-out-of-spec":
        print("Simulation Mode: writing out-of-spec data points directly...")
        write_simulated_metrics()
    else:
        entries = fetch_evaluation_logs(lookback_minutes=60)
        publish_metrics_to_monitoring(entries)
    print("=== Done ===")


if __name__ == "__main__":
    main()

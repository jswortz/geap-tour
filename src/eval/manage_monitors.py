"""Manage model monitors — list, delete, view jobs."""

import sys

from google.cloud.aiplatform_v1beta1 import ModelMonitoringServiceClient

from src.config import GCP_PROJECT_ID, GCP_REGION


def _get_client() -> ModelMonitoringServiceClient:
    return ModelMonitoringServiceClient(
        client_options={"api_endpoint": f"{GCP_REGION}-aiplatform.googleapis.com"}
    )


def list_monitors():
    """List all model monitors and their jobs."""
    client = _get_client()
    parent = f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}"
    monitors = list(client.list_model_monitors(parent=parent))
    if not monitors:
        print("No model monitors found.")
        return
    print(f"Found {len(monitors)} monitor(s):")
    for m in monitors:
        print(f"  - {m.name} | display_name={m.display_name}")
        try:
            jobs = list(client.list_model_monitoring_jobs(parent=m.name))
            for j in jobs:
                print(f"      job: {j.name} | state={j.state}")
        except Exception:
            pass


def delete_monitor(monitor_name: str):
    """Delete a model monitor."""
    client = _get_client()
    op = client.delete_model_monitor(name=monitor_name)
    op.result()
    print(f"Deleted: {monitor_name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.manage_monitors <list|delete> [monitor-name]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "list":
        list_monitors()
    elif action == "delete" and len(sys.argv) >= 3:
        delete_monitor(sys.argv[2])
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

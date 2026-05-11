"""Manage online evaluators — list, pause, resume, delete."""

import sys

from google import genai

from src.config import GCP_PROJECT_ID, GCP_REGION


def get_client() -> genai.Client:
    return genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION)


def list_monitors():
    """List all online evaluators."""
    client = get_client()
    monitors = list(client.evals.list_online_evals())
    if not monitors:
        print("No online monitors found.")
        return
    print(f"Found {len(monitors)} monitor(s):")
    for m in monitors:
        print(f"  - {m.name} | state={m.state} | agent={m.agent}")


def pause_monitor(monitor_name: str):
    """Pause an online evaluator."""
    client = get_client()
    client.evals.pause_online_eval(name=monitor_name)
    print(f"✓ Paused: {monitor_name}")


def resume_monitor(monitor_name: str):
    """Resume a paused online evaluator."""
    client = get_client()
    client.evals.resume_online_eval(name=monitor_name)
    print(f"✓ Resumed: {monitor_name}")


def delete_monitor(monitor_name: str):
    """Delete an online evaluator."""
    client = get_client()
    client.evals.delete_online_eval(name=monitor_name)
    print(f"✓ Deleted: {monitor_name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.manage_monitors <list|pause|resume|delete> [monitor-name]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "list":
        list_monitors()
    elif action in ("pause", "resume", "delete") and len(sys.argv) >= 3:
        {"pause": pause_monitor, "resume": resume_monitor, "delete": delete_monitor}[action](sys.argv[2])
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

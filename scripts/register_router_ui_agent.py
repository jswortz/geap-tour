"""Register (or update) the Router Cost Visualizer in Gemini Enterprise.

Fetches the deployed Cloud Run A2UI agent card (JSONRPC + A2UI v0.8 extension) and registers it
against the GE engine's default assistant via the Discovery Engine v1alpha agents API. Mirrors the
proven pattern in party-store-ge-a2ui/scripts/register_cloud_run_agent.py — CREATE for a new agent,
PATCH when GEMINI_ENTERPRISE_AGENT_ID is set.

Config comes from env (see .env / .env.sample):
  GEMINI_ENTERPRISE_PROJECT, GEMINI_ENTERPRISE_ENGINE_ID, ROUTER_UI_APP_URL,
  A2A_APP_NAME (default "app"), GEMINI_ENTERPRISE_AGENT_ID (optional, to update in place).
"""
import json
import os
import sys

import requests
from google.auth import default
from google.auth.transport.requests import Request

PROJECT_ID = os.environ.get("GEMINI_ENTERPRISE_PROJECT", "wortz-project-352116")
ENGINE_ID = os.environ.get("GEMINI_ENTERPRISE_ENGINE_ID", "gemini-enterprise-17634901_1763490144996")
APP_NAME = os.environ.get("A2A_APP_NAME", "app")
APP_URL = os.environ.get(
    "ROUTER_UI_APP_URL", "https://geap-router-cost-ui-679926387543.us-east1.run.app"
).rstrip("/")
AGENT_ID = os.environ.get("GEMINI_ENTERPRISE_AGENT_ID", "").strip()
CARD_URL = f"{APP_URL}/a2a/{APP_NAME}/.well-known/agent-card.json"

BASE = (
    f"https://discoveryengine.googleapis.com/v1alpha/projects/{PROJECT_ID}/"
    f"locations/global/collections/default_collection/engines/{ENGINE_ID}/"
    f"assistants/default_assistant/agents"
)


def _token() -> str:
    creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token


def main() -> int:
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": PROJECT_ID,
    }

    print(f"Fetching deployed served card: {CARD_URL}")
    served = requests.get(CARD_URL, timeout=30)
    served.raise_for_status()
    card = served.json()
    print(f"  url={card.get('url')} transport={card.get('preferredTransport')}")
    print(f"  extensions={[e.get('uri') for e in card.get('capabilities', {}).get('extensions', [])]}")

    a2a_def = {"jsonAgentCard": json.dumps(card)}

    if AGENT_ID:
        url = f"{BASE}/{AGENT_ID}?updateMask=a2aAgentDefinition.jsonAgentCard"
        print(f"Patching existing GE agent {AGENT_ID} ...")
        r = requests.patch(url, headers=headers,
                           json={"name": f"{BASE}/{AGENT_ID}", "a2aAgentDefinition": a2a_def}, timeout=30)
    else:
        body = {
            "displayName": "GEAP Router Cost Visualizer",
            "description": card.get("description", "Multi-model router cost-accrual dashboard."),
            "a2aAgentDefinition": a2a_def,
        }
        print("Creating new GE agent registration ...")
        r = requests.post(BASE, headers=headers, json=body, timeout=30)

    print(f"Status: {r.status_code}")
    if r.status_code in (200, 201):
        name = r.json().get("name", "")
        print(f"✓ Registered. Agent resource: {name}")
        print("  (set GEMINI_ENTERPRISE_AGENT_ID to that id to update in place next time.)")
        return 0
    print(r.text[:800])
    print(
        "\nIf the API rejects the create, add it in the GE console instead:\n"
        f"  https://console.cloud.google.com/gemini-enterprise/locations/global/engines/{ENGINE_ID}"
        f"/overview/dashboard?project={PROJECT_ID}\n"
        f"  → Agents → Add agent (A2A) → card URL: {CARD_URL}"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

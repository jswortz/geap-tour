"""Publish the two ADK agents (coordinator + router) *directly* to Gemini Enterprise.

Unlike the Router Cost Visualizer (an A2A/A2UI service wrapped in Cloud Run, see
``scripts/register_router_ui_agent.py``), this registers the agents' **reasoning engines**
directly to the GE app via the Discovery Engine v1alpha ``adkAgentDefinition`` —
``provisionedReasoningEngine``. This is the same payload ``agents-cli publish
gemini-enterprise --registration-type adk`` builds; we do it here for both agents in one
idempotent pass with no CLI dependency (only ``requests`` + ``google-auth``).

The upsert is idempotent: it lists the GE app's agents, matches the one whose
``provisionedReasoningEngine.reasoningEngine`` equals a given reasoning-engine resource, and
PATCHes it in place — otherwise it POSTs a new registration. Re-running updates, never duplicates.

Config comes from env (see .env / .env.example), with live-ID resolution as a fallback:
  GEMINI_ENTERPRISE_PROJECT   (default: wortz-project-352116)
  GEMINI_ENTERPRISE_LOCATION  (default: global)
  GEMINI_ENTERPRISE_ENGINE_ID (default: gemini-enterprise-17634901_1763490144996)
  GCP_REGION                  (reasoning-engine region, default: us-central1)
  COORDINATOR_ENGINE_ID / ROUTER_ENGINE_ID (optional; else resolved live by display name)

Usage:
  python scripts/publish_agents_to_ge.py                 # publish both
  python scripts/publish_agents_to_ge.py coordinator     # publish one
  python scripts/publish_agents_to_ge.py --dry-run       # show the payloads, don't write
"""
import argparse
import json
import os
import sys

import requests
from google.auth import default
from google.auth.transport.requests import Request

PROJECT_ID = os.environ.get("GEMINI_ENTERPRISE_PROJECT", os.environ.get("GCP_PROJECT_ID", "wortz-project-352116"))
GE_LOCATION = os.environ.get("GEMINI_ENTERPRISE_LOCATION", "global")
ENGINE_ID = os.environ.get("GEMINI_ENTERPRISE_ENGINE_ID", "gemini-enterprise-17634901_1763490144996")
RE_REGION = os.environ.get("GCP_REGION", "us-central1")

# Icon shown for the agent in the GE console (same default the agents-cli uses).
ICON_URI = "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/smart_toy/default/24px.svg"

# The two publishable ADK agents. `re_display` is the reasoning engine's displayName as set
# by `src.deploy.deploy_agents` (= the agent's `name`); used for live ID resolution.
AGENTS = {
    "coordinator": {
        "re_display": "coordinator_agent",
        # Repo convention writes the coordinator engine id to AGENT_ENGINE_ID (see deploy_agents.py);
        # COORDINATOR_ENGINE_ID is accepted too and takes precedence.
        "engine_id_env": ["COORDINATOR_ENGINE_ID", "AGENT_ENGINE_ID"],
        "display_name": "GEAP Corporate Travel & Expense Assistant",
        "description": (
            "Coordinator agent for corporate travel and expense. Searches flights and hotels, "
            "checks expense policy, and delegates booking and expense submission to specialist "
            "sub-agents — with Memory Bank personalization and Model Armor guardrails."
        ),
        "tool_description": (
            "Use for corporate travel booking, flight/hotel search, and expense-policy questions "
            "and submissions."
        ),
    },
    "router": {
        "re_display": "router_agent",
        "engine_id_env": ["ROUTER_ENGINE_ID"],
        "display_name": "GEAP Multi-Model Cost Router",
        "description": (
            "Multi-model complexity router. Classifies each prompt and routes it to the cheapest "
            "capable model tier (Flash-Lite → Flash → Pro → Sonnet → Opus) to optimize cost while "
            "preserving quality."
        ),
        "tool_description": (
            "Use for general questions; automatically routes each request to the most "
            "cost-effective model tier for its complexity."
        ),
    },
}


def _discovery_endpoint() -> str:
    """Discovery Engine base endpoint for the GE app location (global vs regional)."""
    if GE_LOCATION == "global":
        return "https://discoveryengine.googleapis.com"
    return f"https://{GE_LOCATION}-discoveryengine.googleapis.com"


def _agents_base() -> str:
    return (
        f"{_discovery_endpoint()}/v1alpha/projects/{PROJECT_ID}/"
        f"locations/{GE_LOCATION}/collections/default_collection/engines/{ENGINE_ID}/"
        "assistants/default_assistant/agents"
    )


def _reasoning_engine_name(engine_id: str) -> str:
    return f"projects/{PROJECT_ID}/locations/{RE_REGION}/reasoningEngines/{engine_id}"


def _token() -> str:
    creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": PROJECT_ID,
    }


def resolve_engine_id(spec: dict, token: str) -> str:
    """Return the reasoning-engine ID for an agent: env override, else live lookup by displayName."""
    for env_name in spec["engine_id_env"]:
        override = os.environ.get(env_name, "").strip()
        if override:
            return override.split("/")[-1]  # accept bare ID or full resource name

    url = (
        f"https://{RE_REGION}-aiplatform.googleapis.com/v1beta1/"
        f"projects/{PROJECT_ID}/locations/{RE_REGION}/reasoningEngines?pageSize=100"
    )
    r = requests.get(url, headers=_headers(token), timeout=30)
    r.raise_for_status()
    engines = r.json().get("reasoningEngines", [])
    matches = [e for e in engines if e.get("displayName") == spec["re_display"]]
    if not matches:
        raise SystemExit(
            f"✗ No live reasoning engine named '{spec['re_display']}' in "
            f"{PROJECT_ID}/{RE_REGION}. Deploy it first "
            f"(uv run python -m src.deploy.deploy_agents ...), or set {' / '.join(spec['engine_id_env'])}."
        )
    if len(matches) > 1:
        matches.sort(key=lambda e: e.get("updateTime", ""), reverse=True)
        print(f"  ! {len(matches)} engines named '{spec['re_display']}'; using most recent.")
    return matches[0]["name"].split("/")[-1]


def _adk_reasoning_engine(agent: dict) -> str:
    """Pull the reasoning-engine resource name out of a GE agent dict (camel or snake case)."""
    adk = agent.get("adkAgentDefinition") or agent.get("adk_agent_definition") or {}
    prov = adk.get("provisionedReasoningEngine") or adk.get("provisioned_reasoning_engine") or {}
    return prov.get("reasoningEngine") or prov.get("reasoning_engine") or ""


def find_existing(re_name: str, token: str) -> dict | None:
    """First GE agent registered for this reasoning engine, scanning all pages (or None)."""
    params = {"pageSize": 100}
    while True:
        r = requests.get(_agents_base(), headers=_headers(token), params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        match = next((a for a in data.get("agents", []) if _adk_reasoning_engine(a) == re_name), None)
        if match or not data.get("nextPageToken"):
            return match
        params["pageToken"] = data["nextPageToken"]


def publish_one(key: str, spec: dict, token: str, dry_run: bool) -> dict | None:
    engine_id = resolve_engine_id(spec, token)
    re_name = _reasoning_engine_name(engine_id)
    payload = {
        "displayName": spec["display_name"],
        "description": spec["description"],
        "icon": {"uri": ICON_URI},
        "adk_agent_definition": {
            "tool_settings": {"tool_description": spec["tool_description"]},
            "provisioned_reasoning_engine": {"reasoning_engine": re_name},
        },
    }

    print(f"\n--- {key}: {spec['display_name']} ---")
    print(f"  reasoning engine: {re_name}")

    if dry_run:
        print("  [dry-run] payload:")
        print("  " + json.dumps(payload, indent=2).replace("\n", "\n  "))
        return None

    existing = find_existing(re_name, token)
    if existing:
        url = f"{_discovery_endpoint()}/v1alpha/{existing['name']}"
        print(f"  updating existing registration: {existing['name'].split('/')[-1]}")
        r = requests.patch(url, headers=_headers(token), json=payload, timeout=30)
        action = "updated"
    else:
        print("  creating new registration")
        r = requests.post(_agents_base(), headers=_headers(token), json=payload, timeout=30)
        action = "created"

    if r.status_code not in (200, 201):
        print(f"  ✗ HTTP {r.status_code}: {r.text[:600]}")
        r.raise_for_status()

    result = r.json()
    agent_name = result.get("name", "")
    agent_id = agent_name.split("/")[-1]
    console = (
        f"https://console.cloud.google.com/gemini-enterprise/locations/{GE_LOCATION}/"
        f"engines/{ENGINE_ID}/overview/dashboard?project={PROJECT_ID}"
    )
    print(f"  ✓ {action}: {agent_name}")
    print(f"    agent id: {agent_id}")
    print(f"    console:  {console}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish coordinator + router agents directly to Gemini Enterprise.")
    parser.add_argument("agents", nargs="*", default=[], help="Which to publish: coordinator, router (default: both).")
    parser.add_argument("--dry-run", action="store_true", help="Show the payloads without writing.")
    args = parser.parse_args()

    which = args.agents or list(AGENTS)
    unknown = [a for a in which if a not in AGENTS]
    if unknown:
        print(f"Unknown agent(s): {unknown}. Choose from {list(AGENTS)}.")
        return 2

    print(f"Gemini Enterprise app: projects/{PROJECT_ID}/locations/{GE_LOCATION}/"
          f"collections/default_collection/engines/{ENGINE_ID}")
    token = _token()

    results = {}
    for key in which:
        res = publish_one(key, AGENTS[key], token, args.dry_run)
        if res:
            results[key] = res.get("name", "").split("/")[-1]

    if results and not args.dry_run:
        print("\n=== Published GE agent IDs ===")
        for key, aid in results.items():
            print(f"  {key}: {aid}")
        print("\nSet these to update in place next time, or just re-run (upsert is idempotent).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

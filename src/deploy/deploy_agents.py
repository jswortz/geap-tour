"""Deploy ADK agents to Vertex AI Agent Runtime with identity, gateway, and Memory Bank."""

import json
import os
import subprocess

import vertexai
from vertexai import agent_engines

from src.config import (
    GCP_PROJECT_ID,
    GCP_REGION,
    GCP_STAGING_BUCKET,
    OTEL_ENV_VARS,
    SEARCH_MCP_URL,
    BOOKING_MCP_URL,
    EXPENSE_MCP_URL,
    AGENT_GATEWAY_PATH,
    AGENT_GATEWAY_EGRESS_PATH,
    AGENT_ENGINE_ID,
    OPUS_MODEL,
    LITE_MODEL,
    FLASH_MODEL,
    COMPLEXITY_THRESHOLD_HIGH,
)

REQUIREMENTS = [
    "google-cloud-aiplatform[adk,agent_engines]>=1.88.0",
    "google-genai>=1.14.0",
    "fastmcp>=2.0.0",
    "python-dotenv>=1.0.0",
    "litellm>=1.0.0",
]

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _attach_gateway(resource_name: str) -> None:
    """Attach gateway config to a deployed agent via REST API (Private Preview).

    Tries v1beta1 first, falls back to v1. If the API doesn't support
    agentGatewayConfig yet (requires Private Preview), logs a note and continues.
    """
    gateway_config = {}
    if AGENT_GATEWAY_PATH:
        gateway_config["clientToAgentConfig"] = {"agentGateway": AGENT_GATEWAY_PATH}
    if AGENT_GATEWAY_EGRESS_PATH:
        gateway_config["agentToAnywhereConfig"] = {"agentGateway": AGENT_GATEWAY_EGRESS_PATH}
    if not gateway_config:
        return

    token = subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True
    ).strip()

    for api_version in ("v1beta1", "v1"):
        url = f"https://{GCP_REGION}-aiplatform.googleapis.com/{api_version}/{resource_name}"
        body = {"agentGatewayConfig": gateway_config}

        result = subprocess.run(
            ["curl", "-s", "-X", "PATCH", f"{url}?updateMask=agentGatewayConfig",
             "-H", f"Authorization: Bearer {token}",
             "-H", "Content-Type: application/json",
             "-d", json.dumps(body)],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout:
            resp = json.loads(result.stdout)
            if "error" not in resp:
                print(f"  Gateway attached ({api_version}): ingress={bool(AGENT_GATEWAY_PATH)}, egress={bool(AGENT_GATEWAY_EGRESS_PATH)}")
                return

    print("  Gateway attachment requires Private Preview enrollment — gateways exist but are not yet attached to this agent.")
    print(f"  Ingress: {AGENT_GATEWAY_PATH}")
    print(f"  Egress:  {AGENT_GATEWAY_EGRESS_PATH}")


def _memory_service_builder():
    """Build a VertexAiMemoryBankService for use with AdkApp.

    When deployed to Agent Runtime, the runtime automatically uses its own
    Memory Bank. This builder is used for local development and testing so
    that VertexAiMemoryBankService connects to the same backing store.
    """
    from google.adk.memory import VertexAiMemoryBankService
    return VertexAiMemoryBankService(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
        agent_engine_id=AGENT_ENGINE_ID,
    )


def deploy_agent(agent, display_name: str | None = None) -> str:
    """Deploy a single agent to Agent Runtime. Returns the resource name."""
    print(f"\n--- Deploying {agent.name} ---")

    env_vars = {
        **OTEL_ENV_VARS,
        "SEARCH_MCP_URL": SEARCH_MCP_URL,
        "BOOKING_MCP_URL": BOOKING_MCP_URL,
        "EXPENSE_MCP_URL": EXPENSE_MCP_URL,
        "AGENT_ENGINE_ID": AGENT_ENGINE_ID,
        "OPUS_MODEL": OPUS_MODEL,
        "LITE_MODEL": LITE_MODEL,
        "FLASH_MODEL": FLASH_MODEL,
        "COMPLEXITY_THRESHOLD_HIGH": str(COMPLEXITY_THRESHOLD_HIGH),
        "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "false",
    }

    remote = agent_engines.create(
        agent_engine=agent,
        requirements=REQUIREMENTS,
        display_name=display_name or agent.name,
        env_vars=env_vars,
        extra_packages=[os.path.join(SRC_DIR, "src")],
    )
    print(f"  {agent.name} deployed: {remote.resource_name}")
    print(f"  Memory Bank: enabled (engine_id={AGENT_ENGINE_ID})")

    if AGENT_GATEWAY_PATH or AGENT_GATEWAY_EGRESS_PATH:
        _attach_gateway(remote.resource_name)

    return remote.resource_name


AGENT_SETS = {
    "coordinator": lambda: __import__("src.agents.coordinator_agent", fromlist=["coordinator_agent"]).coordinator_agent,
    "router": lambda: __import__("src.router.agents", fromlist=["router_agent"]).router_agent,
}


def deploy_all_agents(agent_set: str = "all") -> dict[str, str]:
    """Deploy agents and return a map of name → resource name.

    Args:
        agent_set: "coordinator", "router", or "all" (default).
    """
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION, staging_bucket=f"gs://{GCP_STAGING_BUCKET}")

    if agent_set == "all":
        sets = list(AGENT_SETS.keys())
    else:
        sets = [s.strip() for s in agent_set.split(",")]

    deployed = {}
    for name in sets:
        loader = AGENT_SETS.get(name)
        if not loader:
            print(f"  Unknown agent set: {name}. Available: {list(AGENT_SETS)}")
            continue
        agent = loader()
        deployed[agent.name] = deploy_agent(agent)

    return deployed


if __name__ == "__main__":
    import sys
    agent_set = sys.argv[1] if len(sys.argv) > 1 else "all"
    deployed = deploy_all_agents(agent_set=agent_set)
    print("\n=== Deployed Agent Resource Names ===")
    for name, resource in deployed.items():
        print(f"  {name}: {resource}")

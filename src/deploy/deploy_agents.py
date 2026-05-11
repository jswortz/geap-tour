"""Deploy ADK agents to Vertex AI Agent Runtime with identity and gateway."""

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
)

REQUIREMENTS = [
    "google-cloud-aiplatform[adk,agent_engines]>=1.88.0",
    "google-genai>=1.14.0",
    "fastmcp>=2.0.0",
    "python-dotenv>=1.0.0",
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


def deploy_agent(agent, display_name: str | None = None) -> str:
    """Deploy a single agent to Agent Runtime. Returns the resource name."""
    print(f"\n--- Deploying {agent.name} ---")

    env_vars = {
        **OTEL_ENV_VARS,
        "SEARCH_MCP_URL": SEARCH_MCP_URL,
        "BOOKING_MCP_URL": BOOKING_MCP_URL,
        "EXPENSE_MCP_URL": EXPENSE_MCP_URL,
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

    if AGENT_GATEWAY_PATH or AGENT_GATEWAY_EGRESS_PATH:
        _attach_gateway(remote.resource_name)

    return remote.resource_name


def deploy_all_agents() -> dict[str, str]:
    """Deploy all agents and return a map of name → resource name."""
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION, staging_bucket=f"gs://{GCP_STAGING_BUCKET}")

    from src.agents.coordinator_agent import coordinator_agent
    agents = [coordinator_agent]
    deployed = {}

    for agent in agents:
        deployed[agent.name] = deploy_agent(agent)

    return deployed


if __name__ == "__main__":
    deployed = deploy_all_agents()
    print("\n=== Deployed Agent Resource Names ===")
    for name, resource in deployed.items():
        print(f"  {name}: {resource}")

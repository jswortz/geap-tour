"""Deploy ADK agents to Vertex AI Agent Runtime with identity, gateway, and telemetry.

Agent Gateway requires REGIONAL gateways for Agent Runtime agents (with a regional
Agent Registry) and GLOBAL gateways for Gemini Enterprise (with a global registry).
A single gateway cannot support both — they are mutually exclusive.

Gateway config (agent_gateway_config + identity_type) must be set at deploy time via
client.agent_engines.create(config=...). Key requirements:
  - identity_type must use vertexai._genai.types.IdentityType.AGENT_IDENTITY (the enum),
    NOT the string "AGENT_IDENTITY" — the string silently deploys without identity.
  - Egress-only gateway works; ingress-only (client_to_agent_config) fails with code 13.
  - Egress routes ALL outbound traffic through the gateway (MCP-only protocol), which
    breaks gRPC calls (create_session, model inference). MCP tool calls work fine.
"""

import os

import vertexai
from vertexai._genai import types

from src.config import (
    GCP_PROJECT_ID,
    GCP_REGION,
    GCP_STAGING_BUCKET,
    OTEL_ENV_VARS,
    SEARCH_MCP_URL,
    BOOKING_MCP_URL,
    EXPENSE_MCP_URL,
    SEARCH_MCP_SERVER,
    BOOKING_MCP_SERVER,
    EXPENSE_MCP_SERVER,
    AGENT_REGISTRY_LOCATION,
    AGENT_GATEWAY_PATH,
    AGENT_GATEWAY_EGRESS_PATH,
    AGENT_ENGINE_ID,
    OPUS_MODEL,
    LITE_MODEL,
    FLASH_MODEL,
    COMPLEXITY_THRESHOLD_HIGH,
)

REQUIREMENTS = [
    "google-cloud-aiplatform[adk,agent-engines]>=1.152.0",
    "google-genai>=1.66.0",
    "google-auth>=2.52.0",
    "google-adk[a2a,agent-identity]>=1.33.0",
    "a2a-sdk>=0.3.26",
    "google-cloud-iamconnectorcredentials>=0.1.0",
    "fastmcp>=2.0.0",
    "python-dotenv>=1.0.0",
    "litellm>=1.0.0",
    "pydantic>=2.11.1,<3",
    "cloudpickle>=3.0,<4.0",
]

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _build_gateway_config() -> dict | None:
    """Build agent_gateway_config for egress-only gateway attachment.

    Only egress (agent_to_anywhere_config) is supported. Ingress
    (client_to_agent_config) fails with code 13 at deploy time.
    """
    if not AGENT_GATEWAY_EGRESS_PATH:
        return None
    return {
        "agent_to_anywhere_config": {"agent_gateway": AGENT_GATEWAY_EGRESS_PATH},
    }


def deploy_agent(agent, display_name: str | None = None, attach_gateway: bool = True) -> str:
    """Deploy a single agent to Agent Runtime with gateway and identity.

    Uses vertexai.Client().agent_engines.create(config=...) with the v1beta1 API.
    identity_type MUST be the IdentityType enum, not a string.
    """
    os.chdir(PROJECT_ROOT)

    print(f"\n--- Deploying {agent.name} ---")

    env_vars = {
        **OTEL_ENV_VARS,
        "GCP_PROJECT_ID": GCP_PROJECT_ID,
        "GCP_REGION": GCP_REGION,
        "SEARCH_MCP_URL": SEARCH_MCP_URL,
        "BOOKING_MCP_URL": BOOKING_MCP_URL,
        "EXPENSE_MCP_URL": EXPENSE_MCP_URL,
        "AGENT_ENGINE_ID": AGENT_ENGINE_ID,
        "OPUS_MODEL": OPUS_MODEL,
        "LITE_MODEL": LITE_MODEL,
        "FLASH_MODEL": FLASH_MODEL,
        "COMPLEXITY_THRESHOLD_HIGH": str(COMPLEXITY_THRESHOLD_HIGH),
        "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "false",
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
        "GOOGLE_GENAI_USE_VERTEXAI": "1",
        "SEARCH_MCP_SERVER": SEARCH_MCP_SERVER,
        "BOOKING_MCP_SERVER": BOOKING_MCP_SERVER,
        "EXPENSE_MCP_SERVER": EXPENSE_MCP_SERVER,
        "AGENT_REGISTRY_LOCATION": AGENT_REGISTRY_LOCATION,
    }

    config = {
        "staging_bucket": f"gs://{GCP_STAGING_BUCKET}",
        "requirements": REQUIREMENTS,
        "display_name": display_name or agent.name,
        "env_vars": env_vars,
        "extra_packages": ["src"],
        "identity_type": types.IdentityType.AGENT_IDENTITY,
    }

    gateway_config = _build_gateway_config() if attach_gateway else None
    if gateway_config:
        config["agent_gateway_config"] = gateway_config

    client = vertexai.Client(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
        http_options=dict(api_version="v1beta1"),
    )
    remote = client.agent_engines.create(agent=agent, config=config)

    resource_name = remote.api_resource.name
    print(f"  {agent.name} deployed: {resource_name}")

    if gateway_config:
        print(f"  Gateway: egress={AGENT_GATEWAY_EGRESS_PATH}")
        print("  Identity: AGENT_IDENTITY (SPIFFE-based)")
    else:
        print("  Gateway: not configured")
        print("  Identity: AGENT_IDENTITY (SPIFFE-based)")

    return resource_name


AGENT_SETS = {
    "coordinator": {
        "loader": lambda: __import__("src.agents.coordinator_agent", fromlist=["coordinator_agent"]).coordinator_agent,
        "attach_gateway": True,
    },
    "router": {
        "loader": lambda: __import__("src.router.agents", fromlist=["router_agent"]).router_agent,
        "attach_gateway": True,
    },
}


def deploy_all_agents(agent_set: str = "all") -> dict[str, str]:
    """Deploy agents and return a map of name -> resource name.

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
        entry = AGENT_SETS.get(name)
        if not entry:
            print(f"  Unknown agent set: {name}. Available: {list(AGENT_SETS)}")
            continue
        agent = entry["loader"]()
        deployed[agent.name] = deploy_agent(agent, attach_gateway=entry["attach_gateway"])

    return deployed


if __name__ == "__main__":
    import sys
    agent_set = sys.argv[1] if len(sys.argv) > 1 else "all"
    deployed = deploy_all_agents(agent_set=agent_set)
    print("\n=== Deployed Agent Resource Names ===")
    for name, resource in deployed.items():
        print(f"  {name}: {resource}")

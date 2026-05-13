"""Deploy ADK agents to Vertex AI Agent Runtime with identity, gateway, and Memory Bank."""

import os

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


def _build_gateway_config() -> dict | None:
    """Build the agent_gateway_config dict for agent_engines.create().

    Gateway attachment happens at deploy time via the config parameter,
    not via post-deploy PATCH. The egress gateway must have a registries
    link to the regional Agent Registry for agent discovery.
    """
    gateway_config = {}
    if AGENT_GATEWAY_EGRESS_PATH:
        gateway_config["agent_to_anywhere_config"] = {"agent_gateway": AGENT_GATEWAY_EGRESS_PATH}
    if AGENT_GATEWAY_PATH:
        gateway_config["client_to_agent_config"] = {"agent_gateway": AGENT_GATEWAY_PATH}
    return gateway_config or None


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
    """Deploy a single agent to Agent Runtime with gateway and identity.

    Gateway config and AGENT_IDENTITY are passed at create time via the
    config parameter per the Agent Gateway SDK docs.
    """
    from google.genai import types

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

    # Build create() config — gateway + identity are set here, not post-deploy
    create_config = {
        "requirements": REQUIREMENTS,
        "display_name": display_name or agent.name,
        "env_vars": env_vars,
        "extra_packages": [os.path.join(SRC_DIR, "src")],
    }

    gateway_config = _build_gateway_config()
    if gateway_config:
        create_config["agent_gateway_config"] = gateway_config
        create_config["identity_type"] = types.IdentityType.AGENT_IDENTITY

    remote = agent_engines.create(
        agent_engine=agent,
        **create_config,
    )
    print(f"  {agent.name} deployed: {remote.resource_name}")
    print(f"  Memory Bank: enabled (engine_id={AGENT_ENGINE_ID})")

    if gateway_config:
        print(f"  Gateway: ingress={bool(AGENT_GATEWAY_PATH)}, egress={bool(AGENT_GATEWAY_EGRESS_PATH)}")
        print(f"  Identity: AGENT_IDENTITY (SPIFFE-based)")
    else:
        print(f"  Gateway: not configured (set AGENT_GATEWAY_PATH / AGENT_GATEWAY_EGRESS_PATH)")

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

"""Deploy ADK agents to Vertex AI Agent Runtime with identity, gateway, and Memory Bank.

Agent Gateway requires REGIONAL gateways for Agent Runtime agents (with a regional
Agent Registry) and GLOBAL gateways for Gemini Enterprise (with a global registry).
A single gateway cannot support both — they are mutually exclusive.

Gateway config (agent_gateway_config + identity_type) must be set at deploy time via
agent_engines.create(). It cannot be PATCHed onto existing agents.
"""

import os

import vertexai

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
    # Server-side cloudpickle unpickle needs google.auth._regional_access_boundary_utils
    # which was added in google-auth 2.52.0. The base image ships an older version.
    "google-auth>=2.52.0",
    "google-adk[a2a,agent-identity]>=1.33.0",
    "a2a-sdk>=0.3.26",
    "google-cloud-iamconnectorcredentials>=0.1.0",
    "google-genai>=1.14.0",
    "fastmcp>=2.0.0",
    "python-dotenv>=1.0.0",
    "litellm>=1.0.0",
    "pydantic>=2.11.1,<3",
    "cloudpickle>=3.0,<4.0",
]

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _build_gateway_config() -> dict | None:
    """Build the agent_gateway_config dict for agent_engines.create().

    Gateway attachment happens at deploy time via the config parameter,
    not via post-deploy PATCH. The egress gateway must have a registries
    link to the regional Agent Registry for agent discovery.
    """
    if not AGENT_GATEWAY_EGRESS_PATH:
        return None
    # Only egress (agent_to_anywhere_config) is used at deploy time.
    # Ingress (client_to_agent_config) is handled by the gateway's registry link.
    return {"agent_to_anywhere_config": {"agent_gateway": AGENT_GATEWAY_EGRESS_PATH}}


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

    Uses vertexai.Client().agent_engines.create(config=...) which exposes
    agent_gateway_config and identity_type. The high-level
    vertexai.agent_engines.create() wrapper does not expose these fields.
    """
    # SDK tar.add() preserves paths — must run from project root so that
    # extra_packages="src" ends up as "src/" in the tarball.
    os.chdir(PROJECT_ROOT)

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

    config = {
        "staging_bucket": f"gs://{GCP_STAGING_BUCKET}",
        "requirements": REQUIREMENTS,
        "display_name": display_name or agent.name,
        "env_vars": env_vars,
        "extra_packages": ["src"],
    }

    gateway_config = _build_gateway_config()
    if gateway_config:
        config["agent_gateway_config"] = gateway_config
    # AGENT_IDENTITY gives SPIFFE credentials independent of gateway attachment.
    # Gateway config routes agent-to-tool traffic; identity controls auth.
    if gateway_config or os.environ.get("ENABLE_AGENT_IDENTITY"):
        config["identity_type"] = "AGENT_IDENTITY"

    client = vertexai.Client(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
        http_options=dict(api_version="v1beta1"),
    )
    remote = client.agent_engines.create(agent=agent, config=config)

    resource_name = remote.api_resource.name
    print(f"  {agent.name} deployed: {resource_name}")
    print(f"  Memory Bank: enabled (engine_id={AGENT_ENGINE_ID})")

    if gateway_config:
        print(f"  Gateway: ingress={bool(AGENT_GATEWAY_PATH)}, egress={bool(AGENT_GATEWAY_EGRESS_PATH)}")
        print("  Identity: AGENT_IDENTITY (SPIFFE-based)")
    else:
        print("  Gateway: not configured (set AGENT_GATEWAY_PATH / AGENT_GATEWAY_EGRESS_PATH)")

    return resource_name


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

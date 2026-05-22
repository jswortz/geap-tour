"""
Deploy ADK agents to Vertex AI Agent Runtime with identity, gateway, and Memory Bank.

Usage:
  # Deploy new agents
  uv run python -m src.deploy.deploy_agents router
  uv run python -m src.deploy.deploy_agents coordinator
  uv run python -m src.deploy.deploy_agents all

  # Update existing agents (uses engine IDs from .env)
  uv run python -m src.deploy.deploy_agents router --update
  uv run python -m src.deploy.deploy_agents coordinator --update
  uv run python -m src.deploy.deploy_agents all --update

Controlled by .env:
  - ENABLE_AGENT_IDENTITY=1 → sets SPIFFE identity
  - ENABLE_AGENT_GATEWAY=1 → attaches gateway (requires early-access)
"""

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
    SEARCH_MCP_SERVER,
    BOOKING_MCP_SERVER,
    EXPENSE_MCP_SERVER,
    AGENT_REGISTRY_LOCATION,
    AGENT_GATEWAY_PATH,
    AGENT_GATEWAY_EGRESS_PATH,
    AGENT_ENGINE_ID,
    OPUS_MODEL,
    SONNET_MODEL,
    PRO_MODEL,
    LITE_MODEL,
    FLASH_MODEL,
    COMPLEXITY_THRESHOLD_HIGH,
)

REQUIREMENTS = [
    "google-cloud-aiplatform[adk,agent-engines,evaluation]>=1.153.1",
    "google-genai>=1.66.0",
    "google-auth>=2.52.0",
    "google-adk[a2a, agent-identity]>=1.33.0",
    "fastmcp>=2.0.0",
    "python-dotenv>=1.0.0",
    "litellm>=1.83.14",
    "a2a-sdk==0.3.26",
    "pydantic>=2.12.5",
    "cloudpickle>=3.0,<4.0",
    # "google-cloud-iamconnectorcredentials>=0.1.0",
]

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


ENABLE_AGENT_IDENTITY = os.environ.get("ENABLE_AGENT_IDENTITY", "0") in ("1", "true")
ENABLE_AGENT_GATEWAY = os.environ.get("ENABLE_AGENT_GATEWAY", "0") in ("1", "true")


def _build_gateway_config() -> dict | None:
    """Build the agent_gateway_config dict for agent_engines.create().

    Requires ENABLE_AGENT_GATEWAY=1 in .env — gateway integration needs
    early-access activation on the GCP project. Without it, deploy fails
    with FAILED_PRECONDITION.
    """
    if not ENABLE_AGENT_GATEWAY or not AGENT_GATEWAY_EGRESS_PATH:
        return None
    return {
        "agent_to_anywhere_config": {
            "agent_gateway": AGENT_GATEWAY_EGRESS_PATH
        }
    }


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


def _build_config(agent, display_name: str | None = None) -> dict:
    """Build the deployment config dict used for both create and update."""
    env_vars = {
        **OTEL_ENV_VARS,
        "GCP_PROJECT_ID": GCP_PROJECT_ID,
        "GCP_REGION": GCP_REGION,
        "SEARCH_MCP_URL": SEARCH_MCP_URL,
        "BOOKING_MCP_URL": BOOKING_MCP_URL,
        "EXPENSE_MCP_URL": EXPENSE_MCP_URL,
        "AGENT_ENGINE_ID": AGENT_ENGINE_ID,
        "OPUS_MODEL": OPUS_MODEL,
        "SONNET_MODEL": SONNET_MODEL,
        "PRO_MODEL": PRO_MODEL,
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
    }

    if ENABLE_AGENT_IDENTITY:
        config["identity_type"] = "AGENT_IDENTITY"
        print("  Identity: AGENT_IDENTITY (SPIFFE-based)")
    else:
        print("  Identity: default (set ENABLE_AGENT_IDENTITY=1 to enable)")

    gateway_config = _build_gateway_config()
    if gateway_config:
        config["agent_gateway_config"] = gateway_config
        print(f"  Gateway: egress={AGENT_GATEWAY_EGRESS_PATH}")
    else:
        if not ENABLE_AGENT_GATEWAY:
            print("  Gateway: disabled (set ENABLE_AGENT_GATEWAY=1 to enable)")
        else:
            print("  Gateway: not configured (set AGENT_GATEWAY_EGRESS_PATH)")

    return config


def _get_client():
    return vertexai.Client(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
        # http_options=dict(api_version="v1beta1"),
    )


def deploy_agent(agent, display_name: str | None = None) -> str:
    """Create a new agent on Agent Runtime."""
    os.chdir(PROJECT_ROOT)
    print(f"\n--- Creating {agent.name} ---")
    config = _build_config(agent, display_name)

    remote = _get_client().agent_engines.create(agent=agent, config=config)
    resource_name = getattr(remote, 'resource_name', None) or remote.api_resource.name
    print(f"  Created: {resource_name}")
    return resource_name


def update_agent(agent, engine_id: str, display_name: str | None = None) -> str:
    """Update an existing agent on Agent Runtime."""
    os.chdir(PROJECT_ROOT)
    # Accept bare ID or full resource name
    if not engine_id.startswith("projects/"):
        engine_id = f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/reasoningEngines/{engine_id}"
    print(f"\n--- Updating {agent.name} ({engine_id.split('/')[-1]}) ---")
    config = _build_config(agent, display_name)

    remote = _get_client().agent_engines.update(
        name=engine_id,
        agent=agent,
        config=config,
    )
    resource_name = getattr(remote, 'resource_name', None) or remote.api_resource.name
    print(f"  Updated: {resource_name}")
    return resource_name


COORDINATOR_ENGINE_ID = os.environ.get("COORDINATOR_AGENT_ID", "")
ROUTER_ENGINE_ID_ENV = os.environ.get("ROUTER_ENGINE_ID", os.environ.get("AGENT_ENGINE_ID", ""))
LITE_ENGINE_ID = os.environ.get("LITE_ENGINE_ID", "")
FLASH_ENGINE_ID = os.environ.get("FLASH_ENGINE_ID", "")
PRO_ENGINE_ID = os.environ.get("PRO_ENGINE_ID", "")
SONNET_ENGINE_ID = os.environ.get("SONNET_ENGINE_ID", "")
OPUS_ENGINE_ID = os.environ.get("OPUS_ENGINE_ID", "")

AGENT_SETS = {
    "coordinator": {
        "loader": lambda: __import__("src.agents.coordinator_agent", fromlist=["coordinator_agent"]).coordinator_agent,
        "engine_id": COORDINATOR_ENGINE_ID,
        "env_var": "COORDINATOR_AGENT_ID",
    },
    "router": {
        "loader": lambda: __import__("src.router.agents", fromlist=["router_agent"]).router_agent,
        "engine_id": ROUTER_ENGINE_ID_ENV,
        "env_var": "ROUTER_ENGINE_ID",
    },
    "lite": {
        "loader": lambda: __import__("src.agents.lite_agent", fromlist=["lite_agent"]).lite_agent,
        "engine_id": LITE_ENGINE_ID,
        "env_var": "LITE_ENGINE_ID",
    },
    "flash": {
        "loader": lambda: __import__("src.agents.flash_agent", fromlist=["flash_agent"]).flash_agent,
        "engine_id": FLASH_ENGINE_ID,
        "env_var": "FLASH_ENGINE_ID",
    },
    "pro": {
        "loader": lambda: __import__("src.agents.pro_agent", fromlist=["pro_agent"]).pro_agent,
        "engine_id": PRO_ENGINE_ID,
        "env_var": "PRO_ENGINE_ID",
    },
    "sonnet": {
        "loader": lambda: __import__("src.agents.sonnet_agent", fromlist=["sonnet_agent"]).sonnet_agent,
        "engine_id": SONNET_ENGINE_ID,
        "env_var": "SONNET_ENGINE_ID",
    },
    "opus": {
        "loader": lambda: __import__("src.agents.opus_agent", fromlist=["opus_agent"]).opus_agent,
        "engine_id": OPUS_ENGINE_ID,
        "env_var": "OPUS_ENGINE_ID",
    },
}


def _update_env_file(env_var: str, value: str):
    """Update or append a variable in the .env file."""
    engine_id = value.split("/")[-1]
    lines = []
    found = False
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{env_var}="):
                lines[i] = f"{env_var}={engine_id}\n"
                found = True
                break
    if not found:
        lines.append(f"{env_var}={engine_id}\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)
    print(f"  .env updated: {env_var}={engine_id}")


def run_deploy(agent_set: str = "all", update: bool = False) -> dict[str, str]:
    """Deploy or update agents and return a map of name → resource name.

    Args:
        agent_set: "coordinator", "router", or "all" (default).
        update: If True, update existing agents using engine IDs from .env.
                If False, create new agents.
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

        if update:
            engine_id = entry["engine_id"]
            if not engine_id:
                print(f"  No engine ID for {name} — set {entry['env_var']} in .env")
                continue
            deployed[agent.name] = update_agent(agent, engine_id)
        else:
            resource_name = deploy_agent(agent)
            deployed[agent.name] = resource_name
            _update_env_file(entry["env_var"], resource_name)

    return deployed


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Deploy or update ADK agents on Agent Engine")
    parser.add_argument("agent_set", nargs="?", default="all", help="coordinator, router, or all (default: all)")
    parser.add_argument("--update", action="store_true", help="Update existing agents instead of creating new ones")
    args = parser.parse_args()

    deployed = run_deploy(agent_set=args.agent_set, update=args.update)
    print("\n=== Agent Resource Names ===")
    for name, resource in deployed.items():
        print(f"  {name}: {resource}")

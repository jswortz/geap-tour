"""Deploy ADK agents to Vertex AI Agent Runtime with identity and gateway."""

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
)

REQUIREMENTS = [
    "google-cloud-aiplatform[adk,agent_engines]>=1.88.0",
    "google-genai>=1.14.0",
    "fastmcp>=2.0.0",
    "python-dotenv>=1.0.0",
]

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


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

    config = {}
    gateway_config = {}
    if AGENT_GATEWAY_PATH:
        gateway_config["client_to_agent_config"] = {"agent_gateway": AGENT_GATEWAY_PATH}
    if AGENT_GATEWAY_EGRESS_PATH:
        gateway_config["agent_to_anywhere_config"] = {"agent_gateway": AGENT_GATEWAY_EGRESS_PATH}
    if gateway_config:
        config["agent_gateway_config"] = gateway_config
        config["identity_type"] = "AGENT_IDENTITY"
        print(f"  Gateway config: ingress={bool(AGENT_GATEWAY_PATH)}, egress={bool(AGENT_GATEWAY_EGRESS_PATH)}")

    create_kwargs = dict(
        agent_engine=agent,
        requirements=REQUIREMENTS,
        display_name=display_name or agent.name,
        env_vars=env_vars,
        extra_packages=[os.path.join(SRC_DIR, "src")],
    )
    if config:
        create_kwargs["config"] = config

    remote = agent_engines.create(**create_kwargs)
    print(f"✓ {agent.name} deployed: {remote.resource_name}")
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

"""Deploy ADK agents to Vertex AI Agent Runtime with identity and gateway."""

from google import genai
from google.genai import types
from google.adk.app import AdkApp

from src.config import (
    GCP_PROJECT_ID,
    GCP_REGION,
    GCP_STAGING_BUCKET,
    AGENT_GATEWAY_PATH,
    OTEL_ENV_VARS,
)
from src.agents.travel_agent import travel_agent
from src.agents.expense_agent import expense_agent
from src.agents.coordinator_agent import coordinator_agent

REQUIREMENTS = [
    "google-cloud-aiplatform[adk,agent_engines]>=1.88.0",
    "google-genai>=1.14.0",
    "fastmcp>=2.0.0",
    "python-dotenv>=1.0.0",
]


def deploy_agent(client: genai.Client, agent, enable_identity: bool = True) -> str:
    """Deploy a single agent to Agent Runtime. Returns the resource name."""
    app = AdkApp(agent=agent, enable_tracing=True)
    print(f"\n--- Deploying {agent.name} ---")

    config = {
        "requirements": REQUIREMENTS,
        "staging_bucket": f"gs://{GCP_STAGING_BUCKET}",
        "env_vars": OTEL_ENV_VARS,
    }

    if enable_identity:
        config["identity_type"] = types.IdentityType.AGENT_IDENTITY

    if AGENT_GATEWAY_PATH:
        config["agent_gateway_config"] = {
            "agent_to_anywhere_config": {
                "agent_gateway": AGENT_GATEWAY_PATH,
            }
        }

    remote_app = client.agent_engines.create(agent=app, config=config)
    print(f"✓ {agent.name} deployed: {remote_app.name}")
    return remote_app.name


def deploy_all_agents() -> dict[str, str]:
    """Deploy all agents and return a map of name → resource name."""
    client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )

    agents = [travel_agent, expense_agent, coordinator_agent]
    deployed = {}

    for agent in agents:
        deployed[agent.name] = deploy_agent(client, agent)

    return deployed


if __name__ == "__main__":
    deployed = deploy_all_agents()
    print("\n=== Deployed Agent Resource Names ===")
    for name, resource in deployed.items():
        print(f"  {name}: {resource}")

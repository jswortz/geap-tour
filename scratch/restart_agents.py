import os
import vertexai
from src.config import GCP_PROJECT_ID, GCP_REGION, GCP_STAGING_BUCKET, AGENT_ENGINE_ID, ROUTER_ENGINE_ID
from src.deploy.deploy_agents import REQUIREMENTS, AGENT_SETS, _build_gateway_config, PROJECT_ROOT

def restart_agents():
    # SDK tar.add() preserves paths — must run from project root so that
    # extra_packages="src" ends up as "src/" in the tarball.
    os.chdir(PROJECT_ROOT)
    
    client = vertexai.Client(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
        http_options=dict(api_version="v1beta1"),
    )
    
    # 1. Update Coordinator
    print(f"Restarting coordinator agent ({AGENT_ENGINE_ID}) in-place...")
    coordinator_agent = AGENT_SETS["coordinator"]()
    
    # Rebuild env_vars (same as deploy_agents.py, no AGENT_ENGINE_ID)
    from src.config import SEARCH_MCP_URL, BOOKING_MCP_URL, EXPENSE_MCP_URL, OPUS_MODEL, LITE_MODEL, FLASH_MODEL, COMPLEXITY_THRESHOLD_HIGH
    from src.deploy.deploy_agents import OTEL_ENV_VARS
    env_vars = {
        **OTEL_ENV_VARS,
        "PYTHONPATH": "/code/src",
        "GOOGLE_API_USE_CLIENT_CERTIFICATE": "false",
        "SEARCH_MCP_URL": SEARCH_MCP_URL,
        "BOOKING_MCP_URL": BOOKING_MCP_URL,
        "EXPENSE_MCP_URL": EXPENSE_MCP_URL,
        "OPUS_MODEL": OPUS_MODEL,
        "LITE_MODEL": LITE_MODEL,
        "FLASH_MODEL": FLASH_MODEL,
        "COMPLEXITY_THRESHOLD_HIGH": str(COMPLEXITY_THRESHOLD_HIGH),
        "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "false",
    }
    
    config = {
        "staging_bucket": f"gs://{GCP_STAGING_BUCKET}",
        "requirements": REQUIREMENTS,
        "display_name": coordinator_agent.name,
        "env_vars": env_vars,
        "extra_packages": ["src"],
    }
    
    gateway_config = _build_gateway_config()
    if gateway_config:
        config["agent_gateway_config"] = gateway_config
    if gateway_config or os.environ.get("ENABLE_AGENT_IDENTITY") or True: # Force AGENT_IDENTITY
        config["identity_type"] = "AGENT_IDENTITY"
        
    client.agent_engines.update(
        name=f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/reasoningEngines/{AGENT_ENGINE_ID}",
        agent=coordinator_agent,
        config=config
    )
    print("Coordinator restart complete.")

if __name__ == "__main__":
    restart_agents()

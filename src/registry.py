"""Agent Registry integration — discovers MCP servers by registered name."""

from google.adk.integrations.agent_registry import AgentRegistry

from src.config import GCP_PROJECT_ID, AGENT_REGISTRY_LOCATION

_registry = None


def get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry(
            project_id=GCP_PROJECT_ID, location=AGENT_REGISTRY_LOCATION
        )
    return _registry


def get_mcp_tools(server_name: str):
    return get_registry().get_mcp_toolset(server_name)

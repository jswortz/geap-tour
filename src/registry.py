"""Agent Registry integration — discovers MCP servers by registered name.

Falls back to direct Cloud Run URLs when the Agent Registry entry is not found.
"""

import logging

from google.adk.integrations.agent_registry import AgentRegistry
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

from src.config import GCP_PROJECT_ID, AGENT_REGISTRY_LOCATION, MCP_SERVER_URLS

log = logging.getLogger(__name__)

# Default 5s is too short for Cloud Run MCP servers behind IAP/networking
MCP_TIMEOUT_SECONDS = 60.0

_registry = None


def get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry(
            project_id=GCP_PROJECT_ID, location=AGENT_REGISTRY_LOCATION
        )
    return _registry


def get_mcp_tools(server_name: str):
    try:
        toolset = get_registry().get_mcp_toolset(server_name)
        # Agent Registry uses default 5s timeout — override for Cloud Run
        if hasattr(toolset, '_connection_params') and hasattr(toolset._connection_params, 'timeout'):
            toolset._connection_params.timeout = MCP_TIMEOUT_SECONDS
        return toolset
    except RuntimeError:
        url = MCP_SERVER_URLS.get(server_name)
        if not url:
            raise
        log.info("Agent Registry unavailable for %s — using direct URL %s", server_name, url)
        return McpToolset(connection_params=StreamableHTTPConnectionParams(
            url=url, timeout=MCP_TIMEOUT_SECONDS
        ))

"""Agent Registry integration — discovers MCP servers by registered name.

Falls back to direct Cloud Run URLs when the Agent Registry entry is not found.
"""

import logging

from google.adk.integrations.agent_registry import AgentRegistry
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

from src.config import GCP_PROJECT_ID, AGENT_REGISTRY_LOCATION, MCP_SERVER_URLS

log = logging.getLogger(__name__)

# Default 5s connection / 300s read is too slow for Cloud Run MCP servers
MCP_TIMEOUT_SECONDS = 60.0
MCP_READ_TIMEOUT_SECONDS = 90.0

_registry = None


def get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry(
            project_id=GCP_PROJECT_ID, location=AGENT_REGISTRY_LOCATION
        )
    return _registry


def get_mcp_tools(server_name: str):
    """Return an MCP toolset, preferring Agent Registry discovery.

    When running behind Agent Gateway, the registry routes MCP traffic
    through the gateway for governance. Falls back to direct SSE URLs
    if the registry is unavailable.
    """
    try:
        toolset = get_registry().get_mcp_toolset(server_name)
        # Agent Registry uses default 5s/300s — override for Cloud Run
        if hasattr(toolset, '_connection_params'):
            if hasattr(toolset._connection_params, 'timeout'):
                toolset._connection_params.timeout = MCP_TIMEOUT_SECONDS
            if hasattr(toolset._connection_params, 'sse_read_timeout'):
                toolset._connection_params.sse_read_timeout = MCP_READ_TIMEOUT_SECONDS
        return toolset
    except (RuntimeError, Exception):
        url = MCP_SERVER_URLS.get(server_name)
        if not url:
            raise
        log.info("Agent Registry unavailable for %s — using direct URL %s", server_name, url)
        return McpToolset(connection_params=StreamableHTTPConnectionParams(
            url=url, timeout=MCP_TIMEOUT_SECONDS, sse_read_timeout=MCP_READ_TIMEOUT_SECONDS
        ))

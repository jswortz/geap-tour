"""MCP tool integration — connects to MCP tool servers for agent use.

Provides two modes:
  1. MCPToolset (default) — connects directly to MCP server URLs via SSE.
     No import-chain issues during cloudpickle unpickle on Agent Runtime.
  2. AgentRegistry — discovers MCP servers by registered name.
     Triggers the a2a-sdk / iamconnectorcredentials import chain which is
     not available in the Agent Runtime base image.
"""

import os
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseConnectionParams

from src.config import (
    SEARCH_MCP_URL,
    BOOKING_MCP_URL,
    EXPENSE_MCP_URL,
    SEARCH_MCP_SERVER,
    BOOKING_MCP_SERVER,
    EXPENSE_MCP_SERVER,
)

# Map Agent Registry server names → environment-variable MCP URLs.
_SERVER_URL_MAP = {
    SEARCH_MCP_SERVER: SEARCH_MCP_URL,
    BOOKING_MCP_SERVER: BOOKING_MCP_URL,
    EXPENSE_MCP_SERVER: EXPENSE_MCP_URL,
}


def get_mcp_tools(server_name: str) -> MCPToolset:
    """Return an MCPToolset for the given server, using SSE transport."""
    url = _SERVER_URL_MAP.get(server_name)
    if not url:
        raise ValueError(
            f"Unknown MCP server: {server_name}. "
            f"Known: {list(_SERVER_URL_MAP)}"
        )
    return MCPToolset(connection_params=SseConnectionParams(url=url))

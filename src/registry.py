"""Agent Registry integration — discovers MCP servers by registered name.

Falls back to direct Cloud Run URLs when the Agent Registry entry is not found.
"""

import logging
import os
import threading
import time
from urllib.parse import urlsplit

from google.adk.integrations.agent_registry import AgentRegistry
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

from src.config import GCP_PROJECT_ID, AGENT_REGISTRY_LOCATION, MCP_SERVER_URLS

log = logging.getLogger(__name__)

# Default 5s connection / 300s read is too slow for Cloud Run MCP servers
MCP_TIMEOUT_SECONDS = 60.0
MCP_READ_TIMEOUT_SECONDS = 90.0

# --- Authenticated MCP access (private Cloud Run) ------------------------------
# The MCP servers run on Cloud Run under an org that enforces Domain-Restricted
# Sharing, so they can't be made public (no allUsers). Callers must present an
# OIDC ID token whose audience is the service's root URL. Both the deployed
# Reasoning Engine service account and local dev (GCE metadata SA) mint one via
# the ambient credentials — google.oauth2.id_token.fetch_id_token(). This is the
# documented ADK pattern: McpToolset(header_provider=...) injects the Bearer
# header at session/tool-call time. Grant the caller SA roles/run.invoker.
_token_cache: dict[str, tuple[str, float]] = {}
_token_lock = threading.Lock()


def _mint_id_token(audience: str) -> str:
    """Mint (and cache ~50 min) an OIDC ID token for a Cloud Run audience."""
    now = time.time()
    with _token_lock:
        tok, exp = _token_cache.get(audience, (None, 0.0))
        if tok and exp - now > 300:
            return tok
    import google.oauth2.id_token as _id_token
    from google.auth.transport.requests import Request as _AuthRequest
    token = _id_token.fetch_id_token(_AuthRequest(), audience)
    with _token_lock:
        _token_cache[audience] = (token, now + 3000)
    return token


def _bearer_header_provider(url: str):
    """ADK McpToolset header_provider adding a Bearer ID token for `url`'s service."""
    parts = urlsplit(url)
    audience = f"{parts.scheme}://{parts.netloc}"

    def _provider(_ctx=None):
        try:
            return {"Authorization": f"Bearer {_mint_id_token(audience)}"}
        except Exception as e:  # noqa: BLE001 — never break tool loading on token issues
            log.warning("Could not mint ID token for %s: %s", audience, e)
            return {}

    return _provider


def _direct_toolset(url: str) -> McpToolset:
    """Build an McpToolset that connects straight to a (private) Cloud Run MCP URL,
    authenticating each session/tool call with an ID token via header_provider."""
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=url, timeout=MCP_TIMEOUT_SECONDS, sse_read_timeout=MCP_READ_TIMEOUT_SECONDS
        ),
        header_provider=_bearer_header_provider(url),
    )


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

    Opt-in (MCP_USE_DIRECT_URLS=1): connect straight to the MCP server's HTTPS
    URL instead of the Agent Registry. The registry path requests mTLS, which
    isn't available in every environment and (unlike a registry-construction
    error) fails only at session time, so the try/except below can't fall back
    from it. Setting this env var bakes the reliable direct-URL toolset at build
    time. URLs come from MCP_SERVER_URLS (the *_MCP_URL env vars). This mirrors
    src/agents/coordinator/agent.py::_get_mcp_tools.
    """
    if os.environ.get("MCP_USE_DIRECT_URLS") == "1":
        url = MCP_SERVER_URLS.get(server_name)
        if url:
            return _direct_toolset(url)
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
        return _direct_toolset(url)

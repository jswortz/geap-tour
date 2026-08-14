"""GEAP Coordinator Agent — self-contained module for ADK CLI deployment.

Integrates Vertex AI Agent Engine Memory Bank so the agent remembers user
interactions (past bookings, expense submissions, preferences) across sessions.
"""

import os
import re

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.integrations.agent_registry import AgentRegistry
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai.types import Content, Part

AGENT_MODEL = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")


def _resolve_model(model_str: str):
    """Gemini 2.x / models/* pass through (regional). Gemini 3.x is global-only, so use the
    NATIVE Gemini path pinned to global via client_kwargs (LiteLLM garbles Gemini-3 thought
    signatures into bogus tool calls). Claude/other -> LiteLlm global. Mirrors
    src/agents/_shared.resolve_model (this package is self-contained by design)."""
    if model_str.startswith(("gemini-2", "models/")):
        return model_str
    if model_str.startswith("gemini-"):
        from google.adk.models.google_llm import Gemini
        client_kwargs = {"vertexai": True, "location": "global"}
        # Prefer the module's resolved GCP_PROJECT_ID (from .env) over the ambient
        # GOOGLE_CLOUD_PROJECT, which on some dev machines points at a different project.
        proj = GCP_PROJECT_ID or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if proj:
            client_kwargs["project"] = proj
        return Gemini(model=model_str, client_kwargs=client_kwargs)
    from google.adk.models.lite_llm import LiteLlm
    if not model_str.startswith("vertex_ai/"):
        model_str = f"vertex_ai/{model_str}"
    return LiteLlm(model=model_str, vertex_location="global")

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "wortz-project-352116")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")
AGENT_ENGINE_ID = os.environ.get("AGENT_ENGINE_ID", "2479350891879071744")
AGENT_REGISTRY_LOCATION = os.environ.get("AGENT_REGISTRY_LOCATION", "us-central1")
SEARCH_MCP_SERVER = os.environ.get("SEARCH_MCP_SERVER",
    f"projects/{GCP_PROJECT_ID}/locations/us-central1/mcpServers/agentregistry-00000000-0000-0000-4bce-24e82cd98045")
BOOKING_MCP_SERVER = os.environ.get("BOOKING_MCP_SERVER",
    f"projects/{GCP_PROJECT_ID}/locations/us-central1/mcpServers/agentregistry-00000000-0000-0000-f126-e49a4e2ae9c9")
EXPENSE_MCP_SERVER = os.environ.get("EXPENSE_MCP_SERVER",
    f"projects/{GCP_PROJECT_ID}/locations/us-central1/mcpServers/agentregistry-00000000-0000-0000-1089-2fb19b9297d7")

SEARCH_MCP_URL = os.environ.get("SEARCH_MCP_URL", "http://localhost:8001/mcp")
BOOKING_MCP_URL = os.environ.get("BOOKING_MCP_URL", "http://localhost:8002/mcp")
EXPENSE_MCP_URL = os.environ.get("EXPENSE_MCP_URL", "http://localhost:8003/mcp")

MCP_SERVER_URLS = {
    SEARCH_MCP_SERVER: SEARCH_MCP_URL,
    BOOKING_MCP_SERVER: BOOKING_MCP_URL,
    EXPENSE_MCP_SERVER: EXPENSE_MCP_URL,
}

MCP_TIMEOUT_SECONDS = 60.0
MCP_READ_TIMEOUT_SECONDS = 90.0

# Authenticated access to private Cloud Run MCP servers (org Domain-Restricted Sharing blocks
# allUsers). Mint an OIDC ID token for the service root URL via the ambient SA and inject it as a
# Bearer header at session/tool-call time. Mirrors src/registry.py; grant the caller SA run.invoker.
import threading as _threading
import time as _time
from urllib.parse import urlsplit as _urlsplit

_id_token_cache: dict = {}
_id_token_lock = _threading.Lock()


def _mint_id_token(audience: str) -> str:
    now = _time.time()
    with _id_token_lock:
        tok, exp = _id_token_cache.get(audience, (None, 0.0))
        if tok and exp - now > 300:
            return tok
    import google.oauth2.id_token as _idt
    from google.auth.transport.requests import Request as _AuthRequest
    token = _idt.fetch_id_token(_AuthRequest(), audience)
    with _id_token_lock:
        _id_token_cache[audience] = (token, now + 3000)
    return token


def _bearer_header_provider(url: str):
    parts = _urlsplit(url)
    audience = f"{parts.scheme}://{parts.netloc}"

    def _provider(_ctx=None):
        try:
            return {"Authorization": f"Bearer {_mint_id_token(audience)}"}
        except Exception:
            return {}

    return _provider


def _direct_toolset(url: str) -> McpToolset:
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=url, timeout=MCP_TIMEOUT_SECONDS, sse_read_timeout=MCP_READ_TIMEOUT_SECONDS
        ),
        header_provider=_bearer_header_provider(url),
    )


_registry = None

def _get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry(project_id=GCP_PROJECT_ID, location=AGENT_REGISTRY_LOCATION)
    return _registry

def _get_mcp_tools(server_name: str):
    # Opt-in (MCP_USE_DIRECT_URLS=1): connect straight to the MCP server's HTTP URL instead of going
    # through the Agent Registry. The registry path requests mTLS, which isn't available in every
    # environment (local dev, notebooks, the ADK optimizer's LocalEvalSampler) and otherwise fails at
    # session time with "mTLS was requested but AsyncAuthorizedSession channel is not mTLS" -> the
    # toolset loads empty and tool calls raise "Tool not found. Available tools: transfer_to_agent".
    # URLs come from the *_MCP_URL env vars (see MCP_SERVER_URLS).
    if os.environ.get("MCP_USE_DIRECT_URLS") == "1":
        url = MCP_SERVER_URLS.get(server_name)
        if url:
            return _direct_toolset(url)
    try:
        toolset = _get_registry().get_mcp_toolset(server_name)
        if hasattr(toolset, '_connection_params'):
            if hasattr(toolset._connection_params, 'timeout'):
                toolset._connection_params.timeout = MCP_TIMEOUT_SECONDS
            if hasattr(toolset._connection_params, 'sse_read_timeout'):
                toolset._connection_params.sse_read_timeout = MCP_READ_TIMEOUT_SECONDS
        return toolset
    except RuntimeError:
        url = MCP_SERVER_URLS.get(server_name)
        if not url:
            raise
        return _direct_toolset(url)


MAX_INPUT_LENGTH = 4000
BLOCKED_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*/?script", re.IGNORECASE),
]


def input_guardrail_callback(callback_context=None, **kwargs):
    context = callback_context
    user_message = ""
    if context and context.user_content:
        if isinstance(context.user_content, Content):
            for part in context.user_content.parts or []:
                if part.text:
                    user_message += part.text
        elif isinstance(context.user_content, str):
            user_message = context.user_content
    if not user_message:
        return None
    if len(user_message) > MAX_INPUT_LENGTH:
        return Content(parts=[Part(text=f"Input too long ({len(user_message)} chars, max {MAX_INPUT_LENGTH}).")])
    for pattern in BLOCKED_PATTERNS:
        if pattern.search(user_message):
            return Content(parts=[Part(text="I'm sorry, I can't process that request.")])
    return None


travel_agent = LlmAgent(
    model=_resolve_model(AGENT_MODEL),
    name="travel_agent",
    instruction="""\
You are a corporate travel assistant. Help employees search for and book flights and hotels.
When a user asks about travel:
1. Use the search tools to find available flights or hotels.
2. Present the options clearly with prices, times, and ratings.
3. When the user chooses, use the booking tools to confirm.
If the user asks about expenses, let them know to ask the expense assistant.""",
    tools=[
        _get_mcp_tools(SEARCH_MCP_SERVER),
        _get_mcp_tools(BOOKING_MCP_SERVER),
    ],
)

expense_agent = LlmAgent(
    model=_resolve_model(AGENT_MODEL),
    name="expense_agent",
    instruction="""\
You are a corporate expense management assistant. Help employees submit expense reports and check policies.
Policy limits: meals ($75), transport ($200), lodging ($400), supplies ($100), entertainment ($150).
1. Check policy first with check_expense_policy.
2. Submit expenses with submit_expense.
3. View history with get_user_expenses.
If the user asks about travel, direct them to the travel assistant.""",
    tools=[
        _get_mcp_tools(EXPENSE_MCP_SERVER),
    ],
)

async def save_memories_callback(callback_context: CallbackContext = None, **kwargs):
    """Persist session events to Memory Bank after each turn."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None


root_agent = LlmAgent(
    model=_resolve_model(AGENT_MODEL),
    name="coordinator_agent",
    instruction="""\
You are a corporate assistant coordinator. Your primary role is to efficiently \
route user requests and provide direct assistance using available tools when appropriate.

1. Direct Tool Usage (Your Primary Action):
   - Flight Search: Use search_flights directly for find/search requests. \
If invalid airport codes are returned, inform the user clearly.
   - Hotel Search: Use search_hotels directly for hotel find/search requests.
   - Expense Policy Checks: Use check_expense_policy directly for policy questions. \
Known limits: meals ($75), transport ($200), lodging ($400), supplies ($100), entertainment ($150).
   - User Expense Retrieval: Use get_user_expenses directly to show past expenses.

2. Delegation (Transfer to Specialist Agent):
   - Flight/Hotel Booking: If a user asks to book a flight or hotel, \
delegate to travel_agent via transfer_to_agent.
   - Expense Submission: For requests to submit expenses, \
delegate to expense_agent via transfer_to_agent.

3. Memory Bank for Personalization:
   - Use recalled memories to personalize responses — greet returning users by \
referencing their recent bookings, preferred airlines, or past expense submissions.

4. Greeting and Clarification:
   - Always greet the user warmly.
   - If intent is unclear, ask for more details.

5. Reliability & Grounding Guardrails (from BQ Flywheel failure-cluster analysis):
   - Grounding (Tool Output Handling): NEVER fabricate data, results, or IDs. Always call \
the appropriate tool to retrieve information before answering any lookup/listing/data \
request; do not answer such requests from assumption or memory alone.
   - No Hallucinated Arguments (Hallucination): Call each tool with ONLY its documented \
parameters. Never invent parameters (e.g. deep_scan, deep_regex_scan) or pass \
non-existent IDs/entities; if a capability or entity is unavailable, tell the user.
   - Schema-Safe Arguments (Tool Calling): Quote or escape special-character identifiers \
in tool arguments (e.g. column names or IDs containing hyphens) to avoid schema/syntax errors.
   - Timeout & Retry Discipline (Tool Quality): On a tool timeout or 5xx error \
(e.g. 503/504), retry at most once with backoff. Do NOT repeatedly re-issue the same \
failing call; after two failures, stop and report degraded service to the user.

When a request comes in, first determine if you can fulfill it directly using your \
tools. If the request involves booking or submission, delegate to the appropriate \
specialist agent. Always provide the most direct and efficient assistance.""",
    tools=[
        _get_mcp_tools(SEARCH_MCP_SERVER),
        # The instruction tells the coordinator to use check_expense_policy / get_user_expenses
        # DIRECTLY, so it needs the expense toolset in hand (submission is still delegated to
        # expense_agent). Without this the coordinator called a tool it didn't hold -> "Tool
        # 'check_expense_policy' not found. Available tools: transfer_to_agent". Booking stays
        # delegated to travel_agent per the instruction, so the booking toolset is intentionally not
        # added here.
        _get_mcp_tools(EXPENSE_MCP_SERVER),
        PreloadMemoryTool(),
    ],
    sub_agents=[travel_agent, expense_agent],
    before_agent_callback=input_guardrail_callback,
    after_agent_callback=save_memories_callback,
)

import types as _t
agent = _t.SimpleNamespace(root_agent=root_agent)

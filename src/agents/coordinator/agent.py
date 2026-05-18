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

_registry = None

def _get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry(project_id=GCP_PROJECT_ID, location=AGENT_REGISTRY_LOCATION)
    return _registry

def _get_mcp_tools(server_name: str):
    try:
        toolset = _get_registry().get_mcp_toolset(server_name)
        if hasattr(toolset, '_connection_params') and hasattr(toolset._connection_params, 'timeout'):
            toolset._connection_params.timeout = MCP_TIMEOUT_SECONDS
        return toolset
    except RuntimeError:
        url = MCP_SERVER_URLS.get(server_name)
        if not url:
            raise
        return McpToolset(connection_params=StreamableHTTPConnectionParams(
            url=url, timeout=MCP_TIMEOUT_SECONDS
        ))


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
    model=AGENT_MODEL,
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
    model=AGENT_MODEL,
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
    model=AGENT_MODEL,
    name="coordinator_agent",
    instruction="""\
You are a corporate assistant coordinator. Route requests to the right specialist:
- Flight/hotel search and booking → delegate to travel_agent
- Expense submission, policy checks → delegate to expense_agent
- General travel info → use search tools directly

You have access to Memory Bank, which stores information from past conversations \
with each user. Use recalled memories to personalize your responses — for example, \
greeting returning users by referencing their recent bookings, preferred airlines, \
or past expense submissions. If a user asks "what did I book last time?" or \
similar, the memory tool will have that context.

Greet the user and ask how you can help if intent is unclear.""",
    tools=[
        _get_mcp_tools(SEARCH_MCP_SERVER),
        PreloadMemoryTool(),
    ],
    sub_agents=[travel_agent, expense_agent],
    before_agent_callback=input_guardrail_callback,
    after_agent_callback=save_memories_callback,
)

import types as _t
agent = _t.SimpleNamespace(root_agent=root_agent)

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

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "hybrid-vertex")
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

_registry = None

def _get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry(project_id=GCP_PROJECT_ID, location=AGENT_REGISTRY_LOCATION)
    return _registry

def _get_mcp_tools(server_name: str):
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
        return McpToolset(connection_params=StreamableHTTPConnectionParams(
            url=url, timeout=MCP_TIMEOUT_SECONDS, sse_read_timeout=MCP_READ_TIMEOUT_SECONDS
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

When a request comes in, first determine if you can fulfill it directly using your \
tools. If the request involves booking or submission, delegate to the appropriate \
specialist agent. Always provide the most direct and efficient assistance.""",
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

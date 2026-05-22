"""Coordinator Agent — routes user requests to travel or expense sub-agents.

Integrates Vertex AI Agent Engine Memory Bank so the agent remembers user
interactions (past bookings, expense submissions, preferences) across sessions.
"""

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from src.config import AGENT_MODEL, SEARCH_MCP_SERVER, resolve_model
from src.registry import get_mcp_tools
from src.armor.config import get_armored_generate_config, input_guardrail_callback
from src.agents.travel_agent import travel_agent
from src.agents.expense_agent import expense_agent

INSTRUCTION = """\
You are a corporate assistant coordinator. Your primary role is to efficiently \
route user requests and provide direct assistance using available tools when appropriate.

1. Direct Tool Usage (Your Primary Action):
   - Flight Search: Use search_flights directly for find/search requests. \
If invalid airport codes are returned, inform the user clearly.
   - Hotel Search: Use search_hotels directly for hotel find/search requests.
   - Expense Policy Checks: Use check_expense_policy directly for policy questions. \
Known limits: meals ($75), transport ($200), lodging ($400), supplies ($100), entertainment ($150).
   - User Expense Retrieval: Use get_user_expenses directly to show past expenses.

2. Delegation (Use Specialist Agent Tools):
   - Flight/Hotel Booking: If a user asks to book a flight or hotel, \
use the travel_agent tool.
   - Expense Submission: For requests to submit expenses, \
use the expense_agent tool.

3. Memory Bank for Personalization:
   - Use recalled memories to personalize responses — greet returning users by \
referencing their recent bookings, preferred airlines, or past expense submissions.

4. Greeting and Clarification:
   - Always greet the user warmly.
   - If intent is unclear, ask for more details.

When a request comes in, first determine if you can fulfill it directly using your \
tools. If the request involves booking or submission, use the appropriate \
specialist agent tool. Always provide the most direct and efficient assistance.\
"""


async def save_memories_callback(callback_context: CallbackContext):
    """after_agent_callback: persist this session's events to Memory Bank."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None


coordinator_agent = LlmAgent(
    model=resolve_model(AGENT_MODEL),
    name="coordinator_agent",
    instruction=INSTRUCTION,
    tools=[
        get_mcp_tools(SEARCH_MCP_SERVER),
        PreloadMemoryTool(),
        AgentTool(agent=travel_agent),
        AgentTool(agent=expense_agent),
    ],
    after_agent_callback=save_memories_callback,
)

root_agent = coordinator_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=coordinator_agent)

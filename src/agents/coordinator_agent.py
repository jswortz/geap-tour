"""Coordinator Agent — routes user requests to travel or expense sub-agents.

Integrates Vertex AI Agent Engine Memory Bank so the agent remembers user
interactions (past bookings, expense submissions, preferences) across sessions.
"""

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from src.config import AGENT_MODEL, SEARCH_MCP_SERVER
from src.registry import get_mcp_tools
from src.armor.config import get_armored_generate_config, input_guardrail_callback
from src.agents.travel_agent import travel_agent
from src.agents.expense_agent import expense_agent

INSTRUCTION = """\
You are a corporate assistant coordinator. You help employees with travel and \
expense needs by routing their requests to the right specialist.

- For flight/hotel search and booking requests → delegate to travel_agent
- For expense submission, policy checks, or reimbursement → delegate to expense_agent
- For general travel information queries → use the search tools directly

You have access to Memory Bank, which stores information from past conversations \
with each user. Use recalled memories to personalize your responses — for example, \
greeting returning users by referencing their recent bookings, preferred airlines, \
or past expense submissions. If a user asks "what did I book last time?" or \
similar, the memory tool will have that context.

Always greet the user and ask how you can help if their intent is unclear. \
When delegating, briefly explain which specialist is handling their request.
"""


async def save_memories_callback(callback_context: CallbackContext):
    """after_agent_callback: persist this session's events to Memory Bank.

    Uses add_session_to_memory which sends the full session to Memory Bank
    for background processing. Memories are scoped to {user_id, app_name}
    so each user gets their own memory space.
    """
    try:
        await callback_context.add_session_to_memory()
    except (ValueError, RuntimeError):
        # Memory Bank is only available when deployed to Agent Engine.
        # Local dev and eval runs don't have a memory service configured,
        # so add_session_to_memory raises ValueError. Safe to skip.
        pass
    return None


coordinator_agent = LlmAgent(
    model=AGENT_MODEL,
    name="coordinator_agent",
    instruction=INSTRUCTION,
    tools=[
        get_mcp_tools(SEARCH_MCP_SERVER),
        PreloadMemoryTool(),
    ],
    sub_agents=[travel_agent, expense_agent],
    generate_content_config=get_armored_generate_config(),
    before_agent_callback=input_guardrail_callback,
    after_agent_callback=save_memories_callback,
)

root_agent = coordinator_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=coordinator_agent)

"""Coordinator Agent — routes user requests to travel or expense sub-agents.

Integrates Vertex AI Agent Engine Memory Bank so the agent remembers user
interactions (past bookings, expense submissions, preferences) across sessions.
"""

# Workaround for b/330372060 or pyOpenSSL SSL context mutation issue:
try:
    import urllib3.contrib.pyopenssl
    urllib3.contrib.pyopenssl.extract_from_urllib3()
except Exception:
    pass


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

    Uses add_events_to_memory with wait_for_completion=True to block
    synchronously until memory extraction is complete. Memories are
    scoped to {user_id, app_name} so each user gets their own memory space.
    """
    await callback_context.add_events_to_memory(
        events=callback_context.session.events,
        custom_metadata={"wait_for_completion": True}
    )
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

"""Coordinator Agent — routes user requests to travel or expense sub-agents."""

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from src.config import AGENT_MODEL, SEARCH_MCP_SERVER
from src.registry import get_mcp_tools
from src.armor.config import get_armored_generate_config, input_guardrail_callback
from src.agents.travel_agent import travel_agent
from src.agents.expense_agent import expense_agent


async def save_memories_callback(callback_context: CallbackContext):
    """Persist session events to Memory Bank after each turn."""
    await callback_context.add_session_to_memory()
    return None

INSTRUCTION = """\
You are a corporate assistant coordinator. You help employees with travel and \
expense needs by routing their requests to the right specialist.

- For flight/hotel search and booking requests → delegate to travel_agent
- For expense submission, policy checks, or reimbursement → delegate to expense_agent
- For general travel information queries → use the search tools directly

Always greet the user and ask how you can help if their intent is unclear. \
When delegating, briefly explain which specialist is handling their request.
"""

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

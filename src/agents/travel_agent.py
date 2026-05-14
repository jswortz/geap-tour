"""Travel Agent — searches and books flights and hotels via MCP tool servers."""

from google.adk.agents import LlmAgent

from src.config import AGENT_MODEL, SEARCH_MCP_SERVER, BOOKING_MCP_SERVER
from src.registry import get_mcp_tools

INSTRUCTION = """\
You are a corporate travel assistant. You help employees search for and book \
flights and hotels for business trips.

When a user asks about travel:
1. Use the search tools to find available flights or hotels matching their criteria.
2. Present the options clearly with prices, times, and ratings.
3. When the user chooses, use the booking tools to confirm the reservation.
4. Always confirm the booking details before finalizing.

If the user asks about expenses or reimbursement, let them know you only handle \
travel bookings — they should ask the expense assistant for that.
"""

travel_agent = LlmAgent(
    model=AGENT_MODEL,
    name="travel_agent",
    instruction=INSTRUCTION,
    tools=[
        get_mcp_tools(SEARCH_MCP_SERVER),
        get_mcp_tools(BOOKING_MCP_SERVER),
    ],
)

root_agent = travel_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=travel_agent)

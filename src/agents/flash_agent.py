"""Flash Agent — handles simple tasks with light reasoning using a fast model."""

from google.adk.agents import LlmAgent
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from src.config import FLASH_MODEL, SEARCH_MCP_SERVER, BOOKING_MCP_SERVER, EXPENSE_MCP_SERVER, resolve_model
from src.registry import get_mcp_tools


INSTRUCTION = """\
You are a capable corporate assistant for straightforward requests. Your \
primary goal is to efficiently handle user requests by leveraging available \
tools and providing clear, formatted, and accurate information. Use recalled \
memories to personalize responses when available.

**1. Expense Submission:**
   - Always use the expense_mcp_submit_expense tool for expense submissions.
   - If the expense is within policy: confirm submission with expense ID, \
amount, category, status (approved), and the policy limit.
   - If the expense exceeds policy: do NOT confirm submission. Inform the \
user it cannot be automatically approved, explain the policy discrepancy \
(amount vs limit), and advise that manager approval is required.

**2. Flight Booking:**
   - Use the booking_mcp_book_flight tool for flight bookings.
   - Confirm with booking ID, status, passenger, and flight ID.
   - Only include details explicitly returned by the tool.

**3. General Guidelines:**
   - Present information in clear, bulleted lists.
   - For policy checks, state the limit and what happens when exceeded.
   - For searches, format results with relevant details (price, time, rating).\
"""

flash_agent = LlmAgent(
    model=resolve_model(FLASH_MODEL),
    name="flash_agent",
    description="Handles simple tasks with light reasoning — formatted searches, single submissions.",
    instruction=INSTRUCTION,
    tools=[
        get_mcp_tools(SEARCH_MCP_SERVER),
        get_mcp_tools(BOOKING_MCP_SERVER),
        get_mcp_tools(EXPENSE_MCP_SERVER),
        PreloadMemoryTool(),
    ],
)

root_agent = flash_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=flash_agent)

"""Coordinator Agent — routes user requests to travel or expense sub-agents."""

from google.adk.agents import LlmAgent
from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool.mcp_toolset import StreamableHTTPConnectionParams

from src.config import AGENT_MODEL, SEARCH_MCP_URL
from src.armor.config import get_armored_generate_config, input_guardrail_callback
from src.agents.travel_agent import travel_agent
from src.agents.expense_agent import expense_agent

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
        McpToolset(connection_params=StreamableHTTPConnectionParams(url=SEARCH_MCP_URL)),
    ],
    sub_agents=[travel_agent, expense_agent],
    generate_content_config=get_armored_generate_config(),
    before_agent_callback=input_guardrail_callback,
)

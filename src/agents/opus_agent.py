"""Opus Agent — handles expert-level requests using Claude Opus."""

from google.adk.agents import LlmAgent
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from src.config import OPUS_MODEL, SEARCH_MCP_SERVER, BOOKING_MCP_SERVER, EXPENSE_MCP_SERVER, resolve_model
from src.registry import get_mcp_tools


INSTRUCTION = """\
You are an expert corporate assistant for the most complex, high-stakes \
requests. Provide thorough financial and logistical analysis for business \
travel and team events. Cross-reference information across tools.

Follow a rigorous, multi-step planning approach:

1. **Deconstruct Request:** Identify all explicit and implicit requirements.
2. **Information Gathering:**
   - Flights: use search_mcp_search_flights. If no origin specified, assume \
SFO and state the assumption. Prioritize cost-effective options.
   - Hotels: use search_mcp_search_hotels. Find options within $400/night \
lodging policy.
   - Policies: use expense_mcp_check_expense_policy for all relevant \
categories (lodging $400/night, meals $75/day, transport $200, entertainment $150).
3. **Assumptions & Calculations:**
   - If trip duration unspecified, assume 3 days and state the assumption.
   - Calculate per-person and group totals by category.
   - Cross-reference all costs against corporate policy limits.
   - Compare against any user-provided budget. Flag overages clearly.
4. **Analysis & Recommendations:**
   - Summarize findings with data-driven conclusions.
   - Offer strategic recommendations for budget/policy adherence.
   - Articulate any limitations in tool data.
5. **Structured Response:** Use headings, tables, bullet points, bold text. \
Make responses feel complete and authoritative.
6. **Next Steps:** Conclude with actionable next steps.
7. **Scope:** Financial and logistical analysis only. Decline agenda \
drafting or non-logistical tasks.\
"""

opus_agent = LlmAgent(
    model=resolve_model(OPUS_MODEL),
    name="opus_agent",
    description="Handles expert-level requests requiring deep multi-step planning, budget optimization, and strategic synthesis.",
    instruction=INSTRUCTION,
    tools=[
        get_mcp_tools(SEARCH_MCP_SERVER),
        get_mcp_tools(BOOKING_MCP_SERVER),
        get_mcp_tools(EXPENSE_MCP_SERVER),
        PreloadMemoryTool(),
    ],
)

root_agent = opus_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=opus_agent)

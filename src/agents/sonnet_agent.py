"""Sonnet Agent — handles complex, multi-intent requests using Claude Sonnet."""

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from src.config import SONNET_MODEL, SEARCH_MCP_SERVER, BOOKING_MCP_SERVER, EXPENSE_MCP_SERVER
from src.registry import get_mcp_tools


def _resolve_model(model_str: str):
    if model_str.startswith(("gemini-2", "models/")):
        return model_str
    if not model_str.startswith("vertex_ai/"):
        model_str = f"vertex_ai/{model_str}"
    return LiteLlm(model=model_str, vertex_location="global")


INSTRUCTION = """\
You are an advanced corporate assistant specialized in travel and expense \
management. Your primary goal is to provide comprehensive, accurate, and \
actionable insights by analyzing information across multiple domains.

**Core Principles:**
1. **Multi-Domain Analysis:** Consider all relevant aspects including \
flights, hotels, transport, and expense policies. Infer missing details \
like destination cities from airport codes (JFK→New York, ORD→Chicago).
2. **Detailed Structured Output:** Use markdown headings, tables, bullet \
points, and bold text. Summarize key insights and provide recommendations.
3. **Actionable Recommendations:** Highlight "best options" based on \
criteria (cheapest, most convenient, policy-compliant) and suggest next steps.
4. **Expense Policy Compliance:** State corporate limits explicitly, \
compare proposed costs against them, and indicate policy compliance. \
Use $75/day for meals, $400/night for lodging as standard targets.
5. **Scenario Planning:** For comparisons, evaluate different scenarios \
(budget vs premium, varying durations) to provide a holistic view.
6. **Personalization:** Integrate recalled memories and preferences.
7. **Follow-Up:** Conclude by offering relevant next actions.

**Task Guidance:**
- Use specific IDs (FL001, HT001) when referencing or booking.
- For bookings, confirm each item with booking ID, details, and status.
- For comparisons, include a head-to-head summary table.\
"""

sonnet_agent = LlmAgent(
    model=_resolve_model(SONNET_MODEL),
    name="sonnet_agent",
    description="Handles complex, multi-intent requests requiring cross-domain analysis.",
    instruction=INSTRUCTION,
    tools=[
        get_mcp_tools(SEARCH_MCP_SERVER),
        get_mcp_tools(BOOKING_MCP_SERVER),
        get_mcp_tools(EXPENSE_MCP_SERVER),
        PreloadMemoryTool(),
    ],
)

root_agent = sonnet_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=sonnet_agent)

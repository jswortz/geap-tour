"""Lite Agent — handles trivial, single-intent lookups using the fastest model."""

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from src.config import LITE_MODEL, SEARCH_MCP_SERVER, BOOKING_MCP_SERVER, EXPENSE_MCP_SERVER
from src.registry import get_mcp_tools


def _resolve_model(model_str: str):
    if model_str.startswith(("gemini-2", "models/")):
        return model_str
    if not model_str.startswith("vertex_ai/"):
        model_str = f"vertex_ai/{model_str}"
    return LiteLlm(model=model_str, vertex_location="global")


INSTRUCTION = """\
You are a fast, specialized corporate travel and expense assistant. Your \
primary function is to help users with queries related to corporate travel \
and expense management.

**Capabilities:**
*   Searching flights and hotels.
*   Booking travel.
*   Checking corporate expense policies.
*   Submitting expenses.

**Limitations:**
*   You are strictly a corporate travel and expense assistant. You cannot \
provide assistance with general tasks outside of corporate travel and expense \
management. For such queries, clearly state your specific domain and direct \
the user to appropriate alternative tools or resources.

**Response Style:**
*   Provide direct, concise, and helpful answers.
*   Prioritize clarity and brevity in all responses.

**Tool Usage Guidelines:**
*   Always use the appropriate tools when a query requires data retrieval, \
action, or calculation.
*   Extract and utilize all relevant information from tool outputs.
*   For expense submissions, include the expense ID, approval status, and \
whether the expense is within corporate policy limits.
*   For policy queries, state the limit clearly and include what happens \
when exceeded (e.g., requires manager review).

**Personalization:**
*   Use recalled memories to personalize responses when available.\
"""

lite_agent = LlmAgent(
    model=_resolve_model(LITE_MODEL),
    name="lite_agent",
    description="Handles trivial, single-intent lookups — direct facts, single policy checks.",
    instruction=INSTRUCTION,
    tools=[
        get_mcp_tools(SEARCH_MCP_SERVER),
        get_mcp_tools(BOOKING_MCP_SERVER),
        get_mcp_tools(EXPENSE_MCP_SERVER),
        PreloadMemoryTool(),
    ],
)

root_agent = lite_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=lite_agent)

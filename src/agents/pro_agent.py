"""Pro Agent — handles moderate tasks requiring reasoning using Gemini Pro."""

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from src.config import PRO_MODEL, SEARCH_MCP_SERVER, BOOKING_MCP_SERVER, EXPENSE_MCP_SERVER
from src.registry import get_mcp_tools


def _resolve_model(model_str: str):
    if model_str.startswith(("gemini-2", "models/")):
        return model_str
    if not model_str.startswith("vertex_ai/"):
        model_str = f"vertex_ai/{model_str}"
    return LiteLlm(model=model_str, vertex_location="global")


INSTRUCTION = """\
You are a thorough corporate assistant designed to handle moderately complex \
requests. Your responses must be structured, clear, and comprehensive.

**General Operating Principles:**
1. **Problem Breakdown:** Analyze the user's request and break it down into \
manageable sub-tasks.
2. **Tool Utilization:** Employ tools strategically. Validate all required \
parameters before calling. If missing, check recalled memories first, then \
ask the user. Use multiple tool calls if needed.
3. **Structured Responses:** Use tables for comparisons and lists. Include \
all relevant details from tools. When comparing items, calculate both \
absolute difference and percentage savings. Conclude clearly without \
extraneous information.
4. **Personalization:** Leverage recalled memories to personalize responses.
5. **Scope and Safety:** Strictly adhere to the user's request. Do not \
offer unsolicited actions. Do not ask for PII unless required for a \
requested action with a dedicated tool.

**Specific Task Guidance:**
- **Expense Policy:** Use expense_mcp_check_expense_policy. Compile limits \
into a clear table. Include conditions like "requires manager review."
- **Flight Search:** Use search_mcp_search_flights. For comparisons, list \
details and calculate absolute and percentage savings.\
"""

pro_agent = LlmAgent(
    model=_resolve_model(PRO_MODEL),
    name="pro_agent",
    description="Handles moderate tasks requiring reasoning — comparisons, multi-step lookups, policy analysis.",
    instruction=INSTRUCTION,
    tools=[
        get_mcp_tools(SEARCH_MCP_SERVER),
        get_mcp_tools(BOOKING_MCP_SERVER),
        get_mcp_tools(EXPENSE_MCP_SERVER),
        PreloadMemoryTool(),
    ],
)

root_agent = pro_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=pro_agent)

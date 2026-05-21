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
You are a thorough corporate assistant for moderately complex requests. \
Break down the problem, use multiple tools as needed, and provide structured answers. \
Use recalled memories to personalize responses when available.\
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

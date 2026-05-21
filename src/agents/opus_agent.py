"""Opus Agent — handles expert-level requests using Claude Opus."""

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from src.config import OPUS_MODEL, SEARCH_MCP_SERVER, BOOKING_MCP_SERVER, EXPENSE_MCP_SERVER
from src.registry import get_mcp_tools


def _resolve_model(model_str: str):
    if model_str.startswith(("gemini-2", "models/")):
        return model_str
    if not model_str.startswith("vertex_ai/"):
        model_str = f"vertex_ai/{model_str}"
    return LiteLlm(model=model_str, vertex_location="global")


INSTRUCTION = """\
You are an expert corporate assistant for the most complex, high-stakes requests. \
Provide thorough analysis with multi-step planning. \
Cross-reference information across tools and present a comprehensive response. \
Use recalled memories to personalize responses when available.\
"""

opus_agent = LlmAgent(
    model=_resolve_model(OPUS_MODEL),
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

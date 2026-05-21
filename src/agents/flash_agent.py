"""Flash Agent — handles simple tasks with light reasoning using a fast model."""

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from src.config import FLASH_MODEL, SEARCH_MCP_SERVER, BOOKING_MCP_SERVER, EXPENSE_MCP_SERVER
from src.registry import get_mcp_tools


def _resolve_model(model_str: str):
    if model_str.startswith(("gemini-2", "models/")):
        return model_str
    if not model_str.startswith("vertex_ai/"):
        model_str = f"vertex_ai/{model_str}"
    return LiteLlm(model=model_str, vertex_location="global")


INSTRUCTION = """\
You are a capable corporate assistant for straightforward requests. \
Use tools as needed and provide clear, formatted answers. \
Use recalled memories to personalize responses when available.\
"""

flash_agent = LlmAgent(
    model=_resolve_model(FLASH_MODEL),
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

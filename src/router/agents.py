"""Multi-model agent definitions — 5-tier router by prompt complexity.

Routes to: Lite → Flash → Pro → Sonnet → Opus based on classifier score.
"""

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai.types import Content, Part

from .config import LITE_MODEL, FLASH_MODEL, PRO_MODEL, SONNET_MODEL, OPUS_MODEL
from .armor import input_guardrail_callback
from .complexity import classify_complexity

from src.config import SEARCH_MCP_SERVER, BOOKING_MCP_SERVER, EXPENSE_MCP_SERVER
from src.registry import get_mcp_tools


def _resolve_model(model_str: str):
    """Wrap non-Gemini model strings with LiteLlm; pass Gemini strings through."""
    if model_str.startswith(("gemini-", "models/")):
        return model_str
    # LiteLLM needs vertex_ai/ prefix to route through Vertex AI
    if not model_str.startswith("vertex_ai/"):
        model_str = f"vertex_ai/{model_str}"
    kwargs = {}
    # Claude models on Vertex AI are served from location=global
    if "claude" in model_str:
        kwargs["vertex_location"] = "global"
    return LiteLlm(model=model_str, **kwargs)


def _mcp_tools():
    return [
        get_mcp_tools(SEARCH_MCP_SERVER),
        get_mcp_tools(BOOKING_MCP_SERVER),
        get_mcp_tools(EXPENSE_MCP_SERVER),
    ]


def _sub_agent_tools():
    return [*_mcp_tools(), PreloadMemoryTool()]


lite_agent = LlmAgent(
    model=_resolve_model(LITE_MODEL),
    name="lite_agent",
    description="Handles trivial, single-intent lookups — direct facts, single policy checks.",
    instruction=(
        "You are a fast corporate assistant for simple queries. "
        "Give direct, concise answers. Use tools when needed. "
        "Use recalled memories to personalize responses when available."
    ),
    tools=_sub_agent_tools(),
)

flash_agent = LlmAgent(
    model=_resolve_model(FLASH_MODEL),
    name="flash_agent",
    description="Handles simple tasks with light reasoning — formatted searches, single submissions.",
    instruction=(
        "You are a capable corporate assistant for straightforward requests. "
        "Use tools as needed and provide clear, formatted answers. "
        "Use recalled memories to personalize responses when available."
    ),
    tools=_sub_agent_tools(),
)

pro_agent = LlmAgent(
    model=_resolve_model(PRO_MODEL),
    name="pro_agent",
    description="Handles moderate tasks requiring reasoning — comparisons, multi-step lookups, policy analysis.",
    instruction=(
        "You are a thorough corporate assistant for moderately complex requests. "
        "Break down the problem, use multiple tools as needed, and provide structured answers. "
        "Use recalled memories to personalize responses when available."
    ),
    tools=_sub_agent_tools(),
)

sonnet_agent = LlmAgent(
    model=_resolve_model(SONNET_MODEL),
    name="sonnet_agent",
    description="Handles complex, multi-intent requests requiring cross-domain analysis.",
    instruction=(
        "You are an advanced corporate assistant for complex requests. "
        "Analyze across multiple domains, use several tools, and provide detailed structured output. "
        "Use recalled memories to personalize responses when available."
    ),
    tools=_sub_agent_tools(),
)

opus_agent = LlmAgent(
    model=_resolve_model(OPUS_MODEL),
    name="opus_agent",
    description="Handles expert-level requests requiring deep multi-step planning, budget optimization, and strategic synthesis.",
    instruction=(
        "You are an expert corporate assistant for the most complex, high-stakes requests. "
        "Provide thorough analysis with multi-step planning. "
        "Cross-reference information across tools and present a comprehensive response. "
        "Use recalled memories to personalize responses when available."
    ),
    tools=_sub_agent_tools(),
)


async def complexity_router_callback(callback_context=None, **kwargs):
    """Classify prompt complexity and store in state for the router's delegation logic."""
    user_message = ""
    if callback_context and callback_context.user_content:
        if isinstance(callback_context.user_content, Content):
            for part in callback_context.user_content.parts or []:
                if part.text:
                    user_message += part.text
        elif isinstance(callback_context.user_content, str):
            user_message = callback_context.user_content

    if not user_message:
        return None

    guardrail_result = input_guardrail_callback(callback_context=callback_context)
    if guardrail_result is not None:
        return guardrail_result

    result = await classify_complexity(user_message)
    callback_context.state["complexity_level"] = result.level
    callback_context.state["complexity_score"] = result.score
    callback_context.state["complexity_reason"] = result.reason
    return None


async def save_memories_callback(callback_context: CallbackContext = None, **kwargs):
    """Persist session events to Memory Bank after each turn."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None


ROUTER_INSTRUCTION = """\
You are a routing coordinator. A complexity classifier assessed the user's request:

- Level: {complexity_level}
- Score: {complexity_score}
- Reason: {complexity_reason}

You MUST call the transfer_to_agent function to delegate to the correct specialist:
- "low" → transfer_to_agent(agent_name="lite_agent")
- "medium_low" → transfer_to_agent(agent_name="flash_agent")
- "medium" → transfer_to_agent(agent_name="pro_agent")
- "medium_high" → transfer_to_agent(agent_name="sonnet_agent")
- "high" → transfer_to_agent(agent_name="opus_agent")

Always call transfer_to_agent. Do not answer the user's question yourself.\
"""

router_agent = LlmAgent(
    model=_resolve_model(LITE_MODEL),
    name="router_agent",
    instruction=ROUTER_INSTRUCTION,
    tools=[PreloadMemoryTool()],
    sub_agents=[lite_agent, flash_agent, pro_agent, sonnet_agent, opus_agent],
    before_agent_callback=complexity_router_callback,
    after_agent_callback=save_memories_callback,
)

root_agent = router_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=router_agent)

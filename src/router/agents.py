"""Multi-model agent definitions — routes by prompt complexity to Lite, Flash, or Opus."""

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai.types import Content

from .config import LITE_MODEL, FLASH_MODEL, OPUS_MODEL
from .armor import get_armored_generate_config, input_guardrail_callback
from .complexity import classify_complexity

from src.config import SEARCH_MCP_SERVER, BOOKING_MCP_SERVER, EXPENSE_MCP_SERVER
from src.registry import get_mcp_tools


def _resolve_model(model_str: str):
    """Wrap non-Gemini model strings with LiteLlm; pass Gemini strings through."""
    if model_str.startswith(("gemini-", "models/")):
        return model_str
    return LiteLlm(model=model_str)


def _mcp_tools():
    """Connect to MCP servers via Agent Registry (routes through gateway for governance)."""
    return [
        get_mcp_tools(SEARCH_MCP_SERVER),
        get_mcp_tools(BOOKING_MCP_SERVER),
        get_mcp_tools(EXPENSE_MCP_SERVER),
    ]


lite_agent = LlmAgent(
    model=_resolve_model(LITE_MODEL),
    name="lite_agent",
    description="Handles simple, single-intent lookups — flight searches, policy checks, quick facts.",
    instruction=(
        "You are a fast corporate assistant for simple queries. "
        "Give direct, concise answers. Use tools when needed."
    ),
    tools=_mcp_tools(),
    generate_content_config=get_armored_generate_config(),
    before_agent_callback=input_guardrail_callback,
)

flash_agent = LlmAgent(
    model=_resolve_model(FLASH_MODEL),
    name="flash_agent",
    description="Handles moderate tasks requiring reasoning — comparisons, multi-step lookups, summaries.",
    instruction=(
        "You are a capable corporate assistant for moderately complex requests. "
        "Break down the problem, use tools as needed, and provide clear structured answers."
    ),
    tools=_mcp_tools(),
    generate_content_config=get_armored_generate_config(),
    before_agent_callback=input_guardrail_callback,
)

opus_agent = LlmAgent(
    model=_resolve_model(OPUS_MODEL),
    name="opus_agent",
    description="Handles complex, multi-step requests requiring deep analysis and cross-domain reasoning.",
    instruction=(
        "You are an expert corporate assistant for complex, high-stakes requests. "
        "Provide thorough analysis with multi-step planning. "
        "Cross-reference information across tools and present a comprehensive response."
    ),
    tools=_mcp_tools(),
    before_agent_callback=input_guardrail_callback,
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


async def save_memories_callback(callback_context: CallbackContext):
    """Persist session events to Memory Bank after each turn."""
    await callback_context.add_session_to_memory()
    return None


ROUTER_INSTRUCTION = """\
You are a routing coordinator. Check the complexity assessment in state and delegate:

- If complexity_level is "low" → delegate to lite_agent
- If complexity_level is "medium" → delegate to flash_agent
- If complexity_level is "high" → delegate to opus_agent

Briefly tell the user which specialist is handling their request and why \
(e.g. "Routing to our deep-analysis specialist for this multi-step planning task").\
"""

router_agent = LlmAgent(
    model=_resolve_model(LITE_MODEL),
    name="router_agent",
    instruction=ROUTER_INSTRUCTION,
    tools=[PreloadMemoryTool()],
    sub_agents=[lite_agent, flash_agent, opus_agent],
    before_agent_callback=complexity_router_callback,
    after_agent_callback=save_memories_callback,
)

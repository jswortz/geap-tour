"""Expense Agent — submits expenses and checks corporate policy via MCP tool server."""

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from src.config import AGENT_MODEL, EXPENSE_MCP_SERVER


def _resolve_model(model_str: str):
    """Resolve model string — Gemini 3.x and Claude need location=global."""
    if model_str.startswith(("gemini-2", "models/")):
        return model_str
    if not model_str.startswith("vertex_ai/"):
        model_str = f"vertex_ai/{model_str}"
    return LiteLlm(model=model_str, vertex_location="global")
    
from src.armor.config import get_armored_generate_config, input_guardrail_callback
from src.registry import get_mcp_tools

# GEPA-optimized instruction (base score 0.60 → optimized 0.90).
# Produced by running GEPA on expense_agent as a root agent via
# src/agents/expense_agent_opt/ — a workaround for the ADK limitation
# that GEPARootAgentPromptOptimizer only optimizes root agent prompts.
# To re-optimize: uv run python -m src.optimize.run_optimize src/agents/expense_agent_opt src/optimize/expense_sampler_config.json
INSTRUCTION = """\
You are a corporate expense management assistant. Help employees manage \
expense reports while adhering to company policies.

Policy limits: meals ($75), transport ($200), lodging ($400), supplies ($100), \
entertainment ($150). Amounts above these limits require manager review.

Tools and process:

1. check_expense_policy(category, amount): Always call this FIRST for any \
policy question or before submitting. If the category is unrecognized, list \
valid categories. If within policy, state the limit. If over, state the limit \
and note it requires manager review.

2. submit_expense(user_id, category, amount, description): Only call AFTER \
check_expense_policy confirms within policy. If over limit, do not submit — \
inform the user it requires manager review. Requires user_id — ask for it \
if not provided.

3. get_user_expenses(user_id): Retrieve past expenses for a user.

If the user asks about booking travel, inform them you only handle expenses \
and they should ask the travel assistant.\
"""

expense_agent = LlmAgent(
    model=_resolve_model(AGENT_MODEL),
    name="expense_agent",
    instruction=INSTRUCTION,
    tools=[
        get_mcp_tools(EXPENSE_MCP_SERVER),
    ],
    generate_content_config=get_armored_generate_config(),
    before_agent_callback=input_guardrail_callback,
)

root_agent = expense_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=expense_agent)

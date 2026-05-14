"""Expense Agent — submits expenses and checks corporate policy via MCP tool server."""

from google.adk.agents import LlmAgent

from src.config import AGENT_MODEL, EXPENSE_MCP_SERVER
from src.registry import get_mcp_tools

INSTRUCTION = """\
You are a corporate expense management assistant. You help employees submit \
expense reports and check corporate reimbursement policies.

When a user asks about expenses:
1. If they want to check policy, use check_expense_policy first to verify limits.
2. If they want to submit, use submit_expense with all required details.
3. If they want to view past expenses, use get_user_expenses.
4. Always inform the user whether their expense is within policy before submitting.

Policy categories: meals ($75), transport ($200), lodging ($400), supplies ($100), \
entertainment ($150). Amounts above these limits require manager review.

If the user asks about booking travel, let them know you only handle expenses — \
they should ask the travel assistant for that.
"""

expense_agent = LlmAgent(
    model=AGENT_MODEL,
    name="expense_agent",
    instruction=INSTRUCTION,
    tools=[
        get_mcp_tools(EXPENSE_MCP_SERVER),
    ],
)

root_agent = expense_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=expense_agent)

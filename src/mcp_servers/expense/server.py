"""Expense MCP server — exposes expense submission, policy checks, and history over StreamableHTTP."""

from fastmcp import FastMCP

try:
    from .mock_db import submit_expense as _submit, check_policy as _check, get_expenses as _get
except ImportError:
    from mock_db import submit_expense as _submit, check_policy as _check, get_expenses as _get

mcp = FastMCP("expense-mcp", instructions="Submit and manage corporate expense reports.")


@mcp.tool()
def submit_expense(amount: float, category: str, description: str, user_id: str) -> dict:
    """Submit an expense report for reimbursement.

    Args:
        amount: Expense amount in USD
        category: Expense category (meals, transport, lodging, supplies, entertainment)
        description: Brief description of the expense
        user_id: Employee ID submitting the expense
    """
    return _submit(amount, category, description, user_id)


@mcp.tool()
def check_expense_policy(amount: float, category: str) -> dict:
    """Check if an expense amount is within corporate policy limits.

    Args:
        amount: Expense amount in USD
        category: Expense category (meals, transport, lodging, supplies, entertainment)
    """
    return _check(amount, category)


@mcp.tool()
def get_user_expenses(user_id: str) -> list[dict]:
    """Get all expenses submitted by a specific user.

    Args:
        user_id: Employee ID to look up expenses for
    """
    return _get(user_id)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8003)

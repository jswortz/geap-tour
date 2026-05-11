import uuid
from datetime import datetime

POLICY_LIMITS = {
    "meals": 75.00,
    "transport": 200.00,
    "lodging": 400.00,
    "supplies": 100.00,
    "entertainment": 150.00,
}

expenses: dict[str, dict] = {}


def submit_expense(amount: float, category: str, description: str, user_id: str) -> dict:
    expense_id = f"EX-{uuid.uuid4().hex[:8].upper()}"
    policy_check = check_policy(amount, category)
    expense = {
        "expense_id": expense_id,
        "amount": amount,
        "category": category,
        "description": description,
        "user_id": user_id,
        "status": "approved" if policy_check["within_policy"] else "pending_review",
        "policy_check": policy_check,
        "submitted_at": datetime.now().isoformat(),
    }
    expenses[expense_id] = expense
    return expense


def check_policy(amount: float, category: str) -> dict:
    category_lower = category.lower()
    if category_lower not in POLICY_LIMITS:
        return {
            "within_policy": False,
            "reason": f"Unknown category '{category}'. Valid: {', '.join(POLICY_LIMITS.keys())}",
        }
    limit = POLICY_LIMITS[category_lower]
    return {
        "within_policy": amount <= limit,
        "limit": limit,
        "amount": amount,
        "category": category_lower,
        "reason": None if amount <= limit else f"Amount ${amount:.2f} exceeds ${limit:.2f} limit for {category_lower}",
    }


def get_expenses(user_id: str) -> list[dict]:
    return [e for e in expenses.values() if e["user_id"] == user_id]

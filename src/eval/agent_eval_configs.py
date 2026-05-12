"""Per-agent evaluation configs — test cases, AgentInfo builders, and metric selectors."""

import json

from vertexai import types

from src.eval.batch_eval import EVAL_CASES as COORDINATOR_EVAL_CASES, POLICY_COMPLIANCE_METRIC


# ---------------------------------------------------------------------------
# Travel agent test cases
# ---------------------------------------------------------------------------
TRAVEL_EVAL_CASES = [
    {
        "prompt": "Find flights from SFO to JFK on June 15",
        "category": "flight_search",
        "expected_tool": "search_flights",
        "expected_signals": ["SFO", "JFK", "FL001", "FL002"],
        "description": "Basic flight search with known routes",
    },
    {
        "prompt": "Search for flights from LAX to Chicago on June 16",
        "category": "flight_search",
        "expected_tool": "search_flights",
        "expected_signals": ["LAX", "ORD", "FL003"],
        "description": "Flight search with city name mapping",
    },
    {
        "prompt": "Are there any flights from SFO to Los Angeles on June 15?",
        "category": "flight_search",
        "expected_tool": "search_flights",
        "expected_signals": ["SFO", "LAX", "FL005"],
        "description": "Short-haul domestic flight search",
    },
    {
        "prompt": "Search for hotels in New York under $350 per night",
        "category": "hotel_search",
        "expected_tool": "search_hotels",
        "expected_signals": ["Grand Hyatt", "Budget Inn"],
        "description": "Hotel search with price filter",
    },
    {
        "prompt": "Find me a hotel in Miami",
        "category": "hotel_search",
        "expected_tool": "search_hotels",
        "expected_signals": ["Fontainebleau", "Miami"],
        "description": "Hotel search without price constraint",
    },
    {
        "prompt": "Book flight FL001 for Alice Johnson",
        "category": "booking",
        "expected_tool": "book_flight",
        "expected_signals": ["FL001", "Alice Johnson", "confirmed"],
        "description": "Flight booking with valid flight ID",
    },
    {
        "prompt": "Book hotel HT002 for Bob Smith, checkin June 15, checkout June 18",
        "category": "booking",
        "expected_tool": "book_hotel",
        "expected_signals": ["HT002", "Bob Smith"],
        "description": "Hotel booking with dates",
    },
    {
        "prompt": "Find flights from XYZ to ABC tomorrow",
        "category": "edge_case",
        "expected_tool": "search_flights",
        "expected_signals": [],
        "description": "Invalid airport codes — should handle gracefully",
    },
    {
        "prompt": "Search hotels in Atlantis under $100",
        "category": "edge_case",
        "expected_tool": "search_hotels",
        "expected_signals": [],
        "description": "Non-existent city — should handle gracefully",
    },
    {
        "prompt": "What are the cheapest flight options from SFO to anywhere on the East Coast?",
        "category": "flight_search",
        "expected_tool": "search_flights",
        "expected_signals": ["SFO"],
        "description": "Open-ended destination search",
    },
]


# ---------------------------------------------------------------------------
# Expense agent test cases
# ---------------------------------------------------------------------------
EXPENSE_EVAL_CASES = [
    {
        "prompt": "Check if a $50 meal expense is within policy",
        "category": "policy_check",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["within", "75"],
        "description": "Meal under $75 limit — should approve",
    },
    {
        "prompt": "Is a $180 transport expense within corporate policy?",
        "category": "policy_check",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["within", "200"],
        "description": "Transport under $200 limit — should approve",
    },
    {
        "prompt": "Check policy for a $500 entertainment expense",
        "category": "policy_over_limit",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["exceeds", "150", "entertainment"],
        "description": "Entertainment over $150 limit — should flag",
    },
    {
        "prompt": "Is a $100 meal expense allowed?",
        "category": "policy_over_limit",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["exceeds", "75", "meal"],
        "description": "Meal over $75 limit — should flag",
    },
    {
        "prompt": "Submit a $45 meals expense for lunch meeting, user ID EMP001",
        "category": "submission",
        "expected_tool": "submit_expense",
        "expected_signals": ["EMP001", "45", "approved"],
        "description": "Within-policy submission — should auto-approve",
    },
    {
        "prompt": "Submit a $500 entertainment expense for team event, user ID EMP002",
        "category": "submission_over",
        "expected_tool": "submit_expense",
        "expected_signals": ["EMP002", "pending_review", "exceeds"],
        "description": "Over-limit submission — should flag pending_review",
    },
    {
        "prompt": "Show all expenses for user EMP001",
        "category": "history",
        "expected_tool": "get_user_expenses",
        "expected_signals": ["EMP001"],
        "description": "Expense history retrieval",
    },
    {
        "prompt": "What's the corporate limit for lodging expenses?",
        "category": "policy_inquiry",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["400", "lodging"],
        "description": "Direct policy limit inquiry",
    },
    {
        "prompt": "Check policy for $1000 in the 'unknown' category",
        "category": "invalid_category",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["unknown"],
        "description": "Invalid expense category — should return helpful error",
    },
    {
        "prompt": "Submit a $90 supplies expense for office materials, user ID EMP003",
        "category": "submission",
        "expected_tool": "submit_expense",
        "expected_signals": ["EMP003", "90", "supplies"],
        "description": "Supplies within $100 limit — should approve",
    },
]


# ---------------------------------------------------------------------------
# Router agent test cases (with expected complexity levels)
# ---------------------------------------------------------------------------
ROUTER_EVAL_CASES = [
    {
        "prompt": "Find flights from SFO to JFK",
        "category": "low_complexity",
        "expected_tool": "search_flights",
        "expected_signals": ["SFO", "JFK"],
        "expected_complexity": "low",
        "description": "Simple single-intent flight search",
    },
    {
        "prompt": "What's the expense policy for meals?",
        "category": "low_complexity",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["75", "meal"],
        "expected_complexity": "low",
        "description": "Simple policy lookup",
    },
    {
        "prompt": "Search hotels in Chicago under $200",
        "category": "low_complexity",
        "expected_tool": "search_hotels",
        "expected_signals": ["Chicago"],
        "expected_complexity": "low",
        "description": "Simple hotel search with filter",
    },
    {
        "prompt": "Check if a $50 transport expense is within policy",
        "category": "low_complexity",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["within", "200"],
        "expected_complexity": "low",
        "description": "Simple policy check",
    },
    {
        "prompt": "Find flights to NYC and compare the cheapest options by airline",
        "category": "medium_complexity",
        "expected_tool": "search_flights",
        "expected_signals": ["NYC"],
        "expected_complexity": "medium",
        "description": "Comparison requiring moderate reasoning",
    },
    {
        "prompt": "Search hotels in Boston, then check if the nightly rate fits our lodging policy",
        "category": "medium_complexity",
        "expected_tool": "search_hotels",
        "expected_signals": ["Boston", "400"],
        "expected_complexity": "medium",
        "description": "Two-step: search + policy check",
    },
    {
        "prompt": "Show my expense history and flag any items that exceeded policy limits",
        "category": "medium_complexity",
        "expected_tool": "get_user_expenses",
        "expected_signals": [],
        "expected_complexity": "medium",
        "description": "History retrieval with analysis",
    },
    {
        "prompt": (
            "Plan a 5-day trip to Tokyo for a team of 4: find flights, hotels near "
            "Shibuya, estimate daily meal expenses, and check what our corporate policy "
            "allows for international entertainment expenses."
        ),
        "category": "high_complexity",
        "expected_tool": "multiple",
        "expected_signals": ["Tokyo"],
        "expected_complexity": "high",
        "description": "Multi-step cross-domain planning",
    },
    {
        "prompt": (
            "Compare individual vs group flight bookings for our team retreat to Denver. "
            "Factor in cancellation policies, per-diem meal expenses, and whether hotels "
            "near the conference center or downtown with transport are more cost-effective."
        ),
        "category": "high_complexity",
        "expected_tool": "multiple",
        "expected_signals": ["Denver"],
        "expected_complexity": "high",
        "description": "Complex multi-factor comparison",
    },
    {
        "prompt": (
            "Analyze EMP001's expense history: they overspent on entertainment last quarter. "
            "Draft a policy recommendation for new entertainment limits, and submit my "
            "$45 lunch receipt while you're at it."
        ),
        "category": "high_complexity",
        "expected_tool": "multiple",
        "expected_signals": ["EMP001", "entertainment"],
        "expected_complexity": "high",
        "description": "Analysis + action + submission",
    },
    {
        "prompt": (
            "Book the cheapest SFO-JFK flight, find a hotel within walking distance of "
            "350 5th Ave, cross-reference hotel ratings, check our lodging policy limit, "
            "and submit a pre-approval expense for the estimated total trip cost."
        ),
        "category": "high_complexity",
        "expected_tool": "multiple",
        "expected_signals": ["SFO", "JFK", "400"],
        "expected_complexity": "high",
        "description": "Multi-step booking + policy + expense pipeline",
    },
    {
        "prompt": "How much can I spend on meals per day while traveling?",
        "category": "low_complexity",
        "expected_tool": "check_expense_policy",
        "expected_signals": ["75", "meal"],
        "expected_complexity": "low",
        "description": "Simple policy inquiry phrased as question",
    },
]


# ---------------------------------------------------------------------------
# AgentInfo builders
# ---------------------------------------------------------------------------
def build_agent_info(agent_name: str) -> types.evals.AgentInfo:
    """Build AgentInfo manually for offline evaluation without MCP connections."""
    builders = {
        "coordinator_agent": _build_coordinator_info,
        "travel_agent": _build_travel_info,
        "expense_agent": _build_expense_info,
        "router_agent": _build_router_info,
    }
    builder = builders.get(agent_name)
    if not builder:
        raise ValueError(f"Unknown agent: {agent_name}. Valid: {list(builders)}")
    return builder()


def _build_coordinator_info() -> types.evals.AgentInfo:
    return types.evals.AgentInfo(
        name="coordinator_agent",
        root_agent_id="coordinator_agent",
        agents={
            "coordinator_agent": types.evals.AgentConfig(
                agent_id="coordinator_agent",
                agent_type="LlmAgent",
                description="Corporate assistant coordinator routing to travel or expense specialists.",
                instruction=(
                    "Route requests to the right specialist: flight/hotel to travel_agent, "
                    "expenses to expense_agent, general travel info via search tools directly."
                ),
                sub_agents=["travel_agent", "expense_agent"],
            ),
            "travel_agent": types.evals.AgentConfig(
                agent_id="travel_agent",
                agent_type="LlmAgent",
                description="Corporate travel assistant for searching and booking flights and hotels.",
                instruction="Search for and book flights and hotels using MCP tools.",
                sub_agents=[],
            ),
            "expense_agent": types.evals.AgentConfig(
                agent_id="expense_agent",
                agent_type="LlmAgent",
                description="Corporate expense management assistant.",
                instruction=(
                    "Policy limits: meals ($75), transport ($200), lodging ($400), "
                    "supplies ($100), entertainment ($150). Check policy, submit, view history."
                ),
                sub_agents=[],
            ),
        },
    )


def _build_travel_info() -> types.evals.AgentInfo:
    return types.evals.AgentInfo(
        name="travel_agent",
        root_agent_id="travel_agent",
        agents={
            "travel_agent": types.evals.AgentConfig(
                agent_id="travel_agent",
                agent_type="LlmAgent",
                description="Corporate travel assistant for searching and booking flights and hotels.",
                instruction=(
                    "Search for flights and hotels using MCP tools. Present options clearly, "
                    "then use booking tools to confirm reservations."
                ),
                sub_agents=[],
            ),
        },
    )


def _build_expense_info() -> types.evals.AgentInfo:
    return types.evals.AgentInfo(
        name="expense_agent",
        root_agent_id="expense_agent",
        agents={
            "expense_agent": types.evals.AgentConfig(
                agent_id="expense_agent",
                agent_type="LlmAgent",
                description="Corporate expense management assistant.",
                instruction=(
                    "Policy limits: meals ($75), transport ($200), lodging ($400), "
                    "supplies ($100), entertainment ($150). Check policy first, "
                    "submit expenses, view history."
                ),
                sub_agents=[],
            ),
        },
    )


def _build_router_info() -> types.evals.AgentInfo:
    return types.evals.AgentInfo(
        name="router_agent",
        root_agent_id="router_agent",
        agents={
            "router_agent": types.evals.AgentConfig(
                agent_id="router_agent",
                agent_type="LlmAgent",
                description="Routing coordinator that delegates by prompt complexity.",
                instruction=(
                    "Check complexity assessment and delegate: "
                    'low → lite_agent, medium → flash_agent, high → opus_agent.'
                ),
                sub_agents=["lite_agent", "flash_agent", "opus_agent"],
            ),
            "lite_agent": types.evals.AgentConfig(
                agent_id="lite_agent",
                agent_type="LlmAgent",
                description="Handles simple, single-intent lookups.",
                instruction="Fast corporate assistant for simple queries.",
                sub_agents=[],
            ),
            "flash_agent": types.evals.AgentConfig(
                agent_id="flash_agent",
                agent_type="LlmAgent",
                description="Handles moderate tasks requiring reasoning.",
                instruction="Capable assistant for moderately complex requests.",
                sub_agents=[],
            ),
            "opus_agent": types.evals.AgentConfig(
                agent_id="opus_agent",
                agent_type="LlmAgent",
                description="Handles complex, multi-step requests.",
                instruction="Expert assistant for complex, high-stakes requests.",
                sub_agents=[],
            ),
        },
    )


# ---------------------------------------------------------------------------
# Test case and metric selectors
# ---------------------------------------------------------------------------
ALL_AGENTS = ["coordinator_agent", "travel_agent", "expense_agent", "router_agent"]

_EVAL_CASES = {
    "coordinator_agent": COORDINATOR_EVAL_CASES,
    "travel_agent": TRAVEL_EVAL_CASES,
    "expense_agent": EXPENSE_EVAL_CASES,
    "router_agent": ROUTER_EVAL_CASES,
}


def get_eval_cases(agent_name: str) -> list[dict]:
    """Return the test case list for the given agent."""
    cases = _EVAL_CASES.get(agent_name)
    if cases is None:
        raise ValueError(f"Unknown agent: {agent_name}. Valid: {list(_EVAL_CASES)}")
    return cases


def get_metrics(agent_name: str) -> list:
    """Return the appropriate evaluation metrics for the given agent."""
    base_metrics = [
        types.RubricMetric.FINAL_RESPONSE_QUALITY,
        types.RubricMetric.TOOL_USE_QUALITY,
        types.RubricMetric.HALLUCINATION,
        types.RubricMetric.SAFETY,
    ]

    if agent_name in ("coordinator_agent", "expense_agent"):
        base_metrics.append(POLICY_COMPLIANCE_METRIC)

    if agent_name == "router_agent":
        from src.eval.complexity_metrics import COMPLEXITY_ROUTING_METRIC
        base_metrics.append(COMPLEXITY_ROUTING_METRIC)

    return base_metrics

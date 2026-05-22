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
        "reference": "Flights from SFO to JFK: United FL001 at $450 departing 08:00, Delta FL002 at $520 departing 10:30.",
        "category": "flight_search",
        "expected_tool": "search_mcp_search_flights",
        "expected_signals": ["SFO", "JFK", "FL001", "FL002"],
        "description": "Basic flight search with known routes",
    },
    {
        "prompt": "Search for flights from LAX to Chicago on June 16",
        "reference": "American Airlines flight FL003 from LAX to ORD at $380, departing 07:00.",
        "category": "flight_search",
        "expected_tool": "search_mcp_search_flights",
        "expected_signals": ["LAX", "ORD", "FL003"],
        "description": "Flight search with city name mapping",
    },
    {
        "prompt": "Are there any flights from SFO to Los Angeles on June 15?",
        "reference": "Southwest flight FL005 from SFO to LAX at $150, departing 06:00.",
        "category": "flight_search",
        "expected_tool": "search_mcp_search_flights",
        "expected_signals": ["SFO", "LAX", "FL005"],
        "description": "Short-haul domestic flight search",
    },
    {
        "prompt": "Search for hotels in New York under $350 per night",
        "reference": "Grand Hyatt New York at $320/night (4.5 rating) and Budget Inn Downtown at $120/night (3.2 rating).",
        "category": "hotel_search",
        "expected_tool": "search_mcp_search_hotels",
        "expected_signals": ["Grand Hyatt", "Budget Inn"],
        "description": "Hotel search with price filter",
    },
    {
        "prompt": "Find me a hotel in Miami",
        "reference": "Fontainebleau Miami at $400/night with a 4.7 rating.",
        "category": "hotel_search",
        "expected_tool": "search_mcp_search_hotels",
        "expected_signals": ["Fontainebleau", "Miami"],
        "description": "Hotel search without price constraint",
    },
    {
        "prompt": "Book flight FL001 for Alice Johnson",
        "reference": "Flight FL001 (United, SFO to JFK) booked and confirmed for Alice Johnson.",
        "category": "booking",
        "expected_tool": "booking_mcp_book_flight",
        "expected_signals": ["FL001", "Alice Johnson", "confirmed"],
        "description": "Flight booking with valid flight ID",
    },
    {
        "prompt": "Book hotel HT002 for Bob Smith, checkin June 15, checkout June 18",
        "reference": "Hotel HT002 booked for Bob Smith, check-in June 15, check-out June 18. Confirmation provided.",
        "category": "booking",
        "expected_tool": "booking_mcp_book_hotel",
        "expected_signals": ["HT002", "Bob Smith"],
        "description": "Hotel booking with dates",
    },
    {
        "prompt": "Find flights from XYZ to ABC tomorrow",
        "reference": "No flights found for the route XYZ to ABC. These may be invalid airport codes. Please provide valid IATA airport codes.",
        "category": "edge_case",
        "expected_tool": "search_mcp_search_flights",
        "expected_signals": [],
        "description": "Invalid airport codes — should handle gracefully",
    },
    {
        "prompt": "Search hotels in Atlantis under $100",
        "reference": "No hotels found in Atlantis. This location may not be in our database. Please try a different city.",
        "category": "edge_case",
        "expected_tool": "search_mcp_search_hotels",
        "expected_signals": [],
        "description": "Non-existent city — should handle gracefully",
    },
    {
        "prompt": "What are the cheapest flight options from SFO to anywhere on the East Coast?",
        "reference": "Cheapest flights from SFO: FL001 to JFK at $450 (United), FL005 to LAX at $150 (Southwest). Search results listed by price.",
        "category": "flight_search",
        "expected_tool": "search_mcp_search_flights",
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
        "reference": "A $50 meal expense is within the corporate policy limit of $75 for meals.",
        "category": "policy_check",
        "expected_tool": "expense_mcp_check_expense_policy",
        "expected_signals": ["within", "75"],
        "description": "Meal under $75 limit — should approve",
    },
    {
        "prompt": "Is a $180 transport expense within corporate policy?",
        "reference": "A $180 transport expense is within the corporate policy limit of $200 for transportation.",
        "category": "policy_check",
        "expected_tool": "expense_mcp_check_expense_policy",
        "expected_signals": ["within", "200"],
        "description": "Transport under $200 limit — should approve",
    },
    {
        "prompt": "Check policy for a $500 entertainment expense",
        "reference": "A $500 entertainment expense exceeds the corporate policy limit of $150. This requires manager review.",
        "category": "policy_over_limit",
        "expected_tool": "expense_mcp_check_expense_policy",
        "expected_signals": ["exceeds", "150", "entertainment"],
        "description": "Entertainment over $150 limit — should flag",
    },
    {
        "prompt": "Is a $100 meal expense allowed?",
        "reference": "A $100 meal expense exceeds the corporate policy limit of $75 for meals. This requires manager review.",
        "category": "policy_over_limit",
        "expected_tool": "expense_mcp_check_expense_policy",
        "expected_signals": ["exceeds", "75", "meal"],
        "description": "Meal over $75 limit — should flag",
    },
    {
        "prompt": "Submit a $45 meals expense for lunch meeting, user ID EMP001",
        "reference": "Expense submitted: $45 meals expense for EMP001. Status: approved (within $75 policy limit).",
        "category": "submission",
        "expected_tool": "expense_mcp_submit_expense",
        "expected_signals": ["EMP001", "45", "approved"],
        "description": "Within-policy submission — should auto-approve",
    },
    {
        "prompt": "Submit a $500 entertainment expense for team event, user ID EMP002",
        "reference": "A $500 entertainment expense exceeds the $150 policy limit. Status: pending_review, requires manager approval.",
        "category": "submission_over",
        "expected_tool": "expense_mcp_submit_expense",
        "expected_signals": ["EMP002", "pending_review", "exceeds"],
        "description": "Over-limit submission — should flag pending_review",
    },
    {
        "prompt": "Show all expenses for user EMP001",
        "reference": "Expense history for EMP001 retrieved, showing all submitted expenses with amounts, categories, and statuses.",
        "category": "history",
        "expected_tool": "expense_mcp_get_user_expenses",
        "expected_signals": ["EMP001"],
        "description": "Expense history retrieval",
    },
    {
        "prompt": "What's the corporate limit for lodging expenses?",
        "reference": "The corporate policy limit for lodging expenses is $400 per night.",
        "category": "policy_inquiry",
        "expected_tool": "expense_mcp_check_expense_policy",
        "expected_signals": ["400", "lodging"],
        "description": "Direct policy limit inquiry",
    },
    {
        "prompt": "Check policy for $1000 in the 'unknown' category",
        "reference": "The category 'unknown' is not a valid expense category. Valid categories are: meals, transport, lodging, supplies, entertainment.",
        "category": "invalid_category",
        "expected_tool": "expense_mcp_check_expense_policy",
        "expected_signals": ["unknown"],
        "description": "Invalid expense category — should return helpful error",
    },
    {
        "prompt": "Submit a $90 supplies expense for office materials, user ID EMP003",
        "reference": "Expense submitted: $90 supplies expense for EMP003. Status: approved (within $100 policy limit).",
        "category": "submission",
        "expected_tool": "expense_mcp_submit_expense",
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
        "reference": "Flights from SFO to JFK: United FL001 at $450, Delta FL002 at $520.",
        "category": "low_complexity",
        "expected_tool": "search_mcp_search_flights",
        "expected_signals": ["SFO", "JFK"],
        "expected_complexity": "low",
        "description": "Simple single-intent flight search",
    },
    {
        "prompt": "What's the expense policy for meals?",
        "reference": "The corporate policy limit for meals is $75. Amounts above this require manager review.",
        "category": "low_complexity",
        "expected_tool": "expense_mcp_check_expense_policy",
        "expected_signals": ["75", "meal"],
        "expected_complexity": "low",
        "description": "Simple policy lookup",
    },
    {
        "prompt": "Search hotels in Chicago under $200",
        "reference": "Hotels in Chicago under $200/night listed with names, prices, and ratings.",
        "category": "low_complexity",
        "expected_tool": "search_mcp_search_hotels",
        "expected_signals": ["Chicago"],
        "expected_complexity": "low",
        "description": "Simple hotel search with filter",
    },
    {
        "prompt": "Check if a $50 transport expense is within policy",
        "reference": "A $50 transport expense is within the corporate policy limit of $200.",
        "category": "low_complexity",
        "expected_tool": "expense_mcp_check_expense_policy",
        "expected_signals": ["within", "200"],
        "expected_complexity": "low",
        "description": "Simple policy check",
    },
    {
        "prompt": "Find flights to NYC and compare the cheapest options by airline",
        "reference": "Flight options to NYC compared by airline and price, with the cheapest option highlighted.",
        "category": "medium_complexity",
        "expected_tool": "search_mcp_search_flights",
        "expected_signals": ["NYC"],
        "expected_complexity": "medium",
        "description": "Comparison requiring moderate reasoning",
    },
    {
        "prompt": "Search hotels in Boston, then check if the nightly rate fits our lodging policy",
        "reference": "Hotels in Boston listed with rates. The lodging policy limit is $400/night. Hotels under $400 are within policy.",
        "category": "medium_complexity",
        "expected_tool": "search_mcp_search_hotels",
        "expected_signals": ["Boston", "400"],
        "expected_complexity": "medium",
        "description": "Two-step: search + policy check",
    },
    {
        "prompt": "Show my expense history and flag any items that exceeded policy limits",
        "reference": "Expense history retrieved. Items exceeding policy limits flagged with the applicable limit and overage amount.",
        "category": "medium_complexity",
        "expected_tool": "expense_mcp_get_user_expenses",
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
        "reference": "Trip plan for Tokyo: flights from SFO, hotel options near Shibuya, estimated daily meal costs within $75/person policy, entertainment policy limit of $150.",
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
        "reference": "Comparison of individual vs group bookings to Denver with cost breakdown, per-diem meal estimates within policy, and hotel location cost-effectiveness analysis.",
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
        "reference": "EMP001 expense analysis showing entertainment overspend. Policy recommendation drafted. $45 lunch expense submitted for EMP001, status: approved.",
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
        "reference": "Cheapest SFO-JFK flight booked. Hotels near 350 5th Ave listed with ratings. Lodging policy limit is $400/night. Pre-approval expense submitted with estimated total trip cost.",
        "category": "high_complexity",
        "expected_tool": "multiple",
        "expected_signals": ["SFO", "JFK", "400"],
        "expected_complexity": "high",
        "description": "Multi-step booking + policy + expense pipeline",
    },
    {
        "prompt": "How much can I spend on meals per day while traveling?",
        "reference": "The corporate meal policy limit is $75 per day while traveling.",
        "category": "low_complexity",
        "expected_tool": "expense_mcp_check_expense_policy",
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
    if builder:
        return builder()
    if agent_name in STANDALONE_AGENTS:
        return _build_standalone_info(agent_name)
    raise ValueError(f"Unknown agent: {agent_name}. Valid: {list(builders) + STANDALONE_AGENTS}")


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
                    "low → lite_agent, flash → flash_agent, "
                    "sonnet → sonnet_agent, pro → pro_agent, opus → opus_agent."
                ),
                sub_agents=["lite_agent", "flash_agent", "pro_agent", "sonnet_agent", "opus_agent"],
            ),
            "lite_agent": types.evals.AgentConfig(
                agent_id="lite_agent",
                agent_type="LlmAgent",
                description="Handles trivial, single-intent lookups.",
                instruction="Fast corporate assistant for simple queries.",
                sub_agents=[],
            ),
            "flash_agent": types.evals.AgentConfig(
                agent_id="flash_agent",
                agent_type="LlmAgent",
                description="Handles simple tasks with light reasoning.",
                instruction="Capable assistant for straightforward requests.",
                sub_agents=[],
            ),
            "pro_agent": types.evals.AgentConfig(
                agent_id="pro_agent",
                agent_type="LlmAgent",
                description="Handles moderate tasks requiring reasoning — comparisons, multi-step lookups.",
                instruction="Thorough assistant for moderately complex requests.",
                sub_agents=[],
            ),
            "sonnet_agent": types.evals.AgentConfig(
                agent_id="sonnet_agent",
                agent_type="LlmAgent",
                description="Handles complex, multi-intent requests requiring cross-domain analysis.",
                instruction="Advanced assistant for complex requests.",
                sub_agents=[],
            ),
            "opus_agent": types.evals.AgentConfig(
                agent_id="opus_agent",
                agent_type="LlmAgent",
                description="Handles expert-level requests requiring deep multi-step planning.",
                instruction="Expert assistant for complex, high-stakes requests.",
                sub_agents=[],
            ),
        },
    )


# ---------------------------------------------------------------------------
# Standalone agent AgentInfo builders
# ---------------------------------------------------------------------------
STANDALONE_AGENTS = ["lite_agent", "flash_agent", "pro_agent", "sonnet_agent", "opus_agent"]

_STANDALONE_DESCRIPTIONS = {
    "lite_agent": "Handles trivial, single-intent lookups.",
    "flash_agent": "Handles simple tasks with light reasoning.",
    "pro_agent": "Handles moderate tasks requiring reasoning.",
    "sonnet_agent": "Handles complex, multi-intent requests.",
    "opus_agent": "Handles expert-level requests requiring deep planning.",
}


def _build_standalone_info(agent_name: str) -> types.evals.AgentInfo:
    return types.evals.AgentInfo(
        name=agent_name,
        root_agent_id=agent_name,
        agents={
            agent_name: types.evals.AgentConfig(
                agent_id=agent_name,
                agent_type="LlmAgent",
                description=_STANDALONE_DESCRIPTIONS[agent_name],
                instruction="Corporate assistant with access to travel and expense tools.",
                sub_agents=[],
            ),
        },
    )


STANDALONE_EVAL_CASES = TRAVEL_EVAL_CASES + EXPENSE_EVAL_CASES

# ---------------------------------------------------------------------------
# Complexity-tiered eval cases for cross-model experiment
# ---------------------------------------------------------------------------
LOW_COMPLEXITY_CASES = [
    {
        "prompt": "Find flights from SFO to JFK",
        "reference": "Flights from SFO to JFK: United FL001 at $450, Delta FL002 at $520.",
        "category": "low", "expected_tool": "search_mcp_search_flights",
        "expected_signals": ["SFO", "JFK"], "description": "Simple flight search",
    },
    {
        "prompt": "Search for hotels in New York",
        "reference": "Grand Hyatt at $320/night (4.5 stars) and Budget Inn at $120/night (3.2 stars).",
        "category": "low", "expected_tool": "search_mcp_search_hotels",
        "expected_signals": ["Grand Hyatt", "Budget Inn"], "description": "Simple hotel search",
    },
    {
        "prompt": "What is the meal expense limit?",
        "reference": "The corporate meal expense limit is $75. Amounts above require manager review.",
        "category": "low", "expected_tool": "expense_mcp_check_expense_policy",
        "expected_signals": ["75", "meal"], "description": "Simple policy lookup",
    },
    {
        "prompt": "Book flight FL001 for Alice Johnson",
        "reference": "Flight FL001 booked and confirmed for Alice Johnson.",
        "category": "low", "expected_tool": "booking_mcp_book_flight",
        "expected_signals": ["FL001", "Alice Johnson", "confirmed"], "description": "Simple booking",
    },
    {
        "prompt": "Show expenses for user EMP001",
        "reference": "Expense history for EMP001 retrieved.",
        "category": "low", "expected_tool": "expense_mcp_get_user_expenses",
        "expected_signals": ["EMP001"], "description": "Simple history retrieval",
    },
    {
        "prompt": "Is a $50 transport expense within policy?",
        "reference": "A $50 transport expense is within the $200 policy limit.",
        "category": "low", "expected_tool": "expense_mcp_check_expense_policy",
        "expected_signals": ["within", "200"], "description": "Simple policy check",
    },
    {
        "prompt": "Find me a hotel in Miami",
        "reference": "Fontainebleau Miami at $400/night with a 4.7 rating.",
        "category": "low", "expected_tool": "search_mcp_search_hotels",
        "expected_signals": ["Fontainebleau", "Miami"], "description": "Simple hotel search",
    },
]

MEDIUM_COMPLEXITY_CASES = [
    {
        "prompt": "Submit a $45 meals expense for lunch meeting, user ID EMP001",
        "reference": "Policy checked ($45 within $75 limit). Expense submitted for EMP001, status: approved.",
        "category": "medium", "expected_tool": "expense_mcp_submit_expense",
        "expected_signals": ["EMP001", "45", "approved"], "description": "Submit with policy check",
    },
    {
        "prompt": "Find flights to NYC and compare the cheapest options by airline",
        "reference": "United FL001 at $450 vs Delta FL002 at $520. United is $70 cheaper (13.5% savings).",
        "category": "medium", "expected_tool": "search_mcp_search_flights",
        "expected_signals": ["NYC", "FL001", "FL002"], "description": "Flight comparison",
    },
    {
        "prompt": "Search hotels in New York, then check if the nightly rate fits our lodging policy",
        "reference": "Grand Hyatt $320/night within $400 policy. Budget Inn $120/night within policy.",
        "category": "medium", "expected_tool": "search_mcp_search_hotels",
        "expected_signals": ["400", "within"], "description": "Search + policy cross-check",
    },
    {
        "prompt": "Check if a $100 meal and a $250 entertainment expense are both within policy",
        "reference": "Meals $100 exceeds $75 limit. Entertainment $250 exceeds $150 limit. Both need manager review.",
        "category": "medium", "expected_tool": "expense_mcp_check_expense_policy",
        "expected_signals": ["exceeds", "75", "150"], "description": "Multi-category policy check",
    },
    {
        "prompt": "Show expense history for EMP001 and flag any items that exceeded policy limits",
        "reference": "EMP001 expenses reviewed against policy limits. Violations flagged with overage amounts.",
        "category": "medium", "expected_tool": "expense_mcp_get_user_expenses",
        "expected_signals": ["EMP001"], "description": "History with policy analysis",
    },
    {
        "prompt": "Find the cheapest flight from SFO to JFK and tell me how much I'd save vs the most expensive",
        "reference": "Cheapest: United FL001 at $450. Most expensive: Delta FL002 at $520. Savings: $70 (13.5%).",
        "category": "medium", "expected_tool": "search_mcp_search_flights",
        "expected_signals": ["SFO", "JFK", "450", "520"], "description": "Price comparison with savings",
    },
    {
        "prompt": "Book hotel HT002 for Bob Smith June 15-18, and check if it's within lodging policy",
        "reference": "Hotel HT002 booked for Bob Smith. Rate within $400/night lodging policy.",
        "category": "medium", "expected_tool": "booking_mcp_book_hotel",
        "expected_signals": ["HT002", "Bob Smith", "400"], "description": "Book + policy verify",
    },
]

HIGH_COMPLEXITY_CASES = [
    {
        "prompt": "Plan a 5-day trip to Tokyo for a team of 4: find flights from SFO, hotels, estimate daily meal expenses, and check entertainment policy",
        "reference": "Flights searched. Hotels searched. Meals: $75/person/day x4 = $300/day. Entertainment limit: $150. Total estimated.",
        "category": "high", "expected_tool": "multiple",
        "expected_signals": ["Tokyo", "75", "150"], "description": "Multi-step team trip planning",
    },
    {
        "prompt": "Compare flights from SFO to JFK vs LAX to ORD, factoring in hotel costs in each destination city",
        "reference": "SFO-JFK: FL001 $450 + NYC hotels. LAX-ORD: FL003 $380 + Chicago hotels. Full cost comparison.",
        "category": "high", "expected_tool": "multiple",
        "expected_signals": ["SFO", "JFK", "LAX", "ORD"], "description": "Multi-route comparison with hotels",
    },
    {
        "prompt": "Book flight FL001 for Alice, check if Grand Hyatt is within lodging policy, and submit a $75 meals expense for EMP001",
        "reference": "FL001 booked. Grand Hyatt $320 within $400 policy. $75 meals submitted, approved.",
        "category": "high", "expected_tool": "multiple",
        "expected_signals": ["FL001", "Alice", "400", "75"], "description": "Book + policy + expense pipeline",
    },
    {
        "prompt": "I have a $2000 budget for a London trip. Find flights, hotels, check lodging and meal policies, and tell me if I can afford it",
        "reference": "Flights searched. Hotels searched. Lodging $400/night, meals $75/day. Budget analysis against $2000.",
        "category": "high", "expected_tool": "multiple",
        "expected_signals": ["2000", "400", "75"], "description": "Budget-constrained trip planning",
    },
    {
        "prompt": "Review EMP002's expense history, check all policy categories, and submit a $150 supplies expense for office equipment for EMP002",
        "reference": "EMP002 history reviewed. All limits checked. $150 supplies exceeds $100 limit, pending review.",
        "category": "high", "expected_tool": "multiple",
        "expected_signals": ["EMP002", "100", "exceeds"], "description": "Review + audit + submit pipeline",
    },
    {
        "prompt": "Find the cheapest way to fly from SFO to JFK, book it for Bob Smith, find a hotel within policy, and submit a pre-trip expense estimate",
        "reference": "FL001 $450 booked for Bob Smith. Hotel within $400 policy. Pre-trip estimate submitted.",
        "category": "high", "expected_tool": "multiple",
        "expected_signals": ["FL001", "Bob Smith", "400"], "description": "End-to-end trip booking pipeline",
    },
    {
        "prompt": "Pull expense histories for EMP001 and EMP002, flag policy violations across both, and summarize total overspend by category",
        "reference": "EMP001: no violations. EMP002: entertainment $200 exceeds $150. Total overspend: $50.",
        "category": "high", "expected_tool": "multiple",
        "expected_signals": ["EMP001", "EMP002", "150"], "description": "Multi-user expense audit",
    },
]

TIER_EVAL_CASES = {
    "low": LOW_COMPLEXITY_CASES,
    "medium": MEDIUM_COMPLEXITY_CASES,
    "high": HIGH_COMPLEXITY_CASES,
}


# ---------------------------------------------------------------------------
# Test case and metric selectors
# ---------------------------------------------------------------------------
ALL_AGENTS = ["coordinator_agent", "travel_agent", "expense_agent", "router_agent"]

_EVAL_CASES = {
    "coordinator_agent": COORDINATOR_EVAL_CASES,
    "travel_agent": TRAVEL_EVAL_CASES,
    "expense_agent": EXPENSE_EVAL_CASES,
    "router_agent": ROUTER_EVAL_CASES,
    "lite_agent": STANDALONE_EVAL_CASES,
    "flash_agent": STANDALONE_EVAL_CASES,
    "pro_agent": STANDALONE_EVAL_CASES,
    "sonnet_agent": STANDALONE_EVAL_CASES,
    "opus_agent": STANDALONE_EVAL_CASES,
}


def get_eval_cases(agent_name: str) -> list[dict]:
    """Return the test case list for the given agent."""
    cases = _EVAL_CASES.get(agent_name)
    if cases is None:
        raise ValueError(f"Unknown agent: {agent_name}. Valid: {list(_EVAL_CASES)}")
    return cases


def get_metrics(agent_name: str) -> list:
    """Return the appropriate evaluation metrics for the given agent."""
    return [
        types.RubricMetric.FINAL_RESPONSE_QUALITY,
        types.RubricMetric.HALLUCINATION,
        types.RubricMetric.SAFETY,
        types.RubricMetric.TOOL_USE_QUALITY,
        types.RubricMetric.INSTRUCTION_FOLLOWING,
        types.RubricMetric.FINAL_RESPONSE_MATCH,
    ]

"""Complexity-tiered eval cases for the cross-model experiment.

Each tier contains 7 cases matched to a specific complexity level:
- Low: single tool call, direct lookup
- Medium: 2 tools, comparison, or multi-step reasoning
- High: 3+ tools, cross-domain analysis, budget optimization
"""

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

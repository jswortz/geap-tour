"""Generate test traffic to populate OTel traces for evaluation and monitoring."""

import argparse

import vertexai
from vertexai import agent_engines

from src.config import GCP_PROJECT_ID, GCP_REGION, AGENT_ENGINE_ID

QUERIES = [
    # Travel — happy path
    ("Find me flights from SFO to JFK on June 15th", "alice", "low"),
    ("Search for hotels in New York under $350 per night", "bob", "low"),
    ("Book flight FL001 for Alice Johnson", "alice", "low"),
    ("Book hotel HT001 for Bob Smith, checkin June 15, checkout June 18", "bob", "low"),
    # Travel — edge cases
    ("Find flights from XYZ to ABC", "charlie", "low"),
    ("Search hotels in Atlantis", "charlie", "low"),
    # Expense — happy path
    ("Check if a $50 meal expense is within policy", "alice", "low"),
    ("Submit a $45 meals expense for lunch meeting, user ID EMP001", "alice", "low"),
    ("Show all expenses for user EMP001", "alice", "low"),
    # Expense — edge cases
    ("Submit a $500 entertainment expense for team event, user ID EMP002", "bob", "low"),
    ("Check policy for $1000 in the 'unknown' category", "charlie", "low"),
    # Coordinator — routing
    ("I need to book a trip to Chicago and submit my last meal receipt", "alice", "medium"),
    ("What hotels are available in Miami?", "bob", "low"),
    ("Can you help me with an expense report?", "charlie", "low"),
    # Router-specific: medium complexity
    ("Find flights to NYC and compare the cheapest options by airline", "alice", "medium"),
    ("Search hotels in Boston, then check if the nightly rate fits our lodging policy", "bob", "medium"),
    ("Show my expense history and flag any items that exceeded policy limits", "charlie", "medium"),
    # Router-specific: high complexity
    (
        "Plan a 5-day trip to Tokyo for a team of 4: find flights, hotels near Shibuya, "
        "estimate daily meal expenses, and check entertainment policy",
        "alice",
        "high",
    ),
    (
        "Compare individual vs group flight bookings for Denver, factoring in "
        "cancellation policies, per-diem meals, and hotel location trade-offs",
        "bob",
        "high",
    ),
    (
        "Analyze EMP001's expense history for overspending on entertainment, "
        "draft a policy recommendation, and submit my $45 lunch receipt",
        "charlie",
        "high",
    ),
]


def generate_traffic(
    agent_resource_name: str | None = None,
    count: int = 1,
):
    """Send test queries to a deployed agent to generate OTel traces.

    Args:
        agent_resource_name: Full resource name or agent engine ID. Auto-detects if None.
        count: Number of times to repeat the full query set.
    """
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)

    if agent_resource_name is None:
        agent_resource_name = (
            f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}"
            f"/reasoningEngines/{AGENT_ENGINE_ID}"
        )

    agent = agent_engines.get(agent_resource_name)
    sessions: dict[str, str] = {}
    total_queries = len(QUERIES) * count
    complexity_counts = {"low": 0, "medium": 0, "high": 0}
    errors = 0
    query_num = 0

    print(f"Generating traffic: {total_queries} queries ({count}x{len(QUERIES)})")
    print(f"Agent: {agent_resource_name}\n")

    for rep in range(count):
        if count > 1:
            print(f"\n--- Round {rep + 1}/{count} ---")

        for query, user_id, complexity in QUERIES:
            query_num += 1
            print(f"[{query_num}/{total_queries}] ({complexity}) {query[:70]}")
            complexity_counts[complexity] += 1

            try:
                if user_id not in sessions:
                    session = agent.create_session(user_id=user_id)
                    sessions[user_id] = session["id"]

                response = agent.stream_query(
                    user_id=user_id,
                    session_id=sessions[user_id],
                    message=query,
                )
                full_response = ""
                for chunk in response:
                    if hasattr(chunk, "text"):
                        full_response += chunk.text
                    elif isinstance(chunk, dict) and "text" in chunk:
                        full_response += chunk["text"]
                print(f"  -> {full_response[:100]}...")
            except Exception as e:
                errors += 1
                print(f"  x Error: {e}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"TRAFFIC SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total queries:  {total_queries}")
    print(f"  Errors:         {errors}")
    print(f"  Users:          {', '.join(sessions.keys())}")
    print(f"  By complexity:  low={complexity_counts['low']}  medium={complexity_counts['medium']}  high={complexity_counts['high']}")
    print(f"\n  Check Cloud Trace for spans.")
    if total_queries > 0:
        print(f"  Online monitors will evaluate in ~10 minutes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate test traffic for OTel traces")
    parser.add_argument("agent", nargs="?", default=None, help="Agent resource name or engine ID")
    parser.add_argument("--count", type=int, default=1, help="Repeat query set N times (default: 1)")
    args = parser.parse_args()
    generate_traffic(args.agent, count=args.count)

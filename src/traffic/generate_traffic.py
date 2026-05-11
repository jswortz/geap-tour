"""Generate test traffic to populate OTel traces for evaluation."""

from google import genai
from google.genai import types

from src.config import GCP_PROJECT_ID, GCP_REGION

QUERIES = [
    # Travel — happy path
    "Find me flights from SFO to JFK on June 15th",
    "Search for hotels in New York under $350 per night",
    "Book flight FL001 for Alice Johnson",
    "Book hotel HT001 for Bob Smith, checkin June 15, checkout June 18",
    # Travel — edge cases
    "Find flights from XYZ to ABC",
    "Search hotels in Atlantis",
    # Expense — happy path
    "Check if a $50 meal expense is within policy",
    "Submit a $45 meals expense for lunch meeting, user ID EMP001",
    "Show all expenses for user EMP001",
    # Expense — edge cases
    "Submit a $500 entertainment expense for team event, user ID EMP002",
    "Check policy for $1000 in the 'unknown' category",
    # Coordinator — routing
    "I need to book a trip to Chicago and submit my last meal receipt",
    "What hotels are available in Miami?",
    "Can you help me with an expense report?",
]


def generate_traffic(agent_resource_name: str | None = None):
    """Send test queries to a deployed agent to generate OTel traces."""
    client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )

    if agent_resource_name is None:
        agents = list(client.agent_engines.list())
        if not agents:
            print("No deployed agents found. Deploy first: uv run python src/deploy/deploy_all.py")
            return
        agent_resource_name = agents[0].name
        print(f"Using agent: {agent_resource_name}")

    agent = client.agent_engines.get(agent_resource_name)

    for i, query in enumerate(QUERIES, 1):
        print(f"\n[{i}/{len(QUERIES)}] {query}")
        try:
            session = agent.create_session(user_id=f"test-user-{i % 3}")
            response = session.send_message(query)
            print(f"  → {str(response)[:120]}...")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    print(f"\n✓ Sent {len(QUERIES)} queries — check Cloud Trace for spans")


if __name__ == "__main__":
    import sys
    resource = sys.argv[1] if len(sys.argv) > 1 else None
    generate_traffic(resource)

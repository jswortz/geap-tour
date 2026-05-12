"""Generate test traffic to populate OTel traces for evaluation.

Uses stable user IDs so Memory Bank accumulates memories across sessions.
Multi-turn conversations are grouped per user to exercise memory recall.
"""

import vertexai
from vertexai import agent_engines

from src.config import GCP_PROJECT_ID, GCP_REGION

# Each entry is (user_id, query).  Stable user IDs let Memory Bank build up
# a profile: past bookings, expense history, and preferences.
QUERIES = [
    # Alice — travel power user (multiple sessions build memory)
    ("alice", "Find me flights from SFO to JFK on June 15th"),
    ("alice", "Search for hotels in New York under $350 per night"),
    ("alice", "Book flight FL001 for Alice Johnson"),
    ("alice", "Book hotel HT001 for Alice Johnson, checkin June 15, checkout June 18"),
    # Bob — expense-focused user
    ("bob", "Check if a $50 meal expense is within policy"),
    ("bob", "Submit a $45 meals expense for lunch meeting, user ID EMP001"),
    ("bob", "Show all expenses for user EMP001"),
    # Charlie — mixed usage
    ("charlie", "I need to book a trip to Chicago and submit my last meal receipt"),
    ("charlie", "What hotels are available in Miami?"),
    ("charlie", "Submit a $500 entertainment expense for team event, user ID EMP002"),
    # Edge cases
    ("alice", "Find flights from XYZ to ABC"),
    ("bob", "Check policy for $1000 in the 'unknown' category"),
    ("charlie", "Search hotels in Atlantis"),
    # Memory recall — these should trigger PreloadMemoryTool
    ("alice", "What did I book last time?"),
    ("bob", "Can you help me with an expense report?"),
    ("charlie", "Remind me what hotel I looked at"),
]


def generate_traffic(agent_resource_name: str | None = None):
    """Send test queries to a deployed agent to generate OTel traces."""
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)

    if agent_resource_name is None:
        engines = list(agent_engines.list())
        if not engines:
            print("No deployed agents found. Deploy first: uv run python -m src.deploy.deploy_all")
            return
        agent_resource_name = engines[0].resource_name
        print(f"Using agent: {agent_resource_name}")

    agent = agent_engines.get(agent_resource_name)

    # Track per-user sessions so multi-turn conversations share a session
    user_sessions: dict[str, str] = {}

    for i, (user_id, query) in enumerate(QUERIES, 1):
        print(f"\n[{i}/{len(QUERIES)}] ({user_id}) {query}")
        try:
            # Create a new session per user (or reuse existing one)
            if user_id not in user_sessions:
                session = agent.create_session(user_id=user_id)
                user_sessions[user_id] = session["id"]
            session_id = user_sessions[user_id]

            response = agent.stream_query(
                user_id=user_id,
                session_id=session_id,
                message=query,
            )
            full_response = ""
            for chunk in response:
                if hasattr(chunk, "text"):
                    full_response += chunk.text
                elif isinstance(chunk, dict) and "text" in chunk:
                    full_response += chunk["text"]
            print(f"  -> {full_response[:120]}...")
        except Exception as e:
            print(f"  x Error: {e}")

    print(f"\n Done: sent {len(QUERIES)} queries — check Cloud Trace for spans")
    print(f" Memory Bank: memories generated for users: {list(user_sessions.keys())}")


if __name__ == "__main__":
    import sys
    resource = sys.argv[1] if len(sys.argv) > 1 else None
    generate_traffic(resource)

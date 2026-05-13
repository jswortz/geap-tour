"""End-to-end deployment: MCP servers → agents → online monitors."""

import os

from src.deploy.deploy_mcp_servers import deploy_all_servers
from src.deploy.deploy_agents import deploy_all_agents


def main():
    print("=" * 60)
    print("GEAP Workshop — Full Deployment")
    print("=" * 60)

    # Step 1: Deploy MCP servers to Cloud Run
    print("\n[1/3] Deploying MCP servers to Cloud Run...")
    server_urls = deploy_all_servers()

    # Update environment with deployed URLs so agents can find them
    os.environ["SEARCH_MCP_URL"] = f"{server_urls['search-mcp']}/mcp"
    os.environ["BOOKING_MCP_URL"] = f"{server_urls['booking-mcp']}/mcp"
    os.environ["EXPENSE_MCP_URL"] = f"{server_urls['expense-mcp']}/mcp"

    # Step 2: Deploy agents to Agent Runtime
    print("\n[2/3] Deploying agents to Agent Runtime...")
    agent_resources = deploy_all_agents()

    # Step 3: Setup online evaluators (optional, requires traffic first)
    print("\n[3/3] Skipping online evaluator setup (run after generating traffic)")
    print("  → Generate traffic:     uv run python -m src.traffic.generate_traffic")
    print("  → Setup evaluators:     uv run python -m src.eval.setup_online_evaluators create")
    print("  → Verify (after 10min): uv run python -m src.eval.setup_online_evaluators verify")

    print("\n" + "=" * 60)
    print("Deployment complete!")
    print("=" * 60)
    print("\nMCP Server URLs:")
    for name, url in server_urls.items():
        print(f"  {name}: {url}/mcp")
    print("\nAgent Resources:")
    for name, resource in agent_resources.items():
        print(f"  {name}: {resource}")


if __name__ == "__main__":
    main()

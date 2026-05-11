"""Deploy MCP servers to Cloud Run."""

import subprocess
import sys

from src.config import GCP_PROJECT_ID, GCP_REGION

SERVERS = [
    {"name": "search-mcp", "path": "src/mcp_servers/search", "port": 8001},
    {"name": "booking-mcp", "path": "src/mcp_servers/booking", "port": 8002},
    {"name": "expense-mcp", "path": "src/mcp_servers/expense", "port": 8003},
]


def deploy_server(server: dict) -> str:
    """Deploy a single MCP server to Cloud Run and return the service URL."""
    name = server["name"]
    print(f"\n--- Deploying {name} ---")

    cmd = [
        "gcloud", "run", "deploy", name,
        "--source", server["path"],
        "--region", GCP_REGION,
        "--project", GCP_PROJECT_ID,
        "--port", str(server["port"]),
        "--allow-unauthenticated",
        "--quiet",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR deploying {name}: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"Failed to deploy {name}")

    url_cmd = [
        "gcloud", "run", "services", "describe", name,
        "--region", GCP_REGION,
        "--project", GCP_PROJECT_ID,
        "--format", "value(status.url)",
    ]
    url_result = subprocess.run(url_cmd, capture_output=True, text=True)
    service_url = url_result.stdout.strip()
    print(f"✓ {name} deployed at {service_url}")
    return service_url


def deploy_all_servers() -> dict[str, str]:
    """Deploy all MCP servers and return a map of name → URL."""
    urls = {}
    for server in SERVERS:
        urls[server["name"]] = deploy_server(server)
    return urls


if __name__ == "__main__":
    urls = deploy_all_servers()
    print("\n=== Deployed MCP Server URLs ===")
    for name, url in urls.items():
        print(f"  {name}: {url}/mcp")

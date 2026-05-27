# GEAP Agents Overview

## Coordinator Agent
- **Description:** Central hub for handling user requests, interpreting intent, and orchestrating interactions with other agents and MCP tools.
- **Engine ID:** Reads from `COORDINATOR_AGENT_ID` (or `AGENT_ENGINE_ID`) in `.env`.
- **Identity:** `AGENT_IDENTITY` (SPIFFE-based workload identity).
- **Gateways:** Connected to regional ingress/egress gateways to enforce governance and routing policies.

## Router Agent
- **Description:** Multi-model complexity router. Dynamically assesses prompt complexity and routes traffic to the appropriate model tier (Flash Lite → Flash → Opus) for cost optimization.
- **Engine ID:** Reads from `ROUTER_ENGINE_ID` in `.env`.
- **Identity:** `AGENT_IDENTITY`.
- **Gateways:** Connected to regional ingress/egress gateways.

## Sub-Agents / Tools
- **Travel / Booking:** Handled via `booking-mcp-server`.
- **Expense:** Handled via `expense-mcp-server`.
- **Search:** Handled via `search-mcp-server`.
These tools are deployed on Cloud Run and connected securely using the global Model Context Protocol (MCP).

## Gateway Setup
All runtime agents utilize:
- **Ingress:** `geap-workshop-gateway`
- **Egress:** `geap-workshop-gateway-egress`

*Gemini Enterprise accesses these through separate, global gateways (`geap-workshop-ge-gateway`).*

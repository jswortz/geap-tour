# AGENTS.md — GEAP Workshop Developer Agent Guide

This guide defines workspace-specific rules, architectural constraints, and quick reference workflows for AI developer agents collaborating on the **Gemini Enterprise Agent Platform (GEAP) Tour** repository.

---

## 🚀 Key Commands Quick Reference

All Python execution must run through `uv`.

```bash
# Initialize and sync dependencies
uv sync

# Run the test suite
uv run pytest tests/ -v

# Run specific test files
uv run pytest tests/test_armor.py -v      # Model Armor guardrails
uv run pytest tests/test_router.py -v     # Multi-model router
uv run pytest tests/test_mcp_servers.py   # MCP tool servers

# Deploy all infrastructure & components
bash scripts/deploy_all.sh

# Component-specific deployments
uv run python src/deploy/deploy_agents.py all
uv run python src/deploy/deploy_mcp_servers.py

# Operations & Run-time setup
uv run python -m src.traffic.generate_traffic               # Generate basic test traffic
uv run python src/traffic/async_traffic_alerts.py           # Generate quality alert traffic & check metrics
uv run python -m src.eval.setup_online_evaluators create    # Setup online evals
uv run python -m src.eval.batch_eval                        # Run batch evaluation

# Tear down all resources
bash scripts/cleanup.sh
```

---

## 🏛️ Architecture Overview

The workshop demonstrates a complete multi-agent setup deployed onto Google Cloud using **Vertex AI Agent Engine (Reasoning Engine)** and **FastMCP** tool servers deployed on **Cloud Run**.

```
User Request                         External Services
     │                                      ▲
     ▼                                      │
┌─────────────────────┐          ┌─────────────────────┐
│  Ingress Gateway    │          │  Egress Gateway      │
│  (CLIENT_TO_AGENT)  │          │  (AGENT_TO_ANYWHERE) │
└────────┬────────────┘          └──────────▲───────────┘
         │                                  │
         ▼                                  │
    ┌────────────────────────────────────────┤
    │         Agent Runtime                 │
    │                                       │
    │  Coordinator ──► Travel Agent ────────┤──► MCP Tools (Cloud Run)
    │       │                               │
    │       └──► Expense Agent ─────────────┤──► Gemini / Claude models
    └───────────────────────────────────────┘
```

- **Agents (`src/agents/`)**: Travel, Expense, Coordinator (orchestrates travel/expense sub-agents).
- **Tools (`src/mcp_servers/`)**: Search, Booking, Expense.
- **Model Armor (`src/armor/`)**: Guards input/outputs.
- **Complexity Router (`src/router/`)**: Routes queries across Flash Lite, Flash, or Opus based on input complexity.

---

## ⚠️ Critical Constraints & Gotchas

### 1. Agent Gateway Egress Limitation (b/512837903)
*   **Symptom**: Setting an egress gateway (`agent_to_anywhere_config`) causes the agent to fail immediately at runtime with `503 Network is unreachable` or `Failed to create session`.
*   **Root Cause**: The egress gateway forces all outbound container traffic through an MCP-only proxy. The internal gRPC/HTTPS calls made by the Agent Engine runtime (e.g., `create_session()`, model inference, Cloud Resource Manager lookups) are dropped.
*   **Constraint**: Do NOT enable or configure `AGENT_GATEWAY_EGRESS_PATH` during deployment. Let SPIFFE identity and tracing run independently.

### 2. Gateway Configuration is Immutable
*   Gateway settings (`agent_gateway_config` and `identity_type`) MUST be set at creation time. They cannot be patched or updated on existing engines.
*   **Code Implementation**: Use `vertexai.Client().agent_engines.create(agent=..., config={...})` directly instead of the higher-level wrapper `vertexai.agent_engines.create()`, which hides gateway fields.

### 3. Regional vs. Global Gateways
*   A single Agent Gateway cannot mix Gemini Enterprise (global) and Agent Runtime (regional) targets.
*   The scripts deploy **two separate sets** of gateways:
    *   **Regional**: `geap-workshop-gateway` (e.g. `us-central1` for Agent Runtime).
    *   **Global**: `geap-workshop-ge-gateway` (for Gemini Enterprise).

### 4. Gateway API Versioning
*   Use `networkservices.googleapis.com/v1beta1`. Do not use `v1alpha1`.
*   Do not attempt to use `gcloud alpha agent-gateway` commands (they are deprecated/non-existent). Always make REST API calls via `curl` with access tokens.

---

## 🛠️ Development Conventions

1.  **Environment Variables**: All variables reside in `.env` (copied from `.env.example`). Keep `.env` out of VCS.
2.  **Model Configurations**: Configured in `src/config.py`.
3.  **Shell Scripting**: All `.sh` files must use `set -euo pipefail`.
4.  **Test-Driven Development**: Always run `pytest` to confirm local changes before executing any deployment scripts.
5.  **Secure Coding**: Follow the secure coding guidelines if editing tool interfaces or model configuration scripts (e.g., sanitizing outputs via Model Armor).

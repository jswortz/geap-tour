# Agent Guide — GEAP Workshop (Gemini Enterprise Agent Platform)

Enterprise Agent Platform workshop: ADK agents + MCP tool servers on Google Cloud with gateway governance, evaluation, and multi-model routing.

## Quick Reference

```bash
# Dependencies
uv sync

# Run tests
uv run pytest tests/

# Deploy everything
bash scripts/deploy_all.sh

# Deploy agents only (coordinator, router, or all)
uv run python src/deploy/deploy_agents.py all

# Deploy MCP servers to Cloud Run
uv run python src/deploy/deploy_mcp_servers.py

# Generate traffic (20 queries + 3 memory conversations)
uv run python -m src.traffic.generate_traffic

# Setup online evaluators
uv run python -m src.eval.setup_online_evaluators create

# Run batch eval
uv run python -m src.eval.batch_eval

# Cleanup all resources
bash scripts/cleanup.sh
```

## GCP Project & Environment

- **Project:** `wortz-project-352116`
- **Region:** `us-central1`
- **Config:** Lives in `.env` (copied from `.env.example`), loaded by `src/config.py`
- **Workload Identity:** `AGENT_IDENTITY` (SPIFFE credentials) enabled for per-agent IAM policies and audit trails.

## Architecture & Multi-Agent Topology

Three ADK agents (`coordinator`, `travel`, `expense`) connect to three FastMCP tool servers (`search`, `booking`, `expense`) deployed on Cloud Run. Agents deploy to Vertex AI Agent Engine (Agent Runtime).

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

## ⚠️ Critical Deployment Caveat: Agent Gateway Limitation (b/512837903)

**Gateway config must be set at deploy time** via `agent_gateway_config` and `identity_type` during `agent_engines.create()`. It cannot be PATCHed onto existing agents. Use `vertexai.Client().agent_engines.create(agent=..., config={...})` — the high-level `vertexai.agent_engines.create()` wrapper does NOT expose these fields.

### Egress Gateway Limitation & Known Breakage
Attaching an egress gateway (`agent_to_anywhere_config`) currently breaks runtime execution for Agent Engine agents, resulting in `503 Network is unreachable` and `Failed to create session`.

**Root Cause:** The egress gateway forces all outbound container traffic through an MCP-only proxy (`protocols: ["MCP"]`). The internal gRPC/HTTPS calls made by the Agent Engine runtime (such as `create_session()`, Vertex AI model inference `generateContent`, and Cloud Resource Manager lookups) are dropped by the gateway.

**Repository Code Pointers where this breaks:**
1. **Gateway Config Construction:** [deploy_agents.py](file:///usr/local/google/home/jwortz/geap-tour/src/deploy/deploy_agents.py#L51-L63)
   `_build_gateway_config()` constructs the `agent_to_anywhere_config` mapping when `AGENT_GATEWAY_EGRESS_PATH` is set.
2. **Agent Engine Deployment:** [deploy_agents.py](file:///usr/local/google/home/jwortz/geap-tour/src/deploy/deploy_agents.py#L114-L127)
   Injected into `config["agent_gateway_config"]` and passed to `vertexai.Client().agent_engines.create(agent=agent, config=config)`.
3. **Environment Configuration:** [config.py](file:///usr/local/google/home/jwortz/geap-tour/src/config.py#L12)
   Loads `AGENT_GATEWAY_EGRESS_PATH`.

**Workaround:** Until GCP expands Agent Gateway egress protocol support to include gRPC/HTTPS or updates the Agent Engine runtime to bypass the gateway for internal Google API traffic, keep `AGENT_GATEWAY_EGRESS_PATH` unconfigured/disabled during agent deployment. SPIFFE identity (`AGENT_IDENTITY`) and full telemetry operate independently and remain fully functional.

## Regional vs Global Gateways

A single Agent Gateway cannot support both Gemini Enterprise and Agent Runtime. Deploy two separate sets:
- **Regional** gateways (+ regional registry) for Agent Runtime agents
- **Global** gateways (+ global registry) for Gemini Enterprise

The setup script creates both: `geap-workshop-gateway`/`geap-workshop-gateway-egress` (regional) and `geap-workshop-ge-gateway`/`geap-workshop-ge-gateway-egress` (global).

## Gateway API Version

All gateway operations use `networkservices.googleapis.com/v1beta1` (not v1alpha1). The `gcloud alpha agent-gateway` commands do not exist — use REST API via curl.

## Source Layout

```
src/
  agents/           ADK agent definitions (coordinator, travel, expense)
  armor/            Model Armor config + guardrail callbacks
  config.py         Central config (env vars, model names, engine IDs)
  deploy/           Deploy scripts (Cloud Run MCP + Agent Engine)
  eval/             Evaluation pipeline (batch, online, simulated, monitors)
  mcp_servers/      FastMCP tool servers (search, booking, expense)
  optimize/         GEPA prompt optimization
  registry.py       Agent Registry MCP discovery
  router/           Multi-model complexity router (Flash Lite → Flash → Opus)
  traffic/          Traffic generation for traces
scripts/
  setup_agent_gateway.sh      Create regional + global gateways (v1beta1 REST)
  setup_governance_policies.sh IAM + SGP + Model Armor delegation
  setup_agent_identity.sh     SPIFFE workload identity
  setup_model_armor.sh        Model Armor templates
  setup_logging_sink.sh       BigQuery logging sink
  verify_deployment.sh        Verify all deployed resources
  cleanup.sh                  Tear down all resources
docs/
  workshop_guide.md           Full 4-session walkthrough
  faq.md                      Component FAQ
  eval_operations.md          Eval pipeline operations
```

## Testing

```bash
uv run pytest tests/ -v
uv run pytest tests/test_armor.py -v      # Model Armor guardrails
uv run pytest tests/test_router.py -v     # Multi-model router
uv run pytest tests/test_mcp_servers.py   # MCP tool servers
```

## Multi-Model Complexity Router

Complexity-based routing: Flash Lite (low, 0.0-0.34), Flash (medium, 0.35-0.64), Opus (high, 0.65-1.0). Non-Gemini models use LiteLLM. Threshold configurable via `COMPLEXITY_THRESHOLD_HIGH` env var.

## Evaluation Pipeline

Three tiers:
1. **Batch** — `batch_eval.py` / `one_time_eval.py` (20 test cases, 11 categories)
2. **Online** — `setup_online_evaluators.py` (runs every 10 min against OTel traces)
3. **CI/CD** — `simulated_eval.py` (blocks PRs below score 3.0)

Online monitors: `setup_online_monitors.py` / `manage_monitors.py`

## Conventions

- All Python runs through `uv run`
- Agent Engine IDs stored in `.env` as `AGENT_ENGINE_ID` and `ROUTER_ENGINE_ID`
- MCP server URLs stored in `.env` as `SEARCH_MCP_URL`, `BOOKING_MCP_URL`, `EXPENSE_MCP_URL`
- Shell scripts use `set -euo pipefail` and default to env vars from `.env`
- Gateway REST calls require `$(gcloud auth print-access-token)` — tokens expire hourly

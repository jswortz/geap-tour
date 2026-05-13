# GEAP Workshop — Component FAQ

Quick reference for each component — what it is, how it works, and why it matters in the architecture.

## Table of Contents

1. [ADK Agents](#1-adk-agents)
2. [MCP Servers](#2-mcp-servers)
3. [Multi-Model Router](#3-multi-model-router)
4. [Memory Bank](#4-memory-bank)
5. [Agent Gateway](#5-agent-gateway)
6. [Agent Identity (SPIFFE)](#6-agent-identity-spiffe)
7. [Evaluation Pipeline](#7-evaluation-pipeline)
8. [Model Armor](#8-model-armor)
9. [Agent Registry](#9-agent-registry)
10. [GEPA Optimization](#10-gepa-optimization)

---

## 1. ADK Agents

**What is it?** — Three agents built with the Google Agent Development Kit (ADK) that form the core application layer of the workshop. The Coordinator routes user requests to a Travel Agent and an Expense Agent.

**How does it work?** — The Coordinator agent is an `LlmAgent` that uses `sub_agents` delegation to hand off tasks. When a user asks about flights or hotels, the Coordinator delegates to the Travel Agent, which searches and books via MCP tool connections. Expense-related requests go to the Expense Agent, which submits expenses and checks policies. Each agent connects to its backend MCP servers through `McpToolset`. `before_agent_callback` and `after_agent_callback` hooks enforce guardrails (e.g., content screening) and persist memories after each turn.

**Why does it matter?** — These agents are the entry point for every user interaction. They demonstrate how ADK's declarative agent model, sub-agent orchestration, and callback system compose into a production-grade multi-agent application that plugs into the rest of the GEAP stack.

**Key files:**
- `src/agents/coordinator_agent.py` — Root agent with sub-agent routing and memory callbacks
- `src/agents/travel_agent.py` — Flight and hotel search/booking via MCP tools
- `src/agents/expense_agent.py` — Expense submission and policy checking

---

## 2. MCP Servers

**What is it?** — Three FastMCP tool servers deployed to Cloud Run that expose backend capabilities (search, booking, expense management) over the Model Context Protocol.

**How does it work?** — Each server defines tools using `@mcp.tool()` decorators and serves them via StreamableHTTP transport, making them callable by any MCP-compatible client. The Search server provides `search_flights` and `search_hotels` tools. The Booking server provides `book_flight` and `book_hotel`. The Expense server provides `submit_expense`, `check_expense_policy`, and `get_user_expenses`. Each server includes a `mock_db.py` module with in-memory data for demonstration purposes. All three are containerized with Dockerfiles for Cloud Run deployment. Agents discover MCP servers via the Agent Registry using `AgentRegistry.get_mcp_toolset()` rather than hardcoding URLs — see the `src/registry.py` module.

**Why does it matter?** — MCP servers decouple tool implementation from agent logic, allowing any agent to discover and invoke tools over a standard protocol. This is the backbone of the GEAP architecture's tool layer — agents never call APIs directly; they go through MCP.

**Key files:**
- `src/mcp_servers/search/server.py` — Flight and hotel search tools
- `src/mcp_servers/booking/server.py` — Flight and hotel booking tools
- `src/mcp_servers/expense/server.py` — Expense submission and policy tools
- `src/mcp_servers/search/mock_db.py` — Sample data for search results

---

## 3. Multi-Model Router

**What is it?** — A complexity-based routing layer that directs each prompt to the most cost-effective model, using a Gemini Flash Lite micro-judge to score request difficulty.

**How does it work?** — The complexity scorer in `complexity.py` sends each prompt to Gemini Flash Lite, which returns a score between 0.0 and 1.0. Low-complexity prompts (0.00-0.34) stay on Flash Lite at $0.075/M tokens. Medium-complexity prompts (0.35-0.64) route to Gemini Flash at $0.15/M tokens. High-complexity prompts (0.65-1.0) escalate to Claude Opus via LiteLLM at $15/M tokens. The routing decision is injected through a `before_agent_callback` called `complexity_router_callback` on the router agent. Model thresholds and pricing are configurable in `config.py`.

**Why does it matter?** — Running every request through the most capable model is wasteful. The router demonstrates how to cut inference costs by roughly 50% compared to an all-Opus baseline while maintaining quality on hard queries — a critical production pattern for any multi-model deployment.

**Key files:**
- `src/router/complexity.py` — Flash Lite micro-judge scoring logic
- `src/router/agents.py` — Router agent with `complexity_router_callback` (lines 78-100)
- `src/router/config.py` — Model tiers, thresholds, and pricing configuration

---

## 4. Memory Bank

**What is it?** — Vertex AI Agent Engine's built-in persistent memory system, giving agents the ability to recall past conversations and user preferences across sessions.

**How does it work?** — At the start of each turn, `PreloadMemoryTool()` retrieves relevant memories and injects them into the agent's system instruction, providing context from prior interactions. After each turn, the `save_memories_callback` in the Coordinator agent calls `add_session_to_memory()` to persist new information. Memories are scoped by `{user_id, app_name}`, so each user gets an isolated namespace. The router agent also integrates Memory Bank for cross-session continuity. No external database is needed — Agent Engine handles storage and retrieval natively.

**Why does it matter?** — Stateless agents forget everything between sessions. Memory Bank transforms agents into persistent assistants that learn user preferences, remember booking history, and provide continuity — a requirement for any production agent that interacts with the same user more than once.

**Key files:**
- `src/agents/coordinator_agent.py` — `save_memories_callback` (lines 37-44) and `PreloadMemoryTool` integration
- `src/router/agents.py` — Memory Bank integration in the router agent (lines 103-106)

---

## 5. Agent Gateway

**What is it?** — A dual-mode network governance layer that controls both inbound access to agents (ingress) and outbound access from agents to external services (egress).

**How does it work?** — Two gateways are provisioned. The ingress gateway (`CLIENT_TO_AGENT`, named `geap-workshop-gateway`) acts as a front door, controlling which clients can reach agent endpoints. The egress gateway (`AGENT_TO_ANYWHERE`, named `geap-workshop-gateway-egress`) controls what agents can call — including Gemini model endpoints, MCP tool servers, and external APIs. Three governance layers attach to the gateways via authorization extensions: IAM Allow policies using CEL expressions, Service Governance Policies (SGP) written in natural language, and Model Armor for content screening. The setup script provisions both gateways and wires up all policy attachments.

**Why does it matter?** — Without network-level governance, any agent can call any service. The gateway enforces least-privilege access at the infrastructure layer, independent of application code — a defense-in-depth approach that complements the agent-level guardrails in Model Armor and ADK callbacks.

**Key files:**
- `scripts/setup_agent_gateway.sh` — Gateway creation and configuration
- `scripts/setup_governance_policies.sh` — IAM, SGP, and Model Armor policy attachments

---

## 6. Agent Identity (SPIFFE)

**What is it?** — A SPIFFE-based workload identity system that gives each deployed agent a cryptographic identity, eliminating the need for long-lived service account keys.

**How does it work?** — The setup script creates a Workload Identity Pool, an OIDC provider, and service accounts with CEL-based attestation policies. When an agent runs on Cloud Run or GKE, the platform issues a short-lived OIDC token that maps to a SPIFFE ID. The identity federation layer validates the token against the attestation policy before granting access. Three identity types are defined: ID-1 (User) for human callers, ID-2 (Agent) for autonomous agent workloads, and ID-3 (Delegated) for agents acting on behalf of a user.

**Why does it matter?** — In a multi-agent system, you need to know which agent is making each request. SPIFFE identities provide cryptographic proof of caller identity, enabling fine-grained access control at the gateway and audit logging that traces actions back to specific agents — not just service accounts.

**Key files:**
- `scripts/setup_agent_identity.sh` — Workload Identity Pool, OIDC provider, and attestation policies

---

## 7. Evaluation Pipeline

**What is it?** — A three-tier evaluation system covering batch testing, continuous online monitoring, and CI/CD quality gates for the deployed agents.

**How does it work?** — The first tier is batch evaluation: `one_time_eval.py` and `batch_eval.py` run 20 test cases across 11 categories using custom `PointwiseMetric` rubrics that score safety, quality, tool use, and policy compliance. The second tier is continuous online evaluation: `setup_online_evaluators.py` creates native Online Evaluators that run every 10 minutes against OTel traces, scoring them with 4 predefined metrics and 2 custom rubrics (GEAP Task Quality and GEAP Policy Compliance) registered in the Metric Registry. The third tier is CI/CD integration: `simulated_eval.py` runs in the `eval_ci.yaml` GitHub Actions workflow and blocks pull requests when scores fall below 3.0. Supporting tools include `failure_clusters.py` for grouping error patterns and `quality_alerts.py` for threshold-based notifications.

**Why does it matter?** — Deploying agents without evaluation is flying blind. This pipeline ensures quality at every stage — pre-deployment testing, real-time production monitoring, and automated regression detection — closing the loop between development and production.

**Key files:**
- `src/eval/one_time_eval.py` — Batch evaluation with PointwiseMetric rubrics
- `src/eval/batch_eval.py` — Extended batch evaluation (20 test cases, 11 categories)
- `src/eval/setup_online_evaluators.py` — Native Online Evaluators with custom rubrics (create, list, verify, cleanup)
- `src/eval/simulated_eval.py` — CI/CD eval gate (blocks PRs below score 3.0)
- `.github/workflows/eval_ci.yaml` — GitHub Actions workflow for eval-on-PR
- `src/eval/failure_clusters.py` — Failure pattern clustering and analysis

---

## 8. Model Armor

**What is it?** — A dual-layer content screening system that filters both inputs and outputs for responsible AI violations, prompt injection, jailbreak attempts, and PII leakage.

**How does it work?** — The server-side layer uses Model Armor templates configured via `setup_model_armor.sh`, which define screening rules for RAI categories, prompt injection detection, jailbreak detection, and PII filtering. The client-side layer uses ADK guardrail callbacks: a `before_model_callback` screens user input before it reaches the model, and an `after_model_callback` screens model output before it reaches the user. Template resource names are stored in `.env` as `MODEL_ARMOR_PROMPT_TEMPLATE` and `MODEL_ARMOR_RESPONSE_TEMPLATE`. The armor module in `src/armor/config.py` wires these templates into the ADK callback system.

**Why does it matter?** — Models can be manipulated and can produce harmful content. Model Armor provides defense at two levels — infrastructure (server-side templates) and application (ADK callbacks) — ensuring that content screening cannot be bypassed by skipping one layer.

**Key files:**
- `scripts/setup_model_armor.sh` — Server-side Model Armor template creation
- `src/armor/config.py` — Client-side ADK guardrail callbacks (before/after model)

---

## 9. Agent Registry

**What is it?** — A fleet catalog service for agent discovery, governance, and lifecycle management, allowing administrators to register, find, and control agents across the organization.

**How does it work?** — Agents are registered with metadata describing their capabilities, ownership, and access requirements. Each registration can associate MCP toolspec JSON files that advertise the agent's available tools to other agents and governance systems. The registry provides a single pane of glass for managing the agent fleet — including lifecycle state (active, deprecated, retired), access control policies, and capability advertisement. The setup script automates registration, and toolspec files follow a standardized JSON schema. Agents connect to registered MCP servers programmatically via `AgentRegistry(project_id, location).get_mcp_toolset(server_resource_name)` — this replaces hardcoded URLs with registry-based discovery (see `src/registry.py`).

**Why does it matter?** — As agent fleets grow, discovering what agents exist and what they can do becomes a governance challenge. The registry provides a central source of truth for agent capabilities, enabling automated policy enforcement and preventing shadow deployments. Registry-based MCP discovery also decouples agents from specific server URLs, making rotations and migrations seamless.

**Key files:**
- `src/registry.py` — AgentRegistry singleton and `get_mcp_tools()` helper for MCP discovery
- `scripts/register_agent_registry.sh` — Agent registration automation
- `scripts/toolspecs/search_toolspec.json` — Search server capability advertisement
- `scripts/toolspecs/booking_toolspec.json` — Booking server capability advertisement
- `scripts/toolspecs/expense_toolspec.json` — Expense server capability advertisement

---

## 10. GEPA Optimization

**What is it?** — Gemini Evolutionary Prompt Algorithm, an automated prompt engineering system that uses genetic algorithms to evolve better agent instructions over multiple generations.

**How does it work?** — GEPA starts with an initial set of prompt instruction variants. Each generation, the algorithm mutates instructions using the LLM itself — rephrasing, combining, and refining wording. Every variant is evaluated against a test scenario suite, scoring on metrics like task completion, safety, and coherence. Top-performing variants are selected as parents for the next generation, and underperformers are discarded. This cycle repeats for a configurable number of generations. The wrapper script in `run_optimize.py` orchestrates the process, calling ADK's `adk optimize` command under the hood.

**Why does it matter?** — Hand-tuning prompts is time-consuming and hard to do systematically. GEPA automates the search for better instructions, treating prompt engineering as an optimization problem rather than an art — producing measurably better agent behavior without manual iteration.

**Key files:**
- `src/optimize/run_optimize.py` — GEPA orchestration wrapper

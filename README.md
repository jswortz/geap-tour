# GEAP Workshop: Enterprise Agent Platform Tour

A hands-on workshop demonstrating the full Gemini Enterprise Agent Platform (GEAP) — from building ADK agents with MCP tools through deployment, governance, evaluation, and optimization.

## What's Inside

| Area | Description |
|------|-------------|
| **ADK Agents** | Three agents (travel, expense, coordinator) built with Google Agent Development Kit |
| **MCP Servers** | Three FastMCP tool servers deployed to Cloud Run (search, booking, expense) |
| **Deployment** | Agent Runtime deployment with identity, gateway, and OTel tracing |
| **Evaluation** | One-time, continuous (online monitors), and simulated evaluation pipelines |
| **Agent Armor** | Model Armor templates for input/output screening + client-side guardrails |
| **Governance** | Agent identity (SPIFFE), agent gateway, agent registry |
| **Optimization** | Agent optimization via GEPA algorithm |
| **CI/CD** | GitHub Actions workflow running simulated evals on PRs |
| **Diagrams** | Architecture diagrams generated with Paper Banana |

## Quick Start

```bash
# Install dependencies
uv sync

# Copy and configure environment
cp .env.example .env
# Edit .env with your GCP project details

# Run tests
uv run pytest tests/

# Deploy everything in one command
bash scripts/deploy_all.sh
```

## Screenshots

All screenshots are captured from real deployed GCP resources:

| Screenshot | Feature |
|-----------|---------|
| ![Agent Gateway](docs/screenshots/session1_architecture_overview.png) | Agent Gateway detail (geap-workshop-gateway) |
| ![Cloud Run](docs/screenshots/session1_cloud_run_mcp_detail.png) | MCP server on Cloud Run |
| ![Agent Engine](docs/screenshots/session1_agent_engine.png) | Multi-agent deployment |
| ![Agent Gateway](docs/screenshots/session2_agent_gateway.png) | Agent Gateway (ingress/egress) |
| ![Model Armor](docs/screenshots/session4_model_armor.png) | Input/output screening |
| ![Evaluation](docs/screenshots/session2_evaluation_pipeline.png) | Three-tier eval pipeline |
| ![Agent Registry](docs/screenshots/session3_agent_registry_mcp.png) | MCP servers in Agent Registry |
| ![BigQuery Sink](docs/screenshots/session2_bigquery_sink.png) | Log Router sinks to BigQuery |
| ![Policies](docs/screenshots/session3_policies_iam.png) | IAM Allow governance policies |
| ![Business Policies](docs/screenshots/session3_business_policies.png) | Semantic Governance Policies (SGP) |

## Workshop Guide

See [docs/workshop_guide.md](docs/workshop_guide.md) for the full workshop organized into 4 sessions:

| Session | Topic | Duration |
|---------|-------|----------|
| **Session 1** | AI Gateway / MCP Gateway | ~90 min |
| **Session 2** | AI Gateway / MCP Gateway (continued) | ~75 min |
| **Session 3** | Agent Registry | ~15 min |
| **Session 4** | Model Security / Model Armor | ~15 min |

## Architecture

![GEAP Architecture](docs/screenshots/geap_architecture.png)

*Agent Platform architecture showing the full request flow: User → Frontend → Agent Gateway → Agent Identity (Agent Platform Runtime) → Agent Gateway → downstream Agents, Tools, Models, and APIs. Governed by Agent Registry, AI Security, and Access Authorization with full AI Observability.*

### Agent Identity Model

![Identities in Agentic Apps](docs/screenshots/identity_types.png)

The platform supports three identity types for secure agent operations:

| Identity | Purpose | Issuing System |
|----------|---------|----------------|
| **ID-1: User Identity** | User accessing the agent or SaaS application | Human IdP (Entra, Cloud Identity, Auth0) |
| **ID-2: Agent Identity** | Agent accessing resources under its own authority | GCP — created when agent is deployed |
| **ID-3: Delegated Identity** | Agent accessing resources on behalf of the user | OAuth server (1P or 3P) via OAuth dance |

In our workshop, agents use SPIFFE-based workload identity (ID-2) with attestation policies, and the Agent Gateway enforces identity at the network boundary.

### Paper Banana Architecture Diagrams

| Diagram | Description |
|---------|-------------|
| ![Multi-Agent Topology](diagrams/outputs/01_multi_agent_topology.png) | Coordinator agent routing to travel and expense sub-agents with MCP tool servers |
| ![Deployment Architecture](diagrams/outputs/02_deployment_architecture.png) | Cloud Run MCP servers + Agent Runtime deployment topology |
| ![Evaluation Pipeline](diagrams/outputs/03_eval_pipeline.png) | Three-tier evaluation: one-time, continuous, and CI/CD simulated |
| ![Agent Identity & Gateway](diagrams/outputs/04_agent_identity_gateway.png) | SPIFFE identity, attestation policies, and Agent Gateway flow |
| ![Observability Stack](diagrams/outputs/05_observability_stack.png) | OTel traces → Cloud Trace → BigQuery pipeline |
| ![CI/CD Flow](diagrams/outputs/06_ci_cd_flow.png) | GitHub Actions simulated eval gate on pull requests |
| ![Agent Armor](diagrams/outputs/07_agent_armor.png) | Model Armor input/output screening with guardrail callbacks |

## Project Structure

```
src/
├── agents/          # ADK agent definitions
├── armor/           # Agent Armor — Model Armor config + guardrail callbacks
├── mcp_servers/     # FastMCP tool servers (search, booking, expense)
├── deploy/          # Deployment scripts for Cloud Run + Agent Runtime
├── eval/            # Evaluation pipeline (one-time, online, simulated)
├── optimize/        # Agent optimization (GEPA algorithm)
└── traffic/         # Traffic generation for OTel traces
scripts/             # Shell scripts for identity, gateway, registry setup
diagrams/            # Paper Banana architectural diagrams
docs/                # Workshop guide
tests/               # Unit and integration tests
```

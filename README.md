# GEAP Workshop: Enterprise Agent Platform Tour

A hands-on workshop demonstrating the full Gemini Enterprise Agent Platform (GEAP) — from building ADK agents with MCP tools through deployment, governance, evaluation, and optimization.

## Reference Architecture

![GEAP Reference Architecture (detailed)](diagrams/outputs/08_reference_architecture.png)

*Detailed reference architecture showing all GEAP platform components: Shared Service Project (Agent Gateway with ingress/egress, Model Armor input/output screening, Cloud Armor), Build & CI/CD (Cloud Build, Artifact Registry, Workload Identity Federation), three project zones (Development with ADK, Evaluation Framework, GEPA Optimization, Observability; Testing/Staging with staged agents and MCP servers; Production with Agent Engine, SPIFFE Identity, Memory Bank, Multi-Model Router, OTel Tracing), Agent Registry fleet catalog spanning all projects, Vertex AI Models (Gemini Flash/Pro, Claude Opus via LiteLLM), and Gemini Enterprise with A2A protocol for business end users.*

## What's Inside

| Area | Description |
|------|-------------|
| **ADK Agents** | Three agents (travel, expense, coordinator) built with Google Agent Development Kit |
| **MCP Servers** | Three FastMCP tool servers deployed to Cloud Run (search, booking, expense) |
| **Deployment** | Agent Runtime deployment with identity, gateway, and OTel tracing |
| **Evaluation** | One-time, continuous (online evaluators with custom rubrics), and simulated evaluation pipelines |
| **Model Armor** | Model Armor templates for input/output screening + client-side guardrails |
| **Governance** | Agent identity (SPIFFE), agent gateway (ingress + egress), agent registry, Semantic Governance Policies (SGP) |
| **Multi-Model Router** | Complexity-based routing across Flash Lite, Flash, and Opus |
| **Optimization** | Agent optimization via GEPA algorithm |
| **CI/CD** | GitHub Actions workflow running simulated evals on PRs |
| **Diagrams** | Architecture diagrams generated with Paper Banana |

## Documentation

| Document | Description |
|----------|-------------|
| ▶ **[Interactive Evaluation Notebook](src/eval/demo/evaluation_sdk_demo.ipynb)** | **Start here for evals** — flat & **SDK-first**: every Quality-Flywheel phase calls `client.evals.*` / `vertexai.types.*` **inline** (custom code is explicitly called out), scored against the deployed agent. Headless: `python -m src.eval.demo.full_eval_demo` |
| [Workshop Guide](docs/workshop_guide.md) | Full 4-session hands-on walkthrough |
| [Monitoring Guide](docs/monitoring_integration_guide.md) | Quality alerts and custom metrics bridge guide |
| [Component FAQ](docs/faq.md) | What each component does and why it matters |
| [Evaluation Guide](docs/eval_operations.md) | Evaluation pipeline operations + **coverage matrix** for the GEAP Optimize → Evaluation docs |
| [Evaluation Demo Walkthrough](docs/evaluation_demo.md) | End-to-end Quality Flywheel demo (100% doc coverage) — `python -m src.eval.demo.full_eval_demo` |
| [Evaluation Slides](docs/eval_slides.html) ([.pptx](docs/eval_slides.pptx)) | 5-slide Google Cloud–style teach-in on agent evals (real console screenshots + code deep links) |
| [Cost Comparison](docs/multi_model_cost_comparison.md) | Multi-model routing cost analysis |
| [Publish Agents to Gemini Enterprise](docs/publishing_agents_to_gemini_enterprise.md) | How-to: register the **coordinator + router** agents *directly* to a GE app (ADK reasoning-engine registration) — `agents-cli` + repo script, with live console evidence |
| [Slides](docs/slides.pptx) | Workshop deck (34 slides) |

## Reference Documentation

For official product guides and SDK references:
- [Agent Development Kit (ADK) Overview](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-development-kit/overview)
- [Agent Engine (Agent Runtime)](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview)
- [Model Context Protocol (MCP) on Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-development-kit/mcp-tools)
- [Agent Gateway Ingress & Egress](https://cloud.google.com/products/agent-gateway)
- [Model Armor Security Templates](https://cloud.google.com/security/products/model-armor)
- [Cloud Monitoring Alerts](https://cloud.google.com/monitoring/alerts)
- [Cloud Trace Overview](https://cloud.google.com/trace/docs)
- [Vertex AI Agent Evaluation](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/evaluate)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Agent Registry Overview](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-registry/overview)

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

# Setup governance policies (IAM only)
bash scripts/setup_governance_policies.sh

# Setup governance policies with SGP (IAM + Semantic Governance Policies)
bash scripts/setup_governance_policies.sh --sgp
```

## Agent Ingress Routing & Registry

Requests targeting deployed agents flow through a logical client URN mapped in the **Agent Registry** and governed by the **Agent Gateway**:

1. **Logical Endpoint URN:**
   `urn:endpoint:projects-679926387543:projects:679926387543:locations:global:agentregistry:services:coordinator-agent`
   
2. **Registry Mapping:**
   If a Reasoning Engine is redeployed, the service's interface URL in the registry must be updated:
   ```bash
   gcloud alpha agent-registry services update coordinator-agent \
     --location=global \
     --project=wortz-project-352116 \
     --interfaces=protocolBinding=HTTP_JSON,url=https://us-central1-aiplatform.googleapis.com/v1beta1/projects/wortz-project-352116/locations/us-central1/reasoningEngines/<ACTIVE_ENGINE_ID>
   ```

3. **Running the Traffic Simulator & Alert Verification:**
   To test traffic routing, trigger evaluations, and verify Cloud Monitoring alert policies:
   ```bash
   # Generates bad/good traffic, polls logs, publishes custom metrics, checks alerts
   PYTHONPATH=. uv run python src/traffic/async_traffic_alerts.py
   ```


## Gemini Enterprise Agent — Router Cost Visualizer

The **multi-model router** is published to **Gemini Enterprise** as an A2A/A2UI agent. Business users
chat with it in the GE console; every prompt is classified, routed to the cheapest capable model tier,
and executed, while a **Live Cost Dashboard** renders in the side canvas (KPIs, cumulative cost vs an
all-Opus baseline, spend by tier, and per-prompt routing).

![Gemini Enterprise — Router Cost Visualizer live in the GE canvas](docs/screenshots/ge_router_live_canvas_dashboard.png)

**Try it in Gemini Enterprise**
- Open the agent: [GEAP Router Cost Visualizer in GE](https://vertexaisearch.cloud.google.com/home/cid/c4da98d6-1b97-4e31-bb6a-ba979e363c26/r/agent/14432326554756478249)
- Ask a workload prompt (e.g. *"Plan a 5-day Tokyo trip for 4 with a budget"*) and watch the dashboard accrue cost; use **Routing logic & scoring** to see how each prompt is scored and tiered.

**Deploy / (re)register it yourself**
```bash
# Deploys the A2A/A2UI service to Cloud Run and registers/updates the GE agent
set -a; source .env; set +a
bash scripts/deploy_router_ui.sh
```
- A2A agent card: `https://geap-router-cost-ui-679926387543.us-east1.run.app/a2a/app/.well-known/agent-card.json`
- Backend + UI: [`app/`](app/) · registration: [`scripts/register_router_ui_agent.py`](scripts/register_router_ui_agent.py)
- How routing + cost work: [`docs/multi_model_cost_comparison.md`](docs/multi_model_cost_comparison.md)


## Publish the Two Agents Directly to Gemini Enterprise

Beyond the A2A Router Cost Visualizer above, the workshop's two first-class ADK agents —
**`coordinator_agent`** and **`router_agent`** — can be published **directly** to Gemini Enterprise by
registering their Agent Runtime **reasoning engines** (ADK registration via
`adkAgentDefinition` → `provisionedReasoningEngine`). No Cloud Run wrapper is needed; GE invokes the
reasoning engine natively. In the GE Agents table they appear as type **Agent Engine** (contrast the
Router Cost Visualizer's **A2A (Custom)**).

![Coordinator + router published directly to Gemini Enterprise](docs/screenshots/ge_two_agents_published.png)

**Publish both yourself** (idempotent — re-runs update the registration in place):
```bash
set -a; source .env; set +a
uv run python scripts/publish_agents_to_ge.py     # REST publisher (requests + google-auth only)
# ...or the official CLI wrapper:
bash scripts/publish_agents_to_ge.sh              # agents-cli publish gemini-enterprise (ADK mode)
```
- Full how-to: [`docs/publishing_agents_to_gemini_enterprise.md`](docs/publishing_agents_to_gemini_enterprise.md)
- Publisher: [`scripts/publish_agents_to_ge.py`](scripts/publish_agents_to_ge.py) · CLI wrapper: [`scripts/publish_agents_to_ge.sh`](scripts/publish_agents_to_ge.sh)
- Live in GE (engine `gemini-enterprise-17634901_1763490144996`): **GEAP Corporate Travel & Expense Assistant** (`3686131016255017939`) · **GEAP Multi-Model Cost Router** (`13895830063069432068`) — both **Enabled**


## Screenshots

All screenshots are captured from real deployed GCP resources:

| Screenshot | Feature |
|-----------|---------|
| ![Agent Gateway](docs/screenshots/session1_architecture_overview.png) | Agent Gateway ingress detail (geap-workshop-gateway) |
| ![Cloud Run](docs/screenshots/session1_cloud_run_mcp_detail.png) | MCP server on Cloud Run |
| ![Agent Engine](docs/screenshots/session1_agent_engine.png) | Multi-agent deployment |
| ![Agent Gateway](docs/screenshots/session2_agent_gateway.png) | Agent Gateway (ingress + egress) |
| ![Traces](docs/screenshots/session2_agent_traces.png) | Agent traces — session view with model calls and token usage |
| ![Trace Spans](docs/screenshots/session2_agent_trace_spans.png) | Trace spans — individual trace view |
| ![Model Armor](docs/screenshots/session4_model_armor.png) | Input/output screening |
| ![Evaluation](docs/screenshots/session2_evaluation_pipeline.png) | Three-tier eval pipeline |
| ![Evaluation Console](docs/screenshots/eval_console_evaluation.png) | Agent Platform → Agents → Evaluation (Experiments / Metrics / Online monitors) |
| ![Metrics Console](docs/screenshots/eval_console_metrics_tab.png) | Evaluation → Metrics — predefined + registered GEAP custom metrics |
| ![Online Monitors Console](docs/screenshots/eval_console_online_monitors.png) | Evaluation → Online monitors — active continuous evaluators |
| ![Alerting Console](docs/screenshots/eval_console_monitoring_alerts.png) | Cloud Monitoring → Alerting — GEAP quality-drift alert policies |
| ![Agent Registry](docs/screenshots/session3_agent_registry_mcp.png) | MCP servers in Agent Registry |
| ![BigQuery Sink](docs/screenshots/session2_bigquery_sink.png) | Log Router sinks to BigQuery |
| ![Policies](docs/screenshots/session3_policies_iam.png) | IAM Allow governance policies |
| ![Business Policies](docs/screenshots/session3_business_policies.png) | Semantic Governance Policies (SGP) |
| ![Metrics Explorer Out-of-Spec](docs/screenshots/session5_metrics_explorer_out_of_spec.png) | Cloud Monitoring Metrics Explorer showing evaluation scores drop |
| ![Quality Alert Firing](docs/screenshots/session5_monitoring_alert_firing.png) | Cloud Monitoring Alerting Policy in FIRING state |
| ![Two agents in Gemini Enterprise](docs/screenshots/ge_two_agents_published.png) | Coordinator + router published directly to Gemini Enterprise (type **Agent Engine**, Enabled) |

## Workshop Guide

See [docs/workshop_guide.md](docs/workshop_guide.md) for the full workshop organized into 4 sessions. For component-level details, see the [Component FAQ](docs/faq.md).

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
| ![Model Armor](diagrams/outputs/07_agent_armor.png) | Model Armor input/output screening with guardrail callbacks |
| ![Reference Architecture](diagrams/outputs/08_reference_architecture.png) | Comprehensive reference architecture — all GEAP components in a single diagram |

## Project Structure

```
src/
├── agents/          # ADK agent definitions
├── armor/           # Model Armor config + guardrail callbacks
├── mcp_servers/     # FastMCP tool servers (search, booking, expense)
├── deploy/          # Deployment scripts for Cloud Run + Agent Runtime
├── eval/            # Evaluation pipeline (one-time, online, simulated)
├── optimize/        # Agent optimization (GEPA algorithm)
├── router/          # Multi-model complexity router
└── traffic/         # Traffic generation for OTel traces
scripts/             # Shell scripts for identity, gateway, registry setup
diagrams/            # Paper Banana architectural diagrams
docs/                # Workshop guide
tests/               # Unit and integration tests
```

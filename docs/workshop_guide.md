# GEAP Workshop Guide

A hands-on walkthrough of the Gemini Enterprise Agent Platform — from building agents to production governance. Estimated time: ~3 hours.

---

## Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI authenticated (`gcloud auth application-default login`)
- Python 3.11+ with `uv` installed
- APIs enabled: Vertex AI, Cloud Run, Cloud Monitoring, Cloud Logging, BigQuery

```bash
gcloud services enable \
    aiplatform.googleapis.com \
    run.googleapis.com \
    monitoring.googleapis.com \
    logging.googleapis.com \
    bigquery.googleapis.com
```

---

## Section 1: Architecture Overview (~10 min)

**Concept**: The GEAP provides a complete lifecycle for enterprise AI agents — build, deploy, govern, evaluate, and optimize.

**Diagram**: `diagrams/outputs/01_multi_agent_topology.png`

Our workshop system has three ADK agents sharing three MCP tool servers:
- **Coordinator Agent** — routes requests to specialists
- **Travel Agent** — searches flights/hotels, makes bookings
- **Expense Agent** — submits expenses, enforces policy limits

**Key insight**: Multiple agents can share the same MCP server (e.g., both Travel Agent and Coordinator use the Search MCP), demonstrating the 1→many topology.

---

## Section 2: Building ADK Agents (~15 min)

**Code**: `src/agents/travel_agent.py`

ADK agents are defined with `LlmAgent` — a model, a name, instructions, and tools:

```python
from google.adk.agents import LlmAgent
from google.adk.tools.mcp import McpToolset, StreamableHTTPConnectionParams

travel_agent = LlmAgent(
    model='gemini-2.0-flash',
    name='travel_agent',
    instruction='You help users search and book flights...',
    tools=[
        McpToolset(connection_params=StreamableHTTPConnectionParams(url=SEARCH_URL)),
        McpToolset(connection_params=StreamableHTTPConnectionParams(url=BOOKING_URL)),
    ],
)
```

**Multi-agent orchestration** (`src/agents/coordinator_agent.py`):
```python
coordinator_agent = LlmAgent(
    ...
    sub_agents=[travel_agent, expense_agent],
)
```

**Console tour**: Navigate to Vertex AI → Agent Builder in the Cloud Console.

---

## Section 3: MCP Server Development (~15 min)

**Code**: `src/mcp_servers/search/server.py`

MCP servers expose tools via the Model Context Protocol. We use FastMCP:

```python
from fastmcp import FastMCP

mcp = FastMCP("search-mcp")

@mcp.tool()
def search_flights(origin: str, destination: str, date: str | None = None) -> list[dict]:
    """Search available flights."""
    ...
```

Each server has:
- `mock_db.py` — in-memory data (swap with real DB in production)
- `server.py` — FastMCP tool definitions
- `Dockerfile` — for Cloud Run deployment

**Try it locally**:
```bash
# Start the search MCP server
uv run python -m src.mcp_servers.search.server
# In another terminal, test with the MCP inspector or fastmcp client
```

---

## Section 4: Multi-Agent + MCP Topology (~10 min)

**Diagram**: `diagrams/outputs/01_multi_agent_topology.png`

The topology demonstrates key GEAP patterns:
- **Agent → MCP**: Each agent connects to MCP servers via `StreamableHTTPConnectionParams`
- **1→many**: The Search MCP is shared by Travel Agent and Coordinator
- **Sub-agents**: Coordinator delegates to Travel and Expense agents
- **Separation of concerns**: Tools are isolated in MCP servers, agents focus on reasoning

**Console tour**: View the agent-tool connections in the Agent Registry.

---

## Section 5: Deploying MCP Servers to Cloud Run (~15 min)

**Code**: `src/deploy/deploy_mcp_servers.py`

MCP servers deploy as standard Cloud Run services:

```bash
uv run python src/deploy/deploy_mcp_servers.py
```

This runs `gcloud run deploy` for each server with its Dockerfile.

**Console tour**: Navigate to Cloud Run → Services. Show the three deployed MCP servers, their URLs, and logs.

**Diagram**: `diagrams/outputs/02_deployment_architecture.png`

---

## Section 6: Deploying Agents to Agent Runtime (~15 min)

**Code**: `src/deploy/deploy_agents.py`

Agents deploy to Vertex AI Agent Runtime via the `google-genai` SDK:

```python
from google.adk.app import AdkApp

app = AdkApp(agent=travel_agent, enable_tracing=True)
remote_app = client.agent_engines.create(
    agent=app,
    config={
        "requirements": [...],
        "staging_bucket": "gs://...",
        "env_vars": {
            "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
        },
    },
)
```

Key deployment options:
- `enable_tracing=True` — auto-instruments with OpenTelemetry
- `requirements` — Python packages the agent needs at runtime
- `env_vars` — OTel configuration for Cloud Trace integration

**Console tour**: Navigate to Vertex AI → Agents. Show the deployed agents, their configurations, and the "Test" panel.

---

## Section 7: Agent Identity (SPIFFE) (~10 min)

**Script**: `scripts/setup_agent_identity.sh`

Each agent gets a SPIFFE-based identity when deployed with `identity_type=AGENT_IDENTITY`:

```
principal://agents.global.org-{ORG_ID}.system.id.goog/agent/{AGENT_ID}
```

This enables:
- **Per-agent IAM policies** — grant specific agents access to specific resources
- **Audit trails** — every action traces back to a specific agent identity
- **Workload Identity Federation** — agents authenticate without service account keys

```python
config = {"identity_type": types.IdentityType.AGENT_IDENTITY}
```

**Console tour**: Navigate to IAM & Admin → Workload Identity Pools. Show the agent pool and bound principals.

**Diagram**: `diagrams/outputs/04_agent_identity_gateway.png`

---

## Section 8: Agent Gateway (~10 min)

**Script**: `scripts/setup_agent_gateway.sh`

The Agent Gateway controls what agents can communicate with:

- **Egress policies**: What external services agents can call (e.g., allow `*.run.app`)
- **Ingress policies**: What can call your agents

```python
config = {
    "agent_gateway_config": {
        "agent_to_anywhere_config": {
            "agent_gateway": "projects/.../agentGateways/..."
        }
    }
}
```

**Console tour**: Navigate to Agent Gateway in the console. Show egress/ingress rules and audit logs.

---

## Section 9: One-Time Evaluation (~15 min)

**Code**: `src/eval/one_time_eval.py`

One-time evaluation uses `PointwiseMetricPromptTemplate` for custom rubric-based scoring:

```python
HELPFULNESS_METRIC = types.PointwiseMetricPromptTemplate(
    name="helpfulness",
    criteria="Does the response provide helpful information?",
    rating_rubric={
        "1": "Not helpful",
        "5": "Very helpful — exceeds expectations",
    },
)
```

Three custom metrics:
1. **Helpfulness** — relevance and actionability of responses
2. **Tool use accuracy** — correct MCP tool selection and parameters
3. **Policy compliance** — proper enforcement of expense limits

```bash
uv run python -m src.eval.one_time_eval <agent-resource-name>
```

**Console tour**: Navigate to Vertex AI → Evaluation. Show eval results, per-metric scores, and individual sample breakdowns.

**Diagram**: `diagrams/outputs/03_eval_pipeline.png`

---

## Section 10: Online Monitors (Continuous Eval) (~15 min)

**Code**: `src/eval/setup_online_monitors.py`

Online monitors evaluate live agent traffic on a 10-minute cycle:

1. Agent handles user requests → OTel traces flow to Cloud Trace
2. Every 10 minutes, the monitor samples recent traces
3. Runs the same `PointwiseMetricPromptTemplate` rubrics
4. Results flow to BigQuery for analysis

```bash
# Generate traffic first
uv run python src/traffic/generate_traffic.py

# Setup monitors
uv run python -m src.eval.setup_online_monitors <agent-resource-name>

# Wait 10+ minutes, then verify
uv run python -m src.eval.verify_monitors
```

**Manage monitors**:
```bash
uv run python -m src.eval.manage_monitors list
uv run python -m src.eval.manage_monitors pause <monitor-name>
uv run python -m src.eval.manage_monitors resume <monitor-name>
```

**Console tour**: Navigate to Vertex AI → Evaluation → Online Monitors. Show active monitors, their schedules, and recent results.

---

## Section 11: Simulated Evaluation for CI/CD (~15 min)

**Code**: `src/eval/simulated_eval.py`

Simulated evaluation generates synthetic test scenarios and runs them through the agent:

```python
# 1. Generate scenarios
eval_dataset = client.evals.generate_conversation_scenarios(
    agent_info=types.evals.AgentInfo.load_from_agent(agent=agent),
    config={"count": 10, "generation_instruction": "Travel booking scenarios"},
)

# 2. Run inference
eval_with_traces = client.evals.run_inference(
    agent=agent, src=eval_dataset,
    config={"user_simulator_config": {"max_turn": 5}},
)

# 3. Evaluate
eval_result = client.evals.evaluate(
    src=eval_with_traces, config={"metrics": [helpfulness_metric]},
)
```

**CI/CD integration** (`.github/workflows/eval_ci.yaml`):
- On every PR that changes agent code → deploy temp agent → run simulated eval → block if score < 3.0 → cleanup

```bash
uv run python -m src.eval.simulated_eval <agent-resource-name> 3.0
```

**Console tour**: Show a GitHub Actions run with the eval results.

**Diagram**: `diagrams/outputs/06_ci_cd_flow.png`

---

## Section 12: Failure Clusters & Quality Alerts (~10 min)

### Failure Clusters

**Code**: `src/eval/failure_clusters.py`

Instead of reviewing failures individually, `generate_loss_clusters()` groups similar failure patterns:

```bash
uv run python -m src.eval.failure_clusters <eval-result-name>
```

Output shows clusters with titles, descriptions, sample counts, and average scores — enabling targeted improvements.

### Quality Alerts

**Code**: `src/eval/quality_alerts.py`

Set up Cloud Monitoring alerts that fire when eval scores drop:

```bash
# Create alert for helpfulness score dropping below 3.0
uv run python -m src.eval.quality_alerts helpfulness 3.0

# List existing alerts
uv run python -m src.eval.quality_alerts list
```

**Console tour**: Navigate to Cloud Monitoring → Alerting. Show the alert policy, condition, and notification channel configuration.

**Diagram**: `diagrams/outputs/05_observability_stack.png`

---

## Section 13: Agent Armor (Model Armor) (~15 min)

**Code**: `src/armor/config.py` | **Script**: `scripts/setup_model_armor.sh`

Agent Armor protects agents at two layers:

### Layer 1: Server-side — Model Armor Templates

Model Armor templates screen every prompt and response for:
- **Prompt injection / jailbreak detection** (confidence: MEDIUM_AND_ABOVE)
- **Content safety** — hate, harassment, dangerous content, sexually explicit
- **Sensitive data protection** — SSNs, credit cards, API keys (auto-redaction)
- **Malicious URL detection** — phishing and malware links

```bash
# Create Model Armor templates in your GCP project
bash scripts/setup_model_armor.sh
```

Templates are wired into agents via `GenerateContentConfig`:

```python
from google.genai.types import GenerateContentConfig, ModelArmorConfig

travel_agent = LlmAgent(
    model='gemini-2.0-flash',
    name='travel_agent',
    instruction='...',
    tools=[...],
    generate_content_config=GenerateContentConfig(
        model_armor_config=ModelArmorConfig(
            prompt_template_name="projects/.../templates/geap-workshop-prompt",
            response_template_name="projects/.../templates/geap-workshop-response",
        )
    ),
)
```

### Layer 2: Client-side — Input Guardrail Callback

A `before_agent_callback` runs before any request reaches the model:

```python
from src.armor.config import input_guardrail_callback

agent = LlmAgent(
    ...
    before_agent_callback=input_guardrail_callback,
)
```

The callback blocks:
- **Prompt injection patterns** — "ignore previous instructions", "system:", etc.
- **Script injection** — `<script>` tags
- **Oversized inputs** — over 4000 characters

```bash
# Test the guardrails
uv run pytest tests/test_armor.py -v
```

**Console tour**: Navigate to Security → Model Armor in the Cloud Console. Show templates, filter configurations, and enforcement logs.

**Diagram**: `diagrams/outputs/07_agent_armor.png`

---

## Section 14: Agent Optimization (GEPA) (~10 min)

**Code**: `src/optimize/run_optimize.py`

The `adk optimize` command uses the GEPA algorithm to iteratively improve agent system instructions:

1. Evaluate the current instruction against test scenarios
2. Analyze failure patterns
3. Generate instruction variants
4. Evaluate variants and select the best performer

```bash
uv run python -m src.optimize.run_optimize src.agents.travel_agent
```

This produces optimized system instructions that can be compared to the original.

**Console tour**: Show the optimization results — original vs. optimized instructions, and score improvements.

---

## Appendix: Full Deployment Sequence

```bash
# 1. Setup environment
cp .env.example .env
# Edit .env with your GCP project details
uv sync

# 2. Setup infrastructure
bash scripts/setup_agent_identity.sh
bash scripts/setup_agent_gateway.sh
bash scripts/setup_model_armor.sh
bash scripts/setup_logging_sink.sh

# 3. Deploy everything
uv run python src/deploy/deploy_all.py

# 4. Generate traffic
uv run python src/traffic/generate_traffic.py

# 5. Setup evaluation
uv run python -m src.eval.setup_online_monitors <agent-resource-name>
uv run python -m src.eval.quality_alerts helpfulness 3.0

# 6. Run one-time eval
uv run python -m src.eval.one_time_eval <agent-resource-name>

# 7. Generate diagrams
cd diagrams && paperbanana batch --manifest batch_manifest.yaml

# 8. Cleanup when done
bash scripts/cleanup.sh
```

---

## Appendix: Generating Diagrams

All architecture diagrams are generated with Paper Banana at 4K resolution:

```bash
cd diagrams
paperbanana batch --manifest batch_manifest.yaml
```

Individual diagrams:
```bash
paperbanana generate --input inputs/01_multi_agent_topology.txt --output outputs/01_multi_agent_topology.png --width 3840 --height 2160
```

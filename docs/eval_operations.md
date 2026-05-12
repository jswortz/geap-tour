# GEAP Evaluation Operations Guide

This guide covers the end-to-end evaluation pipeline: batch evals, complexity routing, online monitors, and CI/CD integration with GitHub Actions using Workload Identity Federation.

---

## Architecture Overview

```
                    ┌─────────────────────────────────────────────┐
                    │          GitHub Actions CI/CD                │
                    │  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
                    │  │Unit Tests│  │Batch Eval│  │Complexity │ │
                    │  └────┬─────┘  └────┬─────┘  │  Eval     │ │
                    │       │             │         └─────┬─────┘ │
                    └───────┼─────────────┼───────────────┼───────┘
                            │             │               │
                   Workload Identity Federation (WIF)
                            │             │               │
                    ┌───────▼─────────────▼───────────────▼───────┐
                    │              Google Cloud                     │
                    │                                               │
                    │  ┌──────────────┐   ┌──────────────────────┐ │
                    │  │ Agent Engine  │   │ Vertex AI Evaluation │ │
                    │  │ (Coordinator) │   │ Service              │ │
                    │  │              ◄────┤  - EvalTask          │ │
                    │  │  Travel Agent │   │  - EvalRun (genai)   │ │
                    │  │  Expense Agent│   │  - Online Monitors   │ │
                    │  │  Router Agent │   │                      │ │
                    │  └──────┬───────┘   └──────────┬───────────┘ │
                    │         │                      │              │
                    │  ┌──────▼───────┐   ┌──────────▼───────────┐ │
                    │  │ Cloud Trace  │   │ BigQuery             │ │
                    │  │ (OTel spans) │   │ (eval scores, logs)  │ │
                    │  └──────────────┘   └──────────────────────┘ │
                    │                                               │
                    │  ┌──────────────┐   ┌──────────────────────┐ │
                    │  │ Cloud        │   │ Vertex AI            │ │
                    │  │ Monitoring   │   │ Experiments          │ │
                    │  │ (alerts)     │   │ (geap-batch-eval)    │ │
                    │  └──────────────┘   └──────────────────────┘ │
                    └──────────────────────────────────────────────┘
```

---

## 1. Batch Evaluations

Batch evals run agent inference on predefined test cases, then score responses using Vertex AI's evaluation metrics (coherence, fluency, safety, groundedness) and custom metrics (policy compliance, complexity routing).

### Results

![Batch Evaluation Scores](screenshots/eval_batch_scores.png)

**Real results from May 12, 2026 eval run:**

| Metric        | Score    | Threshold | Status |
|---------------|----------|-----------|--------|
| Coherence     | 5.00 / 5 | 3.00      | PASS   |
| Fluency       | 4.80 / 5 | 3.00      | PASS   |
| Safety        | 1.00     | 0.80      | PASS   |
| Groundedness  | 0.20     | 0.50      | BELOW  |

> Groundedness scores low because responses include tool-retrieved data (flight prices, hotel rates) that aren't in the original prompt. This is expected behavior for an agent that calls tools.

### Per-Case Scores

![Per-Case Evaluation Scores](screenshots/eval_per_case_scores.png)

### Running Batch Evals

```bash
# Single agent
uv run python -m src.eval.multi_agent_batch_eval --agents coordinator_agent

# All agents
uv run python -m src.eval.multi_agent_batch_eval

# List available test cases
uv run python -m src.eval.multi_agent_batch_eval --list-cases

# Custom threshold
uv run python -m src.eval.multi_agent_batch_eval --threshold 4.0 --output results.json
```

### Test Cases Per Agent

| Agent             | Cases | Categories                                      |
|-------------------|-------|------------------------------------------------|
| coordinator_agent | 20    | routing, multi-intent, flight, hotel, expense   |
| travel_agent      | 10    | flight search, hotel search, booking, edge cases|
| expense_agent     | 10    | policy check, submission, history, over-limit   |
| router_agent      | 12    | low/medium/high complexity classification       |

### Code: Multi-Agent Batch Eval Runner

```python
# src/eval/multi_agent_batch_eval.py (simplified)
from src.eval.agent_eval_configs import build_agent_info, get_eval_cases, get_metrics

for agent_name in ["coordinator_agent", "travel_agent", "expense_agent", "router_agent"]:
    cases = get_eval_cases(agent_name)
    agent_info = build_agent_info(agent_name)
    metrics = get_metrics(agent_name)

    # Run inference against deployed agent
    inference_result = client.evals.run_inference(
        agent=agent_resource_name,
        src=eval_df,
    )

    # Score with Vertex AI evaluation service
    evaluation_run = client.evals.create_evaluation_run(
        dataset=inference_result,
        agent_info=agent_info,
        metrics=metrics,
    )
```

---

## 2. Complexity Routing Evaluation

The multi-model router uses a Gemini Flash Lite micro-judge to classify prompt complexity (low/medium/high) and route to the appropriate model tier:

- **Low** (score 0.0-0.3): Gemini Flash Lite — simple lookups
- **Medium** (score 0.4-0.6): Gemini Flash — moderate reasoning
- **High** (score 0.7-1.0): Claude Opus via Vertex AI — multi-step planning

### Results

![Complexity Routing Evaluation](screenshots/eval_complexity_routing.png)

**Classifier performance:**

| Expected | Predicted Low | Predicted Medium | Predicted High |
|----------|:---:|:---:|:---:|
| Low      | 2   | 3   | 0   |
| Medium   | 0   | 1   | 2   |
| High     | 0   | 0   | 4   |

The classifier tends to over-estimate complexity (bias upward). High-complexity prompts are classified correctly 100% of the time. The upward bias is acceptable — routing a simple query to a more capable model is better than routing a complex query to a weaker one.

**Cost analysis:**
- Smart router cost: **$0.2448** (12 prompts)
- All-Opus baseline: **$0.4860**
- Savings: **49.6%**

### Code: Complexity Classifier

```python
# src/router/complexity.py
async def classify_complexity(prompt: str) -> ComplexityResult:
    """Use Gemini Flash Lite as a micro-judge to score prompt complexity 0-1."""
    client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION)
    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=CLASSIFIER_PROMPT_TEMPLATE.format(prompt=prompt),
        config=GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            max_output_tokens=80,
            temperature=0.0,
        ),
    )
    data = json.loads(response.text)
    score = max(0.0, min(1.0, float(data["score"])))
    return ComplexityResult(
        level=_score_to_level(score),
        score=score,
        reason=data.get("reason", ""),
    )
```

### Running Complexity Eval

```bash
uv run python -c "
import asyncio
from src.eval.complexity_metrics import run_complexity_accuracy_eval, run_cost_efficiency_eval
from src.eval.agent_eval_configs import ROUTER_EVAL_CASES

accuracy = asyncio.run(run_complexity_accuracy_eval(ROUTER_EVAL_CASES))
cost = asyncio.run(run_cost_efficiency_eval(ROUTER_EVAL_CASES))

print(f'Accuracy: {accuracy[\"accuracy_pct\"]}')
print(f'Savings: {cost[\"savings_pct\"]}%')
"
```

---

## 3. ADK Static Evaluations (Tool Trajectory)

ADK evalsets define expected tool calls for each prompt, enabling automated verification that the agent routes to the correct tools with correct arguments.

### Evalset Schema

```json
{
  "eval_set_id": "coordinator_eval_set",
  "eval_cases": [{
    "eval_id": "flight_search_sfo_jfk",
    "conversation": [{
      "user_content": {
        "parts": [{"text": "Find flights from SFO to JFK on June 15"}],
        "role": "user"
      },
      "final_response": {
        "parts": [{"text": "I found several flights..."}],
        "role": "model"
      },
      "intermediate_data": {
        "tool_uses": [{
          "name": "search_flights",
          "args": {"origin": "SFO", "destination": "JFK", "date": "2026-06-15"}
        }]
      }
    }],
    "session_input": {"app_name": "geap_workshop", "user_id": "eval_user"}
  }]
}
```

### Eval Config (Built-in + Custom Metrics)

```json
{
  "criteria": {
    "tool_trajectory_avg_score": { "threshold": 0.8, "match_type": "IN_ORDER" },
    "response_match_score": 0.6,
    "final_response_match_v2": { "threshold": 0.7 },
    "hallucinations_v1": { "threshold": 0.5 },
    "safety_v1": 0.8,
    "complexity_routing": { "threshold": 0.8 }
  },
  "custom_metrics": {
    "complexity_routing": {
      "code_config": {
        "name": "src.eval.complexity_metrics.check_complexity_routing"
      }
    }
  }
}
```

### Running ADK Static Evals

```bash
# Run with tool trajectory matching
adk eval src/agents/coordinator \
  --config_file_path src/eval/evalsets/eval_config.json \
  coordinator_eval_set \
  --print_detailed_results
```

### Available Evalsets

| File | Cases | Focus |
|------|-------|-------|
| `coordinator.evalset.json` | 10 | Full routing + multi-intent |
| `travel_agent.evalset.json` | 10 | Flight/hotel search + booking |
| `expense_agent.evalset.json` | 10 | Policy check + submission |
| `router_agent.evalset.json` | 12 | Complexity levels (low/med/high) |

---

## 4. ADK User Simulator Evaluations (Multi-Turn)

The ADK user simulator generates dynamic multi-turn conversations using conversation scenarios with starting prompts, conversation plans, and user personas.

### Scenario Schema

```json
{
  "scenarios": [{
    "starting_prompt": "I need help with a work trip",
    "conversation_plan": "Ask to search flights from SFO to JFK. After results, book the cheapest. Then submit a $45 meal expense.",
    "user_persona": "NOVICE"
  }]
}
```

### Running User Sim Evals

```bash
# Create evalset from scenarios
adk eval_set create src/agents/coordinator eval_set_coordinator_sim
adk eval_set add_eval_case src/agents/coordinator eval_set_coordinator_sim \
  --scenarios_file src/eval/scenarios/coordinator_scenarios.json \
  --session_input_file src/eval/scenarios/session_input.json

# Run with multi-turn metrics
adk eval src/agents/coordinator \
  --config_file_path src/eval/scenarios/eval_config.json \
  eval_set_coordinator_sim \
  --print_detailed_results

# Generate synthetic scenarios
adk eval_set generate_eval_cases src/agents/coordinator eval_set_coordinator_gen \
  --user_simulation_config_file=src/eval/scenarios/user_sim_config.json
```

### Multi-Turn Metrics

| Metric | Description |
|--------|-------------|
| `rubric_based_final_response_quality_v1` | Response quality judged by LLM |
| `rubric_based_tool_use_quality_v1` | Tool selection and argument accuracy |
| `hallucinations_v1` | Factual grounding of responses |
| `safety_v1` | Content safety |
| `multi_turn_task_success_v1` | Did the agent complete the full task? |
| `multi_turn_tool_use_quality_v1` | Tool use quality across turns |

### Available Scenario Files

| File | Scenarios | Focus |
|------|-----------|-------|
| `coordinator_scenarios.json` | 8 | Multi-intent routing, booking flows |
| `travel_scenarios.json` | 8 | Search-to-book, comparison shopping |
| `expense_scenarios.json` | 8 | Policy check-to-submit, over-limit |
| `router_scenarios.json` | 10 | Low/medium/high complexity routing |

---

## 5. Online Monitors

Online monitors continuously evaluate agent responses using Cloud Trace telemetry on a 10-minute cycle. Results flow to BigQuery for trend analysis.

### Monitor Setup

```python
# src/eval/setup_online_monitors.py
metrics_to_create = [
    ("helpfulness", HELPFULNESS_METRIC),
    ("tool_use_accuracy", TOOL_USE_METRIC),
    ("policy_compliance", POLICY_COMPLIANCE_METRIC),
]

for metric_name, metric in metrics_to_create:
    monitor = client.evals.create_online_eval(
        agent=agent_resource_name,
        config={
            "metrics": [metric],
            "schedule": {"interval_minutes": 10},
            "sample_rate": 1.0,
        },
    )
```

### Monitor Verification

```bash
# Check monitor status and recent scores
uv run python -m src.eval.verify_monitors --format json

# View BigQuery results
bq query --use_legacy_sql=false \
  "SELECT metric_name, AVG(score) as avg_score, COUNT(*) as n
   FROM \`wortz-project-352116.geap_workshop_logs.online_eval_results\`
   WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
   GROUP BY metric_name"
```

### Quality Alerts

Cloud Monitoring alert policies fire when eval scores drop below thresholds:

```python
# src/eval/quality_alerts.py
ALL_MONITORED_METRICS = [
    ("helpfulness", 3.0),
    ("tool_use_accuracy", 3.0),
    ("policy_compliance", 3.0),
    ("complexity_routing_accuracy", 3.0),
]
```

---

## 6. CI/CD with GitHub Actions + Workload Identity Federation

### How Federated Auth Works

```
┌──────────────┐     ┌───────────────────┐     ┌─────────────────┐
│ GitHub Action │────►│ Workload Identity │────►│ Service Account │
│              │     │ Provider (WIF)     │     │                 │
│ id-token:    │     │                    │     │ Permissions:    │
│   write      │     │ Validates OIDC     │     │ - Agent Engine  │
│              │     │ token from GitHub  │     │ - Vertex AI     │
│              │     │ Maps to SA         │     │ - BigQuery      │
└──────────────┘     └───────────────────┘     └─────────────────┘
```

1. GitHub Actions requests an OIDC token (no stored secrets)
2. `google-github-actions/auth@v2` exchanges the OIDC token with GCP's Workload Identity Federation
3. WIF validates the token and returns short-lived credentials mapped to a service account
4. The workflow uses those credentials to call Vertex AI, Agent Engine, BigQuery, etc.

### Workflow: `.github/workflows/eval_pipeline.yaml`

```yaml
name: Comprehensive Eval Pipeline

on:
  pull_request:
    branches: [main]
    paths: ['src/agents/**', 'src/eval/**', 'src/router/**']
  workflow_dispatch:
    inputs:
      agent_id:
        description: 'Agent Engine ID'
        required: false

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --extra dev
      - run: uv run python -m pytest tests/test_multi_agent_eval.py -v

  batch-evals:
    needs: unit-tests
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write  # Required for WIF
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - uses: astral-sh/setup-uv@v4
      - run: uv sync

      # Federated auth — no secrets stored
      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ vars.WIF_PROVIDER }}
          service_account: ${{ vars.WIF_SERVICE_ACCOUNT }}

      - name: Run batch evaluations
        run: |
          uv run python -m src.eval.multi_agent_batch_eval \
            --threshold 3.0 --output eval_outputs/batch_results.json

      - uses: actions/upload-artifact@v4
        with:
          name: batch-eval-results
          path: eval_outputs/

  complexity-evals:
    needs: unit-tests
    runs-on: ubuntu-latest
    permissions: { contents: read, id-token: write }
    steps:
      # ... auth + run complexity accuracy + cost eval ...

  report:
    needs: [batch-evals, complexity-evals]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
      - name: Generate summary
        run: |
          echo "## Eval Pipeline Results" >> $GITHUB_STEP_SUMMARY
          # ... parse JSON artifacts, build markdown table ...
```

### Setting Up WIF

```bash
# 1. Create workload identity pool
gcloud iam workload-identity-pools create "github-pool" \
  --project=wortz-project-352116 \
  --location="global" \
  --display-name="GitHub Actions Pool"

# 2. Create OIDC provider
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project=wortz-project-352116 \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# 3. Allow the SA to be impersonated
gcloud iam service-accounts add-iam-policy-binding \
  "geap-ci@wortz-project-352116.iam.gserviceaccount.com" \
  --project=wortz-project-352116 \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/679926387543/locations/global/workloadIdentityPools/github-pool/attribute.repository/YOUR_ORG/geap-tour-26"

# 4. Set GitHub repo variables
#   WIF_PROVIDER: projects/679926387543/locations/global/workloadIdentityPools/github-pool/providers/github-provider
#   WIF_SERVICE_ACCOUNT: geap-ci@wortz-project-352116.iam.gserviceaccount.com
```

### Pipeline Flow

```
PR opened/updated
    │
    ▼
┌─────────────┐
│ Unit Tests  │  pytest tests/test_multi_agent_eval.py
└──────┬──────┘
       │ pass
       ▼
┌──────────────┐    ┌──────────────────┐
│ Batch Evals  │    │ Complexity Evals │   (parallel)
│              │    │                  │
│ 4 agents     │    │ accuracy + cost  │
│ 52 test cases│    │ 12 prompts       │
└──────┬───────┘    └────────┬─────────┘
       │                     │
       ▼                     ▼
┌──────────────────────────────────┐
│ Monitor Check                    │
│ Verify BQ has recent eval scores │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ Report                           │
│ $GITHUB_STEP_SUMMARY with tables │
│ + artifact upload                │
└──────────────────────────────────┘
```

---

## 7. Full Pipeline Orchestrator

Run everything with a single command:

```bash
# Full pipeline
uv run python -m src.eval.run_all_evals

# Skip traffic generation (faster, uses existing traces)
uv run python -m src.eval.run_all_evals --skip-traffic

# Batch evals only
uv run python -m src.eval.run_all_evals --batch-only

# Just check monitors
uv run python -m src.eval.run_all_evals --monitors-only
```

### Pipeline Phases

| Phase | Description | Duration |
|-------|-------------|----------|
| 1. Setup | Verify agent, check monitors | ~5s |
| 2. Traffic | Send 20 queries, wait for trace ingestion | ~2min |
| 3. Batch Evals | Run per-agent evaluations (4 agents, 52 cases) | ~5min |
| 4. Simulated | ADK user simulator for coordinator + travel | ~3min |
| 5. Complexity | Classifier accuracy + cost efficiency | ~30s |
| 6. Monitors | Verify BigQuery has online eval results | ~10s |

### Output

```
eval_outputs/run_20260512_015235/
  report.md                # Human-readable summary
  batch_results.json       # Per-agent metrics
  simulation_results.json  # User sim scores
  complexity_eval.json     # Accuracy + cost analysis
  monitor_status.json      # Online monitor health
  full_results.json        # Everything combined
```

---

## 8. Full Results Dashboard

![Full Evaluation Report](screenshots/eval_batch_results.png)

---

## Quick Reference

| Task | Command |
|------|---------|
| Run all evals | `uv run python -m src.eval.run_all_evals` |
| Batch eval (single agent) | `uv run python -m src.eval.multi_agent_batch_eval --agents travel_agent` |
| Complexity eval | `uv run python -c "..."` (see Section 2) |
| ADK static eval | `adk eval src/agents/coordinator --config_file_path src/eval/evalsets/eval_config.json coordinator_eval_set` |
| ADK user sim eval | `bash src/eval/run_user_sim.sh` |
| Generate traffic | `uv run python -m src.traffic.generate_traffic --count 2` |
| Check monitors | `uv run python -m src.eval.verify_monitors --format json` |
| Set up alerts | `uv run python -m src.eval.quality_alerts all` |
| Run unit tests | `uv run --extra dev python -m pytest tests/test_multi_agent_eval.py -v` |

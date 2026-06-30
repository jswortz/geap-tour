# Monitoring & Quality Alerts for Vertex AI Agent Engine

This guide walks you through setting up a complete observability and alerting pipeline for agents deployed on **Vertex AI Agent Engine (Reasoning Engine)**. It explains how to collect OpenTelemetry traces, evaluate agent runs using native **Online Evaluators**, sink traces/logs to **BigQuery**, bridge evaluation scores into **Cloud Monitoring**, and configure alerting thresholds to detect and report quality degradation.

> **Official docs:**
> - [Vertex AI Agent Engine (Reasoning Engine)](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview)
> - [Online Evaluation Monitors](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/evaluate#online-evaluation)
> - [Cloud Logging Sinks](https://cloud.google.com/logging/docs/export/configure_export_v2)
> - [BigQuery](https://cloud.google.com/bigquery/docs)
> - [Cloud Monitoring Custom Metrics](https://cloud.google.com/monitoring/custom-metrics)
> - [Cloud Monitoring Alert Policies](https://cloud.google.com/monitoring/alerts)

---

## 🏛️ Pipeline Architecture

![GCP Monitoring & Alerting Pipeline](./screenshots/session5_pipeline_architecture.jpg)

1. **Agent Engine Runtime** generates OpenTelemetry traces and logs during execution.
2. **Cloud Logging Sink** routes all logs and traces to a **BigQuery** dataset for historical analysis, querying, and custom dashboards.
3. **Online Evaluators** run in the background (every 10 minutes) to evaluate recently collected OTel traces using predefined metrics and custom rubrics.
4. The Online Evaluator writes evaluation scores back into **Cloud Logging** as structured payload entries.
5. A **Metric Publisher Bridge** extracts evaluation scores from Cloud Logging and publishes them to **Cloud Monitoring** as custom time series.
6. **Cloud Monitoring Alert Policies** monitor the custom metrics and trigger notifications if agent performance drops below a specified threshold.

---

## 🛠️ Step 1: Deploy Agents with OpenTelemetry Enabled

To enable OpenTelemetry tracing in your ADK agents, configure the Agent Engine deployment with the required environment variables (defined in [config.py:L33-37](file:///usr/local/google/home/jwortz/geap-tour/src/config.py#L33-L37) and used in [deploy_agents.py:L93-113](file:///usr/local/google/home/jwortz/geap-tour/src/deploy/deploy_agents.py#L93-L113)):

```python
# snippet from src/config.py
OTEL_ENV_VARS = {
    "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
    "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "EVENT_ONLY",
}

# snippet from src/deploy/deploy_agents.py
env_vars = {
    **OTEL_ENV_VARS,
    "PYTHONPATH": "/code/src",
    # ...
}

config = {
    "staging_bucket": f"gs://{GCP_STAGING_BUCKET}",
    "requirements": REQUIREMENTS,
    "display_name": display_name or agent.name,
    "env_vars": env_vars,
    "extra_packages": ["src"],
}

remote = client.agent_engines.create(agent=agent, config=config)
```

Traces and logs will automatically flow to Cloud Logging.

---

## 📥 Step 2: Sink Traces to BigQuery

To store logs and traces permanently in BigQuery, set up a **Logging Sink** pointing to a BigQuery dataset. You can automate this configuration using [setup_logging_sink.sh](file:///usr/local/google/home/jwortz/geap-tour/scripts/setup_logging_sink.sh):

1. Create a BigQuery dataset named `geap_workshop_logs`.
2. Create a Logging Sink targeting the dataset with the following filter:
   ```sql
   resource.type="cloud_run_revision" OR resource.type="aiplatform.googleapis.com/ReasoningEngine"
   ```
3. Verify that log tables are populated as requests hit your agents.

---

## 📊 Step 3: Register Online Evaluators

Online Evaluators perform automated, LLM-as-a-judge assessments on your agent's live traces. 

Create an Online Evaluator configuration (configured in [_build_evaluator_config](file:///usr/local/google/home/jwortz/geap-tour/src/eval/setup_online_evaluators.py#L215-L234) within [setup_online_evaluators.py](file:///usr/local/google/home/jwortz/geap-tour/src/eval/setup_online_evaluators.py)) specifying the target agent, predefined metrics, and your custom evaluation rubrics:

```python
# snippet from src/eval/setup_online_evaluators.py
def _build_evaluator_config(
    agent_label: str, engine_id: str, custom_metric_names: list[str]
) -> dict:
    metric_sources = [
        {"metric": {"predefinedMetricSpec": {"metricSpecName": m}}}
        for m in PREDEFINED_METRICS
    ]
    for name in custom_metric_names:
        metric_sources.append({"metricResourceName": name})

    return {
        "displayName": f"GEAP {agent_label.title()} Online Evaluator",
        "agentResource": _agent_resource(engine_id),
        "metricSources": metric_sources,
        "config": {"randomSampling": {"percentage": 100}},
        "cloudObservability": {
            "traceScope": {},
            "openTelemetry": {"semconvVersion": "1.39.0"},
        },
    }
```

Submit this configuration via the Vertex AI API to activate background evaluation (implemented in [create_evaluators](file:///usr/local/google/home/jwortz/geap-tour/src/eval/setup_online_evaluators.py#L266-L295)).

---

## 🎛️ Custom Metrics Creation & Registration

To evaluate domain-specific behaviors (such as governance policy compliance or task completion quality), you can define and register **Custom Evaluation Metrics** in the Vertex AI Metric Registry. These act as custom LLM-as-a-judge evaluators.

### 1. Structure of a Custom Metric
A custom metric configuration is defined as a JSON object containing a prompt template, scoring range, and scoring rubrics:

```json
{
  "displayName": "GEAP Task Quality",
  "metric": {
    "llmBasedMetricSpec": {
      "metricPromptTemplate": "Instructions, evaluation rubrics, score definitions (1 to 5), inputs: {prompt} and {response}, and output JSON format specification."
    },
    "metadata": {
      "title": "GEAP Task Quality",
      "scoreRange": {
        "min": 1.0,
        "max": 5.0
      }
    }
  }
}
```

*   **`metricPromptTemplate`**: The system prompt given to the LLM judge. It must define the role, the tools the agent has access to, the criteria for scoring, and the rating scores (e.g. 1-5). It must also specify that the output should be returned as a valid JSON object with `score` and `explanation` keys.
*   **`scoreRange`**: The bounds of the numeric score generated by the judge.

### 2. Registering via REST API
Custom metrics are registered via a `POST` request to the Vertex AI API endpoint:
`https://{GCP_REGION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_NUMBER}/locations/{GCP_REGION}/evaluationMetrics`

For an implementation of listing and registering custom metrics, see [setup_online_evaluators.py](file:///usr/local/google/home/jwortz/geap-tour/src/eval/setup_online_evaluators.py#L185-L212):

```python
# snippet from src/eval/setup_online_evaluators.py
def register_custom_metrics() -> list[str]:
    headers = _get_headers()
    # ... check for existing metrics ...
    for metric_def in CUSTOM_METRICS:
        resp = requests.post(
            f"{API_BASE}/evaluationMetrics",
            headers=headers,
            json=metric_def,
        )
        # returns URN format: projects/PROJECT_NUMBER/locations/REGION/evaluationMetrics/CUSTOM_METRIC_ID
```

Once registered, you can include the metric's resource name (URN) inside the Online Evaluator's `metricSources` list (as shown in Step 3).

---

## 🌉 Step 4: Publish Evaluation Metrics to Cloud Monitoring

Online evaluation results are written to Cloud Logging as structured logs. To query and plot these scores in Cloud Monitoring, we use a Metric Publisher Bridge (implemented in [publish_metrics.py](file:///usr/local/google/home/jwortz/geap-tour/src/eval/publish_metrics.py)):

1. Create a custom **Metric Descriptor** for each quality metric (implemented in [create_metric_descriptors](file:///usr/local/google/home/jwortz/geap-tour/src/eval/publish_metrics.py#L41-L82)):
   ```python
   # snippet from src/eval/publish_metrics.py
        descriptor = {
            "type": metric_type,
            "metric_kind": "GAUGE",
            "value_type": "DOUBLE",
            "description": f"GEAP Evaluator score for {internal_name}",
            "display_name": f"GEAP Agent Eval: {custom_name}",
            "labels": [
                {
                    "key": "agent",
                    "value_type": "STRING",
                    "description": "Agent Resource ID"
                }
            ]
        }
        client.create_metric_descriptor(name=project_name, metric_descriptor=descriptor)
   ```
2. Periodically query Cloud Logging for evaluation results (`labels."event.name"="gen_ai.evaluation.result"`) and write them to Cloud Monitoring using the TimeSeries API (implemented in [publish_metrics_to_monitoring](file:///usr/local/google/home/jwortz/geap-tour/src/eval/publish_metrics.py#L120-L188)).

---

## 📈 Step 5: View Metrics in Metrics Explorer & Dashboard

Once metrics are published, you can plot them in **Metrics Explorer** or view them consolidated in the custom dashboard.

### Metrics Explorer
- Navigate to **Monitoring > Metrics Explorer** in the Google Cloud Console.
- Search for the metric `custom.googleapis.com/agent_eval/helpfulness`.
- Group by the `agent` label to isolate individual agent scores.

The screenshot below shows a real-time visualization of a simulated drop in agent helpfulness quality:

![Metrics Explorer showing custom metric going out of spec](./screenshots/session5_metrics_explorer_out_of_spec.png)

### Custom Quality Dashboard
We have deployed a custom Cloud Monitoring dashboard named **"GEAP Agent Performance & Quality Dashboard"** (configured via [dashboard.json](file:///usr/local/google/home/jwortz/geap-tour/scratch/dashboard.json) and deployed with ID `d29ccca2-75be-439b-bfe8-81bf7df8f129`) which aggregates and visualizes all 7 custom metrics in real-time charts:
- **GEAP Agent Task Quality & Policy Compliance** (aggregating Task Quality and Compliance metrics)
- **Helpfulness & Groundedness** (aggregating helpfulness and groundedness scores)
- **Safety & Tool Use Accuracy** (aggregating safety and accuracy metrics)
- **Complexity Routing Accuracy** (aggregating routing classification metric)

To view it:
1. Go to **Monitoring > Dashboards** in the Cloud Console.
2. Select **"GEAP Agent Performance & Quality Dashboard"** from the dashboards list.

---

## 🚨 Step 6: Configure Quality Alert Policies

To get notified when agent performance drops (e.g. below a score of `3.0` for 10 minutes), create a Cloud Monitoring Alert Policy (implemented in [create_quality_alert](file:///usr/local/google/home/jwortz/geap-tour/src/eval/quality_alerts.py#L9-L53) within [quality_alerts.py](file:///usr/local/google/home/jwortz/geap-tour/src/eval/quality_alerts.py)):

```python
# snippet from src/eval/quality_alerts.py
    condition = monitoring_v3.AlertPolicy.Condition(
        display_name=f"Agent {metric_name} score below {threshold}",
        condition_threshold=monitoring_v3.AlertPolicy.Condition.MetricThreshold(
            filter=f'metric.type="custom.googleapis.com/agent_eval/{metric_name}" AND resource.type="global"',
            comparison=monitoring_v3.ComparisonType.COMPARISON_LT,
            threshold_value=threshold,
            duration=duration_pb2.Duration(seconds=600),
            aggregations=[
                monitoring_v3.Aggregation(
                    alignment_period=duration_pb2.Duration(seconds=600),
                    per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_MEAN,
                )
            ],
        ),
    )

    policy = monitoring_v3.AlertPolicy(
        display_name=f"GEAP Workshop: {metric_name} quality alert",
        # ...
        conditions=[condition],
        combiner=monitoring_v3.AlertPolicy.ConditionCombinerType.OR,
        notification_channels=channels,
        enabled=True,
    )
```

If the helpfulness metric remains below `3.0` for 10 consecutive minutes, an incident is created and notifications are dispatched.

Here is the **Alerting Policies** dashboard showing an active quality alert in the **FIRING** state:

![Alert Dashboard showing helpfulness alert firing](./screenshots/session5_monitoring_alert_firing.png)

When an alert fires, a notification is automatically dispatched to the configured notification channels (e.g., via email):

![Email notification showing quality alert details](./screenshots/session5_email_alert.png)

---

## 🏁 Summary of Resources Set Up

- **Logging Sink**: `geap-agent-traces` -> BQ Dataset `geap_workshop_logs` (provisioned via [setup_logging_sink.sh](file:///usr/local/google/home/jwortz/geap-tour/scripts/setup_logging_sink.sh))
- **Online Evaluators**:
  - `GEAP Coordinator Online Evaluator` targeting agent `3532905132637290496` (resolved via Agent Registry URN `urn:endpoint:projects-679926387543:projects:679926387543:locations:global:agentregistry:services:coordinator-agent`)
  - `GEAP Router Online Evaluator` targeting agent `5972730230765256704` (resolved via Agent Registry URN `urn:endpoint:projects-679926387543:projects:679926387543:locations:global:agentregistry:services:router-agent`)

- **Cloud Monitoring Alert Policies**:
  - `GEAP Workshop: helpfulness quality alert` (Threshold < 3.0)
  - `GEAP Workshop: tool_use_accuracy quality alert` (Threshold < 3.0)
  - `GEAP Workshop: policy_compliance quality alert` (Threshold < 3.0)
  - `GEAP Workshop: complexity_routing_accuracy quality alert` (Threshold < 3.0)

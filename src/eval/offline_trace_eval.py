"""Offline (retroactive) evaluation over historical GEAP Traces and Sessions.

WHAT "OFFLINE" MEANS HERE
-------------------------
Offline evaluation scores agent executions that were **already recorded** —
historical Traces and Sessions — retroactively. It does NOT run new inference.
Contrast this with ``src/eval/batch_eval.py`` and ``setup_online_monitors.py``,
which call ``client.evals.run_inference(...)`` to generate *fresh* responses
before scoring. Here we take the prompt/response pairs that already happened in
production and re-score them with the same rubric metrics. This closes the
"evaluate over historical traces/sessions" gap described in Google's docs:
https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/evaluate-offline

TRACE vs SESSION
----------------
- A **Trace** is one execution path: the model inputs, model responses, and any
  tool calls made while handling a single request.
- A **Session** is the full multi-turn conversation (many traces sharing a
  conversation id).

TELEMETRY THIS READS
--------------------
GEAP emits OpenTelemetry gen_ai spans/events. The historical records we score
come from those. Relevant span attributes:
  - ``gen_ai.agent.name`` / ``gen_ai.agent.description`` — which agent ran.
  - ``gen_ai.conversation.id`` — groups traces into a session.
And the inference event ``gen_ai.client.inference.operation.details`` carries:
  - ``gen_ai.input.messages``      — the model inputs (becomes ``prompt``).
  - ``gen_ai.output.messages``     — the model responses (becomes ``response``).
  - ``gen_ai.system_instructions`` — the system prompt in effect.
  - ``gen_ai.tool.definitions``    — the tools available to the agent.
These flow to BigQuery (``geap_workshop_logs``) via the logging sink; see
``docs/monitoring_integration_guide.md``.

CONSOLE EQUIVALENT
------------------
The same thing is available in the UI under:
  Agent Platform > Agents > Evaluation > New evaluation > Traces/Sessions tab
which runs the offline evaluation and writes the results to a Cloud Storage
bucket.

Usage:
    python -m src.eval.offline_trace_eval [agent_name]
    python -m src.eval.offline_trace_eval expense_agent
"""

import json
import os
import sys
from datetime import datetime

from src.config import (
    AGENT_ENGINE_ID,
    BQ_EVAL_DATASET,
    GCP_PROJECT_ID,
    GCP_REGION,
    GCP_STAGING_BUCKET,
)
from src.eval.agent_eval_configs import get_metrics

# Bundled fixture used when BigQuery is empty/unreachable, so demos and
# screenshots always produce output.
_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "sample_traces.jsonl")


def _resolve_agent_resource_name(agent_id: str) -> str:
    """Expand a bare reasoning-engine id into a full resource name.

    Mirrors the convention used across the repo (see setup_online_monitors.py).
    """
    if agent_id.startswith("projects/"):
        return agent_id
    return f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/reasoningEngines/{agent_id}"


# ---------------------------------------------------------------------------
# Loading historical records
# ---------------------------------------------------------------------------
def _extract_text(messages_json: str | None) -> str:
    """Pull plain text out of a gen_ai messages JSON blob.

    ``gen_ai.input.messages`` / ``gen_ai.output.messages`` are JSON arrays of
    ``{"role": ..., "parts": [{"content": ...} | {"text": ...}]}``. We flatten
    the text content so it can be scored as a single prompt/response string.
    """
    if not messages_json:
        return ""
    try:
        messages = json.loads(messages_json)
    except (TypeError, ValueError):
        return str(messages_json)
    if isinstance(messages, dict):
        messages = [messages]
    chunks: list[str] = []
    for msg in messages or []:
        if isinstance(msg, str):
            chunks.append(msg)
            continue
        parts = msg.get("parts") or msg.get("content") or []
        if isinstance(parts, str):
            chunks.append(parts)
            continue
        for part in parts if isinstance(parts, list) else [parts]:
            if isinstance(part, str):
                chunks.append(part)
            elif isinstance(part, dict):
                chunks.append(str(part.get("text") or part.get("content") or ""))
    return "\n".join(c for c in chunks if c).strip()


def _query_bigquery_traces(hours_back: int, limit: int) -> list[dict]:
    """Query the BigQuery logging-sink dataset for recent gen_ai inference rows.

    Returns records shaped like the fixture. Raises on any error so the caller
    can fall back to the bundled fixture.
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=GCP_PROJECT_ID)

    # The logging sink lands one table per resource type; a wildcard scan keeps
    # this robust to the exact table name. We select rows carrying the gen_ai
    # inference event, which holds the input/output messages we score offline.
    query = f"""
    SELECT
        timestamp,
        JSON_VALUE(json_payload, '$."gen_ai.conversation.id"')      AS conversation_id,
        JSON_VALUE(json_payload, '$."gen_ai.agent.name"')           AS agent_name,
        JSON_VALUE(json_payload, '$."gen_ai.input.messages"')       AS input_messages,
        JSON_VALUE(json_payload, '$."gen_ai.output.messages"')      AS output_messages,
        JSON_VALUE(json_payload, '$."gen_ai.tool.definitions"')     AS tool_definitions
    FROM `{GCP_PROJECT_ID}.{BQ_EVAL_DATASET}.*`
    WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(hours_back)} HOUR)
      AND JSON_VALUE(json_payload, '$."event.name"')
          = 'gen_ai.client.inference.operation.details'
      AND JSON_VALUE(json_payload, '$."gen_ai.output.messages"') IS NOT NULL
    ORDER BY timestamp DESC
    LIMIT {int(limit)}
    """

    rows = list(client.query(query).result())
    records: list[dict] = []
    for row in rows:
        prompt = _extract_text(row.input_messages)
        response = _extract_text(row.output_messages)
        if not prompt or not response:
            continue
        records.append(
            {
                "conversation_id": row.conversation_id or "",
                "agent_name": row.agent_name or "",
                "prompt": prompt,
                "response": response,
                "tool_calls": [],
            }
        )
    return records


def _load_fixture_traces(limit: int) -> list[dict]:
    """Load the bundled JSONL fixture of historical traces."""
    records: list[dict] = []
    with open(_FIXTURE_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records[:limit]


def _load_historical_with_source(hours_back: int, limit: int) -> tuple[list[dict], str]:
    """Load historical records, returning ``(records, source)``.

    Strategy, in order:
      (a) BigQuery scan of ``{GCP_PROJECT_ID}.{BQ_EVAL_DATASET}`` for recent
          gen_ai input/output messages.
      (b) Bundled fixture ``sample_traces.jsonl`` if BigQuery is empty or errors.
    All cloud calls are wrapped in try/except and fall back to the fixture.
    """
    try:
        records = _query_bigquery_traces(hours_back, limit)
        if records:
            print(
                f"  Source: BigQuery {GCP_PROJECT_ID}.{BQ_EVAL_DATASET} "
                f"({len(records)} historical traces, last {hours_back}h)"
            )
            return records, "bigquery"
        print(
            f"  BigQuery {GCP_PROJECT_ID}.{BQ_EVAL_DATASET} returned no gen_ai "
            "traces; falling back to bundled fixture."
        )
    except Exception as e:  # noqa: BLE001 - degrade gracefully offline
        print(f"  BigQuery unavailable ({e}); falling back to bundled fixture.")

    records = _load_fixture_traces(limit)
    print(f"  Source: fixture {_FIXTURE_PATH} ({len(records)} traces)")
    return records, "fixture"


def load_historical_traces(hours_back: int = 24, limit: int = 50) -> list[dict]:
    """Load already-recorded historical gen_ai records for offline scoring.

    Tries BigQuery first, then falls back to the bundled fixture. Each returned
    dict has at least ``prompt`` and ``response`` and, when available,
    ``tool_calls``, ``conversation_id`` and ``agent_name``. No inference is run.
    """
    records, _ = _load_historical_with_source(hours_back, limit)
    return records


# ---------------------------------------------------------------------------
# Building the evaluation dataset
# ---------------------------------------------------------------------------
def build_offline_dataset(records: list[dict]):
    """Build a pandas DataFrame the evaluate API can score without inference.

    Columns: ``prompt``, ``response`` (bring-your-own-response, so no new
    inference) and ``session_inputs`` — a ``types.evals.SessionInput`` per row,
    keyed on the conversation id, matching the pattern used across the eval modules.
    """
    import pandas as pd
    from vertexai import types

    rows = []
    for i, rec in enumerate(records):
        user_id = rec.get("conversation_id") or f"offline-trace-{i:04d}"
        rows.append(
            {
                "prompt": rec.get("prompt", ""),
                "response": rec.get("response", ""),
                "session_inputs": types.evals.SessionInput(user_id=user_id),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Offline evaluation
# ---------------------------------------------------------------------------
def evaluate_from_traces(
    client=None,
    agent_name: str = "coordinator_agent",
    hours_back: int = 24,
    limit: int = 50,
    score_threshold: float = 3.0,
) -> dict:
    """Score historical traces offline and return a JSON-serializable summary.

    Loads already-recorded records, builds a response-based dataset (no new
    inference), and evaluates it with ``get_metrics(agent_name,
    include_custom=False)``. Prints a per-metric PASS/FAIL summary at
    ``score_threshold`` and returns the summary. The evaluate call is wrapped so
    it degrades gracefully offline.
    """
    print(f"Offline trace evaluation ({agent_name})")
    print(f"  Agent resource: {_resolve_agent_resource_name(AGENT_ENGINE_ID)}")

    records, source = _load_historical_with_source(hours_back, limit)
    if not records:
        return {
            "status": "skipped",
            "reason": "no historical records available",
            "source": source,
            "agent_name": agent_name,
            "record_count": 0,
        }

    df = build_offline_dataset(records)
    metrics = get_metrics(agent_name, include_custom=False)
    print(f"  Scoring {len(df)} historical traces with {len(metrics)} metrics...")

    if client is None:
        try:
            import vertexai
            from vertexai import Client

            vertexai.init(
                project=GCP_PROJECT_ID,
                location=GCP_REGION,
                staging_bucket=f"gs://{GCP_STAGING_BUCKET}",
            )
            client = Client(project=GCP_PROJECT_ID, location=GCP_REGION)
        except Exception as e:  # noqa: BLE001
            return {
                "status": "skipped",
                "reason": f"could not initialize Vertex AI client: {e}",
                "source": source,
                "agent_name": agent_name,
                "record_count": len(records),
            }

    try:
        eval_result = client.evals.evaluate(dataset=df, metrics=metrics)
    except Exception as e:  # noqa: BLE001 - degrade gracefully offline
        print(f"  Evaluation skipped: {e}")
        return {
            "status": "skipped",
            "reason": str(e),
            "source": source,
            "agent_name": agent_name,
            "record_count": len(records),
        }

    metrics_summary: dict = {}
    print("\n  Per-metric results:")
    for result in getattr(eval_result, "summary_metrics", None) or []:
        mean = getattr(result, "mean_score", None)
        name = str(getattr(result, "metric_name", "unknown"))
        # The eval service returns rubric scores on a 0-1 scale; the repo scores
        # on a 1-5 scale (pass >= 3.0), rescaling 0-1 values ×5. Mirror the
        # convention in multi_agent_batch_eval.py so PASS/FAIL is consistent.
        scaled = mean * 5.0 if (mean is not None and mean <= 1.0) else mean
        passed = scaled is not None and scaled >= score_threshold
        status = "PASS" if passed else "FAIL"
        mean_str = f"{scaled:.2f}" if scaled is not None else "N/A"
        total = getattr(result, "num_cases_total", None)
        errors = getattr(result, "num_cases_error", None)
        print(
            f"    [{status}] {name}: score={mean_str}/5 "
            f"(raw={mean if mean is None else round(mean, 3)}, "
            f"total={total}, errors={errors}, threshold={score_threshold})"
        )
        metrics_summary[name] = {
            "raw_mean": mean,
            "score": scaled,
            "num_cases_total": total,
            "num_cases_error": errors,
            "status": status,
        }

    return {
        "status": "ok",
        "source": source,
        "agent_name": agent_name,
        "hours_back": hours_back,
        "record_count": len(records),
        "score_threshold": score_threshold,
        "timestamp": datetime.now().isoformat(),
        "metrics": metrics_summary,
    }


if __name__ == "__main__":
    agent = sys.argv[1] if len(sys.argv) > 1 else "coordinator_agent"
    summary = evaluate_from_traces(agent_name=agent)
    print("\n=== Offline Evaluation Summary ===")
    print(json.dumps(summary, indent=2, default=str))

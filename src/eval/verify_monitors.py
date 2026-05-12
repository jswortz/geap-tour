"""Verify online monitor results by querying BigQuery — with rich output and JSON mode."""

import json
import sys

from google.cloud import bigquery

from src.config import GCP_PROJECT_ID, BQ_EVAL_DATASET


def _check_table_exists(client: bigquery.Client) -> bool:
    table_ref = f"{GCP_PROJECT_ID}.{BQ_EVAL_DATASET}.online_eval_results"
    try:
        client.get_table(table_ref)
        return True
    except Exception:
        return False


def verify_monitor_results(output_format: str = "text") -> dict | None:
    """Query BigQuery for online evaluation results.

    Args:
        output_format: "text" for human-readable, "json" for structured output.

    Returns:
        dict with results when format is "json", None otherwise.
    """
    client = bigquery.Client(project=GCP_PROJECT_ID)

    if not _check_table_exists(client):
        msg = (
            f"Table {GCP_PROJECT_ID}.{BQ_EVAL_DATASET}.online_eval_results does not exist.\n"
            "  1. Set up monitors: uv run python -m src.eval.setup_online_monitors <agent>\n"
            "  2. Generate traffic: uv run python -m src.traffic.generate_traffic\n"
            "  3. Wait 10 minutes for the first monitor cycle to complete."
        )
        if output_format == "json":
            return {"status": "no_table", "message": msg}
        print(msg)
        return None

    query = f"""
    WITH scores AS (
        SELECT
            metric_name,
            score,
            timestamp,
            TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), timestamp, HOUR) as hours_ago
        FROM `{GCP_PROJECT_ID}.{BQ_EVAL_DATASET}.online_eval_results`
        WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    )
    SELECT
        metric_name,
        COUNT(*) as eval_count,
        ROUND(AVG(score), 3) as avg_score,
        ROUND(MIN(score), 3) as min_score,
        ROUND(MAX(score), 3) as max_score,
        ROUND(APPROX_QUANTILES(score, 100)[OFFSET(50)], 3) as p50_score,
        ROUND(APPROX_QUANTILES(score, 100)[OFFSET(90)], 3) as p90_score,
        COUNTIF(score < 3.0) as below_threshold,
        MIN(timestamp) as first_eval,
        MAX(timestamp) as last_eval,
        -- Trend: last 1h vs last 6h
        ROUND(AVG(IF(hours_ago <= 1, score, NULL)), 3) as avg_1h,
        ROUND(AVG(IF(hours_ago <= 6, score, NULL)), 3) as avg_6h,
        ROUND(AVG(score), 3) as avg_24h
    FROM scores
    GROUP BY metric_name
    ORDER BY metric_name
    """

    try:
        results = client.query(query).result()
        rows = list(results)
    except Exception as e:
        if output_format == "json":
            return {"status": "error", "error": str(e)}
        print(f"  Query failed: {e}")
        return None

    if not rows:
        msg = "No evaluation results in the last 24 hours. Monitors may still be initializing."
        if output_format == "json":
            return {"status": "empty", "message": msg}
        print(msg)
        return None

    data = {
        "status": "ok",
        "metrics": {},
        "total_evals": sum(row.eval_count for row in rows),
    }

    for row in rows:
        data["metrics"][row.metric_name] = {
            "eval_count": row.eval_count,
            "avg_score": row.avg_score,
            "min_score": row.min_score,
            "max_score": row.max_score,
            "p50_score": row.p50_score,
            "p90_score": row.p90_score,
            "below_threshold": row.below_threshold,
            "first_eval": str(row.first_eval),
            "last_eval": str(row.last_eval),
            "trend": {
                "avg_1h": row.avg_1h,
                "avg_6h": row.avg_6h,
                "avg_24h": row.avg_24h,
            },
        }

    if output_format == "json":
        return data

    # Print human-readable report
    print("=" * 60)
    print("ONLINE MONITOR RESULTS (last 24h)")
    print("=" * 60)
    print(f"  Total evaluations: {data['total_evals']}")
    print()

    for metric_name, m in data["metrics"].items():
        print(f"  {metric_name}:")
        print(f"    Evals:  {m['eval_count']}")
        print(f"    Avg:    {m['avg_score']}  (min: {m['min_score']}, max: {m['max_score']})")
        print(f"    P50:    {m['p50_score']}  P90: {m['p90_score']}")
        trend = m["trend"]
        parts = []
        if trend["avg_1h"] is not None:
            parts.append(f"1h: {trend['avg_1h']}")
        if trend["avg_6h"] is not None:
            parts.append(f"6h: {trend['avg_6h']}")
        parts.append(f"24h: {trend['avg_24h']}")
        print(f"    Trend:  {' | '.join(parts)}")
        if m["below_threshold"]:
            print(f"    WARNING: {m['below_threshold']} scores below 3.0 threshold")
        print()

    print("=" * 60)
    return data


def generate_markdown_report(data: dict) -> str:
    """Generate a markdown summary report from verify results."""
    if data.get("status") != "ok":
        return f"## Monitor Status\n\n{data.get('message', data.get('error', 'Unknown'))}\n"

    lines = [
        "## Online Monitor Health Report",
        "",
        f"**Total evaluations (24h):** {data['total_evals']}",
        "",
        "| Metric | Evals | Avg | P50 | P90 | Below 3.0 | 1h Trend |",
        "|--------|-------|-----|-----|-----|-----------|----------|",
    ]
    for name, m in data["metrics"].items():
        trend_1h = f"{m['trend']['avg_1h']}" if m["trend"]["avg_1h"] is not None else "N/A"
        lines.append(
            f"| {name} | {m['eval_count']} | {m['avg_score']} | "
            f"{m['p50_score']} | {m['p90_score']} | {m['below_threshold']} | {trend_1h} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    fmt = "text"
    if "--format" in sys.argv:
        idx = sys.argv.index("--format")
        if idx + 1 < len(sys.argv):
            fmt = sys.argv[idx + 1]

    result = verify_monitor_results(output_format=fmt)
    if fmt == "json" and result:
        print(json.dumps(result, indent=2, default=str))

"""Verify online monitor results by querying BigQuery."""

from google.cloud import bigquery

from src.config import GCP_PROJECT_ID

DATASET = "geap_workshop_logs"


def verify_monitor_results():
    """Query BigQuery for recent online evaluation results."""
    client = bigquery.Client(project=GCP_PROJECT_ID)

    query = f"""
    SELECT
        metric_name,
        AVG(score) as avg_score,
        COUNT(*) as eval_count,
        MIN(timestamp) as first_eval,
        MAX(timestamp) as last_eval
    FROM `{GCP_PROJECT_ID}.{DATASET}.online_eval_results`
    WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    GROUP BY metric_name
    ORDER BY metric_name
    """

    print("=== Online Monitor Results (last 24h) ===\n")
    try:
        results = client.query(query).result()
        for row in results:
            print(f"  {row.metric_name}:")
            print(f"    Avg Score: {row.avg_score:.2f}")
            print(f"    Eval Count: {row.eval_count}")
            print(f"    Time Range: {row.first_eval} → {row.last_eval}")
            print()
    except Exception as e:
        print(f"  Query failed (table may not exist yet): {e}")
        print("  → Generate traffic first, then wait for monitors to run (10 min cycle)")


if __name__ == "__main__":
    verify_monitor_results()

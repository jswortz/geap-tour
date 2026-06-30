import time
import datetime
from google.cloud import monitoring_v3
from src.config import GCP_PROJECT_ID

def read_metrics():
    client = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{GCP_PROJECT_ID}"
    
    metrics = [
        "custom.googleapis.com/agent_eval/policy_compliance",
        "custom.googleapis.com/agent_eval/geap_task_quality",
    ]
    
    now = time.time()
    # Query last 1 hour
    interval = monitoring_v3.TimeInterval(
        start_time={"seconds": int(now - 3600), "nanos": 0},
        end_time={"seconds": int(now), "nanos": 0}
    )
    
    for metric_type in metrics:
        print(f"\nQuerying: {metric_type}...")
        try:
            results = client.list_time_series(
                name=project_name,
                filter=f'metric.type = "{metric_type}"',
                interval=interval,
                view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL
            )
            count = 0
            for series in results:
                for point in series.points:
                    count += 1
                    print(f"  Time: {point.interval.end_time} | Value: {point.value.double_value}")
            print(f"  Total points found: {count}")
        except Exception as e:
            print(f"  Error querying metric: {e}")

if __name__ == "__main__":
    read_metrics()

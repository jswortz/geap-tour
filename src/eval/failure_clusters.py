"""Failure cluster analysis — group failure patterns from evaluation results."""

from google import genai

from src.config import GCP_PROJECT_ID, GCP_REGION


def analyze_failure_clusters(eval_result_name: str):
    """Run failure cluster analysis on evaluation results.

    Groups similar failures together to identify systemic issues rather than
    reviewing individual failures one by one.
    """
    client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )

    print(f"Analyzing failure clusters for {eval_result_name}...")

    clusters = client.evals.generate_loss_clusters(
        src=eval_result_name,
    )

    print(f"\n=== Failure Cluster Report ===")
    print(f"Total clusters: {len(clusters)}\n")

    for i, cluster in enumerate(clusters, 1):
        print(f"Cluster {i}: {cluster.title}")
        print(f"  Description: {cluster.description}")
        print(f"  Sample count: {cluster.sample_count}")
        print(f"  Avg score: {cluster.avg_score:.2f}")
        if cluster.examples:
            print(f"  Example: {cluster.examples[0][:100]}...")
        print()

    return clusters


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.failure_clusters <eval-result-name>")
        sys.exit(1)
    analyze_failure_clusters(sys.argv[1])

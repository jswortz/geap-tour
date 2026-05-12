import os
from dotenv import load_dotenv

load_dotenv()

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "wortz-project-352116")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")
GCP_STAGING_BUCKET = os.environ.get("GCP_STAGING_BUCKET", f"{GCP_PROJECT_ID}-geap-staging")
AGENT_GATEWAY_PATH = os.environ.get("AGENT_GATEWAY_PATH", "")
AGENT_GATEWAY_EGRESS_PATH = os.environ.get("AGENT_GATEWAY_EGRESS_PATH", "")

SEARCH_MCP_URL = os.environ.get("SEARCH_MCP_URL", "http://localhost:8001/mcp")
BOOKING_MCP_URL = os.environ.get("BOOKING_MCP_URL", "http://localhost:8002/mcp")
EXPENSE_MCP_URL = os.environ.get("EXPENSE_MCP_URL", "http://localhost:8003/mcp")

# Agent Registry — MCP server resource names (global location)
AGENT_REGISTRY_LOCATION = os.environ.get("AGENT_REGISTRY_LOCATION", "global")
SEARCH_MCP_SERVER = os.environ.get(
    "SEARCH_MCP_SERVER",
    f"projects/{GCP_PROJECT_ID}/locations/global/mcpServers/agentregistry-00000000-0000-0000-0c51-2a7dc998220b",
)
BOOKING_MCP_SERVER = os.environ.get(
    "BOOKING_MCP_SERVER",
    f"projects/{GCP_PROJECT_ID}/locations/global/mcpServers/agentregistry-00000000-0000-0000-a5e6-d1cf2bb18c63",
)
EXPENSE_MCP_SERVER = os.environ.get(
    "EXPENSE_MCP_SERVER",
    f"projects/{GCP_PROJECT_ID}/locations/global/mcpServers/agentregistry-00000000-0000-0000-02e2-cd6d7450ab52",
)

OTEL_ENV_VARS = {
    "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "EVENT_ONLY",
}

AGENT_MODEL = "gemini-2.0-flash"

# Multi-model router
LITE_MODEL = os.environ.get("LITE_MODEL", "gemini-2.0-flash-lite")
FLASH_MODEL = os.environ.get("FLASH_MODEL", "gemini-2.5-flash")
OPUS_MODEL = os.environ.get("OPUS_MODEL", "vertex_ai/claude-opus-4-7")
COMPLEXITY_THRESHOLD_HIGH = float(os.environ.get("COMPLEXITY_THRESHOLD_HIGH", "0.65"))
CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL", "gemini-2.0-flash-lite")

# Evaluation
EVAL_OUTPUT_DIR = os.environ.get("EVAL_OUTPUT_DIR", "eval_outputs")
BQ_EVAL_DATASET = os.environ.get("BQ_EVAL_DATASET", "geap_workshop_logs")
AGENT_ENGINE_ID = os.environ.get("AGENT_ENGINE_ID", "1316648131831529472")
ROUTER_ENGINE_ID = os.environ.get("ROUTER_ENGINE_ID", "6023683798619652096")

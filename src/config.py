"""Global configuration — GCP project settings, MCP server URLs, model configs, and eval params."""

import os
from dotenv import load_dotenv

load_dotenv()

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "wortz-project-352116")
PROJECT_NUMBER = os.environ.get("PROJECT_NUMBER", "")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")
GCP_STAGING_BUCKET = os.environ.get("GCP_STAGING_BUCKET", f"{GCP_PROJECT_ID}-geap-staging")
AGENT_GATEWAY_PATH = os.environ.get("AGENT_GATEWAY_PATH", "")
AGENT_GATEWAY_EGRESS_PATH = os.environ.get("AGENT_GATEWAY_EGRESS_PATH", "")

SEARCH_MCP_URL = os.environ.get("SEARCH_MCP_URL", "http://localhost:8001/mcp")
BOOKING_MCP_URL = os.environ.get("BOOKING_MCP_URL", "http://localhost:8002/mcp")
EXPENSE_MCP_URL = os.environ.get("EXPENSE_MCP_URL", "http://localhost:8003/mcp")

# Agent Registry — MCP server resource names (global location)
AGENT_REGISTRY_LOCATION = os.environ.get("AGENT_REGISTRY_LOCATION", "us-central1")
SEARCH_MCP_SERVER = os.environ["SEARCH_MCP_SERVER"]
BOOKING_MCP_SERVER = os.environ["BOOKING_MCP_SERVER"]
EXPENSE_MCP_SERVER = os.environ["EXPENSE_MCP_SERVER"]

# Fallback: map Agent Registry server names → Cloud Run URLs
MCP_SERVER_URLS = {
    SEARCH_MCP_SERVER: SEARCH_MCP_URL,
    BOOKING_MCP_SERVER: BOOKING_MCP_URL,
    EXPENSE_MCP_SERVER: EXPENSE_MCP_URL,
}

OTEL_ENV_VARS = {
    "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "EVENT_ONLY",
}

AGENT_MODEL = "gemini-2.5-flash"

# Multi-model router
LITE_MODEL = os.environ.get("LITE_MODEL", "gemini-2.5-flash-lite")
FLASH_MODEL = os.environ.get("FLASH_MODEL", "gemini-2.5-flash")
OPUS_MODEL = os.environ.get("OPUS_MODEL", "claude-opus-4-6")
COMPLEXITY_THRESHOLD_HIGH = float(os.environ.get("COMPLEXITY_THRESHOLD_HIGH", "0.65"))
CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL", "gemini-2.5-flash-lite")

# Evaluation
EVAL_OUTPUT_DIR = os.environ.get("EVAL_OUTPUT_DIR", "eval_outputs")
BQ_EVAL_DATASET = os.environ.get("BQ_EVAL_DATASET", "geap_workshop_logs")
AGENT_ENGINE_ID = os.environ.get("AGENT_ENGINE_ID", "2479350891879071744")
ROUTER_ENGINE_ID = os.environ.get("ROUTER_ENGINE_ID", "6023683798619652096")

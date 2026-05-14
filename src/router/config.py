"""Router-local configuration — self-contained for Agent Runtime deployment."""

import os
from dotenv import load_dotenv

load_dotenv()

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "wortz-project-352116")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")

SEARCH_MCP_URL = os.environ.get("SEARCH_MCP_URL", "http://localhost:8001/mcp")
BOOKING_MCP_URL = os.environ.get("BOOKING_MCP_URL", "http://localhost:8002/mcp")
EXPENSE_MCP_URL = os.environ.get("EXPENSE_MCP_URL", "http://localhost:8003/mcp")

LITE_MODEL = os.environ.get("LITE_MODEL", "gemini-2.5-flash-lite")
FLASH_MODEL = os.environ.get("FLASH_MODEL", "gemini-2.5-flash")
PRO_MODEL = os.environ.get("PRO_MODEL", "gemini-2.5-pro")
SONNET_MODEL = os.environ.get("SONNET_MODEL", "claude-sonnet-4-6")
OPUS_MODEL = os.environ.get("OPUS_MODEL", "claude-opus-4-6")
COMPLEXITY_THRESHOLD_HIGH = float(os.environ.get("COMPLEXITY_THRESHOLD_HIGH", "0.65"))
CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL", "gemini-2.5-flash-lite")

"""Shared authentication utilities for MCP server connections.

Uses static headers dict (not callable) to satisfy Agent Runtime picklability constraint.
"""

import google.auth
import google.auth.transport.requests


def get_auth_headers() -> dict[str, str]:
    """Get a static Authorization headers dict with a fresh access token."""
    credentials, _ = google.auth.default()
    credentials.refresh(google.auth.transport.requests.Request())
    return {"Authorization": f"Bearer {credentials.token}"}

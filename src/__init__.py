"""GEAP Workshop — src package.

Patches resource_manager_utils.get_project_id to handle ServiceUnavailable,
which occurs when Agent Gateway routes gRPC traffic through an MCP-only egress.
"""

def _patch_get_project_id():
    try:
        from google.cloud.aiplatform.utils import resource_manager_utils

        _original = resource_manager_utils.get_project_id

        def _patched(project_number, credentials=None):
            try:
                return _original(project_number, credentials=credentials)
            except Exception:
                return str(project_number)

        resource_manager_utils.get_project_id = _patched
    except ImportError:
        pass

_patch_get_project_id()

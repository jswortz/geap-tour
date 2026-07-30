"""Tests for the pure deploy-config builders in ``src/deploy``.

These are dict-building functions with no network calls, so they're cheap to test and
they guard against import/shape regressions (e.g. the ``deploy_all.py`` broken import).
"""

import importlib
from types import SimpleNamespace


def test_deploy_all_imports_cleanly():
    """deploy_all.py must import the real deploy API (regression: it imported a
    non-existent ``deploy_all_agents`` and raised ImportError)."""
    m = importlib.import_module("src.deploy.deploy_all")
    assert callable(m.main)
    assert callable(m.run_deploy)  # the real API it now delegates to


def test_build_config_core_keys():
    from src.deploy import deploy_agents

    cfg = deploy_agents._build_config(SimpleNamespace(name="coordinator_agent"))
    assert cfg["extra_packages"] == ["src"]
    assert cfg["display_name"] == "coordinator_agent"
    assert cfg["labels"] == {"app": "geap-workshop", "component": "agent"}
    assert cfg["staging_bucket"].startswith("gs://")

    env = cfg["env_vars"]
    assert env["GCP_PROJECT_ID"] and env["GCP_REGION"]
    assert env["GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY"] == "true"
    # all five router tiers are wired into the deployed env
    for key in ("LITE_MODEL", "FLASH_MODEL", "PRO_MODEL", "SONNET_MODEL", "OPUS_MODEL"):
        assert key in env, f"{key} missing from deploy env_vars"


def test_build_config_display_name_override():
    from src.deploy import deploy_agents

    cfg = deploy_agents._build_config(SimpleNamespace(name="x"), display_name="Custom Name")
    assert cfg["display_name"] == "Custom Name"


def test_build_gateway_config_shape():
    """Returns None when the gateway isn't configured, else a dict (never crashes)."""
    from src.deploy import deploy_agents

    gc = deploy_agents._build_gateway_config()
    assert gc is None or isinstance(gc, dict)

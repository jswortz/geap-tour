"""Tests for evaluation pipeline — validates metric definitions and config."""

from src.eval.one_time_eval import (
    HELPFULNESS_METRIC,
    TOOL_USE_METRIC,
    POLICY_COMPLIANCE_METRIC,
    HELPFULNESS_TEMPLATE,
    TOOL_USE_TEMPLATE,
    POLICY_COMPLIANCE_TEMPLATE,
)


def test_helpfulness_metric_defined():
    assert HELPFULNESS_METRIC.name == "helpfulness"
    assert HELPFULNESS_METRIC.prompt_template is not None


def test_tool_use_metric_defined():
    assert TOOL_USE_METRIC.name == "tool_use_accuracy"
    assert TOOL_USE_METRIC.prompt_template is not None


def test_policy_compliance_metric_defined():
    assert POLICY_COMPLIANCE_METRIC.name == "policy_compliance"
    assert POLICY_COMPLIANCE_METRIC.prompt_template is not None


def test_templates_contain_rubric():
    for template in [HELPFULNESS_TEMPLATE, TOOL_USE_TEMPLATE, POLICY_COMPLIANCE_TEMPLATE]:
        assert "{prompt}" in template
        assert "{response}" in template
        assert "1 -" in template
        assert "5 -" in template


def test_templates_have_five_levels():
    for template in [HELPFULNESS_TEMPLATE, TOOL_USE_TEMPLATE, POLICY_COMPLIANCE_TEMPLATE]:
        for level in ["1 -", "2 -", "3 -", "4 -", "5 -"]:
            assert level in template

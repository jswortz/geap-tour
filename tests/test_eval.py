"""Tests for evaluation pipeline — validates eval config and evalset structure."""

import json


def _load_eval_config():
    with open("src/eval/evalsets/eval_config.json") as f:
        return json.load(f)


def _load_evalset(name):
    with open(f"src/eval/evalsets/{name}") as f:
        return json.load(f)


def test_eval_config_has_criteria():
    config = _load_eval_config()
    assert "criteria" in config
    assert len(config["criteria"]) > 0


def test_eval_config_has_response_match():
    config = _load_eval_config()
    assert "response_match_score" in config["criteria"]


def test_eval_config_has_safety():
    config = _load_eval_config()
    assert "safety_v1" in config["criteria"]


def test_coordinator_evalset_has_cases():
    evalset = _load_evalset("coordinator.evalset.json")
    assert "eval_cases" in evalset
    assert len(evalset["eval_cases"]) >= 5


def test_evalset_cases_have_required_fields():
    evalset = _load_evalset("coordinator.evalset.json")
    for case in evalset["eval_cases"]:
        assert "eval_id" in case
        assert "conversation" in case
        assert len(case["conversation"]) > 0
        conv = case["conversation"][0]
        assert "user_content" in conv
        assert "final_response" in conv

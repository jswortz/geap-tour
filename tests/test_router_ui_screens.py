"""Structural tests for the native A2UI screens (no network, no image assets)."""
from app.cost_model import Accrual
from app.ui_builder import (
    DASHBOARD_SURFACE,
    ROUTING_SURFACE,
    build_dashboard_screen,
    build_routing_logic_screen,
)


def _accrual_with_steps() -> Accrual:
    acc = Accrual()
    acc.add("Find flights from SFO to JFK", {"score": 0.15, "reason": "single lookup", "tier_label": "Lite",
            "model": "gemini-3.1-flash-lite", "input_tokens": 40, "output_tokens": 120,
            "cost": 0.00004, "baseline_cost": 0.009})
    acc.add("Plan a 5-day Tokyo trip for 4 with a budget", {"score": 0.9, "reason": "multi-step planning",
            "tier_label": "Opus", "model": "claude-opus-4-6", "input_tokens": 60, "output_tokens": 700,
            "cost": 0.0528, "baseline_cost": 0.0528})
    return acc


def _ids_and_refs(commands: list):
    """Return (declared_ids, referenced_ids) from the surfaceUpdate command."""
    su = next(c["surfaceUpdate"] for c in commands if "surfaceUpdate" in c)
    ids, refs = set(), set()
    for comp in su["components"]:
        ids.add(comp["id"])
        body = comp["component"]
        for kind, spec in body.items():
            if kind in ("Column", "Row"):
                refs.update(spec["children"]["explicitList"])
            elif kind == "Card":
                refs.add(spec["child"])
            elif kind == "Button":
                refs.add(spec["child"])
    return su, ids, refs


def _assert_valid_surface(commands, expect_actions, surface):
    assert isinstance(commands, list) and len(commands) == 2
    begin = next(c["beginRendering"] for c in commands if "beginRendering" in c)
    assert begin["surfaceId"] == surface and begin["root"] == "root-layout"
    su, ids, refs = _ids_and_refs(commands)
    assert su["surfaceId"] == surface
    assert "root-layout" in ids
    # Referential integrity: every referenced child id is declared.
    missing = refs - ids
    assert not missing, f"dangling child refs: {missing}"
    # Expected button actions present.
    actions = {b["component"]["Button"]["action"]["name"]
               for b in su["components"] if "Button" in b["component"]}
    assert expect_actions <= actions, f"missing actions {expect_actions - actions}"


def test_dashboard_empty_state():
    cmds = build_dashboard_screen(Accrual())
    _assert_valid_surface(cmds, {"view_routing"}, DASHBOARD_SURFACE)
    # No VegaChart on the empty state.
    su = next(c["surfaceUpdate"] for c in cmds if "surfaceUpdate" in c)
    assert not any("VegaChart" in c["component"] for c in su["components"])


def test_dashboard_with_steps_has_chart_and_buttons():
    cmds = build_dashboard_screen(_accrual_with_steps())
    _assert_valid_surface(cmds, {"view_routing", "reset"}, DASHBOARD_SURFACE)
    su = next(c["surfaceUpdate"] for c in cmds if "surfaceUpdate" in c)
    vegas = [c for c in su["components"] if "VegaChart" in c["component"]]
    assert len(vegas) == 1
    spec = vegas[0]["component"]["VegaChart"]["spec"]
    assert spec["width"] == "container" and spec["data"]["values"], "chart must have data"


def test_routing_logic_screen_structure():
    cmds = build_routing_logic_screen(_accrual_with_steps())
    _assert_valid_surface(cmds, {"view_dashboard", "reset"}, ROUTING_SURFACE)
    su = next(c["surfaceUpdate"] for c in cmds if "surfaceUpdate" in c)
    # The classifier's real reason for a routed prompt is surfaced somewhere in the text.
    blob = "".join(
        c["component"]["Text"]["text"]["literalString"]
        for c in su["components"] if "Text" in c["component"]
    )
    assert "multi-step planning" in blob and "Opus" in blob


def test_routing_logic_empty_has_no_chart():
    cmds = build_routing_logic_screen(Accrual())
    _assert_valid_surface(cmds, {"view_dashboard", "reset"}, ROUTING_SURFACE)
    su = next(c["surfaceUpdate"] for c in cmds if "surfaceUpdate" in c)
    assert not any("VegaChart" in c["component"] for c in su["components"])

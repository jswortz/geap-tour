"""Structural tests for the A2UI screens (Image docked in the GE canvas) + PNG render smoke tests."""
import pytest

from app.cost_model import Accrual
from app.ui_builder import CANVAS_SURFACE, build_dashboard_screen, build_routing_logic_screen

URL = "https://svc.example/panels/dashboard.png?ctx=abc&v=2"


def _accrual_with_steps() -> Accrual:
    acc = Accrual()
    acc.add("Find flights from SFO to JFK", {"score": 0.15, "reason": "single lookup", "tier_label": "Lite",
            "model": "gemini-3.1-flash-lite", "input_tokens": 40, "output_tokens": 120,
            "cost": 0.00004, "baseline_cost": 0.009})
    acc.add("Plan a 5-day Tokyo trip for 4 with a budget", {"score": 0.9, "reason": "multi-step planning",
            "tier_label": "Opus", "model": "claude-opus-4-6", "input_tokens": 60, "output_tokens": 700,
            "cost": 0.0528, "baseline_cost": 0.0528})
    return acc


def _ids_refs_and_su(commands):
    su = next(c["surfaceUpdate"] for c in commands if "surfaceUpdate" in c)
    ids, refs = set(), set()
    for comp in su["components"]:
        ids.add(comp["id"])
        for kind, spec in comp["component"].items():
            if kind in ("Column", "Row"):
                refs.update(spec["children"]["explicitList"])
            elif kind in ("Card", "Button"):
                refs.add(spec["child"])
    return su, ids, refs


def _assert_valid(commands, expect_actions):
    assert isinstance(commands, list) and len(commands) == 2
    begin = next(c["beginRendering"] for c in commands if "beginRendering" in c)
    assert begin["surfaceId"] == CANVAS_SURFACE and begin["root"] == "root-layout"
    su, ids, refs = _ids_refs_and_su(commands)
    assert su["surfaceId"] == CANVAS_SURFACE and "root-layout" in ids
    assert not (refs - ids), f"dangling refs: {refs - ids}"
    actions = {b["component"]["Button"]["action"]["name"] for b in su["components"] if "Button" in b["component"]}
    assert expect_actions <= actions, f"missing actions {expect_actions - actions}"
    # Exactly one Image, carrying the given URL (this is what docks in the GE canvas).
    imgs = [c for c in su["components"] if "Image" in c["component"]]
    assert len(imgs) == 1
    assert imgs[0]["component"]["Image"]["url"]["literalString"] == URL


def test_dashboard_screen_is_image_plus_tabs():
    _assert_valid(build_dashboard_screen(_accrual_with_steps(), URL), {"view_routing", "reset"})


def test_dashboard_empty_still_valid():
    _assert_valid(build_dashboard_screen(Accrual(), URL), {"view_routing", "reset"})


def test_routing_logic_screen_is_image_plus_tabs():
    _assert_valid(build_routing_logic_screen(_accrual_with_steps(), URL), {"view_dashboard", "reset"})


# --- PNG render smoke tests (skip if matplotlib isn't installed in the local env) ---
matplotlib = pytest.importorskip("matplotlib")


def _is_png(b: bytes) -> bool:
    return isinstance(b, bytes) and b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) > 1000


def test_render_dashboard_png_empty_and_populated():
    from app import panel_render
    assert _is_png(panel_render.render_dashboard_png(Accrual()))
    assert _is_png(panel_render.render_dashboard_png(_accrual_with_steps()))


def test_render_routing_png_empty_and_populated():
    from app import panel_render
    assert _is_png(panel_render.render_routing_png(Accrual()))
    assert _is_png(panel_render.render_routing_png(_accrual_with_steps()))

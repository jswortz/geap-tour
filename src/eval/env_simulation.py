"""Environment simulation for agent evaluation — tool-call interception, mocking,
and deterministic error injection.

Implements the "environment simulation" capability described in the Optimize >
Evaluation docs, complementing the simulated-user eval in
``src/eval/simulated_eval.py``:

  - Evaluate with simulated users:
    https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/evaluate-simulated
  - Agent evaluation overview:
    https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation

Whereas ``simulated_eval`` drives the *user* side of a conversation with an LLM
user-simulator, environment simulation controls the *world* the agent acts on:
we intercept the agent's tools (MCP toolsets in production) so we can

  1. return deterministic **mocked** data instead of calling a live backend, and
  2. inject deterministic **failures** (e.g. HTTP 503 / latency) to test how the
     agent recovers — retries, apologies, graceful degradation — without ever
     touching production systems.

Feeding these traces into the multi-turn autoraters (task success, tool-use
quality, trajectory quality) then measures resilience, not just happy-path
behavior.

Determinism note: error injection is **counter-based**, never random. Given the
same call sequence you get the same failures, so eval runs are reproducible and
CI stays stable.

Usage:
    uv run python -m src.eval.env_simulation
"""

import functools


def tool_call_interceptor(tool_fn, mock_result=None, error_every: int = 0, error_exc=None):
    """Wrap ``tool_fn`` so calls can be mocked and/or fail deterministically.

    The wrapper counts invocations (1-based). On the Nth call where
    ``error_every > 0`` and ``call_index % error_every == 0`` it raises
    ``error_exc`` (or a default ``RuntimeError`` simulating an HTTP 503).
    Otherwise it returns ``mock_result`` if one was supplied, else it delegates
    to the original ``tool_fn``.

    Args:
        tool_fn: The original callable being intercepted.
        mock_result: If not None, returned in place of calling ``tool_fn``.
        error_every: Inject a failure on every Nth call (0 disables injection).
        error_exc: Exception instance to raise instead of the default 503.

    Returns:
        A wrapped callable with the same call signature. The wrapper exposes a
        ``call_count`` attribute (a callable returning the invocation count).
    """
    state = {"calls": 0}

    def wrapped(*args, **kwargs):
        state["calls"] += 1
        call_index = state["calls"]
        if error_every > 0 and call_index % error_every == 0:
            raise (error_exc or RuntimeError("simulated tool failure (HTTP 503)"))
        if mock_result is not None:
            return mock_result
        return tool_fn(*args, **kwargs)

    # Preserve the original tool's identity where possible (name/doc), so a
    # wrapped tool still looks like the real one to the agent framework.
    try:
        functools.update_wrapper(wrapped, tool_fn)
    except (AttributeError, TypeError):
        pass

    wrapped.call_count = lambda: state["calls"]
    return wrapped


def wrap_tools(tools: dict, mocks: dict | None = None, error_every: int = 0) -> dict:
    """Apply :func:`tool_call_interceptor` across a set of named tools.

    Args:
        tools: Mapping of tool name -> original callable.
        mocks: Optional mapping of tool name -> mock result. A tool with no
            entry falls through to its real implementation (unless an error is
            injected).
        error_every: Inject a failure on every Nth call of *each* wrapped tool.

    Returns:
        A new dict mapping each tool name to its intercepted callable.
    """
    mocks = mocks or {}
    return {
        name: tool_call_interceptor(
            fn,
            mock_result=mocks.get(name),
            error_every=error_every,
        )
        for name, fn in tools.items()
    }


# ---------------------------------------------------------------------------
# Illustrative, offline demo — no live GCP required
# ---------------------------------------------------------------------------
def _example_live_tools() -> dict:
    """Stand-in "live" tools. In production these are the agent's MCP toolsets;
    here they just mark output as LIVE so mock vs. real is visible in the demo.
    """

    def search_flights(origin="SFO", destination="JFK", date="Monday"):
        return f"LIVE search_flights({origin}->{destination}, {date})"

    def search_hotels(city="New York", max_price=None):
        return f"LIVE search_hotels({city}, max_price={max_price})"

    def check_expense_policy(category="meals", amount=0):
        return f"LIVE check_expense_policy({category}, {amount})"

    return {
        "search_flights": search_flights,
        "search_hotels": search_hotels,
        "check_expense_policy": check_expense_policy,
    }


def _example_mocks() -> dict:
    """Deterministic mocked responses that mirror the eval environment_context
    (FL001-FL005 flights, HT001-HT003 hotels, corporate policy limits)."""
    return {
        "search_flights": [
            {"flight_id": "FL001", "route": "SFO->JFK", "price": 420, "airline": "United"},
            {"flight_id": "FL002", "route": "SFO->JFK", "price": 510, "airline": "Delta"},
        ],
        "search_hotels": [
            {"hotel_id": "HT001", "name": "Grand Hyatt", "city": "New York", "price": 320},
            {"hotel_id": "HT002", "name": "Budget Inn", "city": "New York", "price": 145},
        ],
        "check_expense_policy": {"category": "meals", "limit": 75, "within_policy": True},
    }


def run_with_env_simulation(
    agent_resource=None,
    agent_name: str = "travel_agent",
    inject_errors: bool = True,
) -> dict:
    """Demonstrate how to intercept an agent's tools before a simulated eval.

    This is an *illustrative* driver: it documents and exercises the pattern
    you'd apply to the agent's MCP tools ahead of
    ``src.eval.simulated_eval.run_simulated_eval`` so resilience is tested
    against mocked data and injected failures instead of production backends.
    It runs fully offline (no live GCP).

    Args:
        agent_resource: Deployed agent resource name (unused in the demo; shown
            to illustrate where it would flow into ``run_simulated_eval``).
        agent_name: Which agent's world to simulate.
        inject_errors: When True, inject a deterministic HTTP 503 on every 3rd
            tool call to exercise the agent's error handling.

    Returns:
        A summary dict describing the demo run.
    """
    print("=" * 72)
    print(f"Environment simulation demo — agent_name={agent_name!r}")
    print("=" * 72)
    print(
        "In production, replace each MCP toolset on the agent with an\n"
        "intercepted version, then run the simulated-user eval:\n"
        "    live_tools = {t.name: t for t in agent.tools}         # MCP tools\n"
        "    wrapped    = wrap_tools(live_tools, mocks=..., error_every=3)\n"
        "    # ...attach `wrapped` to the agent, then:\n"
        "    run_simulated_eval(agent_resource, agent_name=..., multi_turn=True)\n"
    )

    error_every = 3 if inject_errors else 0
    live_tools = _example_live_tools()
    mocks = _example_mocks()
    wrapped = wrap_tools(live_tools, mocks=mocks, error_every=error_every)

    print(f"Wrapped {len(wrapped)} tools: {sorted(wrapped)}")
    print(f"Error injection: every {error_every} call(s)" if error_every else "Error injection: OFF")
    print("-" * 72)

    injected_errors = 0
    mock_hits = 0
    total_calls = 0

    # Exercise one tool several times so the demo shows: mocked data on most
    # calls and one injected 503 on the 3rd call.
    tool_name = "search_flights"
    tool = wrapped[tool_name]
    for attempt in range(1, 5):
        total_calls += 1
        try:
            result = tool(origin="SFO", destination="JFK")
            mock_hits += 1
            print(f"  call {attempt}: {tool_name} -> mocked data: {result}")
        except Exception as e:  # noqa: BLE001 — this is the injected failure path
            injected_errors += 1
            print(f"  call {attempt}: {tool_name} -> INJECTED FAILURE: {type(e).__name__}: {e}")

    # Show that mocks also apply to the other tools (single call each).
    for other in ("search_hotels", "check_expense_policy"):
        total_calls += 1
        try:
            result = wrapped[other]()
            mock_hits += 1
            print(f"  call 1: {other} -> mocked data: {result}")
        except Exception as e:  # noqa: BLE001
            injected_errors += 1
            print(f"  call 1: {other} -> INJECTED FAILURE: {type(e).__name__}: {e}")

    print("-" * 72)
    summary = {
        "agent_name": agent_name,
        "agent_resource": agent_resource,
        "tools_wrapped": sorted(wrapped),
        "total_calls": total_calls,
        "mock_hits": mock_hits,
        "injected_errors": injected_errors,
        "error_every": error_every,
    }
    print(f"Summary: {summary}")
    print(
        "\nNext step: feed these intercepted-tool traces through the multi-turn\n"
        "autoraters (MULTI_TURN_TASK_SUCCESS / _TOOL_USE_QUALITY / _TRAJECTORY_QUALITY)\n"
        "to score how the agent recovers from injected failures — resilience,\n"
        "not just happy-path behavior."
    )
    return summary


if __name__ == "__main__":
    run_with_env_simulation()

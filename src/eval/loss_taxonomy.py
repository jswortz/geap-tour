"""Predefined loss-pattern taxonomies for agent-evaluation failure triage.

These are the named failure taxonomies documented by Google's Gemini Enterprise
Agent Platform for interpreting evaluation results and failure clusters. The
patterns below are the fixed vocabulary that failures surfaced by
``client.evals.generate_loss_clusters()`` get grouped into: each auto-generated
loss cluster (title + description) is mapped onto one of these predefined loss
patterns so that systemic weaknesses can be tallied by category.

- ``TASK_SUCCESS_TAXONOMY`` is used with the ``multi_turn_task_success_v1`` metric.
- ``TOOL_USE_QUALITY_TAXONOMY`` is used with the ``multi_turn_tool_use_quality_v1``
  metric.

See "Analyze evaluation results and failure clusters":
https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/view-results
"""

from __future__ import annotations

# --- Loss-pattern taxonomy for the multi_turn_task_success_v1 metric ---------
TASK_SUCCESS_TAXONOMY: dict[str, list[str]] = {
    "Hallucination": [
        "Hallucination of Action",
        "Hallucination of Missing Information",
        "Hallucination of Tool or Capability",
    ],
    "Instruction Following": [
        "Constraint Violation",
        "Futile Action (Under-Punting)",
        "Incomplete Execution",
        "Over-Punting",
    ],
    "Tool Calling": [
        "Incorrect Tool Selection",
        "Semantically Incorrect Tool Parameters",
        "Syntactically Incorrect Tool Call",
    ],
    "Tool Output Handling": [
        "Incorrect Tool Output Processing",
    ],
    "Tool Quality": [
        "Insufficient Tool Output",
        "Tool Failure",
    ],
}

# --- Loss-pattern taxonomy for the multi_turn_tool_use_quality_v1 metric ------
TOOL_USE_QUALITY_TAXONOMY: dict[str, list[str]] = {
    "Hallucination": [
        "Hallucination of Parameter Value",
        "Hallucination of Tool",
    ],
    "Tool Calling": [
        "Failure to Set Parameter",
        "Incorrect Parameter Data Type",
        "Incorrect Parameter Mapping",
        "Incorrect Parameter Value",
        "Incorrect Tool Selection",
        "Invalid Tool Call Syntax",
        "Non-Existent Parameter",
        "Omission of Required Tool Call",
        "Under-Punting",
    ],
    "Tool Response": [
        "Irrelevant Tool Response",
        "Tool Error",
    ],
}


def _build_all_patterns() -> dict[str, str]:
    """Merge both taxonomies into ``lowercased pattern -> category``."""
    merged: dict[str, str] = {}
    for taxonomy in (TASK_SUCCESS_TAXONOMY, TOOL_USE_QUALITY_TAXONOMY):
        for category, patterns in taxonomy.items():
            for pattern in patterns:
                merged[pattern.lower()] = category
    return merged


# Lowercased pattern name -> category, merged across both taxonomies.
ALL_PATTERNS: dict[str, str] = _build_all_patterns()

# Canonical (original-cased) pattern name keyed by its lowercased form, so we can
# report the properly-cased pattern label after a case-insensitive match.
_CANONICAL_PATTERNS: dict[str, str] = {}
for _taxonomy in (TASK_SUCCESS_TAXONOMY, TOOL_USE_QUALITY_TAXONOMY):
    for _patterns in _taxonomy.values():
        for _pattern in _patterns:
            _CANONICAL_PATTERNS.setdefault(_pattern.lower(), _pattern)

# Match longest (most specific) pattern phrases first so that, e.g.,
# "hallucination of tool or capability" wins over "hallucination of tool".
_PATTERNS_BY_SPECIFICITY: list[str] = sorted(
    ALL_PATTERNS, key=len, reverse=True
)


def _field(cluster, name: str) -> str:
    """Read ``name`` from a cluster whether it is a dict or an object."""
    if isinstance(cluster, dict):
        value = cluster.get(name, "")
    else:
        value = getattr(cluster, name, "")
    return "" if value is None else str(value)


def map_cluster_to_taxonomy(cluster) -> dict:
    """Map a loss cluster onto a predefined loss pattern + category.

    ``cluster`` may be an object (with ``title`` / ``description`` attributes) or
    a dict (with ``title`` / ``description`` keys). The cluster's text is matched
    case-insensitively (substring/keyword match) against the known pattern names.

    Returns ``{"pattern": <matched pattern or "Uncategorized">,
    "category": <category or "Uncategorized">}``.
    """
    title = _field(cluster, "title")
    description = _field(cluster, "description")
    haystack = f"{title} {description}".lower()

    for pattern in _PATTERNS_BY_SPECIFICITY:
        if pattern in haystack:
            return {
                "pattern": _CANONICAL_PATTERNS[pattern],
                "category": ALL_PATTERNS[pattern],
            }

    return {"pattern": "Uncategorized", "category": "Uncategorized"}


def list_taxonomy(which: str = "both") -> list[str]:
    """Return a flat list of ``"Category: Pattern"`` strings.

    ``which`` selects the taxonomy: ``"task_success"``, ``"tool_use"`` /
    ``"tool_use_quality"``, or ``"both"`` (default).
    """
    which = (which or "both").lower()
    taxonomies: list[dict[str, list[str]]] = []
    if which in ("task_success", "both"):
        taxonomies.append(TASK_SUCCESS_TAXONOMY)
    if which in ("tool_use", "tool_use_quality", "both"):
        taxonomies.append(TOOL_USE_QUALITY_TAXONOMY)

    entries: list[str] = []
    for taxonomy in taxonomies:
        for category, patterns in taxonomy.items():
            for pattern in patterns:
                entries.append(f"{category}: {pattern}")
    return entries

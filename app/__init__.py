"""GEAP Router Cost Visualizer — an A2UI (generative-UI) app for Gemini Enterprise.

Renders how the multi-model complexity router accrues cost: each prompt is classified,
routed to a model tier, and its cost accumulates — visualized against an all-frontier
(all-Opus) baseline so the savings are obvious.

Follows the proven GE + A2UI-over-Cloud-Run pattern from party-store-ge-a2ui and
dg-ge-data-agent: a deterministic AgentExecutor emits branded ``WebFrameSrcdoc`` HTML
panels (DataParts tagged ``application/json+a2ui``) served as an A2A HTTP service.
"""

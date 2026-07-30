# GEAP Workshop — Documentation Index

A map of everything under `docs/`. New here? Start with the **Workshop Guide**, or jump straight to the
two **SDK-first notebooks** (build, then evaluate). Full project overview: [`../README.md`](../README.md).

## Start here
| Doc | What it's for |
|-----|----------------|
| [workshop_guide.md](workshop_guide.md) | The full 4-session hands-on walkthrough (build → govern → evaluate → secure). |
| [`../src/deploy/demo/platform_sdk_demo.ipynb`](../src/deploy/demo/platform_sdk_demo.ipynb) | **Build → Deploy → Register** notebook (SDK-first): MCP tools, ADK agents, deploy, GE registration, routing/cost. |
| [`../src/eval/demo/evaluation_sdk_demo.ipynb`](../src/eval/demo/evaluation_sdk_demo.ipynb) | **Evaluation** notebook (SDK-first): the Quality Flywheel end-to-end. |
| [faq.md](faq.md) | What each platform component is and why it matters. |

## Hands-on deep-dives (SDK-first notebooks)
| Notebook | What it teaches |
|----------|-----------------|
| [`../src/deploy/demo/gateway_sdk_demo.ipynb`](../src/deploy/demo/gateway_sdk_demo.ipynb) | **Agent Gateway** — dual-mode (ingress/egress) config, create gateways, attach at deploy, and the three policy layers (IAM/CEL, Semantic Governance, IAP + Model Armor). |
| [`../src/deploy/demo/registry_sdk_demo.ipynb`](../src/deploy/demo/registry_sdk_demo.ipynb) | **Agent Registry** — register/discover, bindings, and **cross-project hub-and-spoke** discovery via App Hub + `agent-registry agents search`. |
| [`../src/mcp_servers/demo/mcp_sdk_demo.ipynb`](../src/mcp_servers/demo/mcp_sdk_demo.ipynb) | **MCP servers** — author a FastMCP tool, deploy, register, then monitor (Cloud Run metrics, logs, traces, alerts). |

## Evaluation
| Doc | What it's for |
|-----|----------------|
| [eval_operations.md](eval_operations.md) | Evaluation operations guide + the Optimize→Evaluation **coverage matrix**. |
| [evaluation_demo.md](evaluation_demo.md) | Screenshot-backed Quality-Flywheel demo walkthrough. |
| [eval_slides.html](eval_slides.html) / [eval_slides.pptx](eval_slides.pptx) | 7-slide teach-in on agent evaluation. |

## Publish & operate
| Doc | What it's for |
|-----|----------------|
| [publishing_agents_to_gemini_enterprise.md](publishing_agents_to_gemini_enterprise.md) | Register the coordinator + router directly to a Gemini Enterprise app. |
| [router_cost_visualizer_published.md](router_cost_visualizer_published.md) | Evidence log: the Router Cost Visualizer live in GE. |
| [monitoring_integration_guide.md](monitoring_integration_guide.md) | Observability + quality-alerts pipeline setup. |
| [multi_model_cost_comparison.md](multi_model_cost_comparison.md) | Multi-model routing cost/latency/quality analysis. |
| [gateway_test_report.md](gateway_test_report.md) | Agent Gateway test report. |

## Slides & diagrams
| Doc | What it's for |
|-----|----------------|
| [slides.pptx](slides.pptx) / [slides.html](slides.html) | The full workshop deck (34 slides). |
| [eval_slides.html](eval_slides.html) / [eval_slides.pptx](eval_slides.pptx) | Evaluation teach-in deck (7 slides). |
| [router_cost_visualizer.html](router_cost_visualizer.html) | Self-contained interactive cost dashboard. |
| [`../diagrams/outputs/`](../diagrams/outputs/) | Architecture diagrams (PNG). |

## Reference artifacts
- [screenshots/](screenshots/) — console screenshots used across the docs and slides.
- [verification/](verification/) — captured GCP resource evidence (Cloud Run, sinks, Model Armor).

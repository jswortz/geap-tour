# Multi-Model Cost Comparison

## Thesis

> "The future is multi-model — right model for right task and needs at hand."
> — [gemini-model-router](https://github.com/jswortz/gemini-model-router)

This demo routes prompts by complexity to the most cost-effective model:
- **Low** (simple lookups) → Gemini 2.0 Flash Lite ($0.075/M input)
- **Medium** (moderate reasoning) → Gemini 2.5 Flash ($0.15/M input)
- **High** (deep analysis) → Claude Opus 4-7 via Vertex AI ($15/M input)

## Architecture

```
User Prompt
    |
    v
[Model Armor] -- safety screening (RAI, PI, jailbreak)
    |
    v
[Router Agent] (gemini-2.0-flash-lite)
    |  before_agent_callback: classify_complexity()
    |  Gemini Flash Lite scores prompt 0-1, maps to low/med/high
    |
    |-- low ----> [Lite Agent]  gemini-2.0-flash-lite  $0.075/M in
    |-- medium -> [Flash Agent] gemini-2.5-flash       $0.15/M in
    |-- high ---> [Opus Agent]  claude-opus-4-7        $15.00/M in
```

**Why not Model Armor for complexity?** Model Armor only provides safety filters
(RAI, PI detection, jailbreak, malicious URI). It has no prompt complexity scoring.
We use Gemini Flash Lite as a micro-classifier (~$0.00002/call).

**Why not AI Gateway for routing?** The Agent Gateway operates at the network level
(CLIENT_TO_AGENT / AGENT_TO_ANYWHERE) with IAM and SGP policies. It cannot select
models based on prompt content. Routing happens at the ADK orchestration layer.

## Results

**Test set:** 10 prompts (2 low, 3 medium, 5 high)

**Assumed tokens:** 200 input, 500 output per request

| Configuration | Model(s) | Total Cost | vs All-Opus Savings |
|--------------|----------|-----------|-------------------|
| All Flash Lite | mixed | $0.001650 | 99.6% |
| All Flash | mixed | $0.003300 | 99.2% |
| All Opus | mixed | $0.405000 | baseline |
| Smart Router | mixed | $0.203907 | 49.7% |

## Per-Prompt Routing Decisions (Smart Router)

| # | Prompt (truncated) | Score | Level | Model |
|---|-------------------|-------|-------|-------|
| 1 | Find flights from SFO to JFK... | 0.30 | low | gemini-2.0-flash-lite |
| 2 | What's the expense policy for meals?... | 0.30 | low | gemini-2.0-flash-lite |
| 3 | Search hotels in Chicago under $200... | 0.40 | medium | gemini-2.5-flash |
| 4 | Check if a $50 transport expense is within policy... | 0.40 | medium | gemini-2.5-flash |
| 5 | Find flights to NYC and compare the cheapest optio... | 0.60 | medium | gemini-2.5-flash |
| 6 | Search hotels in Boston, then check if the nightly... | 0.70 | high | claude-opus-4-7 |
| 7 | Plan a 5-day trip to Tokyo for a team of 4: find f... | 0.80 | high | claude-opus-4-7 |
| 8 | Compare individual vs group flight bookings for ou... | 0.80 | high | claude-opus-4-7 |
| 9 | Analyze EMP001's expense history: they overspent o... | 0.80 | high | claude-opus-4-7 |
| 10 | Book the cheapest SFO-JFK flight, find a hotel wit... | 0.90 | high | claude-opus-4-7 |

## At Scale (monthly projections)

| Scenario | Requests/mo | All-Opus | Smart Router | Savings |
|----------|------------|----------|-------------|---------|
| Light usage | 1,000 | $40.50 | $4.23 | 90% |
| Medium usage | 10,000 | $405.00 | $62.56 | 85% |
| Heavy usage | 100,000 | $4,050.00 | $828.15 | 80% |

## Limitations

- Model Armor's `ModelArmorConfig` only works with Gemini models; the Opus agent uses client-side guardrails only
- Claude Opus 4-7 availability may vary by region (us-east5, global endpoint)
- Classifier adds ~100-200ms latency per request
- Cost comparison uses list pricing; enterprise discounts change ratios
- Token counts are estimated averages, not measured from actual API responses

## Connection to gemini-model-router

The [gemini-model-router](https://github.com/jswortz/gemini-model-router) demonstrated
35% cost savings with a 4-backend router (Gemma4, Gemini, Claude, Vertex API) using
embedding-based classification. This demo validates the same thesis using GCP-native
infrastructure (ADK + Model Armor + Gateway) with an LLM-as-classifier approach.
The key insight is identical: **you pay for what you need** — most prompts don't
require frontier-model reasoning.
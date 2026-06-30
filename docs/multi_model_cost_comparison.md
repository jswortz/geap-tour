# Multi-Model Prompt Router — Cost, Latency & Quality Report

> Generated: 2026-05-27T21:07:11  
> Rounds: 3 | Cases/round: 22 | Models evaluated: 5 | Judge: `gemini-2.5-pro`

> **Official docs:**
> - [Gemini Models on Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini)
> - [Claude on Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/partner-models/use-claude)
> - [Vertex AI Pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)

## Architecture

```
User Prompt
    |
    v
[Model Armor] -- safety screening (RAI, PI, jailbreak)
    |
    v
[Router Agent] (gemini-3.1-flash-lite)
    |  before_agent_callback: classify_complexity()
    |  Flash Lite scores prompt 0-1, maps to 5-tier
    |
    |-- score<0.30   --> [Lite]   `gemini-3.1-flash-lite`
    |-- score<0.45   --> [Flash]  `gemini-3.5-flash`
    |-- score<0.60   --> [Sonnet] `claude-sonnet-4-5`
    |-- score<0.80   --> [Pro]    `gemini-3.1-pro-preview`
    +-- score>=0.80  --> [Opus]   `claude-opus-4-6`
```

## Classifier Accuracy

**Overall: 100.0%** (95% CI: [100.0%, 100.0%])

| Tier | Accuracy | Correct / Total |
|------|----------|-----------------|
| low | 100% | 30/30 |
| medium | 100% | 18/18 |
| high | 100% | 18/18 |

### Confusion Matrix

| Expected \ Actual | Low | Medium | High |
|-------------------|-----|--------|------|
| low | 30 | 0 | 0 |
| medium | 0 | 18 | 0 |
| high | 0 | 0 | 18 |

Avg classifier latency: **3307 ms**  

## Per-Model Latency

Wall-clock time from request to response. Direct API calls — no tools, no MCP, no ADK overhead.

| Tier | Model | Mean (ms) | p50 (ms) | p95 (ms) | 95% CI of mean |
|------|-------|-----------|----------|----------|----------------|
| lite | `gemini-3.1-flash-lite` | 4352 | 2697 | 16203 | [3017, 6148] |
| flash | `gemini-3.5-flash` | 4922 | 4722 | 7227 | [4644, 5211] |
| pro | `gemini-3.1-pro-preview` | 11258 | 11560 | 14361 | [10686, 11827] |
| sonnet | `claude-sonnet-4-5` | 10578 | 10504 | 11686 | [10414, 10750] |
| opus | `claude-opus-4-6` | 11786 | 11615 | 13840 | [11492, 12094] |

## Per-Model Cost

Real token counts from API `usage_metadata`, cost computed from current per-1M-token pricing.

| Tier | Model | Avg In Tokens | Avg Out Tokens | $/call | Total $ |
|------|-------|--------------:|---------------:|-------:|--------:|
| lite | `gemini-3.1-flash-lite` | 101 | 277 | $0.000091 | $0.0060 |
| flash | `gemini-3.5-flash` | 101 | 258 | $0.000170 | $0.0112 |
| pro | `gemini-3.1-pro-preview` | 102 | 232 | $0.002444 | $0.1564 |
| sonnet | `claude-sonnet-4-5` | 111 | 385 | $0.006101 | $0.4027 |
| opus | `claude-opus-4-6` | 112 | 451 | $0.035489 | $2.3423 |

## Per-Model Quality (LLM-as-Judge)

4-dim rubric, each 1-5. Overall = mean of the four. Single comparative judge call per prompt (responses anonymized A-E, order shuffled per call to mitigate bias).

| Tier | Model | Plan | Correct | Reasoning | Tools | **Overall** | 95% CI |
|------|-------|-----:|--------:|----------:|------:|------------:|--------|
| lite | `gemini-3.1-flash-lite` | 4.77 | 4.21 | 4.47 | 4.30 | **4.44** | [4.28, 4.59] |
| flash | `gemini-3.5-flash` | 4.74 | 4.54 | 4.42 | 4.69 | **4.60** | [4.50, 4.69] |
| pro | `gemini-3.1-pro-preview` | 3.93 | 4.03 | 3.91 | 4.34 | **4.06** | [3.76, 4.33] |
| sonnet | `claude-sonnet-4-5` | 4.94 | 3.92 | 4.58 | 4.21 | **4.41** | [4.24, 4.57] |
| opus | `claude-opus-4-6` | 4.91 | 4.29 | 4.82 | 4.50 | **4.63** | [4.49, 4.75] |

## Cost-Quality Frontier

Quality per dollar — higher is better. Sorted by efficiency.

| Rank | Tier | Model | Quality | $/call | Quality / $ |
|------|------|-------|--------:|-------:|------------:|
| 1 | lite | `gemini-3.1-flash-lite` | 4.44 | $0.000091 | 48,974 |
| 2 | flash | `gemini-3.5-flash` | 4.60 | $0.000170 | 27,064 |
| 3 | pro | `gemini-3.1-pro-preview` | 4.06 | $0.002444 | 1,659 |
| 4 | sonnet | `claude-sonnet-4-5` | 4.41 | $0.006101 | 723 |
| 5 | opus | `claude-opus-4-6` | 4.63 | $0.035489 | 130 |

## Smart Router Synthesis

What you actually get in production: for each prompt, pick the response from the model the classifier routed to. Compared against the two extremes (all-Lite = cheapest, all-Opus = most expensive).

| Strategy | Avg Latency (ms) | Avg Quality | Total $ | vs all-Opus |
|---|---|---|---|---|
| **Smart Router** | 8144 | 4.38 | $0.7327 | +68.7% |
| All-Lite | 4352 | 4.44 | $0.0060 | +99.7% |
| All-Opus | 11786 | 4.63 | $2.3423 | baseline |

## Statistical Significance

- **Cost savings (smart router vs all-Opus):** mean 68.7%, 95% CI [68.6%, 69.0%].
- **Quality (smart router vs all-Opus, paired t-test):** t=-2.76, p=0.0058, n=51 — Smart router quality differs significantly from Opus (review direction below).
  - Mean quality delta (smart - opus): -0.319 — Opus scored higher.

## Pricing Reference (per 1M tokens)

| Model | Input $ | Output $ |
|-------|--------:|---------:|
| `gemini-3.1-flash-lite` | $0.075 | $0.30 |
| `gemini-3.5-flash` | $0.150 | $0.60 |
| `gemini-3.1-pro-preview` | $1.250 | $10.00 |
| `claude-sonnet-4-5` | $3.000 | $15.00 |
| `claude-opus-4-6` | $15.000 | $75.00 |

## Scaling Projections

Monthly cost projection assuming the per-prompt mix observed in this benchmark.

| Daily Volume | All-Opus / day | Smart Router / day | Monthly Savings |
|-------------|---------------:|-------------------:|----------------:|
| 100 | $3.55 | $1.11 | $73 |
| 1,000 | $35.49 | $11.10 | $732 |
| 10,000 | $354.89 | $111.02 | $7,316 |
| 100,000 | $3548.93 | $1110.20 | $73,162 |

## Methodology

- **Test set:** 22 prompts spanning low / medium / high complexity tiers.
- **Rounds:** 3. Each (prompt, model) cell is run 3 time(s); metrics are aggregated across all runs.
- **Inference:** direct API calls (`google.genai` for Gemini, LiteLLM `acompletion` for Claude). No ADK orchestration, no MCP tools, no Cloud Run round-trip — to isolate model behavior.
- **System instruction:** asks models to describe the plan they'd execute (tool names, args, synthesis steps) since tools are not provided. Quality is rated on reasoning, not tool execution.
- **Quality judge:** single comparative call per prompt over all anonymized responses (A-E, shuffled). Mitigates ordering bias. Judge is `gemini-2.5-pro` (not Opus, to avoid self-grading bias).
- **Concurrency:** within each prompt, the 5 models are called in parallel via `asyncio.gather`. Across prompts, runs are sequential to avoid quota spikes.

## Limitations

- **No tool execution.** Quality reflects reasoning and tool *selection*, not real tool outcomes. End-to-end task success requires the full ADK + MCP stack and would add Cloud Run latency.
- **LLM-as-judge bias.** Even with anonymization and a non-Opus judge, the rubric is subjective. Treat quality scores as comparative, not absolute.
- **List pricing.** Cost uses public per-1M-token rates; enterprise discounts change ratios.
- **Latency variance.** Cold starts and queueing effects can vary by run; we report mean / p50 / p95.
- **Token estimates for thinking models.** Gemini 3.x thinking tokens are billed at output rate and already included in `candidates_token_count`.

---
*Report generated by `src/eval/router_report.py`*
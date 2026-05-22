# GEPA Optimizer Wrapper Modules

The `*_agent_opt/` directories are **optimization scaffolding** for running GEPA
(Gemini Evolutionary Prompt Algorithm) on each router sub-agent.

GEPA's `GEPARootAgentPromptOptimizer` only optimizes root agent prompts. Since
the router's sub-agents aren't root agents, each wrapper module re-exports a
sub-agent as `root_agent` so GEPA can optimize its instruction.

## Structure

```
lite_agent_opt/
├── __init__.py              # Exposes lite_agent as root_agent
└── lite_eval_set.evalset.json  # 15 eval cases for optimization
```

## Usage

```bash
uv run python -m src.optimize.run_optimize src/router/lite_agent_opt src/optimize/lite_sampler_config.json
```

## After Optimization

Copy the optimized instruction from GEPA output into the corresponding
standalone agent file (`src/agents/lite_agent.py` etc.). The router sub-agents
in `src/router/agents.py` import instructions from the standalone agents,
so updating one updates both.

## These directories can be safely deleted

They are not imported by any production code. They exist only for running
GEPA optimization and can be recreated from the pattern above.

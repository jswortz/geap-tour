from src.router.agents import sonnet_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=sonnet_agent)
root_agent = sonnet_agent

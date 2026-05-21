from src.router.agents import opus_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=opus_agent)
root_agent = opus_agent

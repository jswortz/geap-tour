from src.router.agents import flash_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=flash_agent)
root_agent = flash_agent

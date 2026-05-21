from src.router.agents import pro_agent

import types as _t
agent = _t.SimpleNamespace(root_agent=pro_agent)
root_agent = pro_agent

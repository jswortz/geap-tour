import vertexai
from vertexai import agent_engines
vertexai.init(project="wortz-project-352116", location="us-central1")
agent = agent_engines.get("projects/wortz-project-352116/locations/us-central1/reasoningEngines/4926149092750393344")
try:
    session = agent.create_session(user_id="alice")
    print(session)
except Exception as e:
    import traceback
    traceback.print_exc()

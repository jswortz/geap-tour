import vertexai
from vertexai import agent_engines
vertexai.init(project="wortz-project-352116", location="us-central1")
agent = agent_engines.get("projects/wortz-project-352116/locations/us-central1/reasoningEngines/4926149092750393344")
try:
    response = agent.stream_query(message="Hello")
    full_response = ""
    for chunk in response:
        if hasattr(chunk, "text"):
            full_response += chunk.text
        elif isinstance(chunk, dict) and "text" in chunk:
            full_response += chunk["text"]
    print(full_response)
except Exception as e:
    import traceback
    traceback.print_exc()

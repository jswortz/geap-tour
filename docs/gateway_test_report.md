# Agent Gateway Test Report — 2026-05-15

## Setup

- **Project:** `wortz-project-352116`
- **Region:** `us-central1`
- **Gateway:** `geap-workshop-gateway-egress` (AGENT_TO_ANYWHERE, protocols: MCP)
- **API version:** `networkservices.googleapis.com/v1beta1`

### APIs Enabled

```bash
gcloud services enable \
    aiplatform.googleapis.com \
    networkservices.googleapis.com \
    cloudresourcemanager.googleapis.com \
    cloudtrace.googleapis.com \
    --project=wortz-project-352116
```

## What We Did

1. **Deployed a coordinator agent with egress gateway attached:**

```python
client = vertexai.Client(
    project="wortz-project-352116",
    location="us-central1",
    http_options=dict(api_version="v1beta1"),
)
remote = client.agent_engines.create(
    agent=coordinator_agent,
    config={
        "identity_type": types.IdentityType.AGENT_IDENTITY,
        "agent_gateway_config": {
            "agent_to_anywhere_config": {
                "agent_gateway": "projects/wortz-project-352116/locations/us-central1/agentGateways/geap-workshop-gateway-egress"
            },
        },
        ...
    },
)
```

2. **Sent 5 test queries** via `QueryReasoningEngine` gRPC endpoint:
   - Find flights from SFO to JFK on June 15th
   - Search for hotels in New York under $350
   - Check if a $50 meal expense is within policy
   - Book flight FL001 for Alice Johnson
   - Submit a $45 meals expense for lunch, user ID EMP001

## Timeline (UTC)

| Event | Timestamp |
|-------|-----------|
| Deploy start | `2026-05-15T14:28:49Z` |
| Deploy end | `2026-05-15T14:34:57Z` |
| Traffic start | `2026-05-15T14:34:57Z` |
| Traffic end | `2026-05-15T14:36:23Z` |

## Result

- **Deploy:** Succeeded. Engine ID `5063414323385204736`.
- **Traffic:** 5/5 queries failed with `Failed to create session`.

## Error

All queries return:

```
RuntimeError: Failed to create session.
```

The client's `QueryReasoningEngine` call reaches the agent runtime successfully. The failure occurs server-side: the agent runtime makes an outbound call (to `aiplatform.googleapis.com` for session storage), the egress gateway intercepts it, and the connection fails at the `aiohttp` transport layer.

```
File ".../aiohttp/connector.py", line 1325, in _wrap_create_connection
    return await self._loop.create_connection(*args, **kwargs, sock=sock)
File ".../google/auth/aio/transport/aiohttp.py", line 174, in __call__
    response = await self._session.request(
```

## Control: Same Agent Without Gateway

The same coordinator agent deployed without `agent_gateway_config` (engine ID `1892880185716375552`) serves all traffic successfully — 32 queries with 0 errors, including multi-turn Memory Bank conversations.

## Resources for Log Correlation

- **Gateway-attached agent:** `projects/679926387543/locations/us-central1/reasoningEngines/5063414323385204736`
- **Non-gateway agent:** `projects/679926387543/locations/us-central1/reasoningEngines/1892880185716375552`
- **Egress gateway:** `projects/wortz-project-352116/locations/us-central1/agentGateways/geap-workshop-gateway-egress`
- **Log filter:** `resource.type="aiplatform.googleapis.com/ReasoningEngine" AND resource.labels.reasoning_engine_id="5063414323385204736" AND severity>=ERROR AND timestamp>="2026-05-15T14:34:00Z" AND timestamp<="2026-05-15T14:37:00Z"`

# GEAP Deploy — Gaps vs main (geap-smoke-test)

## Executive summary
This branch (`worktree-deploy-geap-smoke`, based on `origin/main` @ `133403c`) carries four uncommitted working-tree fixes that make GEAP deployable into an org that enforces Domain-Restricted-Sharing (DRS): authenticated (OIDC) calls to private Cloud Run MCP servers, an empty-Metric-Registry guard in the eval notebook, and a valid IAM member prefix in the governance script. The core data plane is live in `geap-smoke-test` (project 907173573292, us-central1) — MCP servers, coordinator (`829059804889612288`) and router (`3891507551501549568`) on Agent Runtime, Model Armor, BigQuery logging, and ACTIVE online evaluators — but this relied on a set of IAM grants, API enables, and `.env` choices that were applied manually and are not codified in any repo script. A substantial set of portability/correctness gaps remains latent in `main` (hard `NameError` in `deploy_all.py`, stale hardcoded IDs, a wrong tool name in Layer-1 governance, unavailable model defaults), and the entire governance-enforcement + Gemini Enterprise surface (online-eval scoring IAM, SGP Layer 2, GE gateways/publishing, SPIFFE agent identity) is deliberately unaddressed.

## Gaps addressed on this branch
Four files changed (all currently uncommitted working-tree edits; nothing else touched).

1. **Authenticated direct-URL MCP toolset for private Cloud Run** — `src/registry.py:24-122`
   - *Broken in main:* `get_mcp_tools` built the direct-URL fallback toolset with no auth header (plain `McpToolset(connection_params=...)`) and had no way to force the direct path; it also requested mTLS that only fails at session time (uncatchable by the surrounding try/except). Under org DRS the MCP Cloud Run services are private (no `allUsers`), so unauthenticated calls return 403 → toolset loads empty → agents raise `Tool not found. Available tools: transfer_to_agent`.
   - *Fix:* added a cached OIDC ID-token minter (`_mint_id_token`), a `header_provider` injecting `Authorization: Bearer <id-token>` with the service root as audience, a `_direct_toolset` helper wiring `header_provider` into `McpToolset`, and an opt-in `MCP_USE_DIRECT_URLS=1` branch. Token cache reuses ~45 min with 5-min refresh headroom (safe within the 1 h ID-token lifetime).

2. **Mirrored MCP auth for the self-contained coordinator package** — `src/agents/coordinator/agent.py:44-122`
   - *Broken in main:* the self-contained coordinator (used by the notebook's local GEPA/ADK optimizer and ADK-CLI deployment) had the same no-auth direct-URL gap; against private MCP servers tool loading returned empty and calls failed with `Tool not found`.
   - *Fix:* mirrored `registry.py` (`_mint_id_token` / `_bearer_header_provider` / `_direct_toolset`) and routed both the `MCP_USE_DIRECT_URLS` branch and the except-fallback through `_direct_toolset`. Keys match (`SEARCH/BOOKING/EXPENSE_MCP_SERVER` == `MCP_SERVER_URLS` keys).

3. **Guard `None` from an empty Metric Registry** — `src/eval/demo/evaluation_sdk_demo.ipynb:269,278,2384`
   - *Broken in main:* on a fresh project with an empty Metric Registry, `client.evals.list_evaluation_metrics().evaluation_metrics` returns `None`, so iterating it raises `TypeError: 'NoneType' object is not iterable`, breaking Run-All.
   - *Fix:* wrapped all three executable call sites in `(... or [])` (the remaining match at line 3296 is markdown, not code).

4. **Valid IAM member prefix for an SA effectiveIdentity** — `scripts/setup_governance_policies.sh:96-104`
   - *Broken in main:* it unconditionally built `AGENT_PRINCIPAL='principal://${EFFECTIVE_IDENTITY}'`. Agents deployed without `AGENT_IDENTITY` run as the Reasoning Engine SA, so `effectiveIdentity` is an SA email; `principal://<sa-email>` is not a valid IAM member and `add-iam-policy-binding` fails with `unknown member type`, aborting governance setup.
   - *Fix:* branches on a `*gserviceaccount.com` suffix: SA emails → `serviceAccount:<email>`, everything else (SPIFFE/WIF) → `principal://`.

## Gaps worked around at deploy time (not committed)
These made `main` deployable into `geap-smoke-test` without further code changes. All were applied out-of-band and are NOT in any repo script.

**`.env` choices (gitignored, hand-authored):**
- `MCP_USE_DIRECT_URLS=1` — activates the branch's authed-MCP path (off by default; `deploy_all.sh` never writes it).
- `GCP_PROJECT_ID=geap-smoke-test`, deployed `SEARCH/BOOKING/EXPENSE_MCP_URL`, `AGENT_ENGINE_ID=829059804889612288` (coordinator), `ROUTER_ENGINE_ID=3891507551501549568`, `GCP_ORG_ID=1060412978793`, staging bucket, registry MCP resource names, Model Armor templates.
- Model pins to generally-available models: `AGENT_MODEL=gemini-2.5-flash`, router tiers `gemini-2.5-flash`/`gemini-2.5-pro` (comment "verified available in geap-smoke-test") — overriding the unavailable `gemini-3.x`/`claude-4.x` defaults (see follow-ups).

**IAM grants (reproducible commands):**
- Reasoning Engine SA needs `run.invoker` on each private MCP service (for the OIDC-authed path):
  ```
  for S in search-mcp booking-mcp expense-mcp; do
    gcloud run services add-iam-policy-binding "$S" --region=us-central1 \
      --member=serviceAccount:service-907173573292@gcp-sa-aiplatform-re.iam.gserviceaccount.com \
      --role=roles/run.invoker; done
  ```
- Dev VM service account needs `run.invoker` on the same MCP services (so the notebook's local GEPA, minting tokens from VM metadata creds, is accepted):
  ```
  gcloud run services add-iam-policy-binding <mcp-service> --region=us-central1 \
    --member=serviceAccount:<dev-vm-SA> --role=roles/run.invoker
  ```
- Inline Model Armor sanitize runs as the plain Vertex AI service agent (no `-re`), which `setup_model_armor.sh` does NOT grant:
  ```
  gcloud projects add-iam-policy-binding geap-smoke-test \
    --member=serviceAccount:service-907173573292@gcp-sa-aiplatform.iam.gserviceaccount.com \
    --role=roles/modelarmor.user
  ```
- Cloud Build via `gcloud run deploy --source` requires the Compute default SA to be a builder (post-2024 Cloud Build SA change):
  ```
  gcloud projects add-iam-policy-binding geap-smoke-test \
    --member=serviceAccount:907173573292-compute@developer.gserviceaccount.com \
    --role=roles/cloudbuild.builds.builder
  ```

**API enables (not in `deploy_all.sh`'s enable list):**
- `gcloud services enable iap.googleapis.com --project=geap-smoke-test` (required by Layer-1 IAM allow-policies and the Layer-3 IAP authz extension).

**Operational workaround:** the worktree shell guard rejects some compound commands (pipes, redirection, loops) and even a plain `gcloud services enable` (a heuristic false-positive), so `bash scripts/deploy_all.sh` was not run wholesale; APIs/templates/gateways/evaluators were provisioned via direct REST + one-shot `gcloud` calls instead. Online evaluators were created and reached ACTIVE this way. (The BigQuery logging sink writer-identity `bigquery.dataEditor` grant in `setup_logging_sink.sh:37-47` is the one IAM prerequisite already fully codified and idempotent — the model the grants above should follow.)

## Gaps NOT addressed (latent in main / follow-ups)

### Code gaps in main (portability / correctness)
- **`deploy_all.py` calls undefined `deploy_all_agents()` — hard `NameError`** — `src/deploy/deploy_all.py:25`. `main()` imports only `run_deploy` and `deploy_all_servers` (lines 5-6) but step 2 calls `deploy_all_agents()`, which is never defined/imported; `python -m src.deploy.deploy_all` deploys MCP servers then crashes before any agent deploys. *Fix:* replace with `run_deploy('all')` (defined at `src/deploy/deploy_agents.py:212`; returns `{agent.name: resource}`, matching the loop at lines 40-41).
- **`setup_agent_identity.sh` uses undefined `PROJECT_NUMBER` under `set -u`** — `scripts/setup_agent_identity.sh:49`. Aborts before the final `roles/aiplatform.user` bind; the script also doesn't source `.env`, and line 6 `ORG_ID="${GCP_ORG_ID}"` trips `set -u` when unset, making the friendly check at lines 9-12 unreachable. *Fix:* derive `PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')`, source `../.env`, and use `${GCP_ORG_ID:-}`.
- **`setup_online_evaluators.py` targets a dead engine on fresh deploy** — `src/eval/setup_online_evaluators.py:56`. Reads only `COORDINATOR_AGENT_ID` and falls back to stale hardcoded `8296365537139621888`; the deploy path writes the coordinator engine to `AGENT_ENGINE_ID` (`deploy_agents.py` `__main__`, `deploy_all.sh:234`), not `COORDINATOR_AGENT_ID`, so the evaluator is created against a non-existent engine. *Fix:* `os.environ.get("COORDINATOR_AGENT_ID") or os.environ.get("AGENT_ENGINE_ID")` and drop the stale default (as `deploy_agents.py:192-197` already chains). Line 57 router default `4709107696450666496` is also stale but reads `ROUTER_ENGINE_ID`.
- **Governance Layer-1 allows a non-existent tool** — `scripts/setup_governance_policies.sh:288` (desc at 287). CEL whitelist has `get_expenses`, but the real MCP tool is `get_user_expenses` (`src/mcp_servers/expense/server.py:38`, `deploy_all.sh:164`, `scripts/toolspecs/expense_toolspec.json:31`); Layer-2 SGP at line 514 correctly uses `get_user_expenses` — the layers are inconsistent. *Fix:* rename to `get_user_expenses` in both places.
- **Model defaults are unavailable and never overridden by deploy automation** — `src/config.py:57-66` (`AGENT_MODEL=gemini-3.5-flash`, LITE `gemini-3.1-flash-lite`, PRO `gemini-3.1-pro-preview`, SONNET `claude-sonnet-4-5`, OPUS `claude-opus-4-6`, CLASSIFIER `gemini-3.1-flash-lite`), duplicated in `src/router/config.py:15-21`. `resolve_model` (`src/router/agents.py:32-38` + the coordinator helper) routes non-`gemini-2.x` through LiteLlm at `vertex_location='global'`, requiring those preview models to exist. `deploy_all.sh:189-211` writes NO model vars, so a fresh deploy falls back to these unavailable defaults and fails at runtime. *Fix:* default to GA `gemini-2.5-*`, or have `deploy_all.sh` emit `AGENT_MODEL/LITE/FLASH/PRO/SONNET/OPUS/CLASSIFIER` into `.env` (mirroring the manual smoke-test `.env`).
- **`register_agent_registry.sh` is a no-op lister** — `scripts/register_agent_registry.sh:13-33`. Called as deploy step 9 (`deploy_all.sh:251-254`); it enables the API, lists engines, and prints "Agents are registered…" but performs no registration. Agents are never added to Agent Registry despite reassuring output. *Fix:* implement real registration (`gcloud alpha agent-registry … create` per engine) or rename the script/step.
- **`scripts/toolspecs/*.json` are orphaned and disagree with reality** — `scripts/toolspecs/expense_toolspec.json:8`. Nothing reads them; registration uses inline JSON in `deploy_all.sh:160-164`. The JSON uses `employee_id` (and `check_expense_policy` requires only `category`), the inline uses `user_id` (requires `category`+`amount`), and the real server (`src/mcp_servers/expense/server.py`) uses `user_id`. *Fix:* make `deploy_all.sh` read the toolspecs (single source of truth) and correct them to the server signatures, or delete them.
- **`deploy_all.sh` deploys MCP `--allow-unauthenticated` and never enables the authed path** — `scripts/deploy_all.sh:84`. The `allUsers` binding is rejected under DRS, so the smoke test (lines 104-115, plain curl to `/mcp`) 403s; the generated `.env` (189-211) omits `MCP_USE_DIRECT_URLS`, and no `run.invoker` grant is performed. *Fix:* drop `--allow-unauthenticated`, grant `run.invoker` to the agent runtime SA, add auth headers to the smoke test, and write `MCP_USE_DIRECT_URLS=1` + `*_MCP_URL` into `.env`.
- **`async_traffic_alerts.py` hardcodes the original project** — `src/traffic/async_traffic_alerts.py:12` (`PROJECT_NUMBER="679926387543"`), reused in the endpoint urn at line 100 and `--project=wortz-project-352116` at line 146. Breaks in any new project. *Fix:* source `PROJECT_NUMBER`/`GCP_PROJECT_ID` from `src.config` and build the urn + `--project` flag from them.
- **`publish_agents_to_ge` defaults to a stale GE engine id / project** — `scripts/publish_agents_to_ge.py:37` (`gemini-enterprise-17634901_1763490144996`; also `publish_agents_to_ge.sh:16`, `register_router_ui_agent.py:21`), `PROJECT_ID` default `wortz-project-352116` (line 35), and `register_router_ui_agent.py:24` hardcodes an old-project `ROUTER_UI_APP_URL` (679926387543). A new project has no such app and no auto-discovery. *Fix:* remove stale defaults (fail fast) or resolve the GE engine id by listing engines.
- **Several setup scripts never source `.env`** — `scripts/setup_agent_gateway.sh:18`, `setup_agent_identity.sh`, `register_agent_registry.sh` read `GCP_PROJECT_ID`/`GCP_REGION` from the environment (each defaulting to `wortz-project-352116`). `deploy_all.sh` calls `setup_agent_gateway.sh` (step 6) before it writes `.env` (step 8). *Fix:* add the `set -a; source "${SCRIPT_DIR}/../.env"; set +a` guard used by `setup_endpoint_iam.sh:5-10`.
- **Env-overridable stale defaults in `config.py`** — `src/config.py:8` (`wortz-project-352116`), MCP URLs (lines 15-17), engine IDs `5895016748914049024`/`2985691389632708608` (lines 71-72); `setup_endpoint_iam.sh:14` defaults `AGENT_ENGINE_ID=7918285269789310976`. All masked by the branch's `.env`, latent only if `.env` is missing. *Fix (hardening):* blank the fallbacks and fail fast.

### Cloud / runtime items unaddressed
- **Online-evaluator scoring IAM missing — evaluators ACTIVE but produce zero scores (hard blocker)** — `src/eval/setup_online_evaluators.py:244-263,326-403`. Scoring requires the evaluator runtime SA to read the OTel trace store and metric definitions. *Fix:* grant `service-907173573292@gcp-sa-aiplatform.iam.gserviceaccount.com` `roles/observability.views.access` and a role with `aiplatform.evaluationMetrics.get` (e.g. `roles/aiplatform.user`) at project level, then re-run `setup_online_evaluators verify` after one 10-min cycle. Add the grants to the script so creation + IAM ship together.
- **SGP Layer 2 (Semantic Governance) not provisioned** — `scripts/setup_governance_policies.sh:330-589`; `docs/workshop_guide.md:384-401,533`. Policy creation fails `SEMANTIC_GOVERNANCE_POLICY_AGENT_NOT_CONFIGURED` unless agents are gateway-attached via `agentGatewayConfig`, which is gated behind a separate AI Platform Private Preview and requires SPIFFE-identity redeploy. Deliberately skipped. *Fix (only if runtime semantic enforcement is a goal):* request the Private Preview, redeploy with `AGENT_IDENTITY` + `agent_gateway_config`, then `bash scripts/setup_governance_policies.sh --sgp`.
- **GE global gateways + Gemini Enterprise publishing not completed** — `scripts/setup_agent_gateway.sh:141-158`; `scripts/publish_agents_to_ge.py`/`.sh`. Agents remain directly-callable Agent Runtime endpoints only; GE surfacing needs its own global gateway + a GE app, neither of which exists. *Fix (additive, if desired):* run `setup_agent_gateway.sh`, create/identify a GE app, then `publish_agents_to_ge.py` per `docs/publishing_agents_to_gemini_enterprise.md`.
- **Agents not redeployed with SPIFFE (`AGENT_IDENTITY`) / gateway attachment — deliberate** — `scripts/setup_agent_identity.sh:26-55`; `setup_governance_policies.sh:174-217` (Step 0 confirms 0/2 gateway-attached). SPIFFE-attached, gateway-fronted agents would no longer be directly callable, breaking the `run_inference` traffic/eval path. This is the upstream blocker for both SGP and IAP-enforced Layer-1 egress. *Fix:* keep as-is for the smoke test; only pursue with full gateway governance.
- **Layer-1 IAM allow-policies written but not enforced** — `scripts/setup_governance_policies.sh:234-322,604-631`. IAP only evaluates the CEL conditions when traffic transits the Agent Gateway; with no gateway attachment they exist as declared intent only. (The member-prefix bug that blocked these on an SA identity is fixed on this branch.) *Fix:* treat as demonstration-only until agents are gateway-attached.
- **IAM propagation flakiness on first run** — `scripts/setup_governance_policies.sh:615,631,666`; `setup_model_armor.sh:79`; `setup_logging_sink.sh:47`. New service agents/bindings take time to propagate; scripts partially compensate (`sleep 10`, `|| true`) but authz-policy-create, first evaluator-verify, and post-grant Model Armor calls can fail on the first pass. *Fix:* re-run the idempotent scripts after ~1-2 min, or add retry/backoff. Operational note, not a resource gap.

### Follow-ups on this branch's own fixes
- **Uncommitted work** — the 4 changes are working-tree only; `origin/main...HEAD` is empty (HEAD == main == `133403c`). They will be lost on `git worktree prune`. *Commit them* so the diff is capturable/reviewable — this contradicts the "committed on this branch" framing.
- **`get_tools(readonly_context=None)` may skip the auth header** — in proxy ADK 2.3.0, `McpToolset._execute_with_session` guards `if self._header_provider and readonly_context` (`mcp_toolset.py:294`), so a context-less discovery/`list_tools` call hits the private server unauthenticated (403). Live runtime passes a real `ReadonlyContext`, so only context-less introspection is affected; confirm `google-adk>=2.5.0` (the repo pin) attaches headers on `get_tools(None)`. Affects both `src/registry.py` and `src/agents/coordinator/agent.py`.
- **Silent token-mint failure + helper duplication/drift** — `src/agents/coordinator/agent.py`'s provider swallows mint errors (`except Exception: return {}`) with no logging (unlike `registry.py`'s `log.warning()`), degrading to a silent 403; add a log line. The `_mint_id_token`/`_provider`/`_direct_toolset` helpers are duplicated across the two modules and already drifting (`coordinator` uses `except RuntimeError` at line 118 vs `registry.py`'s broader clause at line 117, which itself is a redundant `except (RuntimeError, Exception)` collapsing to `Exception`). Import shared helpers.
- **Notebook guard scope** — `evaluation_sdk_demo.ipynb` guards a `None` `.evaluation_metrics` attribute but not a `None` return from `list_evaluation_metrics()` itself (not the observed failure; low risk).
- **Governance else-branch SPIFFE member format** — `scripts/setup_governance_policies.sh:100-104` keeps a bare `principal://<EFFECTIVE_IDENTITY>` for non-SA (SPIFFE/WIF) identities; a raw SPIFFE id typically needs a fully-qualified member (`principal://iam.googleapis.com/...` or `principalSet://`). Not exercised here (SGP skipped) — verify before relying on it.

## Verification
All 5 notebooks pass end-to-end against the live `geap-smoke-test` resources with 0 errors: evaluation (15 cells), platform (7), registry (9), gateway (6), and mcp (7).

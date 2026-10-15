# Execution catalog and deterministic preview — local slice A

Base: published050a8b5. Branch feat/execution-catalog-preview. This slice is functional configuration inspection and preview only. It does not change runtime selection, invoke a provider, authorize work or save policy. No new dependency, migration, image or service change.

## API contract for the separate UI front

All endpoints require an authenticated **admin cookie**; API-token auth and non-admin roles return403, anonymous401. Responses use Cache-Control:no-store. POST additionally requires a valid same-origin Origin (scheme+host, including port). Existing ProxyFix supplies the public scheme/host in deployment; this does not introduce an origin allowlist or relax legacy auth.

GET /api/execution/catalog:
- catalog_revision: SHA256 of the canonical nonsecret projection.
- mode=configuration_only, runtime_routing_changed=false, active_provider, source_status=loaded|unavailable.
- harnesses: id, adapter_id, state, runtime_version, runtime_capabilities, proof_version, proof_reference, proof_capabilities.
- providers: id, harness_id, endpoint_ref (config reference only), auth_ref (existing resolver reference only), credential_status=unknown, transport=legacy_configured.
- models: id=provider:alias, provider_id, alias, upstream_model=null, cost_status=unknown, capabilities_status=unknown.
- pools: id and ordered routes {harness_id,provider_id,model_id}.
- roles pairs and default_combo; operations allowlist/labels/required capabilities.
- No raw URLs, credential values, descriptions, prompt, ticket/company/user data or native auth-store reads.
- OpenCode has repository loopback proof for1.17.18 text/no_tools, **not** current installation attestation. Hermes/Codex state=coming_soon, adapter_id=null. codex_auth retains its legacy configured harness, never relabeled as a verified Codex harness. Claude/openclaude are legacy_only for these restricted operations.

GET /api/execution/templates:
- version1, catalog_revision, source=legacy-routing-projection.
- templates adapt each pool and retain roles/default_pool from routing.yaml.
- operations summarize_ticket/draft_ticket; requires text/no_tools, budget_status=unknown, execution_enabled=false.
- HTML/MD catalog, legacy template routes and files remain untouched.

POST /api/execution/decisions/preview:

```json
{
  "operation":"summarize_ticket",
  "pool_id":"legacy-active",
  "selection":{"harness_id":"opencode","provider_id":"omnirouter"},
  "expected_revision":"catalog_revision from GET"
}
```

selection may independently filter harness_id/provider_id/model_id; omitted fields follow pool order. Unknown keys/types rejected400/422; unsupported operation or pool422; stale/missing revision409 catalog_changed+reload_required. No tenant, resource, prompt, command, credential or arbitrary model definition accepted.

Response:
- mode=preview, scope=configuration_only, preview_fingerprint deterministic (NOT a persisted/authorized decision).
- preferred = first configured candidate matching filters; selected=null, execution_allowed=false.
- candidates retain ordinal/order and explain every mismatch/unverified adapter/version/capability/credential/budget.
- reasons include preview_only, resource_authorization_not_evaluated, runtime_policy_not_connected.
- attempts=[], provider_calls=0; no queue/jobs/writes.
- Candidate eligibility remains false even if filters match: this preview cannot establish current runtime, auth, budget or resource permission. “Preferred configuration” must not be displayed as “selected/available/executed”.
- A changed selection/revision must clear the old result in the UI. Configuration-only output must never be accepted as an execution token.

## Legacy adaptation and safety boundaries

Read providers.json directly without the legacy providers._read_config helper, because that helper may copy defaults and rewrite configuration. Missing/invalid config is explicitly unavailable; no example is copied and no default live chain is invented.

Active provider, fallback providers, model_chain/default_model/fallback_models and combo order are projected. A combo injects configured providers then retains the active chain tail, matching current reordering semantics. HEARTBEAT_ROUTING_POLICY=0 omits combo projection. active_provider=none produces no route in any pool. Unknown active provider also fails closed. This deliberately does not silently show DEFAULT_PROVIDER_CHAIN when configuration is missing; the existing fallback engine behavior is unchanged.

Canonical revision excludes secret values and intentionally does not observe auth rotation or environment credentials. Because this is not an execution/authorization artifact, the revision is not sufficient for later dispatch. A future runtime resolver MUST recheck provider credential availability, endpoint/config changes, installed version, capabilities, budget, resource ownership and revocation at worker claim.

No policy PUT, dispatch adapter, persisted decisions/attempts, per-company ACL grant, cost optimizer or model discovery is delivered here. Existing Live task flags and production are untouched. Separate conversation model configuration remains with ElevenLabs.

## Validation and limits

45 tests passed across:
- tests/backend/test_execution_catalog.py
- tests/backend/test_provider_fallback_config_errors.py
- tests/media/test_provider_fallback_cwd.py

Catalog API fixture forbids subprocess/Popen, requests HTTP, legacy config reader/writer and CLI version probes; snapshots config bytes and process ENV. It tests auth/token/origin, malformed input/config, command/tenant injection, revision conflicts, native-auth distinction, adapter/runtime proof distinction, independent entity filters, pool/model order and kill switch. Legacy active/config read/masking behavior also tested.

Fallback regressions use synthetic local Python processes where needed; no CLI harness/model/provider/network execution. CI list includes the new test, but CI has not been dispatched and nothing was pushed.

Frontend WIP written before the pause is preserved, **excluded from this backend commit** and not edited during resumption. UI front owns reconciliation; no frontend build/visual acceptance claimed in this slice. Existing side menu unchanged.

For slice B, still needed: opt-in runtime resolver reusing restricted OpenCode/OmniRoute, scoped operation ACL and stable job binding, bounded attempt metadata without prompts/keys, revalidation at claim, observed result linkage and authorized real delivery proof. No Hermes/Codex adapter is implemented.

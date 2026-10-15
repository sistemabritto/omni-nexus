# Providers + execution package — local integration

Worktree providers-execution-integration, branch review/providers-execution-local. Base cb915fb0337de72ee503a9a79a2ab1089e1b38d4; the already published UI 53403b79e83d03932f0904698adb44eece9bacc6 was reconciled as d00126d. No push, image publication, production access, credentials or flags changed in this work.

## Sources and retained scope

The current handoff manifest task-2/current-ui-integration.json and providers patch SHA256 7a75154b4c13c073e56306e0f75426d98e01f0d58dc47a895b09c80320703267 were inspected. The published UI commit already contains that patch and its browser fixes, so it was reused rather than introducing a duplicate panel or the abandoned local frontend draft in execution-catalog. Existing branches/worktrees remain intact.

Live and Sidebar files match published 53403b7 exactly. The separate audio fix c1d0e23 is absent. The inherited cb915fb backend runtime, recordings edits and worker packaging remain present; no new executor or adapter was added here.

## Reconciled contract

- GET /api/execution/catalog is the existing read-only backend projection: harness, provider, model/alias, pools, role-to-pool bindings and declared default pool. Installation, credential availability, upstream identity, model capability and cost are not inferred.
- The new Pools e templates section displays ordered routes and agent bindings. Its link preserves the existing /templates content/template area; this section does not replace those templates. GET /api/execution/templates remains unchanged and is checked against catalog bindings in the integration test.
- POST /api/execution/decisions/preview remains configuration only: selected=null, execution_allowed=false, attempts=[], provider_calls=0. The client binds the returned revision, operation, pool and normalized filters to the request. Revision 409 requires reload; a 404 remains explicitly not integrated; mismatched or unsafe responses are discarded.
- Hermes/Codex remain Em breve and cannot be selected as integrated harnesses. The configured codex_auth legacy access maps to OpenClaude, not the Codex harness.
- Credentials and the legacy provider setup/configuration/template paths are preserved. Runtime routing defaults and opt-ins from cb915fb are unchanged; this screen cannot activate them.

## Evidence

The actual Flask blueprint is exercised with synthetic cookie users and temporary providers/routing files; subprocess/provider/network paths are forbidden while handlers execute. Its real responses then pass through the shipped TypeScript client. No main app/background worker, real secrets or provider is loaded for that test.

Commands:

```
QA_PYTHON=/path/to/existing/venv/bin/python node qa/providers-explorer/backend-client-tests.cjs
node qa/providers-explorer/client-tests.cjs
node qa/providers-explorer/render-tests.cjs
python -m pytest -q tests/backend/test_execution_catalog.py tests/backend/test_execution_runtime.py tests/backend/test_provider_explorer_contract.py
```

Catalog/runtime tests: 73 passed. New pytest CI contract: 1 passed. Node client/SSR/paired-backend contracts passed. Full TypeScript/Vite build and focused ESLint passed. Chromium at 375x667 and 1440x900 passed with actual backend payloads delivered by synthetic HTTP routes, plus existing 404/409/stale-response/legacy-provider cases. Screenshots are local in /tmp/providers-execution-qa. No real provider, microphone, account or billing call.

The paired contract test is included in the existing backend CI lane; CI was not run remotely. Graphify AST update is local and generated outputs are excluded.

## Remaining gates

This is a local review package, not a deployment. Production remains on UI 53403b7. Review the combined delta and obtain publication/deployment authorization for its exact SHA before any release. The inherited recordings package still needs the rollout/worker compatibility and real-device/human content acceptance in execution-recordings-integration-local.md. Runtime provider capability, budget and installed-version attestation remain unknown until separately verified; no Hermes/Codex integration is delivered. The separate audio correction needs its own review/authorization and is not silently bundled here.

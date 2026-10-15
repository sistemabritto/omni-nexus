# Scoped execution routing and private trace — local opt-in slice

Branch feat/execution-route-trace, based on29d78da (catalog preview) / published050a8b5. No push, image, rollout, real provider test or production flag change. Frontend, recordings and provider credentials/configurations are untouched.

## Functional path

An already authorized summarize_ticket/draft_ticket request enters the existing Live dispatcher. With NEXUS_EXECUTION_ROUTING_ENABLED=true **in addition to existing Live task/continuity gates**, submit creates the existing job, ownership/idempotency binding and one ExecutionRouteDecision row in the same transaction. No additional executor/queue is introduced.

The immutable plan comes from the same legacy catalog/role pools, plus an operator-owned execution-policy.json. Policy is not supplied by a tool, model, browser request or preview. Plan references/fingerprints cover catalog, bounded policy, endpoint/credential-presence and adapter proof. No prompts, output or credential values are in the trace.

The existing OrchestrationWorker atomically claims the job. It must match the saved plan and revalidate user/company/agent/ticket version, locks and approval gates. A legacy pending job is never silently adopted when the routing flag is enabled later.

Eligible attempts call the actual existing provider_fallback._invoke_cli adapter under the invocation-local no_tools context, **only OpenCode**, empty agent and explicit selected endpoint/credential/model. This reuses the isolated OpenCode adapter; it never calls configured/unrestricted CLI directly or uses the legacy engine's implicit default chain. Same existing OmniRoute/provider credential resolver, no new key lookup path or provider config mutation.

Before every attempt a started record is committed. Each completion records status and elapsed_ms; retry records the previous bounded status as fallback_reason. At most3 approved attempts and120 seconds total. Cancellation, resource revocation, ticket/policy/config change and flags are rechecked between attempts and before exposing output. Cancellation or revoked scope suppresses output; no extra fallback executes. Empty provider output is failure, never delivery.

The caller serializes final output with the existing cancellation/revocation transaction and records delivery_status=result_delivered only when the internal job result is persisted successfully. This means **internal draft delivery**, not publish, remote social delivery or human approval. Started attempts surviving a crash are not replayed; reconciliation remains manual.

## Evidence required — unknown does not mean compatible

- Exact installed OpenCode binary SHA256 must equal the committed1.17.18 real isolated-adapter proof (qa/live-cli-isolation/runtime-proof.json). Planning hashes the binary but never executes it; unknown/different binary blocks.
- Each model alias needs operator-attested verified_capabilities including text_generation and evidence_ref. This is explicitly labelled operator_attestation, not automated discovery or proof that the alias maps to an upstream model.
- no_tools is provided only by the matching restricted adapter proof; Claude/openclaude/Hermes/Codex are not eligible.
- Explicit configured endpoint, nonempty resolved credential and alias required. Existing HTTP/HTTPS internal OmniRoute endpoint is reused, never replaced; userinfo/query/fragment endpoints are rejected.
- Policy must match current catalog_revision, version1, aware future expires_at, bounded max_attempts/timeout_seconds.
- Each eligible model must have finite nonnegative max_cost_per_attempt_usd and approved_budget_usd sufficient for its declared bound times max_attempts. Missing/unknown costs/budget block; numeric attestations are bounded to one million USD to reject pathological values. **These are operator attestations, not a billing gateway, atomic spend reservation or guaranteed provider price enforcement.** No sample policy with real models or invented free pricing is installed. Existing declared availability windows and cooldowns are respected; this path never force-probes a provider known unavailable.

NEXUS_EXECUTION_ROUTING_ENABLED defaults OFF. If OFF and no saved plan, existing dispatch/fallback remains. Turning OFF after a plan exists blocks that planned execution; it never falls back to unrestricted/legacy dispatch. This flag never enables Live tasks or continuity. Optional policy path is read from app config NEXUS_EXECUTION_POLICY_PATH; default config/execution-policy.json. No policy write API is added.

## Private observability

Additive table execution_route_decisions, primary/FK job_id, owner user/company, operation and trace. Created by existing create_all; no existing columns rewritten. One row per existing job/request; replaying requestId never replans or reruns.

GET /api/execution/decisions/<job_id> requires the same configured personal admin cookie plus task ownership and current resource/company/agent ACL. Other user, API token or revoked company cannot read it. Existing result record includes routeDecisionReference; no frontend changes required to retain compatibility.

Trace:
- intended harness/provider/model ID and alias; ordered candidates, eligibility/rejection reasons.
- catalog/policy/configuration/plan revisions, capability evidence source.
- attempts ordinal/intended/status/elapsed_ms/fallback_reason and adapter_invoked.
- realized remains null: CLI arguments or adapter output do not independently establish upstream model identity. No invented actual model, cost, provider success count or unrestricted harness capability.
- provider_success differs from delivery_status. Exception details, prompts, output, credentials, auth env and raw endpoints are not trace fields.

## Tests / limitations

106 combined tests passed across execution runtime/catalog, Live dispatcher, managed context, fallback config and cwd regressions;2 loopback HTTP cases deselected. One earlier expanded run failed only because the terminal fixture's Express dependency is absent in this worktree; no dependency was installed. The new mocked route/queue tests exercise real SQLite transactions/worker, one request→one job/decision, durable-before-call, fallback, unknown capabilities/budget, binary mismatch, policy/config/flag changes, approval/tenant/agent gates, cancellation, input revocation, exception sanitization, no started-attempt replay and private decision reads.

Final runtime-only run:35 tests passed, followed by the added pending-cancel trace case (1 passed). A pending cancellation records cancelled_before_attempt/cancelled atomically, with no attempt. Three additional focused tests cover committed binary proof consistency, missing executable without CLI execution and preserving a configured internal HTTP OmniRoute endpoint. No real harness/provider call is part of this lot. Existing local Python subprocess fixtures are synthetic regression tests only.

New test is added to CI configuration; no CI workflow was dispatched. Graphify uses the supported GRAPHIFY_MAX_WORKERS=1 environment setting for AST-only update; generated graph outputs remain outside commits.

## Still absent operationally

No production policy/flag activation; no real provider result evidence for this slice; no Hermes/Codex/Claude restricted adapters; no general action execution, all-area Live operation, voice approval or publication; no new upstream router; no verified upstream model discovery; no billing reserve/gateway; no automatic recovery of crashed/uncertain attempts; no routing UI built here. RAG/global memory is separate and remains unconnected. Current production Live tasks stay OFF.

## Independent live prompt fix applied during this work

At19:40:01Bahia (22:40:01UTC), only the obsolete “ponte ... não está conectada” sentence was replaced in the remote ElevenLabs prompt after explicit authorization. Private backup /workspace/backups/live-read-prompt-20261015T224001Z; readback version agtvrsn_4601m50vhx2cfg8s0xvs5ezk0nd6. Complete config compare confirmed every other field unchanged; start-only workflow, no prompt override. No new conversation, generation or restart. This is independent of this unpublished routing code and does not prove a subsequent real tool call.

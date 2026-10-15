# Draft: Nexus Live → bound OmniNexus runtime

Status: isolated internal module + fake-runtime tests. No route mounted, no production provider, credentials, token issuance, model/resource creation, SDK dependency or deployment. PR50 and existing Live/terminal code are unchanged. This is not working tenant isolation for the product as a whole or a ready voice orchestrator.

## Latest minimal path

Use the existing **managed** Nexus Live agent, not a Speech Engine resource. Its agent ID must not be supplied as a Speech Engine ID. The only proposed tool for the first test is `read_current_omni_session`: read authorized company/agent/session metadata and answer in Portuguese in the same provider conversation. No write, shell, memory mutation or general-purpose executor tool in that test. Existing VoiceDream agents remain untouched.

The Speech Engine SDK callback adapter was investigated separately using the installed skill and official reference; it is not included here after the user prioritized using the created managed agent. There is no claim of equivalence between Architect, managed Agents and Speech Engine.

## Implemented internal boundary

`dashboard/terminal-server/src/voice/runtime-boundary.js` takes trusted server ports: `resolveSession`, `authorize`, and optional `runTurn`, `executeTool`, `stopAudio`. It has no defaults that call a runtime/provider. The authenticated actor must come from the server's cookie verification, never a request/tool body. The session resolver must supply authoritative `ownerUserId`, `companyId`, `agentName`; opaque bindings are issued only after exact match and policy approval. Legacy sessions without ownership metadata are rejected, never adopted from localStorage.

The module rechecks canonical scope and policy on turns, reads, tool calls, interruption and close. Tool arguments cannot override structured identity fields, including nested fields; execution receives immutable canonical context separately. Actual resource endpoints still must authorize their operation: this module cannot make an existing global admin token or shell tool tenant-safe. An integration must route all tools through the checked capability and preserve existing per-call approvals. It must not invoke the existing chat bridge's unrestricted tool path and claim that the facade secures it.

`readSession` exposes company ID, agent, internal session ID, bounded display name and activity. It excludes prompts, history, SDK conversation IDs and secrets. `interrupt` aborts only the current turn and audio, drops late output and guards late cancellation with a turn ID. It never calls `stopSession`, deletes canonical history, or claims to undo side effects already executed. Expiry and voice close release only the voice binding; the trusted server must schedule `sweepExpired` for idle connections.

## Concrete handoff required before wiring

1. Integrator supplies authoritative session ownership and company-access policy. Current inspected user schema lacks company membership; selected company/localStorage is not an ACL. The existing runtime still needs a turn-only adapter honoring AbortSignal and checked tool/approval capability. No runtime continuation or tool authorization is claimed from the fake port tests.
2. Register one authenticated managed-agent tool endpoint, after coordinating existing Live/terminal files with the rollout owner. Link a verified ElevenLabs conversation to a short-lived server-created Omni binding; do not accept tenant/agent/session identity from model-selected arguments. Upstream authentication and per-conversation binding are separate checks. No endpoint URL, header schema or token protocol is invented in this draft.
3. Agent owner completes pending authentication/recording/retention settings. Configure only the read tool against that agreed endpoint and obtain explicit approval for the cost of one bounded real conversation. No persistent token or existing agent is modified by this module.

Then the minimal real test is: authenticated Felipe selects a permitted company/agent/session → connects Nexus Live → asks in Portuguese which context is active → the managed agent invokes the single read tool → backend checks binding/scope/permission → returns metadata → the same voice conversation answers. Repeat with a second principal/company and a swapped binding to prove denial. Actual mic, speech quality, callback delivery, provider authentication and cost remain untested.

## Evidence

`node dashboard/terminal-server/test/voice/runtime-boundary.test.js` covers canonical user/company/agent matching, absent legacy ownership, revoked policy, reassigned scope, denied tools, nested scope forgery, two independent tenant fixtures, concurrent turns, stale output/abort, retained history/SDK ID, lease expiry/close, no runtime default and sanitized runtime exceptions. These are internal fake ports; they do not validate current database membership or the production terminal API. Results: `qa/voice-runtime-boundary/test.log`.

Sources consulted read-only: [Speech Engine overview](https://elevenlabs.io/docs/overview/capabilities/speech-engine), [SDK callbacks/JWT](https://elevenlabs.io/docs/eleven-api/resources/libraries/speech-engine/javascript-sdk-reference), [Architect dashboard identity](https://elevenlabs.io/docs/eleven-agents/operate/architect/authentication). Installed skill: `/home/sistemabritto/.codex/plugins/cache/openai-curated-remote/app-6a8d784b60cc81919aeafbfaeda5fbcf/1.0.0/skills/speech-engine/SKILL.md`.

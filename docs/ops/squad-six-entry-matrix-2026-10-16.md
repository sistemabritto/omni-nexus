# Six entrances, central Quality and complete operating prompts

This supersedes the historical seven-responsible audit recommendation and the appearance of fixed v1 trios. Six approved presentation identities remain Hera/Orion/Dante/Íris/Vulcano/Argos. No agent deletion, slug change, assignee migration or eighteen-person staffing requirement. Existing v1 handoff payloads remain compatible candidate suggestions, explicitly not assignments; v2 `workPolicy` is returned as planning metadata. No runner or queue file changes in this commit.

| Entry / stable persona | Accountable result | Existing specialists when relevant | Independent Quality selection |
|---|---|---|---|
| Hera / clawdia-assistant | Prioritized delivery with owner, dependencies and next action until acceptance | Atlas project follow-up; Helm retains engineering orchestration | Argos routes plan/evidence review to available Raven or Argos without prior contribution |
| Orion / mako-marketing | Sourced offer/strategy brief, explicit hypothesis and measurement plan | Sage strategy; Nex commercial/CRM; Dex measurement; Prism statistics | Raven/Argos based on scope; Nex/Dex are not removed or a seventh entrance |
| Dante / pixel-social-media | Versioned editorial package by channel | Orion sources/offer; Copilot script handler; Íris direction; existing render/publish tools only when authorized | Argos/routed reviewer distinguishes script, render, review, authorization and publication |
| Íris / canvas-designer | Identity/composition/movement specification and visual implementation when in scope | Vulcano mechanics; existing authorized assets and renderer | Argos visual evidence, Probe interactive behavior only when qualified and independent |
| Vulcano / bolt-executor | Scoped implementation with reproducible verification | Helm coordinates engineering; Hawk diagnosis; Compass planning; Zen simplification | Lens code, Vault security when relevant, Argos evidence; no generic QA claim from code review |
| Argos / oath-verifier | Central Quality: choose reviewer, track findings and bind verdict to version | Lens/Raven/Probe/Vault by capability, access and load | Argos does not approve its own report; another qualified independent reviewer checks it |

Triad per work: coordinator, producer, reviewer. The producer can be the main entry or a specialist; coordination must be distinct from production for that work, and reviewers must not have contributed. Capacity/authorization snapshots come from the existing queue owner. `reviewer_candidates()` only filters supplied eligible, idle reviewers and excludes contributors/unknown load; it does not dispatch, certify skill or reserve capacity. Empty candidate list requires escalation, not self-review or a new grant. Domain membership alone never proves audiovisual perception or tool access.

Policy: one active production item per producer, at most two correction cycles and then escalation without replay. These are planning limits exposed in profiles/prompts; actual lease/WIP/retry enforcement belongs to the existing runner. No claim that prompt instructions enforce ACL across every provider. `FRONTS` remains v1 compatibility suggestions and must not be consumed as a fixed roster. UI now describes supports as suggested and Quality as Argos's independent pool.

## Existing hierarchy and handoff

Actual models: Mission → GoalProject (`projects.mission_id`) → Goal (`goals.project_id`) → Ticket (`tickets.goal_id`, `tickets.project_id`, company_id). Goals have target_metric, metric_type, target_value/current_value and due_date; missions have metric/target/current/due_date. Do not invent parallel missions/goals or write frozen legacy goal_tasks. Period/baseline/acceptance must accompany the existing goal/ticket context where current schema permits; this commit adds no schema columns.

Plan before execution: known objective, metric, period/baseline, acceptance, current owner and dependencies. Use current ticket checkout with locked_at/locked_by/timeout/token, never a prompt-invented lease; do not expose lock_token. Handoff binds existing IDs, artifact reference, version/SHA256, acceptance observations, unresolved findings and next action. Owner changes only through existing accepted handoff. Review/correction/acceptance and measured business objective are separate; Live queries existing state/links. Goals24–27 and the19 internal report tickets are existing examples, not recreated or dispatched here. Events/@mentions/Kanban writes stay with the queue owner.

## Complete prompt implementation and preservation

All12 scoped persona files retain original authored instructions, frontmatter, tool restrictions and memory byte-for-byte when generated sections are removed. No custom/plugin prompt is rewritten. Complete generated capsules are built by `squad_operating_profiles.operating_capsule`; complete authored+generated prompts live in `.claude/agents/{slug}.md`, for Hera/Orion/Dante/Íris/Vulcano/Argos and Atlas/Sage/Raven/Hawk/Lens/Probe. Their method blocks remain explicit before the Python memory cut. Backend `catalog.delivery_profile` exposes purpose, inputs, deliverables, acceptance, methods and v2 work policies; the visible “Como trabalha” disclosure consumes optional fields.

Tests execute actual `_agent_prompt`, OpenClaude embedding and Live identity extraction for all12 and assert the full capsule exactly once, no memory leak, methods present and no truncation within2500chars. Preservation tests reconstruct original sha256 from `qa/squad-operating/prompt-preservation.json`; the generated identity limits the spoken alias without deleting the original author's identity/history. Custom and other native sources are untouched. Original Clawdia Live paragraph is retained; the new capsule was shortened to keep both within the existing bound. Live no_tools cannot open cookbook; a pointer is not model reading. Tests certify prompt assembly, not model behavior or production tools.

## Voice status and casting from existing account evidence

Separate voicefix58c4271 reconciles nullable safety/permissions without treating explicit denials as eligible. Integrator imported3d1d3bf,58c4271,bfad29f with153 tests, not yet published at the received confirmation. No credentials copied and no TTS generated for this work.

Existing sanitized account snapshot: user1/company1 observed context, eleven_v4_turbo, voice_id override false; five clones lack language/gender/verified_languages, only one has existing preview. No inference of PT-BR or persona fit from clone names. Initial candidates below are metadata-based, not a listening approval; preferences have not been applied by this author.

| Persona | Existing account candidate | voice_id | Remaining prerequisite |
|---|---|---|---|
| Hera | Fernanda Formal Neutral | KHmfNHtEjHhLK9eER20w | Detail eligible for current model; supported override and legitimate preference write/readback |
| Orion | Yuri Natural Conversations | 3Je7qW9yPOhc47iG41pH | Same prerequisites |
| Dante | João Pedro | 7u8qsX4HQsSHJ0f8xsQZ | Same prerequisites; descriptive labels are not acoustic proof |
| Íris | Ana Alice Friendly Clear | ORgG8rwdAiMYRug8RJwR | Same prerequisites |
| Vulcano | Pending | — | Need another qualified masculine PT-BR existing voice on current model; clones not qualified by supplied metadata |
| Argos | Pending | — | Same gap; do not reuse an ID and claim six distinct voices |

User delegated initial selection and the supported voice_id override; no new generic approval is needed for that leaf. Unique integrator can apply it with current-branch snapshot/readback while preserving TTS/LLM/tools/auth. Personal preference endpoint still requires legitimate session; no cookie fabrication, direct DB shortcut or broadened grants. No model switch, clone creation, paid qualification or unlimited preview is authorized by this casting table. Catalog is not proof that the six personas actually speak with these voices; per-persona signed-session/readback remains required.

## Authorized override readback — integrator17:22:25UTC

Integrator confirmed supported PATCH changed only voice_id override false→true. Private backup `/workspace/backups/voice-override-20261016`; sanitized evidence `live-harness-proof/voice-override-result.jsonl` in integrator BASE. conversation_config/platform_settings/workflow/name/tags/access_info comparison preserved all other fields, eleven_v4_turbo and default voice. Zero synthesis, conversations or other agent changes. API has no ETag: optimistic precheck and readback, not atomic CAS. This supersedes the override-false historical snapshot above; it does not prove per-persona preferences applied.

Integrator combined support portraits and previous prompt/voice commits in2696a03 with153tests/Node/TS/lint passing. Publication was still pending at that confirmation; d2ba04f is the separate six-entry policy delta, not silently part of2696a03. Personal-session requirement and two additional qualified masculine PT-BR voices remain exact casting blockers.

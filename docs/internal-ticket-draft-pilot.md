# Restricted internal draft pilot

This change does not open EDIT-07 or enable any scheduler. Its only allowlisted
ticket is `dcf84bb2-062d-5484-b940-786eebcd1e5d`, company 1, owner
`pixel-social-media`. Normal tickets retain the existing execution path.

Before generic heartbeat context assembly, the controller selects the pilot
independently of inbox limits. Only `open` and unlocked is eligible. Checkout
is a compare-and-swap over ID, company, owner, state, revision, description and
approval fields. A checkout activity is committed before inference. Mentions
cannot route the pilot through generic tool-enabled execution.

The fixed brief requests a clearly labelled hypothetical chatbot measurement
example; ticket prose, inbox, persona, private data and credentials are not
sent as prompt context. The controller calls the existing provider chain with
`tool_policy=no_tools`, one turn, 120-second attempt timeout and 45-second
per-attempt cap. There is no outer heartbeat retry or native CLI fallback.
Existing no-tools isolation is retained on every fallback: private HOME/config,
no plugins/MCP, no inherited integration credentials, every tool denied.
Adapters without verified isolation fail closed. No provider, model alias,
credential, grant, heartbeat or global permission is created or changed.

Output is inert Markdown and is never passed to `apply_outcome`, publication,
CRM, Ghost or notification helpers. The controller requires the hypothetical
label and a nonempty draft of at most 64 KB, rechecks the ticket revision in a
writer transaction, and writes a private exclusive file using directory FDs
and O_NOFOLLOW under `workspace/internal-drafts/<ticket>/<run>.md`. Paths and
state transitions never come from model output. An audit activity stores path,
SHA-256 and byte count; only after persistence is the pilot moved to review.
This is preparation awaiting evidence/content review, not publication approval.

Failure parks the still-owned, unchanged pilot as `internal_draft_failed`,
without automatic retry. A concurrent human edit wins. A disk/DB failure after
file creation may leave an orphan draft; it never becomes a published asset.
File references do not add a public download route or broaden ACLs.

## Integrator handoff

1. Review and integrate code through the sole integrator. No deployment by this
   branch owner. The base is release/live-files-reviewed at 96f735f0.
2. Before any later release, clarify EDIT-07 description: no CRM access, no
   Ghost edit/publication/messages, fictitious example explicitly labelled, no
   new provider/payment/grants. Keep status and owner unchanged during that edit.
3. Confirm the already configured provider has a supported isolated adapter;
   an unsupported adapter must block rather than enable tools or change provider
   configuration. Existing configured fallback may run; this is not a guarantee
   of zero inference cost, and no real inference was used in validation.
4. If separately authorized, release ONLY this ticket via expected-state CAS.
   Verify checkout activity followed by artifact existence/hash and its content.
   Heartbeat success alone is not acceptance. No other report ticket is released.

Tests use simulated providers and temporary SQLite/files; they cover CAS, owner/
company/approval mismatch, malicious action JSON remaining inert, prompt isolation,
missing hypothesis label, symlink escape, concurrent edits, failures without retry,
controller integration, and policy propagation across provider fallback. Existing
CLI-isolation tests cover configuration and credential isolation. No production
ticket mutation or live provider call is part of this PR.

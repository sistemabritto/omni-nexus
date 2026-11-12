# Blocked queue recovery — 16 October 2026

Read-only production audit: current dashboard e2cc39272f38 healthy. SQLite mode=ro and query_only=ON; no heartbeat, publication, quota probe, grant or credential change. Current code contains the unavailable-owner queue filter and heartbeat Telegram opt-in policy.

## Actual queue

92 blocked, 2 review, 411 resolved, 44 closed; no open/in_progress in this snapshot. Resolved/closed are recorded statuses, not a new audit of every deliverable. Never treat review as completion.

Blocked causes: 37 NULL, 49 stale sweep markers, 4 agent_blocked, 1 review_exhausted, 1 explicit dependency on a newly approved Short and public URL. All have requires_human_approval=0 in this snapshot; this does not establish authorization. Approval counts: 74 approved, 128 expired, 268 published, 23 rejected, none pending.

Among blocked/review items, 9 have no owner. Three are assigned to compass-planner or dex-data, whose persona files exist but autopilot heartbeats are disabled. This is unavailable execution, not proven missing code/skill. Do not enable these jobs or invent an owner. Other assignments have enabled heartbeats; that alone does not prove dependency resolution or authorization.

## Concrete cases

- 677838b4 moved from review back to blocked. Latest agent comment requests Felipe's revenue-model decision and legitimate CRM access. Admin evidence records Cloudflare403 browser_signature_banned/owner_action_required and a delivered internal specification proposing four revenue fields. Internal specification delivered; implementation legitimately blocked by decision and external access. Do not bypass Cloudflare or call the entire task complete.
- 087d2fd8 (Sessão de Start) remains blocked with no owner. Recent history says Cal.com and the sales page respond200, old delivery link404, and a controlled R$150 purchase/email/cancellation test remains. Description also records prior Cakto delivery configuration; these reports need authorized readback to resolve the discrepancy. Do not charge a purchase or modify Cakto merely to prove readiness.
- df371ba3's former false sweep diagnosis was administratively reconciled in production: explicit wait for new approved Short and public URL. Fixing sweep does not satisfy the editorial requirement.
- Existing isca15 investigation proved material/share available but an unrelated reel-sequence15 campaign with mismatched bait numbers. No new proof of campaign delivery in this audit; no campaign replay or modification.

## Reproducible recovery defect and patch

Creation uses the actual persona inventory, but individual and bulk reassignment accepted arbitrary nonexistent agents. Recovery could therefore route a blocked task to a fictional owner and leave it impossible to dispatch. Four regression cases failed before the patch, covering invalid owners and repeated assignment.

Individual and bulk reassignment now validate against that same persona inventory and normalize whitespace. Explicit unassignment remains supported. Repeating the same valid owner assignment does not touch updated_at or add assignment events; duplicate bulk ids do not duplicate effects. Bulk reassignment prevalidates immutable thread owners before changing any row, matching the individual route's rule and avoiding partial recovery of a mixed batch.

This patch changes no ticket status, blocked_reason, approval marker, heartbeat enablement or grants. It does not auto-recover the current92 blocked items. It makes later explicit recovery/reassignment safer after dependency evidence and scope have been reviewed. Invalid owner returns400, immutable thread change409; the caller must present a real owner rather than silently route elsewhere.

Only Codex was used in this round; no Claude/OpenCode process or model probe was started. Integration/deployment belongs solely to executive01a13c9a-dd49-73a0-a0fc-87b82fb29016.

Validation: 65 tests passed (ticket API, owner queue, heartbeat delivery policy, sweep race); existing SQLAlchemy Query.get deprecation warnings only. Four new cases were red before the patch. No external network transport used in tests.

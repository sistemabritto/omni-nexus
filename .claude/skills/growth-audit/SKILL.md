---
name: growth-audit
description: "Read-only Growth, Revenue and Vibe Seller audit that correlates existing Instagram, CRM, site, video and engineering evidence. Use for requests such as 'audite os últimos 30 dias do negócio'."
---

# Growth Audit — Omni Nexus

This is a shared intelligence capability, not a new agent. It reuses Pixel for editorial decisions, `int-instagram` for professional insights, `int-evo-crm` for commercial evidence, site analytics for funnel evidence, and the existing Reels/video stack for creative analysis.

## Safety contract

- Default is **read-only**. Do not send DMs, WhatsApp messages, templates, posts, approvals, or create tickets/goals.
- Never print tokens, cookies, phone numbers, emails, full CRM identities, or signed media URLs.
- Mark unavailable data exactly as `NOT_AVAILABLE`, `NOT_SUPPORTED`, `COLLECTION_FAILED`, or `PERMISSION_REQUIRED`.
- Distinguish **EVIDÊNCIA**, **HIPÓTESE**, and **OPINIÃO**. Do not turn correlation into causality.
- Instagram professional insights are authoritative for owned-account performance. Agent Reach and public research are complementary, never replacements.

## Execution order

1. Confirm the requested interval; default to 30 days.
2. Run the deterministic collector:

   ```bash
   python3 scripts/growth_audit.py --days 30 --account sistemabritto
   ```

3. Pull each owned-account Reel with `int-instagram`; normalize reach, likes, comments, saves, and shares. Preserve `NOT_SUPPORTED` fields rather than zeroing them.
4. Prove one Reel end-to-end before scaling: authorized media URL → `ffprobe` → audio → `transcricao.py` → fixed early frames (0, 0.5, 1, 2, 3, 5s) → scene samples → contact sheet → structured creative card.
5. Query CRM read-only. Report masked/pseudonymous leads only; identify unassigned, unread, inbound-last-message and intent signals. Verify WhatsApp’s 24-hour window immediately before proposing any action.
6. Query the site’s existing analytics and lead endpoints only when their configured authorization is available. Reconcile UTM/CTA/lead/deal, otherwise record the exact break.
7. Reconstruct engineering/VPS timeline with git, deployed service history, logs and existing reports.
8. Use `plugins/reach` only via its upstream-supported desktop OpenCLI + user-controlled Chrome session. Never copy cookies or bypass login/CAPTCHA. Review last30days security/setup before installation; do not use browser-cookie setup without user consent.
9. Produce a report under `workspace/reports/[C]auditoria-growth-intelligence-<date>.md`. Do not publish a Nexus share unless explicitly asked.

## Required report sections

1. Executive summary: origin, changes, wins, losses, pending work, revenue/cost/equity, threat, opportunity, next action.
2. Evidence timeline.
3. Content inventory and available analytics.
4. Reel creative cards and performance hypotheses.
5. Vibe Seller classification: Rastrear, Vibe Codar, Monetizar, Prova/Build in Public, Ferramenta/TOFU, Fora da tese.
6. CRM pending leads, anonymized and ranked P0–P3.
7. Site/funnel matrix.
8. VPS/technology-cost observations.
9. Market benchmark with sources and methodology.
10. Opportunity radar and a prioritized 30-day proposal.

## Ownership boundaries

| Output | Existing owner/capability |
|---|---|
| Editorial experiments and content response | Pixel Social Media |
| Pipeline/lead follow-up decision | EvoCRM commercial owner |
| Video processing | media worker, ffmpeg/ffprobe, `transcricao.py`, vision stack |
| Posts/approval/publication | Postiz + approval gate |
| Reporting/sharing | `workspace/reports` then Nexus shares only with explicit publication approval |

## Automation threshold

Do not add a heartbeat or monthly ADW until two manual audits generate useful, reviewed reports. At that point, schedule a read-only collection/report routine; retain human approval for CRM actions, ticket creation and publication.

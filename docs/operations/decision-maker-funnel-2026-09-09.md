# Decision-maker lead magnets → Architecture Session

User decision: visibility/CRM materials target business owners and decision-makers. The paid bridge is the existing Architecture Session, shared by Sprint and Implementation, not the self-paced Challenge.

## Source and routing

- Versioned guide source: `assets/lead-magnets/guia-visibilidade-decisores.html`.
- Existing Nexus public share: `JmqUbtpIsv8eU8Gif-9XzmuU9w2O7S95M_g1pCxYMQ4`.
- Existing volume-relative file: `reports/[C]guia-ser-mencionado-por-ia-v2.html`. Filename retained for link compatibility; visible content identifies v3.
- CTA labels: `guia-ia-v3-sessao-principal`, `guia-ia-v3-sessao-final`.
- Destination: `/sessao-de-arquitetura` with campaign `visibilidade-ia-arquitetura-v3` and content `guia-ia-v3`.
- Existing checkout `35xvemn` is shared through `site/lib/architecture-session.ts`; no new payment product created.
- Site commit: `ea9084a`, with session page, classroom bridge, bio links hierarchy and four configuration/attribution tests.

## Verification

Next build and TypeScript passed. Browser checks passed at 375, 768 and 1440px: no horizontal overflow, expected destinations, preserved origin UTMs and no page exceptions. The guide was checked under the Nexus-style restrictive CSP and in light/dark schemes. Tests mocked APIs and blocked non-local network: no real lead, DM, OTP or purchase was generated.

## Deployment and rollback discipline

Wait for the session page to return 200 with the expected content before replacing the existing guide file. Validate the old file hash before the write; back it up outside the active share path. Deploy with same-directory atomic rename, preserving the share token and counters.

Expected pre-change guide SHA256: `5630cc220cc591658821ffaf3539aea5ae18d47c68178277c994eec3f0bbd0ca`.

Backup target: `reports/backups/[C]guia-ia-before-decisores-20260909.html`. To roll back, copy that verified backup over the exact active guide path. This changes both existing shares pointing to that file; it does not revoke links or reset counts. All embedded conversion links are attributed to the primary distribution token; do not interpret per-share counts as distinct visitor cohorts.

Pre-deployment baseline: primary token 65 accumulated views / 1 click; another share of the same file had 16 views. Generic Nexus `triggers` did not contain ID 17. No automation or recipient selection was changed based on an assumed mapping. Separate release-version click labels from lifetime counters; diagnostic checks may increment view counts.

## Intentionally not done in this release

Instagram profile changes are a proposed copy, not published. No outreach, new pricing policy, payment test or lead backfill. OTP gate and lead persistence remediation remain separate work; this release changes the commercial bridge, not authentication or CRM reliability.

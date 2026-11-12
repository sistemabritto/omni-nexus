# Voice, access feedback and publication integration

Base: `7e84d6b55fdb2dce4ee2b919fcf7e383af159683`.

## Exact selected inputs

| Review | Source commits | Included behavior |
| --- | --- | --- |
| PR74 | `74e9410a1109776b57dd1250639bcc833b7b2f0b`, `efa1bcd38dc7ed82cd3be9fc51d6af7eba572e2f` | Account voice metadata, existing preview proxy and explicit next-call preference scoped to user/company/provider agent |
| PR75 | `849dfbac4d31921f4e3808a0f77beed225685c83` | Authorized agent selection independent of Live readiness; actionable errors and retry |
| PR73 | `b61bde7bbfc848fb1475f11eb2e3752b8b7d886d` | One fixed-registry publisher; exact source revision and explicit image targets |
| PR71 | `f233f23`, `0b64384`, `924d7a4`, `36b2f13`, `ac121d3`, `98c8f06`, `b2cfd16`, `73d97a2` | Previously reviewed selective design, marketing, team and Reels methods; source PR61/62/63/64/67 only |

The integration preserves the keyed company composer from the base, adds VoicePicker beside it, combines voice state with specific start errors, and keeps both sets of CI checks. Retry resets occur in the user's click handler rather than synchronously inside an effect. The context test fixture imports its routes package explicitly so it can run first.

## Validation

- 107 selected Python tests passed, including account metadata/preference guards, company/conversation scope, real loopback terminal HTTP handlers, publication contracts and skill retrieval. The loopback case requires permission to bind localhost; other tests do not contact a provider.
- TypeScript, scoped ESLint, Vite build and client/session tests passed.
- Browser QA at 375x667 and 1440x900 passed for pagination, existing preview, explicit save/reload, next-call override, unchanged current conversation, access/cost errors and retry. API, WebSocket and audio were simulated; unmocked external HTTPS was blocked.
- No real provider conversation, synthesis, publication or task execution was performed during validation.

## Remaining boundaries

This change does not add RAG, persistent conversational memory, persona injection or task dispatch to Live. The selected runtime agent supplies the existing read context; it is not executed by that client tool. Voice overrides require permission in the existing provider agent and fail closed when unavailable. No provider configuration, credential or billing change is part of this diff.

PR56/66/72 recordings/media releases, PR76 owner recovery and continuity work are outside this batch. Existing heartbeat Telegram policy and company-switch cleanup remain in the base.

## Promotion

Run the publisher once for `target=core` from the final reviewed commit. The fixed destinations are `docker.io/excarplex/evo-nexus-dashboard` and `docker.io/excarplex/evo-nexus-runtime`. Record their immutable digests, run isolated image boot checks, then promote dashboard and runtime services separately with backup, idle checks and unchanged ENV/Args/mounts. Synchronize only those image digests in the existing private Portainer source. Media-worker and OmniRoute are not targets of this core promotion.

The workflow remains proposed until its branch is promoted to the repository's default branch; manual use from a review ref does not change main. Workflow publication never deploys services by itself. Preserve private environment and user-approved personal settings during rollback; do not restore an old DB over new transactions.

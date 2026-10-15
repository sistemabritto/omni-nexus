# Current UI release

Isolated base: 050a8b506b255fa69d61ae324d25be5b174839f4. Includes only the currently authorized Live/providers patches, not execution integration cb915fb, routing, recordings trims or older UI proposals.

Verified input SHA256:
- Live: f0ef0e28a9f3155321c2137f5d43c0efc1141b622510b32dadf89cbf1580126f
- Providers: 7a75154b4c13c073e56306e0f75426d98e01f0d58dc47a895b09c80320703267

Live uses compact controls, collapsed optional transcript, results/copy/sources and explicit resume/new/end actions in the current company. No automatic microphone or conversation. Providers presents configuration only and handles backend catalog 404 honestly; this release does not include the unpublished catalog backend.

Central browser QA found desktop controls shrunk below 44px by existing global CSS and select labels containing option text. Integration enforces a scoped 48px minimum button height, provides explicit accessible select labels, and permits the legacy provider row to wrap on mobile. Controller, audio, tools, backend, ACL, voice/model and ENV are unchanged.

Publication target: dashboard only through the existing GitHub Actions workflow. Runtime, media worker and separate OmniRoute remain unchanged. VPS rollout requires private spec/config/data backup, no active call/job execution, immutable image revision verification, preservation comparison and healthy service/served asset verification. Rollback restores the previous dashboard digest without restoring database or changing ENV. Keep continuity ON and tasks OFF.

Validation: full TypeScript/Vite build passed; Live render/integrated controller/session/continuity and Providers client/SSR regressions passed. Chromium fixture QA passed at 375x667 and 1440x900 for Live and Providers, including real SDK transport with simulated provider/audio. Focused lint passed. Graphify AST update completed; generated output excluded. No actual microphone or paid provider call.

Audio audit remains open: commit 3e90e3f in test/live-playback-audit reproduces queue cancellation and stale audio after interruption. This presentation release does not fix or claim to fix either defect. No paid call is required for UI validation.

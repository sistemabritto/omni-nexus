# Live playback audit — 2026-10-15

Read-only production investigation and offline reproducer. No new provider call, microphone permission, voice/model change or deployment performed for this audit.

## Publication and source parity

Production source is 050a8b506b255fa69d61ae324d25be5b174839f4. Actions publication 38812893454 and image smoke 38813859311 succeeded for that revision. Dashboard registry manifest, running image and OCI revision agree: sha256:e32e7993a59a913fc6290644511811dc371fd906f72f47859e70c264a42662e6.

The server serves index-CT8byBh7.js, SHA256 7396d894181626d6e9439ec91ceb6f80d85a00fb64ed026dd15545a722385e79, matching container dist bytes. This verifies server assets, not a user's browser cache. `/api/version` reports a package version rather than deployment SHA.

Production audio.ts matches local source SHA256 7eb7626b83de4b933c1cd61ddcab4cbad239bb65408707f30e0e8d13eacd1a92; managed-session.ts matches 073b9475f3ee3c5b8d07ef9834311b6d1ff037b11c4469bf0d391933377d8086. Sanitized supporting artifacts are in the sibling live-harness-proof directory: live-audio-source-parity.json, live-audit-dockerhub-manifest.json and live-real-event-timeline.jsonl.

## Actual call evidence

Calls conv_3801m50vyv1jfbjtfwvb0vcqscmb (company 1, aria-hr, 22:47:05 UTC) and conv_9501m50w564ffa0a7f0ejmhtkrec (company 2, apex-architect, 22:50:33 UTC) use corrected agent version agtvrsn_4601m50vhx2cfg8s0xvs5ezk0nd6. Both have exactly one contextual_update request/result and no read_current_omni_session request/result. HTTP logs show one successful signed session, binding, continuity and read per context; event polling is not a repeated provider contextual_update.

For the second call, provider message timestamps are: greeting 0, context update 0, user 1, agent 3, user 10, agent 18, user 28, agent 40, user 51, agent 57, user 65, agent 68 seconds. Agent responses are marked interrupted. These metadata do not contain raw chunk timing/event IDs and do not identify the local playback stop reason. They cannot establish whether a particular interruption came from user speech, VAD, local queue cancellation or stale chunks. No company leakage is demonstrated. No duplicated connection/reconnect cause is established by these logs.

## Reproduced failures using production source

Run `node /absolute/path/to/live-tool-context/qa/managed-live-context/playback-regression-audit.cjs` from execution-integration (its installed frontend dependencies are used). The baseline JSON alongside the script deliberately reports FAIL and exits 1 for the two defects; it is not a successful acceptance test.

1. FAIL: seven one-second PCM chunks arriving before the audio clock advances cause six already scheduled nodes to stop, with zero provider interruption events. Playback's `next - currentTime > 5` branch calls `stop()`, discarding queued speech. This proves a silent cut mechanism during a sufficiently fast burst or stalled playback clock.
2. FAIL: audio event 10, interruption event 20, then late audio event 10 schedules another node. ManagedSession consumes the SDK low-level WebSocketConnection audio listener, which strips event_id. Unlike the SDK high-level conversation implementation, it cannot filter audio older than the interruption watermark. This proves stale speech can re-enter playback after cancellation.
3. PASS controls: concurrent starts create one connection and one audio listener; three continuity polls retain one contextual_update; audio arriving after end is discarded.

The reproducer uses real Playback/ManagedSession and installed ElevenLabs WebSocketConnection with synthetic sockets, HTTP and AudioContext. Provider calls, hardware audio and microphone permissions are zero. Neither product source file was changed.

## Release implication and remaining evidence

These are demonstrated causes of cut/re-entry in the served code, not proof that every reported spontaneous utterance has the same cause. A minimal fix needs both negative tests to pass while retaining the three controls. If actual-call attribution is still needed, collect only event kind/id, monotonic timing, queue duration, generation and stop reason during an explicitly user-started call; exclude audio, transcript, keys and signed URLs. Do not tune voice, model, turn-taking or company binding speculatively.

Integration cb915fb is preserved. The separately authorized current Live/providers UI patches do not modify these audio/controller files and must not be represented as an audio fix. UI publication scope can remain separate from execution routing and recordings changes.

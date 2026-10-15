# Playback fix for review — not deployed

Branch fix/live-playback-ordering, isolated from UI release 53403b7 and integration cb915fb. No remote settings, provider calls, microphone or production changes.

The baseline audit commit 3e90e3f reports two FAILs. The same real-source/installed-SDK reproducer now passes: seven one-second chunks retain their scheduled order instead of cancelling six seconds; an audio event older than the interruption watermark cannot re-enter playback.

Playback no longer treats a five-second scheduling backlog as an interruption. It preserves scheduled nodes and imposes explicit bounds of ten seconds per chunk and 120 seconds queued PCM. Exceeding a bound reports a visible error and disables the microphone; it does not silently restart a sentence. These are safety ceilings, not measured latency targets or a claim that a 120-second delay is desirable.

ManagedSession consumes raw SDK message audio to retain event_id. A single no-op output listener drains the SDK mirrored pendingAudioEvents queue; it never plays audio. Raw messages remain the sole playback path. Interruption watermarks only advance; duplicate/older interruption events cannot stop a newer response. Malformed interruption IDs disable audio with a visible status. Missing/invalid audio IDs are not played. Audio with an ID equal to the watermark remains accepted, matching the installed SDK high-level comparison; integration must preserve provider event semantics.

Regression evidence: qa/managed-live-context/playback-regression-fixed.json. Tests cover burst order, explicit stop cleanup, bounded queue overflow without silent cancellation, one connection/listener, no repeated contextual_update on polling, stale audio rejection, newer audio playing once with zero SDK backlog, duplicate interruption, later watermark, oversized audio status/mic shutdown and audio after end. Existing session and continuity regressions, focused TypeScript and lint passed. AudioContext/socket/HTTP are synthetic; actual SDK WebSocketConnection is used. No actual call, echo/VAD or browser audio-device acceptance is claimed.

Before publication: review this delta, integrate it separately with the current UI, run browser/SDK regression and build, then obtain authorization for the new revision. UI 53403b7 remains the only presently authorized deployment target. Existing real-call logs do not contain raw chunk timing, so this patch fixes demonstrated mechanisms without attributing every reported spontaneous utterance to them.

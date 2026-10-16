# Reviewed audio + Providers release

Release branch release/audio-providers-reviewed integrates 9d27b75 (Providers + cb915fb) and c1d0e23 (audio), including the baseline regression from 3e90e3f. Published UI 53403b7 is retained. Publication/deployment of these presented lots was explicitly authorized by Felipe; final SHA, Actions and digests are recorded in the deployment evidence outside the source tree.

## Exact scope

- Audio: preserve queued speech across the old five-second boundary; filter stale/duplicate interruption generations using raw SDK event IDs; retain one SDK mirror drain listener and one playback path; explicit chunk/queue bounds with visible errors. No voice, model, remote prompt or microphone auto-start change.
- Providers: read-only catalog/preview and templates/role bindings, unknown runtime/cost/capabilities remain unknown, Hermes/Codex Em breve. Preview cannot execute, and response revision/operation/pool/filters are bound to its request.
- Inherited cb915fb: opt-in restricted execution route trace (default OFF), manual immutable recording trims and worker packaging of recording_edits.py. These existing package components require compatible dashboard/runtime/media-worker images. No operator policy, credential, quota/budget attestation, social publication or execution activation is introduced.
- Audio regression is now in the existing backend CI lane; no generated graph or dependency lockfile change is included.

## Combined verification

118 backend tests passed, including real loopback HTTP/terminal handler tests with mock provider, catalog/runtime/continuity/ownership and the new paired TS and playback CI tests. 62 media/recording/release/packaging tests passed with synthetic local rendering and mocked distribution. The separate new trim-smoke render was not repeated. Twelve playback checks passed using actual source and the installed SDK with synthetic socket/AudioContext; actual user audio/VAD/echo acceptance is not claimed.

Controller/session/continuity, mounted Live and Providers client/SSR/paired real Flask payload contracts passed. Full frontend build and focused lint passed. Chromium fixture checks passed at375x667 and1440x900 on the integrated build for Live SDK transport and Providers, including404/409/stale response and legacy preservation. No paid call, actual microphone, Postiz submission or external execution is part of verification.

## Controlled rollout and rollback

Publish the exact reviewed SHA with the existing fixed-namespace GitHub Actions publisher for all three images; verify Actions, digest and OCI source labels. Image smoke boots ephemeral data with external networking disabled. Preserve service ENV/mounts/data/sessions, continuity ON and Live tasks OFF; execution routing must remain absent/false. OmniRoute is excluded.

Stage images before interruption, inspect global workspace lock, active CLI/render processes, database queues and finished-call metadata. Never kill work or mistake an inter-attempt pause for idle. Back up private service Specs/compose/config, SQLite through backup+quick_check and session data. Update compatible worker first, then scheduler/Telegram runtime and dashboard, checking health and exact image-only Spec deltas. Persist only reviewed image lines in the existing compose source. Verify source/runtime SHA/digest, served UI assets, unchanged ENV bytes, flags, DB counts/integrity and session persistence afterward.

Rollback uses saved immutable images and original Specs without restoring databases or replaying any job/upload/post. If a new recording snapshot contains trim fields, retain the compatible new worker while rolling back core services; an old worker must not consume those snapshots. Report any such retained worker explicitly. A failure or authorization rejection is a blocker, not permission to bypass checks.

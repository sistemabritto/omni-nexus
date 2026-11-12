# Live model diagnostics contract v1

Prepared policy; no activation, production update, real audio or quota claim.

GET /api/live/status keeps cookie+same-origin auth and no-store. Additive fields:

```json
{"enabled":false,"freeTierVerified":false,"configuredModel":"gemini-3.8-live","activeModel":null,"fallbackModels":[],"fallbackBlockedModels":["gemini-3.1-flash-live-preview"],"maxProviderAttempts":2,"fallbackPolicy":"startup_model_unavailable_only","contextResumptionSupported":false}
```

`activeModel` is always null on this HTTP endpoint: activity belongs to the browser WebSocket, not global configuration. Never label configuredModel as active. `fallbackModels` contains independently quota-verified configured candidates. `fallbackBlockedModels` names configured candidates lacking that evidence; model listing does not supply it.

WebSocket additions (existing ready/listening/audio/transcript/interrupted remain):

```json
{"event":"model_attempt","configuredModel":"gemini-3.8-live","model":"gemini-3.8-live","attempt":1,"maxAttempts":2,"reason":"initial","contextPreserved":false}
{"event":"model_switch","fromModel":"gemini-3.8-live","toModel":"gemini-3.1-flash-live-preview","reason":"model_unavailable","attempt":2,"maxAttempts":2,"contextPreserved":false}
{"event":"model_attempt","configuredModel":"gemini-3.8-live","model":"gemini-3.1-flash-live-preview","attempt":2,"maxAttempts":2,"reason":"model_unavailable","contextPreserved":false}
{"event":"model_active","activeModel":"gemini-3.1-flash-live-preview","attempt":2,"contextPreserved":false}
{"status":"ready"}
{"status":"reconnect_required","reason":"go_away","activeModel":"gemini-3.1-flash-live-preview","contextPreserved":false}
```

model_active is emitted only after Google setupComplete. Model switches only before any ready/audio, on structured404/501/NOT_FOUND/UNIMPLEMENTED, at most one fallback. No repeated model or third attempt. Auth401/403, quota,429, generic503 and network errors never switch models. No automatic reconnect or replay after readiness. Provider resumption is not implemented by this bridge: show explicit new-session/context-reset wording, not continuity. No handles, prompts, audio or exception strings in logs.

Error enums: provider_auth_failed, provider_quota_exhausted (structuredQuotaFailure), provider_rate_limited (other429), provider_network_error, provider_model_unavailable, provider_unavailable. Existing live_disabled, session_limit, setup_timeout, audio_rate_limit, invalid_audio_or_provider_protocol, session_rate_limit remain. Network loss after readiness additionally sends reconnect_required with reason network_error and contextPreserved false.

Non-secret configuration proposed, not applied:

```dotenv
GEMINI_LIVE_MODEL=gemini-3.8-live
GEMINI_LIVE_FALLBACK_MODELS=gemini-3.1-flash-live-preview,gemini-2.5-flash-native-audio-latest
GEMINI_LIVE_VERIFIED_MODELS=
GEMINI_LIVE_ENABLED=false
GEMINI_FREE_TIER_VERIFIED=false
```

VERIFIED_MODELS must be populated only after per-model project quota/tier confirmation; no derivation from catalog or successful handshake. Primary is explicitly selected in MODEL; no silent model default. Eligible candidates preserve configured order, only first eligible used (max2total). Native-audio fallback has the same PCM16k input/24k output contract, but metadata compatibility is not a successful end-to-end audio test. No TTS, transcription, translation, robotics or music model is in the conversational allowlist.

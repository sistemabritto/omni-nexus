---
name: cloudflare-protected-api-403-diagnosis
displayName: "Cloudflare 403 Diagnosis"
description: "Diagnose and resolve 403 errors from Cloudflare-protected API origins by distinguishing bot-fight-mode UA blocks from IP/geo-based WAF blocks (error code 1010), and using a hosting VPS as a trusted-IP relay to confirm and route around the block. Use when an API call to a Cloudflare-fronted domain (e.g. *.workflowapi.com.br) returns 403 despite a valid API key/credential."
category: "debugging"
envKeys: []
---
# Cloudflare 403 Diagnosis

When working with Cloudflare-protected APIs (like Plausible at `track.workflowapi.com.br` or Groq), you may encounter HTTP 403 errors even with valid credentials. This skill helps diagnose the two most common root causes and provides workarounds.

## Two Distinct Root Causes

### 1. Bot-Fight-Mode (Non-Browser User-Agent)
- **Trigger**: Cloudflare challenges requests with default Python `urllib`/`requests` User-Agent (or other non-browser UA).
- **Evidence**: Same request succeeds via `curl` (which sends a browser-like UA by default) or when you manually set a browser-like User-Agent.
- **Fix**: Use `curl` for such calls, or set a real browser-like User-Agent (e.g., `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"` and case-sensitive `Host`/headers) in your Python client.

### 2. Origin-Rules/WAF Block (Error Code 1010)
- **Trigger**: Cloudflare error code `1010` visible in the response body (`{"error": "Error 1010 Ray ID: ...: The owner of this website has banned your browser's user agent."}`).
- **Root Cause**: Geographic or IP-reputation based block — not fixed by changing User-Agent.
- **Diagnostic Technique**: Replay the exact same request from the VPS (via `ssh` + `curl`) that hosts the target service.
  - If it succeeds from the VPS but fails locally → Cloudflare is allowlisting/trusting the VPS's IP (or geography) and blocking your local/residential IP.
- **Fix**: Route API calls that hit Cloudflare-protected origins through the VPS instead of trying to bypass the WAF client-side.

## Workflow

When you encounter a 403 against a known Cloudflare-protected endpoint:

1. **Inspect the response body** for `"error": "Error 1010"`.
2. **If 1010 present**:
   - Test the request from your VPS (where the service is hosted) using `ssh` and `curl`.
   - If the VPS request succeeds (200), confirm the block is source-based.
   - **Solution**: Configure your script to proxy the request through the VPS (e.g., via an internal API or SSH tunnel) OR use the VPS as a relay.
3. **If no 1010 (or generic 403)**:
   - Retry the request with a browser-like User-Agent header.
   - If it succeeds, the issue was bot-fight-mode triggered by your script's default UA.
   - **Solution**: Permanently set a realistic User-Agent in your HTTP client.

## Examples from EvoNexus

### Plausible API (`track.workflowapi.com.br`)
- **Symptom**: `GET /api/v1/sites/<id>/stats` returns 403.
- **Diagnosis**: Response body contained Error 1010; identical `curl` from VPS succeeded.
- **Fix**: The dashboard backend now proxies Plausible API calls through the VPS (see `dashboard/backend/sdk_client.py`).

### Groq Whisper Transcription API
- **Symptom**: `POST https://api.groq.com/openai/v1/audio/transcriptions` returns 403.
- **Diagnosis**: Response body showed Error 1010; request succeeded when run from VPS.
- **Fix**: The `terminal-server` (Node.js) already runs on the VPS, so the proxy endpoint `/api/transcribe` inherently avoids the block. For direct testing, use the VPS.

## Prevention

- For any new integration targeting a Cloudflare-protected domain, assume 403s are possible and implement diagnostics early.
- Prefer using the VPS as a trusted relay for external API calls when the service is hosted there (as with `terminal-server`).
- Keep a library of known-good User-Agent strings for quick testing.


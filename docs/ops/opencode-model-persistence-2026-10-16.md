# Normal chat: selected OpenCode model

Base: production 96f735f. This change does not rewrite provider configuration.

Read-only production diagnosis found an active OpenCode entry with default_model
but no OPENAI_MODEL. The API exposed only existing environment keys and silently
ignored a newly submitted model key; the Node loader dropped default_model and
model resolution ignored it. The resulting missing-model error precedes HTTP.
Both configured gateway model catalog GETs returned 200 with existing credentials;
no generation was performed. A previous normal-chat log instead showed a 401 on
an OpenRouter/Claude SDK fallback. These are separate observations, not evidence
of a quota failure.

The API now exposes and accepts the missing OpenCode model field. The loader
preserves its configured default, used only when OPENAI_MODEL is empty. Explicit
saved models win. Native and unrelated provider fields retain existing behavior.
Unsupported Agent SDK CLIs now use the selected HTTP chat endpoint instead of
silently selecting an SDK-compatible fallback. This is text chat compatibility,
not execution of OpenCode CLI tools, terminal sessions or harness capabilities.

The regression exercises authenticated Flask endpoints, a temporary config file,
the real Node config loader and chat bridge with an SSE transport fixture. It
checks defaults, explicit saves, mode=code, key/URL/provider preservation and
rejection of unrelated fields. All credentials in fixtures are invented. No real
provider generation, deployment or production config write occurs in this test.
Initial harness failures (Python import path and incomplete SSE response mock)
were corrected; they are not counted as product regression evidence.

Publication still requires CI/image verification and a deployment window with
fresh configuration preservation, because Felipe is editing provider settings.
Do not restore any historical providers.json or overwrite his URL/key/model.
Local graph extraction is deferred while CPU/swap are saturated.

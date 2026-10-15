# OpenReply draft guard and runtime preflight

A generated creative previously inserted an active OpenReply campaign with a `{link}` placeholder before any delivery link had been created. `pendingNextReel` is a binding mode, not an authorization or messaging safety gate. The creator now inserts an inactive draft with DM, public replies and public report sharing disabled. It reports `status=draft`, `activation_required=true` and `delivery_link_required=true`. Existing campaigns/links are not modified or migrated.

Artifact/card metadata is updated from the draft result before rendering. A real operator must review the exact material/destination, keyword collisions and post binding, provide the delivery link and explicitly authorize activation through the supported OpenReply flow. Approving a creative or finding a campaign with the same keyword does not prove delivery readiness. This patch does not add automatic activation or change existing campaign states.

The creator rolls back on a database error and returns a fixed error enum; connection strings and driver exception messages do not reach the caller. PostgreSQL access continues using the existing environment configuration and does not gain permissions.

Runtime preflight now mirrors existing clients: the Nexus SDK has a localhost/FLASK_PORT fallback, so an absent URL override does not mean missing auth; the OpenReply adapter has host/user/db defaults when a password is configured. Preflight names its actual Python executable and reports driver availability in that interpreter, distinguishing a system-Python import failure from the installed application environment. It performs no connection itself. Configuration/driver presence is not proof of connectivity or authorization; an operational check must use SELECT 1 in a read-only transaction before claiming connectivity.

Tests use fake DB connections and fixture credentials only. They verify inactive messaging/report flags even when a generated row claims activation, UTC timestamps, rollback/redacted errors, SDK endpoint fallback, driver/interpreter guidance, cards and preserved human gates. No campaign, DM, CRM change or production deployment is performed by the tests.

Material rollout behavior change: newly generated campaigns will remain drafts until link and activation review. Existing campaign repair and activation require their own scoped authorization. Coordinate this backend patch with any frontend integration rather than overwriting unrelated menu work.

## Secret-file compatibility smoke

The existing image entrypoint supports `GEMINI_API_KEY_FILE` before starting Flask, while the app consumes `GEMINI_API_KEY` from its process environment. The isolated default-supervisor CI mounts a clearly fictitious value at a differently named secret path and explicitly sets `_FILE`; a quiet equality check verifies the value reaches the real Flask process without printing it. The basename intentionally cannot auto-map to GEMINI_API_KEY, so this tests the `_FILE` mechanism independently of auto-discovery. Both Live flags remain false and container network remains none. No real secret is read, configured or sent to Google.

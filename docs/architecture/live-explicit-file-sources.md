# Live: explicitly owned Workspace file sources

Base a310ae1. Isolated checkout live-file-search, branch
feat/live-explicit-file-sources. Software only: no deployment, production file
binding, ownership transfer, remote agent/tool configuration, paid call or grant.

## 1. Ownership discovery

The existing code establishes different, incomplete relationships:

* `models.has_workspace_folder_access` and `routes.workspace._check_folder_access`
  enforce a user's current role against a top-level Workspace folder. The
  canonical file reader also enforces root/blocklist/path rules. A folder-role
  grant is not an association with a particular company.
* `GoalProject.company_id` plus `workspace_folder_path` associates a project with
  a folder, but the generic project create/update API accepts the path and does
  not certify ownership of every file, a content revision, or a particular user.
  This pointer alone is therefore not auto-adopted by Live retrieval.
* `FileShare.created_by_id` establishes the sharing user and a path, but has no
  company relation. Share tokens and public/external URLs are not imported.
* Current RecordingScript already has its own company/user ACL and revision/hash
  adapter. That source remains unchanged and distinct from Workspace files.

Earlier read-only diagnosis found file-name candidates for scripts but no proven
company mapping. This increment does not crawl those files or migrate their
ownership. A positive test explicitly seeds a project folder pointer and proves
that it alone does NOT expose a file.

## 2. Explicit binding, never a permission grant

A human in the existing personally configured admin session selects a file and
company, previews metadata and explicitly confirms ownership. The existing
Workspace view/folder/path permissions are still required. Binding additionally
requires goals:manage; no user role, folder ACL or company membership is changed.

The new `live_file_sources` table resides in the EXISTING context SQLite database
(`NEXUS_LIVE_CONTEXT_DB` / nexus-live-context.sqlite3). Its fields are id, user_id,
company_id, path, sha256, revision, active, updated_at. No source text is copied,
indexed, embedded or logged. This is one additive, lazily created metadata table;
no application/model schema migration or new global database is introduced.
There are no prepopulated bindings. Rollback software may leave the inert table.

Bindings are scoped to the authenticated user AND selected active company, and
persist across that user's authorized sessions for that company. Each Live query
still requires the owned runtime/provider conversation. Another company or user
receives no source, even when that user independently has Workspace permission.
An active path cannot silently be bound to another company; explicit revocation
of the earlier association is required. No such transfer is performed here.

Preview returns only path, digest, bytes, mtime, companyId and expectedRevision.
Bind uses a fresh file read, the reviewed SHA256 and compare-and-swap revision,
plus confirmOwnership=true. It stores only metadata. A changed file stops
matching immediately and requires preview + explicit rebind. Revocation increments
revision and removes it from subsequent delivery; it never deletes the file.

## 3. Browser and API flow before a paid conversation

The Live page has a collapsed “Arquivos para consultar · <empresa>” panel below
the conversation. It uses the company selected in the global menu, and is usable
with voice consumption disabled. No runtime or provider session is created.

1. Copy an already accessible Workspace file path (workspace/pasta/roteiro.md).
2. Choose “Conferir arquivo”; this returns metadata, not source text.
3. Review the file in Workspace and confirm that it belongs to the displayed
   company and may be included in your queries. The checkbox starts unchecked.
4. Bind it. List/status and “Remover vínculo” remain available. Changing company
   remounts the panel, aborts outstanding requests and clears pending confirmation.

Authenticated same-origin POST endpoints:

| Endpoint | Exact body |
| --- | --- |
| /api/live/file-sources/{companyId}/preview | path |
| /api/live/file-sources/{companyId}/bind | path, sha256, expectedRevision, confirmOwnership:true |
| /api/live/file-sources/{companyId}/list | {} |
| /api/live/file-sources/{companyId}/revoke | id, expectedRevision |

The analogous /api/live/omni-context/{contextId}/file-sources/{action} routes require
conversationId in addition and enforce the immutable context/conversation scope.
Company/user/session/model override fields are rejected. All routes retain the
personal active-admin, cookie-only and HTTPS same-origin guard. Inactive/missing
companies are denied. These actions are NOT model tools; neither read_current
nor a remote agent can register or confirm a file through this tool contract.

## 4. File and retrieval boundaries

* Only explicit individual .md/.txt/.html files, at most 128 KiB each; at most
  32 active bindings per user/company. No recursive scan, PDF extraction, media,
  shell, network fetching, shared corpus or link following.
* Canonical Workspace resolver/folder ACL is reused. Only paths strictly within
  workspace/ are accepted; admin roots, traversal, noncanonical paths, dotfiles,
  sensitive names and unsupported extensions are denied. Descriptor traversal
  with O_NOFOLLOW rejects symlinks at every component, including substitution
  between resolve/open. Hardlinks, special files, unstable reads, invalid UTF8
  and NUL/binary content are denied.
* A conservative full-file detector refuses private-key markers and recognizable
  credential assignments/tokens before preview/bind/search. This is a pattern
  filter, not proof that arbitrary prose contains no confidential information;
  explicit human review/ownership confirmation remains necessary. No blocked
  content or exception detail is included in responses or new logs.
* Search intersects active own bindings with current ACL and exact current digest.
  The top 3 matches use the existing derived terms and bounded 600-character
  matching excerpts. Unbound files never enter candidate selection. Digest/ACL
  and binding active/revision/hash are rechecked before serialization.
* Results are untrusted reference data in queryResult.files for the existing
  no-argument read tool, or files in explicit /query. Each has original Workspace
  API reference/path, binding ID, binding revision, SHA256, mtime and source label.
  They do not become RecordingScript results or approved factual memory.
* Existing 4,000-character derived-query and 23,500-character combined budgets
  also trim file results. Current transcript memory/recording files retain their
  separate source labels. Counts distinguish bound/current/unavailable files.
  A generic “arquivos” question can return zero lexical hits while availableCount
  honestly reports current bindings; this is not semantic file browsing.

## 5. Validation and limits

68 backend tests passed, including actual loopback HTTP -> Flask -> SQLite ->
real TypeScript dispatcher -> simulated SDK output. Tests cover explicit-file
positive retrieval through /query and zero-argument /read; persistence across
contexts; an unbound file excluded; original reference/hash/revision; changed
content requiring CAS rebind; revocation and revocation during read; current
Workspace permission revocation while memory remains available; company/user/
conversation isolation; unsupported/unsafe paths, links, secret-like content,
binary/oversized files; binding cap including reactivation; company binding before
voice with zero runtime calls; cookie/origin/inactive-company guards.

TypeScript no-emit typecheck passed with installed dependencies (no installation
or production frontend build). Browser QA passed on the real local Live page at
375 and 1440 px with synthetic APIs: unchecked ownership prevents binding, preview
is nonbinding, bind/revoke requests match displayed company, denied preview shows
inline feedback, company switch clears confirmation, no horizontal overflow,
44px input target, zero provider/microphone calls. Mobile screenshot inspected.
Browser QA: qa/live-file-sources/browser-qa.cjs; screenshots in
/tmp/live-file-source-ui/. This verifies browser interaction, not live model use.

Initial HTTP fixture incorrectly used provider-a against current-provider and
was corrected; an intermediate run had 45 passed / that one fixture failure.
The final 68-test run passed. Initial visual attempts failed because Vite DEV's
localhost:8080 API and blocked HMR conflicted with the existing production-style
fixture. The /tmp-only QA configuration uses same-origin API and permits only
local HMR; application production configuration is unchanged. All nonlocal
requests/provider sockets remain mocked or denied. Existing SQLAlchemy Subquery
warning remains.

To reproduce browser QA without a new build, use a local Vite config extending
the existing config, cacheDir in /tmp, define import.meta.env.DEV=false (fixture
API same-origin), and allow ws://127.0.0.1:5207 in the LOCAL QA CSP only. Run Vite
with --configLoader runner on 127.0.0.1:5207; then set QA_PLAYWRIGHT_MODULE to the
existing installed Playwright package and run the browser script. This temporary
harness configuration is not deployed.

## 6. Handoff

Integrator reviews and publishes software separately. Publishing with no bindings
exposes no files. Actual productive associations require the owner to select and
confirm particular paths/company in the new panel; this delivery does not infer
those choices or mutate production data. No queue/skills/audio handlers changed.
Future automatic artifact attachment must carry canonical company/user ownership
and content revision at creation; legacy project/share pointers are not enough.

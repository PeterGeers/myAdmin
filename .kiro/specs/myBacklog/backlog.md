
# Time tracking

- Quick add part
  -- Missing product or NOT
  -- What about more people able to track time
  -- What about access to the time tracking app as a stand alone app (cognito/jwt impact)
  -- What is the added value
  -- How can we easy filter a period for submitting (day, week, month or year)


# STR Import Guesty

https://app.guesty.com/reservations?viewId=6a72237ce377681f84e3746c
Add website data loading from guesty
Strip fee is not in Guesty and can be found in stripe link reservation code

What is this : https://report.guesty.com/apps/reservations?apiKey=89b048a6196d1b5fbcbc40f8cb6b75924419bce37cd1efa83af5d4c6b230e089ddb4caaaad87ab85a5444543e00bcd0c80e18d3bb037d66aca1a1f7513fea2ff

## prompt:
Checkin is between 2 months ago and 1 year into the future for Platform Manual



# s3 object management module and SAM
How can we manage s3 management attributes similar as in Flask and see  .kiro\specs\Common\image-asset-management
How can wwe make a resusable piece of code as in .kiro\specs\Common\Frameworks and .kiro\steering\37-shared-building-blocks.md

# PITR / Backup in dynamodb
Check the current settings and what is needed


# Candidates for Shared frontend component library





# SPEC: Tenant Administration architecture — registry-driven admin surfaces
**Problem:** the Tenant-Admin dashboard tabs are a HARDCODED flat list with ad-hoc gating
(`frontend/src/components/TenantAdmin/TenantAdminDashboard.tsx`): some tabs always render
(Users, Functions, Storage, Templates, Media, Tenant Info, Sender, Pivot, Landing), FIN shows
`if hasFIN`, Members `if hasMembers`, Advanced `if isSysAdmin`. There is NO model of "which admin
surface belongs to / is needed by which module", so the differences a user sees
(FIN admin gets Advanced/Storage; Members admin gets a 4-subtab editor; etc.) are ACCIDENTAL, not
designed. Standardize it.

## The three KINDS of admin surface (the core model)
1. **Cross-cutting capabilities** — Storage, Functions, Pivot, Templates, Media Assets, Advanced.
   Not owned by one module; they SERVE modules. Storage is the clearest: one tenant choice that
   many object-storing modules (FIN invoices, Members docs, STR) consume.
2. **Module-specific config** — Financial (FIN), Members (MEMBERS). Owned by exactly one module;
   meaningful only when that module is entitled. A module's panel may be a single view (FIN) or a
   sub-tabbed panel (Members' 4 tabs) — richness is the module's own concern, NOT something to
   force uniform.
3. **Namespace-driven parameter views** — "Advanced" is the generic one: it renders ALL params in
   a namespace as a table. It is not a feature; it is a GENERIC parameter editor pointed at a
   namespace. Members' typed config editor is the FRIENDLY version of the same underlying thing.

## The architecture: one registry of admin surfaces + modules declare what they CONSUME
Replace the hardcoded tab list with a registry; each surface declares WHEN it applies:
- **`always`** — platform baseline for any Tenant_Admin (e.g. Users, Tenant Info).
- **`module: <NAME>`** — shown only when that module is entitled (Financial→FIN, Members→MEMBERS).
- **`capability` (cross-cutting)** — shown when ANY entitled module DECLARES it consumes that
  capability. Storage renders because some entitled module said `consumes: storage`, NOT because
  it is hardcoded always-on.

Extend `MODULE_REGISTRY` (`backend/src/services/module_registry.py`) with an admin declaration
per module, e.g.:
```
FIN      → admin_panel: "financial";  consumes: [storage, templates, pivot]
MEMBERS  → admin_panel: "members";    consumes: [storage, media]
STR      → consumes: [storage, pivot]
```
The dashboard DERIVES its tabs: baseline ∪ (module panels for entitled modules) ∪ (cross-cutting
surfaces any entitled module consumes) ∪ (role-gated surfaces e.g. Advanced for SysAdmin). No
if-ladder. Adding a module's admin surface = one registry entry, not editing the dashboard.

## Storage — a SHARED CAPABILITY with a per-tenant choice (the key example)
Storage is "one choice relevant for many modules that store objects." Architecture:
- **Config once** — a tenant-scoped param (`storage.invoice_provider`, options
  google_drive/s3_shared/s3_tenant), authored in the Storage admin surface.
- **Many consumers via one resolver** — `services/storage_resolver.py::resolve_storage_provider`
  is the single dispatch; FIN, Members, STR all call it. (This is the config-value→handler
  pattern; see the "Member number policy" spec's StrategyResolver — Storage is a sibling use.)
- **Surface visibility** — the Storage tab appears when an entitled module declares
  `consumes: storage`. So a Members-only tenant that stores docs still gets Storage; a tenant
  whose modules store nothing does not.

## "Advanced" + Members config — one thing at two polish levels (namespace parameter editing)
Both are PARAMETER-NAMESPACE editors over the `parameters` table:
- Every module namespace gets a GENERIC namespace editor for free (the raw table = "Advanced",
  SysAdmin-gated because raw params are dangerous).
- A module MAY register a TYPED editor that supersedes the raw table for its namespace (Members
  did this with its 4-tab config; FIN could). "Advanced" stays the catch-all for namespaces
  without a typed editor.
This unifies why Members-config and Advanced felt inconsistent — they are the same mechanism
(namespace param editing), one typed, one raw.

## Open questions (design pass)
- Which cross-cutting surfaces are truly `always` vs `capability`-consumed? Today Storage/
  Templates/Media are always-on — likely wrong for a module that stores nothing. Make each an
  explicit per-module `consumes` decision.
- Where does the admin-surface registry live: extend `MODULE_REGISTRY` (backend, projectable) vs
  a frontend-only surface map? Prefer backend so both the entitlement truth and the surface
  declaration share one source.
- Relationship to `tenant_functions` (the Functions tab): that is the WITHIN-module toggle layer;
  the admin-surface registry is the WHICH-surfaces layer. Keep them distinct but consistent.
- SCOPE: `MODULE_REGISTRY` + `TenantAdminDashboard.tsx` + the generic namespace param editor +
  the storage resolver. Relates to: "Member identity & number policy" (StrategyResolver / config
  patterns), "Fail-loud integrity" (generic-vs-tenant placement), "Shared frontend component
  library" (the dashboard is a reuse consumer). Own spec.





# Projection version gap — config/param changes don't auto-bump the projection version
**Problem (discovered during s5m h-dcn SAM Code migration, 2026-09-30):** a change to a
tenant's `members.*` parameter (e.g. `members.field_overlay` via `seed-hdcn-members-config.py`
or the Tenant-Admin config UI) does NOT propagate to the DynamoDB `governance_projection`
`config#fields` / `config#scope` / `config#views` rows on its own. `ProjectionSync` writes each
row only when its `version` strictly supersedes the stored one (`_conditional_put` +
`_supersedes`, `services/projection_sync.py`), and that `version` is derived by
`_scope_config_version(tenant)` from the **tenant row's** `version`/`updated_at`/`revision`/
`modified_at` — NOT from the changed param's content. So after seeding the param, `sync_administration`
reported `written=0 skipped=15` and the app kept serving the OLD field config until we manually
bumped the tenant row (`UPDATE tenants SET updated_at = CURRENT_TIMESTAMP WHERE administration='h-dcn'`)
and re-ran the sync (then `written=4`).

**Impact:** any future members-config change (new/edited overlay field, changed enum values, a
new `member_number` format regex) will SILENTLY not take effect in the app plane unless someone
also touches the tenant row `updated_at` (or knows to). Easy to rediscover the hard way.

**Interim workaround (what we did):** after seeding a param, bump the tenant row `updated_at`,
then run the projection sync for that tenant. (For h-dcn, the sync must READ Railway MySQL and
WRITE the real `governance_projection` in the `nonprofit-deploy` account — strip the `.env`
personal-account AWS keys + local `AWS_ENDPOINT_URL_DYNAMODB`, force `AWS_PROFILE=nonprofit-deploy`.)

**Now committed as a one-command runner:** `scripts/aws/project-config-to-prod.py --tenant <t> --apply` performs seed → `tenants.updated_at` bump → AWS re-strip + STS account guard → `ProjectionSync.sync_administration` → read-back verify, and REFUSES to report success on `written==0` (which signals the version bump did not take). Dry-run is the default. This removes the manual-dance footgun for the interim; the proper fix below still stands.

**Proper fix (the deferred "task 6.x" the code comment references in `_scope_config_version`):**
thread a per-parameter change revision through so a `members.*` param write bumps the relevant
`config#*` projection version directly — no reliance on the coarse tenant-row timestamp. Options:
(a) `ParameterService.set_param` stamps/increments a per-namespace revision the builders read;
(b) the param-change route enqueues the sync AND the builders version off the param's own
`updated_at` rather than the tenant row's. Either way: a config change should be sufficient on its
own to propagate to the projection. Add a test that a param change alone yields `written>0`.

**Scope:** `services/projection_sync.py` (`_scope_config_version` / the config#* builders),
`services/parameter_service.py`, the members-config seed/route. Relates to the Tenant Administration
registry spec (same params/projection plumbing).




# Passkeys fails again. has been resolved more times
Nog geen passkeys geregistreerd. Registreer er een voor sneller en veiliger inloggen.

Aanmelden mislukt
Passkey registreren mislukt. Probeer het opnieuw.

# load_dotenv() in database.py clobbers AWS_PROFILE → ops scripts silently hit the WRONG AWS account
**Problem (cost ~2 sessions during members-modal-field-mapping-mismatch, 2026-10-01):** `backend/src/database.py` calls `load_dotenv()` at IMPORT time. The repo-root `.env` exports STATIC personal-account `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` plus `AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000`. boto3's credential chain ranks static ENV keys ABOVE `AWS_PROFILE`, so ANY script that (a) strips those keys in the shell to target `nonprofit-deploy`, then (b) imports `database` (or anything that transitively imports it), gets the keys SILENTLY RE-INJECTED by that import-time `load_dotenv()`. The DynamoDB client then resolves the WRONG account (personal `344561557829`) or the LOCAL emulator — surfacing as `ResourceNotFoundException: Cannot do operations on a non-existent table` on prod tables (e.g. `governance_projection`) that only exist in `nonprofit-deploy` `506221081911`. The failure is maximally confusing because a direct boto3 read of the SAME table name/region/account (in a process that never imported `database`) succeeds, so it looks like an intermittent "table doesn't exist" when it is really a credential/account swap.

**Impact:** every local ops script that spans "strip env → import backend code → write real AWS" is a landmine: the strip is undone by the import. This is the root cause of the hours lost projecting the h-dcn members config to prod. It will recur for ANY future Railway-MySQL-read → nonprofit-deploy-DynamoDB-write script.

**Interim workaround (now committed):** `scripts/aws/project-config-to-prod.py` bakes in a `_restrip_aws_env()` that re-pops `AWS_ENDPOINT_URL_DYNAMODB` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` and re-pins `AWS_PROFILE` + `AWS_REGION` AFTER the database-dependent imports run (so after their `load_dotenv`) and BEFORE building any boto3 client, plus a hard STS account guard. Any new ops script in this shape must do the same (import database-dependent modules → re-strip → account guard → write).

**Proper fix (candidates):** (a) make `database.py` NOT call `load_dotenv()` at import time (load config explicitly at app startup instead), or at least have it NOT override an already-set `AWS_PROFILE` / already-exported AWS creds (`load_dotenv(override=False)` is already the default — the real issue is the `.env` exporting static AWS keys at all); (b) move the static personal-account AWS keys OUT of the repo `.env` so nothing re-injects them (use a profile for local DynamoDB too); (c) a shared `ops_env` helper that establishes the correct account/endpoint and is import-safe. Add a test that importing `database` does not mutate pre-set AWS_* env.

**Scope:** `backend/src/database.py` (the import-time `load_dotenv()`), repo-root `.env` (static AWS keys), steering `41-shell-environment.md` (already warns about the `.env`-overrides-`AWS_PROFILE` hazard — this is the concrete code cause). Relates to the "Projection version gap" item above (both bite the same prod-projection path).


# Your main branch isn't protected
Protect this branch from force pushing or deletion, or require status checks before merging. View documentation. See https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets

# Optional follow-ups I can do, just say which:

Fix scalability_manager.py (pool_recycle + pool_size=50→≤32) so the startup error disappears and the multi-pool path is safe if ever re-enabled.
Route logging to stdout so Railway stops labeling INFO lines as errors.


# Stale TEST_MODE / testfinance in system_health_routes.py (contradicts the APP_ENV model)
**Problem (found during test-environment Phase 6 Task 44 env-var audit, 2026-10-03):**
`backend/src/routes/system_health_routes.py` still reads the legacy `TEST_MODE` env var and
`TEST_DB_NAME` (default `testfinance`) to report the active database name in its health/environment
diagnostics (two spots: `use_test = os.getenv("TEST_MODE", "false").lower() == "true"` ->
`os.getenv("TEST_DB_NAME", "testfinance")`, plus a `"TEST_MODE": os.getenv("TEST_MODE", ...)` echo).
This contradicts the model the test-environment spec established and the rest of the backend already
follows: there is **no `test_mode` flag** and **no `finance`/`testfinance` schema split** -- the schema
is always `finance`, and TEST vs PRODUCTION is a resolved DB **target** selected by `APP_ENV`
(local Docker vs Railway). Phase 3 removed `test_mode` from the real DB path; this diagnostic route
is a leftover that was missed, so the health endpoint can report a `testfinance` DB name that does not
exist and does not reflect how the app actually resolves its target.

**Impact:** misleading diagnostics -- the environment/health report can show a stale `testfinance`
name and a `TEST_MODE` value that nothing else honours, which will confuse anyone debugging a TEST vs
PROD DB-target issue (the exact kind of confusion the APP_ENV model was meant to end). Low functional
risk (diagnostic-only), but it keeps a retired concept alive in a user-facing status endpoint and
re-introduces the `testfinance` term the steering/`#database` skill were updated (Phase 5 Task 29) to
remove.

**Proper fix:** make `system_health_routes.py` report the RESOLVED target instead of the legacy flag --
derive the environment + DB name from the Environment_Resolver / `ResolvedConfig` (schema `finance`,
target label TEST/PRODUCTION from `APP_ENV`), the same way `environment/health_report.py` already does.
Drop the `TEST_MODE` / `TEST_DB_NAME` / `testfinance` reads from this route. Add/adjust a test that the
health report names the resolved target and never emits `testfinance` or a `TEST_MODE` field.

**Scope:** `backend/src/routes/system_health_routes.py`; cross-check `environment/health_report.py`
(the canonical, already-correct implementation to mirror). Relates to the test-environment spec
(`.kiro/specs/Common/test-environment/`) Phase 3 `test_mode` removal + Phase 5 steering alignment, and
is recorded as finding #1 in that spec's `env-var-audit.md`.

Note (same audit, lower priority): the Google-Drive `TEST_MODE` folder toggle
(`TEST_FACTUREN_FOLDER_ID` in `google_drive_service.py` / `output_service.py` /
`missing_invoices_routes.py` / `folder_routes.py` / `seed_tenant_parameters.py`) is a SEPARATE,
still-legitimate flag (orthogonal to `APP_ENV`), but is a candidate to fold into the resolver later so
there is ONE environment selector. Not part of this bugfix.


# CodeQL backlog — 30 pre-existing open code-scanning alerts (triage + fix)
**Context (surfaced 2026-10-03 while handling a GitHub CodeQL email on PR #66):** the email's
`py/clear-text-logging-sensitive-data` alert on `scripts/test-environment/provision-test-account.py`
is ALREADY FIXED/closed (password generation+printing was removed in `94c45f2`; the current file
requires `--password` and never logs it). No action needed there. BUT querying
`repos/PeterGeers/myAdmin/code-scanning/alerts?state=open` revealed **30 OTHER pre-existing open
alerts** unrelated to that PR's diff — recorded here for triage. None block current merges (they are
not on changed lines), but they are real findings.

## The 30 open alerts, grouped by rule

**1) `py/stack-trace-exposure` — 27 alerts (raw exception/stack text returned to the client).**
A route returns the exception/stack trace in the HTTP response, leaking internal detail to callers.
Files (alert #s):
- `backend/src/admin_routes.py` — #1228–#1236 (9)
- `backend/src/routes/tenant_admin_users.py` — #1245–#1248 (4)
- `backend/src/routes/sysadmin_roles.py` — #1237–#1240 (4)
- `backend/src/routes/str_routes.py` — #1250–#1253 (4)
- `backend/src/routes/tenant_admin_roles.py` — #1242–#1243 (2)
- `backend/src/routes/tenant_admin_credentials.py` — #1258 (1)
- `backend/src/routes/tenant_admin_scope.py` — #1244 (1)
- `backend/src/routes/tenant_admin_email.py` — #1241 (1)
- `backend/src/reporting_routes.py` — #1257 (1)
- `backend/src/routes/aangifte_ib_routes.py` — #1256 (1)
**Proper fix:** return a generic error body to the client (e.g. `{"error": "internal error"}` + a
correlation id) and log the detail server-side only. This is a cross-cutting error-handling pattern,
not 27 independent edits — ideally one shared error handler / Flask `errorhandler` so the fix is
systemic and future routes inherit it. Candidate for its own small security-hardening spec.

**2) `py/clear-text-logging-sensitive-data` — 1 alert.**
- `scripts/onboarding/members/_generic/load-cognito-users.py` — #1249. A sensitive value (likely a
  password/credential) is logged in clear text. Same class as the already-fixed provisioner finding;
  apply the same remedy: never print/log the secret (require it as input, don't echo it).

**3) `actions/missing-workflow-permissions` — 1 alert.**
- `.github/workflows/full-test-suite.yml` — #1227. The workflow has no explicit least-privilege
  `permissions:` block, so it inherits broad default token perms. **Proper fix:** add a top-level
  `permissions: { contents: read }` (tighten per-job if any job needs more). Quick, isolated win.
  (Cross-check the other workflows while here — only this one was flagged, but a repo-wide default is
  good hygiene. Relates to the "main branch isn't protected" item above — both are CI/supply-chain
  hardening.)

**Scope / recommendation:** the 27 stack-trace-exposure findings want ONE systemic fix (shared error
handler) — spec it rather than patch piecemeal. The 2 isolated ones (workflow permissions block;
load-cognito-users clear-text log) are quick wins that could be done independently. Relates to steering
`43-cicd-deploys.md` (CI security gates: "CodeQL must be green") — these pre-date that gate.


# SPEC CANDIDATE: Secret & config management is inconsistent across planes
**Problem (observed 2026-10-10 during the Members mail/pivot prod release):** the SAME class of
problem — "how does a value (a secret, or a piece of config) get to the code that needs it" — is
solved with DIFFERENT tools in different parts of the codebase. There is no single documented
convention, so each plane/spec reinvented it. This makes rotation, auditing, and onboarding harder
and the differences are accidental, not designed.

## Concrete evidence — the OpenRouter API key alone is handled THREE ways
One secret, three mechanisms:
- **Flask / Railway plane:** `OPENROUTER_API_KEY` is a **Railway service variable**, read at runtime
  via `os.getenv(...)` (e.g. `backend/src/image_ai_processor.py`, `services/budget_ai_service.py`,
  `services/ai_template_assistant.py`, `pdf_ai_extraction.py`, `routes/sysadmin_health.py`). Declared
  in `backend/validate_env.py`.
- **SAM Members plane:** same key is a **GitHub Actions repo secret** → passed by
  `deploy-sam-members.yml` as a CloudFormation **`NoEcho` template parameter** (`OpenRouterApiKey`,
  `sk-or-v1-` AllowedPattern) → wired into the Lambda **env var** `OPENROUTER_API_KEY`
  (`sam/members/template.yaml`), read fail-fast by `sam/members/domain/ai_improve.py`.
- **Frontend:** surfaces the "Improve with AI" button only; holds NO key — calls the SAM API
  (`POST /members/templates/{id}/ai-improve`). (Correct — a browser must never hold the key.)

Note: we are **NOT** using AWS Secrets Manager / SSM SecureString anywhere for this — the SAM key
lives as a Lambda env var (in the function config + CFN deploy history), not fetched at runtime.

## The broader pattern to inventory (same "different tools, same problem" smell)
- **Secrets at rest:** Railway vars vs GitHub secrets vs CFN NoEcho→Lambda env vs (nowhere) AWS
  Secrets Manager/SSM. Which should be canonical? When is Secrets Manager worth the IAM/rotation cost?
- **Non-secret config/env selection:** Flask `.env` + `DB_*`/`APP_ENV` resolver; SAM `samconfig.toml`
  `[test]`/`[prod]` parameter_overrides; frontend `VITE_*` build-time env. Three env-selection models.
- **Tenant config values:** MySQL `parameters` table (namespace/scope/scope_id) projected into
  DynamoDB `config#*` rows — vs the above. (This release even needed a manual local→Railway copy of
  5 `members.*` rows because config authored in TEST never reached PROD — a symptom of no convention
  for "promote tenant config between environments".)

## Why a spec later, not a fix now
Converging these is cross-cutting (Flask + SAM + frontend + IAM + steering) and risky to retrofit on
a live secret path. Scope it deliberately:
1. **Inventory** every secret + config value and how each is sourced per plane (read-only sweep:
   `validate_env.py`, Railway vars, all `samconfig.toml`, `template.yaml` params, `VITE_*`, any
   Secrets Manager/SSM usage).
2. **Decide the canonical tool(s)** per category (runtime secret / deploy secret / env selection /
   tenant config promotion) and write it into steering.
3. **Migrate the outliers** incrementally; don't big-bang the prod secret path.

Relates to: steering `43-cicd-deploys.md` ("no secrets in CI"), `41-shell-environment.md` + the
`#database` skill (env model), and possibly the open `.kiro/specs/Members/Parameter redesign/`
analysis. Also connects to the open "s3 object management module and SAM" + shared-building-blocks
backlog items (same reuse-across-planes theme).

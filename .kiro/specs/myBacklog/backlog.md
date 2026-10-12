
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
> MOVED (2026-10-12) → `.kiro/specs/Members/Parameter redesign/analysis.md` §2.4 (the typed-vs-raw
> namespace-editor model now lives next to the Members dual-surface #12 it shapes). The platform-wide
> admin-surface registry that makes "Advanced" a registered catch-all surface stays this spec's
> concern — see the SCOPE line below ("the generic namespace param editor").

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
> MOVED (2026-10-12) → `.kiro/specs/Members/Parameter redesign/impact-analysis.md` §0.3 + Phase 0
> step 2. This is the "version-bump trap" the spec already owns (the `_scope_config_version`
> tenant-row-proxy defect that silently drops `members.*` edits). The spec covers the proper fix
> (per-param revision, Phase 0 step 2) and goes further — adding a read-side delivered/loaded
> status (Phase 0 step 3) so stale/failed syncs are diagnosable. The field evidence
> (`written=0 skipped=15` on h-dcn) and the committed interim runner
> (`scripts/aws/project-config-to-prod.py`, which refuses success on `written==0`) are preserved
> in that §0.3 note. The runner's `_restrip_aws_env()` dependency stays the SEPARATE backlog item
> below ("load_dotenv() clobbers AWS_PROFILE").




# Passkeys fails again. has been resolved more times
Nog geen passkeys geregistreerd. Registreer er een voor sneller en veiliger inloggen.

Aanmelden mislukt
Passkey registreren mislukt. Probeer het opnieuw.

# load_dotenv() in database.py clobbers AWS_PROFILE → ops scripts silently hit the WRONG AWS account
> PROMOTED TO BUGFIX (2026-10-12) → `.kiro/specs/BUGS/20261012 load_dotenv clobbers AWS_PROFILE/analysis.md`.
> Decided fix: **(a) remove the import-time `load_dotenv` side-effect in `database.py` + (b) strip
> the static personal-account AWS keys from both `.env` and `backend/.env`** (option (c) ops-env
> helper rejected). Grounded re-check found the earlier `backend/.env` pin only MOVED the clobber
> (both files still export the static keys; `backend/.env` also exports the local DynamoDB
> endpoint), and that the local-DynamoDB path already defaults creds to `"local"` so (b)'s blast
> radius is small. This is the **prerequisite gate** before the Members `Parameter redesign` Phase 0
> (whose committed `project-config-to-prod.py` runner carries a `_restrip_aws_env()` workaround for
> THIS bug). Stays a standalone infra bugfix — NOT folded into the redesign.


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


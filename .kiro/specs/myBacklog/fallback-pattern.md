# SPEC: Fail-loud integrity — kill silent fallbacks + reconcile stale projection + post-deploy pre-checks
**One spec — the projection-reconcile gap is an INSTANCE of the fallback pattern ("trust a
stale/derived value instead of failing/resyncing"), so they share a design.** Raised by the user
2026-09-23: *"many of these fallbacks create a mess ... a separate issue broader than the
token/claim issue ... address it as part of the code-quality exercises."*

## Part A — Silent fallbacks hide misconfiguration (the mess)
Across the stack, when a value is missing/ambiguous the code silently substitutes a "reasonable"
default instead of failing loudly. Individually harmless; in aggregate they HIDE real
misconfiguration and make "why is it empty/wrong?" undiagnosable — the failure surfaces far from
its cause (empty lists, wrong-tenant data), never as an error.

Concrete instances seen (evidence, not speculation):
- **Frontend API base URL fallback → localhost.** Deployed SPA baked WITHOUT
  `VITE_MEMBERS_API_BASE_URL` fell back to `127.0.0.1:3000` → prod called localhost, showed no
  members, no error (fixed PR #16). Default masks missing config.
- **Roles fallback in `getCurrentUserRoles()`** — `/api/auth/me` (MySQL merged roles) then FALLS
  BACK to `cognito:groups` on failure. Two sources of truth; on divergence the UI silently trusts
  whichever answered.
- **Active-tenant "default to first tenant"** — the SAM edge (s5f) deliberately rejected this
  (deny, don't default) because a silent default exposes WRONG-TENANT data. The same "just pick
  one" instinct may live in other paths (select-never-default).
- **`.env` static AWS keys overriding `AWS_PROFILE`** (steering 41) — a credential "fallback"
  chain that silently runs against the WRONG account (`ResourceNotFoundException` instead of
  "wrong creds").

## Part B — Stale projection rows are never reconciled (a security-relevant instance)
Found during s5d C.12. `ProjectionSync.sync_administration`
(`backend/src/services/projection_sync.py`) only diff-deletes obsolete `scopegrant#` rows
(`_reconcile_scopegrants`); its docstring notes `tenant`/`module#*`/`role#*`/`config#*` are
"never listed and never deleted." Consequence: a role REMOVED from MySQL `user_tenant_roles`
leaves a STALE `role#<email>#<role>` row in `governance_projection` indefinitely — the projection
keeps advertising a role the source no longer grants (SECURITY-relevant staleness). Real example:
prod `h-dcn` had 3 orphaned role# rows with no MySQL source (`Regio_All`, a `h-scn` typo'd
Tenant_Admin, a `member-test@example.com` row) — cleaned up manually in C.12. The
capability path reads the projection (`has_capability` off `custom:entitlements`), so a stale
`role#` row can INFLATE a resolved entitlement once the PreTokenGen trigger is live — worth
fixing early (likely the FIRST phase of this spec given the security angle).
- Options: extend the reconcile to `role#` (and consider `module#`) with the same
  diff-and-delete pattern, scoped per tenant; OR a periodic reconciliation sweep.

## Direction (needs a design pass — do NOT blind-patch)
- **Inventory** every fallback/default in the request/auth/config paths (frontend + Flask + SAM
  edge). For each: SAFE degenerate case, or MASKING a missing input?
- **Fail loud on missing REQUIRED config** — missing API base URL, missing tenant selection for a
  multi-tenant user, missing entitlement → explicit error at startup/at the edge, not a silent
  substitution. (s5f is the template: select-never-grant, deny-don't-default.)
- **Single source of truth** — remove the roles double-read fallback (MySQL-merged authoritative;
  treat `cognito:groups` divergence as an error to surface).
- **Reconcile derived data** — Part B: no stale projection rows advertising removed capabilities.
- **Post-deploy pre-checks** — after a deploy, verify parameters/config availability (API URLs,
  required env vars, projection freshness) so a missing input is caught at deploy time, not as an
  empty screen in prod.
- **Guard rails** — extend the "no fallback tenant symbol in live code" grep guard (s5f R4.3) into
  a broader lint for known fallback anti-patterns.
- SCOPE: cross-cutting code-quality; own spec. Relates to steering 41, s5f (ADR 0007).

## Part C — generic-vs-tenant placement: converge on ONE selection pattern (investigated 2026-09-24)
Where behavior differs per tenant, converge on ONE pattern — a CONFIG value (or per-tenant data)
selects a registered GENERIC handler — NOT per-tenant code branches. Classification: (A) tenant-name
branch [anti-pattern] · (B) registry keyed by tenant · (C) config-value selects handler · (D)
parameter-driven data. Findings (read-only, both planes):
- **(A) is ABSENT on the Flask plane** — no hardcoded real tenant names, no `if administration ==
  "<tenant>"` in `backend/src/**` (`administration == "all"` is a UI "all my tenants" data filter,
  not a branch; `h-dcn`/`hdcn` appear only on the SAM plane). So alignment is ADDITIVE, not cleanup.
- **Flask tenant-admin functions are GENERIC services parameterized by `administration`** (D),
  gated by three data-driven registries: `MODULE_REGISTRY` + `tenant_modules`
  (`services/module_registry.py`; also a (C) dispatch — `module_backing`/`resolve_module_api_base`
  route MEMBERS to SAM by module name); `FUNCTION_REGISTRY` + `tenant_functions` +
  `TenantFunctionService` (D toggles); `ParameterService` + `parameter_schema.py` (D config store),
  `FieldConfigMixin` (D field overlay — the analogue of the SAM `overlay_provider`).
- **The proven (C) TEMPLATE** already exists: `services/storage_resolver.py::resolve_storage_provider`
  reads the `storage.invoice_provider` param and dispatches to the storage handler. Copy this shape
  for any future config-selected behavior.
- **SAM plane** uses `TenantHookRegistry` keyed by `(HookName, tenant_id)` with safe defaults
  (`sam/members/domain/tenant_hooks.py`) — selection is tenant-in-code via a registry (B); the core
  never branches on tenant (Property 5).
- **CONVERGENCE RULE (record as steering — cf. `36-config-and-parameters.md`):** new tenant-specific
  behavior lands as (C) a config-selected generic handler by DEFAULT; only truly un-configurable
  logic uses (B) a tenant-keyed hook registry; NEVER (A) a tenant-name branch; data differences stay
  (D). (Steering 36 already states this order — Part C is the evidence + audit behind it.)

## Deliverables

These are what this spec produces if implemented. They map straight onto Parts A–C and the
Direction list above; each is phrased as a concrete artifact so the spec can be scoped and
verified. Ordering reflects the security-first note in Part B (do the projection reconcile early).

### 1. Fallback inventory + classification (from Part A "Inventory")
- A written audit table of every fallback/default in the request / auth / config paths across
  the three planes (frontend SPA, Flask backend, SAM edge). For each entry: location, the input
  it substitutes for, and a verdict — **SAFE degenerate case** vs **MASKING a missing input**.
- This is the design artifact that decides which of the code changes below are actually needed;
  nothing gets blind-patched (per the "needs a design pass" note).

### 2. Stale-projection reconcile (Part B — first implementation phase, security-relevant)
- Extend `ProjectionSync` in `backend/src/services/projection_sync.py` so it diff-deletes stale
  `role#<email>#<role>` rows (same pattern as the existing `_reconcile_scopegrants`), scoped per
  tenant, and a decision recorded on whether `module#*` is included now or deferred.
- A reconciliation mechanism for rows the current sync "never lists" — either inline diff-delete
  or a periodic sweep (the spec lists both as options; the design picks one).
- Regression coverage: a role removed from MySQL `user_tenant_roles` must not leave a lingering
  `role#` row that could inflate a resolved entitlement once PreTokenGen is live.

### 3. Fail-loud on missing REQUIRED config (Part A "Fail loud")
- Startup / edge-time checks that raise an explicit error instead of silently substituting for:
  missing API base URL, missing tenant selection for a multi-tenant user, and missing
  entitlement. Follows the s5f template (select-never-grant, deny-don't-default).
- Removal or hard-failing of the frontend API-base-URL → `localhost` fallback class (the PR #16
  failure mode) so a SPA built without the required var fails visibly rather than calling
  localhost in prod.

### 4. Single source of truth for roles (Part A "Single source of truth")
- Remove the double-read fallback in `getCurrentUserRoles()`: treat the MySQL-merged roles
  (`/api/auth/me`) as authoritative and surface a `cognito:groups` divergence as an **error**,
  not a silent substitution.

### 5. Post-deploy pre-checks (Direction "Post-deploy pre-checks")
- A post-deploy verification step that asserts config/parameter availability (API URLs, required
  env vars) and projection freshness, so a missing input is caught at deploy time rather than
  showing up as an empty screen in prod.

### 6. Guard-rail lint (Direction "Guard rails")
- Broaden the existing "no fallback tenant symbol in live code" grep guard (s5f R4.3) into a
  reusable lint that flags the known fallback anti-patterns catalogued in deliverable #1, so
  regressions are caught in CI.

### 7. Convergence steering for generic-vs-tenant placement (Part C)
- A steering rule (alongside `36-config-and-parameters.md`) recording the CONVERGENCE RULE:
  new tenant-specific behavior defaults to **(C)** a config-selected generic handler; **(B)** a
  tenant-keyed hook registry only for truly un-configurable logic; **never (A)** a tenant-name
  branch; data differences stay **(D)**. Backed by the read-only audit evidence already captured
  in Part C, with `services/storage_resolver.py::resolve_storage_provider` cited as the proven
  (C) template to copy.
- Note from Part C: on the Flask plane pattern (A) is ABSENT, so this deliverable is **additive
  guidance**, not a cleanup task.

### Out of scope / dependencies
- Landing the PreTokenGen trigger itself is a separate effort; deliverable #2 makes the
  projection safe *for* it but does not deliver it.
- This is a cross-cutting code-quality spec related to steering 41 and s5f (ADR 0007); it does not
  change tenant-selection storage or the SAM edge authorization contract.

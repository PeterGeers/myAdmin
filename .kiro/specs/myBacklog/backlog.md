
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

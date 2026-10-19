# Redesign Considerations — Members config: SAM-owned projection records + MySQL cleanup

> Status: considerations / assessment (not yet a task breakdown). Scope locked to Phase 1 (Items A+B+C). Items D + role/scope deferred to a later spec.

## Problem statement
Today all `governance_projection` records are authored on the Flask plane (UI -> MySQL `parameters`/`tenant_modules`/`user_tenant_roles` -> one-directional `ProjectionSync` -> DynamoDB `governance_projection`). SAM reads them read-only and has no config-write path. The goal of this phase is to let the single myAdmin frontend write the Members **tenant-level config** records directly to a new SAM write path, making DynamoDB `governance_projection` the system-of-record for those records, and to retire the corresponding MySQL `members.*` params and `ProjectionSync` config builders.

The "Flask and SAM cannot talk at runtime" rule is preserved: the frontend (one UI plane) talks to each backend plane separately; the planes never call each other.

## Scope (locked)
- **In scope (Phase 1):** `config#scope`, `config#fields`, `config#mail` become SAM-owned. The frontend writes them directly to a new SAM write path. DynamoDB becomes system-of-record for these three rows. MySQL `members.*` params and `ProjectionSync`'s three `config#*` builders are retired.
- **Sender (Item B):** only the Members `config#mail` sender fields (domain / local-part + mail-enabled) move, riding with Item A. Invoice SES verification (`SenderSettingsTab`) stays on the Flask/SES plane, untouched.
- **Advanced params (Item C):** a second (raw namespace) editor VIEW over the SAME SAM write path — not a separate store.
- **Out of scope (deferred to a later spec):** `tenant`, `module#<name>`, `role#<email>#<role>`, `scopegrant#<email>#<dimension>`. These stay MySQL-owned and `ProjectionSync`-written exactly as today.
- **Cognito:** unchanged. Flask provisioning keeps writing `custom:tenants` and user invites. No SAM identity-plane writes in this phase.

## Background / verified findings
These are grounded in the current code (verified during analysis):
- **`ProjectionSync` is the sole writer** of `governance_projection` (`backend/src/services/projection_sync.py`). It is one-directional (MySQL -> DynamoDB); there is NO DynamoDB -> MySQL back-sync. It reconciles on a timer and on every MySQL governance change, and `_reconcile_scopegrants` actively DELETES projection rows it doesn't recognize (scoped to the `scopegrant#` prefix).
- **SAM has no config-write path today.** `sam/members/repository/projection_config_reader.py` is read-only (query only). `GET /members/field-config` is the only config-facing route and is GET-only. The Members Lambda IAM role is READ-ONLY on `governance_projection` (per `sam/members/template.yaml`).
- **The pre-token-gen Lambda already reads the projection, not MySQL** (`sam/pretokengen/handler.py`, `sam/pretokengen/projection_governance_reader.py`; "Design amendment A": no `mysql-connector` in the bundle, no Railway egress). So SAM apps' identity path is already decoupled from MySQL.
- **BUT the Flask plane reads `user_tenant_roles` directly from MySQL at request time** (`backend/src/auth/role_cache.py`) to authorize FIN/invoices/etc. So any dual-plane user's role grants must still exist in MySQL. This is why `role#`/`tenant`/`module#` ownership is deferred — it entangles the identity plane and the dual-plane-user problem. Phase 1 deliberately avoids all of that by moving ONLY the three `config#*` rows that ONLY SAM reads.
- **`custom:tenants` is a Cognito user attribute; SysAdmin is a Cognito group.** Whoever writes tenant membership must write Cognito. Today Flask does; Phase 1 keeps it that way.

## The critical consequence: `governance_projection` becomes a split-ownership table
After Phase 1, one DynamoDB table has two writers, split cleanly by sort-key prefix:
- **SAM writes:** `config#scope`, `config#fields`, `config#mail`.
- **`ProjectionSync` (Flask) still writes:** `tenant`, `module#`, `role#`, `scopegrant#`.

The two writers never touch the same rows — the split is clean by prefix. Three guardrails are required:
1. **`ProjectionSync` must stop emitting `config#*` entirely.** Its `sync_administration` currently builds all three in the same batch as the base rows; those three builder calls (`build_config_scope_row` / `build_config_fields_row` / `build_config_mail_row`) must be removed so a SAM tenant's batch contains only `tenant`/`module#`/`role#`/`scopegrant#`.
2. **The residue-cleanup / delete-sweep must not touch SAM-owned rows.** `ProjectionSync`'s `_reconcile_scopegrants` delete-sweep and the `delete_config_views_residue` path must be confirmed scoped to their own prefixes and must never delete `config#scope`/`fields`/`mail`. A sweep that deletes a SAM-authored config row would silently break a tenant's Members config. **(FLAGGED DESIGN ITEM for execution — verify, do not assume.)**
3. **Versioning ownership transfers.** Today `ProjectionSync` stamps `version` on `config#*` from the MySQL param revision, and the SAM reader uses `version` for staleness. The SAM writer must own a consistent monotonic `version` (e.g. an ISO-8601 updated-at, matching the live `config#scope` row convention) so the reader's staleness logic keeps working unchanged.

## Item-by-item effort & risk

### Item A — Members config write path (core): MEDIUM effort, MEDIUM risk
- New SAM surface: API Gateway routes (existing GET + new PUT/write) -> Lambda handler -> a new config-writer repository doing versioned `put_item` on the three `config#*` keys. Net-new (no config write exists today).
- IAM: grant the Members Lambda role a scoped WRITE on the `config#*` keys of `governance_projection` (currently read-only). Infra change, needs a deploy.
- Frontend rewire: `MembersConfigEditor` + `MembershipTypesManager` currently call Flask `parameter_admin_routes` via `membersConfigService.ts`. Repoint to the new SAM routes. The save-result UX (today shows `projected`/`projection_error`) simplifies — a successful SAM write IS the authoritative state, there is no projection step.
- One-time data migration: copy current `members.*` values from MySQL into the SAM-owned `config#*` rows for every live tenant (h-dcn at minimum), with verification read-back, BEFORE `ProjectionSync` stops writing them.
- Retire: delete the three `config#*` builders from `ProjectionSync`; drop `members.*` params from MySQL (retire, not freeze).
- Risk drivers: the dual-writer guardrails above; migration cutover ordering (write SAM first, verify, then remove the Flask builder in the same change per the change-with-tests contract); versioning continuity.

### Item B — Sender fields: LOW effort, LOW risk
Rides inside Item A's `config#mail` write. The only real work is NOT touching the invoice SES verification path. **FLAGGED DESIGN ITEM:** confirm whether the UI surface that should move is `MemberSenderIdentitiesTab` (member sender) vs leaving `SenderSettingsTab` (invoice SES verification) alone. The "double things pointing to one item" the user noticed resolves here: invoice SES verification and the Members sender are genuinely different concerns sharing the word "sender"; only the Members one is in scope.

### Item C — Advanced / raw namespace view: LOW effort (given A), LOW-MEDIUM risk
A second editor VIEW over Item A's write path (the user's backlog already notes "Advanced + Members config — one thing at two polish levels"). Risk: it must not offer a conflicting second way to write the same `config#mail` keys as the sender view. One writer, two views: both the typed editor and the raw editor post to the single write API.

## TEST -> PROD config promotion + CI/CD to main (in scope for Phase 1)
The user's backlog already records that config authored in TEST never reached PROD (a manual 5-row `members.*` copy). Moving to SAM-owned config is the moment to fix this rather than repeat it.
- The SAM write path must work against BOTH `test_governance_projection` (TEST) and `governance_projection` (PROD), resolved via `GOVERNANCE_PROJECTION_TABLE` (fail-fast, no default).
- There must be a deliberate promotion story: either (a) a copy/promote path TEST -> PROD for the `config#*` rows, or (b) direct per-environment authoring with an explicit promote step.
- **CI/CD to main:** the promotion/cutover must fit the existing deploy pipeline (steering `43-cicd-deploys.md`: CodeQL must be green, no secrets in CI). Consider: the IAM write-grant change and the new SAM routes ship via the SAM deploy workflow (`deploy-sam-members.yml`); the frontend rewire + `ProjectionSync` builder removal ship via the Flask/full-test-suite path. The migration (MySQL -> SAM copy) is an operational step that must be ordered relative to the merge-to-main that removes the Flask builders — SAM must be live and verified in PROD BEFORE the merge that stops `ProjectionSync` writing `config#*`, or tenants lose their config between deploy and migration. Document the required ordering as part of the promotion design. Note also the related open backlog item "Your main branch isn't protected" — branch protection / required status checks on main are a prerequisite hygiene item for a cutover of this blast radius.

## Cross-cutting risks (whole phase)
- **Rollback story.** Once MySQL `members.*` is dropped and `ProjectionSync` stops writing `config#*`, reverting means re-seeding MySQL and the builder. Keep the migration reversible (don't drop MySQL params until SAM is verified live in PROD) even though the end-state deletes them.
- **Change-with-tests contract (workspace rule).** Retiring the three builders and the `members.*` params is a behavior change with allocated tests: `ProjectionSync` property/preservation tests that currently assert `config#*` rows are emitted must be updated to assert they are NOT; SAM reader tests must point at SAM-authored rows. These move in the SAME change, not after.
- **Account/region.** All writes target `nonprofit-deploy` (506221081911), `eu-west-1`. No identity-account involvement this phase (Cognito stays on Flask), keeping the IAM blast radius small — a genuine benefit of deferring Item D.

## What stays reassuringly unchanged
- Pre-token-gen Lambda: zero changes — it reads `role#`/`module#`, which stay MySQL-fed.
- SAM edge entitlement check: unchanged.
- Flask `role_cache` / FIN / invoices authorization: unchanged — none read `config#*`.
- "Flask and SAM cannot talk at runtime": preserved.

## Bottom line
Phase 1 (A+B+C) is a contained, defensible change: SAM takes ownership of exactly the three rows only SAM reads, so there is no identity entanglement and no dual-plane-user problem (those live entirely in the deferred D + role/scope work). The real engineering is (1) the net-new SAM write path + scoped IAM grant, (2) the clean hand-off from `ProjectionSync` to SAM for `config#*` with the delete-sweep and versioning guardrails, and (3) the migration + TEST->PROD promotion cutover ordering relative to CI/CD to main. Effort: roughly a medium spec. Risk: medium, concentrated in the cutover / dual-writer mechanics rather than in identity or cross-plane coupling.

## Flagged design items to resolve in the execution phase
1. Confirm `ProjectionSync`'s delete-sweep (`_reconcile_scopegrants`) and residue cleanup never touch `config#scope`/`config#fields`/`config#mail`.
2. Confirm which sender UI tab moves: `MemberSenderIdentitiesTab` (likely) vs `SenderSettingsTab` (invoice SES — stays).
3. Choose the TEST->PROD promotion mechanism (copy/promote path vs per-environment authoring + promote step) and document the cutover ordering vs merge-to-main.

---

## Option D — split into Phase 2 (possible) and Not possible (stays Flask/MySQL-owned)

Option D is "manage the identity/governance records (`tenant`, `module#<name>`, `role#<email>#<role>`, `scopegrant#<email>#<dimension>`) on the SAM plane." Analysis (code-verified) shows it is NOT one thing — it splits cleanly into a movable part and an irreducible part.

The guiding distinction: **per-module data** (what a module reads — role grants, scope grants) can be plane-routed to the module's owning plane. The **pre-module gate** (tenant existence + module enablement + Cognito membership) is read by the platform's authorization layer *to decide which modules/roles even apply*, so it cannot "decode per plane" — it is read before any single module's plane is selected.

### Per-record verdict (verified against the code)

| Record | Movable to SAM? | Why |
| --- | --- | --- |
| `scopegrant#<email>#<dimension>` | **Yes — clean (Phase 2)** | No Flask request-time reader. The Flask plane only AUTHORS `user_tenant_scope` and PROJECTS it; enforcement (deny-by-default on scope dimensions) is entirely SAM-side. Already Members-specific (a `module` column, filtered to MEMBERS). Moves end-to-end with zero Flask breakage. |
| `role#<email>#<role>` | **Yes, conditional (Phase 2)** | Role names ARE disjoint by module/plane (`Members_*` → MEMBERS/sam; `Finance_*`/`STR_*`/`ZZP_*` → flask; globals `SysAdmin`/`Administrators`/`System_CRUD`/`Tenant_Admin` are not module roles). So a sort-key partition `role#…#Members_*` → SAM vs the rest → Flask is unambiguous. BUT two Flask readers assume MySQL `user_tenant_roles` is COMPLETE and would under-report SAM-only Members roles: (1) the tenant-admin manage-users view `list_tenant_users`; (2) the Flask entitlement FALLBACK `resolve_capabilities_from_db`. The fallback is narrow — the normal path prefers the verified token claim (already built from the projection by the pre-token-gen Lambda), so it only fires when the token has no answer. Movable IF those two readers are made projection-aware (or Flask views accept that they omit Members roles). |
| `module#<name>` | **No — stays Flask/MySQL-owned** | MySQL `tenant_modules` is the LIVE authorization gate: `has_module` / the `module_required` decorator read it directly on every gated Flask request. The SysAdmin module-management view (`get_tenant_modules`) and the entitlement fallback also enumerate modules from it. A module enabled only in SAM would make the Flask plane treat it as NOT enabled. And module enablement is what gates roles (`required_roles` count only when the module is active). Foundational, read as system-of-record by Flask's own authorization. |
| `tenant` | **No — stays Flask/MySQL-owned** | Pre-module. It is the FK target for MySQL `user_tenant_roles.administration`, and tenant membership is carried by the Cognito `custom:tenants` attribute, which the pre-token-gen Lambda reads to decide which tenant partitions to query AT ALL (before any module/role). Creating a tenant inherently requires a Cognito (identity-plane) write, not a DynamoDB write. Gates every plane, SAM included. |

### Phase 2 (possible) — the movable part of D
Move `scopegrant#` (clean) and `role#` (with the two-reader rework above) to SAM ownership, using the same prefix-scoped split pattern Phase 1 uses for `config#*`:
- SAM owns and writes `scopegrant#<email>#<dimension>` and `role#<email>#Members_*`.
- `ProjectionSync` stops writing exactly those rows (and its delete-sweep must not touch SAM-owned prefixes — same guardrail family as Phase 1).
- For `role#`, decide the policy for the two Flask MySQL readers: either make `list_tenant_users` + `resolve_capabilities_from_db` projection-aware for Members roles, or accept that those Flask views do not display Members roles (the SAM plane remains authoritative via the token).
- Pre-token-gen Lambda: unchanged — it already reads `role#`/`scopegrant#` from the projection regardless of who wrote them.

### Not possible — stays Flask/MySQL-owned (SAM reads via the projection as today)
`tenant` and `module#<name>` remain authored on the Flask plane (MySQL + Cognito), projected one-directionally into `governance_projection`, and read by SAM read-only — exactly as today. A SAM SysAdmin surface could DISPLAY these (reading the projection) but must not become their writer. Tenant creation + user invite (the Cognito `custom:tenants` write) and module enablement (`tenant_modules`, the live Flask gate) stay a Flask/identity responsibility, because Flask's own authorization reads them as system-of-record and they gate all planes before any module is selected.

### Net framing
- **Phase 1 (this spec):** `config#scope` / `config#fields` / `config#mail` → SAM-owned.
- **Phase 2 (later spec, possible):** `scopegrant#` (clean) + `role#` Members slice (with reader rework) → SAM-owned.
- **Not possible / permanent Flask-MySQL ownership:** `tenant` + `module#<name>` — the pre-module gate, projected to SAM read-only.

The insight that drives the split: "a module decodes where to read" is true for per-module data (roles, scope) but NOT for the pre-module gate (tenant existence, module enablement, Cognito membership), which is read by the platform's authorization layer to decide which modules/roles apply in the first place.

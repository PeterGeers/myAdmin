# Implementation Plan

## S5c — Members-runnable-in-SPA (representative pilot, proven dev/test → prod) — Tasks

- Requirements: `./requirements.md` · Design: `./design.md` · Analysis (settled): `./analysis.md`
- Reuse: s5 domain (`../s5-members-first-migration/`), s5b plumbing/frontend
  (`../s5b-members-runnable-in-spa/`), S4 PreTokenGen Lambda (`sam/pretokengen/*`).
- Legend: `[ ]` todo · `[H]` human-run / gated (deploy, Cognito, prod) · `(dt)` dev/test-first ·
  each task cites the Requirement(s) + design Component it implements.
- **Ordering rule (steering 23):** everything runs in **dev/test first**; prod steps are
  explicitly gated `[H]` and only after the dev/test proof passes. No table drops in any step.

## Execution rules — steering to FOLLOW while doing the work (not just to update at close-out)

The executor SHALL read and comply with these steering files **as binding inputs** while performing
every task (they govern *how* the work is done; task 8.2 separately updates the ones s5c *changes*):

- **`.kiro/steering/41-shell-environment.md` — READ FIRST, applies to EVERY command.** This is a WSL
  workspace. Non-negotiables when running anything in Phases 0/2–7:
  - **Path split:** file/read/list/validate tools use the **UNC** path
    (`\\wsl.localhost\Ubuntu\home\peter\projects\myAdmin\...`); the **bash/terminal** tool uses the
    **POSIX** path (`/home/peter/projects/myAdmin/...`). Never cross them.
  - **Always bash/Linux commands**; never `wsl -d Ubuntu`, PowerShell, or Windows cmd. Never use the
    terminal `cwd` param — use an **inline POSIX `cd`** (`bash -lc 'cd /home/peter/projects/myAdmin && …'`).
  - **Exit code is always reported as `-1` — that is NOT failure.** Judge success by stdout/stderr +
    an in-band marker: append `; printf '\n<<<DONE marker=%s>>>\n' "$?"` and read `marker=0`.
  - **Empty/absent output ≠ failure and ≠ finished** — wait for the `<<<DONE marker>>>`; do not
    blindly re-run a mutating command.
  - **Never run long-running processes in the foreground** (dev servers, `sam local start-api`,
    `docker compose up`, watchers) — use `control_bash_process` / background. See
    `42-local-dynamodb-testing.md`.
  - **Pagers are disabled** (`PAGER=cat`, `AWS_PAGER=""`); AWS CLI uses `--output json`
    (+ belt-and-suspenders `--no-cli-pager`). Python venv at `backend/.venv`
    (`source backend/.venv/bin/activate`). Scratch/logs under `.agent-output/` (git-ignored); prefer
    streaming stdout over log-file round-trips.
- **`.kiro/steering/42-local-dynamodb-testing.md`** — local topology (Docker network `myadmin-local`,
  `dynamodb-local`, `sam local start-api` joined to the network) for Phases 5/6.
- **`.kiro/steering/23-aws-accounts.md`** — AWS accounts/profiles/regions + tables-outside-CFN/retain
  for Phases 5/7 (identity `personal`/344561557829; data `nonprofit-deploy`/506221081911; `eu-west-1`).
- **`.kiro/steering/31-backend-database-flask-mysql.md`** — `DatabaseManager` / dialect helpers /
  parameterized queries / `administration` tenant scoping for all Flask-plane work (Phases 2/6).
- **`.kiro/steering/35-sam-module-architecture-sam.md`** — SAM-plane layering (thin handler → domain →
  repository; `tenant_id` + `LeadingKeys`) for module work (Phases 1/3/4).
- **`.kiro/steering/32-frontend-ui.md`** — table/modal/i18n + BankingProcessor pattern for the SPA
  (Phases 2/3/4). **`33-frontend-testing.md` / `34-backend-testing.md`** — test conventions + PBT
  exclusions for every test task. **`22-authentication.md` / `21-identity.md`** — verified-JWT rules
  for the edge + PreTokenGen (Phases 0/5).
- **`.kiro/steering/40-spec-workflow.md`** — the workflow + the governance definition-of-done (task 8.2).

## Overview

s5c is delivered in 9 phases. Phase 0 unwinds the s5b shortcuts to a clean baseline. Phases 1–4
build the representative, parameter-driven member surface + the `members.*` authoring UI on the
Flask plane (module reads via the projection). Phase 5 switches on the PreTokenGen capability
channel in dev/test; Phase 6 runs the full provisioning playbook in dev/test; Phase 7 is the gated
PROD cutover proving the CI/CD path; Phase 8 ships docs + governance close-out. Phases 1–4 and
Phase 5 are largely independent and converge at Phase 6.

## Task Dependency Graph

Waves group tasks that can proceed in parallel; each wave completes before the next. Phase 0 is the
baseline; the field-model → authoring → view-contexts → surface chain (Phases 1–4) runs alongside
the PreTokenGen channel (Phase 5); both converge at provisioning (Phase 6), then the gated prod
cutover (Phase 7) and close-out (Phase 8).

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1", "0.2", "0.3", "0.4", "0.5"] },
    { "id": 1, "tasks": ["0.6", "1.1", "5.1"] },
    { "id": 2, "tasks": ["1.2", "1.3", "1.4", "1.4a", "1.4b", "1.4c"] },
    { "id": 3, "tasks": ["1.5", "2.1"] },
    { "id": 4, "tasks": ["2.2", "2.3", "2.4"] },
    { "id": 5, "tasks": ["2.5", "2.6"] },
    { "id": 6, "tasks": ["2.7", "3.1"] },
    { "id": 7, "tasks": ["3.2", "3.3"] },
    { "id": 8, "tasks": ["3.4", "3.5"] },
    { "id": 9, "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7"] },
    { "id": 10, "tasks": ["4.8", "5.2"] },
    { "id": 11, "tasks": ["5.3"] },
    { "id": 12, "tasks": ["5.4", "5.5", "5.6"] },
    { "id": 13, "tasks": ["6.1", "6.2", "6.3", "6.4"] },
    { "id": 14, "tasks": ["6.5", "6.6"] },
    { "id": 15, "tasks": ["7.1"] },
    { "id": 16, "tasks": ["7.2", "7.3"] },
    { "id": 17, "tasks": ["7.4"] },
    { "id": 18, "tasks": ["7.5", "7.6", "7.7"] },
    { "id": 19, "tasks": ["7.8"] },
    { "id": 20, "tasks": ["8.1", "8.2", "8.3"] }
  ]
}
```

- Phase 1 → 2 → 3 → 4 is a strict chain (each needs the prior's output).
- Phase 5 depends only on Phase 0 and runs in parallel with 1–4.
- Phase 6 depends on Phases 2–5 (authoring + surface + real capability channel).
- Phase 7 (`[H]`, gated) depends on Phase 6 (dev/test proof passed). Phase 8 depends on Phase 7.

## Tasks

---

## Phase 0 — Baseline + unwind the s5b shortcuts

> Get to a clean, honest starting point before wiring the real channel. No new behavior yet.

- [x] **0.1 Remove the capability fallback.** Delete `_local_dev_group_grants_capability` and the
  `MEMBERS_LOCAL_AUTH_FALLBACK` env from `sam/members/handler/app.py` + `env-vars.local.json`.
  Grep-clean: no code path derives a Members capability from `cognito:groups`. _(R6.1, C-UNWIND;
  Property 5)_
- [x] **0.2 Remove the tenant fallback.** Delete `MEMBERS_LOCAL_TENANT_ID` and its substitution;
  tenant resolves from the verified entitlement only. _(R6.2, C-UNWIND)_
- [x] **0.3 Remove prod-Pool-A coupling** from `env-vars.local.json` (drop `HDCN_COGNITO_ISSUER =
  eu-west-1_Hdp40eWmu`). _(R2.3, R6.3, C-UNWIND)_
- [x] **0.4 Demote `onboard-hdcn-local.py`** to a data-track fixture (docstring + placement make
  clear it never substitutes for SPA governance onboarding). _(R6.5, C-UNWIND)_
- [x] **0.5 Confirm no per-tenant `Members_*` Cognito group exists** on any pool (the prod one was
  removed 2026-09-19); add a check to the verify script. _(R6.4, C-UNWIND)_
- [x] **0.6 Baseline tests green** after removals (the ~600 module tests + frontend suite) — the
  page will now correctly DENY without a real channel; assert that deny is the expected pre-wiring
  state. _(R12.1)_

**Dependencies:** none. **Deliverable:** clean module edge, fallbacks gone, honest deny.

---

## Phase 1 — Field model: Fixed / Parameter / Calculated (authoring deliverable)

> **The classification table in `design.md` (Data Models → "Field classification table") is the
> SINGLE SOURCE for the field definitions built in this phase.** Every `fixed_fields.py` entry,
> calculated field, and seeded overlay entry is derived **row-by-row** from that table by its
> Classification column. The table drives everything downstream (overlay, view contexts, seed data).
> Traceability rule: each row → exactly one definition in the right place; no field is defined that
> is not a table row, and no table row (except `OUT`) is left unimplemented.

- [x] **1.1 Finalize the classification table** for the h-dcn field set, rebuilt from
  `/home/peter/projects/h-dcn/frontend/src/config/memberFields/`, in `design.md`'s table form:
  Platform key (canonical EN for Fixed/Calculated; tenant-authored for Parameter) · functional Group
  · Classification · h-dcn source key · enum-values/format source. Apply the R4.2 rule (Fixed field
  may have Parameter enum values / format). This table is the authoring contract 1.2–1.4 consume.
  _(R4.1, R4.2, C-FIELDS; design Data Models → classification table)_
- [x] **1.2 Build the Fixed base — one `FixedField` per `Fixed` row** in
  `sam/members/domain/fixed_fields.py` (REFACTOR from ~9 fields), using the table's **English
  canonical `snake_case` keys** + `{nl, en}` labels, `type`, `required`, and storage group
  (`personal`/`membership`). Covers: `first_name`, `last_name`, `name_infix`, `initials`,
  `birth_date`, `gender` (Parameter enum values), `email`, `phone`, `street`, `postal_code`, `city`,
  `country`, `status` (Parameter enum values), `membership_type` (catalog ref), `member_number`,
  `joined_date`, plus system `created_at`/`updated_at`. Keep tenant-agnostic; no h-dcn specifics.
  `member_number` = Fixed **`string`** (never numeric) + tenant format pattern + manual entry (h-dcn's
  counter stays in its `derive_member_number` hook, R4.8). _(R4.3, R4.6, R4.7, R4.8, C-FIELDS)_
- [x] **1.3 Build the Calculated fields — one per `Calculated` row** as derived read-only
  `ResolvedField`s (never stored), with English canonical keys + `{nl, en}` labels and their inputs
  per the table: `display_name` (name parts), `age` + `birthday` (`birth_date`), `years_member`
  (`joined_date`), `application_year` (record creation year). _(R4.4, R4.6, R4.7, C-FIELDS)_
- [x] **1.4 Seed the generic-placeholder overlay — the `Parameter` rows as ILLUSTRATIVE defaults**
  in a `members.field_overlay` sample (`functional_groups` catalog + `fields` + `fixed_overrides`).
  The table's Parameter rows (`guardian_name`; communication prefs; motor `motor_brand`/`motor_type`/
  `build_year`/`license_plate`; `iban`/`payment_method`; `notes`/`signature_date`) are h-dcn's real
  overlay — but the **platform seed uses generic placeholder names** (Field A / Region A), NOT h-dcn's
  list (R4.5). h-dcn authors its real overlay as data at onboarding (Phase 6). `fixed_overrides` seeds
  the functional-group reassignments (e.g. address fields → "address" display group). `region` is a
  scope dimension (`members.scope_dimensions`), NOT the field overlay. `welcome_pack_*` is `OUT`
  (R11.2) — not defined anywhere. _(R4.5, R4.9, C-FIELDS)_
- [x] **1.4a Add the functional-group model** to the domain: extend `OverlayField` with
  `functional_group` and `FixedFieldOverride` with `functional_group`; add a `functional_groups`
  catalog to `TenantOverlay`; `FieldResolver` surfaces `functional_group` on each `ResolvedField`
  (default from the base for fixed/calculated). Storage group (`personal`/`membership`/`overlay`)
  stays fixed by origin — unchanged. _(R4.9, C-FIELDS)_
- [x] **1.4b Member-number format constraint:** keep `member_number` a Fixed `string`; add a
  **tenant-configurable format pattern** (prefix + zero-padded width, e.g. `Nr-0001`, or a regex) to
  its fixed-field config; the domain layer authoritatively validates create/edit/import input against
  the pattern (uniqueness unchanged; generation OUT). _(R4.2, R4.8, C-FIELDS)_
- [x] **1.4c Enum-option model + value-level role gating + `show_when`:** model enum options as
  `{ value, label{nl,en}, roles? }` for both fixed-field enum values and overlay-field `choices`;
  resolve options onto the `ResolvedField`. The **domain layer authoritatively rejects** a create/
  edit that sets an option value the caller's role is not permitted (422/403). Carry a per-field
  `show_when` condition on the resolved field (already in the field-config shape) so hidden fields are
  not required server-side. _(R4.11, R4.12, C-FIELDS)_
- [x] **1.5 Tests + traceability check:** unit for calculated derivations; `FieldResolver` merge over
  the broadened base; Property 2 (config round-trip) extended to the broadened base. **Traceability:**
  assert every classification-table row (except `OUT`) maps to exactly one definition — each `Fixed`
  row → a `FixedField`, each `Calculated` row → a derived field, each `Parameter` row → an overlay
  seed/example — and that no defined field is absent from the table (table ⇄ definitions is total).
  _(R4, R4.10, Property 2)_

**Dependencies:** Phase 0. **Deliverable:** representative field model built row-by-row from the
classification table (Fixed base + calculated fields + seeded overlay), table ⇄ definitions verified.

---

## Phase 2 — `members.*` parameter schema + typed authoring UI (Flask plane)

> The direct fix for "authoring UI unreachable" (analysis B.3). Flask/MySQL plane only.

- [x] **2.1 Declare the `members` namespace** in `backend/src/services/parameter_schema.py`
  (`module: "MEMBERS"` gate) for `field_overlay`, `scope_dimensions`, `view_contexts` (each a `json`
  param). Verify `get_schema_for_tenant([...,"MEMBERS"])` includes it and `parameter_admin_routes.py`
  permits it. _(R3.1, C-SCHEMA)_
- [x] **2.2 Add `backend/src/config/members_parameters.json`** — the typed-editor definitions,
  extending the ledger def language with `list<object>` (scope_dimensions, view_contexts,
  `functional_groups`) and `map<field_def>` (field_overlay, each field carrying `functional_group`).
  _(R3.1, R3.2, R4.9, C-SCHEMA)_
- [x] **2.3 Add `GET /api/config/members-parameters`** in `config_routes.py` (analogous to
  `ledger-parameters`) serving 2.2. _(R3.1, C-SCHEMA)_
- [x] **2.4 Backend save validation:** on PUT of `members.view_contexts`, reject any `field_key` not
  resolvable in the tenant's field set; on `members.field_overlay`, reuse
  `FieldResolver._reject_invalid_overlay` semantics (fail-fast) AND reject any `functional_group` not
  present in the `functional_groups` catalog. _(R5.1a, R4.9, C-SCHEMA/C-VIEW; Property 7)_
- [x] **2.5 Members typed editor UI** in `frontend/src/components/TenantAdmin/` reusing the
  `AccountModal.tsx` renderer, extended for `list<object>` + `map<field_def>`: sub-editors for the
  functional-group catalog, field overlay (each field assigned a `functional_group` from the
  catalog + `fixed_overrides` incl. `functional_group`), scope dimensions, and view contexts.
  **Enum options** are authored as `{ value, label{nl,en}, roles? }` (per-option role restriction,
  R4.12) on fixed-field enum values + overlay-field `choices`. Pickers offer only defined groups /
  resolvable field keys. _(R3.2, R4.9, R4.11, R4.12, C-EDITOR)_
- [x] **2.6 Save-once + unsaved-changes guard:** each sub-editor commits its whole object in one PUT;
  warn on navigate-away with unsaved edits. No draft/publish, no raw-JSON path. _(R3.3, R3.5, R3.6,
  C-EDITOR; Property 8)_
- [x] **2.7 Tests:** namespace gating in `get_schema_for_tenant`; definition endpoint; save-once →
  single `enqueue_sync` (Property 8); dangling-reference rejection for BOTH view-context `field_key`s
  and field `functional_group`s (Property 7); editor rendering of the composite types
  (functional-group catalog, field overlay w/ group assignment, scope dimensions, view contexts) +
  unsaved-changes guard. _(R3, R4.9, R5.1a)_

**Dependencies:** Phase 1 (field set to validate references against). **Deliverable:** reachable,
structured, bilingual authoring for all three `members.*` params, projecting via the existing
channel.

---

## Phase 3 — View contexts end-to-end (parameter → projection → generic renderer)

- [x] **3.1 Decide + implement the `view_contexts` projection shape** (Open Design Item 1: sibling
  `config#views` row vs fold into `config#fields`). Extend `projection_sync.py` builder + the module
  reader accordingly; empty → one default context. _(R5.1, C-VIEW; design Open Item 1)_
- [x] **3.2 View-contexts provider** in the module reader (mirrors `ScopeConfigProvider` /
  `TenantOverlayProvider`); expose contexts on `GET /members/field-config` (or a sibling field on the
  resolved config). _(R5.1, C-VIEW)_
- [x] **3.3 Generic renderer** on `MembersPage`: context dropdown gated by `permission_roles`;
  per-selected-context hand `{columns, filterableColumns, defaultSort, pageSize}` to the existing
  `useFilterableTable` / `FilterableHeader`. Unresolvable key → skipped, not crash. _(R5.1, R5.1a,
  C-VIEW; Property 7)_
- [x] **3.4 Seed 2–3 generic-placeholder contexts** (overview + one specialized) as onboarding data
  (not code). _(R5.1, R4.5)_
- [x] **3.5 Tests:** Property 7 (reference resolution/skip); per-context column rendering; dropdown
  permission gating; empty-is-valid default context. _(R5.1, R5.1a, Property 7)_

**Dependencies:** Phase 2. **Deliverable:** multiple selectable, parameter-driven view contexts.

---

## Phase 4 — Representative surface + modals (broaden the s5b frontend)

- [x] **4.1 Parameter-driven columns + calculated columns** wired to the resolved field config +
  selected view context. _(R5.1, R5.2, C-SURFACE)_
- [x] **4.2 Scope badge + scope filtering** surfaced from the projected `scopegrant#` via
  `resolve_scope_access` (reuse); values from `config#scope`. Applies regardless of context. _(R5.3,
  R5.4, C-SCOPE)_
- [x] **4.3 Filters/sort/stats** via the shared toolkit per context (reuse). _(R5.4, C-SURFACE)_
- [x] **4.4 View / edit / add / delete modals** over the resolved field set, **sectioned by
  `functional_group`** (display), honoring field-level view/edit permissions, **`show_when`
  conditional visibility**, and **value-level role-restricted enum options** (dropdowns render options
  from the correct source per R4.11, filtered to the caller's permitted values; the domain rejects
  disallowed values authoritatively — R4.12). **`member_number` is a manual-entry `string` field** for
  `Members_CRUD` (typed, validated against the tenant format pattern, then held unique by the
  repository); do NOT build platform auto-numbering — h-dcn's auto-counter stays in its
  `derive_member_number` tenant hook. _(R5.5, R4.8, R4.9, R4.11, R4.12, C-SURFACE)_
- [x] **4.5 Export** wired to `export_members` (remove "coming soon"). _(R5.6, C-SURFACE)_
- [x] **4.6 Single + bulk transitions, deliberately limited** — do not over-build the state machine.
  _(R5.7, C-SURFACE)_
- [x] **4.7 Membership-type dropdown** of active catalog entries, domain-validated (reuse s5
  catalog). _(R5.8, C-SURFACE)_
- [x] **4.8 Tests:** modals over resolved fields; scope badge + filtering; export; transition limits;
  catalog dropdown; **value-level role-restricted enum** (frontend filters options by role; domain
  rejects a disallowed value — 422/403); **`show_when`** conditional visibility (hidden field not
  required). _(R5, R4.11, R4.12)_

**Dependencies:** Phase 3. **Deliverable:** representative, parameter-driven Leden Overzicht.

---

## Phase 5 — Switch on the PreTokenGen channel in dev/test `(dt)`

> Generic platform infra; Members is the first consumer. Test-pool-first.
> **Shell/AWS-CLI + accounts:** follow steering `41-shell-environment.md` (POSIX inline `cd`,
> `<<<DONE marker>>>`, exit `-1` ≠ failure, `--output json`) and `23-aws-accounts.md` (profiles:
> identity `personal`/344561557829, data `nonprofit-deploy`/506221081911; `eu-west-1`).

- [x] **5.1 Repoint module Cognito config** to `myAdmin-test` for local + CI: `HDCN_COGNITO_ISSUER`
  = `…/eu-west-1_xyrlzfqbl`, matching JWKS URI, `HDCN_COGNITO_CLIENT_ID` =
  `43s15cm8qcgg8an85udt0e087u`. _(R2.1, R2.2, C-POOL)_
- [x] **5.2 `[H]` Deploy the PreTokenGen Lambda to the data account (506221081911)**; confirm
  same-account read of `governance_projection`. _(R1.2, R1.5, C-PTG)_
- [x] **5.3 `[H]` Attach the trigger to `myAdmin-test` (identity account 344561557829)** + the
  cross-account `aws_lambda_permission` (invoke crosses accounts; data read does not). _(R1.1, R1.2,
  C-PTG)_
- [x] **5.4 Seed a `myAdmin-test` user** whose projected entitlement is non-empty (via the governance
  path — Phase 6 onboarding, or a throwaway Members-enabled test tenant). _(R1.3, C-PTG)_
- [x] **5.5 Prove the channel:** decoded test-pool token carries `custom:entitlements`; the module
  authorizes off it with **zero `cognito:groups`** reliance (Property 5). _(R1.3, Property 5)_
- [x] **5.6 Prove fail-safe + detach-reversible:** resolution failure omits the claim (login still
  succeeds); detaching the trigger restores prior behavior (Property 6). _(R1.4, R12.5, Property 6)_

**Dependencies:** Phase 0 (fallbacks gone). Runs in parallel with Phases 1–4. **Deliverable:** the
capability channel is real in dev/test.

---

## Phase 6 — Provisioning playbook in dev/test (governance vs data tracks) `(dt)`

> **Scripts + local topology:** follow steering `41-shell-environment.md` (bash/POSIX, marker-based
> success, `.agent-output/` for scratch, background for any long-runner) and
> `42-local-dynamodb-testing.md` (Docker `myadmin-local`, `dynamodb-local`); Flask-plane writes obey
> `31-backend-database-flask-mysql.md`.

- [x] **6.1 Governance track (SPA):** onboard the (test) h-dcn tenant via **SysAdmin** (tenant +
  `MEMBERS` entitlement + role definitions) and **Tenant-Admin** (user role assignments + author the
  three `members.*` params via the Phase 2 editor). Observe `enqueue_sync` → projection at each write
  (F.8). Role assignments flow through the endpoints only. _(R8.1, R8.5, C-PLAYBOOK)_
- [x] **6.2 Data/migration script — member import** (Google-Sheet → `sam-members` DynamoDB).
  **REUSE `sam/members/migration/hdcn_backfill.py`** (already built): the Google Sheet is consumed as
  a **CSV/JSON export file** via `FileSourceAdapter` (no live Google API); `map_hdcn_row` transforms +
  `validate_fixed_fields` each row; `build_backfill_plan` produces the dry-run report
  (duplicate-member-number / missing-region). **Maps h-dcn's Dutch source columns → the English
  canonical Fixed keys** (the one place that translation happens; `member_number` → fixed string,
  validated against the tenant format pattern); tenant overlay keys pass through as authored.
  Writes **only via `MembersRepository`** (tenant_id-keyed, member-number uniqueness → 409) — NOT the
  `parameters` table and NOT the projection (this is member business data, not governance).
  **Unmapped/extra export columns are OUT of scope for s5c** (e.g. `Gezinslid`, `Bestuursfunctie`,
  termination dates, `Bedrag`, duplicate number/pref columns, the empty-named column): the importer
  SHALL tolerate them without failing — `map_hdcn_row` folds unrecognized columns into `overlay` (or
  drops the empty column) and lists them in the dry-run report; they are NOT individually classified
  or surfaced in the pilot UI. Only the classification-table fields are mapped to fixed/overlay keys.
  - **Where it runs:** a **host script** (bash, POSIX path, venv `backend/.venv`, steering 41) →
    `dynamodb-local` (`localhost:8000`, steering 42) for dev/test; prod `sam-members` in Phase 7.3
    (`nonprofit-deploy` profile). Idempotent, **dry-run first**, verify summary; the export file /
    logs under `.agent-output/`. _(R8.2, R8.3, R4.6, R4.8, C-PLAYBOOK)_
- [x] **6.3 Data/migration script — membership-type catalog seed:** idempotent, dry-run, verify.
  _(R8.2, R8.3, C-PLAYBOOK)_
- [x] **6.4 Data/migration script — bulk Cognito user load** into `myAdmin-test` from an editable
  file derived from the h-dcn pool (~10×2 + 3 users, capability + scope); users by script, role
  assignments via the governance endpoint. Idempotent, dry-run, verify. _(R8.2, R8.3, C-PLAYBOOK)_
- [x] **6.5 Confirm the reconciliation backstop** is scheduled/runnable in dev/test. _(R8.6,
  C-PLAYBOOK)_
- [x] **6.6 End-to-end dev/test verification:** a scoped user sees only their subset; a general user
  sees all; capability via `custom:entitlements`; all three channels demonstrably propagate a real
  SPA write to a module read. _(R7.4 analog in dev/test, R8, Properties 2/4/5)_

**Dependencies:** Phases 2–5. **Deliverable:** full pilot proven in dev/test.

---

## Phase 7 — Gated PROD cutover (prove CI/CD) `[H]`

> Only after Phase 6 passes. Human-run, gated, test-pool-first already satisfied.
> Tables managed outside CFN / retain — no table create/drop by deploy.
> **Shell/AWS-CLI + accounts:** follow steering `41-shell-environment.md` + `23-aws-accounts.md`
> (correct profile per account; `eu-west-1`; marker-based success; no foreground long-runners).

- [ ] **7.1 `[H]` Build → deploy** `sam-members` (+ `sam/pretokengen` if not already) to prod; confirm
  `sam-members` + `governance_projection` are NOT template resources. _(R7.1, R7.2, C-DEPLOY;
  Property 9)_
- [ ] **7.2 `[H]` Provision (governance track, prod SPA):** onboard h-dcn via SysAdmin + Tenant-Admin
  (entitlement, roles, `members.*` params — h-dcn authors its REAL region values + field set here as
  data). _(R7.1, R8.1, C-DEPLOY/C-PLAYBOOK)_
- [ ] **7.3 `[H]` Data track (prod):** run the **same** reused importer (6.2, `hdcn_backfill.py` via
  `FileSourceAdapter`) against the prod `sam-members` table (`nonprofit-deploy` profile) + the catalog
  seed (6.3) + the Cognito user load into **Pool A** (6.4) — dry-run then apply, with verify
  summaries. Member data via `MembersRepository`; role assignments still via the governance endpoint.
  _(R7.1, R8.2, C-PLAYBOOK)_
- [ ] **7.4 `[H]` Project:** run/observe the sync; confirm the prod projection carries the h-dcn
  governance + config rows. _(R7.1, C-DEPLOY)_
- [ ] **7.5 `[H]` Gate: attach the Pool A (`eu-west-1_Hdp40eWmu`) PreTokenGen trigger** +
  cross-account permission — the highest-blast-radius step, detach-to-rollback. _(R1.4, R7.3, C-PTG;
  Property 6)_
- [ ] **7.6 `[H]` Verify in prod:** a scoped user sees only their subset; a general user sees all;
  capability carried by `custom:entitlements` with zero `cognito:groups` reliance. _(R7.4, Property 5)_
- [ ] **7.7 Confirm the reconciliation backstop** is scheduled/runnable in prod. _(R8.6)_
- [ ] **7.8 Rehearse the non-destructive rollback** (in a safe window): detach trigger → remove
  `MEMBERS` entitlement / scope-role assignments → re-project; confirm NO table drops, NO data
  deletion, and that the live h-dcn app was untouched throughout. _(R7.5, R12.3, C-DEPLOY; Property 9)_

**Dependencies:** Phase 6. **Deliverable:** the full CI/CD path proven in prod, reversibly.

---

## Phase 8 — Documentation + governance close-out

- [ ] **8.1 End-user manual** — extend `docs/docs/members/` (nl + `*.en.md`) with the representative
  surface, view contexts, scope behavior, and the Tenant-Admin Members authoring UI; wire nav in
  `docs/mkdocs.yml`; `mkdocs build` succeeds (both locales). _(R5, R3; steering 40 / Common
  end-user-documentation)_
- [ ] **8.2 Steering/ADR update (REQUIRED definition-of-done, per steering 40).** A step is NOT
  complete until the steering/ADRs it changes are updated to match. s5c SHALL update, at minimum,
  these specific files in `.kiro/steering/`:
  - [ ] **`23-aws-accounts.md`** — the standing note that `myAdmin-test` has "no Pre-Token-Generation
    trigger … nothing to mirror" is now stale: record that s5c **added** the trigger to `myAdmin-test`
    (then Pool A), with the cross-account invoke wiring (identity → data account). _(R1)_
  - [ ] **`20-platform-architecture.md`** — record the PreTokenGen entitlement channel as **switched
    on end-to-end** (dev/test + prod), and the `members.*` parameter schema + typed-authoring pattern
    + the view-context generalization of `ui.tables`. _(R1, R3, R5.1)_
  - [ ] **`21-identity.md`** — record that Pool A now stamps `custom:entitlements` (the claim reality
    changed once the live trigger is attached). _(R1.4, R7.3)_
  - [ ] **`35-sam-module-architecture-sam.md`** — record the field model (Fixed/Parameter/Calculated;
    storage group vs parameter-driven functional group; fixed-type-string + parameter-format
    member_number) and that the S5 migration it governs is proven end-to-end. _(R4)_
  - [ ] **`00-index.md`** — update current phase/status (single source) and mark **s5b SUPERSEDED by
    s5c**; record the pilot as **passed only after Phase 7 verification**. _(R9)_
  - [ ] **ADR note (0006 area)** — the "live Pool A trigger deferred" framing is superseded: the
    channel is a required, switched-on generic prerequisite (F.2). _(R1)_
  - [ ] Update the roadmap (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`) to reflect s5c +
    the s5b supersession. _(R9)_
  _(R9 governance; steering 40 governance discipline)_
- [ ] **8.3 Confirm the deferred boundary held:** no generic config-editor framework and no
  draft/publish were built (belong to `json-editor.md`); reporting + onboarding/offboarding left
  cleanly addable (R10); Cognito-Beheer + Welkomstpakketten not ported (R11). _(R3.3, R10, R11)_

**Dependencies:** Phase 7. **Deliverable:** shipped docs + updated governance; pilot closed.

---

## Notes

- **Parallelism:** Phases 1–4 (representative surface + authoring) and Phase 5 (capability channel)
  are largely independent and can proceed in parallel; both converge at Phase 6.
- **Reuse discipline:** do not rebuild the s5 domain, s5b projection plumbing/frontend, or the S4
  Lambda — only broaden/wire/remove as the tasks specify.
- **Safety invariants (every phase):** verified-JWT only; MySQL SoR + one-directional projection;
  tables managed outside CFN / retain; test-pool-first + gated + detach-to-rollback for any
  prod/Cognito change; PreTokenGen fail-safe; no `if tenant == "h-dcn"` in the generic core.
- **Shell/exec discipline (steering `41-shell-environment.md` — applies to EVERY command task):**
  UNC path for file tools, POSIX path (inline `cd`) for bash; bash/Linux only (no PowerShell/`wsl -d`);
  treat terminal exit code `-1` as NOT failure — judge by stdout + the appended
  `<<<DONE marker=$?>>>`; empty output ≠ done (wait for the marker, don't blindly re-run mutating
  commands); AWS CLI `--output json`, pagers disabled; venv `backend/.venv`.
- **Verification hygiene:** stream stdout for test/verify output; scratch under `.agent-output/`;
  no long-running foreground processes (`sam local start-api`, `docker compose up`, watchers →
  `control_bash_process`/background, per steering 41/42).

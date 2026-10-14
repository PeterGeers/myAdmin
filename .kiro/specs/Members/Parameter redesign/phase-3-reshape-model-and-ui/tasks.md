# Implementation Plan

> **‼️ SHIPPED-WITH-DEFECTS — see the remediation spec before trusting the `[x]` below.** A review of
> the built group 4 drill-down surfaced nine issues (logged in `review-issues.md`, this folder). The
> drill-down tasks (4.x) are checked `[x]` as "built", but several carry blocker defects — most of them
> one root cause: the UI reads the raw `field_overlay` (write model) instead of the resolved
> `FieldConfig` (display model), so fixed/calculated fields, enum values (`status`, `region`), scope,
> and labels are missing or wrong; plus a move-to-group revert and a Flask builder gap. These are being
> fixed in a dedicated spec — do NOT treat Phase 3 as "done":
>
> - **Issue log:** `review-issues.md` (this folder) — I-1..I-9, with a verified server-truth
>   correction block.
> - **Remediation spec:** `.kiro/specs/Members/members-config-drilldown-remediation/`
>   (requirements/design/tasks) — fixes the bug clusters (A: read resolved config + labels; B: scope
>   as an editable field attribute + the builder gap; C: move-to-group).
> - **✅ REMEDIATED (update):** the 4.x drill-down defects shipped here (I-3/I-4/I-5/I-6/I-8/I-9 + the
>   I-2 SPA half) were fixed in the `members-config-drilldown-remediation` spec and shipped on branch
>   `spec/members-config-phase3-reshape` (one PR into `test`). See that spec's tasks.md and the ticked
>   statuses in `review-issues.md` (this folder). The deferred follow-up items (steering `38` rule-6
>   text, I-7a, I-7b) remain tracked separately.
> - **Deferred follow-up (separate spec, TBD):** the steering `38` rule-6 i18n-label reversal (I-2
>   text), a general per-field validation feature (I-7a), and `member_number_format` runtime authoring
>   (I-7b).
>
> **Two restarts of this phase (history):**
> 1. **Restart 1 — design rewrite (flat badge build → drill-down).** The first build shipped a flat
>    `MembersFieldProvenanceList` + read-only badge hierarchy via the slice editors (commit
>    `e78c73e81`). `design.md` was then rewritten to the group → field → attribute **drill-down** and
>    this tasks.md was re-derived (see the ⚠️ note under Overview). The drill-down (4.0–4.9) was then
>    built.
> 2. **Restart 2 — remediation (drill-down built against assumptions → re-grounded on server truth).**
>    The review above found the drill-down read the wrong data source and several attributes were
>    unwired. Rather than patch Phase 3 further, the fixes moved to the `members-config-drilldown-
>    remediation` spec, grounded in a verified server-truth table so the work is built against reality.

## Overview

Phase 3 — Reshape the Model + UI of the Members config redesign (`impact-analysis.md` §9 steps 8–11 +
the §5 dual-surface retirement). Four deliverables, all **authoring/presentation re-presentation** over
an unchanged store, resolver, and runtime: **(8)** collapse the fixed/overlay split into ONE field
model (provenance DERIVED, drives the field modal's actions — NOT a shown badge); **(9)** scope-binding
→ field attribute (resolver UNCHANGED); **(10)** analytics → calculated fields / field attributes;
**(11)** rebuild the authoring UI as a **group → field → attribute drill-down** (groups table → group
modal → fields table → field modal); plus retire the dual editing surface. Grounded in `design.md`;
every task names the steering it conforms to.

> **⚠️ Re-derived against the rewritten `design.md` (supersedes the first build).** An earlier pass
> shipped step 8/11 as a FLAT `MembersFieldProvenanceList` + a read-only per-group
> `MembersGroupFieldHierarchy` table with prominent provenance BADGES, authored through the
> `MembersParamSubEditor` slice editors (commit `e78c73e81`, branch
> `spec/members-analytics-role-removal`). The current `design.md` **replaces** that with a
> **drill-down (table → modal → table → modal)** where provenance DRIVES the field modal's actions and
> is NOT shown as a badge. This tasks.md is realigned to the new design: the **server-side**
> representation work (groups 1-server / 2 / 3 and their tests) is **genuinely done and still valid**;
> the **SPA** work (the badge list, the read-only hierarchy, the slice-editor authoring path) is
> **REOPENED** and re-specified against the drill-down, with an explicit supersede/cleanup task.

**Prerequisites (given, not re-opened):** Phase 0 (reliability), Phase 1 (catalog backbone), Phase 2
(deleted the redundant surface) are DONE. The sibling `members-analytics-role-removal` cleanup is DONE
through its task 8; its ship step was postponed into THIS folder (it ships with Phase 3 — see group 6).
Config home settled = Option B; Phase 4 DECIDED = Option B (`36` unchanged). The two high-blast-radius
bets — "only `member_id` is fixed" and Option C — are **out of scope** (see `requirements.md`).

Planes: SAM = `sam/members/...` + `sam/tests/` (pytest via `sam/pytest.ini`); Flask = `backend/src` +
`backend/tests` (pytest via `backend/pytest.ini`); SPA = `frontend/src` (Vitest + RTL). Do NOT import
`sam.*` into `backend/src` (steering 30/31 cross-plane boundary). Tests follow `34-backend-testing.md`
/ `33-frontend-testing.md`; the **Change-With-Tests Contract** (`30`/`32`) applies to every behavioural
edit — the paired test moves in the SAME task. Shell per `41-shell-environment.md` (POSIX `cd` inline,
`<<<DONE marker=$?>>>`, `backend/.venv`).

**Behaviour-preservation is the whole safety story.** Steps 8/9/10 are equivalences (Properties 1–3);
member data is invariant (Property 4). No task weakens an assertion to go green — a step that cannot be
shown equivalent is a defect to reconcile, not an accepted change.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1", "2.3", "3.1"] },
    { "id": 1, "tasks": ["4.0", "4.1"] },
    { "id": 2, "tasks": ["4.2", "4.3"] },
    { "id": 3, "tasks": ["4.4", "4.5"] },
    { "id": 4, "tasks": ["4.6", "4.7"] },
    { "id": 5, "tasks": ["4.8"] },
    { "id": 6, "tasks": ["4.9", "5.1"] },
    { "id": 7, "tasks": ["6.1", "6.2", "6.3"] }
  ]
}
```

Dependency rationale: the step 8/9/10 **server-side** representation changes + their paired tests are
mutually independent and already landed (wave 0, all `[x]`). The rebuilt UI (group 4, step 11) authors
against all three. The sub-tasks are ordered so each is independently reviewable and the build stays
green: first the pure overlay working-model + mutation helpers and the shared label helper (4.0–4.1),
then the removal of the superseded flat list + hierarchy badge surface with their paired tests
(4.2–4.3), then the drill-down built bottom-up — groups table + group modal (4.4), fields table (4.5),
field modal (4.6), provenance-driven actions + move-to-group (4.7) — then wiring it onto the one save
path (4.8) and the full suite rebuild (4.9). The dual-surface retirement (group 5, §5) lands with the
UI so there is never a window with zero authoring doors. Verification + property suite + ship —
including the postponed role-removal ship — converge last (group 6). The whole UI group (4.0–4.9 + 5.1)
is one branch → one PR into `test`, so the editor is only ever half-built mid-branch, never in a merged
commit. None of this is member-data destructive (Property 4).

## Tasks

### Deliverable (8): collapse fixed/overlay → ONE field model; provenance DERIVED, drives field-modal actions (R1, R6) — `32`, `33`, `35`, `38`, `34`

> **Server side DONE + still valid.** 1.1/1.2 are the bounded `_apply_override` simplification + its
> SAM test; the new drill-down UI consumes the SAME derived provenance (it just uses it to pick modal
> actions instead of rendering a badge). The SPA re-presentation moves into group 4 (it is now the
> field modal's action-gating, not a flat badge list) — see 4.0 (supersede) + 4.4 (field modal).

---

- [x] 1. Fixed/overlay → one field model (provenance derived) — SERVER SIDE
  - [x] 1.1 Simplify the SAM `_apply_override` / `_as_variable_field` branch in `sam/members/domain/field_resolver.py` to the bounded extent the single-model provenance needs — DERIVE a provenance marker (base / tenant-added / base-overridden) at resolve time; keep the merge+sort+project pipeline and keep EVERY current fixed field immovable (do NOT adopt "only `member_id` is fixed"). The resolved field SET + order stay invariant. Conforms to `35`, `38` rule 2. _(R1.2, R1.5, R6.1, R6.2)_
  - [x] 1.2 Change-With-Tests (SAM): update `sam/tests/test_field_resolver.py` provenance/override cases to the single-model representation; keep the resolved-field-SET and `(group.order, field.order, key)` order assertions UNCHANGED (do not weaken). Conforms to `34`, `30` Change-With-Tests. _(R8.1, R1.6)_

---

### Deliverable (9): scope-binding → field attribute, resolver unchanged (R2) — `35`, `36`, `30`, `38`, `32`, `34`

> **Server side DONE + still valid.** 2.1/2.3 author scope as a field attribute on the Flask writer +
> SAM read representation and prove scope-resolution equivalence; the resolver stays byte-for-byte. The
> SPA retirement of the standalone scope sub-editor + authoring scope on the field moves into the field
> modal (group 4, task 4.4) — the old 2.2 slice-editor version is superseded by it.

---

- [x] 2. Scope-binding as a field attribute (resolver UNCHANGED) — SERVER SIDE
  - [x] 2.1 Author scope-binding as a field attribute on the Flask writer + the SAM read representation: express "field is a scope axis / enabled / value vocabulary" as field attributes; keep the projected config the resolver consumes SEMANTICALLY EQUIVALENT. If the `config#...` row shape changes, move schema + validator + builder + reader together (`36` rule 1); do NOT touch `handler/app.py` scope resolution or the `scopegrant#<email>#<dim>` grants. Conforms to `36`, `30`, `35`, `38`. _(R2.1, R2.3, R2.4, R2.5, R6.2)_
  - [x] 2.3 Change-With-Tests + **Property 2** (SAM): keep `sam/tests/test_scope_access.py` / `test_scope_dimensions.py` asserting the SAME `allowed_scopes`; update only the authoring/config-shape setup. Add a scope-equivalence property test: for any tenant scope config + user grants, `allowed_scopes` after scope-as-attribute == before. **Property 2: scope resolution equivalent across the authoring-representation change.** **Validates: Requirements 2.3, 2.5, 2.6** Conforms to `34`. _(R8.2, R2.6)_

---

### Deliverable (10): analytics → calculated fields / field attributes (R3) — `35`, `36`, `38`, `32`, `34`

> **Server side DONE + still valid** (also reinforced by the sibling `members-analytics-role-removal`
> cleanup, which stripped the redundant role/jubilee/address machinery). 3.1 is the SAM representation.
> The SPA removal of the separate analytics sub-editor moves into group 4 — the folded
> analytics-role/alias attribute is authored in the field modal (task 4.4); there is no standalone
> analytics editor in the new drill-down at all.

---

- [x] 3. Fold analytics into calculated fields / field attributes — SERVER SIDE
  - [x] 3.1 Represent jubilee-years-type analytics needs as **calculated fields** (the `sam/members/domain/calculated_fields.py` registry — unchanged in mechanism, import-time-guarded, never stored) and analytics field-role aliases (cancellation-date, referral-source, address-mapping) as **field attributes**. Data continues to ride on `config#fields` — do NOT introduce a `members.*` analytics param (`38` rule 3). Keep `sam/tests/test_calculated_fields.py` green; add the analytics value-equivalence test (**Property 3**). **Validates: Requirements 3.6** Conforms to `35`, `36`, `38` rule 3, `34`. _(R3.1, R3.2, R3.4, R3.5, R3.6, R8.3)_

---

### Deliverable (11): rebuild the authoring UI as a group → field → attribute DRILL-DOWN (R4) — `32`, `33`, `37`, `38`

> **REOPENED against the rewritten design.** The shipped SPA (flat `MembersFieldProvenanceList` +
> read-only `MembersGroupFieldHierarchy` table with provenance BADGES, authoring through
> `MembersParamSubEditor` slice editors) is SUPERSEDED. The new design is a drill-down: a groups table
> → a group modal → a fields table (within the group) → a field modal, with CRUD through the modals and
> provenance DRIVING (not displaying) the field modal's actions. Gate: wave 1–4, runs after the step
> 8/9/10 server representations (groups 1–3, all done) because the new UI authors against them.

---

> **Grounding (verified in code, this branch).** Current authoring = two Chakra `Tabs`
> (`MembersConfigEditor.tsx`) → `MembersParamSubEditor` slice editors (`sliceKey="functional_groups"`
> and `sliceKeys={['fields','fixed_overrides']}`) → the recursive `MembersTypedField` renderer, all
> saving the WHOLE `field_overlay` object once via `saveMembersParameter(key, value, existing)`
> (PUT when a tenant row exists, else POST). The read-only `MembersGroupFieldHierarchy` +
> `MembersFieldProvenanceList` render provenance BADGES. Shared blocks to compose from (steering 37):
> `useFilterableTable(rows,{initialFilters})` + `FilterableHeader` (`components/filters/`), the Chakra
> `Modal`+`useDisclosure`+`AlertDialog` pattern from `AccountModal.tsx`, `LazySelect`
> (`components/common/`), toast for API errors, and the i18n Option-b resolver `resolveShippedLabel` +
> `LABEL_KEY_SCHEME` (`admin` namespace, keys in `locales/{nl,en}/admin.json` → `membersConfig.*`).
> **Hard invariant for the whole group:** every modal CRUD action mutates an in-memory
> `field_overlay` working copy and commits it through the ONE `saveMembersParameter` primitive — one
> save → one request → one re-projection. No new param, no per-field request, no second save door.

- [ ] 4. Rebuild the authoring UI as a group → field → attribute drill-down

  - **Preparation / shared scaffolding**
  - [x] 4.0 **Overlay working-model + mutation helpers (pure, unit-tested first).** Add a small pure
    module (e.g. `MembersConfig/overlayModel.ts`) that reads/writes the one `field_overlay` object:
    helpers to list groups, list a group's fields (derived `(group.order, field.order, key)` via the
    existing `groupResolvedFields`), create/edit/delete a group (delete only when it holds no fields),
    create/edit/delete a field, add/edit/delete a field attribute, and move a field to another group
    (reassign `functional_group`). All helpers are pure `(overlay, …) → overlay'` — NO network, NO
    React — so the single-save contract is trivially preserved (the editor commits the result via
    `saveMembersParameter`). Add `__tests__/overlayModel.test.ts` covering each helper, the
    delete-group-only-when-empty guard, and the move-to-group reassignment. Conforms to `38` rules
    2/5, `33`, `30`/`32` Change-With-Tests. _(R4.8, R1.5, R8.4)_
  - [x] 4.1 **i18n keys + label resolution for the drill-down.** Confirm/extend the Option-b resolver
    usage: shipped group/field/enum labels via `resolveShippedLabel` + `LABEL_KEY_SCHEME` under the
    `admin` namespace; add any missing `membersConfig.group.*` / `membersConfig.field.*` keys to
    `locales/{nl,en}/admin.json` (enum `value` language-neutral, only `label` per-language). This is
    the shared label helper the tables + modals (4.3–4.6) call; keep it a thin wrapper, do not grow a
    new i18n mechanism. Conforms to `38` rule 6, `37`, `32`. _(R4.6)_

  - **Supersede the first build (removal + its paired tests, in lockstep)**
  - [x] 4.2 **Remove the superseded flat provenance-badge list + its test.** DELETE
    `MembersConfig/MembersFieldProvenanceList.tsx` AND `__tests__/MembersFieldProvenanceList.test.tsx`
    (if present) outright; drop its re-export from `MembersConfig/index.ts`; remove the
    `MembersFieldProvenanceList` import + `<MembersFieldProvenanceList/>` render and the now-dead
    `resolvedFields` / `orderResolvedFields` wiring from `MembersConfigEditor.tsx`. Keep
    `orderResolvedFields` in the service only if another consumer remains (grep first; delete if
    genuinely unreferenced). Provenance SHALL no longer render as a badge anywhere. The deletions ARE
    the paired-test action. Conforms to `38` rule 5, `33`, `30`/`32` Change-With-Tests.
    _(R1.3, R8.4, R8.6)_
  - [x] 4.3 **Retire the read-only hierarchy's badge/column presentation.** In
    `MembersGroupFieldHierarchy.tsx` remove the provenance BADGE column + the `PROVENANCE_BADGE` map
    (and the `provenance` sort column); either repurpose the component into the new read-side of the
    fields table (4.5) or delete it in favour of the new components, dropping its `index.ts`
    re-export if deleted. REWRITE `__tests__/MembersGroupFieldHierarchy.test.tsx`: drop the
    `members-hierarchy-provenance-*` / badge assertions; keep the `groupResolvedFields` derivation
    cases (defined-group sections, derived order, the unresolvable "ungrouped" bucket) — move them to
    `overlayModel.test.ts` or the fields-table suite if the component is deleted. Grep the SPA test
    tree for `members-hierarchy-provenance*` and remove every orphan. Conforms to `38` rule 5, `33`,
    `30`/`32` Change-With-Tests. _(R1.3, R8.4, R8.6)_

  - **Build the drill-down (table → modal → table → modal)**
  - [x] 4.4 **Functional-groups table + group modal (entry point).** New `MembersGroupsTable.tsx`:
    a `useFilterableTable` + `FilterableHeader` table of the overlay's functional groups (columns =
    resolved `label`, `key`, `order`; derived order `(group.order, key)`), with a CREATE-group action
    and row-click opening `MembersGroupModal.tsx`. The group modal (Chakra `Modal`/`useDisclosure`,
    `AccountModal` pattern) edits `key`/`label`(nl/en)/`order`, offers DELETE **only when the group has
    no fields** (guarded via `overlayModel`; disabled + reason tooltip otherwise, with an
    `AlertDialog` confirm), and exposes a **Fields** button opening the fields table (4.5). All edits
    mutate the working `field_overlay` and bubble up; nothing saves here directly. Conforms to `38`
    rules 1/2, `32`, `37`. _(R4.1, R4.2, R4.4)_
  - [x] 4.5 **Fields table within a group.** New `MembersFieldsTable.tsx`: a `useFilterableTable` +
    `FilterableHeader` table of the selected group's fields (columns = resolved `label`, `key`,
    `type`, key attribute flags like required/visible/scope-axis; derived order `(field.order, key)`),
    row-click opening the field modal (4.6). Surfaces an unresolvable-group field in a trailing
    "ungrouped" bucket rather than dropping it (reuse `groupResolvedFields`). Conforms to `38` rules
    1/2, `32`, `37`. _(R4.1, R4.3, R4.5, R8.7)_
  - [x] 4.6 **Field modal — all options as attributes.** New `MembersFieldModal.tsx` exposing EVERY
    editable field option as an attribute: name/key, type, label(nl/en), required, visibility,
    calculated-from/read-only, enum `choices` (reuse `EnumOptionsEditor`), the **scope-binding
    attribute** (step 9: `{enabled, values, required_for}`), and the **analytics role/alias
    attribute** (step 10) — with add/edit/delete of attributes. Reuse `MembersTypedField` for the
    per-attribute controls where it fits, rather than re-implementing control mappings. All edits
    mutate the working `field_overlay`; the modal does not save on its own. Conforms to `38` rules
    1/2/6, `32`, `37`. _(R2.1, R2.2, R3.2, R3.3, R4.3, R4.6)_
  - [x] 4.7 **Provenance-driven field-modal actions + move-to-group.** In the field modal, use the
    DERIVED `field.provenance` (base / tenant_added / base_overridden) to GATE the actions offered —
    tenant-added → destructive **Delete** (AlertDialog confirm); base → **Reset to default** / **Hide**
    (no destructive delete); base-overridden → **Reset to default** — and add a **Move to another
    group** action whose picker (`LazySelect` / catalog-resolvable groups only) reassigns
    `functional_group` via `overlayModel`. Provenance is NEVER rendered as a badge/label — it only
    selects actions (R1.3). Conforms to `38` rules 1/2, `32`, `37`. _(R1.2, R1.3, R4.3)_

  - **Wire + save + tests**
  - [x] 4.8 **Wire the drill-down into `MembersConfigEditor` on the ONE save path.** Replace the
    two-tab `MembersParamSubEditor` slice-authoring surface with the groups-table entry point (4.4),
    holding the working `field_overlay` in editor state and committing it through the single
    `saveMembersParameter(…, rows.field_overlay)` primitive (one save → one request → `load()`
    refresh). Keep `MembersConfigStatus` and the best-effort `getMembersFieldConfig` load. Preserve the
    "fetch never blocks authoring" posture. Conforms to `38` rule 5, `32`. _(R4.8, R1.1)_
  - [x] 4.9 **Rebuild the Vitest + RTL suites against the drill-down.** Rewrite
    `__tests__/MembersConfigEditor.test.tsx` and `__tests__/MembersConfigSingleSavePath.test.tsx` to
    the drill-down, and add focused suites `__tests__/MembersGroupsTable.test.tsx`,
    `__tests__/MembersFieldsTable.test.tsx`, `__tests__/MembersFieldModal.test.tsx`. Cover: the
    groups table → group modal → fields table → field modal drill-down (row-click-opens-modal); group
    create / edit / delete-when-empty (and delete BLOCKED when non-empty); field move-to-group;
    **provenance-driven field-modal actions** (tenant-added → delete; base → reset/hide;
    base-overridden → reset — asserted as the AVAILABLE ACTIONS, never a rendered badge, R1.3); the
    picker-resolvability guard (only catalog groups/fields offered; an authored unresolvable reference
    SURFACED, not dropped); and the **single-save path** (one modal commit → exactly one
    create/update request, the real `saveMembersParameter` + `overlayModel` un-mocked, counting
    `parameterService.create/update`). No assertion is weakened to go green; contradictory tests are
    reconciled toward the drill-down (R8.6). Conforms to `38` rule 5, `33`, `30`/`32` Change-With-Tests.
    _(R4.8, R8.4, R8.6)_

---

### Deliverable (§5): retire the dual editing surface (R5) — `32`, `33`, `38` rule 5

> **Gate:** lands with group 4 (step 11) so there is never a window with zero authoring doors.

---

- [x] 5. Retire the dual editing surface (one door)
  - [x] 5.1 Exclude the `members.*` namespace from the raw generic parameter editor (`frontend/src/components/TenantAdmin/ParameterManagement.tsx`, mounted via `AdvancedTab.tsx`) so the typed `MembersConfig` editor is the single authoring surface for `members.*`; keep EVERY other namespace served (do NOT remove the component). Change-With-Tests: add a test asserting `members.*` is not editable there and other namespaces still are. Conforms to `32`, `33`, `38` rule 5. _(R5.1, R5.2, R5.3, R5.4, R8.5)_

---

### Verification + ship (R7, R8, R9) — `34`, `33`, `43`, `41`, `40`

---

- [ ] 6. Verification, member-data + behaviour invariance, ship
  - [x] 6.1 Run the touched suites. SAM: `cd sam && pytest tests/test_field_resolver.py tests/test_scope_access.py tests/test_scope_dimensions.py tests/test_calculated_fields.py tests/test_members_projection_reader.py -q`. Flask (via `backend/.venv`): the members_config_validation + projection_sync + parameter_schema tests (+ any config-row migration test). SPA: the **rebuilt** MembersConfig drill-down (groups table / group modal / fields table / field modal) + raw-editor-exclusion Vitest suites — the superseded flat-list/badge suites are gone (4.0). All green; the Phase 1 catalog drift guard stays green. Conforms to `34`, `33`, `41`. _(R8.7, R8.1, R8.2, R8.3, R8.4, R8.5)_
  - [x] 6.2 **Property 1 + Property 4** + behaviour-invariance close-out. **Property 1: the provenance collapse preserves the resolved field set and order** — snapshot the resolved field set + `(group.order, field.order, key)` order before/after step 8; assert identical. **Property 4: member data invariant across every Phase 3 step** — snapshot arbitrary member records before/after each step; assert byte-for-byte equality. Confirm no `members.*` analytics param was introduced and the `config#fields`/`TenantOverlay.overrides` names are unchanged (Phase 2 R6.8 guard continued). **Validates: Requirements 1.6, 6.1, 7.1, 7.2** _(R7.1, R7.2, R6.4)_
    > **Close-out evidence.** The drill-down rebuild (group 4) is SPA-only: the branch diff vs the merge base changed ZERO files under `sam/` or `backend/` and touched no `sam-members` data path — only `.kiro/specs/*` + `frontend/src/components/TenantAdmin/MembersConfig/*`. **Property 1** is locked by the UNCHANGED `field_resolver.py` and its green `sam/tests/test_field_resolver.py` (asserts the resolved field SET + `(group.order, field.order, key)` order); the step-8 provenance derivation it encodes is unchanged this phase. **Property 4** holds by construction — no code on this branch reads or writes member records; there is no member-data migration. **Name guards:** the diff adds NO `members.*` analytics param (grep for added `members.analytics`/`'analytics'` lines is empty), and every `fixed_overrides` diff line is a DELETION of old comments/code — the attribute is read/written by its existing name in `overlayModel.ts`, never renamed (Phase 2 R6.8 continued). Steps 8/9/10 server-side property tests (Property 1/2/3) remained green in task 6.1; adding snapshot tests over unchanged resolver code would duplicate them.
  - [ ] 6.3 CI/CD + ship + governance (per `43-cicd-deploys.md`, `40-spec-workflow.md`). This ship ALSO carries the postponed `members-analytics-role-removal` ship step (that spec's task 9, deferred into this folder). Feature branch (e.g. `spec/members-config-phase3-reshape`); never push to `test`/`main` directly. Run the paired tests locally first. PR into `test`; clear CodeQL + GitGuardian. Preview the prod changeset (`--no-execute-changeset`) — confirm NO unexpected `Replacement: True` (Phase 3 adds no infra/table change). Promote `test → main` by MERGE commit (not squash — preserve phase history). IF a config-row migration is needed, run it against TEST then PRODUCTION via `backend/scripts/railway-db.sh` (`#database` skill) — not auto-applied, never member data. Deploys touch the DATA account only; no Cognito/identity change. **Governance DoD:** update `38-sam-module-field-config.md` (+ `35`/`37`/`00-index.md` cross-refs) to the SHIPPED drill-down model (group→field→attribute drill-down, provenance-driven field actions, scope-as-attribute, analytics-as-fields), ELSE record "no steering change due" with evidence. Tick `impact-analysis.md` §9 Phase 3 steps 8–11 done with a pointer to this spec folder. _(R9.1, R9.2, R9.3, R9.4, R9.5)_

---

## Notes

### Realignment summary (what changed vs the first tasks.md)

| First build (superseded) | Now (drill-down design) | Task(s) |
|---|---|---|
| SAM `_apply_override` provenance derivation + SAM test | unchanged — server side still valid | 1.1, 1.2 (done) |
| scope-as-attribute on writer/reader + equivalence test | unchanged — server side still valid | 2.1, 2.3 (done) |
| analytics folded into fields/calculated + value-equiv test | unchanged — server side still valid | 3.1 (done) |
| flat `MembersFieldProvenanceList` + provenance BADGE | DELETED; provenance drives modal actions, no badge | 4.2, 4.7 |
| read-only `MembersGroupFieldHierarchy` table + badge column | badge column removed; replaced by groups table → group modal → fields table | 4.3, 4.4, 4.5 |
| slice `MembersParamSubEditor` authoring (2 tabs) | REPLACED by modal CRUD (create/delete group, field modal, move-to-group) | 4.4, 4.6, 4.7, 4.8 |
| standalone scope sub-editor (old 2.2 SPA) | folded into the field modal's scope attribute | 4.6 |
| standalone analytics sub-editor (old 3.2 SPA) | folded into the field modal's analytics-role attribute | 4.6 |
| single-save test over the slice editors | single-save test over the drill-down | 4.0, 4.9 |

### Requirements coverage

| Requirement | Tasks |
|---|---|
| R1 (one field model; provenance drives actions, not a badge) | 1.1, 1.2, 4.2, 4.3, 4.7, 4.8 |
| R2 (scope-binding → field attribute, resolver unchanged) | 2.1, 2.3, 4.6 |
| R3 (analytics → calculated fields / attributes) | 3.1, 4.6 |
| R4 (group → field → attribute drill-down UI) | 4.0, 4.1, 4.4, 4.5, 4.6, 4.7, 4.8 |
| R5 (one authoring surface) | 5.1 |
| R6 (bounded, layering-preserving SAM reshaping) | 1.1, 2.1, 6.2 |
| R7 (non-destructive to member data) | 6.2 |
| R8 (Change-With-Tests blast radius, incl. R8.6 reconcile-don't-weaken) | 1.2, 2.3, 3.1, 4.0, 4.2, 4.3, 4.9, 5.1, 6.1 |
| R9 (ship safely + governance DoD) | 6.3 |

### Correctness property → task

| Property | Task |
|---|---|
| P1 — provenance collapse preserves resolved field set + order | 6.2 |
| P2 — scope resolution equivalent across the authoring-representation change | 2.3 |
| P3 — analytics folding value-equivalent | 3.1 |
| P4 — member data invariant across every step | 6.2 |

### Ordering guarantees

- Steps 8/9/10 server-side (groups 1–3) are mutually independent, behaviour-preserving (Properties
  1–3), and already shipped with their paired tests.
- Step 11 (group 4) authors against all three; the pure overlay working-model + mutation helpers land
  first (4.0–4.1), the superseded flat list + hierarchy badge surface is removed with its paired tests
  (4.2–4.3), the drill-down is built bottom-up (4.4–4.7), wired onto the one save path (4.8), and the
  suites rebuilt (4.9) — so provenance stops being a badge and the slice-editor path is retired.
- §5 (group 5, one door) lands WITH step 11 — never a window with zero authoring surfaces.
- The postponed `members-analytics-role-removal` ship (its task 9) ships WITH this phase (task 6.3).
- Nothing in Phase 3 migrates member data (Property 4); any config-row migration is `31`-compliant.

### Deferred / explicitly NOT done here (recorded)

- "Only `member_id` is fixed" literal model change — out of scope (`impact-analysis.md` §4.1, §10).
- Option C (SAM-native authoring; deletes the projection layer; needs a steering-36 revision) — out of
  scope (`impact-analysis.md` §9 step 12, §10). Config home stays Option B.
- Renaming `TenantOverlay.overrides` / `config#fields.overrides` — continues the Phase 2 R6.8 guard.
- Any change to the generic Members table runtime (`useFilterableTable`) — the TOP-rated surface stays.
- Starting the next SAM modules (Webshop, Events) — `impact-analysis.md` §11 is forward guidance.

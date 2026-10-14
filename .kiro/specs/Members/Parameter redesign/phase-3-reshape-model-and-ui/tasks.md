# Implementation Plan

## Overview

Phase 3 — Reshape the Model + UI of the Members config redesign (`impact-analysis.md` §9 steps 8–11 +
the §5 dual-surface retirement). Four deliverables, all **authoring/presentation re-presentation** over
an unchanged store, resolver, and runtime: **(8)** collapse fixed/overlay → one list + provenance
badge; **(9)** scope-binding → field attribute (resolver UNCHANGED); **(10)** analytics → calculated
fields / field attributes; **(11)** rebuild the group → field → attribute authoring UI; plus retire the
dual editing surface. Grounded in `design.md`; every task names the steering it conforms to.

**Prerequisites (given, not re-opened):** Phase 0 (reliability), Phase 1 (catalog backbone), Phase 2
(deleted the redundant surface) are DONE. Config home settled = Option B; Phase 4 DECIDED = Option B
(`36` unchanged). The two high-blast-radius bets — "only `member_id` is fixed" and Option C — are
**out of scope** (see `requirements.md`).

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
    { "id": 0, "tasks": ["1.1", "1.2", "2.1", "3.1"] },
    { "id": 1, "tasks": ["1.3", "2.2", "2.3", "3.2"] },
    { "id": 2, "tasks": ["4.1", "4.2"] },
    { "id": 3, "tasks": ["4.3", "5.1"] },
    { "id": 4, "tasks": ["6.1", "6.2", "6.3"] }
  ]
}
```

Dependency rationale: steps 8/9/10 (groups 1/2/3) prepare each plane's representation and are mutually
independent, so their server-side changes + paired tests run first (waves 0–1). The rebuilt UI
(group 4, step 11) authors against all three, so it depends on them (waves 2–3). The dual-surface
retirement (group 5, §5) lands with the UI so there is never a window with zero authoring doors
(wave 3). Verification + property suite + ship (group 6) converge last (wave 4). None of this is
member-data destructive (Property 4).

## Tasks

### Deliverable (8): collapse fixed/overlay → one list + provenance badge (R1, R6) — `32`, `33`, `35`, `38`, `34`

---

- [x] 1. Fixed/overlay → one list + provenance badge
  - [x] 1.1 Simplify the SAM `_apply_override` / `_as_variable_field` branch in `sam/members/domain/field_resolver.py` to the bounded extent the single-list provenance needs — DERIVE a provenance marker (base / tenant-added / base-overridden) at resolve time; keep the merge+sort+project pipeline and keep EVERY current fixed field immovable (do NOT adopt "only `member_id` is fixed"). The resolved field SET + order stay invariant. Conforms to `35`, `38` rule 2. _(R1.5, R6.1, R6.2)_
  - [x] 1.2 Change-With-Tests (SAM): update `sam/tests/test_field_resolver.py` provenance/override cases to the single-list representation; keep the resolved-field-SET and `(group.order, field.order, key)` order assertions UNCHANGED (do not weaken). Conforms to `34`, `30` Change-With-Tests. _(R8.1, R1.6)_
  - [x] 1.3 SPA re-presentation (`frontend/src/components/TenantAdmin/MembersConfig/MembersConfigEditor.tsx`): render base + tenant fields as ONE ordered list (order `(group.order, field.order, key)`, no new position field) with a provenance badge per field; keep authoring ONE `field_overlay` object (one save → one re-projection). Change-With-Tests: rewrite the fixed/overlay-split cases in `MembersConfig/__tests__/MembersConfigEditor.test.tsx`. Conforms to `32`, `33`, `38` rules 2/5. _(R1.1, R1.2, R1.3, R1.4, R8.4)_

---

### Deliverable (9): scope-binding → field attribute, resolver unchanged (R2) — `35`, `36`, `30`, `38`, `32`, `34`

---

- [x] 2. Scope-binding as a field attribute (resolver UNCHANGED)
  - [x] 2.1 Author scope-binding as a field attribute on the Flask writer + the SAM read representation: express "field is a scope axis / enabled / value vocabulary" as field attributes; keep the projected config the resolver consumes SEMANTICALLY EQUIVALENT. If the `config#...` row shape changes, move schema + validator + builder + reader together (`36` rule 1); do NOT touch `handler/app.py` scope resolution or the `scopegrant#<email>#<dim>` grants. Conforms to `36`, `30`, `35`, `38`. _(R2.1, R2.3, R2.4, R2.5, R6.2)_
  - [x] 2.2 SPA: retire the standalone `scope_dimensions` sub-editor and author scope as a field attribute in the typed editor; pickers offer only catalog-resolvable fields. Change-With-Tests: rewrite the scope sub-editor cases in `MembersConfigEditor.test.tsx`. Conforms to `32`, `33`, `38`. _(R2.1, R2.2, R8.4)_
  - [x] 2.3 Change-With-Tests + **Property 2** (SAM): keep `sam/tests/test_scope_access.py` / `test_scope_dimensions.py` asserting the SAME `allowed_scopes`; update only the authoring/config-shape setup. Add a scope-equivalence property test: for any tenant scope config + user grants, `allowed_scopes` after scope-as-attribute == before. **Property 2: scope resolution equivalent across the authoring-representation change.** **Validates: Requirements 2.3, 2.5, 2.6** Conforms to `34`. _(R8.2, R2.6)_

---

### Deliverable (10): analytics → calculated fields / field attributes (R3) — `35`, `36`, `38`, `32`, `34`

---

- [x] 3. Fold analytics into calculated fields / field attributes
  - [x] 3.1 Represent jubilee-years-type analytics needs as **calculated fields** (the `sam/members/domain/calculated_fields.py` registry — unchanged in mechanism, import-time-guarded, never stored) and analytics field-role aliases (cancellation-date, referral-source, address-mapping) as **field attributes**. Data continues to ride on `config#fields` — do NOT introduce a `members.*` analytics param (`38` rule 3). Conforms to `35`, `36`, `38` rule 3. _(R3.1, R3.2, R3.4, R3.5, R3.6)_
  - [x] 3.2 SPA + Change-With-Tests: remove the separate analytics sub-editor section from `MembersConfigEditor.tsx`, authoring the folded representation instead; rewrite the analytics sub-editor cases in `MembersConfigEditor.test.tsx`; keep `sam/tests/test_calculated_fields.py` green (extend only if a jubilee calculated field is added). Add an analytics value-equivalence test (**Property 3**). **Validates: Requirements 3.6** Conforms to `32`, `33`, `34`. _(R3.3, R8.3, R8.4)_

---

### Deliverable (11): rebuild the group → field → attribute authoring UI (R4) — `32`, `33`, `37`, `38`

> **Gate:** wave 2–3 — runs after the step 8/9/10 representations (groups 1–3) are in place, because the
> new UI authors against them.

---

- [x] 4. Rebuild the group → field → attribute authoring UI
  - [x] 4.1 Build the group → field → attribute authoring hierarchy on the Phase 1 attribute catalog (`sam/members/domain/attribute_catalog.py`): author functional groups (`key`/`label`/`order`), fields within groups, and per-field attributes; display order DERIVED `(group.order, field.order, key)` (no stored absolute position); pickers offer only catalog-resolvable field keys / defined groups (keep the drift guard green). Conforms to `38` rules 1/2, `32`. _(R4.1, R4.2, R4.3, R8.7)_
  - [x] 4.2 i18n (Option b) + composition: render shipped labels via resource keys (`members.field.<key>`) with an inline per-language tenant override (enum `value` language-neutral, `label` per-language); compose from the registered building blocks (Table Filter Framework v2, LazySelect, API/error standard) rather than bespoke equivalents; meet `32` table/modal/i18n/row-click + accessibility. Conforms to `38` rule 6, `37`, `32`. _(R4.4, R4.5, R4.6)_
  - [x] 4.3 Single save path + Change-With-Tests: the new UI saves through ONE typed save → one re-projection, through which the provenance badge (8), scope-as-attribute (9), and analytics-as-fields (10) all author. Add Vitest + RTL tests for the group→field→attribute flow, the provenance badge, the picker-resolvability guard, and the single-save path. Conforms to `38` rule 5, `33`. _(R4.7, R8.4)_

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
  - [x] 6.1 Run the touched suites. SAM: `cd sam && pytest tests/test_field_resolver.py tests/test_scope_access.py tests/test_scope_dimensions.py tests/test_calculated_fields.py tests/test_members_projection_reader.py -q`. Flask (via `backend/.venv`): the members_config_validation + projection_sync + parameter_schema tests (+ any config-row migration test). SPA: the MembersConfig editor + new authoring-UI + raw-editor-exclusion Vitest suites. All green; the Phase 1 catalog drift guard stays green. Conforms to `34`, `33`, `41`. _(R8.7, R8.1, R8.2, R8.3, R8.4, R8.5)_
  - [ ] 6.2 **Property 1 + Property 4** + behaviour-invariance close-out. **Property 1: the provenance collapse preserves the resolved field set and order** — snapshot the resolved field set + `(group.order, field.order, key)` order before/after step 8; assert identical. **Property 4: member data invariant across every Phase 3 step** — snapshot arbitrary member records before/after each step; assert byte-for-byte equality. Confirm no `members.*` analytics param was introduced and the `config#fields`/`TenantOverlay.overrides` names are unchanged (Phase 2 R6.8 guard continued). **Validates: Requirements 1.6, 6.1, 7.1, 7.2** _(R7.1, R7.2, R6.4)_
  - [ ] 6.3 CI/CD + ship + governance (per `43-cicd-deploys.md`, `40-spec-workflow.md`). Feature branch (e.g. `spec/members-config-phase3-reshape`); never push to `test`/`main` directly. Run the paired tests locally first. PR into `test`; clear CodeQL + GitGuardian. Preview the prod changeset (`--no-execute-changeset`) — confirm NO unexpected `Replacement: True` (Phase 3 adds no infra/table change). Promote `test → main` by MERGE commit. IF a config-row migration is needed, run it against TEST then PRODUCTION via `backend/scripts/railway-db.sh` (`#database` skill) — not auto-applied, never member data. Deploys touch the DATA account only; no Cognito/identity change. **Governance DoD:** update `38-sam-module-field-config.md` (+ `35`/`37`/`00-index.md` cross-refs) IF the authoring model evolved, ELSE record "no steering change due" with evidence. Tick `impact-analysis.md` §9 Phase 3 steps 8–11 done with a pointer to this spec folder. _(R9.1, R9.2, R9.3, R9.4, R9.5)_

---

## Notes

### Requirements coverage

| Requirement | Tasks |
|---|---|
| R1 (fixed/overlay → one list + provenance) | 1.1, 1.2, 1.3 |
| R2 (scope-binding → field attribute, resolver unchanged) | 2.1, 2.2, 2.3 |
| R3 (analytics → calculated fields / attributes) | 3.1, 3.2 |
| R4 (rebuild group → field → attribute UI) | 4.1, 4.2, 4.3 |
| R5 (one authoring surface) | 5.1 |
| R6 (bounded, layering-preserving SAM reshaping) | 1.1, 2.1, 6.2 |
| R7 (non-destructive to member data) | 6.2 |
| R8 (Change-With-Tests blast radius) | 1.2, 2.2, 2.3, 3.2, 4.3, 5.1, 6.1 |
| R9 (ship safely + governance DoD) | 6.3 |

### Correctness property → task

| Property | Task |
|---|---|
| P1 — provenance collapse preserves resolved field set + order | 6.2 |
| P2 — scope resolution equivalent across the authoring-representation change | 2.3 |
| P3 — analytics folding value-equivalent | 3.2 |
| P4 — member data invariant across every step | 6.2 |

### Ordering guarantees

- Steps 8/9/10 (groups 1–3) are mutually independent representation changes; each is behaviour-
  preserving on its own (Properties 1–3) and ships with its paired tests.
- Step 11 (group 4) authors against all three, so it runs after them.
- §5 (group 5, one door) lands WITH step 11 — never a window with zero authoring surfaces.
- Nothing in Phase 3 migrates member data (Property 4); any config-row migration is `31`-compliant.

### Deferred / explicitly NOT done here (recorded)

- "Only `member_id` is fixed" literal model change — out of scope (`impact-analysis.md` §4.1, §10).
- Option C (SAM-native authoring; deletes the projection layer; needs a steering-36 revision) — out of
  scope (`impact-analysis.md` §9 step 12, §10). Config home stays Option B.
- Renaming `TenantOverlay.overrides` / `config#fields.overrides` — continues the Phase 2 R6.8 guard.
- Any change to the generic Members table runtime (`useFilterableTable`) — the TOP-rated surface stays.
- Starting the next SAM modules (Webshop, Events) — `impact-analysis.md` §11 is forward guidance.

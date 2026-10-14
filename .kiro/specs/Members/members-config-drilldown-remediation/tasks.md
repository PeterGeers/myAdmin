# Implementation Plan — Members config drill-down remediation

## Overview

Remediates the Phase-3 drill-down defects (issue log
`Parameter redesign/phase-3-reshape-model-and-ui/review-issues.md`, I-3..I-9). Grounded in `design.md`
(the VERIFIED server-truth table). Three clusters:
- **A** — the drill-down DISPLAYS from the resolved `FieldConfig`, writes back to the overlay slice;
  labels resolve from the served `label{}` (SPA-only). *(R1, R2, R4)*
- **B** — scope is an editable field attribute whose values ARE the field's enum values
  (single-vocabulary); SAM read-wire + Flask vocabulary change + the `_map_fixed_override` builder gap.
  *(R3, R5)*
- **C** — move-to-group persists through save. *(R6)*

Planes: SPA (`frontend/src`, Vitest+RTL), SAM (`sam/members`, pytest), Flask (`backend/src`, pytest).
Change-With-Tests (`30`/`32`/`34`) on every behavioural edit. Shell per `41` (POSIX `cd`,
`<<<DONE marker=$?>>>`, `backend/.venv`). Member data invariant (P5). Catalog drift guard stays green.

**Branch:** continue on `spec/members-config-phase3-reshape` (the drill-down lives there), or a fresh
`spec/members-config-drilldown-remediation` — decide at ship (task 7). One PR into `test`.

## Task dependency graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3"] },
    { "id": 3, "tasks": ["4.1"] },
    { "id": 4, "tasks": ["5.1"] },
    { "id": 5, "tasks": ["6.1", "6.2"] },
    { "id": 6, "tasks": ["7.1"] }
  ]
}
```

Rationale: Cluster A's read-layer (1) + modal seed (2) land first — the biggest visible win and the
foundation the modal's scope/enum work builds on. Scope (B) needs the SAM read-wire + Flask change (3)
before the modal scope section (that's within 2/3). The builder gap (4) and move-to-group (5) are
independent. Verify (6), ship (7) last.

## Tasks

### Cluster A — display from the resolved config (R1, R2, R4) — SPA only

- [x] 1. Read the resolved `FieldConfig` for display (not the raw overlay)
  - [x] 1.1 Add/confirm a resolved-config read layer for the drill-down tables: derive the group list
    and per-group field list from the resolved `FieldConfig` (reuse `groupResolvedFields` /
    `orderResolvedFields` in `membersConfigService.ts` — the superseded hierarchy already did this
    correctly). Keep `overlayModel` as the WRITE model only. Wire `MembersGroupsTable` /
    `MembersFieldsTable` to display from the resolved config; `groupFieldCount` for the delete-guard
    counts RESOLVED fields. Change-With-Tests: the two table suites assert fixed+calculated+added
    fields all appear, in derived order; delete-guard counts base fields. _(R1.1–R1.4, R7.1)_
  - [x] 1.2 Label resolution (R4): resolve drill-down field/group labels from the served `label{}`
    (`label[lang] ?? label.en ?? label.nl ?? key`); REMOVE `useMembersLabels`/`resolveShippedLabel`/
    `LABEL_KEY_SCHEME` as the drill-down's label authority (keep the service functions only if a
    seed/default consumer remains; else delete). Change-With-Tests: label-resolution test reads the
    served dict, language selector picks the variant, fallback never blank; the `useMembersLabels`
    test is removed/realigned. _(R4.1–R4.4, R7.1)_
  - [x] 1.3 **Steering guardrail — rewrite `38` rule 6 (governance, in THIS change, R4.5).** Update
    `.kiro/steering/38-sam-module-field-config.md` rule 6 from "Option (b) resource keys" to "tenant
    labels are plain per-language values stored in config, resolved at runtime; shipped resource files
    are a seed/default for base fields only." Keep the still-true parts (enum `value` language-neutral;
    the fallback order). This is an `inclusion: auto` guardrail that steers Events/Webshop — it MUST
    land with the label-resolution change (1.2), not be deferred, so the steering and the code agree.
    (Already drafted during spec authoring — confirm it matches the shipped behaviour at close-out.)
    _(R4.5)_

- [x] 2. Field modal seeds from the resolved field; writes back to the right overlay slice
  - [x] 2.1 `MembersFieldModal.formFromField`: seed `type` from the resolved `field.type` (NO silent
    `string` default, R2.2); seed the enum vocabulary from `options` (rich or bare — NOT `choices`,
    R2.1); seed `label` from `label{}`. Change-With-Tests: `status` opens as enum with 6 options;
    `region` opens as enum with its scope-sourced values; a string field opens as string.
    _(R2.1–R2.3, R7.1)_
  - [x] 2.2 Origin-aware write-back: `overlayModel` create/edit targets the right slice by
    origin/provenance — tenant-added → `fields[key]`; base/base_overridden → `fixed_overrides[dotted]`;
    calculated → read-only (no write). The single-save path is unchanged. Change-With-Tests: editing a
    FIXED field writes a `fixed_overrides` entry; editing an ADDED field writes a `fields` entry; one
    save → one request. _(R1, R7.1)_

### Cluster B — scope as an editable field attribute + the builder gap (R3, R5)

- [x] 3. Scope-as-field-attribute, single-vocabulary (R3)
  - [x] 3.1 SAM read-wire: add `scope` to `ResolvedField`; populate it in `_apply_override` /
    `_as_variable_field` from `override.scope` / `of.scope`; emit `scope` `{enabled, required_for}`
    in `_serialize_field`. Correct the misleading docstrings ("carried verbatim" → actually carried).
    Resolver edge (`handler/app.py`) UNCHANGED. Change-With-Tests: `test_field_resolver.py` /
    `test_members_resolved_field_surface.py` assert the served `scope`; `test_scope_access.py` asserts
    unchanged `allowed_scopes` (P3). _(R3.5, R3.8, R7.1)_
  - [x] 3.2 Flask single-vocabulary change: `_scope_dimensions_from_overlay` derives the dimension
    `values` from the field's ENUM VALUES (`choices`/`options[].value`) when `scope.enabled`, not from
    `scope.values`. `members_parameters.json` scope object drops `values`; `_validate_field_scope`
    requires an enum-with-values when scope enabled (legacy `scope.values` honoured as fallback only).
    Change-With-Tests: builder derives values from the enum; validator rejects scope-enabled on a
    value-less/non-enum field; projection-sync test. _(R3.3, R3.4, R7.1)_
  - [x] 3.3 SPA scope section (single vocabulary): add `scope?: {enabled?, required_for?}` to
    `FieldConfigField` (`types/members.ts`); the field modal scope section = `enabled` toggle +
    `required_for` control, reading the served `scope`; the field's enum-values editor is the ONE
    vocabulary (no separate scope-values list). Change-With-Tests + **round-trip (P2, R3.7):** enable
    scope, ADD a value, REMOVE a value, save → the committed overlay + re-resolved config reflect it in
    both the enum options and `config#scope`. _(R3.1, R3.2, R3.6, R3.7, R7.2)_

- [x] 4. Flask `config#fields` builder carries fixed-override attributes (R5, I-9)
  - [x] 4.1 `_map_fixed_override` / `_FIXED_OVERRIDE_FIELDS` carry `options` (+ coherent `choices`) and
    `scope` through to `config#fields`, preserving presentation-only invariants (no weakening). DO NOT
    add `member_number_format` here (deferred, R5.2). Change-With-Tests: a fixed-override enum
    relabel + a fixed-override scope survive projection (`test_projection_sync` / builder tests).
    _(R5.1, R5.3, R7.1)_

### Cluster C — move-to-group persistence (R6, I-8)

- [x] 5. Move-to-group persists through save
  - [x] 5.1 `functional_group` single source of truth: `MembersFieldModal.buildField` STOPS hardcoding
    `functional_group: groupKey`; it leaves the field's current group untouched unless the user changed
    it in the modal (derive from the working overlay). The move action stays the mutator.
    Change-With-Tests + **regression (P4, R6.3):** move a field to another group → editor Save → the
    field persists in the TARGET group. _(R6.1, R6.2, R6.3, R7.2)_

### Verify + ship

- [x] 6. Verification + behaviour/data invariance
  - [x] 6.1 Run the touched suites green: SPA MembersConfig folder + ParameterManagement; SAM
    `test_field_resolver`/`test_scope_access`/`test_members_resolved_field_surface`/
    `test_calculated_fields`; Flask members_config_validation + projection_sync + builders. Catalog
    drift guard green. _(R7.1, R7.3)_
  - [x] 6.2 **Properties P1–P5** close-out: display completeness (P1), scope round-trip (P2), scope
    resolution invariance (P3), move persistence (P4), member-data invariance (P5 — by construction,
    no member-data path). Confirm `config#fields`/`TenantOverlay.overrides` names unchanged (Phase-2
    R6.8). _(R8.1, R7.2)_
- [ ] 7. Ship (per `43`, `40`)
  - [ ] 7.1 Feature branch → PR into `test`; CodeQL + GitGuardian green; preview the prod changeset
    (no unexpected replacement); promote `test → main` by merge. DATA account only. Tick the
    remediated issues (I-3/I-4/I-5/I-6/I-8/I-9 + I-2 SPA half) in `review-issues.md`; note Phase-3
    `tasks.md` that 4.x shipped-with-defects were remediated here. The follow-up spec (steering `38`
    rule-6 text, I-7a validation feature, I-7b member-number authoring) is tracked separately.
    _(R8.2, R8.3)_

## Notes

### In THIS spec (not deferred)
- Steering `38` rule-6 rewrite (the i18n-label guardrail) — task 1.3, lands with the label code (1.2).

### Deferred to the follow-up spec (recorded)
- I-7a — general per-field validation/format attribute (iban/date-time/…) — needs a decision.
- I-7b — member_number_format runtime tenant authoring (schema + builder + modal).

### Issue → requirement → task map
| Issue | Req | Task |
|---|---|---|
| I-3 (missing fields) | R1 | 1.1 |
| I-4 (enum values) + status-as-string | R2 | 2.1 |
| I-2 (SPA label resolution + steering `38` rule-6 guardrail) | R4 | 1.2, 1.3 |
| I-5 + I-6 (scope attribute, single-vocabulary) | R3 | 3.1, 3.2, 3.3 |
| I-9 (fixed-override builder drop) | R5 | 4.1 |
| I-8 (move-to-group revert) | R6 | 5.1 |

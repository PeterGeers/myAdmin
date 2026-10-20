# Requirements — Members config drill-down remediation

> **Status: REQUIREMENTS.** A focused BUGFIX/remediation spec for the Members config drill-down UI
> built in `.kiro/specs/Members/Parameter redesign/phase-3-reshape-model-and-ui/` (tasks 4.x). A
> review of the shipped build surfaced nine issues (logged in that phase's `review-issues.md`); this
> spec fixes the ones that are **bugs in the shipped build** and defers the ones that are **model /
> steering / new-feature changes** to a second follow-up spec.
>
> **Grounded in a verified server-truth pass** (not assumptions): the SAM resolver + serializer +
> Flask builders + h-dcn seed were read end-to-end. The resulting attribute table is in `design.md`
> §Server truth and is the baseline every requirement here is written against.
>
> **Source of record:** the issue log
> `.kiro/specs/Members/Parameter redesign/phase-3-reshape-model-and-ui/review-issues.md` (issues
> I-1..I-9). This spec's requirements map 1:1 to those issues.

## Introduction

The Phase-3 drill-down (functional-groups table → group modal → fields table → field modal) was built
reading the **raw `field_overlay`** param (tenant deltas only). The server, however, serves a fully
**resolved `FieldConfig`** (fixed ⊕ overlay ⊕ calculated, with provenance, enum `options`, labels).
Reading the wrong source makes most of the visible defects: fixed/calculated fields missing from
groups, `region`'s enum values gone, `status` shown as `string`, scope "not selected". Three further
issues are independent: scope is not wired on the SAM READ path, the Flask `config#fields` builder
drops some fixed-override attributes, and move-to-group reverts on save.

This spec remediates the **bugs**. It does NOT reverse steering (the i18n-label steering text), add a
new validation subsystem, or add member-number runtime authoring — those are a separate follow-up
spec (see Out of scope).

## Scope — the fix clusters

- **Cluster A — the drill-down reads the resolved config (SPA-only).** Covers I-3 (missing
  fixed/calculated fields), I-4 (enum values gone), the `status`-as-`string` instance, and the SPA
  half of I-2 (labels read from the resolved `label{}`, dropping the resource-key resolver).
- **Cluster B — scope as an editable field attribute + the builder gap.** Covers I-5+I-6 (scope is a
  real, editable, round-tripping field attribute with the SINGLE-vocabulary rule) and I-9 (the
  `_map_fixed_override` builder drops attributes).
- **Cluster C — move-to-group revert (I-8).**

## Requirements

### R1 — The drill-down displays the full resolved field set (I-3)

**User story:** As a tenant admin, I want every field in a group — platform fixed, calculated, and
tenant-added — to appear in the drill-down, so that I see the real configuration, not only the
tenant's overlay deltas.

#### Acceptance criteria
1. THE drill-down tables (groups, fields) SHALL derive their displayed fields and groups from the
   RESOLVED `FieldConfig` (`GET /members/field-config`), NOT from the raw `field_overlay` param.
2. A group's fields table SHALL list ALL resolved fields assigned to that group — fixed, calculated,
   and tenant-added — in the derived `(group.order, field.order, key)` order.
3. `groupFieldCount` (the delete-group-only-when-empty guard, R4.2 of Phase 3) SHALL count the
   RESOLVED fields in a group, so a group holding only base fields is correctly non-empty.
4. WHERE the resolved config is unavailable (fetch failure / older module build) THEN the drill-down
   SHALL degrade to an "unavailable" note and never block, per the existing best-effort posture.
5. THE fixed and calculated (predefined) fields SHALL ALWAYS appear in the drill-down ("seeded"
   items) — a tenant SHALL NOT be able to ADD or DELETE them. "Add field" in a group SHALL create a
   tenant VARIABLE field only. A tenant MAY change a predefined field's presentation (group / label /
   order / `visible` show-hide); a CALCULATED field is additionally value/type/inputs read-only. No
   "add predefined field from catalog" picker is in scope (the fields are already present).
   _(confirmed design decision)_

### R2 — Field type and enum values display correctly (I-4, status-as-string)

**User story:** As a tenant admin, I want a field's type and its enum values to show correctly in the
field modal (e.g. `status` as an enum with its 6 options, `region` with its 10 values), so that I can
see and edit the real vocabulary.

#### Acceptance criteria
1. THE field modal SHALL read a field's `type` and enum vocabulary from the RESOLVED field, which
   serves enum values under the `options` key (rich `{value,label,roles?}` OR a bare string list) —
   NOT from the overlay's `choices`.
2. THE field modal SHALL NOT silently default an unknown/absent `type` to `string`; it SHALL use the
   resolved field's actual `type`.
3. WHEN a fixed enum field (e.g. `status`) is opened THEN its 6 options SHALL be shown; WHEN a
   scope-backed enum (`region`) is opened THEN its scope-sourced values SHALL be shown (R3).

### R3 — Scope is an editable field attribute; its values ARE the field's enum values (I-5 + I-6)

**User story:** As a tenant admin, I want to make a field a scope axis and edit its value vocabulary
directly in the field modal (add a value, remove a value), with scope resolution honouring whatever I
define, so that scope is configured where the field is configured — no separate scope editor.

#### Acceptance criteria
1. THE field modal SHALL present a scope section with an `enabled` toggle and a `required_for` roles
   control. It SHALL NOT present a separate "scope values" list.
2. THE scope VALUES SHALL BE the field's ENUM VALUES — a single vocabulary. The field's enum-values
   editor is the ONE editor; marking the field a scope axis references that list. Adding an enum value
   adds a scope value; removing one removes it from scope.
3. THE stored `scope` attribute SHALL be `{enabled, required_for}` only — it SHALL NOT carry a `values`
   list (a legacy stored `scope.values` MAY be honoured as a migration fallback only).
4. THE Flask scope builder (`_scope_dimensions_from_overlay`) SHALL derive the `config#scope`
   dimension's `values` from the field's ENUM VALUES (`choices` / `options[].value`) when
   `scope.enabled` is true, instead of reading `scope.values`. The param schema SHALL drop the
   `scope.values` subfield; the validator SHALL require the field to be an enum WITH values when scope
   is enabled.
5. THE SAM resolver SHALL populate `ResolvedField.scope` (from the overlay/override scope) and the
   serializer SHALL emit a `scope` key, so the modal can READ the current scope state back (today it
   is dead — never populated, never serialized). The misleading docstring SHALL be corrected.
6. THE frontend `FieldConfigField` type SHALL model the served `scope` attribute.
7. **Round-trip:** WHEN a tenant enables scope on a field, ADDS a value and REMOVES a value, and saves,
   THEN `config#scope` SHALL reflect the edited vocabulary, the field's resolved enum options SHALL
   reflect it, and scope resolution SHALL honour it — asserted by a regression test.
8. THE scope RESOLUTION code (`handler/app.py` → `allowed_scopes`) and the `scopegrant#` grants SHALL
   remain unchanged (Phase 3 R2.3/R2.4 preserved).

### R4 — Field LABELS resolve from the stored per-language value, not shipped resource keys (SPA half of I-2)

**User story:** As a tenant admin, I want a field's label to come from the label stored on the field
(editable at runtime), so that renaming a field takes effect immediately without a new app version.

#### Acceptance criteria
1. THE drill-down SHALL resolve a field/group label from the RESOLVED field's stored `label{nl,en}`
   dict (the server already serves a plain inline label — no resource-key indirection on the server).
2. THE SPA resource-key resolver layer (`useMembersLabels` / `resolveShippedLabel` / `LABEL_KEY_SCHEME`
   as the resolution AUTHORITY, task 4.1) SHALL be removed from the drill-down's label resolution; a
   plain `label[lang] ?? label.en ?? label.nl ?? key` helper SHALL be used.
3. THE shipped `locales/*/admin.json` `membersConfig.*` entries MAY remain as an onboarding/default
   SEED for platform base fields, but SHALL NOT be the runtime resolution source for a tenant-editable
   label.
4. THE viewer's language (the language selector) SHALL select the label variant; fallback SHALL never
   be blank. The tenant's preferred language is the admin's active UI language at authoring time (no
   new hard setting).
5. THE steering `38-sam-module-field-config.md` **rule 6 SHALL be rewritten IN THIS SPEC** (NOT
   deferred): from "Option (b) resource keys" to "tenant labels are plain per-language values stored in
   config, resolved at runtime; shipped resource files are a seed/default for base fields only." Rule 6
   is an `inclusion: auto` **guardrail** that steers the next modules (Events/Webshop); leaving it
   stating the reversed model would (a) make this remediation violate its own governing steering and
   (b) steer the next module straight back into the unsustainable choice. The governance
   definition-of-done (`40`) requires the steering a change touches to be updated in the same change.

### R5 — The Flask `config#fields` builder carries fixed-override attributes (I-9)

**User story:** As a maintainer, I want a tenant's fixed-field overrides (enum options, scope,
member-number format) to survive projection to `config#fields`, so that editing a fixed field via the
generic path is not silently dropped.

#### Acceptance criteria
1. THE Flask builder `_map_fixed_override` / `_FIXED_OVERRIDE_FIELDS` SHALL carry `options` (and the
   coherent `choices`) and `scope` on a fixed-override entry through to `config#fields`, in addition to
   the current label/visible/required/order/functional_group.
2. `member_number_format` on a fixed override is DEFERRED to the follow-up spec (I-7b) — it is NOT
   added to the builder here, to keep this spec to the drill-down's needs. (Recorded so the omission
   is deliberate.)
3. THE change SHALL preserve the "fixed override is presentation-only, cannot weaken a platform
   invariant" rule (the resolver's existing rejection semantics stay authoritative).

### R6 — Move-to-group persists through save (I-8)

**User story:** As a tenant admin, I want moving a field to another group to stick after I save, so
that the move is not silently reverted.

#### Acceptance criteria
1. `functional_group` SHALL have ONE source of truth per field: the field's stored value (edited by
   the move action), read live from the working overlay — NOT the stale group the modal was opened
   under.
2. THE field modal SHALL NOT re-author `functional_group` to the opened-group prop on save; it SHALL
   either leave `functional_group` untouched unless the user changed it in the modal, or derive it
   from the field's current working value.
3. **Regression:** WHEN a field is moved to another group and the editor saves THEN the field SHALL
   persist in the TARGET group (asserted by a test).

### R7 — Every behavioural change updates its allocated tests (Change-With-Tests)

**User story:** As a maintainer, I want the paired tests updated in the same change as each
behavioural edit, so the remediation does not pass locally by luck and break the nightly suite.

#### Acceptance criteria
1. Each Cluster-A/B/C change SHALL update/add its paired SPA (Vitest/RTL) and/or SAM/Flask (pytest)
   tests in the SAME change (`30`/`32`/`34` Change-With-Tests).
2. THE scope round-trip (R3.7), the move-to-group persistence (R6.3), the resolved-config read
   (R1/R2), and the label resolution (R4) SHALL each have an explicit regression test.
3. THE Phase-1 catalog drift guard SHALL stay green.

### R8 — Ships safely; member data invariant

#### Acceptance criteria
1. NO change SHALL read or write member records (`sam-members`); member data stays invariant.
2. THE remediation SHALL ship through the standard pipeline (feature branch → PR into `test` → promote
   by merge), per `43-cicd-deploys.md`. IF a config-row migration is needed (it is not expected) it is
   `31`-compliant.
3. THE deploy SHALL touch the DATA account only; no Cognito/identity change.

## Out of scope (this spec) — deferred to the follow-up

- **I-7a — a general per-field validation/format attribute (IBAN / date-time / email / regex):** a new
  capability absent from the attribute model, with no recorded decision found. Needs a design decision
  on provenance/scope first.
- **I-7b — member_number_format runtime tenant authoring:** add the authoring control + the Flask
  schema/builder path. Depends on R5's builder work but adds new authoring surface; deferred.
- Any change to the generic Members table runtime (`useFilterableTable`) or member-record validation.

## Traceability to the issue log

| Req | Issue(s) | Cluster |
|-----|----------|---------|
| R1 | I-3 | A |
| R2 | I-4, status-as-string | A |
| R3 | I-5 + I-6 (merged, single-vocabulary) | B |
| R4 | I-2 (SPA half) | A |
| R5 | I-9 | B |
| R6 | I-8 | C |
| R7 | R7 of Phase 3 / `30`/`32`/`34` | all |
| R8 | `43`; Phase-3 R7 (member-data invariant) | ship |

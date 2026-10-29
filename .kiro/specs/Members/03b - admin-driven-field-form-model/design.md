# Design Document

## Overview

03b makes the tenant admin's field configuration authoritative by REMOVING the hardcoded bindings
that overrule it, UNIFYING selectable fields under one model (an enum field carries its own values
with a per-option `allowed` flag — "reference" is a feature on a field, not a separate catalog),
fixing the config toggles that silently drop an OFF write, making enum labels resolve uniformly in
filters, and deleting the dead plumbing left behind — for a NET DECREASE in code. It concerns the
SAM Members module (`sam/members/`) and its React frontend; the only cross-plane touch is the Flask
`members.scope_dimensions` mirror + the grant reconciliation (Req 4).

All design claims below are grounded in the real code and LIVE h-dcn data read during this phase
(not assumptions). No code is written until this design is approved.

## Verified ground truth (evidence gathered this phase)

- **The field store is generic.** `config#fields` is a JSON record with no fixed attribute schema
  (steering 39; `data-model.md`). A field already carries heterogeneous feature attributes
  (`required`, `scope:{enabled}`, `application_*`), so adding a per-option `allowed` flag is the
  existing mechanism, not a schema change.
- **`region` is ALREADY unified** (live `config#fields.region`): full inline `choices`+`options`
  (10 values incl. `Geen`) with `scope:{enabled:true}`; `config#scope` mirrors the same 10 values
  with `required_for:["Members_CRUD"]`. So region needs **no data migration** — only the
  derive-on-save trigger (Req 4) keeps the two consistent going forward.
- **`membership_type` is the one real relocation.** Its override in `config#fields` carries NO
  inline options (only `application_choices` + `application_visible`); the vocabulary lives entirely
  in the `membershiptype#<code>` catalog in `sam-members` (7 entries; `erelid` is `active:false`).
- **`application_*` attributes** are written onto fields by the code but absent from
  `data-model.md`/`config-guide.md` — a documentation gap, not a structural divergence.
- **The grant reconciliation is built but UNWIRED.** `UserTenantScopeService.reconcile_scope_change`
  / `assert_appliable` exist and are unit-tested but have NO production caller (full-repo grep);
  it lives on the Flask plane while `config#scope` is now SAM-authored.

## Architecture

Unchanged from the platform standard (steering 35): React (presentation) → API Gateway → Lambda
handler (thin adapter) → domain service (authoritative rules) → repository (the only DynamoDB
touch) → DynamoDB. 03b changes WHAT the domain/repository do for selectable fields, not the layering.

Planes and ownership (steering 35/39, confirmed this phase):
- **SAM plane** authors `config#fields` and `config#scope` in `governance_projection` via the
  Change-Op write path (`projection_config_write_repository`), and owns member data + the (soon
  removed) membership-type catalog in `sam-members`.
- **Flask plane** owns `user_tenant_roles` / `user_tenant_scope` (the grants), projected into SAM as
  `scopegrant#` rows, and holds the `members.scope_dimensions` mirror the grant validators read.
- **The one cross-plane interaction** 03b adds is the scope-field save (Req 4): it updates SAM
  `config#scope` and keeps the Flask mirror consistent, and wires in the grant reconciliation. No
  runtime SAM→MySQL call (the reconciliation runs on the Flask plane — decision D-a below).

Data-flow deltas:
- Selectable-field read: options come from the FIELD's own resolved `options` (one assembly pass),
  no catalog injection.
- Member write: the membership_type reference check reads the field's options, not the catalog.
- Scope-field save: derive `config#scope` from the field → reconcile grants → write SAM then mirror.

## Migration-safety proof (Req 3.6 — the implementation gate)

The collapse of the `membershiptype#<code>` catalog into the `membership_type` field's enum options
must orphan NO stored member reference. Proven against the FULL live h-dcn member population
(1215 `member#` rows, complete query — no pagination), tallied by `membership.membership_type`:

| stored value | members | catalog entry | after collapse |
| --- | ---: | --- | --- |
| `gewoon_lid` | 936 | active (order 10) | option, `allowed:true` |
| `gezins_lid` | 200 | active (order 15) | option, `allowed:true` |
| `overig` | 57 | active (order 50) | option, `allowed:true` |
| `gezins_donateur` | 17 | active (order 35) | option, `allowed:true` |
| `erelid` | 4 | **retired** (order 20) | option, **`allowed:false`** (grandfathered) |
| `donateur` | 1 | active (order 30) | option, `allowed:true` |

**Result:** every stored value maps to an existing catalog entry → zero orphans. The only retired
value, `erelid` (4 members), is the grandfather case the `allowed:false` flag preserves (kept,
displayed, valid on read; not offered for new records). Catalog entries with zero members
(`gezins_donateur` had 17, `sponsor` 0) are harmless — an offered option nobody has picked.
`region` needs no proof row (already unified); the proof confirms `config#scope` and
`config#fields.region` carry the same 10 values today.

This proof is re-run as the pre-migration integrity scan (Req 6.3) against TEST and PROD before the
migration applies.

## Data Models

### The unified enum-field model (Req 3)

### Option shape
The existing `EnumOption` (`sam/members/domain/fixed_fields.py`) is `{value, label{nl,en}, roles?}`.
03b adds one optional attribute:

```
EnumOption = { value, label{nl,en}, roles?, allowed: bool = true, order?: int }
```

- `value` — the stored, immutable reference key (the former `type_code` for membership_type).
- `label{nl,en}` — per-language display; `value` stays language-neutral.
- `allowed` — `true` (offered in the picker) / `false` (grandfathered: hidden from new/changed
  records, retained+valid for existing). Freely toggleable both ways.
- `order` — presentation order (carries the catalog's `order`; absent elsewhere → stable input order).

"Reference" becomes a feature on the field: a field whose options are authored and whose `value`s
are referenced by member records. No distinct storage model, no `active_only` catalog.

### Re-pointing the reference check (the orphan-safety seam)
`_membership_writes_validation._validate_membership_type_reference` today calls
`self._repo.get_membership_type(tenant_id, type_code)` and checks `entry.active`. It is re-pointed
to the field's resolved options:

- "exists" → `type_code` ∈ the `membership_type` field's `options[].value`;
- "assignable" → that option's `allowed is true`;
- unchanged: the check runs ONLY on create/update of a CHANGED value, so existing members with a
  now-retired value stay valid (grandfathering preserved by construction — design C8).

The option-assembly seam `_membership_writes_fieldconfig.get_field_config` /
`_assemble_field_options` stops injecting `list_membership_types(active_only=True)` as the field's
options; the options come from the field itself (resolved view). This is the ONE assembly pass —
no per-kind branching.

### Authoring surface (replaces the catalog UI)
membership_type options are authored through the ORDINARY field-options editor
(`MembersFieldModal` family), carrying per-option `label`/`order`/`allowed`, `value` immutable. The
separate TenantAdmin → Members → Membership Types screen is removed (Req 7.2).

## Components and Interfaces

The per-requirement changes below are grouped by component. Each names the exact file/function seam
(verified this phase) and the paired tests to update in the same change (steering 30/34/39).

## Requirement 1 — remove the hardcoded bindings

Two enforcement sites, both confirmed in `sam/members/` (NOT the retired Flask copy):

1. **No-relax (author-time):** `config_write_service._validate_application_attributes` →
   `_collect_application_attr_reasons` invariant 3: `if platform_required and
   spec["application_required"] is False: <reject>`, with `platform_required` from
   `fixed_fields.field_by_key`. **Remove** invariant 3 and the `platform_required` plumbing; KEEP
   invariant 1 (`application_choices` ⊆ field choices) and invariant 2 (known `format.checker`) —
   those are well-formedness, not an overrule.
2. **Overlay invariant (resolve-time):** `field_resolver._reject_invalid_overlay`:
   `if override.required is False and fixed.required: "cannot make a platform-required fixed field
   optional"`. **Remove** this clause (the only required field that remains intrinsically required
   is `member_id`; every other requiredness is the admin's config, Req 1.3). Keep the other
   overlay checks (unknown-key, key-collision, dangling functional_group, choiceless-non-scope-enum).

**Forced-required/visible special-cases (frontend):** `ApplicationFieldAttributes.tsx`
`requiredForced = isPlatformRequired(field) || isMembershipType` and the membership_type default
stamp (`_membership_writes_application._default_membership_type`) — remove the forcing so the admin
decides; keep the "supply the default when the field is OFF the form" behaviour (Req 3.1-equivalent:
a field left off the form still submits a valid default).

Tests to update in the same change: `test_config_write_service.py` (relax cases ~753/829),
`test_field_resolver.py:209`, `test_status_retirement_preservation_props.py:397`,
`test_field_models_application_attrs.py` (keep the "two axes don't alias" assertion).

## Requirement 2 — config toggles persist both ways

Root cause is FRONTEND only (backend `set_field_application` already SETs an explicit `false`).
In `fieldConfigChangeOps.ts`, `applicationAttrs` omits any `undefined` attr and the emit gate drops
an all-`undefined` op, so turning a toggle OFF (written as `undefined`) emits NO op and the stored
`true` persists. Fix mirrors the 03a `required` fix in `MembersFieldModal.tsx` (send explicit
`false`, not `undefined`):

- `ApplicationFieldAttributes.tsx` `onToggleRequired`: `application_required: next` (not
  `next ? true : undefined`).
- `ApplicationFieldModal.tsx` `toggleOnForm`: `application_visible: on` (not `on ? true : undefined`).

So an OFF emits an explicit `false` → `set_field_application` issues `SET ... = false`. Applies to
every field in every group (Req 2.3). Paired tests: `fieldConfigChangeOps.test.ts`,
`ApplicationFieldAttributes.test.tsx`, `ApplicationFieldModal.test.tsx`.

## Requirement 4 — scope dimension DERIVED from the field; reconciliation wired in

### Two-item save
Saving a scope-flagged field (`scope:{enabled:true}`) derives the `config#scope` dimension from the
field's own options and updates BOTH: (1) SAM `config#scope` (authoritative, the frontend-mirror
model, spec 02 — SAM first), (2) the Flask `members.scope_dimensions` mirror the grant validators
read. The Flask→SAM projection of `user_tenant_roles`/`user_tenant_scope` (`scopegrant#` rows) is
UNCHANGED and keeps working. A failed mirror surfaces a retry; SAM stays source of truth (Req 4.3/4.4).

### Reconciliation (the combined Tenant_Admin + SysAdmin rule)
Before a scope-field save that changes the value set is applied, the proposed dimension set is
classified by `reconcile_scope_change` (routine vs. orphaning). Routine → apply + remind. Orphaning
(a rename/remove stranding a grant) → BLOCK with "contact your System Administrator to realign
grants" (`assert_appliable` raises `ScopeReconciliationBlocked`). This logic EXISTS but is unwired;
03b wires it into the save path.

**Cross-plane design decision (open, to resolve here):** the reconciliation reads `user_tenant_scope`
(MySQL) and lives on the Flask plane; `config#scope` is authored on the SAM plane. Steering 35/39
forbid a runtime SAM→MySQL call. Options for where the check runs:
- **(D-a) Flask authoring endpoint owns it** — the scope-field save is mediated by the existing Flask
  config path that already writes the mirror; it calls `reconcile_scope_change` before writing SAM
  `config#scope` via the SAM write API. Keeps the DB read on the Flask plane (no boundary breach).
- **(D-b) SAM save returns "proposed", Flask reconciles** — SAM computes the derived dimension,
  Flask (owning the grant data) reconciles and either applies or blocks.
RECOMMENDED: **D-a** — the frontend-mirror model already has the frontend/Flask writing both planes;
the reconciliation belongs where the grant data is. Confirm in review before implementation.

## Requirement 5 — uniform enum labels in filters

Display already resolves labels (`fieldValue.renderFieldValue` → `resolveEnumValueLabel`). The
FILTER paths in `useMembersColumns.ts` (`searchedRows`, `enrichedRows` via `columnValue.coerceByType`)
key off the raw stored value. Fix: resolve the per-language label for enum columns in the
filter/search value (reuse `resolveEnumValueLabel`/`labelResolver`), so typing "Actief" matches
`status=active`. Paired test: `applicationFilterParity.test.ts` + a `useMembersColumns` test.

## Requirement 6 — the data migration (membership_type only)

A SAM-plane (DynamoDB) migration script under `sam/members/migration/`:

1. **`config#fields`** (`governance_projection` / `test_governance_projection`) — fold the catalog
   into the `membership_type` field's `options` (`value`=type_code, `label`, `order`, `allowed`=`active`);
   `erelid` → `allowed:false`. Carry any residual 03a `choices`→`options` cleanup.
2. **`sam-members`** — retire the `membershiptype#<code>` rows after the fold (member references
   untouched; existing values grandfathered).
3. region / `config#scope` — NOT migrated (already consistent); kept so by the Req 4 trigger.

Properties: idempotent + re-runnable; back up every affected row first (reuse the
`.agent-output` backup pattern + a committed fixture under `backend/tests/fixtures/`);
integrity scan (the proof above) before AND after asserting zero orphans; run TEST then PROD
identically, scan-gated (account `nonprofit-deploy` 506221081911, steering 23/41). A value
rename/remove that would strand a grant is a SAVE-time block (Req 4), never a migration step.

## Requirement 7 — remove dead/not-asked-for code

- `config#views`: NOT touched (deferred feature, Req 7.1 / backlog `members-preferred-overview-columns.md`).
- Remove the no-relax + overlay-invariant plumbing and their tests (Req 1), not merely disable.
- Remove the membership-type management apparatus: `MembershipTypesManager.tsx` /
  `MembershipTypeModal.tsx`, the `list/create/update/deactivate MembershipType` client wrappers, the
  `GET/POST/PUT/DELETE /membership-types` routes, the catalog domain CRUD (`_membership_catalog.py`)
  + repository methods, and their tests — the member-form/validation READ path is RE-POINTED at the
  field options, not deleted (Req 3).
- Design-phase trace enumerates any reader/builder left unreachable after the above for same-spec removal.

## Requirement 8 — governance definition-of-done

- Update steering `38-sam-module-field-config.md` where it documents the removed no-relax/forced rules.
- Update `sam/members/docs/data-model.md` + `config-guide.md`: the unified enum model (reference as a
  field feature with `allowed`), that `config#fields`/`config#scope` are SAM-authored (not
  MySQL-projected), and document the `application_*` field attributes (close the doc gap, Req 3.5).

## Correctness Properties

### Property 1: No orphaned reference
After the collapse+migration, every stored `membership.membership_type` resolves to a field option (proven: 6/6 values map; see proof).

**Validates: Requirements 3.6, 6.3**
### Property 2: Grandfather preserved
A member holding an `allowed:false` value (e.g. `erelid`) stays valid on read and on an update that does not change the value; it is absent from the picker.

**Validates: Requirements 3.2**
### Property 3: Admin not overruled
For any field other than `member_id`, no save is rejected on a cross-field binding the admin did not author (the removed no-relax/overlay invariants).

**Validates: Requirements 1.1, 1.2, 1.4**
### Property 4: Toggle round-trip
For `required`/`application_visible`/`application_required`, OFF→save→reload shows OFF (an explicit `false` is written, never a dropped `undefined`).

**Validates: Requirements 2.1, 2.2, 2.3**
### Property 5: Scope consistency
After a scope-field save, `config#scope` values equal the field's option values, and no `user_tenant_scope` grant is stranded (routine) or the save is blocked (orphaning).

**Validates: Requirements 4.2, 4.5, 4.6**
### Property 6: Label resolution
Every enum display AND filter resolves `label[locale]→en→nl→value`.

**Validates: Requirements 5.1, 5.2, 5.3**

## Error Handling

- Config write validation failures stay caller-safe (`ConfigWriteValidationError` → keyed, no
  internals), per steering 30's caller-safe contract; 03b does not take on the wider error-exposure
  sweep.
- The membership_type reference check raises a localized `MemberValidationError` (422) with
  `code` (`errors.membershipType.unknownReference` / `.retired`-equivalent) — re-pointed at the
  field options but the error contract is unchanged.
- An orphaning scope change raises `ScopeReconciliationBlocked` → a caller-safe "contact your
  System Administrator to realign grants" message (Req 4.6); the save is refused atomically.
- A failed Flask mirror write (SAM `config#scope` already written) surfaces a retry; SAM stays
  authoritative (Req 4.4).

## Testing strategy

- **Property/round-trip against REAL data** (steering 39): read→write→read of `config#fields`
  preserves field identity/group/flags and the membership_type options incl. `erelid` `allowed:false`.
- **Migration-safety scan** as an automated test over the real member tally (the proof above).
- **Behavioral tests** for each removal (admin CAN set application_required off on a platform field;
  a toggle OFF persists; a retired option is hidden from the picker but an existing member keeps it).
- **Scope reconciliation**: routine applies; an orphaning change blocks with the SysAdmin message.
- **Filter parity**: label-based filtering matches the resolved label, not the stored value.
- Change-with-tests contract (steering 30/34/39): every behavioral edit updates its paired test in
  the same change; no weakening assertions to go green.

## CI/CD and promotion

Per steering 43: CodeQL + GitGuardian per PR; SAM changes deploy on push per `deploy-sam-*`; the
frontend TEST surface is the local dev server (frontend deploys only from `main`). Promotion
`test → main` is BLOCKED until 03b lands AND the membership_type migration (+ any residual 03a
backfill) runs against PRODUCTION, integrity-scan-gated, identically to TEST (analysis D5).

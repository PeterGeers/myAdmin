# Design Document

## Overview

03b makes the tenant admin's field configuration authoritative by REMOVING the hardcoded bindings
that overrule it, UNIFYING selectable fields under one model (an enum field carries its own values
with a per-option `allowed` flag — "reference" is a feature on a field, not a separate catalog),
fixing the config toggles that silently drop an OFF write, making enum labels resolve uniformly in
filters, and deleting the dead plumbing left behind — for a NET DECREASE in code. It concerns the
SAM Members module (`sam/members/`) and its React frontend; the only cross-plane touch is the Flask
`members.scope_dimensions` mirror (Req 4).

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
- **Scope changes split by AXIS vs VALUE (owner rule).** Adding/removing a VALUE in the scope
  field (e.g. a region) auto-applies — one more/fewer selectable value, grants extend/shrink, the
  tenant admin owns the data consequence. Only a SCOPE-AXIS change (a different field, or a field
  combination, becomes the scope) triggers a "create a project with your SysAdmin" message. The
  value-level `reconcile_scope_change` orphan-block is NOT 03b's gate.

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
- **The scope-field save** (Req 4): the frontend makes two separate calls (SAM `config#scope`,
  then the Flask mirror) — no runtime cross-plane call. A VALUE add/remove auto-applies on both; a
  scope-AXIS change instead surfaces the SysAdmin-project message and does not auto-apply.

Data-flow deltas:
- Selectable-field read: options come from the FIELD's own resolved `options` (one assembly pass),
  no catalog injection.
- Member write: the membership_type reference check reads the field's options, not the catalog.
- Scope-field save (value change): derive `config#scope` from the field → write SAM → write Flask mirror; grants extend/shrink. Scope-AXIS change → SysAdmin-project message, no auto-apply.

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
displayed, valid on read; not offered for new records). A catalog entry with zero members
(`sponsor`, 0) is harmless — an offered option nobody has picked yet.
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

**Option integrity rules (well-formedness, enforced at the write seam in `config_write_service`):**
- An option whose `value` is still referenced by a member record MAY be set `allowed:false`
  (retired/grandfathered) but SHALL NOT be deleted or renamed through the normal author path. If an
  option IS removed anyway, existing records keep their stored value (read-stable), but a SAVE of
  such a record is rejected until its value is changed to an existing option (Req 3.2a).
- A required enum, or one OFF the application form, SHALL have ≥1 `allowed:true` option; the
  form-supplied default is the first `allowed:true` option by `order` (or an explicit default flag).
  A config that would zero the `allowed:true` set for such a field is rejected (Req 3.4a).
- `options` / `options.value` is the ONLY representation. The legacy `choices` key is FORBIDDEN on
  config fields and is removed from stored data (migration) and code (Req 7.4).

### Re-pointing the reference check (the orphan-safety seam)
`_membership_writes_validation._validate_membership_type_reference` today calls
`self._repo.get_membership_type(tenant_id, type_code)` and checks `entry.active`. It is re-pointed
to the field's resolved options:

- "exists" → `type_code` ∈ the `membership_type` field's `options[].value`;
- "assignable" → that option's `allowed is true`;
- unchanged: the check runs ONLY on create/update of a CHANGED value, so existing members with a
  now-retired value stay valid (grandfathering preserved by construction — design C8).
- the membership_type DEFAULT (when the field is off the form) comes from the field's options (first
  `allowed:true` by `order`), NOT the deleted catalog.

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

**Root-cause fix (Req 2.4), not per-toggle patching:** the diff in `fieldConfigChangeOps.ts` treats
`undefined` as BOTH "unchanged" and "off", so an OFF is dropped. Fix the diff to distinguish them —
diff against the LOADED state so a true→false transition always emits an explicit `false` — so NO
boolean attribute can silently drop an OFF. Add a test that round-trips EVERY boolean attribute
(ON→OFF→ON) in every modal (Req 2.5), preventing a fourth recurrence. Toggle call sites
(`ApplicationFieldAttributes.tsx` `onToggleRequired`, `ApplicationFieldModal.tsx` `toggleOnForm`)
send the explicit boolean. Paired tests: `fieldConfigChangeOps.test.ts`,
`ApplicationFieldAttributes.test.tsx`, `ApplicationFieldModal.test.tsx`.

## Requirement 4 — scope dimension DERIVED from the field; axis-change gates to SysAdmin

### Two-item save
Saving a scope-flagged field (`scope:{enabled:true}`) derives the `config#scope` dimension from the
field's own options and updates BOTH: (1) SAM `config#scope` (authoritative, the frontend-mirror
model, spec 02 — SAM first), (2) the Flask `members.scope_dimensions` mirror the grant validators
read. The Flask→SAM projection of `user_tenant_roles`/`user_tenant_scope` (`scopegrant#` rows) is
UNCHANGED and keeps working. A failed mirror surfaces a retry; SAM stays source of truth (Req 4.3/4.4).

### Value change vs axis change (the gate)
- **Value add/remove within the SAME scope field** (e.g. a region) → AUTO-APPLY on both planes: one
  more/fewer selectable value; a `user_tenant` grant extends or shrinks. The platform does NOT block
  and does NOT auto-reconcile the data of a removed value — that is the tenant admin's responsibility
  (there is no "proven" safe reconciliation to offer).
- **Scope-AXIS change** — a different field, or a combination of fields, becomes the scope → do NOT
  auto-apply; surface a "create a project with your System Administrator" message. This is a
  structural access-model change (the tenant-onboarding decision point).

Note: the existing `UserTenantScopeService.reconcile_scope_change` (value-level orphan classifier)
is NOT the 03b gate and is not wired in by this spec; the gate is the axis-vs-value distinction
above. `reconcile_scope_change` stays as-is (built, unwired) for a possible later use.

**No cross-plane call — the FRONTEND is the only coordinator (Req 4).** SAM and Flask never call
each other at runtime (steering 35/39). On a scope-field save the frontend makes TWO separate calls:
1. **SAM call** `PUT /members/config/scope` — derive the dimension from the field's options and
   write `config#scope` (authoritative) first.
2. **Flask call** — update the `members.scope_dimensions` mirror the grant validators read (the
   grant data `user_tenant_scope` lives on the Flask plane, reached without any cross-plane hop).

Flask's own projection of `user_tenant_roles` / `user_tenant_scope` back into SAM as `scopegrant#`
rows is a SEPARATE, unchanged pipeline. No SAM→Flask or Flask→SAM runtime call is added. The
axis-vs-value gate (above) decides auto-apply vs the SysAdmin-project message.

## Requirement 5 — uniform enum labels in filters

The record stores the KEY (`options.value`, e.g. `died`); table + modal already resolve the label
for the active language (nl `Overleden`, gb `Passed Away`). The FILTER/search paths in
`useMembersColumns.ts` (`searchedRows`, `enrichedRows` via `columnValue.coerceByType`) key off the
raw KEY, so a user must type `died`. Fix: for enum columns, match the filter/search against the
RESOLVED label text for the active language (an NL user types "Overleden"/part, a GB user "Passed
Away"/part). Build a per-column value→label map ONCE (not per row per keystroke). Where two options
share a label, the match includes both keys. Paired test: `applicationFilterParity.test.ts` + a
`useMembersColumns` test.

## Requirement 6 — the data migration (membership_type only)

A SAM-plane (DynamoDB) migration under `sam/members/migration/`, run EXPAND → DEPLOY → VERIFY →
CONTRACT so the data is converted before the re-pointed code runs (Req 6.4):

1. **EXPAND (`config#fields`)** — fold the tenant's CURRENT membership types into the
   `membership_type` field's `options` (`value`=type_code, `label`, `order`, `allowed`=`active`;
   `erelid`→`allowed:false`) and REMOVE the forbidden legacy `choices` key (incl. region) so
   `options` is the only representation. Additive/harmless to the old reader. LIST the resulting
   values for owner verification (Req 6.2).
2. **DEPLOY** the re-pointed reader. If deploy order cannot guarantee EXPAND-first in an
   environment, a LOCK prevents the re-pointed path until the fold is confirmed (Req 6.4).
3. **VERIFY** — the post-fold integrity scan (the proof) passes for ALL tenants (not just h-dcn):
   zero un-folded catalog rows, zero orphaned member references.
4. **CONTRACT** — retire the `membershiptype#<code>` rows in `sam-members`; the member-form/
   validation read path is already on the field options. (Removing the routes/UI/CRUD is a later
   change so rollback survives — Req 7.2.)

region / `config#scope` values are NOT migrated (already consistent; only the forbidden `choices`
residue is dropped); kept consistent by the Req 4 trigger. Properties: idempotent + re-runnable;
back up every affected row first (committed fixture under `backend/tests/fixtures/`); run TEST then
PROD identically, scan-gated (account `nonprofit-deploy` 506221081911, steering 23/41). Scope
value/axis changes are a save-time concern (Req 4), never a migration step.

## Requirement 7 — remove dead/not-asked-for code

- `config#views`: NOT touched (deferred feature, Req 7.1 / backlog `members-preferred-overview-columns.md`).
- Remove the no-relax + overlay-invariant plumbing and their tests (Req 1), not merely disable.
- Remove the membership-type management apparatus: `MembershipTypesManager.tsx` /
  `MembershipTypeModal.tsx`, the `list/create/update/deactivate MembershipType` client wrappers, the
  `GET/POST/PUT/DELETE /membership-types` routes, the catalog domain CRUD (`_membership_catalog.py`)
  + repository methods, and their tests — the member-form/validation READ path is RE-POINTED at the
  field options, not deleted (Req 3).
- DELETE the dead `reconcile_scope_change` / `ScopeChangeReconciliation` / `ScopeReconciliationBlocked`
  / `assert_appliable` + their tests (confirmed: no production caller; never the 03b gate).
- Remove the forbidden `choices` key from code paths that still read/write it (`options` is canonical).
- Design-phase trace enumerates any reader/builder left unreachable after the above for same-spec removal.
- RECORD the net lines-of-code + file-count delta in the definition of done (measurable simplification).

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
After a scope-field VALUE change, `config#scope` values equal the field's option values and the change auto-applies (grants extend/shrink); a scope-AXIS change does NOT auto-apply and surfaces the SysAdmin-project message.

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
- A scope-AXIS change is not auto-applied; the save returns a caller-safe "create a project with
  your System Administrator" message (Req 4.6). A value add/remove auto-applies (no error).
- A failed Flask mirror write (SAM `config#scope` already written) surfaces a retry; SAM stays
  authoritative (Req 4.4).

## Testing strategy

- **Property/round-trip against REAL data** (steering 39): read→write→read of `config#fields`
  preserves field identity/group/flags and the membership_type options incl. `erelid` `allowed:false`.
- **Migration-safety scan** as an automated test over the real member tally (the proof above).
- **Behavioral tests** for each removal (admin CAN set application_required off on a platform field;
  a toggle OFF persists; a retired option is hidden from the picker but an existing member keeps it).
- **Scope gate**: a value add/remove auto-applies on both planes; a scope-AXIS change surfaces the SysAdmin-project message and does not auto-apply.
- **Filter parity**: label-based filtering matches the resolved label, not the stored value.
- Change-with-tests contract (steering 30/34/39): every behavioral edit updates its paired test in
  the same change; no weakening assertions to go green.

## CI/CD and promotion

Per steering 43: CodeQL + GitGuardian per PR; SAM changes deploy on push per `deploy-sam-*`; the
frontend TEST surface is the local dev server (frontend deploys only from `main`). Promotion
`test → main` is BLOCKED until 03b lands AND the membership_type migration (+ any residual 03a
backfill) runs against PRODUCTION, integrity-scan-gated, identically to TEST (analysis D5).

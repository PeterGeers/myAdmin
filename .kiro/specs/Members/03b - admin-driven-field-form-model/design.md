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

Build units an executing agent implements, in dependency order. Each names the exact seam
(file/function, verified this phase), the concrete before→after, and the paired test(s) to write in
the SAME change (steering 30/34/39). Requirements are referenced by number, not restated. The
rollout order across units follows the EXPAND→DEPLOY→VERIFY→CONTRACT sequence in "Migration".

### BU-1 — Unified option model + option-integrity write-seam (Req 3, the spine)

The central change; everything else depends on the option shape.

- **Shape change** — `sam/members/domain/fixed_fields.py` `EnumOption`: add `allowed: bool = true`
  and `order: int | None = None` to the existing `{value, label{nl,en}, roles?}`. Backward
  compatible: an option without `allowed` reads as `true`. Serializers that emit options carry the
  two new keys.
- **Write-seam integrity (SAM authoritative)** — `sam/members/domain/config_write_service.py`, at
  the same seam as the kept invariants 1/2 (`_collect_application_attr_reasons` lives here), add two
  well-formedness checks on a `set_field`/`set_field_application` op:
  - a required enum, or one with `application_visible=false` (off the form → default supplied), must
    carry ≥1 option with `allowed:true`; a write that would zero that set → `ConfigWriteValidationError`
    (Req 3.4a).
  - an option `value` present in the CURRENT stored options may be set `allowed:false` or relabelled,
    but MUST NOT disappear/rename if a member references it. The write service cannot read member
    data (storage-agnostic), so this is enforced via the injected `usage_probe` already used by the
    delete-field guard (`config_fields_crud_service`): an in-use `value` missing from the new option
    set → reject with a caller-safe message naming the option (Req 3.2a, author path). A record that
    still ends up pointing at a removed option is caught on member save (BU-2).
- Paired tests: `sam/tests/test_config_write_service.py` — add zero-allowed-rejected, in-use-option-
  cannot-vanish, `allowed:false` permitted; property/round-trip over the real `config#fields` fixture
  (BU-7) asserting the `membership_type` options incl. `erelid`=`allowed:false` survive read→write→read.

### BU-2 — Reference check reads field options, not the catalog (Req 3)

- `sam/members/domain/_membership_writes_validation.py` `_validate_membership_type_reference`:
  replace `self._repo.get_membership_type(tenant_id, type_code)` + `entry.active` with a lookup
  against the RESOLVED `membership_type` field options:
  - unknown value (not in `options[].value`) → `MemberValidationError(MEMBERSHIP_TYPE_UNKNOWN_REFERENCE)`;
  - value present but `allowed:false` → `MEMBERSHIP_TYPE_RETIRED`;
  - the value-changed-only guard stays (`_membership_type_of` compare), so existing members with a
    retired/removed value stay valid on reads and on updates that don't touch the value (Req 3.2/3.2a).
- The DEFAULT when the field is off the form (`_membership_writes_application._default_membership_type`)
  returns the first `allowed:true` option by `order`, NOT a catalog read (Req 3.4a).
- **Transitional fallback (makes deploy order safe, Req 6):** while the catalog rows still exist
  (pre-CONTRACT), if a field carries NO inline options the reader MAY fall back to the catalog; the
  fallback is removed in CONTRACT. Alternatively a LOCK gates the re-pointed path until EXPAND is
  confirmed. Pick one in BU-6; both make EXPAND-before-DEPLOY non-fatal.
- Paired tests: `sam/tests/test_membership_writes*` — unknown/retired/grandfathered-existing cases
  against field options; default-from-options when off-form.

### BU-3 — Option assembly reads the field (Req 3)

- `sam/members/domain/_membership_writes_fieldconfig.py` `get_field_config` / `_assemble_field_options`:
  stop injecting `list_membership_types(active_only=True)` as the `membership_type` field's options.
  Options come from the field's own resolved `options` — the ONE assembly pass, no per-kind branch.
  `membership_type_options` standalone feed is dropped (frontend reads the field like any enum).
- Paired tests: `sam/tests/test_projection_sync.py` / resolved-field surface tests — assert the
  field carries its options and no catalog injection occurs.

### BU-4 — Remove the hardcoded bindings (Req 1)

- `config_write_service._collect_application_attr_reasons`: delete invariant 3 (the
  `platform_required and application_required is False` reject) and the `platform_required` plumbing
  fed from `fixed_fields.field_by_key`. KEEP invariant 1 (`application_choices` ⊆ options) and
  invariant 2 (known `format.checker`).
- `field_resolver._reject_invalid_overlay`: delete the `override.required is False and fixed.required`
  clause. Keep unknown-key, key-collision, dangling-functional_group, choiceless-non-scope-enum.
- Frontend `ApplicationFieldAttributes.tsx`: drop `requiredForced = isPlatformRequired(field) ||
  isMembershipType` so no field is force-on/disabled; keep "off the form → default supplied".
- Paired tests: delete/invert the relax assertions in `test_config_write_service.py` (~753/829),
  `test_field_resolver.py:209`, `test_status_retirement_preservation_props.py:397`; keep the
  "two axes don't alias" assertion in `test_field_models_application_attrs.py`.

### BU-5 — Toggle persistence at the ROOT (Req 2)

- Root cause: `frontend/.../fieldConfigChangeOps.ts` treats `undefined` as both "unchanged" and
  "off", so an OFF emits no op. Fix the diff to compare against the LOADED state so a true→false
  transition emits an explicit `false`; `applicationAttrs`/`definitionAttrs` no longer omit a
  deliberately-false attr. Backend `set_field_application` already SETs `false` correctly.
- Call sites `ApplicationFieldAttributes.onToggleRequired` / `ApplicationFieldModal.toggleOnForm`
  send the explicit boolean (not `? true : undefined`).
- Paired tests: a round-trip-every-boolean (ON→OFF→ON, every attr, every modal) test in
  `fieldConfigChangeOps.test.ts`; `ApplicationFieldAttributes.test.tsx`, `ApplicationFieldModal.test.tsx`.

### BU-6 — Scope derive-on-save; axis-vs-value gate; two-call orchestration (Req 4)

- Frontend scope-field save: the FRONTEND makes two separate calls — SAM `PUT /members/config/scope`
  (derive the dimension from the field's options, authoritative) THEN the Flask mirror call. No
  runtime cross-plane call.
- Gate: a VALUE add/remove auto-applies on both (one more/fewer selectable value). A SCOPE-AXIS change
  — the set of fields with `scope.enabled=true` changes (incl. turning scope off) — does NOT
  auto-apply; it surfaces the "create a project with your System Administrator" message, and the
  `scope.enabled` change is NOT persisted (atomic refusal).
- Robustness: on a detected failure of the second (Flask) call, show a proper caller-safe error AND
  a resync button on the scope screen (owner decision); SAM stays authoritative.
- `UserTenantScopeService.reconcile_scope_change` is NOT wired in (it is deleted in BU-8). The
  axis-vs-value distinction is the gate.
- Paired tests: axis-change-blocks-atomic; value-add/remove-auto-applies; two-call order + mirror-
  failure surfaces error+resync.

### BU-7 — Data migration (Req 6)

See "Migration" section for the EXPAND→DEPLOY→VERIFY→CONTRACT sequence, the all-tenant scan, the
TEST/PROD parity gate, and the forbidden-`choices` removal. Deliverables: `sam/members/migration/`
script (idempotent, backs up, lists loaded values) + the committed `backend/tests/fixtures/` real-row
fixture + the integrity-scan test (the proof).

### BU-8 — Remove dead/not-asked-for code (Req 7)

- membership-type management apparatus (after CONTRACT): `MembershipTypesManager.tsx` /
  `MembershipTypeModal.tsx`, the `list/create/update/deactivate MembershipType` client wrappers, the
  `GET/POST/PUT/DELETE /membership-types` routes, `_membership_catalog.py` + the repository catalog
  methods, and their tests.
- the removed-binding plumbing from BU-4 (not merely disabled).
- DELETE `reconcile_scope_change` / `ScopeChangeReconciliation` / `ScopeReconciliationBlocked` /
  `assert_appliable` in `backend/src/services/user_tenant_scope_service.py` + their tests in
  `test_user_tenant_scope_service.py` (confirmed: no production caller).
- remove forbidden `choices` read/write code paths (`options` canonical).
- do NOT touch `config#views` (deferred, Req 7.1).
- RECORD the net lines-of-code + file-count delta (DoD, Req 7.7/8.3).

### BU-9 — Filter/display by resolved label (Req 5)

- `frontend/.../useMembersColumns.ts` `searchedRows` + `enrichedRows` (`columnValue.coerceByType`):
  for enum columns match the filter/search against the active-language label (via
  `resolveEnumValueLabel`/`labelResolver`), not the stored key. The record keeps the key; table+modal
  already resolve the label. Build a per-column value→label map ONCE (not per row per keystroke);
  where two options share a label, the match includes both keys.
- Paired tests: `applicationFilterParity.test.ts` + a `useMembersColumns` test (nl `Overleden` and
  gb `Passed Away` both match the stored `died`).

### BU-10 — Governance: steering + docs (Req 8)

- Update steering `38-sam-module-field-config.md` where it documents the removed no-relax/forced rules.
- Update `sam/members/docs/data-model.md` + `config-guide.md`: the unified enum model (reference as a
  field feature with `allowed`); `config#fields`/`config#scope` are SAM-authored (not MySQL-projected);
  document the `application_*` field attributes (close the doc gap, Req 3.5); the forbidden-`choices`
  removal; the membership-type catalog retirement.

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

# SPEC: Scope-dimension authoring trigger — field-save must mirror scope to BOTH planes

**Raised 2026-10-29** while debugging the TEST Members config editor (spec 03a). A tenant edits
a scope-axis field's options (e.g. `region`) in the field editor, but the scope dimension on
NEITHER plane is updated — the trigger that keeps `config#scope` (SAM) and
`members.scope_dimensions` (Flask) in sync with the field was RETIRED and never replaced.
Access control can therefore silently desync from the authored vocabulary.

## Confirmed model (owner decision + the codebase's established design)
- A scope-backed field is a NORMAL ENUM. Its dropdown vocabulary is its own inline `options`,
  authored in the field editor — the ONLY authoring surface (the standalone `scope_dimensions`
  editor was retired, R2.2). `scope` on the field is JUST A BOOLEAN axis flag
  (`{enabled, required_for?}`).
- The scope dimension's values ARE the field's enum values. They are consumed by TWO access-control
  readers, NOT by the field dropdown:
  - **SAM `config#scope`** — read by `MembersProjectionReader.get_scope_config` →
    `resolve_scope_access` (which members a scoped caller may see).
  - **Flask `members.scope_dimensions`** (MySQL param) — read by `UserTenantScopeService` to
    validate/grant "user X may see region = Noord".
- **Frontend-mirror model (deliberate, spec 02 Task 3.7):** the two planes NEVER call each other at
  runtime. The FRONTEND writes each plane separately — SAM `config#scope` FIRST (authoritative,
  `PUT /members/config/scope`), THEN mirrors the SAME dimension set into Flask
  `members.scope_dimensions` (best-effort; a failed mirror surfaces a retry, SAM stays source of
  truth). `ProjectionSync` no longer emits `config#scope` (split-ownership end-state).
- **No plane-split breach:** verified `UserTenantScopeService` reads ONLY the MySQL
  `members.scope_dimensions` param — it never reads SAM `config#fields`/DynamoDB. The split holds.

## The gap (evidence, not speculation)
The frontend-mirror write EXISTS but is ORPHANED:
- `membersConfigService.saveMembersParameter('scope_dimensions', …)` performs the two-plane write
  (Step 1 `writeScopeConfig` → `PUT /members/config/scope`; Step 2 Flask
  `members.scope_dimensions` mirror, with `mirrorError`/retry semantics). This is wired to the
  RETIRED standalone `scope_dimensions` sub-editor (`MembersParamSubEditor`).
- `MembersFieldModal.tsx` (lines ~15-18): the field's scope toggle "REPLACES the retired standalone
  scope_dimensions editor (R2.2) … the scope VALUES ARE the field's enum values."
- `ParameterManagement.tsx`: `scope_dimensions` is HIDDEN from the raw editor because "a scope
  dimension is part of a field's definition (R2.2)."
- A UI grep finds NO component that mounts `MembersParamSubEditor` for `scope_dimensions`. So the
  two-plane mirror trigger is defined but **not wired to any live UI action.**
- The field-editor save path (`MembersConfigEditor`/`ApplicationFormBuilder` →
  `deriveFieldConfigChangeOps` → `saveFieldConfigChangeOps` → `PUT /members/config/fields`) writes
  `config#fields` ONLY. It does NOT derive the scope dimension nor write `config#scope` / the Flask
  mirror.

**Net:** the OLD trigger (standalone dimensions editor) was removed; the NEW trigger (field-save →
derive dimension → write both planes) was never added. A region add/remove/rename in the field
editor does not propagate to access control on either plane. The dimension only changes via the
orphaned path or manual seeding.

## Direction (needs a small design pass — do NOT blind-patch; access-control blast radius)
- **Make the field-editor save the SINGLE scope-authoring trigger.** On a successful
  `config#fields` save, for each saved field that is a scope AXIS (scope.enabled), derive the
  dimension set from that field's enum `options` and run the EXISTING two-plane mirror
  (`writeScopeConfig` → SAM `config#scope` authoritative, then Flask `members.scope_dimensions`
  mirror with the existing `mirrorError`/retry surfacing). Reuse the orphaned
  `saveMembersParameter('scope_dimensions')` logic rather than duplicating it.
- **Keep the planes split:** the frontend remains the only cross-plane bridge; no runtime
  plane-to-plane call; SAM stays authoritative; Flask copy is the best-effort mirror the grant
  validators read.
- **Sequencing / dimension sync semantics:** decide how the derived dimension handles a value
  RENAME/REMOVE that would strand an existing `user_tenant_scope` grant — the Flask
  `is_orphaning` reconciliation (`UserTenantScopeService`) already classifies this; the field-save
  path must surface the same block/contact-SysAdmin interim, not silently strand grants.
- **Retire the orphaned path** (or re-point it) once the field-save trigger lands, so there is
  exactly ONE authoring door (Property 8).

## Relationship to the SAM read path (03a context)
03a added an S5j-style read behavior where the SAM field-config read sources a choiceless scope
field's dropdown FROM `config#scope`. With the field-as-source-of-truth model, that read coupling
is redundant (the field owns its options). This item should reconcile the read path too: the field
dropdown reads the field's own `options`; `config#scope` is consumed only for access control.
(03a already removed the W2 write-guard that was blocking the field save — that unblock is DONE;
this item is the missing derive-and-mirror TRIGGER, which is separate and larger.)

## Out of scope / dependencies
- NOT part of spec 03a (enum round-trip / no-silent-fallbacks). 03a only removed the W2 guard that
  blocked saving a scope field; this is the separate, pre-existing authoring-trigger hole
  (scope-authoring migration R2.2 / R22 / R26).
- Touches ACCESS CONTROL on both planes — must preserve `resolve_scope_access` (SAM) and
  `UserTenantScopeService` grant validation (Flask) exactly; add explicit regression coverage that
  a field-editor region change propagates to both planes AND that grant-orphaning is surfaced, not
  silently applied.

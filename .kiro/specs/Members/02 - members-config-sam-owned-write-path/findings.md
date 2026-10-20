# Findings — config#fields SAM write-path cutover (TEST live-test, 2026-10-20)

Three latent defects surfaced only by a real end-to-end TEST login (authoring a new
`membership.status` value `died` and setting "Passed Away" on a member). Each was hidden
behind the one in front of it, and none was caught by the unit/round-trip suites because
those used the CANONICAL shapes, not the real frontend `field_overlay` payload. Regression
tests were added at each layer.

## 1. IAM — unsatisfiable `LeadingKeys` condition (500 AccessDenied on every write)
- Symptom: `PUT /members/config/fields` → 500. Log: `AccessDeniedException ... dynamodb:PutItem
  on test_governance_projection ... no identity-based policy allows the action`.
- Cause: task 1.8's `MembersWriteGovernanceProjectionConfig` grant pinned
  `dynamodb:LeadingKeys` to `${aws:PrincipalTag/tenant_id}`. The SHARED Members Lambda role
  carries no per-tenant principal tag, so the variable resolved empty and IAM denied all PutItem.
  (The codebase already documented this as a PLAN-ONLY pattern — `LEADING_KEYS_IAM_POLICY_PLAN`
  — undeployed because it needs per-request session tagging.)
- Fix: removed the condition. Tenant isolation on writes is APPLICATION-LAYER (route resolves
  `tenant_id` from the verified token; repository pins it as the partition key), matching the
  sibling read statement. Commit `089c94b01`. Test: `test_members_env_stack_contract.py`
  (`...write_is_a_single_scoped_putitem` now asserts no `Condition`).

## 2. WRITE — frontend `fixed_overrides` vs backend `overrides` (silent override wipe)
- Symptom: save returned 200 but `config#fields.overrides` persisted EMPTY — wiping
  membership.status / personal.* (groups showed "0 fields").
- Cause: the frontend `field_overlay` object (and the legacy Flask builder) author fixed-field
  overrides under the key `fixed_overrides`; `ConfigWriteService._validate_fields_body` read only
  the canonical `overrides`, so the alias-keyed map was dropped on write.
- Fix: the write service accepts `fixed_overrides` as an input alias → normalizes to canonical
  `overrides` (canonical wins if both present). Commit `64b9b44b5`. Tests in
  `test_config_write_service.py`.

## 3. READ — override enum values under `choices` vs `options` (`died` dropped on read)
- Symptom: after fix #2, `died` was stored on the row but still absent from the resolved
  field-config; the editor showed the fixed base's 6 status values.
- Cause: `MembersProjectionReader._build_override` built the override's enum values from
  `options` only; the frontend authors them under `choices` ([{value,label}]). With no `options`,
  the override carried no values and `FieldResolver._apply_override` fell back to the fixed
  field's base choices.
- Fix: `_build_override` sources options from `choices` when `options` is absent (options wins if
  both present), mirroring the variable-field path. Commit `a16aa4ff4`. Tests in
  `test_members_projection_reader.py`.

## Still open
- No "Saved" confirmation toast reported in the editor after a successful save — UX only, does
  not affect data. To investigate in the editor's `handleSave` toast path.

## Process note
These fixes were shipped as direct edits + CI/CD deploys to TEST (steering 43: PR → CodeQL +
GitGuardian green → merge to `test` → `deploy-sam-members.yml`) while the spec task-state tools
were unavailable. Task reconciliation pending: 1.8 effectively reopened+fixed; 1.12 (migration
script) and 1.13/1.14 (frontend repoint) committed but not yet formally marked complete.

# ADR 0009 — `config#fields` CRUD: Change-Op writes with server-owned placement (write by `update_item` path, read stays the Flat_View)

- Status: Accepted
- Date: 2026-10-26
- Relates to: ADR 0003 (myAdmin is a platform; base modules are SAM apps — this is the
  governance-projection config for the Members module), ADR 0008 (public intake reads the same
  `config#fields` Flat_View it fences). Introduced by the config-fields foolproof-CRUD spec.
  Spec: `.kiro/specs/Members/03 - config-fields-foolproof-crud/`
  (`requirements.md` R1/R2/R4/R6/R7/R9/R11, `design.md` §Overview/§Components/§Key decisions
  D1–D5). The **why** this spec exists: `.kiro/specs/Members/root-cause-analysis.md`.

## Context

The Members module stores its tenant field configuration in a single `config#fields` row as a
**nested delta over a code-defined base**: `fields` (tenant-added variable fields), `overrides`
(deltas on base/calculated fields keyed by a dotted path), and `functional_groups` (the group
catalog). Readers resolve base ⊕ overlay into a **Flat_View** the UI consumes.

The write path was a whole-row `put_item` FULL REPLACE fed by a best-effort, reader-dependent
service-side merge (`ConfigWriteService.put_config` → `_merge_fields_slices` → `put_config`).
The client sent a whole-ish object; the server merged it onto what it had just read and replaced
the entire record. `functional_groups` was replace-if-non-empty.

That shape caused a **partial-overlay-overwrites-full-record** defect, proven three times (see
`root-cause-analysis.md`): a partial payload — a configurator editing one group, a stale slice,
an empty-ish catalog — replaced the whole record, truncating the group catalog and dropping
base/other-field data. Correctness depended on the in-memory merge being perfect on every call,
and there was no version guard (last-writer-wins) and no end-to-end proof. "Safe only if the
merge is perfect" is not safe.

## Decision

**Make `config#fields` CRUD foolproof structurally: the client sends intent by identity
(Change-Ops); the server owns storage placement; each write is a single `update_item` addressing
one PATH; the read stays the Flat_View.** The whole-record replace leaves the client-reachable
interface entirely.

Concretely:

- **Change-Op writes, server-owned placement.** The client never supplies a storage key or a
  whole object. It names an identity and intent (`set_field`, `set_field_application`,
  `reset_field`, `delete_field`, `set_group`, `delete_group`). The server decides placement —
  variable field → `fields.<key>`, base/calculated field → `overrides.<dotted>`, group →
  `functional_groups.<gkey>` — from the fixed-field registry. **The store remains the nested
  delta**; the one translation (identity → storage path) lives server-side only.

- **Write via `update_item` PATH expressions, NOT a whole-record `put`.** The server resolves the
  record ONLY to (a) validate the op and (b) choose the storage path, then issues a single
  `update_item` with a scoped `SET`/`REMOVE` on that path (dotted keys bound via
  `ExpressionAttributeNames`). DynamoDB leaves every attribute the op did not name physically
  untouched. **The read stays the Flat_View** — `get_field_config` / `get_public_field_config`
  are unchanged; the raw overlay shape is internal only and never crosses the API boundary
  (steering 39).

- **Write merges onto the Resolved_Record; `Merge_Target = Resolved_Record`.** Because base
  definitions live in code, the resolved (base ⊕ overlay) record is the reference a Change-Op is
  validated and placed against — NOT the raw stored overlay and NOT a client-supplied whole
  object. The merge target is always the Resolved_Record; the write itself is a single path
  mutation, so the merge decides *placement*, never *replacement*.

- **R7 = A — application attributes stay inline, protected by a narrow Change-Op.** Ratified this
  run (task 0.1): the four application attributes (`application_visible`, `application_required`,
  `application_choices`, `format`) remain inline on `config#fields`, but ALL form-builder writes
  route through `set_field_application`, which can touch ONLY those four attributes of a named
  field and is structurally incapable of writing a field or group definition. Option **B** — a
  separate `config#application_form` record — is recorded as the **deferred** future end-state
  (full blast-radius isolation), to be chosen later only if form config grows independent of
  field definitions or shared-row contention justifies it.

## Rationale

- **Truncation becomes structurally impossible, not best-effort.** A Change-Op addresses one
  path; no op ever writes the whole catalog or the whole overlay, so a partial payload cannot
  reduce the group count or drop base/other-field data. This removes the residual "safe only if
  the in-memory merge is perfect" risk the old whole-row put carried — DynamoDB simply never
  writes what the op did not name.
- **Server-owned placement removes the client's ability to be wrong.** The client knew storage
  keys and reconstructed them; that reconstruction was the drift. Moving placement entirely
  server-side means the client cannot send a shape that truncates.
- **Resolved_Record as the merge target is the one non-obvious rule for base⊕overlay config.**
  Unlike a plain member record (where the stored row IS the full record), `config#fields` is a
  delta over code; validating and placing against the resolved record — then writing a single
  path — keeps the stored row a true minimal delta (D4) and is checkable.
- **R7 = A ships the stability guarantee now without a migration.** The narrow
  `set_field_application` surface satisfies R7.2 (the form builder cannot reach a definition
  attribute) through the op's shape, not a separate table — so A delivers the isolation A/B both
  require, with less work now, while B stays available as a clean future move.

## Consequences

- **The whole-record replace leaves the client-reachable interface.** The dangerous operation no
  longer exists to be misused: the write boundary exposes only Change-Ops. The repository
  `put_item` survives ONLY as an internal create/migration primitive (row-skeleton seed +
  LIST→MAP migration), guarded by the mechanical-enforcement layer (R11).
- **Truncation is structurally impossible.** Because every runtime write is a single path
  `update_item`, no partial payload can truncate the `functional_groups` catalog or any slice —
  the class of defect proven 3× in `root-cause-analysis.md` cannot recur by construction (backed
  by an E2E invariant harness against the real `h-dcn` row and a truncation tripwire, R9).
- **Phase 6 is skipped (R7 = A).** No `config#application_form` record and no inline-attr
  migration are built this run; application attributes stay inline behind `set_field_application`.
  Phase 6 is the documented, deferred path if B is later chosen.
- **A version-conditional guard replaces last-writer-wins.** Each Change-Op's `update_item`
  carries a `ConditionExpression` on `version` (with the legacy-no-version and no-row branches)
  and bumps `version` atomically, so a stale write fails cleanly (409, no partial change) instead
  of silently losing an update (D5).
- **Read-only consumers are untouched.** The Flat_View read contract is byte-for-byte unchanged,
  so Members Overview, the member Add/Edit/View modal, and Members Analytics are unaffected; only
  the configurator/form-builder write path changes.
- **Governance definition-of-done (steering 40).** This ADR and the steering 38/39 updates land
  in the same change set as the code; `root-cause-analysis.md` is linked as the why, and the
  live-verified fix retires the "do not edit groups on TEST" warning.

## Related

- **Why this exists:** `.kiro/specs/Members/root-cause-analysis.md` — the
  partial-overlay-overwrites-full-record defect, proven three times; this ADR records the
  structural fix (Change-Op + merge-onto-resolved + path `update_item`).
- **Spec:** `.kiro/specs/Members/03 - config-fields-foolproof-crud/` —
  `requirements.md` (R1/R2/R4/R6 structural correctness, R7 inline-vs-separate, R9 E2E invariant,
  R11 mechanical enforcement, R10 this ADR); `design.md` §Overview, §Components (C1–C6),
  §Key decisions D1 (Change-Op not whole-object), D2 (resolve to validate+place, then one path
  `update_item`), D3 (R7 = A), D4 (minimal-delta authoring), D5 (version-conditional).
- **Steering:** `.kiro/steering/39-*` — extended with the Change-Op / no-whole-record-replace
  rule and `Merge_Target = Resolved_Record`; `.kiro/steering/38-*` — references the new CRUD
  contract.
- **ADR 0008** — public unauthenticated intake reads the same `config#fields` Flat_View this ADR
  keeps stable; **ADR 0003** — the SAM module / governance-projection platform model this config
  belongs to.

# Requirements — Foolproof CRUD for `config#fields` (SAM plane)

- Status: **Draft** (requirements phase — review before design/tasks). **No code until approved.**
- Scope: a reliable, foolproof READ/WRITE (CRUD) service for the SAM-owned `config#fields` record,
  with the pattern + E2E test framework reusable for other SAM-plane CRUD. Grounded in the live code
  (verified 2026-10-26) and in `.kiro/specs/Members/root-cause-analysis.md`.
- Governing steering: **35** (SAM layering handler→service→repository→DynamoDB), **38** (field-config
  specifics), **39** (data-access: resolved-view contract, no raw shape crosses the repository
  boundary), **34** (testing / change-with-tests), **42** (local DynamoDB). Proposes **one new ADR**
  (data model for config#fields CRUD) — see R10.
- Non-negotiable (from the root cause): a writer must NEVER delete data it did not intend to touch.

## Introduction

`config#fields` is the tenant's Members schema (field definitions, functional groups, and — today —
the application-form attributes). It is written as a WHOLE DynamoDB item (`put_item` replace), while
the frontend holds only a PARTIAL delta (the overlay); base definitions live in code/resolver, not in
the stored row. This mismatch caused three verified production/TEST corruptions (root-cause-analysis
§"partial-overlay-overwrites-full-record"): tenant-field attributes stripped, base-group edits
silently no-op'd, and the `functional_groups` catalog truncated 6→2.

Note the current code ALREADY has partial mitigations — `ConfigWriteService._merge_fields_slices`
(read-modify-write merge) and a one-key wire contract (`get_raw_fields_overlay`). They reduce but do
not eliminate the bug, because: (a) the merge is best-effort and depends on a reader being wired;
(b) `functional_groups` is an ordered LIST merged by "replace-if-non-empty", so a save carrying a
*partial* non-empty list still truncates; (c) base definitions absent from the stored overlay are not
part of the merge target; (d) the client still assembles and sends a whole-ish object. This spec makes
the correctness STRUCTURAL and VERIFIED, not best-effort.

## Glossary

- **Resolved_Record**: the full field config the server computes = fixed/calculated base (in code)
  ⊕ tenant overlay (stored) ⊕ scope vocabulary. The flat, identity-keyed list consumers read.
- **Stored_Overlay**: the DynamoDB `config#fields` row = `{fields, overrides, functional_groups,
  slug, published_*}` — a tenant DELTA over base, NOT the full record.
- **Flat_View**: the resolved, bare-`key`-keyed field list (`get_field_config`/`get_public_field_config`
  output). The READ projection. Never saved back whole.
- **Change_Op**: an intent-level write keyed by domain identity (e.g. set field `motor_brand`
  `functional_group=motor`; set group `motor` order=40; set field on-form=true), NOT a whole-record
  replace.
- **Merge_Target**: the record a write merges a Change_Op onto. For `config#fields` it is the
  Resolved_Record (base ⊕ overlay), because base definitions are not in the Stored_Overlay.
- **Invariant_Test**: a read→write→read test over the REAL `h-dcn` row asserting a Change_Op changes
  only what it names and preserves everything else byte-for-byte.
- **Application_Attributes**: the four per-field form attributes (`application_visible`,
  `application_required`, `application_choices`, `format`) today stored inline on each field in
  `config#fields`.
- **Choice_Kinds**: the three ways a field carries selectable values — ENUM (inline `options`/
  `choices`), SCOPE (values from the `config#scope` dimension, single-source), REFERENCE
  (`membership_type` → live catalog).

## Requirements

### R1 — No write may delete data it did not name (the core guarantee)
**User story:** As a tenant admin, I want a save to change only what I edited, so a config save can
never silently drop fields, groups, labels, choices, or attributes.
#### Acceptance criteria
1. A write SHALL be applied as a Change_Op (or a set of them) onto the Merge_Target; it SHALL NOT
   replace the whole record from a client-supplied full object.
2. After ANY write, every field/group/attribute the write did NOT name SHALL be byte-identical to
   before (verified by the Invariant_Test, R9).
3. The `functional_groups` catalog SHALL NEVER shrink as a side effect of a write that did not
   explicitly delete a group — in particular a partial/empty groups payload SHALL NOT truncate it.
4. A base definition (base field attribute, base group) absent from the Stored_Overlay SHALL survive
   every write, because the Merge_Target is the Resolved_Record (base ⊕ overlay), not the overlay
   alone.
5. The whole-object `put_item` replace SHALL be removed from the client-reachable write path (it may
   remain only as an internal repository primitive the Change_Op layer builds its final item with).

### R2 — CRUD by domain identity, server owns placement (steering 39 / decision B)
**User story:** As a maintainer, I want the frontend to write by field/group identity and the server
to own physical storage placement, so the client can never reconstruct or corrupt the stored shape.
#### Acceptance criteria
1. The write API SHALL accept Change_Ops keyed by domain identity (bare field `key`, group `key`),
   NOT by physical storage keys (`fields` vs `overrides`, dotted `{group}.{key}`).
2. The server SHALL decide physical placement (whether a field change lands in `fields` or
   `overrides`, the dotted key form) — the client SHALL NOT supply it.
3. No raw Stored_Overlay shape (`field_overlay`, `overrides`, `fixed_overrides`, dotted keys) SHALL
   cross the repository boundary into a response or the frontend (steering 39). Reads serve the
   Flat_View.
4. The CRUD operations SHALL be: create/update/delete a FIELD (by key), create/update/delete a GROUP
   (by key), and set a field's attributes (type/label/order/required/visible/choices/scope/
   functional_group and — per R7 decision — application attributes).
5. A delete SHALL be explicit (an operation), never inferred from an omission.

### R3 — The read is the Flat_View; the store stays the nested delta
**User story:** As a maintainer, I want read-for-display and write-by-identity to use one flat
identity model, while storage stays the minimal nested delta.
#### Acceptance criteria
1. Reads (`get_field_config` staff, `get_public_field_config` applicant) SHALL return the Flat_View
   (resolved, bare-key, grouped by `functional_group`) — unchanged contract, confirmed correct.
2. The Flat_View SHALL NOT be accepted as a write payload to be stored back whole.
3. Storage SHALL remain the nested delta (`fields`/`overrides`/`functional_groups`), authoring only
   what the tenant changed over base.
4. There SHALL be exactly ONE place that maps Flat_View identity → storage placement (the server),
   so read and write cannot drift (root cause: two places disagreeing).

### R4 — Functional groups are first-class, base ⊕ overlay, never truncated
**User story:** As a tenant admin, I want to edit any functional group (including platform base
groups) and have the full catalog preserved.
#### Acceptance criteria
1. Editing a BASE group (present in resolved catalog, absent from overlay) SHALL materialize a
   tenant override of only the changed attributes, preserving all other groups (fixes occurrence 2).
2. A group write SHALL merge onto the full resolved catalog (base ⊕ overlay); it SHALL NOT replace
   the catalog with a partial list (fixes occurrence 3).
3. Deleting a group SHALL be explicit and SHALL be refused when the group still holds fields (the
   existing delete-when-empty guard), with a caller-safe reason.
4. A group's `key`, bilingual `label`, and `order` SHALL round-trip read→write→read without loss.

### R5 — ENUM, SCOPE, and REFERENCE fields handled correctly
**User story:** As a tenant admin, I want enum/scope/reference fields and their choices to read,
edit, and persist correctly, so choices never vanish or get mis-validated.
#### Acceptance criteria
1. **ENUM:** a field's inline `options` (rich `{value,label,roles?}`) and/or bare `choices` SHALL
   round-trip; a tenant-authored enum value (e.g. a `membership.status` value) SHALL NOT be dropped
   on read or write (the `_build_override` options⊕choices fallback is preserved/strengthened).
2. **SCOPE:** a scope-axis field's `scope` sub-object SHALL be preserved verbatim on write (so
   `config#scope` derivation stays correct), and a scope-dimension-backed choiceless enum SHALL
   source its choices from `config#scope` values (single source), not require duplicated inline
   choices.
3. **REFERENCE:** `membership_type` choices SHALL resolve from the live catalog; an
   `application_choices` subset SHALL validate against the catalog values (fail-loud on a dangling
   subset entry), not against static field choices.
4. `application_choices` (the subset) SHALL be validated subset ⊆ the field's resolved choices for
   enum fields, against the catalog for reference, and rejected on a choiceless field — one shared
   authority for the public read and the submit validator (no drift).
5. A write that changes a field's Choice_Kind data SHALL preserve the other attributes of that field
   (R1) — e.g. editing choices does not drop the field's label/group/application flags.

### R6 — Optimistic concurrency (no lost update)
**User story:** As a platform operator, I want concurrent edits not to silently clobber each other.
#### Acceptance criteria
1. A write SHALL carry the version it read; the repository SHALL reject a write whose base version is
   stale (conditional write on `VERSION_ATTR`), returning a caller-safe conflict the UI can surface.
2. A rejected stale write SHALL make NO change (atomic), so a losing writer never partially corrupts.
3. The Version_Stamp SHALL remain a monotonic ISO-8601 marker (existing model), now also used as the
   concurrency guard condition.

### R7 — Application-form config: decide inline vs. separate record (data-model decision)
**User story:** As the owner, I want the application-form attributes to not endanger the core field
schema, per the stability concern raised in the root cause.
#### Acceptance criteria
1. The design SHALL make an explicit, ADR-backed decision (R10) between:
   - **(A) keep inline** on `config#fields` but fully protected by R1–R3 (a form save is a Change_Op
     that can only touch application attributes, never field/group definitions), OR
   - **(B) separate record** (`config#application_form` or similar) holding the per-field form
     selections, composed with field defs at read; the application-form builder can ONLY write that
     record and is structurally incapable of touching `config#fields`.
2. WHICHEVER is chosen, a buggy or crafted application-form write SHALL be structurally incapable of
   deleting or altering a field/group DEFINITION (the stability guarantee the owner required).
3. The chosen option SHALL preserve the existing public read contract (`get_public_field_config`) and
   the submit validator behavior (subset gates, membership_type reference), or migrate them coherently.
4. IF (B), a migration SHALL lift existing inline application attributes off `config#fields` into the
   new record per tenant, with a read→write→read verification, PROD as the known-good source.

### R8 — Layering, isolation, fail-fast (carry the SAM-plane standards)
#### Acceptance criteria
1. The CRUD service SHALL be a domain service (no boto3); the repository SHALL own DynamoDB; the edge
   SHALL shape HTTP only (steering 35).
2. `tenant_id` SHALL come from the verified token, never the body; the write SHALL require a non-empty
   partition key; no `.scan()` across tenants (steering 23/35).
3. The table SHALL resolve fail-fast from `GOVERNANCE_PROJECTION_TABLE` (no default).
4. The write surface SHALL stay closed to the SAM-owned config ids (no other row type writable).

### R9 — E2E / invariant test framework (the proof, reusable)
**User story:** As a maintainer, I want a test framework that PROVES the CRUD is foolproof against
real data, reusable for other SAM-plane records.
#### Acceptance criteria
1. There SHALL be an E2E round-trip harness exercising the REAL repository + REAL reader against
   **local DynamoDB** (`amazon/dynamodb-local`, steering 42) seeded with the REAL `h-dcn`
   `config#fields` row (not a hand-built fixture — root-cause lesson "trust runs, not inference").
2. The Invariant_Test SHALL assert: for each Change_Op kind (set field attr, add/edit/delete field,
   add/edit/delete group, set choices, set application attr), read→apply→read changes ONLY the named
   target and leaves every other byte identical — including the full `functional_groups` catalog and
   all base definitions.
3. There SHALL be a truncation tripwire test: a partial/empty payload MUST NOT reduce the group count
   or field count (the exact occurrence-3 scenario), asserted red-then-green.
4. The harness SHALL be structured so another SAM record (e.g. `config#scope`, `config#mail`, a member
   record) can reuse the same read→write→read invariant pattern with minimal new code.
5. Unit tests (in-memory fakes, existing pattern) SHALL remain for fast feedback; the E2E layer is the
   authoritative proof. Both run in `sam/tests` via `sam/pytest.ini`.

### R10 — Steering + ADR are updated/created as part of the work
#### Acceptance criteria
1. A NEW ADR under `docs/decisions/` SHALL record the decision: "config#fields CRUD is Change-Op /
   server-owned-placement; the store is a nested delta; reads are the Flat_View; writes merge onto the
   Resolved_Record; application-form config is (A inline-protected / B separate) per R7." Append-only,
   never rewrite an existing ADR (repo convention).
2. Steering **39** SHALL be extended (or confirmed sufficient) to state the Change-Op / no-whole-record-
   replace rule and the Merge_Target=Resolved_Record rule, so future SAM CRUD inherits it.
3. Steering **38** (field-config) SHALL be updated to reference the new CRUD contract.
4. The root-cause-analysis SHALL be linked from the ADR as the "why".

### R11 — The solution is MECHANICALLY enforced on future development (not advisory)
**User story:** As a platform operator, I want future code to be structurally unable to reintroduce
the partial-overlay-overwrites-full-record defect, so the fix survives pace and personnel changes —
because the root cause proved advisory measures (docs/steering/"remember to…") do NOT survive.
Enforcement hierarchy, strongest first (each a required deliverable, not optional):
#### Acceptance criteria
1. **Make the bad operation not exist (structural, primary):** the write API SHALL expose ONLY
   Change-Ops; there SHALL be NO client-reachable method that replaces a whole `config#fields` record
   or accepts a whole `functional_groups`/overlay object. A developer cannot misuse an operation that
   is not in the interface.
2. **CI/pre-commit guard that FAILS the build:** a committed guard (modeled on the Flask
   `mysql.connector` DB-access guard, steering 31/39) SHALL fail on (a) a raw
   `put_item`/`update_item`/`delete_item` on the governance table outside the sanctioned Change-Op
   write repository, and (b) a raw-shape key (`field_overlay`/`overrides`/`fixed_overrides`/dotted
   `{group}.{key}`) in an API response. Wired into `.githooks/pre-commit` AND CI (steering 43),
   report-only → blocking once the baseline is clean.
3. **The invariant E2E test SHALL be in the REQUIRED gate**, not merely present — run in the gate
   that actually blocks a merge (the nightly full-suite at minimum, per steering 43; per-PR if the
   local-DynamoDB container is feasible). A test that exists but is not gated is how the original
   regression reached `main` (Frontend CI was `disabled_manually`).
4. **Boundary/import test:** extend `sam/tests/test_handler_repository_boundary.py` to assert no
   handler/domain module imports the raw whole-record replace primitive — only the Change-Op service
   does.
5. **Runtime tripwire (defense in depth):** the write repository SHALL refuse to persist a
   `config#fields` whose resolved group/field count is LOWER than the base unless an explicit delete
   Change-Op was issued — so even a logic bug cannot silently truncate reaching DynamoDB.
6. **Review-layer detector:** `.kiro/specs/code-quality-maintenance/prompts/prompt-code-quality.md`
   SHALL detect the foolproof-CRUD violations (raw write bypass, whole-record replace, frontend
   whole-overlay write) as HIGH-priority correctness findings. (Added already; this requirement keeps
   it in scope and consistent with the CI guard's patterns.)
7. The measures SHALL be CONSISTENT across layers (authoring=steering 39; review=the quality prompt;
   commit=the CI guard; runtime=the tripwire) — same patterns, so a violation is caught at the
   earliest layer and, failing that, every later one.

## Out of scope (v1)
- Member-record CRUD rework (the same pattern applies, but this spec proves it on `config#fields`
  first; a follow-up can generalize).
- The jabaki hosting migration / publish path (spec 12 territory).
- Any change to the resolved READ contract shape beyond what R7's chosen option requires.

### Impact on Members Overview, the member Add/Edit/View modal, and Members Analytics
These three surfaces are READ-ONLY consumers of `config#fields` — they render the Flat_View
(`get_field_config`), they never write it. This spec deliberately leaves them UNCHANGED, and that is
a hard requirement, not an omission:
- **They keep working exactly as today.** This spec changes only the WRITE path (Change-Ops via
  `update_item`) and, per R3.1, the resolved READ contract (`get_field_config` /
  `get_public_field_config`) stays byte-for-byte the same. Overview's columns/filters/sort, the
  member modal's field rendering, and Analytics' pivot/grouping all consume that unchanged Flat_View,
  so no code in those surfaces changes and no behavior shifts.
- **They get MORE reliable, not less.** Overview/analytics never corrupted anything precisely because
  they only read the flattened resolved list (root-cause-analysis). The corruptions came from the
  authoring surfaces' writes; fixing those writes removes the risk that a bad config save degrades the
  very schema overview/analytics/the modal read. In other words: this spec protects the data these
  three surfaces depend on, without touching the surfaces themselves.
- **The ONE change they will see is a bug fix, not a regression:** once a write can no longer truncate
  the `functional_groups` catalog or strip field definitions (R1/R4), the groups/fields these surfaces
  render stay complete — the empty-groups / missing-fields symptoms that were caused by corrupted
  `config#fields` data simply stop occurring.
- **Explicitly out of scope for THESE surfaces:** no change to Overview's table/filter framework, the
  member modal's form rendering, or the Analytics pivot engine. If any of them is later found to
  ALSO write config (none does today — verified: they are read-only consumers), that would be separate
  follow-up work, not part of v1.
- The member-RECORD modal's own write path (creating/editing a member's *data*, not the config schema)
  is a different record (`member#…`) and is covered by the separate "Member-record CRUD rework"
  out-of-scope item above — the same Change-Op pattern will apply there in a follow-up.

## Traceability to the root cause
- "partial-overlay-overwrites-full-record" (3 occurrences) → R1, R3, R4.2.
- base-group edit no-op / blank form → R4.1.
- read/write source mismatch → R2, R3.4.
- "trust runs, not inference" (bad fixture hid the bug) → R9.1 (real h-dcn row, local DynamoDB).
- owner's stability concern (form save must not endanger schema) → R7.2.

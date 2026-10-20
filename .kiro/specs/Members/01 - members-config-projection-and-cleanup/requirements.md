# Requirements Document

> **Origin.** Day of manual TEST verification after the Members parameter-model migration
> (`.kiro/specs/Members/application-app/issues_found.md`). Two of the recorded findings are
> bundled here because both are loose ends of that migration and both must land before
> `test` → `main`. A THIRD finding (the `membership_type` reference catalog has no TenantAdmin
> management UI) is deliberately SPLIT into its own spec. A FOURTH (the `died` operational
> unblock for h-dcn) is handled ad-hoc, not here — once R1 ships, a tenant-authored status
> value propagates on the next sync anyway.

## Introduction

Two deliverables, one spec:

1. **Harden the MySQL → DynamoDB config projection write** so a freshly-built, valid row is
   never skipped by a version check that disagrees with the content it guards. This is the
   root cause of the "tenant-added enum value never appears" bug (the `died`/"Overleden"
   case): the projected `config#fields` row wedged with stale content stamped at the current
   version, and the strictly-greater version gate then refused every correcting write.

2. **Retire `view_contexts`** — the final, deferred Phase-2 step (d). The param is read by
   nothing in live code; only an authoring-key declaration and its test still name it. Remove
   the stored rows, the `config#views` projection residue, and the lingering frontend key
   reference.

Both are Flask/MySQL-plane + projection changes. R1 touches the projection writer (shared by
every `config#*` row), so it is correctness-sensitive and gets property-based tests. No SAM
domain behaviour change is required by either deliverable (the SAM read side already consumes
whatever the projection serves; `view_contexts` serialization was already removed in step (c)).

---

## Glossary

- **Projection / `config#*` row** — the DynamoDB read-model copy of a tenant's Members config, built from MySQL `parameters` by `ProjectionSync` and read by the SAM module.
- **Content-gate** — a write decision based on whether the freshly-built row's semantic content differs from the stored row's, replacing the version-strictly-greater gate.
- **Wedge** — a stored projection row holding stale content stamped at the current source version, which the strictly-greater version gate can never overwrite.
- **`view_contexts`** — a retired Members config param (named column layouts); only `page_size` survived, re-homed to `default_page_size`.

## Requirements

### R1 — The config projection write reflects current source content, not a stale version proxy

**User story:** As a tenant admin, when I change a Members config value (add an enum option,
relabel a field), I want the change to appear in the app, so that authoring actually takes
effect — every time, not only when a timestamp happens to advance.

### Background (grounded in current code)

`ProjectionSync._conditional_put` (`backend/src/services/projection_sync.py`) writes a
`config#*` row only when `_supersedes(incoming.version, stored.version)` is true — i.e. the
incoming version is STRICTLY greater than the stored one. `version` is derived per-param from
the source param's `updated_at` (`_config_row_version` + `ParameterService.get_param_revision`
— the earlier "version-bump-trap" fix). The CONTENT is built by `build_config_fields_row`
reading the overlay via `ParameterService.get_param` (which has an in-memory value cache).

The defect: version and content can DISAGREE. A run can stamp the row with a fresh revision
while serializing stale cached content; the stored version then equals the source revision, so
`_supersedes` is false forever and the correct content can never overwrite the stale row (it
wedges). Confirmed on `test`: MySQL `members.field_overlay` carried all 7 status values incl.
`died`; the projected `config#fields` carried 6 and a version identical to the source
`updated_at`; a fresh (uncached) rebuild produced all 7 with the SAME version.

### Acceptance criteria

1. WHEN the projection builds a `config#*` row for a tenant THEN the row's content SHALL be
   built from the CURRENT source value (not a stale cached value) — the build path SHALL read
   the source parameters without reusing a cache that a concurrent/previous write may have left
   stale.
2. WHEN a freshly-built row's CONTENT differs from the stored row's content THEN the projection
   SHALL write the fresh row, EVEN IF the incoming version is not strictly greater than the
   stored version (the write decision SHALL be driven by content, not by version alone).
3. WHEN a freshly-built row's content is byte-for-byte equal to the stored row's content THEN
   the projection SHALL skip the write (idempotence preserved — no churn on an unchanged
   re-sync).
4. BEFORE writing a `config#*` row THE projection SHALL validate the row for completeness and
   syntax (the existing `validate_items` batch gate, extended as needed), and SHALL NOT write a
   row that fails validation — a malformed build is a loud failure, never a silent stale-leave.
5. THE `version`/`updated_at` attribute SHALL be RETAINED on the row for recording ("when was
   this last projected") and for ordering genuinely concurrent writes; it SHALL NO LONGER be
   the sole gate for WHETHER to write. (Keep the DynamoDB datastore-level conditional guard only
   as a concurrency backstop, not as the change-detector.)
6. THE write decision SHALL be deterministic and idempotent: re-running the sync against an
   unchanged source re-produces the same stored content and performs no write (criterion 3).
7. THE fix SHALL be GENERAL — it applies to every `config#*` row the sync writes
   (`config#fields`, `config#scope`, `config#mail`, …), not a status/`config#fields` special
   case; a content change to ANY of them propagates.
8. A tenant-authored `membership.status` value that is not a platform value (e.g. `died`) SHALL,
   after a sync, be present in the projected `config#fields` `overrides["membership.status"]`
   vocabulary exactly as `gender` values already are — i.e. the concrete regression that
   triggered this spec is covered by a test.

---

### R2 — `view_contexts` is retired (Phase-2 step d), nothing left reads or declares it

**User story:** As a maintainer, I want the dead `view_contexts` surface fully removed, so that
no one inspecting `parameters` or the config code is misled by a retired artifact again.

### Background (grounded in current code)

Phase 2 retired `view_contexts` in ordered steps (a)→(c): `page_size` was re-homed to the
`default_page_size` scalar on `config#fields`; the SPA stopped reading `view_contexts`; the SAM
server stopped serializing it (SAM tests assert `"view_contexts" not in config`). Step (d) —
delete the param + `config#views` projection + any domain/builder modules + the frontend key
reference — was DEFERRED and never run. Verified: no live code READS `view_contexts`; the only
residual references are the stored param rows, the frontend `MEMBERS_PARAM_KEYS` /
`MEMBERS_PARAM_TO_CONFIG_ID` declaration (+ its test), and comments/specs.

### Acceptance criteria

1. THE stored `members.view_contexts` parameter rows SHALL be removed for every tenant (a
   reversible, auditable migration under `backend/src/migrations/`, dry-run by default), AND any
   `config#views` projection residue SHALL be removed from the projection table.
2. THE frontend SHALL remove `view_contexts` from `MEMBERS_PARAM_KEYS` and
   `MEMBERS_PARAM_TO_CONFIG_ID` (`frontend/src/services/membersConfigService.ts`), and any test
   that exercises it (`membersConfigService.test.ts`) SHALL be updated to the retired reality
   (not weakened — re-pointed to a surviving key).
3. IF any Flask-plane `build_config_views_row` / view-context domain/validation modules remain,
   THEY SHALL be deleted, and their paired tests updated/removed (change-with-tests contract).
4. AFTER retirement, a full search for `view_contexts` across live source (excluding build
   artifacts and spec/steering docs) SHALL find NO reader and NO authoring-key declaration — only
   historical mentions in docs.
5. THE retirement SHALL NOT change any surviving behaviour: `default_page_size` continues to
   drive pagination, and the per-user Session Columns feature (the live column chooser) is
   untouched (it never read `view_contexts`).
6. THE `config#views` row SHALL NOT be re-created by a subsequent sync (the builder that would
   produce it is removed, so the sync no longer emits it).

---

## Out of scope

- The `membership_type` reference catalog management UI — its OWN spec.
- The `died` operational unblock for h-dcn — ad-hoc (R1 makes it propagate on the next sync).
- Any SAM domain behaviour change — the SAM read side already consumes the projection as served.
- The `member_number` `format.checker None` save error and the "where are application-form
  attributes authored" question — separate `issues_found.md` items, not this spec.

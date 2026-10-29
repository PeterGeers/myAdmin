# SPEC: Members user-preferred overview columns (revive the retired config#views feature)

**Raised 2026-10-29** (surfaced while scoping spec 03b). A user used to be able to define which
columns the Members overview opens with — their preferred column set. The feature was REMOVED
during an earlier spec over an unresolved error, leaving only dead `config#views` residue. It is
a VALID requirement, DEFERRED — not junk to delete. 03b deliberately does NOT touch the residue
so reviving it stays possible.

## What it is
- A per-user (not per-tenant) preference: the ordered set of overview columns a user wants to see.
- Historically stored under the `config#views` sort key (the `view_contexts` shape). The only
  value that survived the removal (`page_size`) was re-homed to `default_page_size` on
  `config#fields`.

## Current state (evidence)
- `config#views` is retired residue: no builder emits it, nothing reads it; on the SAM plane it is
  structurally unwritable (writable config set is `{scope, fields, mail}`). A cleanup routine
  `delete_config_views_residue` (Flask `projection_sync.py`) exists only to DELETE leftovers and
  has no production caller.
- There is a related, LIVE per-user column preference on the SAM plane: `colprefs#<sub>` rows in
  `sam-members` (a user's chosen overview columns). A revival should decide whether the preferred-
  SETS feature builds on `colprefs#` or reintroduces a `views`-style store — do NOT assume.

## Why deferred / what to decide on revival
- Find and understand the ORIGINAL unresolved error that caused the removal before rebuilding
  (do not repeat it). Likely in the earlier Members config spec history.
- Decide storage: extend the existing `colprefs#<sub>` per-user model vs. a new preferred-sets
  row — per steering 35 (SAM owns its data) / 39 (Change-Op, resolved-view).
- Per-user, not per-tenant: this is a USER preference (keyed by Cognito `sub`), not tenant config.

## Relation to other specs
- 03b (`Members/03b - admin-driven-field-form-model`) leaves `config#views` untouched and records
  this as Out of Scope / deferred.

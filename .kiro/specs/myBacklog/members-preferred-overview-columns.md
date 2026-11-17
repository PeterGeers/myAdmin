# SPEC: Members user-preferred overview columns — RESOLVED (delivered as Session Columns)

**Raised 2026-10-29** (surfaced while scoping spec 03b) · **Closed 2026-11-17** — owner decision:
ONE ordered per-user column set (no named / no multiple sets).

**Provenance:** owner correction recorded in `Members/03b` Req 7.1 (commit `60bb9efc3`), backlog entry
`625304f04`. **Original framing** ("revive the retired `config#views` feature") conflated TWO
different column preferences. Only one was retired; the requirement this item is about is the other
one — and it is LIVE. See sections 2-3.

## 1. Decision (2026-11-17)

- The requirement is **ONE ordered per-user column set** — not named, not multiple sets.
- That is **already delivered and live**: the *Session Columns* (per-user column chooser) feature.
  **No rebuild, no revival of `config#views`.** This backlog item is **CLOSED as satisfied**.
- **Per-user page size is NOT part of this requirement** — it was retired separately
  (Req 25.9; section 4). Nothing to revive there either.
- **Named / multiple per-user column sets are NOT required.** If that ever changes, mirror the live
  preferred-list pattern (`preflist#<sub>` + refs) — never a TENANT view-object (steering 38
  rule 3).

## 2. The live contract (what "members user-preferred overview columns" is today)

| Aspect | Contract | Evidence |
| --- | --- | --- |
| Owner / key | a USER — the verified Cognito `sub` (user is not a member) | `sam/members/domain/column_preferences.py` (module docstring) |
| Store | exactly one `colprefs#<sub>` row per user in the tenant partition of the members table | `sam/members/repository/_table_schema.py` (`RECORD_TYPE_COLUMN_PREFS`, `column_prefs_sk`); `_table_items.py` (`build_column_prefs_item`) |
| Shape | ordered list of field-config KEYS (`columns`) + `updated_at` — references only, never copies of field/member data; `member_number` implied + always-first and not stored | `sam/members/domain/column_preferences.py`; `frontend/src/types/members.ts` (`MemberColumnPreferences`) |
| API | `GET /members/column-preferences` (members:read) + `PUT` (members:export OR members:write); the owning `sub` comes from the edge principal, never from the body or a path param | `sam/members/handler/routes_table.py` (column-preferences `RouteSpec` pair); `_dispatch_analytics.py` |
| Service | GET returns an EMPTY list when unset (empty is valid, never 404); PUT is a FULL REPLACE that drops blank / duplicate / non-candidate keys and stamps `updated_at` | `sam/members/domain/_membership_analytics.py` (`get_/save_column_preferences`, `_clean_column_keys`, `_candidate_column_keys`) |
| UI | toolbar `ColumnChooser` modal; every change is applied live AND persisted immediately | `frontend/src/components/members/ColumnChooser.tsx`; `frontend/src/components/members/overview/useMembersData.ts` |
| First-time default | no saved preferences → the admin/compact default columns plus the fixed `member_number` | `frontend/src/pages/__tests__/MembersPage.sessionColumns.test.tsx` ("empty-default") |
| Robustness | a stored key that no longer resolves is SKIPPED on read (no column, no error) | `useMembersData.ts` seed effect; `_serialize_column_preferences` |

**Source-spec note.** The spec that authored this feature
(`.kiro/specs/Members/member-field-search/session-columns/{requirements,design,tasks}.md`) was deleted
as a side effect of the 2026-10-13 spec reorganisation (`b4363cb9f`) while the feature shipped; two
component docstrings still cite that path. It has since been RESTORED (F3, 2026-11-17) from
`git show b4363cb9f^:<path>`, so those references resolve again. Its R1-R7 are exactly this
requirement, and its Out-of-scope section already ruled out sharing / promoting column sets - the
"revival" question was answered there too.

## 3. What was actually RETIRED (do NOT revive this)

`members.view_contexts` (parameter) → `config#views` (projection): a TENANT-authored list of contexts,
each carrying `key`, a bilingual label, `permission_roles`, `columns`, `filterable_columns`,
`default_sort` and `page_size`.

- Retired in the Members config Phase 2 — commits `467ae94fd` / `ccb00705c` (PR #121, 2026-10-17); MySQL
  rows removed by `backend/src/migrations/retire_members_view_contexts.py`; the projection step landed
  in TEST via `138279d9d`.
- Rationale: the generic filter + flexible-columns table, the per-user preferences and the capability
  gates subsume it; "only pagination was the residual" (`Parameter redesign/analysis.md` section 2.3).
- Governing rule: steering **38** rule 3 — "no standalone view/analytics param objects —
  columns/sort/filter/pagination are runtime behaviours of the generic table + per-user prefs, not
  stored config".
- Residue today: `config#views` is structurally unwritable by the SAM-owned writer
  (`_WRITABLE_CONFIG_IDS = {scope, fields, mail}`) and nothing reads it. `config#*` rows are
  UPSERT-ONLY, so leftovers persist until deleted explicitly;
  `ProjectionSync.delete_config_views_residue` (`backend/src/services/projection_sync.py`) plus
  `CONFIG_ID_VIEWS` (`backend/src/services/projection_schema.py`) exist for exactly that, are covered
  by unit tests (`backend/tests/unit/test_projection_sync.py`), and have NO production caller (F1).

## 4. The "original unresolved error" — recorded finding (discharges "do not repeat it")

Nothing in the repo records the error itself (the phrase appears only in this item and in
`03b/requirements.md` Req 7.1). The evidence pins it to this code path, in one of two forms:

1. **`OverlayError` → HTTP 500 when the field config is resolved WITHOUT the tenant scope
   vocabulary.** The live code documents it verbatim: `_candidate_column_keys` — "The resolve MUST
   pass the tenant's scope vocabulary ... Resolving bare here was a 500 on save for any such tenant"
   (`sam/members/domain/_membership_analytics.py`). The same class was root-caused in
   `.../s5j-members-config-authoring-path/tasks.md` (production `OverlayError` because `app.py` built
   the service without `scope_config_provider`, so the vocabulary was empty) and in
   `.kiro/specs/myBacklog/sam-data-migration-framework.md`.
2. **The opaque "unresolved" column block UX defect** the owner reported — rows marked
   "unresolved" that expand into a wall of field names (`Parameter redesign/analysis.md` section 2.3:
   "Whatever survives of column config must not reproduce this opaque 'unresolved' state").

CI fallout from the same change (stale `view_contexts` tests plus a ruff-format failure) is recorded in
`code-quality-maintenance/full-test-suite-fixes/full-test-suite-fixes-2026-10-17/tasks.md`.

**Invariant to preserve (why it cannot recur):** any code that derives candidate columns must resolve
the field config WITH `scope_vocab`, and must never surface an opaque "unresolved" state. The live
per-user path honours both — which is why this item CLOSES instead of reviving.

## 5. Verification (re-check in one minute)

```
cd sam && python -m pytest tests/test_column_preferences_entity.py tests/test_members_repository.py -q
# 96 passed — verified 2026-11-17 (exit 0)
cd sam && python -m pytest tests/test_cleanup_config_views_residue_script.py -q
# 9 passed — the residue entry point (F1), verified 2026-11-17 (exit 0)
cd frontend && npx vitest run src/pages/__tests__/MembersPage.sessionColumns.test.tsx \
    src/__tests__/MembersPage.test.tsx \
    src/services/members/membersColumnPreferencesApi.test.ts \
    src/services/membersApiService.test.ts
# 104 passed / 4 files — verified 2026-11-17 (exit 0)
```

Residue cleanup (F1) — DRY RUN by default, `--apply` to delete:
`python scripts/cleanup_config_views_residue.py --tenants <administration> [--apply]`

> Note: `npx tsc -b` is RED on this branch (54 PRE-EXISTING errors, all in
> `frontend/src/components/TenantAdmin/MembersConfig/*` + `PublicApplicationForm.axe.test.tsx`);
> none are in the files this item touched.

## 6. Follow-ups — status (2026-11-17)

- **F1 — DONE (keep + wire, not delete).** `ProjectionSync.delete_config_views_residue` keeps its
  implementation and its 5 unit tests, and now has a REAL, documented entry point:
  `scripts/cleanup_config_views_residue.py` (dry run by default; `--apply` deletes;
  `--tenants a,b` or `--all`), covered by `sam/tests/test_cleanup_config_views_residue_script.py`
  (9 tests: parsing, dry-run default, tenant scoping, idempotence, CLI guard). Chosen over deletion
  because `config#*` rows are UPSERT-ONLY — this routine is the ONLY thing that can remove a stray
  `config#views` row, so deleting it would make any existing residue permanent.
- **F2 — DONE (frontend) / deliberately retained (SAM read-side).** Deleted the dead Members
  pagination-precedence module `frontend/src/pages/membersPagination.ts` plus its two tests
  (`membersPagination.test.ts`, `membersPagination.property.test.ts`), removed the retired
  `page_size` from `MemberColumnPreferences` and its mapper (`membersColumnPreferencesApi.ts`),
  and removed `default_page_size` from `FieldConfigResponse` (`frontend/src/types/members.ts`),
  updating the four affected test files. RETAINED on purpose: the SAM-side `default_page_size`
  still served on `GET /members/field-config` (`DefaultPageSizeProvider` / `get_default_page_size`
  / `_membership_writes_fieldconfig.py`) — it is a served response key with its own tests
  (`sam/tests/test_pagination_precedence_props.py`, `test_members_projection_reader.py`,
  `test_config_write_service.py`), no client reads it, and dropping it is an API change: a
  separate SAM-plane task if wanted.
- **F3 — DONE (restore, not repoint).** `.kiro/specs/Members/member-field-search/` restored from
  `git show b4363cb9f^` (5 files: `design-options.md` + `session-columns/{requirements,design,tasks}.md`
  + `tasks.meta.json`), so the `@see` references in `ColumnChooser.tsx` / `FieldChecklist.tsx` resolve
  again and this item has its parent spec; a dated "Restored 2026-11-17" note heads
  `requirements.md`.

## 7. Relation to other specs

- **03b (`Members/03b - admin-driven-field-form-model`)** still leaves `config#views` untouched
  (Req 7.1) — that non-touch rule stands, but its "DEFERRED / revivable" rationale is SUPERSEDED by
  this closure; dated notes point here from 03b requirements / design / tasks.
- **Steering:** `38-sam-module-field-config` rule 3 (no stored view objects),
  `35-sam-module-architecture-sam` (the module owns its data),
  `39-backend-data-access-sam-dynamodb` (Change-Op / resolved view),
  `36-config-and-parameters` (retirement mechanics).
- **Precedent if named sets are ever wanted:** the analytics preferred-list (`preflist#<sub>` +
  `refs: ["preset:...", "set:..."]`, `GET/PUT /members/analytics-sets/preferred`) — a per-user list of
  saved REFERENCES, no new storage pattern.

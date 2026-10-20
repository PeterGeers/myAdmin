# Implementation Plan

## Overview

Phase 2 — Delete the Redundant Surface of the Members config redesign (`impact-analysis.md` §9
steps 6+7). Two deliverables: **(1) retire `view_contexts`** (order-critical, SPA-gated) and
**(2) clean dead code** (the legacy `overrides` dual-accept + `SAMPLE_SCOPE_CONFIG`). Grounded in
`design.md`; every task names the steering it conforms to.

**Prerequisites (given, not re-opened):** Phase 0 (reliability fixes) and Phase 1 (catalog backbone)
are DONE. Config home is settled = Option B.

Planes: SAM = `sam/members/...` + `sam/tests/` (pytest via `sam/pytest.ini`); Flask = `backend/src` +
`backend/tests` (pytest via `backend/pytest.ini`); SPA = `frontend/src` (Vitest + RTL). Do NOT import
`sam.*` into `backend/src` (steering 30/31 cross-plane boundary). Tests follow `34-backend-testing.md`
/ `33-frontend-testing.md`; the **Change-With-Tests Contract** (`30`/`32`) applies to every behavioural
edit — the paired test moves in the SAME task. Shell per `41-shell-environment.md` (POSIX `cd` inline,
`<<<DONE marker=$?>>>`, `backend/.venv`).

**The ordering is the whole risk.** The task waves ENCODE the (a)→(b)→(c)→(d) sequence: Deliverable-1
steps may not be reordered — a server-removal task (c/d) can never be scheduled before the SPA-strip
task (b). Deliverable 2 is independent and runs in parallel.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "5.1", "6.1"] },
    { "id": 1, "tasks": ["1.3", "2.1", "2.2", "5.2", "6.2"] },
    { "id": 2, "tasks": ["2.3", "3.1", "3.2", "5.3"] },
    { "id": 3, "tasks": ["3.3", "4.1", "4.2"] },
    { "id": 4, "tasks": ["4.3", "4.4", "4.5"] },
    { "id": 5, "tasks": ["7.1", "7.2", "7.3"] }
  ]
}
```

Critical path (Deliverable 1, order-critical): `1.* (a) → 2.1/2.2 (a served) → 3.* (b, SPA strip) →
4.1/4.2 (c, server stops serializing) → 4.3/4.4 (d, drop param+projection+domain)`. Deliverable 2
(`5.*` migration-then-dual-accept-delete, `6.*` SAMPLE_SCOPE_CONFIG move) runs independently and
converges at verification (`7.*`). The waves guarantee (b) completes before (c), and (c) before (d).

## Tasks

### Deliverable 1, step (a): re-home `page_size` (R2) — `36`, `38`, `30`, `32`

---

- [x] 1. Pagination default home (step a)
  - [x] 1.1 Add the tenant-level `default_page_size` default (Flask plane) — a `members`-namespace scalar param `members.default_page_size` (positive int, optional) in `backend/src/services/parameter_schema.py`, with a validator that rejects non-positive values. Conforms to `38` rule 3 (a default, not a view object) + `30`. _(R2.1, R2.6)_
  - [x] 1.2 Thread `default_page_size` through the projection + reader so it is available to the field-config response — carry it on the existing config#fields-adjacent payload (NOT a new view row); read it in SAM. Keep `view_contexts` fully in place for now (additive). _(R2.1, R1.2)_
  - [x] 1.3 Serve `default_page_size` on `GET /members/field-config` ALONGSIDE the still-present `view_contexts` array (`_membership_writes.get_field_config`). Additive — an old SPA ignores it. _(R1.2, R2.1)_

---

- [x] 2. Pagination resolution + its tests (step a) — SAM read side + SPA read side
  - [x] 2.1 Implement the pagination precedence `userPreference ?? default_page_size ?? platformDefault` on the SPA read path (`MembersPage.tsx`), reading the user preference from the existing per-user column/table preference mechanism (`column_preferences`) and the tenant default from the field-config response. _(R2.2, R2.3, R2.4)_
  - [x] 2.2 Property test — pagination precedence (SAM + SPA). **Property 1: Pagination precedence is total and deterministic.** Generate the (userPref present/absent × tenantDefault present/absent) matrix with random positive ints; assert resolved == first present and always a positive int. **Validates: Requirements 2.2, 2.3, 2.4, 9.4** _(R9.4)_
  - [x] 2.3 Example test — step-(a) additivity: the field-config response at step (a) carries BOTH `view_contexts` and `default_page_size`; serializing does not raise. _(R1.2, R1.6)_

---

### Deliverable 1, step (b): strip SPA consumption (R3) — `32`, `33`

> **Gate:** wave 2 — runs only after step (a) (waves 0–1) is complete, so `page_size` has its new home
> before the SPA stops reading `view_contexts`.

---

- [x] 3. Strip SPA view-context consumption (step b)
  - [x] 3.1 Remove the view-context machinery from `frontend/src/pages/MembersPage.tsx`: `normalizeViewContexts`, `isContextAvailable`, the `viewContexts`/`availableContexts`/`selectedContext`/`selectedContextKey` state + memos, the context `<Select>` dropdown (`aria-label={t('viewContext.label')}`), and the `ViewContext` import. Render the table over `FieldConfig.visible_fields()` directly (preserving the empty-`columns` default-context behaviour). Keep `useFilterableTable`/`FilterableHeader`. _(R3.1, R3.2, R3.6)_
  - [x] 3.2 Remove the view-context sub-editor from `frontend/src/components/TenantAdmin/MembersConfig/` (the `MembersConfigEditor.tsx` sub-section + any dedicated context editor component/import); keep every other sub-editor. Remove `ViewContext` + `view_contexts` from `frontend/src/types/members.ts` (add the optional `default_page_size`); remove the dead `viewContext.*` i18n keys. _(R3.3, R3.4, R3.5)_
  - [x] 3.3 Change-With-Tests (SPA): **delete** `MembersPage.viewContexts.test.tsx`; **rewrite** the MembersConfig editor tests (`MembersConfig/__tests__/MembersConfigEditor.test.tsx`) to drop the view-context sub-editor cases and keep the rest; add/extend a Members-table test asserting it renders over `visible_fields()` with no dropdown and paginates by the precedence rule. _(R9.1, R3.2, R2.2)_

---

### Deliverable 1, steps (c)+(d): remove server serialization, then drop param/projection/domain (R4, R5) — `35`, `34`, `36`, `30`

> **Gate:** wave 3 (step c) runs only after wave 2 (step b) — the server stops serializing only after
> the SPA has stopped reading. Wave 4 (step d) runs only after wave 3 (step c).

---

- [x] 4. Remove server serialization (c), then drop param + projection + domain (d)
  - [x] 4.1 **Step (c)** — in `sam/members/domain/_membership_writes.py` `get_field_config`: delete the `view_contexts` array entry (~L997) + the `_serialize_view_context` method (~L1178) + the `_view_contexts_provider` dependency and its handler wiring. Keep `default_page_size` in the response. _(R4.1, R4.2, R4.3, R4.4)_
  - [x] 4.2 Change-With-Tests + **Property 4**: update `sam/tests/test_members_resolved_field_surface.py` to assert `view_contexts` is ABSENT and `default_page_size` is PRESENT; the served field SET is unchanged. **Property 4: field-config carries no view-context surface after step (c).** **Validates: Requirements 4.1, 4.4, 1.6** _(R9.2, R4.1)_
  - [x] 4.3 **Step (d) Flask** — delete the `view_contexts` param (`parameter_schema.py`), `validate_view_contexts` + its dispatch branch (`members_config_validation.py`), `build_config_views_row`/`_map_view_context`/helper constants (`_projection_config_builders.py`), the `config#views` assembly + import + re-export (`projection_sync.py`), and the `config#views` entry (`projection_schema.py`). _(R5.1, R5.2, R5.3, R5.4)_
  - [x] 4.4 **Step (d) SAM** — delete `get_view_contexts`/`_build_view_context`/`_CONFIG_ID_VIEWS` + the `ViewContext` import (`projection_config_reader.py`); **delete** `sam/members/domain/view_contexts.py` and `sam/members/domain/seed_view_contexts.py` in full; remove any view-contexts provider wiring in `handler/app.py`. _(R5.5, R5.6)_
  - [x] 4.5 Change-With-Tests (step d): **delete** `sam/tests/test_seed_view_contexts.py`; **rewrite** `sam/tests/test_config_roundtrip_props.py` to drop the views roundtrip (keep fields/scope/overrides); update `backend/tests/.../test_projection_sync.py` (no `config#views` item), `test_parameter_schema.py` (no `view_contexts` param), and members_config_validation tests (no view validator). _(R9.1, R9.2, R5.7)_

---

### Deliverable 2: clean dead code (R6, R7) — `31`, `30`, `35`, `34`, `36`

> Independent of Deliverable 1 — runs in parallel. Within D2, the migration (5.1/5.2) MUST precede the
> dual-accept deletion (5.3), encoded as its wave dependency.

---

- [x] 5. Legacy `overrides` dual-accept — migrate then delete (step 7 / R6)
  - [x] 5.1 Write the one-time migration under `backend/src/migrations/` (a `.py` migration like `migrate_tenant_config_to_parameters.py`): rewrite every stored `members.field_overlay` row carrying a legacy top-level `overrides` key into `fixed_overrides` (merge; `fixed_overrides` wins on collision). `administration`-scoped, parameterized queries, `--dry-run` default, idempotent, rewrites the KEY NAME only (never member records or override values). Applied via `DatabaseMigration.run_all_migrations()` (not auto-applied). Conforms to `31`. _(R6.1, R6.2, R6.3, R6.4, R6.5, R8.2)_
  - [x] 5.2 Property + example test for the migration (`backend/tests/`). **Property 2: migration preserves data and is idempotent.** Generate overlays with/without legacy `overrides` and overlapping keys; assert the merge invariant (`fixed_overrides` wins on collision), other keys + member records untouched, and `f(f(x)) == f(x)`; plus an example test that dry-run makes no change and the applied run performs the rename. **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 8.1, 8.3** _(R9.5)_
  - [x] 5.3 Delete the dual-accept branches (ONLY after 5.1 lands): in `backend/src/services/_projection_config_builders.py` and `sam/members/repository/projection_config_reader.py`, read ONLY `fixed_overrides`. Do NOT rename the internal `TenantOverlay.overrides` field or the `config#fields.overrides` attribute. Change-With-Tests: update `sam/tests/test_field_resolver.py` override cases to the `fixed_overrides` key. _(R6.6, R6.7, R6.8, R9.3)_

---

- [x] 6. Move `SAMPLE_SCOPE_CONFIG` into tests (step 7 / R7) — `35`, `34`
  - [x] 6.1 Create a shared fixtures module `sam/tests/_scope_fixtures.py` defining `SAMPLE_SCOPE_CONFIG` (the synthetic region North/South/East/West dimension), and switch the five consumers (`test_scope_normalization_verify.py`, `test_scope_access.py`, `test_scope_dimensions.py`, `conftest.py`, `members_parity_harness.py`) to import from it. _(R7.2, R7.3)_
  - [x] 6.2 Delete `SAMPLE_SCOPE_CONFIG` from `sam/members/domain/scope_dimensions.py` (+ its `__all__` entry + the docstring references framing it as a domain sample). Keep the scope MODEL (`ScopeDimension`/`ScopeConfig`/`WILDCARD`/providers) unchanged. The `.aws-sam/build` mirror is a build artifact — do not hand-edit. _(R7.1, R7.4, R7.5)_

---

### Verification + ship (R8, R9, R10) — `34`, `33`, `43`, `41`

---

- [ ] 7. Verification, member-data invariance, ship
  - [x] 7.1 Run the touched suites. SAM: `cd sam && pytest tests/test_members_resolved_field_surface.py tests/test_field_resolver.py tests/test_config_roundtrip_props.py tests/test_scope_dimensions.py tests/test_scope_access.py tests/test_scope_normalization_verify.py -q`. Flask (via `backend/.venv`): the projection_sync + parameter_schema + members_config_validation + migration tests. SPA: the Members-table + MembersConfig-editor Vitest suites. All green. _(R9.*)_
  - [x] 7.2 Property 3 + close-out greps. **Property 3: member data is invariant across every Phase 2 step** — snapshot arbitrary member records before/after each step; assert byte-for-byte equality. Then the close-out greps (zero product-code matches for `view_contexts`/`ViewContext`/`get_view_contexts`/`build_config_views_row`/`config#views`/`_serialize_view_context`; zero legacy-`overrides` dual-accept branches; zero `SAMPLE_SCOPE_CONFIG` in `sam/members/domain`). **Validates: Requirements 8.1, 8.3** _(R5.7, R8.1, R8.3)_
  - [x] 7.3 CI/CD + ship (per `43-cicd-deploys.md`). Feature branch (e.g. `spec/members-config-phase2-delete-surface`), never push to `test`/`main` directly. Run the paired tests locally first. PR into `test`; clear CodeQL + GitGuardian. **Ship step (b) frontend first** (`deploy-frontend.yml`) and confirm it is live on every client BEFORE merging the SAM step (c)/(d) removal (`deploy-sam-members.yml`). Preview the prod changeset (`--no-execute-changeset`) — confirm NO unexpected `Replacement: True` (no infra/table change). Promote `test → main` by MERGE commit. Run the one-time migration against TEST then PRODUCTION via `backend/scripts/railway-db.sh` (`#database` skill) — not auto-applied. Deploys touch the DATA account only; no Cognito/identity change. Tick `impact-analysis.md` §9 Phase 2 steps 6+7 done with a pointer to this spec folder. _(R10.1, R10.2, R10.3, R10.4, R10.5)_

---

## Notes

### Requirements coverage

| Requirement | Tasks |
|---|---|
| R1 (ordering contract) | wave structure, 1.3, 2.3, 4.1, 4.3/4.4 |
| R2 (re-home `page_size`) | 1.1, 1.2, 1.3, 2.1, 2.2, 2.3 |
| R3 (strip SPA consumption) | 3.1, 3.2, 3.3 |
| R4 (remove server serialization) | 4.1, 4.2 |
| R5 (drop param + projection + domain) | 4.3, 4.4, 4.5, 7.2 |
| R6 (migrate rows + drop dual-accept) | 5.1, 5.2, 5.3 |
| R7 (move `SAMPLE_SCOPE_CONFIG`) | 6.1, 6.2 |
| R8 (non-destructive to member data) | 5.1, 7.2 |
| R9 (Change-With-Tests blast radius) | 2.2, 3.3, 4.2, 4.5, 5.2, 5.3, 7.1 |
| R10 (ship safely) | 7.3 |

### Correctness property → task

| Property | Task |
|---|---|
| P1 — pagination precedence total/deterministic | 2.2 |
| P2 — migration preserves data + idempotent | 5.2 |
| P3 — member data invariant across every step | 7.2 |
| P4 — field-config no view-context surface after (c) | 4.2 |

### Ordering guarantees (the hard part — `impact-analysis.md` §6.1)

- Step (a) (waves 0–1) adds `default_page_size` additively → nothing breaks for old clients.
- Step (b) (wave 2) strips SPA reads → runs ONLY after (a).
- Step (c) (wave 3) stops serving the array → runs ONLY after (b); the (b)→(c) gap is the safe
  backward-compat window.
- Step (d) (wave 4) deletes param/projection/domain → runs ONLY after (c).
- Deliverable 2: the migration (5.1) precedes the dual-accept deletion (5.3).

### Deferred to later phases (recorded, not done here)

- Collapsing fixed/overlay → one list + provenance badge; "only `member_id` is fixed" — Phase 3 (step 8).
- Folding scope-binding into a field attribute; retiring the standalone `scope_dimensions` editor — Phase 3 (step 9).
- Folding analytics into field attributes / calculated fields — Phase 3 (step 10).
- Rebuilding the group → field → attribute authoring UI — Phase 3 (step 11).
- Renaming the internal `TenantOverlay.overrides` / `config#fields.overrides` names (R6.8).

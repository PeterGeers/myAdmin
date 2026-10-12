# Full Test Suite Fixes — 2026-10-10

## Summary

Full Test Suite run (GitHub Actions run #60 / id `38056285364`) on branch `test` @ `c4e30fab`, 2026-10-10 13:35 UTC, triggered by `workflow_dispatch`. **CI conclusion: ❌ failure.** Analysis is CI-artifact-based only (no local scans), from the downloaded `backend-test-reports`, `sam-test-reports`, `frontend-test-reports`, and `backend-lint-reports` artifacts.

| Category                     | Count                                       | Δ vs 2026-10-05                                |
| ---------------------------- | ------------------------------------------- | ---------------------------------------------- |
| Backend test failures        | **1** (of 7068; 7053 passed, 14 skip)       | 🟢 **improving** 2 → 1                           |
| SAM module-plane tests       | ✅ pass (0 fail)                             | ✅ held green                                    |
| Frontend test failures       | **3** (of 3602; 3587 passed, 12 skip, 2 files) | 🔴 **regressed** 0 → 3                           |
| Ruff lint errors (backend)   | **3** (G201 ×2, RUF100 ×1)                  | 🔴 **regressed** 0 → 3                           |
| Ruff format violations (be)  | **2 files**                                 | 🔴 **regressed** 0 → 2                           |
| Vulture (dead code)          | ✅ Pass                                      | — stable green                                  |

**CI job result**: **Backend Full Test Suite ❌ (1 failed)** · SAM Module-Plane ✅ · **Frontend ❌ (3 failed)** · **Backend Lint & Static Analysis ❌ (3 ruff + 2 format)**. Three jobs are red this cycle, but every failure is **small and tightly scoped**. All of them trace back to **one feature landing on this branch** — a Members "mail" config namespace (`mail_local_part` / `mail_domain` / `mail_certified`) and a Members analytics/sender-identity surface — whose tests, schema expectations, and lint were not all updated together.

> ⚠️ **Common root cause across planes**: the new Members **mail** config keys drive the backend test failure (schema expected-set drift) *and* the two reformatting targets (`members_config_validation.py`, `members_analytics_audit.py`), while the new sender-identity routes drive the ruff-lint `G201` errors. The frontend 3 failures are a separate Members-UI cluster (tenant-switch role re-resolution + session-column filter composition). This is a classic "feature merged on a branch without running the full suite" cycle — the opposite of the 10-05 arc, which was converging on green.

> ⚠️ **Ruff version**: CI ran **ruff 0.16.5** (pinned, matches local). The 3 lint + 2 format findings are real new debt on this branch, not a version-mismatch artifact.

---

## Test Results — Backend (7053 passed, 14 skipped, **1 failed**, 0 collection errors — 938.38s ≈ 15m38s)

🔴 **Red — one runtime failure.** 7068 tests collected; the single failure runs (not a collection error).

### F1 — Members parameter schema expected-set drift (1 failure)

| Test | Error |
| ---- | ----- |
| `test_parameter_admin_routes.py::TestParameterSchemaEndpointMembersGating::test_schema_members_tenant_permits_members_namespace` | `AssertionError: set(params.keys()) == {...}` — extra keys `mail_domain`, `mail_local_part`, `mail_certified` |

**Root cause:** the parameter-schema endpoint now returns three **new Members mail config keys** — `mail_certified`, `mail_domain`, `mail_local_part` — in addition to `field_overlay`, `mail_enabled`, `scope_dimensions`, `view_contexts`. The test's hard-coded expected set (`test_parameter_admin_routes.py:567`) was **not updated** when the mail namespace was added (same feature that introduced `members_config_validation.py`'s `mail_local_part` / `mail_certified` validators — the two files flagged by ruff-format below). The production side is correct; the **test's expected set is stale**. Fix is in the **test**: add the three new keys to the expected set (confirm against the schema definition that these are intentional). This is **feature-vs-test drift**, not a production regression.

```
Full diff (left = actual, right = expected):
    {
        'field_overlay',
  +     'mail_certified',
  +     'mail_domain',
        'mail_enabled',
  +     'mail_local_part',
        'scope_dimensions',
        'view_contexts',
    }
```

---

## Test Results — SAM module-plane (✅ PASS)

✅ **Green.** 0 failures, 0 errors (≈100% dots in the summary tail). Collection healthy; held green across the arc.

---

## Test Results — Frontend (3587 passed, 12 skipped, **3 failed** across **2 files** — 258 files, 182.28s)

🔴 **Red — 3 failures in 2 files**, both in the **Members UI** area. A regression from 10-05 (0 failures).

### F2 — tenant-switch role re-resolution (1 failure)

| Test | Error |
| ---- | ----- |
| `src/context/__tests__/tenantSwitchRoles.test.tsx > Bug condition: stale roles after in-app tenant switch (h-dcn) > re-resolves roles on switch to h-dcn: hides Tenant Administration, shows Members Overview, refetches with X-Tenant: h-dcn` | `TestingLibraryElementError: Unable to find an accessible element with the role "button" and name /Members Overview/` |

**Root cause:** after an in-app tenant switch to `h-dcn`, the test expects a "Members Overview" button to appear (and "Tenant Administration" to hide). The accessible button with name `/Members Overview/` is **not rendered** — either the role re-resolution did not surface the Members Overview entry, the label/role changed, or the nav gating for `h-dcn` changed. Needs confirmation against the current tenant-switch role-resolution + nav-gating code (`TenantContext` / role resolver + the Members Overview nav item).

### F3 / F4 — MembersPage session-column filter composition (2 failures)

| Test | Error |
| ---- | ----- |
| `src/pages/__tests__/MembersPage.sessionColumns.test.tsx > … AND-composition of a chosen-column filter (R2.4) > composes a chosen-column filter with the global all-fields search` | `expect(element).not.toBeInTheDocument()` — expected the row to be filtered out, but `found <td>Marie</td>` |
| `src/pages/__tests__/MembersPage.sessionColumns.test.tsx > … context switch retains a saved column list (OQ-1, R3.3) > keeps the user chosen columns after switching the view context` | `expect(element).not.toBeInTheDocument()` — expected a row absent, but `found <td>` |

**Root cause:** both failures are the same shape — a row expected to be **filtered out** of the Members table is still present. The combination of a chosen-column filter AND the global all-fields search (`members-global-search` value `"regulier"`) is not narrowing the rows as the test expects (stats strip shows `total 3 / filtered 2`, but a row that should be excluded — `Marie` — is still in the DOM). Likely a change in how the chosen-column filter composes (AND) with the global search, or in how the saved column list / view-context switch re-applies filters. Both live in the Members session-column filter path — treat as **one cluster** (shared filter-composition cause).

**Grouped by root cause:** 3 FE failures → **2 clusters** — (a) tenant-switch role re-resolution not surfacing "Members Overview" (F2), and (b) Members session-column filter composition not excluding rows (F3/F4, shared cause).

---

## Lint & Static Analysis (Backend Lint job — ❌ FAIL)

| Check | Result |
|-------|--------|
| Ruff Lint | ❌ Fail — **3 errors** (`G201` ×2, `RUF100` ×1), ruff 0.16.5 |
| Ruff Format | ❌ Fail — **2 files** would be reformatted |
| Vulture | ✅ Pass (no dead code) |

### Ruff Lint — 3 errors (CI-blocking)

| Rule | Count | Auto-fixable | File:line |
| ---- | ----- | ------------ | --------- |
| `G201` | 2 | ❌ manual | `src/routes/members_sender_identity_routes.py:90:16`, `:156:16` — `logging .exception(...)` should be used instead of `.error(..., exc_info=True)` |
| `RUF100` | 1 | ✅ `--fix` | `src/routes/members_analytics_audit.py:107:29` — unused `# noqa` directive (non-enabled: `BLE001`) |

Ruff reports **1 of 3 fixable** with `--fix` (the `RUF100`). The two `G201` are a trivial manual rewrite (`logger.error(msg, exc_info=True)` → `logger.exception(msg)` inside the `except` block). All three sit in the **new Members sender-identity / analytics-audit routes** — same feature family as the backend test and format findings.

### Ruff Format — 2 files

| File | Site |
| ---- | ---- |
| `src/routes/members_analytics_audit.py:85` | collapse a split f-string into one line |
| `src/services/members_config_validation.py:411, 433` | re-wrap `MembersConfigError({...})` dict/call expressions |

Both are **auto-fixable** via `ruff format src/`. Both are files from the **new Members mail-config feature** — the same change that introduced the `mail_local_part` keys driving F1.

### Totals by category

- **CI-blocking** this cycle: **1 backend test failure + 3 frontend test failures + 3 ruff-lint errors + 2 ruff-format files** (three red jobs).
- **Auto-fixable vs manual (lint)**: `RUF100` (1) + both format files (2) are mechanical `--fix` / `ruff format`; the two `G201` are a small manual edit.
- **Test fixes**: F1 is a one-line test expected-set update (manual, S). F2/F3/F4 are Members-UI behaviour/assertion investigations (manual, M).
- **Version mismatch**: none (CI ruff 0.16.5 == local 0.16.5).

---

## Comparison with recent runs (the 10-02 → 10-10 arc)

| Metric               | 10-02 | 10-03 | 10-04 | 10-05 | 10-10 | Trend                                                  |
| -------------------- | ----- | ----- | ----- | ----- | ----- | ------------------------------------------------------ |
| CI conclusion        | ❌     | ❌     | ❌     | ❌     | ❌     | 🟠 Red — but the failure mix shifted this cycle         |
| Backend failures     | 0     | 46    | 17    | 2     | **1** | 🟢 Still improving 2 → 1                                 |
| SAM plane            | ❌ collect | ✅ | ✅ | ✅ | ✅     | ✅ Held green 4 cycles                                   |
| Frontend failures    | 0     | 0     | 0     | 0     | **3** | 🔴 **Regressed** 0 → 3 (new Members-UI cluster)         |
| Ruff lint errors     | 0     | 40    | 39    | 0     | **3** | 🔴 Regressed 0 → 3 (new sender-identity routes)         |
| Ruff format files    | 0     | 1     | 17    | 0     | **2** | 🔴 Regressed 0 → 2 (new mail-config files)              |
| Vulture              | Pass  | Pass  | Pass  | Pass  | Pass  | — Stable                                                 |
| Total backend tests  | 6645  | 6684  | 6938  | 6938  | 7068  | ↑ +130 (new Members mail tests)                         |
| Total frontend tests | 2756  | 2756  | 2928  | 3602  | 3602  | ↑ large growth; now 3 failing                           |

### Held / fixed (stayed green)

- ✅ **SAM** held green for a fourth consecutive cycle.
- ✅ **Vulture** green across the whole arc.
- 🟢 **Backend failures 2 → 1**: the 10-05 F1 (stale `os` patch in `test_landing_page_contact.py`) and F2 (Airbnb `Bevestigingscode` numeric coercion) did **not** reappear — the 10-05 H1/H2 fixes held.

### Regression this cycle

- 🔴 **Frontend regressed 0 → 3.** A new Members-UI cluster: tenant-switch role re-resolution (F2) and session-column filter composition (F3/F4). Not present in the 10-05 run — introduced by Members UI work merged onto the `test` branch.
- 🔴 **Backend Lint regressed 0 → 3 ruff + 2 format.** New `members_sender_identity_routes.py` (G201 ×2) + `members_analytics_audit.py` (RUF100, format) + `members_config_validation.py` (format). All brand-new files/lines from the Members feature.

### Recurring failures that were "fixed" last time but reappear

- **None.** No 10-05 failure recurred. The 10-05 fixes (landing-page patch target, Airbnb string key) stayed green.

### New failures introduced since the previous fix sprint

- **All of this cycle's failures are new** and all trace to **Members feature work landing on the `test` branch** without the full suite + lint being run together:
  - **F1** — new `mail_*` config keys added to the parameter schema, expected-set in `test_parameter_admin_routes.py` not updated.
  - **F2/F3/F4** — new Members-UI behaviour (tenant-switch role resolution, session-column filter composition) that the existing tests no longer match.
  - **Lint** — new `members_sender_identity_routes.py` / `members_analytics_audit.py` / `members_config_validation.py` landed un-linted / un-formatted.

---

## Lessons / Recurring Issues

1. **A feature that adds config keys must update the paired expected-set tests in the same change.** F1 is the textbook case: adding `mail_certified` / `mail_domain` / `mail_local_part` to the parameter schema left `test_parameter_admin_routes.py`'s hard-coded expected set stale. Whenever a schema/enum/key-set grows, grep for the tests that assert the full set and update them in lockstep (the Change-With-Tests contract).

2. **New files must be linted and formatted before they land.** The three new Members route/service files landed with 3 ruff-lint + 2 ruff-format findings — all mechanical (`G201`, `RUF100`, format). A pre-push `ruff check src/ && ruff format --check src/` (the still-open **L1** from the 10-03→10-05 arc) would have blocked every one of them. **This is the fourth consecutive cycle L1 would have prevented the red Backend Lint job** — it remains the highest-leverage prevention item and is carried forward again.

3. **The whole suite must run on the branch before merge, not just at the next scheduled run.** This cycle regressed on two planes (frontend + lint) that were green last cycle, because the Members work was validated piecemeal. The 10-05 spec was converging on green (46→17→2 backend); this `test`-branch cycle re-opened frontend and lint. A branch-level full-suite gate (or at least the changed-path subset from L1) would have surfaced F1–F4 and the lint debt before this run.

4. **`G201` is a trivial but blocking idiom.** `logger.error(msg, exc_info=True)` inside an `except` block should be `logger.exception(msg)`. It is CI-blocking (same priority as a test failure) and takes seconds to fix — but it only gets caught if lint runs on new code.

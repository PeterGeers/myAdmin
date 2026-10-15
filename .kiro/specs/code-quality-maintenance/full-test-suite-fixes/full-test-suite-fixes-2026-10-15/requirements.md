# Full Test Suite Fixes — 2026-10-15

## Summary

Full Test Suite run (GitHub Actions run #72 / id `38691915907`) on branch `main` @ `e600d5e2`, 2026-10-15 06:21 UTC, triggered by `schedule`. **CI conclusion: ❌ failure.** Analysis is CI-artifact-based only (no local scans), from the downloaded `backend-test-reports`, `sam-test-reports`, `frontend-test-reports`, and `backend-lint-reports` artifacts.

| Category                     | Count                                              | Δ vs 2026-10-13                                   |
| ---------------------------- | -------------------------------------------------- | ------------------------------------------------- |
| Backend test failures        | **0** (of 7214; 7200 passed, 14 skip)              | 🟢 held green 0 → 0 (+34 tests)                     |
| SAM module-plane tests       | **1 ERROR** (collection/import; 0 fail of 2061)    | 🔴 **regressed** ✅ → 1 collection error (new)      |
| Frontend test failures       | **4 assertion** (of 3684; 3668 passed, 12 skip)    | 🔴 **regressed** 0 → 4 (2 files)                    |
| Ruff lint errors (backend)   | **1** (RUF100 ×1)                                  | ⚪ flat 1 → 1 (different file)                       |
| Ruff format violations (be)  | **3 files**                                        | 🔴 **regressed** 0 → 3                              |
| Vulture (dead code)          | ✅ Pass                                             | — stable green                                     |

**CI job result**: Backend Full Test Suite ✅ (0 failed) · **SAM Module-Plane ❌ (1 collection error)** · **Frontend ❌ (4 assertion failures)** · **Backend Lint & Static Analysis ❌ (1 ruff lint + 3 ruff format)**. Three of four jobs are red. Unlike the clean 10-13 run, this cycle has a genuine **Critical** item (a SAM collection/import error that stops 1 test module from even loading) plus **4 real frontend assertion failures** in the Members UI/service area.

> 🔴 **New Critical — SAM plane broke a 5-cycle green streak.** `sam/tests/test_member_data_invariance_props.py` fails at **collection** because it imports a **Flask/MySQL-plane** migration module that transitively pulls in `mysql.connector`, which is not installed in the SAM (DynamoDB) test environment. This is a **cross-plane dependency leak**, not a logic bug — see C1.

> 🔴 **Frontend regressed 0 → 4.** Two files, two root-cause clusters: a `membersApiService` column-preferences response-envelope/shape mismatch (3 failures) and a `MembersFieldFormBody` rich-enum **locale label** mismatch (`'Standard'` vs `'Standaard'`, 1 failure). Both are in the **Members** area — the same surface that keeps re-attracting failures across the arc.

> 🟢 **The 10-13 frontend worker-OOM (E1) did NOT recur.** This run shows 0 unhandled worker errors; all 3684 frontend tests collected and ran. The 10-13 M1 heap-headroom bump (`NODE_OPTIONS=--max-old-space-size=6144`) appears to be holding for now (the suite grew +24 to 3684).

> ⚠️ **Ruff version**: CI ran **ruff 0.16.5** (pinned, matches local). The findings are real new debt, not a version-mismatch artifact.

> 🔁 **Recurring file**: `parameter_admin_routes.py` carries **both** this cycle's `RUF100` **and** one of the 3 format findings — and `members_config_validation.py` is a **recurring format file** (flagged across the 10-10 → 10-13 arc). The dead-`# noqa: BLE001` pattern is identical to the 10-13 `members_analytics_audit.py` finding, just in a different route. See Lessons.

---

## Test Results — Backend (7200 passed, 14 skipped, **0 failed**, 0 collection errors — 719.41s ≈ 11m59s)

✅ **Green.** 7214 tests collected; **zero failures, zero errors**. Backend has now held clean for two consecutive cycles (0 at 10-13, 0 here) while growing +34 tests. No backend action required.

---

## Test Results — SAM module-plane (❌ ERROR — 1 collection error of 2061 collected; 0 failures)

🔴 **Red job — a test module cannot be imported.** 2061 tests collected, **0 failures**, **1 collection ERROR**. One module never loads, so its property tests never run.

### C1 — cross-plane import leak: SAM test pulls in a MySQL migration (`ModuleNotFoundError: No module named 'mysql'`)

| Hop | Location | What happens |
| --- | -------- | ------------ |
| 1 | `sam/tests/test_member_data_invariance_props.py:77` | `from migrate_overrides_to_fixed_overrides import rename_overrides_key` |
| 2 | `backend/src/migrations/migrate_overrides_to_fixed_overrides.py:48` | `from database import DatabaseManager` |
| 3 | `backend/src/database.py:6` | `import mysql.connector` → **`ModuleNotFoundError: No module named 'mysql'`** |

**Root cause:** the SAM (DynamoDB) test environment deliberately does **not** install `mysql-connector-python` — it is the module plane, not the Flask/MySQL plane. The test only wants the **pure, DB-free** transform `rename_overrides_key` (its own comment at line 76 calls it "the PURE, DB-free config-row key migration transform"), but importing it from `migrate_overrides_to_fixed_overrides` drags in that module's **top-level** `from database import DatabaseManager`, which imports `mysql.connector` at module load. So a pure function is coupled to a MySQL driver purely by where it lives. This is a **cross-plane dependency leak**: a SAM-plane test reaching into a Flask/MySQL-plane module whose import graph requires MySQL.

**Classification: Critical.** The module fails at **collection** — nothing in `test_member_data_invariance_props.py` runs until the import is decoupled. (Per the runbook priority model, import/collection errors are Critical.)

---

## Test Results — Frontend (3668 passed, 12 skipped, **4 assertion failures** — 2 files failed of 270, 262.91s)

🔴 **Red job — 4 real assertion failures in 2 files**, both in the Members area. Grouped into two root-cause clusters:

### F1 — `membersApiService` column-preferences response-shape mismatch (3 failures)

File: `frontend/src/services/membersApiService.test.ts` — suite *"membersApiService — column preferences (task 2.5.5)"*.

| Test | Assertion | Observed |
| ---- | --------- | -------- |
| `getColumnPreferences > unwraps the {data} envelope and maps { sub, columns, updated_at }` | expected 2-key object | got **3-key** object `{ sub, …(3) }` |
| `getColumnPreferences > defaults columns to [] when the backend omits the field entirely` | expected `{ Object (sub, columns, ...) }` | got `{ sub: '', columns: [], …(2) }` |
| `saveColumnPreferences > PUT /members/column-preferences with a { columns } body` | expected 2-key object | got **3-key** object `{ sub, …(3) }` |

**Root cause (one cluster):** the service now returns an **extra field** (the `…(3)` vs the expected `…(2)`) — consistent with `getColumnPreferences`/`saveColumnPreferences` beginning to surface `updated_at` (or a similarly added key) in the mapped result while the tests still assert the older 2-key `{ sub, columns }` shape. Classic **source-ahead-of-test drift**: the service's response contract changed and its allocated test still encodes the previous shape. Either the service now maps a field the tests should assert, or it leaks a field it should strip — needs a one-line look at `membersApiService.getColumnPreferences`/`saveColumnPreferences` to decide which side is correct, then align the paired test (per the Change-With-Tests Contract).

### F2 — `MembersFieldFormBody` rich-enum **locale label** mismatch (1 failure)

File: `frontend/src/components/members/MembersFieldFormBody.currentValue.test.tsx` — *"current value always visible + preserved (LazySelect) > shows a rich-enum value at rest even when the caller role cannot pick that option"*.

| Assertion | Observed |
| --------- | -------- |
| expected `[ 'Standaard' ]` (nl) | got `[ 'Standard' ]` (en) |

**Root cause (one cluster):** the rendered rich-enum option label resolved to the **English** `'Standard'` where the test expects the **Dutch** `'Standaard'`. Either the component's label resolution changed its locale/source (now showing the raw/English label instead of the localised one) or the test's expected label drifted from the fixture. A locale/label-source regression in the LazySelect current-value rendering path — scope is a single assertion.

**Grouped by root cause:** 2 clusters — F1 (members column-preferences shape, 3 tests) and F2 (members rich-enum locale label, 1 test). Both in the Members UI/service surface.

---

## Lint & Static Analysis (Backend Lint job — ❌ FAIL)

| Check | Result |
|-------|--------|
| Ruff Lint | ❌ Fail — **1 error** (`RUF100` ×1), ruff 0.16.5 |
| Ruff Format | ❌ Fail — **3 files** would be reformatted (325 already formatted) |
| Vulture | ✅ Pass (no dead code) |

### Ruff Lint — 1 error (CI-blocking)

| Rule | Count | Auto-fixable | File:line |
| ---- | ----- | ------------ | --------- |
| `RUF100` | 1 | ✅ `--fix` | `src/routes/parameter_admin_routes.py:73:31` — unused `# noqa` directive (non-enabled: `BLE001`) |

The flagged line is `except Exception as exc:  # noqa: BLE001 — surface the real projection error to the caller`. `BLE001` (blind-except) is **not enabled** in `backend/ruff.toml`, so the `# noqa: BLE001` suppresses nothing and ruff reports the directive itself as dead. **1 of 1 fixable** with `--fix`. Because the comment carries a real rationale, the clean fix is to drop **only** the `# noqa: BLE001` token and keep the human comment — this is the **identical pattern** ruff flagged at 10-13 in `members_analytics_audit.py` (H1 there), now recurring in a different route. See Lessons.

### Ruff Format — 3 files

| File | Nature of reformat |
| ---- | ------------------ |
| `src/routes/parameter_admin_routes.py:324` | collapse a multi-line `jsonify({...})` to a single line |
| `src/services/_projection_config_builders.py:169` | blank-line normalisation after a docstring before a nested `def` |
| `src/services/members_config_validation.py:174, 472` | blank-line after docstring + collapse a multi-line `raise MembersConfigError({...})` |

✅ All 3 are mechanical whitespace/line-wrap fixes that `ruff format` applies automatically. Note `parameter_admin_routes.py` appears in **both** lint and format (same file, two findings), and `members_config_validation.py` is a **recurring format file** across the arc.

### Totals by category

- **CI-blocking** this cycle: **1 ruff-lint error + 3 ruff-format files** (Backend Lint job red), the **SAM collection error** (SAM job red), and **4 frontend assertion failures** (Frontend job red). Backend tests and vulture are green.
- **Auto-fixable vs manual (lint/format)**: the single `RUF100` is `--fix`-able (prefer surgical token removal to preserve the rationale comment); all 3 format findings are `ruff format`-applied (fully automatic).
- **Test fixes**: C1 is a structural import decoupling (Critical); F1/F2 are frontend assertion fixes (High).
- **Version mismatch**: none (CI ruff 0.16.5 == local 0.16.5).

---

## Comparison with recent runs (the 10-04 → 10-15 arc)

| Metric               | 10-04 | 10-05 | 10-10 | 10-13 | 10-15 | Trend                                                       |
| -------------------- | ----- | ----- | ----- | ----- | ----- | ----------------------------------------------------------- |
| CI conclusion        | ❌     | ❌     | ❌     | ❌     | ❌     | 🔴 Still red — broader this cycle (3 red jobs)               |
| Backend failures     | 17    | 2     | 1     | 0     | **0** | 🟢 Held green 0 → 0 (+34 tests)                               |
| SAM plane            | ✅     | ✅     | ✅     | ✅     | **❌** | 🔴 Broke a 5-cycle green streak (1 collection error)         |
| Frontend failures    | 0     | 0     | 3     | 0*    | **4** | 🔴 Regressed 0 → 4 (2 Members files); 10-13 OOM did not recur |
| Ruff lint errors     | 39    | 0     | 3     | 1     | **1** | ⚪ Flat 1 → 1 (different file)                                |
| Ruff format files    | 17    | 0     | 2     | 0     | **3** | 🔴 Regressed 0 → 3                                            |
| Vulture              | Pass  | Pass  | Pass  | Pass  | Pass  | — Stable                                                     |
| Total backend tests  | 6938  | 6938  | 7068  | 7166  | 7214  | ↑ +48 since 10-13                                            |
| Total frontend tests | 2928  | 3602  | 3660  | 3660  | 3684  | ↑ +24; no worker OOM this run                                 |

\* 10-13 frontend was 0 assertion failures + 1 infra worker-OOM error (E1).

### Held / fixed (stayed green)

- 🟢 **Backend held 0 → 0**: no backend assertion or collection failures for a second consecutive cycle.
- 🟢 **Frontend worker-OOM (E1) did NOT recur**: 0 unhandled worker errors this run; all 3684 tests collected and ran. The 10-13 M1 `NODE_OPTIONS` heap bump is holding so far.
- 🟢 **Ruff lint count flat at 1** and **vulture green**.

### Recurring failures that were "fixed" last time but reappear

- **Dead-`# noqa: BLE001` pattern recurs across files.** 10-13 cleared an `RUF100` `# noqa: BLE001` in `members_analytics_audit.py` (H1). This cycle the **same pattern** reappears in a **different** route, `parameter_admin_routes.py:73` — a `# noqa: BLE001` on an `except Exception` boundary against a rule the project does not enable. The individual line was fixed; the **habit** was not. (See Lessons.)
- **`members_config_validation.py` is a recurring format file**: it carried format findings earlier in the arc and is back among the 3 format files here.
- **Members UI/service area keeps re-attracting failures**: 10-10 had a Members-UI cluster (F2/F3/F4), 10-13 had an `members_analytics_audit.py` lint finding, and 10-15 has F1/F2 (membersApiService + MembersFieldFormBody) plus two Members-area lint/format files. The Members surface is the arc's most failure-prone area.

### New failures introduced since the previous fix sprint

- **C1 (SAM collection error)** is new and is a **regression**: a 5-cycle-green plane went red because a SAM test imports a Flask/MySQL-plane migration whose import graph needs `mysql.connector`. This is a structural cross-plane leak, likely introduced when the invariance property test was added/edited to reuse `rename_overrides_key`.
- **F1/F2 (frontend, 4 assertions)** are new Members regressions — F1 is source-ahead-of-test drift on the column-preferences response shape; F2 is a rich-enum locale-label regression.
- **3 ruff-format files** are new since the clean 10-13 format run.

---

## Lessons / Recurring Issues

1. **Keep the planes' import graphs separate — a SAM test must not transitively import `mysql.connector`.** C1 is the textbook cross-plane leak: a DynamoDB-plane test imports a Flask/MySQL-plane migration module (`migrate_overrides_to_fixed_overrides`) only to reach one **pure** function, but that module's top-level `from database import DatabaseManager` drags in the MySQL driver, which the SAM env does not install. The durable fix is to make the pure transform importable **without** the DB dependency — either move `rename_overrides_key` into a DB-free helper module, or make `migrate_overrides_to_fixed_overrides` import `DatabaseManager` lazily (inside the function that needs it) rather than at module top level. A pure, DB-free function should never force a MySQL import.

2. **Source-ahead-of-test drift is the top recurring Full Test Suite failure — and it is here again (F1).** `membersApiService` changed its column-preferences response shape (now a 3-key object) while the allocated test still asserts the 2-key shape. Per the Change-With-Tests Contract, a behavioral change to the service's response contract must update its paired test in the **same** change. Decide which side is correct (does the service rightly surface `updated_at`, or should it strip it?), then align the test — do not weaken assertions to go green.

3. **The dead-`# noqa: BLE001` habit keeps re-appearing in exception boundaries.** 10-13 fixed one in `members_analytics_audit.py`; 10-15 has the identical pattern in `parameter_admin_routes.py`. Writing `# noqa: <rule>` for a rule the project does not enable in `backend/ruff.toml` is self-defeating — ruff flags the suppression as dead every time. When adding an exception-boundary comment, keep the human rationale but **drop the `# noqa:` token** unless the rule is actually enabled. A pre-push `ruff check` (the long-open **L1**) would have caught both the lint and the 3 format findings before they landed on `main`.

4. **The pre-push ruff gate (carried L1) would, again, have blocked the Backend Lint job.** This is the Nth consecutive cycle where a pre-push `ruff check src/ && ruff format --check src/` would have prevented a red Backend Lint job — this run it would have caught 1 lint + 3 format findings in seconds. It remains the highest-leverage prevention item and is carried forward as L1.

5. **The Members surface is the arc's hotspot.** Members-area tests/lint findings have appeared in 10-10, 10-13, and 10-15. Consider a focused Members-area test-health pass (service response contracts + locale label resolution + exception-boundary comments) rather than fixing one Members failure at a time.

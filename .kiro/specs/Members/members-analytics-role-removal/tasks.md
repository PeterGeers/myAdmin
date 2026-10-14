# Implementation Plan

## Overview

This is a **removal plan**, executed green-at-every-step. The ordering mirrors design.md's
**Step A → B → C → D** (consumers-before-definitions) so the build never goes red mid-removal.
Task 0 is the EQUIVALENCE GATE and MUST pass before any deletion task (1.x–4.x) runs.

**Change-With-Tests (steering 30/34):** every task that removes or slices product code updates or
deletes its paired test(s) **in that same task** — there is no separate "fix tests later" task.
Deleted-in-full test files are called out explicitly; realigned test files are called out per task.

## Task Dependency Graph

Run top-to-bottom; no task deletes a definition before its consumers (frontend consumers in Step A
are re-wired before the SAM serve/read slice in Step B, which is removed before the SAM domain
classes in Step C). Waves run in order; tasks within a wave may run in parallel once their
dependencies are satisfied.

```json
{
  "waves": [
    { "wave": 1, "tasks": ["0"], "depends_on": [], "note": "EQUIVALENCE GATE — blocks all deletions" },
    { "wave": 2, "tasks": ["1"], "depends_on": ["0"], "note": "Step A — frontend leaves + consumers" },
    { "wave": 3, "tasks": ["1.G"], "depends_on": ["1"], "note": "green gate A" },
    { "wave": 4, "tasks": ["2"], "depends_on": ["1.G"], "note": "Step B — SAM serve/read + Flask param slice" },
    { "wave": 5, "tasks": ["2.G"], "depends_on": ["2"], "note": "green gate B" },
    { "wave": 6, "tasks": ["3"], "depends_on": ["2.G"], "note": "Step C — SAM domain classes last" },
    { "wave": 7, "tasks": ["3.G"], "depends_on": ["3"], "note": "green gate C" },
    { "wave": 8, "tasks": ["4"], "depends_on": ["3.G"], "note": "Step D — fixtures + spec retirement" },
    { "wave": 9, "tasks": ["4.G"], "depends_on": ["4"], "note": "green gate D" },
    { "wave": 10, "tasks": ["5"], "depends_on": ["0"], "note": "read-only TEST+PROD inventory (independent of code steps)" },
    { "wave": 11, "tasks": ["6"], "depends_on": ["2.G", "3.G"], "note": "single re-projection of config#fields" },
    { "wave": 12, "tasks": ["7"], "depends_on": ["5", "6"], "note": "manual TEST pivot sign-off — gates PROD promotion" },
    { "wave": 13, "tasks": ["8"], "depends_on": ["1.G", "2.G", "3.G", "4.G"], "note": "completeness: manifest + suites" },
    { "wave": 14, "tasks": ["9"], "depends_on": ["7", "8"], "note": "ship: PR→test→merge to main" }
  ]
}
```

## Tasks

- [x] 0. **EQUIVALENCE GATE** — prove every removed capability is reachable generically (code level, BEFORE any deletion)
  - **Property 1: Bug Condition** — Role/Jubilee/Address/Preset machinery is live and redundant
  - **IMPORTANT:** This is the exploratory + gating task. Run it on the UNFIXED code. It MUST confirm
    `C(X)` currently holds (the manifest returns hits) AND that each removed capability already has a
    generic-pivot equivalent — this gates tasks 1.x–4.x. Do NOT delete anything in this task.
  - **GOAL:** surface the current footprint and confirm the 11-row EQUIVALENCE GATE table (design.md
    §Fix Implementation) at code level, so no capability is lost by the removal.
  - Run the four grep manifest patterns across `{source ∪ tests}` (exclude `**/.aws-sam/build/**`,
    `**/node_modules/**`, `**/.venv/**`, Vitest caches, spec/history prose) and confirm hits match the
    bugfix §Known footprint — **expected: non-zero** (this confirms the bug exists):
    - `AnalyticsRole|field_roles|fieldRoles|cancellation_date|referral_source|clubblad_paper|clubblad_digital|country_detail`
    - `JubileeRule|jubilee_rule|jubileeRule|usesJubileeRule|candidateJubileeYears|selectedJubileeYear|applyJubileeYearFilter|DEFAULT_JUBILEE|JUBILEE_YEAR|jubileeYear`
    - `AddressMapping|address_mapping|addressMapping|resolveAddressMapping|composeAddresses|generateAddressLabelPdf`
    - `AnalyticsConfig|_build_analytics|_serialize_analytics|analyticsConfig|hasAnalyticsConfig`
  - Walk each of the **11 EQUIVALENCE GATE rows** and confirm, in code, the surviving generic mechanism
    exists and produces the subset — all 8 presets + the address-label path + the mail-recipient path:
    - rows 1–8 (presets): `membership-types` → group-by COUNT on `membership_type`; `birthday-birth-month`
      → `applyDefinitionFilters({ birth_month })` + list columns; `jubilees` → `applyDefinitionFilters`
      equality on calculated `years_member`; `new-members` → `applyDefinitionFilters` on `joined_date`;
      `cancellations`/`clubblad-paper`/`clubblad-digital`/`referral-source` → `applyDefinitionFilters`
      equality (e.g. `{ clubblad: 'Papier' }`) and/or `groupColumns` + COUNT.
    - row 9 (address labels): template path `composeLabelLines` / `generateLabelTemplatePdf` /
      `MemberLabelsPanel`.
    - rows 10–11 (mail/CSV recipient): `resolveEmailField` typed-`email`-then-`CONVENTIONAL_EMAIL_KEYS`
      body + user column selection on the pivot result.
  - **Confirm `MemberLabelsPanel` / `composeLabelLines` read NO `analytics.*`** (template-label
    independence) — grep those files for `analytics` and assert zero functional hits.
  - **Paired check:** no code change in this task; record the confirmed footprint + per-row equivalence
    as the review artifact (write the walk-through under repo-root `.agent-output/`, git-ignored).
  - _Design: EQUIVALENCE GATE (11-row table) + Exploratory Bug Condition Checking_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.8_
  - **Verify:** manifest returns the expected non-zero footprint; all 11 rows confirmed reachable
    generically; `MemberLabelsPanel`/`composeLabelLines` confirmed `analytics.*`-free. GATE OPEN.

---

## Step A — Frontend leaves + consumers (nothing below the frontend depends on it)

- [x] 1. Remove the frontend role/jubilee/address/preset surface (consumers re-wired first, then leaves deleted/sliced)
  - **Depends on:** Task 0 (GATE OPEN).

  - [x] 1.1 Re-wire `MemberPivotViews.tsx` consumer + build the **empty Pivot Views entry point**
    - Drop the preset import/memo (`getAvailablePresets` / `getPresetsWithAvailability` /
      `MemberPivotPreset`); make the `sets` list **saved-models-only** (remove preset-sourced
      `SelectableSet` entries, so the preset `<optgroup>` disappears).
    - Remove the jubilee-year and joined-after-year selectors and their state
      (`showsJubileeSelector` / `jubileeYearOptions` / `showsJoinedAfterSelector` / `joinedYearOptions`
      and the `usesJubileeRule` / `usesJoinedAfterFilter` plumbing).
    - Drop the `generateAddressLabelPdf` + `resolveAddressMapping` imports and the old address-path
      branch (template `MemberLabelsPanel` already covers labels).
    - **Empty-state hint:** when there are no saved sets, render the existing shared
      `AnalyticsStateNotice` in an empty-hint variant with the `MemberFieldPicker` **New set** button as
      the single CTA. Reuse existing components — no new component, no dead control. Keep Execute,
      `MemberFieldPicker` compose/save, `PivotResultTable`, and the CSV/mail/template-label export slot
      exactly as-is.
    - **Paired test:** realign preset/jubilee/address assertions in `MemberPivotViews.test.tsx`; add the
      empty-state (empty-hint + New set CTA, generic compose/execute/export) assertions.
    - _Design: Step A.1 + Empty Pivot Views entry point_
    - _Requirements: 2.3, 2.4, 2.5, 3.1, 3.3_

  - [x] 1.2 Re-wire `MemberMailCompose.tsx` consumer
    - Drop the `resolveAddressMapping` import; the "Attach PDF labels" toggle gates on the presence of a
      label template (consistent with `MemberLabelsPanel`), not on `resolveAddressMapping`.
    - Switch `resolveEmailField` usage to the field-config-only resolution (typed-`email` then
      `CONVENTIONAL_EMAIL_KEYS`).
    - **Paired test:** realign `MemberMailCompose.test.tsx` to the field-config recipient resolution and
      the template-gated toggle.
    - _Design: Step A.2_
    - _Requirements: 2.5, 2.6, 3.3_

  - [x] 1.3 Delete the two full-delete leaf modules + their paired tests
    - **Delete in full:** `memberPivotPresets.ts` **and** `memberPivotPresets.test.ts`;
      `AddressLabelGenerator.tsx` **and** `AddressLabelGenerator.test.tsx`.
    - **Paired test:** the deletions ARE the paired-test action (both test files are deleted in full in
      this same task — do not leave them asserting removed behavior).
    - _Design: Step A.3; EQUIVALENCE GATE rows 1–9_
    - _Requirements: 2.3, 2.5, 2.10_

  - [x] 1.4 Slice `analytics/analyticsConfig.ts`
    - Remove `resolveRole`, `isJubileeYear`, `candidateJubileeYears`, `selectedJubileeYear`,
      `applyJubileeYearFilter`, `JUBILEE_YEAR_FILTER_KEY`, `DEFAULT_JUBILEE_MULTIPLE`, `MAX_JUBILEE_YEAR`,
      `resolveAddressMapping`, `hasAnalyticsConfig`, the preset-specific joined-after selector
      (`candidateJoinedYears` / `selectedJoinedAfterYear` / `applyJoinedAfterFilter` /
      `JOINED_AFTER_FILTER_KEY`), and the `field_roles` branch of `resolveEmailField`.
    - **Keep** `applyDefinitionFilters`, `CONVENTIONAL_EMAIL_KEYS`, and the surviving `resolveEmailField`
      body (field-config only).
    - **Paired test:** realign `__tests__/analyticsConfig.test.ts` — remove role/jubilee/address cases;
      keep/strengthen `applyDefinitionFilters` (equality narrowing, reserved-key skip, blank-value
      no-narrow) and the field-config `resolveEmailField` cases.
    - _Design: Step A.4; Mixed modules sliced-not-deleted_
    - _Requirements: 2.4, 2.6, 2.10, 3.1_

  - [x] 1.5 Slice `analytics/addressLabelService.ts`
    - Remove `composeAddresses`, `generateAddressLabelPdf`, `LabelSortOrder`, `ComposedAddress`,
      `ComposeResult`. **Keep** `composeLabelLines`, `generateLabelTemplatePdf`, and the Avery
      formats/geometry (`AVERY_LABEL_FORMATS`, `getLabelFormat`, `labelsPerPage`, `cellPosition`,
      `pageCount`, `clampFontSize`, `MIN/MAX_FONT_SIZE`, `LabelAlignment`, `LabelStyleOptions`,
      `GenerateResult`).
    - **Paired test:** realign `addressLabelService.test.ts` — remove the address-path assertions; keep
      the template-path + Avery geometry tests (file survives).
    - _Design: Step A.5; EQUIVALENCE GATE row 9_
    - _Requirements: 2.5, 2.10, 3.3_

  - [x] 1.6 Slice the `analytics/index.ts` barrel
    - Drop the removed re-exports (the C-CONFIG role-helpers block, the C4 preset block, the C5
      `composeAddresses` / `generateAddressLabelPdf` / `AddressLabelGenerator` block); keep the surviving
      re-exports.
    - **Paired test:** no dedicated barrel test; covered by the suites in gate 1.G (import resolution).
    - _Design: Step A.6_
    - _Requirements: 2.3, 2.5_

  - [x] 1.7 Remove the Members config **Analytics** tab
    - Delete `TenantAdmin/MembersConfig/membersAnalyticsFold.ts` and remove the `MembersConfigEditor`
      Analytics slice; keep the save-once / reference-validation behavior for surviving slices unchanged.
    - **Paired test:** realign the `MembersConfig` suites — remove the Analytics-tab assertions; assert
      surviving-slice save/validation is unchanged.
    - _Design: Step A.7_
    - _Requirements: 2.2, 2.10_

  - [x] 1.8 Slice `types/members.ts`
    - Remove `AnalyticsRole`, `MemberAnalyticsConfig`, and the `analytics?` member of `FieldConfig`.
      **Keep** the analytics-SET types (`MemberAnalyticsSetSummary`, `MemberAnalyticsSet`,
      preferred-list types).
    - **Paired test:** covered by the type-consuming suites in gate 1.G (compile + referencing tests).
    - _Design: Step A.8; Scope boundary (analytics-SET preserved)_
    - _Requirements: 2.1, 2.3_

  - [x] 1.9 Locale keys: remove removed keys, add the empty-hint keys
    - In `locales/{nl,en}/members.json` remove the analytics-role / jubilee / address-mapping keys **and**
      `analytics.pivotViews.presetNames.*`; **add** `analytics.pivotViews.emptyHint.*` (bilingual nl/en)
      used by the Task 1.1 empty-state hint.
    - **Paired test:** realign `labelOptions.test.ts` and `MemberAnalyticsPage.test.tsx` to the new/removed
      keys (no reference to removed preset/jubilee/address strings; empty-hint strings present).
    - _Design: Step A.9 + A.10; Empty Pivot Views entry point_
    - _Requirements: 2.2, 2.3, 3.3_

  - [x] 1.G **Green gate A** — frontend compiles and the touched frontend suites are green
    - Run: `cd frontend && npx vitest run src/components/members/analytics src/components/TenantAdmin/MembersConfig`
    - Confirm the deleted-in-full tests (`memberPivotPresets.test.ts`, `AddressLabelGenerator.test.tsx`)
      are gone and that `analyticsConfig.test.ts`, `MemberPivotViews.test.tsx`, `MemberMailCompose.test.tsx`,
      `addressLabelService.test.ts`, `labelOptions.test.ts`, `MemberAnalyticsPage.test.tsx`, and the
      `MembersConfig` suites are GREEN.
    - _Design: Green gate A_
    - _Requirements: 3.9_
    - **Verify:** build green, named suites green, deleted tests absent. Build NOT red before Step B.

---

## Step B — SAM read/serve + Flask param slice (depends on the domain classes; consumed by the payload removed in A)

- [x] 2. Remove the SAM serve/read of the analytics role-config slice + the Flask param schema slice
  - **Depends on:** gate 1.G (frontend no longer consumes the served `analytics` payload).

  - [x] 2.1 SAM writer — remove `_serialize_analytics` and the served `"analytics"` key
    - In `sam/members/domain/_membership_writes.py` remove `_serialize_analytics` and the `"analytics"`
      key from the served field-config payload. Do NOT touch
      `_membership_analytics._serialize_analytics_set` (preserved analytics-SET feature).
    - **Paired test:** realign `sam/tests/test_field_config_endpoint.py` to assert the served payload
      **omits** the `analytics` key and is otherwise identical.
    - _Design: Step B.11; Scope boundary_
    - _Requirements: 2.1, 2.10, 3.5_

  - [x] 2.2 SAM reader — remove `_build_analytics` / `_build_jubilee_rule` / `_build_address_mapping`
    - In `sam/members/repository/projection_config_reader.py` remove those three builders and the
      `analytics=` wiring on `get_overlay`.
    - **Paired test:** realign `sam/tests/test_members_projection_reader.py` — remove the
      analytics/role/jubilee/address assertions; keep the surviving overlay-read assertions.
    - _Design: Step B.12_
    - _Requirements: 2.1, 2.10, 3.5_

  - [x] 2.3 Flask param schema — remove the `analytics` object slice
    - In `backend/src/config/members_parameters.json` remove the `analytics` object slice (the schema
      authoring `jubilee_rule` / `field_roles` / `address_mapping`). No Flask service builder/validator
      exists (confirmed in design) — nothing else on this plane.
    - **Paired test:** if a members-parameters schema test references the removed slice, realign it;
      otherwise covered by gate 2.G.
    - _Design: Step B.13; 30/31 Flask-plane compliance_
    - _Requirements: 2.1, 2.10_

  - [x] 2.G **Green gate B** — SAM serve/read suites green
    - Run (from the SAM test root per repo layout):
      `cd backend && source .venv/bin/activate && python -m pytest sam/tests/test_field_config_endpoint.py sam/tests/test_members_projection_reader.py -q`
    - _Design: Green gate B_
    - _Requirements: 3.9_
    - **Verify:** served payload omits `analytics` and is otherwise identical; reader suites green.
      Build NOT red before Step C.

---

## Step C — SAM domain classes last (consumed by B; delete only once B stops referencing them)

- [x] 3. Remove the SAM domain role/jubilee/address classes + catalog prose
  - **Depends on:** gate 2.G (reader/writer no longer reference the domain classes).

  - [x] 3.1 Remove the domain classes and their wiring
    - In `sam/members/domain/field_resolver.py` remove `AnalyticsRole`, `AnalyticsConfig`, `JubileeRule`,
      `AddressMapping`, the `FieldConfig.analytics` and `TenantOverlay.analytics` members, and their
      `__all__` entries. Remove the `domain/__init__.py` re-exports of `AddressMapping` /
      `AnalyticsConfig` / `AnalyticsRole`.
    - **Paired test:** realign `sam/tests/test_field_resolver.py` — remove the `AnalyticsConfig`/role/
      jubilee/address assertions; keep the surviving resolved-field (fixed ⊕ overlay ⊕ calculated),
      ordering, groups, scope, lifecycle assertions.
    - _Design: Step C.14; Preservation Req 3.5_
    - _Requirements: 2.1, 2.10, 3.5_

  - [x] 3.2 Remove the analytics role/alias prose from the attribute catalog
    - In `sam/members/domain/attribute_catalog.py` remove the role/alias `note=` prose (metadata only,
      no behavior).
    - **Paired test:** realign the role/analytics assertions inside `sam/tests/test_attribute_catalog.py`
      and `sam/tests/test_field_classification_traceability.py` so the catalog drift guard stays green.
    - _Design: Step C.15; catalog drift guard_
    - _Requirements: 2.1, 2.10, 3.9_

  - [x] 3.G **Green gate C** — SAM domain + drift-guard suites green
    - Run:
      `cd backend && source .venv/bin/activate && python -m pytest sam/tests/test_field_resolver.py sam/tests/test_attribute_catalog.py sam/tests/test_field_classification_traceability.py sam/tests/test_members_modal_mapping_preservation.py -q`
    - _Design: Green gate C_
    - _Requirements: 3.9_
    - **Verify:** domain classes gone, no import errors, catalog drift guard GREEN, modal-mapping
      preservation GREEN.

---

## Step D — Fixtures + `member-analytics` spec retirement (no code depends on these)

- [x] 4. Clean fixtures and retire the `member-analytics` ACs/tasks
  - **Depends on:** gates 1.G / 2.G / 3.G (all code removed/sliced).

  - [x] 4.1 Fixture verify-and-assert-clean (expected no-op)
    - In `scripts/onboarding/members/h-dcn/members_config.json` **verify no `jubilee_rule` /
      `field_roles` / `address_mapping` slice is authored** (confirmed clean during design). If a slice
      is found, delete it in this task; otherwise no edit.
    - **Paired test:** no paired test — the grep gate (Task 8) explicitly covers this fixture.
    - _Design: Step D.16_
    - _Requirements: 2.10_

  - [x] 4.2 Retire the `member-analytics` spec ACs/tasks (annotate as removed by `members-analytics-role-removal`)
    - In the `member-analytics` spec: annotate/retire acceptance criteria **R9.1–R9.4** in full; the
      role/jubilee/address-mapping clauses of **R4.2 / R4.3 / R4.10 / R4.12**; and the fixed/calculated
      preset clauses of **R4.2 / R4.3**.
    - Annotate the design **C4 preset table** as removed.
    - Annotate/retire tasks **6.1–6.4**, **7.6**, the role parts of **7.2 / 8.2 / 8.3**, the
      `field_roles` recipient-resolution part of **9.2**, and the preset-table / serving-fn / Pivot-Views
      preset-dropdown task(s) — so **no AC/task still mandates any predefined preset**.
    - Reflect the retirement in `tasks.meta.json` where that spec tracks task state.
    - **Paired test:** spec-prose only (no code paired test); covered by the Task 8 grep manifest for any
      lingering symbol references.
    - _Design: Step D.17_
    - _Requirements: 1.8, 2.9_

  - [x] 4.G **Green gate D** — spec/fixture plane clean under the grep manifest
    - Run the full four-pattern grep manifest across spec + fixtures; confirm the only remaining hits are
      **non-historical-exempt prose** that records the removal.
    - _Design: Green gate D_
    - _Requirements: 2.7, 2.9_
    - **Verify:** no fixture authors the removed slice; no `member-analytics` AC/task mandates removed
      machinery.

---

## Data flow (lean) — read-only inventory, single re-projection, manual sign-off

- [x] 5. Read-only stored-reference inventory in TEST **and** PROD (member records never touched)
  - **Depends on:** Task 0 (can run any time after the GATE; independent of the code steps).
  - Run a **read-only** inventory across the h-dcn **TEST** and **PROD** DynamoDB tables reporting which
    saved pivots / analytics-sets reference a removed construct (a role name, the `jubilee_rule`-driven
    `years_member` filter key, or an address-mapping slot). Reporting only: query **no** member records
    (`sam-members` is never queried), write nothing.
  - Go through the documented wrapper (steering 41 + `#database`):
    `PYTHONPATH=backend/src backend/scripts/railway-db.sh python <inventory_script>` against the
    `finance` schema. **Sanity-check identity before any PROD read** — `aws sts get-caller-identity`
    MUST print `506221081911` (NonprofitDeployRole), not `344561557829`; apply the env-strip
    belt-and-suspenders if stale static keys linger.
  - Output a human-readable report under repo-root `.agent-output/` (git-ignored, NOT a committed
    fixture) listing each referencing set by `set_id`/name and the construct it references — this is the
    checklist the human re-runs in Task 7.
  - **Paired test:** none — read-only reporting script, no product-code change.
  - _Design: Data Flow — read-only inventory; Validation Honesty gate_
  - _Requirements: 2.11, 3.7_
  - **Verify:** report produced for TEST and PROD; `sam-members` untouched; identity confirmed
    `506221081911` before PROD read.

- [x] 6. **Single** re-projection to clean the `config#fields` role-config slice
  - **DONE (no-op, already clean — evidence):** Task-5 inventory showed the MySQL source (TEST Docker + PROD Railway, schema `finance`) has ZERO `members.*` rows carrying a removed analytics slice. A READ-ONLY, account-guarded (506221081911) probe of the PROD `governance_projection` `config#fields` row for `h-dcn` returned `has_analytics_key=False` (keys: fields, functional_groups, overrides, sk, tenant_id, version). Source clean + projection clean + served payload omits `analytics` (gate 2.G) ⇒ nothing to re-project. A forced re-projection would only bump the tenant row to write a byte-identical analytics-free row — pure churn — so it was deliberately NOT run. Member records (`sam-members`) never touched.
  - **Depends on:** Step B (2.G) + Step C (3.G) landed — once the `analytics` slice no longer projects.
  - Run **one** re-projection through the existing `backend/src/services/projection_sync.py` path (the
    same mechanism that projects the overlay onto `config#fields`); the row is rewritten without the
    `analytics` role-config slice. No staged production-migration apparatus. Member records never read
    or written.
  - Run via `PYTHONPATH=backend/src backend/scripts/railway-db.sh python <reprojection_entry>`, identity
    sanity-checked as in Task 5.
  - **Paired test:** none for the migration run itself; the served-shape guarantee is asserted by
    `test_field_config_endpoint.py` (Task 2.1) — `config#fields` omits `analytics`, otherwise identical.
  - _Design: Data Flow — single re-projection; member-data invariant_
  - _Requirements: 2.11, 3.5, 3.7_
  - **Verify:** `config#fields` no longer carries the `analytics` role-config slice; the resolved field
    SET/ordering/other slices unchanged; `sam-members` untouched.

- [ ] 7. **MANUAL human sign-off gate** — re-run inventoried pivots in TEST before any PROD promotion
  - **Depends on:** Task 5 (inventory report) + Task 6 (TEST re-projection).
  - A **person** manually re-runs each pivot/set from the Task 5 inventory **in TEST** and confirms each
    still produces the intended result. This is an explicit human checklist, not an automated claim —
    the automation proves only code-level equivalence (Task 0) + the read-only inventory (Task 5).
  - **This gate MUST pass before the PROD promotion in Task 9.** Record sign-off (who, when, which sets
    confirmed) alongside the inventory report under `.agent-output/`.
  - **Paired test:** none — human verification gate.
  - _Design: Explicit human sign-off gate; Validation Honesty_
  - _Requirements: 2.11, 3.1_
  - **Verify:** every inventoried TEST pivot/set confirmed by a human to produce its intended result;
    sign-off recorded. GATE for PROD promotion.

---

## Completeness

- [ ] 8. **Fix-Checking completeness** — manifest clean, drift guard green, touched suites green
  - **Depends on:** gates 1.G / 2.G / 3.G / 4.G.
  - **Property 1: Expected Behavior** — Role/Jubilee/Address/Preset machinery fully removed
  - **IMPORTANT:** re-run the SAME manifest + suites from the gates — do not write new ones. This
    confirms `C(X)` holds nowhere.
  - Run the full **four-pattern** grep manifest across `{source ∪ tests}` (excluding `**/.aws-sam/build/**`,
    `**/node_modules/**`, `**/.venv/**`, Vitest caches, and removal-recording prose) → **zero
    non-historical hits**.
  - Confirm the **catalog drift guard** is GREEN (`sam/tests/test_attribute_catalog.py`,
    `sam/tests/test_field_classification_traceability.py`).
  - Confirm the touched **SAM** suites (`test_field_resolver.py`, `test_members_projection_reader.py`,
    `test_field_config_endpoint.py`, `test_members_modal_mapping_preservation.py`), the **Flask** plane,
    and the touched **frontend** suites (`analyticsConfig.test.ts`, `MemberPivotViews.test.tsx`,
    `MemberMailCompose.test.tsx`, `labelOptions.test.ts`, `MemberAnalyticsPage.test.tsx`, the
    `MembersConfig` suites) are GREEN; the deleted-in-full tests
    (`memberPivotPresets.test.ts`, `AddressLabelGenerator.test.tsx`) are gone.
  - _Design: Fix Checking; Property 1_
  - _Requirements: 2.7, 2.9, 3.9_
  - **Verify:** `grep(P, non_historical) = ∅` AND catalog drift guard GREEN AND all touched suites GREEN.

---

## Ship (steering 43)

- [ ] 9. Ship — feature branch → PR into `test` → promote by merge to `main` (DATA account only)
  - **Depends on:** Task 7 (manual TEST sign-off) + Task 8 (completeness) — both MUST pass first.
  - Commit the removal on the feature branch (`spec/...`); **never push straight to `main`**. Open a PR
    into **`test`**; let the per-PR gates (CodeQL + GitGuardian) go green. Promotion to TEST is by
    **push/merge to `test`** (branch decides the env).
  - After TEST is verified (Task 7 sign-off done), open **ONE** PR `test → main`. **Preview the prod
    changeset** — `sam deploy --config-env prod --no-execute-changeset` — and confirm **no unexpected
    `Replacement: True`** on stateful resources. Clear CodeQL + GitGuardian. **Merge with a merge
    commit** (not squash) to preserve phase history.
  - A merge to `main` **IS** a production deploy; it fires `deploy-sam-members.yml` on the **DATA account
    `506221081911`** (OIDC `NonprofitDeployRole`, no stored secrets). The removal touches no Cognito pool
    trigger wiring. Confirm each deploy run `success` and stacks settle `UPDATE_COMPLETE`.
  - **The manual pivot sign-off gate (Task 7) MUST precede the PROD promotion.**
  - **Paired test:** none — release task; gates are the per-PR CodeQL/GitGuardian + the nightly Full Test
    Suite.
  - _Design: CI/CD compliance; steering 43 promote-to-prod runbook_
  - _Requirements: 2.7, 3.9_
  - **Verify:** PR green in `test`; prod changeset preview shows no unexpected replacement; `test → main`
    merged via merge commit after Task 7 sign-off; DATA-account deploy `success`, stacks
    `UPDATE_COMPLETE`.

---

## Notes

- **CodeQL trigger (undocumented — recorded here).** CodeQL is GitHub default-setup (no committed YAML, no `workflow_dispatch` — `gh workflow run` returns 422). On a feature→`test` PR it normally fires automatically on the `pull_request` open/synchronize event (confirmed: PRs #91/#92 base=`test` got `refs/pull/NNN/head` CodeQL runs). If it does NOT attach to a PR, a REAL content push (fires `synchronize`) re-triggers it; an empty commit / `gh pr reopen` may not. A manual run on the DEFAULT branch (`main`) can be forced with `gh api --method PATCH repos/<owner>/<repo>/code-scanning/default-setup -f state=configured` (returns a `run_id`), but that analyzes `main`, not the PR head — it does not post the PR check. Do NOT `gh pr close` a PR to "re-trigger": it leaves the PR in a stale state and no checks fire.

- **Removal, not feature build.** "Exploratory" (Task 0) means confirming the current manifest hits
  exist and the 11-row EQUIVALENCE GATE holds *before* deleting; "fix-checking" (Task 8) means the
  manifest is clean after; "preservation-checking" means the surviving suites and the generic pivot
  behave identically.
- **Green at every step.** Each step (A–D) ends with its named green gate (1.G / 2.G / 3.G / 4.G).
  Do not start the next step until the current gate is green — the ordering exists so the build never
  goes red mid-removal.
- **Mixed modules are sliced, not deleted.** `analyticsConfig.ts`, `addressLabelService.ts`,
  `analytics/index.ts`, and `types/members.ts` each retain surviving symbols (generic-filter helper,
  template-label path, analytics-SET types). Slicing the address path cannot regress labels —
  `MemberLabelsPanel` / `composeLabelLines` read **no** `analytics.*` (confirmed in Task 0).
- **Scope boundary.** The generic analytics-SET feature (`analytics_set.py`, `_membership_analytics.py`,
  saved sets, the Pivot Views surface itself, CSV/mail/template-label exports, Overview + violins, the
  SAM `RouteGroup.ANALYTICS` routes, `members_analytics_audit.py`) is OUT of scope and preserved. The
  bare token `.analytics` matches both — the removal targets only the role-config members and the named
  constructs, never the analytics-SET feature.
- **Member-data invariant (hard).** `sam-members` is never read-for-mutation or written. The only data
  touched is the `config#fields` projection row's `analytics` role-config slice, cleaned by the single
  re-projection in Task 6. Tasks 5–7 touch stored references and config only.
- **Validation honesty.** The automation proves only code-level equivalence (Task 0) and produces a
  read-only inventory (Task 5). It does NOT prove that every live user-created pivot/set still returns
  its author's intended result — that is the manual human sign-off gate (Task 7), which MUST precede
  any PROD promotion (Task 9).
- **Reminder — write/confirm tests in the same task.** Every deletion/slice task above carries its
  paired-test action. Do not defer test realignment to a later task (the `test-sync-on-source-change`
  hook reminds you on each product-file save; this contract is the source of truth even when it does
  not fire).

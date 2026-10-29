# Implementation Plan — Enum-Vocabulary Round-Trip & No-Silent-Fallbacks (SAM plane)

- Status: **Draft** (tasks phase — build gated on approval of requirements + design). **No code until approved.**
- Follows `bugfix.md` (R2.1–R2.7, R3.1–R3.3) and `design.md` (components C1–C8, properties P1–P5,
  fallback-removal F1–F12 — F9/F10/F12 added by the task-0.1 sweep's N1/N1b/N2 findings, F11 a
  documented source-selector carve-out for N3; write-side source-integrity guards W1–W3). Delivers
  ONE vocabulary model: every selectable field resolves to ONE canonical `options` populated at the
  read-assembly seam; `choices` retired; every silent fallback removed; "declares selectable but no
  source propagated" becomes a loud, caller-safe error.
- **Two increments (design "Rollout"):** **increment 1 = the fix (C7 + C1–C6)** — backfill, uniform
  read-assembly seam, write-side guards, scope derivation, fail-loud (with the C6 hard gate);
  **increment 2 = the guard (C8)** — mechanical anti-reintroduction guard, report-only → clear
  baseline → BLOCKING, flipped only AFTER increment 1 lands and the gate is green (G6).
- **Ordering principle (spec-03 discipline — the whole point):** the symmetry/isolation harness lands
  and is proven RED FIRST; then C7 light migration so every live row carries `options`; then C1–C6
  structural fixes; the C8 guard flips to BLOCKING LAST. Proof precedes "done". (Design "Deployment
  ordering".)
- Change-with-tests throughout (steering 34/30/39): a behavioral edit updates its paired test in the
  SAME task. E2E is container-gated via `AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000` (steering 42)
  and skips cleanly when the container is absent.
- Checkbox vocab: `[ ]` not started · `[x]` done · `❌` blocked. Each task names the exact files it
  touches + a VERIFY step, and cites the requirement(s) + component(s) it delivers.
- Do NOT touch sibling spec `03`, `findings.md`, or product code outside the named seams.

---

## Phase 1 — Harness FIRST: prove RED on UNFIXED code (spec-03 discipline) — ~1 day  (R2.2, R2.5, R2.6)

- [x] 0.1 **DISCOVERY — identify EVERY old path/pattern; reconcile against F1–F8 (close the gap).**
  - The fallback-removal list F1–F8 was built from the seams traced during design — NOT an exhaustive
    codebase sweep. This task PROVES the list complete before any removal, so no old path slips through.
  - **Sweep both planes** for the vocabulary old-paths/patterns:
    - `sam/**/*.py`: `\.choices`, `options or choices`, `choices or options`,
      `_build_options\(`, `\.get\("choices"\)`, `FieldScope\(`, `\.values` on a scope object,
      per-field-KIND branches (`type is FieldType.ENUM` / `== "reference"` / `membership_type` /
      `scope` special-casing) in any vocabulary consumer, and every call site of
      `_build_override` / `_build_overlay_field` / `_as_variable_field` / `_apply_override`.
    - `frontend/src/**/*.{ts,tsx}`: `choices`, `options`, `optionsToChoices`, `DEFINITION_ATTRS`,
      and any `options || choices` / member-form fallback.
    - the DynamoDB `config#fields` rows: enumerate which stored rows actually carry bare `choices`
      vs `options` (scope the C7 migration precisely).
  - **Produce a reconciliation table**: every hit → mapped to an existing F-item (F1–F8), OR flagged
    as a NEW old-path that must be added to the design's fallback-removal list (and thus a removal
    task), OR marked benign-with-reason. Record it under the spec (e.g. `old-paths-inventory.md`).
  - **Gate**: if the sweep finds an old path NOT covered by F1–F8, STOP and surface it — extend the
    design (new F-item + removal task) before proceeding. Discovery drives scope; the removals
    (tasks 4–9) must cover 100% of the confirmed inventory.
  - Files: read-only sweep (grep) + a committed `old-paths-inventory.md`; no product code changes.
  - VERIFY: the inventory lists every hit with its F-mapping/disposition; zero unmapped old paths
    remain (or each unmapped one has a new F-item + task). Cross-check the count against F1–F8.
  - _Requirements: 2.1, 2.3, 2.6, 2.7_ · _Components: scope-defining input for C1–C6 + C8_


- [x] 1. **Property 1: Bug Condition** — Unified Selectable-Vocabulary Round-Trip Asymmetry (extend the RED gate)
  - **CRITICAL**: write/extend these cases BEFORE any fix — they MUST FAIL on UNFIXED code; failure
    confirms the bug. **DO NOT fix the test or the code when it fails.** These cases encode the
    expected post-fix behavior and become the acceptance gate.
  - **GOAL**: surface counterexamples for all three kinds through the ONE read path.
  - **Scoped PBT approach**: the enum cases are deterministic (the real h-dcn bare-`choices` shape) —
    scope the properties to the concrete failing shapes for reproducibility.
  - Files: `sam/tests/e2e/test_enum_vocab_roundtrip_e2e.py` (EXTEND — the RED gate already has
    `test_roundtrip_symmetry_options_authored` GREEN and `test_roundtrip_symmetry_choices_only_legacy_row`
    RED); `sam/tests/e2e/test_config_fields_roundtrip_red.py` (STRENGTHEN
    `test_set_enum_choices_on_field_is_isolated`).
  - Extend the E2E gate with:
    - **NEW scope case** — author a scope-backed field; assert `options` is populated AND
      `FieldScope.values == [o.value for o in options]` (catches the `FieldScope(values=())`
      divergence). FAILS today.
    - **NEW reference case** — a `membership_type` field; assert resolved `options` == the CURRENT
      active catalog for that key, and that BOTH reads agree with each other AND with the current
      catalog — **NOT** `options == what was PUT` (the catalog lives elsewhere and changes
      independently; design G3 carve-out). FAILS today.
    - Confirm the enum options-authored case still PASSES and the enum bare-`choices` case still FAILS.
  - Strengthen spec-03's `test_set_enum_choices_on_field_is_isolated` from isolation-ONLY to:
    isolation (unchanged) + round-trip symmetry (PUT == GET via the editor read path) + the real
    stored shapes incl. the bare-`choices` / `options`-absent legacy row (R2.5).
  - **EXPECTED OUTCOME**: enum bare-`choices`, scope, and reference cases FAIL on unfixed code; document
    each counterexample (enum reads `[]`; scope `options` populated but `FieldScope(values=())`;
    reference inline options empty with no catalog population) — all one disease (no populated
    `options` from the declared source, read split by kind).
  - VERIFY: `cd sam && AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000 python -m pytest tests/e2e/test_enum_vocab_roundtrip_e2e.py tests/e2e/test_config_fields_roundtrip_red.py -q`
  - Mark complete when the cases are written, run, and the RED failures are documented.
  - _Requirements: 1.1, 1.2, 1.3, 2.2, 2.5, 2.6_ · _Components: acceptance gate for C1–C6_

- [x] 2. **Property 2: Preservation** — Already-Resolving & Separate-Concept Behavior (observation-first, BEFORE the fix)
  - **IMPORTANT**: follow the observation-first methodology — run UNFIXED code for the non-bug inputs,
    record the actual outputs, then write property-based tests asserting those outputs. These MUST
    PASS on unfixed code (they capture the baseline to preserve).
  - Files: `sam/tests/test_membership_writes_fieldconfig.py` (or the existing unit test for the seam) +
    the E2E gate from task 1.
  - Observe + lock in on UNFIXED code:
    - an options-authored selectable field renders IDENTICALLY in the editor read and the member-form
      read (R3.1);
    - `application_choices` (the public-form SUBSET) is unchanged — different concept (R3.2);
    - scope ACCESS resolution still reads `config#scope` / `ScopeConfig` — unchanged (DISPLAY-vocabulary
      fix only);
    - the spec-03 Change-Op guarantees (isolated, non-truncating, no whole-row replace) still hold.
  - PBT recommended: generate already-resolving selectable fields of each kind + `application_choices`
    usage; assert unchanged after the fix.
  - **EXPECTED OUTCOME**: all preservation cases PASS on unfixed code (baseline confirmed).
  - VERIFY: `cd sam && source ../backend/.venv/bin/activate 2>/dev/null; python -m pytest tests/test_membership_writes_fieldconfig.py -q` and the container-gated E2E preservation cases.
  - _Requirements: 3.1, 3.2, 3.3_ · _Components: preservation baseline for C1–C6_

## Phase 2 — C7 light migration FIRST (every live row carries `options` before reads tighten) — ~0.5 day  (R2.1)

- [x] 3. **C7** — Small, idempotent, targeted `choices`→`options` backfill (right-sized)
  - Real usage is LIMITED (essentially the one h-dcn `referral_source` row carries bare `choices`), so
    this is a SMALL idempotent targeted backfill — NOT a flag-day, NOT a PITR prod-copy rehearsal.
    With one row there is NO fix-forward fallback to reason about: **run the backfill and verify**
    (design dropped fix-forward). The C6 hard-gate all-tenant zero-un-migrated scan (task 9's blocking
    sub-step) is what CONFIRMS this backfill is complete before C6 fail-loud is enabled.
  - Files: a one-shot migration script under `sam/members/` or `scripts/` (e.g.
    `scripts/migrate_config_fields_choices_to_options.py`) + its unit test; committed fixture under
    `backend/tests/fixtures/` or the existing `sam/tests/fixtures/` if a sample row is needed.
  - Behavior: enumerate the few `config#fields` rows carrying bare `choices`; rewrite each to value-only
    `options` (`[{"value": v} for v in choices]`); drop `choices`. Idempotent — re-running is a no-op
    once a row has `options` and no `choices`. Goes through the spec-03 Change-Op path (no whole-row
    replace, R3.3). Must run BEFORE C6 fail-loud is enabled (task 9) and before task 12 flips C8 to
    BLOCKING, and the C6 hard-gate all-tenant scan (task 9 sub-step) must confirm zero un-migrated
    rows remain, so no live bare-`choices` row trips either guard.
  - **EXPECTED OUTCOME**: the real h-dcn `referral_source` row's 6 values survive as value-only
    `options`; re-run is a no-op.
  - VERIFY: read→migrate→read check against the REAL h-dcn row —
    `PYTHONPATH=backend/src backend/scripts/railway-db.sh python scripts/migrate_config_fields_choices_to_options.py --dry-run` is N/A (SAM plane); run the script's unit test
    `cd sam && python -m pytest tests/test_migrate_config_fields_choices_to_options.py -q`, then a live
    read→migrate→read against the local-DynamoDB h-dcn seed. Confirm idempotence on re-run.
  - _Requirements: 2.1_ · _Components: C7_

## Phase 3 — C1–C6 structural fixes (collapse to one `options`; read-assembly seam; fail-loud) — ~3 days

- [x] 4. **C4** — Read-assembly seam populates `options` uniformly; resolver stays PURE
  - Files: `sam/members/domain/_membership_writes_fieldconfig.py` (`get_field_config`,
    `_active_membership_type_options`, `_scope_vocab`, `_public_field_options` — drop the
    `field.choices` fallback, F10/N1b, PRESERVING the R3.2 public-subset filter);
    `sam/members/domain/_membership_catalog.py` (`CatalogMixin._serialize_field` — collapse the
    `membership_type` per-kind branch and drop the `elif field.choices` fallback, F9/N1 — this is the
    staff config-editor read serializer the seam's output flows through); `sam/members/domain/field_resolver.py`
    (UNCHANGED in purity — assert, do not modify, its no-catalog/no-DB contract).
  - Replace the one-off `_active_membership_type_options` reference merge + implicit per-kind handling
    with a UNIFORM pass at the seam: for every selectable field, set `options` from its INJECTED source
    — inline overlay (enum), the injected `_active_membership_type_options` catalog map (reference, F8),
    the injected `scope_vocab` dimension (scope). The pure `FieldResolver` is NOT given catalog/DB
    access and does NOT read `listMembershipTypes`/`catalogChoices`; `_as_variable_field` /
    `_apply_override` keep sourcing inline `options` purely. Reference/scope population lives at the
    seam only. The two SERIALIZERS of the seam's output — `_serialize_field` (staff editor read, F9)
    and `_public_field_options` (public-form read, F10) — serialize the ONE `options` the seam
    populated: collapse their per-kind branches and drop their `field.choices` fallbacks; the R3.2
    public-subset FILTER in `_public_field_options` is preserved (only the fallback is retired).
  - Change-with-tests: update `sam/tests/test_membership_writes_fieldconfig.py` /
    `sam/tests/test_field_config_endpoint.py` (and the paired test for `_serialize_field` —
    grep the test tree for `_serialize_field` / the catalog serializer) to assert uniform population,
    the collapsed per-kind branches, the dropped `choices` fallbacks (F9/F10), the preserved R3.2
    public subset, and the resolver's no-catalog dependency.
  - VERIFY: `cd sam && python -m pytest tests/test_membership_writes_fieldconfig.py tests/test_field_resolver.py tests/test_field_config_endpoint.py -q`
  - _Bug_Condition: isBugCondition(X) — declaredSourceExists AND assembledOptions empty, or reads disagree_
  - _Expected_Behavior: assembleSelectableOptions populates `options` from the injected source at ONE seam_
  - _Preservation: Preservation Requirements (P2); the R3.2 public-subset filter in `_public_field_options`_
  - _Requirements: 2.1, 2.6, 3.2_ · _Components: C4, F8, F9, F10_

- [x] 5. **C5** — Reader build collapses split handling to ONE `options`; scope `values` derived
  - Files: `sam/members/repository/_fields_overlay_reader.py` (`_build_overlay_field`, `_build_override`,
    `_build_options`); `sam/members/domain/_field_models.py` (`FieldScope`).
  - Drop the `options or choices` coalesce (F1), the separate-`choices` carry (F2), and the bare-string
    coercion / degrade-malformed-to-`None` branch (F3) — surface ONE `options` of canonical entries;
    an unexpected shape becomes a loud error (feeds C6). Build scope so `FieldScope.values` is the
    DERIVED projection `[o.value for o in options]` at a SINGLE point (F7) — never an independently
    stored copy — removing the `FieldScope(values=())` divergence by construction. Scope ACCESS
    resolution via `config#scope` / `ScopeConfig` is untouched (DISPLAY vocabulary only).
  - Change-with-tests: update `sam/tests/test_fields_overlay_reader*.py` (grep the test tree for
    `_build_override` / `_build_options` / `FieldScope`) to assert one `options`, no coalesce, raise on
    unexpected shape, and `values == [o.value for o in options]`.
  - VERIFY: `cd sam && python -m pytest tests/ -k "overlay_reader or field_models or field_scope" -q`
  - _Bug_Condition: scope `options` and `scope.values` tracked as two copies; legacy `choices` coalesce_
  - _Expected_Behavior: one `options`; `FieldScope.values` = derived projection at one point_
  - _Preservation: P2_
  - _Requirements: 2.1, 2.6_ · _Components: C5, F1, F2, F3, F7_

- [-] 6. **C1** — Frontend author/read ONE `options`, no kind branch
  - Files: `frontend/src/components/TenantAdmin/MembersConfig/fieldConfigChangeOps.ts` (drop `choices`
    from `DEFINITION_ATTRS` so the write emits ONLY `options`);
    `frontend/src/components/TenantAdmin/MembersConfig/MembersFieldModal.tsx` (`optionsToChoices` /
    `formFromResolvedField` seed from the single `options` the seam returns — identically for enum,
    reference, scope; no kind branch, F6); the member-form read path drops the `options or choices`
    fallback (F5);
    `frontend/src/components/TenantAdmin/MembersConfig/applicationChoiceSource.ts` (`resolveChoiceSource`
    — F11, LEGITIMATE SOURCE-SELECTOR CARVE-OUT, NO code change required. Confirmed by reading the
    file: `resolveChoiceSource` ONLY selects the declared source (reference→live catalog, scope→own
    `options`, enum→own `options`) and normalizes it via `optionsToChoices` — it does NOT branch the
    consumer READ SHAPE of the resulting `options`. Choosing the declared SOURCE this way mirrors the
    SAM seam's `declaredSource` and is allowed; it is NOT the forbidden "per-kind branch of the read
    shape in a consumer". Named here so the task-6 edit set is explicit about it. The needing-this
    carve-out is exactly WHY design DROPPED the C8 blocking rule (c) — a per-kind AST rule that must
    exempt this file (and the R3.2 subset filter) would false-positive; the "no per-kind read-shape
    branch in a consumer" invariant is instead covered by the targeted test in task 9b, which
    explicitly ALLOWS this source-selector. The forbidden pattern is per-kind branching of the
    resulting `options` READ shape, which this file does not do).
  - A propagated-but-empty source becomes a C6 error, not a silent empty.
  - Change-with-tests: update
    `frontend/src/components/TenantAdmin/MembersConfig/__tests__/fieldConfigChangeOps.test.ts` and
    `.../__tests__/MembersFieldModal.test.tsx` to assert `choices` is never written and the editor
    seeds from one `options`.
  - VERIFY: `cd frontend && npx vitest run src/components/TenantAdmin/MembersConfig/__tests__/fieldConfigChangeOps.test.ts src/components/TenantAdmin/MembersConfig/__tests__/MembersFieldModal.test.tsx`
  - _Bug_Condition: editor reads `options` only; member form has `options or choices` fallback_
  - _Expected_Behavior: one `options` read, no fallback, no consumer read-shape kind branch (source-selection in `resolveChoiceSource` is allowed, F11)_
  - _Preservation: P2; `resolveChoiceSource` source-selection behavior unchanged (F11 carve-out)_
  - _Requirements: 2.1, 2.6_ · _Components: C1, F5, F6, F11_

- [-] 7. **C2** — Write surface accepts `options` only, WITH source-integrity guards (W1/W2/W3); Change-Op + one-key contract preserved
  - Files: `sam/members/domain/config_fields_crud_service.py` (`FIELD_DEFINITION_ATTRS` drops `choices`;
    ADD the three write-side source-integrity guards W1/W2/W3 below);
    `sam/members/domain/config_write_service.py` (`_field_choice_values`, :542 — F12/N2: migrate
    `_collect(spec.get("options")) or _collect(spec.get("choices"))` to read `options` ONLY. This is a
    write-side validation helper that reads a field's vocabulary to validate an `application_choices`
    subset; after C7 backfills every live row and C2 drops `choices` on the write, the `choices`
    fallback is dead and the coalesce is MIGRATED away — preferred over a C8 allow-list carve-out so
    the C8 rule (b) stays clean).
  - Write accepts `options` only; storage key stays `overrides`, served under wire key `fixed_overrides`
    (one-key contract preserved, R3.3). Remains a Change-Op on a single path — no whole-row replace.
    `_field_choice_values` validates the `application_choices` subset against the ONE canonical
    `options` (R3.2 subset concept preserved — only its vocabulary SOURCE is tightened to `options`).
  - **NOTE — these three guards are NEW behavior the uncommitted C2 code must GAIN** (design Write-side
    invariants W1/W2/W3, Property 5). They did not exist before; C1 now seeds the editor from `options`
    IDENTICALLY for all kinds, so the write edge must stop a stale catalog/scope snapshot being
    re-frozen inline:
    - **W1 — reject an inline-`options` payload on a REFERENCE field** with a caller-safe 400. A
      reference field's `options` are a LIVE-catalog snapshot populated at the read seam (C4);
      persisting them inline re-freezes a stale copy — the two-copies disease on the WRITE side, a
      latent bug introduced by C1's identical seeding. Reference vocabulary lives in the catalog,
      never inline.
    - **W2 — reject inline options on a SCOPE-backed field** with a caller-safe 400 (chosen over a
      read-time precedence rule; keeps the stored row honest — no inline vocabulary competing with the
      `scope_vocab` dimension). This is Bug 2's shape.
    - **W3 — reject a save of an inline-source enum with ZERO `options`** (the write-edge invariant)
      with a caller-safe 400. This is what makes the read-time fail-loud discriminator unambiguous:
      a saved inline-source enum cannot have empty options ⇒ empty-on-read is ALWAYS the P3 asymmetry.
    - All three reject with a caller-safe 400 (steering 30 — no `str(e)` leak, full detail logged
      server-side).
  - **Deploy-skew ordering (hard constraint, design "Deployment ordering" §2).** The C2
    `choices`-rejection MUST NOT ship ahead of the deployed C1 frontend. The order is:
    **backend TOLERATES `choices` (accept-but-ignore) → frontend stops emitting `choices` (C1
    deployed) → backend REJECTS `choices` (C2 rejection enabled).** Any cached/older frontend still
    emitting `choices` would break if rejection shipped first.
  - Change-with-tests: update `sam/tests/test_config_fields_crud_service.py` to assert a `choices` write
    is no longer accepted and the Change-Op + `overrides`→`fixed_overrides` contract is intact; ADD a
    paired unit test per guard (W1 reference-inline-options → 400; W2 scope-inline-options → 400; W3
    inline-source enum with zero `options` → 400), each caller-safe; add/adjust the paired test for
    `_field_choice_values` (grep the test tree for `_field_choice_values` / `application_choices`
    validation) to assert it reads `options` only and the subset validation is unchanged in behavior.
  - VERIFY: `cd sam && python -m pytest tests/test_config_fields_crud_service.py -q` (incl. the W1/W2/W3
    rejection cases) plus the `_field_choice_values` paired test
  - _Bug_Condition: write emits vocabulary under `choices` / `options` / both; subset validator coalesces `options or choices`; a reference/scope snapshot re-frozen inline; an inline-source enum saved empty_
  - _Expected_Behavior: write accepts one `options`; subset validator reads `options` only; Change-Op path preserved; W1/W2/W3 reject inline-options-on-reference, inline-options-on-scope, and zero-options inline enum with a caller-safe 400_
  - _Preservation: spec-03 Change-Op guarantees (P2, R3.3); `application_choices` subset validation behavior unchanged (R3.2)_
  - _Requirements: 2.1, 2.4, 2.6, 3.2, 3.3_ · _Components: C2, F12, P5 (W1/W2/W3)_

- [-] 8. **C3** — Write-edge duplicate-`value` guard → caller-safe 400 before any repo call
  - Files: `sam/members/domain/config_fields_crud_service.py` (before any repository call).
  - Reject an `options` list containing a duplicate `value` via `ConfigFieldsCrudError`
    (subclasses `ValueError`); the edge maps it to a caller-safe 400 — no `str(e)` leak, full detail
    logged server-side (steering 30).
  - Change-with-tests: add a duplicate-`value` rejection case to
    `sam/tests/test_config_fields_crud_service.py`.
  - VERIFY: `cd sam && python -m pytest tests/test_config_fields_crud_service.py -k duplicate -q`
  - _Bug_Condition: duplicate `value` stored verbatim (no content validation)_
  - _Expected_Behavior: duplicate `value` → caller-safe 400 before repo call_
  - _Preservation: P2_
  - _Requirements: 2.4_ · _Components: C3 (P4)_

- [-] 9. **C6** — Fail-loud boundary on the ASYMMETRY only; per-consumer blast-radius split (staff-raise / public-drop+alert)
  - Files: `sam/members/domain/_membership_writes_fieldconfig.py` (the seam from task 4, incl.
    `_public_field_options` — F10: the dropped `choices` fallback means a declared-but-unpropagated
    source reaches the uniform fail-loud rather than silently coercing via `field.choices`);
    `sam/members/domain/_membership_catalog.py` (`CatalogMixin._serialize_field` — F9: with the
    `choices` fallback dropped, a present-source-but-empty-`options` field raises here on the
    ASYMMETRY instead of degrading to `list(field.choices)` / `None`); supporting error type as needed.
  - Raise a LOUD, caller-safe, diagnosable error ONLY when a field's DECLARED source EXISTS but its
    vocabulary did NOT propagate into `options` (the P3 asymmetry). **Discriminator wording (design
    C6 / write-edge invariant):** fail-loud fires on the asymmetry per the WRITE-EDGE INVARIANT — a
    saved inline-source enum CANNOT have empty options (W3), so empty-on-read is ALWAYS the asymmetry
    (an un-migrated / bare-`choices` legacy row that failed to propagate). For a reference, a fetch
    ERROR (source unreachable) raises, but an empty RESULT (fetch succeeded, zero active types on a
    new tenant) does NOT raise (G5). The `choices`-present-but-`options`-empty sentinel the current
    seam keys off is the MIGRATION-WINDOW encoding only, retired after C7.
  - **Per-consumer blast-radius SPLIT (design "Blast-radius policy" — this is NEW behavior; the
    currently-implemented seam raises UNIFORMLY and the public-drop/alert path is NOT there yet):**
    - **STAFF config-editor read**: FAIL THE FIELD LOUDLY — the seam's raise propagates. The editor
      is exactly where a config bug must surface; a staff admin seeing the loud error is the intended
      signal.
    - **PUBLIC application path**: FAIL THE ONE FIELD, not the whole page — the PUBLIC serializer
      (`_public_field_options`) CATCHES the seam's per-field raise, DROPS that one field from the
      served config, and emits an error LOG + METRIC + ALERT (same correlation id as the server-side
      detail); the page is still served. One misconfigured field must never black out a tenant's
      public application form.
  - **Do NOT** raise on a legitimately-empty source (a scope dimension with zero values yet, a
    newly-created not-yet-populated field, an EMPTY active catalog on a new tenant — a fetch that
    SUCCEEDED with zero active types, distinct from a fetch error) or a reference whose catalog
    correctly populates `options` — those stay valid in-progress states (G5). No per-kind exemption.
    Generic client message; full detail logged under a correlation id (steering 30).
  - Change-with-tests: add to `sam/tests/test_membership_writes_fieldconfig.py` (plus the
    `_serialize_field` paired test):
    - **staff-raise cases** — the asymmetry raises on the staff config-editor read (un-migrated /
      bare-`choices` row, inline-source enum empty-on-read, reference catalog FETCH ERROR);
    - **public-drop + alert cases** — the SAME asymmetry on the public path drops just that field,
      still serves the page, and emits an error log + metric + alert (same correlation id);
    - **G5 must-NOT-raise cases** — empty active catalog on a new tenant (fetch ok, zero active
      types = empty RESULT), a scope dimension with ZERO values yet, a newly-created
      not-yet-populated field, and the reference fetch-error-RAISES-vs-empty-result-does-NOT
      distinction.
  - VERIFY: `cd sam && python -m pytest tests/test_membership_writes_fieldconfig.py -k "fail_loud or asymmetry or empty_source or staff_raise or public_drop or alert or g5" -q` plus the `_serialize_field` paired test
  - _Bug_Condition: declared source present (write-edge invariant) but `options` empty (asymmetry)_
  - _Expected_Behavior: staff read raises caller-safe error on the asymmetry; public path drops the one field + logs/metrics/alerts; never degrade to empty (P3)_
  - _Preservation: legitimately-empty source does NOT raise (G5); R3.2 public subset preserved_
  - _Requirements: 2.3, 2.6_ · _Components: C6, F4, F9, F10_

  - [ ] 9a. **C6 hard gate — all-tenant zero-un-migrated scan (BLOCKING, before fail-loud enabled)**
    - **BLOCKING deployment step** gating C6 fail-loud (design "Hard gate before C6 goes live" /
      "Deployment ordering" §4). Fail-loud must NOT be enabled until an all-tenant scan confirms ZERO
      un-migrated bare-`choices` rows remain — not "essentially one row" by assumption. A single
      missed un-migrated row is an OUTAGE under fail-loud: staff read raises; public read drops a REAL
      field. The staff-raise / public-drop split (task 9) bounds the blast radius but does NOT remove
      this gate.
    - Behavior: a precise read→count scan across EVERY tenant's `config#fields` rows; PASS iff zero
      rows still carry bare `choices` (i.e. C7 backfill is confirmed complete tenant-wide). Runs as a
      blocking step in Deployment ordering before C6 fail-loud goes live — an explicit scan, not an
      inference.
    - Files: a scan script/command under `sam/members/` or `scripts/` (e.g.
      `scripts/scan_config_fields_un_migrated_choices.py`) + its unit test.
    - VERIFY: run the scan across all tenants' `config#fields` (local-DynamoDB seed + the real h-dcn
      row) — `cd sam && python scripts/scan_config_fields_un_migrated_choices.py` exits non-zero / FAILs
      if any bare-`choices` row remains, zero otherwise; plus its unit test
      `cd sam && python -m pytest tests/test_scan_config_fields_un_migrated_choices.py -q`.
    - _Requirements: 2.3_ · _Components: C6 (hard gate), C7 (confirms backfill completeness)_

  - [ ] 9b. **No-per-kind-branch serializer test (covers DROPPED C8 rule (c))**
    - Design dropped C8 blocking rule (c) (the per-field-KIND AST branch) — it needed two carve-outs
      (R3.2 subset filter, F11 source-selector) → false-positive risk. The invariant it protected is
      now covered by a TARGETED TEST instead of a blocking AST rule.
    - Add a targeted unit/integration test asserting `_serialize_field` (F9) and
      `_public_field_options` (F10) resolve the ONE canonical `options` from the seam with NO per-kind
      read-shape branch. The R3.2 public-SUBSET FILTER (`application_choices` ⊆ `options`) in
      `_public_field_options` and the F11 frontend source-selector (`resolveChoiceSource`) remain
      LEGITIMATE and are explicitly ALLOWED by this test — it asserts absence of the forbidden
      per-kind read-shape branch, not absence of the subset projection or source selection.
    - Files: `sam/tests/test_membership_writes_fieldconfig.py` / `sam/tests/test_membership_catalog*.py`
      (grep the test tree for `_serialize_field` / `_public_field_options`).
    - VERIFY: `cd sam && python -m pytest tests/ -k "no_per_kind_branch or serialize_field or public_field_options" -q`
    - _Requirements: 2.6, 2.7_ · _Components: C4 (F9/F10 collapse), test-based replacement for dropped C8 rule (c)_

## Phase 4 — C8 mechanical guard (increment 2, REPORT-ONLY first; three rules a/b/d) — ~1 day  (R2.7)

- [ ] 10. **C8 (report-only, increment 2)** — Extend the AST guard with THREE anti-reintroduction rules (a)(b)(d)
  - Files: `scripts/check_sam_config_crud.py` (EXTEND — real code only, not comments/docstrings;
    allow-list discipline; never `--no-verify`); `sam/tests/test_check_sam_config_crud.py` (planted-
    violation tests).
  - Add THREE BLOCKING rules, each with a PLANTED-VIOLATION test (plant → guard fails; clean tree →
    passes):
    (a) a `choices` key on the config#fields WRITE path; (b) an `options or choices` /
    `choices or options` fallback expression in reader/resolver OR a read of `field.choices` as a
    fallback vocabulary SOURCE in a serializer — this rule covers `_serialize_field` (F9),
    `_public_field_options` (F10), AND the write-side `_field_choice_values` coalesce (F12, which is
    why F12 is MIGRATED to `options`-only rather than allow-listed); (d) `FieldScope.values` populated
    independently of `options` (not the derived projection).
  - **Rule (c) is DROPPED** (design "Rule (c) is DROPPED from the blocking guard"). The proposed
    per-field-KIND AST rule already needed TWO documented carve-outs (the R3.2 public-SUBSET FILTER in
    `_public_field_options`, and the frontend source-selector `resolveChoiceSource` / F11) — a rule
    that needs carve-outs to avoid flagging legitimate code will false-positive and erode trust in the
    guard. The invariant it was meant to protect ("the serializers have NO per-kind read-shape
    branch") is instead COVERED BY the targeted no-per-kind-branch TEST (task 9b), with the R3.2
    subset filter and the F11 source-selector explicitly allowed. F11 stays a documented no-change
    source-selector carve-out; F9/F10's per-kind branches are removed by C4 (task 4) and verified by
    task 9b's test, not by a blocking AST rule.
  - **Rollout REPORT-ONLY first** — emit findings without failing the build; the flip to BLOCKING is
    task 12 (increment 2's second step), only after increment 1 (C7 + C1–C6) lands and the gate is
    green (G6).
  - VERIFY: `cd /home/peter/projects/myAdmin && python -m pytest sam/tests/test_check_sam_config_crud.py -q` (planted-violation tests for rules a/b/d ONLY) and run the guard report-only against the tree.
  - _Requirements: 2.7_ · _Components: C8 (report-only, three rules a/b/d)_

## Phase 5 — Verify the fix GREEN (fix checking + preservation) — ~0.5 day

- [ ] 11. Fix for enum-vocabulary round-trip & no-silent-fallbacks — verification

  - [ ] 11.1 **Property 1: Expected Behavior** — extended symmetry gate GREEN (enum + scope + reference)
    - **IMPORTANT**: re-run the SAME cases from task 1 — do NOT write new tests. When they pass, the
      unified-vocabulary behavior is confirmed.
    - Per-kind assertion (design G3): reads ALWAYS agree; enum strict inline PUT==GET; scope `options`
      derived-from `scope_vocab` AND `scope.values == [o.value...]`; reference `options` == CURRENT
      active catalog (NOT == what was PUT).
    - **EXPECTED OUTCOME**: enum bare-`choices`, scope, and reference cases now PASS; the strengthened
      spec-03 isolation test PASSES.
    - VERIFY: `cd sam && AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000 python -m pytest tests/e2e/test_enum_vocab_roundtrip_e2e.py tests/e2e/test_config_fields_roundtrip_red.py -q`
    - _Requirements: 2.1, 2.2, 2.6_

  - [ ] 11.2 **Property 2: Preservation** — preservation holds; spec-03 suite still green
    - **IMPORTANT**: re-run the SAME tests from task 2 — do NOT write new tests.
    - Confirm: options-authored fields render identically in both reads; `application_choices`
      unchanged; scope ACCESS resolution via `config#scope` / `ScopeConfig` unchanged; the full spec-03
      E2E suite still green (no regressions).
    - **EXPECTED OUTCOME**: all preservation + spec-03 cases PASS.
    - VERIFY: `cd sam && python -m pytest tests/ -q` then
      `AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000 python -m pytest tests/e2e/ -q`
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ] 11.3 Real h-dcn round-trip through the editor read path
    - Drive a final read→(author/edit)→read of the real h-dcn `referral_source` vocabulary through the
      config editor read path; confirm the 6 values survive as `options` and both reads agree.
    - VERIFY: live local-DynamoDB h-dcn seed, container-gated E2E; manual editor read confirmation.
    - _Requirements: 2.1, 2.2_

## Phase 6 — C8 flip to BLOCKING (increment 2, LAST) + checkpoint — ~0.5 day  (R2.7, G6)

- [ ] 12. **C8 (blocking, increment 2)** — Flip the guard (rules a/b/d) to BLOCKING once the tree is clean (G6)
  - Files: `scripts/check_sam_config_crud.py` / its pre-commit + CI wiring (steering 43).
  - ONLY after increment 1 — C7 (task 3) + C1–C6 (tasks 4–9, incl. the C6 hard-gate scan 9a) — has
    landed and the extended gate is GREEN (tasks 11.x): clear the baseline, then flip report-only →
    BLOCKING. Flipping earlier would redden valid in-flight states (a half-authored field, a scope
    dimension not yet populated, an un-migrated row). A new sanctioned site is a REVIEWED allow-list
    addition, never a `--no-verify` suppression.
  - VERIFY: plant each of the THREE violations (a)(b)(d) in a temp commit → guard FAILS the build;
    revert → guard passes. Proves the guard actually blocks, not just exists. Confirm the clean tree
    passes AFTER the F9/F10/F12 removals land — i.e. no surviving `field.choices` fallback in
    `_serialize_field` / `_public_field_options` / `_field_choice_values` trips rule (b). Rule (c) is
    DROPPED, so the serializer no-per-kind-branch invariant is confirmed by task 9b's test, NOT by a
    planted guard violation; the R3.2 public-subset FILTER in `_public_field_options` and the F11
    source-selector (`resolveChoiceSource` / `applicationChoiceSource.ts`) are legitimate and, with
    rule (c) gone, there is no blocking rule for them to trip.
  - _Requirements: 2.7_ · _Components: C8 (blocking, three rules a/b/d)_

- [ ] 13. Checkpoint — ensure all tests pass
  - Full SAM unit suite + container-gated E2E (extended symmetry gate + strengthened isolation +
    spec-03 suite) + frontend vitest + the guard tests all green; the real h-dcn round-trip verified.
    Ask the user if questions arise.

---

## Task Dependency Graph
```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1"] },
    { "id": 1, "tasks": ["1", "2"] },
    { "id": 2, "tasks": ["3"] },
    { "id": 3, "tasks": ["4", "5"] },
    { "id": 4, "tasks": ["6", "7", "8", "9"] },
    { "id": 5, "tasks": ["10"] },
    { "id": 6, "tasks": ["11.1", "11.2", "11.3"] },
    { "id": 7, "tasks": ["12", "13"] }
  ]
}
```
Notes: the waves above are **increment 1 = the fix (C7 + C1–C6, waves 0–4 tasks 0.1–9)** then
**increment 2 = the guard (C8, waves 4–7 tasks 10/12)** — C8 is the only increment-2 work.
**Wave 0 is harness-first — prove RED (enum/scope/reference) before any fix.** Wave 1 is the
C7 light migration FIRST, so every live row carries `options` before the reads tighten. Wave 2 lands
the read-assembly seam (C4) + the reader collapse / scope-derivation (C5) — the core. Wave 3 lands the
frontend (C1), the write surface + write-side guards W1/W2/W3 (C2), the duplicate guard (C3), and the
fail-loud with the per-consumer blast-radius split (C6, task 9: staff-raise / public-drop+alert).
Task 9's sub-steps run within wave 4: **9a is the BLOCKING C6 hard gate (all-tenant zero-un-migrated
scan) that must PASS before C6 fail-loud is enabled**, and 9b is the no-per-kind-branch serializer
test (test-based replacement for the dropped C8 rule (c)). Wave 4 also adds the C8 guard REPORT-ONLY
(task 10, three rules a/b/d). Wave 5 verifies the fix GREEN (extended symmetry gate + preservation +
spec-03 suite + real h-dcn round-trip). **Wave 6/7 flips C8 to BLOCKING LAST (G6) and checkpoints** —
the enforcement that makes C1–C7 un-regressable.

## Definition of Done (steering 40)
- The extended E2E symmetry gate is GREEN for all three kinds through the ONE read path — enum (strict
  inline PUT==GET), scope (`options` + `FieldScope.values == [o.value...]`), reference (`options` ==
  current active catalog; both reads agree with each other and the catalog, NOT with the PUT) — with
  the G3 per-kind assertion (R2.2, R2.6).
- The strengthened spec-03 `test_set_enum_choices_on_field_is_isolated` (isolation + round-trip
  symmetry + bare-`choices`/`options`-absent shape) is GREEN (R2.5).
- ONE canonical `options` end-to-end; `choices` retired; the real h-dcn `referral_source` vocabulary
  survives the round-trip through the editor read path (R2.1); C7 migration idempotent — run and
  verify, NO fix-forward fallback (design dropped fix-forward). The C6 hard-gate all-tenant
  zero-un-migrated-rows scan (task 9a) PASSES as a blocking step before C6 fail-loud is enabled.
- Every silent fallback removed (F1–F12 — F9 `_serialize_field`, F10 `_public_field_options`
  fallback with the R3.2 subset preserved, F12 write-side `_field_choice_values` migrated to
  `options`-only; F11 `resolveChoiceSource` is a documented source-selector carve-out, no removal);
  "declares selectable but source didn't propagate" raises a uniform, caller-safe, diagnosable error
  on the ASYMMETRY only (the write-edge-invariant discriminator) — a legitimately-empty source does
  NOT raise (R2.3, R2.6, G5). The fail-loud is split by CONSUMER: the STAFF config-editor read raises
  the field loudly; the PUBLIC application path drops the ONE field and emits an error
  log + metric + alert while still serving the page (C6 blast-radius policy).
- Write-side source-integrity guards (W1/W2/W3, Property 5) enforced in C2: reject an inline-`options`
  payload on a REFERENCE field (W1) and on a SCOPE-backed field (W2), and reject a save of an
  inline-source enum with ZERO `options` (W3, the write-edge invariant) — each with a caller-safe 400
  (R2.4, R2.6).
- Duplicate-`value` write rejected with a caller-safe 400 before any repo call (R2.4).
- The pure `FieldResolver` is UNCHANGED in purity — no catalog/DB read added; population lives at the
  read-assembly seam only.
- Preservation holds: options-authored fields render identically in both reads; `application_choices`
  unchanged; scope ACCESS resolution via `config#scope`/`ScopeConfig` unchanged; spec-03 Change-Op
  guarantees preserved; full spec-03 E2E suite still green (R3.1, R3.2, R3.3).
- The C8 AST guard (increment 2) is EXTENDED with THREE blocking rules (a)(b)(d), each with a
  planted-violation test, rolled out report-only → BLOCKING only AFTER increment 1 (C7 + C1–C6) lands
  and the gate is green; a planted violation fails the build (R2.7, G6). Rule (c) is DROPPED (it needed
  two carve-outs → false-positive risk); the serializer no-per-kind-branch invariant it protected is
  covered by the targeted no-per-kind-branch TEST (task 9b) instead, with the R3.2 subset filter and
  the F11 source-selector explicitly allowed.
- Change-with-tests honored throughout (steering 34/30/39): every behavioral edit updated its paired
  test in the same task.

## Reminders (spec-03 discipline)
- **Write the exploration cases (task 1) BEFORE implementing the fix.** Run them on UNFIXED code and
  confirm they FAIL — that failure proves the bug exists. Do not fix the test or the code when it fails.
- **Follow observation-first for preservation (task 2):** observe UNFIXED behavior, then assert it; the
  preservation tests must PASS on unfixed code before the fix lands.
- **Do NOT flip C8 to BLOCKING until C7 + C1–C6 have landed and the gate is green (task 12, LAST).**

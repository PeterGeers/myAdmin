# Implementation Plan

Phase 1 — Catalog Backbone — tasks. Implements `design.md` against `requirements.md`.

## Overview

Each task is additive and non-breaking (R2); after each, the full existing SAM + Flask + frontend
field-model suites must stay green. Tasks are ordered so each lands safely on its own.

Planes: SAM = `sam/members/...` (pytest via `sam/pytest.ini`); Flask = `backend/src` +
`backend/tests` (pytest via `backend/pytest.ini`). Do NOT import `sam.*` into `backend/src`
(steering 30/31 cross-plane boundary) — Flask-side conformance tests read JSON + a transcribed view
and compare, never import the SAM catalog.

**Testing conventions (per `40-spec-workflow.md` "include testing per phase" + `34`/`33`).** Each
phase below states its testing requirement inline (the `_test_` tasks). All tests follow
`34-backend-testing.md` (naming `test_{function}_{scenario}_{expected}`; SAM tests under
`sam/tests/` run via `sam/pytest.ini`; Flask unit tests under `backend/tests/unit/` with the
`mock_db`/`mock_env` isolation fixtures, never a real DB) and `33-frontend-testing.md` for any
frontend-touching i18n-resolution test. The **Change-With-Tests Contract** (`30`/`32`) applies: any
behavior/markup change updates its paired test in the SAME task. A phase is not done until its
stated tests are green.

## Tasks

### 1. Base functional-group set (R4, R5)
> *Testing (R5):* 1.3 is this phase's test — the base-group closure guard.

- [ ] **1.1 Define `BASE_FUNCTIONAL_GROUPS`** in the SAM domain (`attribute_catalog.py` or a small
  sibling imported by it): the frozen tuple of `FunctionalGroup(key,label{nl,en},order)` for
  `personal`(1), `address`(2), `membership`(3), `administrative`(4) (design §4). Pure, import-time
  safe. _(R5.1)_
- [ ] **1.2 Reconcile the seed fixture** so `seed_overlay.SEED_FUNCTIONAL_GROUPS` is defined in terms
  of `BASE_FUNCTIONAL_GROUPS` (base keys come from the one constant; seed-only extras like `group_a`
  stay seed/test data). One base-group definition, not two. _(R5.2)_
- [ ] **1.3 Base-group closure test** (`sam/tests/test_attribute_catalog.py`): every
  `FIXED_FIELDS` + `CALCULATED_FIELDS` field's `default_functional_group()` is a key in
  `BASE_FUNCTIONAL_GROUPS`. Fails if a registry field names a group absent from the base set. _(R5.2)_

### 2. The attribute vocabulary (R1)
> *Testing (R1/R7):* covered by phase 3's drift + completeness tests (3.3, 3.4) once the inventory
> is built on this vocabulary.

- [ ] **2.1 Define `AttributeApplies`, `AttributeSpec`, `CatalogField`, `AttributeCatalog`
  dataclasses** in `sam/members/domain/attribute_catalog.py` (design §2). Frozen, pure. _(R1.1)_
- [ ] **2.2 Author the attribute vocabulary** — one `AttributeSpec` per attribute the model carries
  today (design §2 table): `key, type, required, label, visible, order, functional_group, choices,
  options, show_when, member_number_format, calculated_from`, plus the Phase-3-declared
  `scope_binding` + `alias`. Set `value_type`, `required`, `applies_to`, `tenant_authorable`,
  `required_when` per the table. _(R1.1, R1.2, R1.5, R8.1)_
- [ ] **2.3 Encode the enum rule** — `choices` and `options` carry
  `required_when=(("type","enum"),)` so an enum field must declare values, mirroring
  `_reject_invalid_overlay` (document the scope-dimension-backed exception in the `note`). _(R1.3)_
- [ ] **2.4 Mark `scope_binding` + `alias` as declared-only** — set a `note` stating they are wired
  in Phase 3 (resolver/render), not Phase 1. _(R8.1, R8.2, R8.3)_

### 3. The field inventory (computed, drift-guarded) (R1.4, R7)
> *Testing (R1/R7):* 3.3 (inventory ⇄ registry drift guard), 3.4 (vocabulary completeness),
> 3.5 (self-validation raises) — `sam/tests/test_attribute_catalog.py`.

- [ ] **3.1 Implement `build_attribute_catalog()`** — iterate `FIXED_FIELDS` then
  `CALCULATED_FIELDS`, projecting each into a `CatalogField` via the SAME accessors the resolver uses
  (`dotted_key()`, `type.value`, `required`, `label`, `default_functional_group()`, `order`,
  `read_only` for calculated). Re-type NO field names/labels. Assemble `AttributeCatalog(attributes,
  fields, functional_groups=BASE_FUNCTIONAL_GROUPS, label_convention="i18n-keys+tenant-inline-override")`.
  _(R1.4, R1.6, R3.4)_
- [ ] **3.2 Import-time self-validation** in `build_attribute_catalog()` (or module import): raise
  `ValueError` on a duplicate `AttributeSpec.key`, a `CatalogField.functional_group` not in the base
  group keys, or an enum-rule inconsistency — same fail-fast discipline as `fixed_fields.py`. _(R7.1)_
- [ ] **3.3 Drift-guard test** (`test_attribute_catalog.py`): catalog field inventory ==
  `{f.dotted_key() for f in FIXED_FIELDS} | {c.dotted_key() for c in CALCULATED_FIELDS}`; each
  `CatalogField`'s platform-fixed attributes (`type`, `required` for fixed, `read_only` for calc,
  base `functional_group`, `label`) == the registry's. Adding/renaming a registry field without
  updating the catalog fails. _(R1.4, R7.2)_
- [ ] **3.4 Vocabulary-completeness test**: every attribute the `FixedField` / `CalculatedField` /
  `OverlayField` / `FixedFieldOverride` dataclasses expose has a matching `AttributeSpec` (no
  attribute the model carries is missing from the vocabulary). _(R1.1, R7.2)_
- [ ] **3.5 Self-validation raises test**: inject an inconsistent catalog (dup key / dangling group)
  in a test and assert `build_attribute_catalog()` raises. _(R7.1)_

### 4. Base-group-aware reference validation (the one resolver-adjacent change) (R4.2, R5.4)
> *Testing (R2/R4/R5):* 4.2 (resolver output unchanged — the non-breaking guard), 4.3 (base-key
> resolves / dangling still raises), 4.4 (group merge rule) — extend `sam/tests/test_field_resolver.py`.

- [ ] **4.1 Extend the group set used for reference validation** so the resolver validates a field's
  `functional_group` against `BASE_FUNCTIONAL_GROUPS` ⊕ the tenant's authored catalog, instead of
  only the authored catalog (design §4). A field referencing a base key (e.g. `administrative`) is
  reference-VALID even when the tenant authored no catalog. Keep the empty-authored-catalog path
  non-raising for everything that passes today (strictly preservation-safe). _(R4.2, R5.3, R5.4)_
- [ ] **4.2 Resolver regression test** (`test_field_resolver.py`): `resolve()` output is byte-for-
  byte identical to before for existing fixtures (same fields, order, groups) — R2.1. _(R2.1, R2.4)_
- [ ] **4.3 Base-key-resolves test**: a tenant with NO authored functional-group catalog but a field
  (or override) referencing a base key resolves WITHOUT `OverlayError`; a dangling (non-base,
  non-authored) key still raises. _(R4.2, R5.4)_
- [ ] **4.4 Group merge-rule test**: resolved groups = base ⊕ tenant, tenant key wins on collision,
  base keys fill the rest; a base group is always present (no hiding in Phase 1). _(R5.3)_

### 5. The i18n label model — Option (b) (R3)
> *Testing (R3):* 5.3 (value/label split), 5.4 (tenant-label save round-trip, `backend/tests/unit/`
> with `mock_db`), 5.5 (missing-locale fallback), 5.6 (add-a-language proof) — follow `33`/`34`.

- [ ] **5.1 Define the shipped-label key scheme (conform to the i18n convention) + seed the resource
  namespace** — adopt keys under the `admin` namespace per `TRANSLATION_KEY_CONVENTIONS.md` /
  `32-frontend-ui.md`: `admin:membersConfig.field.<fieldKey>` / `.group.<groupKey>` /
  `.enum.<fieldKey>.<optionValue>` (category path camelCase; the key/value segment stays the
  canonical snake_case field key — the one documented deviation, R3.4). CONFIRM the exact
  namespace/category against the conventions doc before coding (new `admin:membersConfig.*` category
  vs overloading an existing one). SEED the `admin` i18n files (nl + en) for every base key from the
  existing `{nl,en}` values in `FIXED_FIELDS` / `CALCULATED_FIELDS` / base groups / built-in enum
  options, so day-one behavior is unchanged and a third language is a new resource file only. Keep
  the registry `{nl,en}` dicts as the fallback/default behind the keys (do NOT delete in Phase 1).
  _(R3.1, R3.7, R2; conforms to `32` + i18n conventions)_
- [ ] **5.2 Implement the resolve-with-precedence rule** — label text =
  `tenant_inline[locale] ?? resource(key)[locale] ?? fallback(locale)`. Land it so the SERVED label
  stays an inline `{nl,en,…}` dict (serializer resolves resource defaults into the dict, then
  overlays tenant inline values) → `GET /members/field-config` response shape unchanged;
  `resolveLabel(label, lang)` on the frontend unchanged. _(R3.3, R2.2)_
- [ ] **5.3 Enum value/label split guardrail** — ensure an enum option's canonical `value` is never
  translated or language-keyed; only its `label` is per-language (resource key for shipped, inline
  dict keyed by `value` for tenant). Add a test that a stored `value` is stable across locales and a
  label change in one locale does not touch `value`. _(R3.4)_
- [ ] **5.4 Tenant-label save: per-locale inputs → inline dict** — the Flask members-config save
  folds the editor's per-locale inputs (generalized from the old `label_en`/`label_nl`) into the
  stored `{nl, en, …}` dict keyed by locale, for custom fields / groups / enum options. Round-trip
  test: per-locale inputs → stored dict → served dict. _(R3.2)_
- [ ] **5.5 Missing-locale fallback test** — a label with no value for the active locale falls back
  `active → en → nl → key`, never blank; order documented in the artifact. _(R3.5)_
- [ ] **5.6 Add-a-language proof test** — add a `de` resource entry for ONE base key and assert it
  resolves with NO domain code change; a tenant custom field with no `de` label falls back per 5.5.
  Documents the stated impact (R3.6). _(R3.6)_
- [ ] **5.7 Record the convention in the artifact** —
  `label_convention="i18n-keys+tenant-inline-override"` + the fallback order + the key scheme on the
  catalog. _(R3.7)_

### 6. Flask ⇄ catalog conformance (no cross-plane import) (R7.2)
> *Testing (R7 / `36` rule 5):* 6.1 IS the test — a cross-plane vocabulary guard, the `36` rule-5
> pattern (one source, agreement enforced by a test), mirroring `members_config_validation`'s
> field-key guard. `backend/tests/unit/`, no `sam.*` import.

- [ ] **6.1 Editor-schema conformance test** (`backend/tests/unit/`): read
  `backend/src/config/members_parameters.json` and a locally-transcribed view of the catalog's
  `tenant_authorable` attribute keys (transcribed, NOT imported from `sam.*`), and assert the editor
  field-def attribute keys ⊆ the authorable catalog attributes. Guards the two from diverging
  (`analysis.md` 2.4). Add a note pointing at `attribute_catalog.py` as the source of truth to
  re-transcribe from on change. _(R7.2, R7.3)_

### 7. Display-ordering contract (R6)

- [ ] **7.1 Document the display-ordering contract** in `design.md`/the catalog `note`: display
  position = `(functional_group.order, field.order, field.key)`; distinct from the resolver's
  storage-bucket sort; derived by the consumer from existing served data (no new response field).
  _(R6.1, R6.2, R6.3, R6.5)_
- [ ] **7.2 Ordering determinism test**: given base groups + fields, computing display position by
  `(group.order, field.order, key)` is stable and ties break by `key`. _(R6.4)_

### 8. Module-neutral shape + the `38` steering file (R9)

- [ ] **8.1 Shaping review** — review the catalog model (`AttributeSpec`/`CatalogField`/
  `AttributeCatalog`, the functional-group model, the i18n rule, the drift-guard) and confirm NO
  Members-only concept is baked into the SHAPE (Members-specific DATA — the field list, base-group
  values, `members.*` resource keys — legitimately stays Members-specific). Record the confirmation
  in the design decision log. _(R9.1)_
- [ ] **8.2 Confirm no shared library is built** — the catalog stays in `sam/members/domain/`; no
  `sam/shared` field-catalog extraction in Phase 1. _(R9.2)_
- [ ] **8.3 Write `38-sam-module-field-config.md`** — new steering file, front-matter
  `inclusion: auto`, in `.kiro/steering/`. A THIN guidance file capturing the six recommended-
  practice points from design §10 (catalog-first; group→field→attribute + ordering; no view/
  analytics param objects; first-class versioned+observable projection; single authoring surface;
  i18n Option (b)) + the rule-of-three extraction boundary. Point at Members as the reference impl
  and at this spec folder for detail; do NOT copy their content (facts-in-one-place). _(R9.3)_
- [ ] **8.4 Register `38` in `00-index.md`** — add it to the `3x` "Coding conventions" row and to
  the `auto` load-behavior table; add a one-line rationale (full-stack/next-module guidance, always
  discoverable), mirroring how 35/36/37 are described. _(R9.4)_
- [ ] **8.5 Cross-reference from `35`/`37` (light)** — add a one-line pointer from
  `35-sam-module-architecture-sam.md` (next SAM modules) and/or `37-shared-building-blocks.md` to
  `38` so a module author finds it, without duplicating its content. _(R9.4)_
- [ ] **8.6 Confirm R9 adds no runtime surface** — R9 is a shaping + docs requirement; verify it
  introduced only the steering file + a design note, no code behavior change. _(R9.5)_

### 9. Verification + close-out

- [ ] **9.1 Run the SAM suite**: `cd sam && pytest tests/test_attribute_catalog.py
  tests/test_field_resolver.py tests/test_members_resolved_field_surface.py -q` (via `sam/pytest.ini`).
  All green. _(R2.4)_
- [ ] **9.2 Run the Flask suite** for the touched files: the fold round-trip + the schema-conformance
  test + `test_members_config_validation.py`. All green. _(R2.4)_
- [ ] **9.3 Confirm non-breaking** — `GET /members/field-config` response shape unchanged (diff a
  serialized sample before/after); stored `members.field_overlay` shape unchanged; no data migration.
  _(R2.1, R2.2, R2.3)_
- [ ] **9.4 Update the impact analysis** — tick `impact-analysis.md` §9 Phase 1 steps 4 + 5 as done,
  with a one-line pointer to this spec folder; note R9 added steering `38`.
- [ ] **9.5 End-user-documentation close-out** (per `Common/end-user-documentation/` — "every
  feature needs a manual section"): Phase 1 is a backbone/model change with NO end-user-visible
  surface of its own (the authoring UI is Phase 3), so no manual page is due this phase. Record the
  obligation as carried forward to the Phase 3 authoring-UI spec (a Tenant-Admin "configure member
  fields" manual section). Confirm this is a deliberate deferral, not an omission. _(40-spec-workflow
  "Writing Design" docs clause)_
- [ ] **9.6 Governance definition-of-done** (per `00-index.md` / `40-spec-workflow.md`): confirm the
  steering the phase changed is updated — `38-sam-module-field-config.md` added and registered in
  `00-index.md` (tasks 8.3/8.4), with `35`/`37` cross-refs (8.5). A phase is not complete until its
  steering is updated.

### 10. CI/CD + ship (per `43-cicd-deploys.md`)

> **What this phase actually deploys.** Phase 1 is additive and non-runtime-breaking (R2). The code
> touches: `sam/members/domain/**` (the catalog + the one resolver-adjacent change), `backend/src`
> + `backend/tests` (the i18n fold + conformance test), one frontend i18n resource file
> (`frontend/**`), and steering/spec docs. Per the branch→env + deploy-path contract in `43`:
> - `sam/members/**` changes → **`deploy-sam-members.yml`** fires on push to `test`/`main` (data
>   acct `506221081911`, via GitHub OIDC `NonprofitDeployRole` — no stored AWS secrets).
> - `frontend/**` (the i18n resource file) → **`deploy-frontend.yml`** fires on push to `main` only
>   (TEST frontend is the local dev server; no hosted TEST target).
> - `backend/**` and `.kiro/**` do not trigger a SAM/frontend deploy; the Flask app deploys on its
>   own rails (Railway), unaffected by this phase.

- [ ] **10.1 Feature branch, never push to `test`/`main` directly** — do the work on a
  `spec/members-config-phase1-catalog` branch. A feature branch never deploys; only CodeQL +
  GitGuardian run per-PR today (Backend/Frontend CI are `disabled_manually`; the nightly
  `full-test-suite.yml` is the standing lint/test gate). _(43 "Branch → environment contract" +
  "Non-negotiables")_
- [ ] **10.2 Run the paired tests locally before the PR** (scoped, not a full-suite run) — the SAM
  `test_attribute_catalog.py` / `test_field_resolver.py` and the Flask fold + conformance tests
  (tasks §9). Change-with-tests contract; a full-suite dispatch is only warranted if blast radius
  grows. _(43 "Bugfix scope note"; `34`)_
- [ ] **10.3 PR into `test`; clear security gates** — CodeQL **and** GitGuardian green on the PR
  (fix root cause, never suppress). On merge to `test`, confirm `deploy-sam-members.yml` runs
  `--config-env test` and the `test-sam-members` stack settles `UPDATE_COMPLETE`. _(43 "Deploy
  workflows", "Quality gates")_
- [ ] **10.4 Verify in live TEST, not just units** — exercise `GET /members/field-config` against
  the deployed TEST stack and confirm the response is unchanged (R2.2) and the base-group-aware
  resolution behaves (R5.4). This is the "exercised in live TEST" precondition for promotion. _(43
  promote runbook step 1)_
- [ ] **10.5 Preview the prod changeset** — `sam deploy --config-env prod --no-execute-changeset`
  for the Members stack; confirm NO unexpected `Replacement: True` on stateful resources (this phase
  adds no infra/table change, so expect none). _(43 promote runbook step 3)_
- [ ] **10.6 Promote `test → main` via ONE PR, MERGE COMMIT (not squash)** — preserve phase history
  on `main`; treat the merge as a production release. The merge fires `deploy-sam-members.yml`
  (`--config-env prod`, stack `sam-members`) and, because the i18n resource file is under
  `frontend/**`, `deploy-frontend.yml` (production SPA → Pages). Watch each run to `success` /
  `UPDATE_COMPLETE`. _(43 promote runbook steps 2, 5, 6; "A merge to `main` IS a production deploy")_
- [ ] **10.7 Pool trigger is NOT touched** — note for the record: this phase changes no PreTokenGen
  / Cognito wiring, so no identity-account (`344561557829`) manual step applies. _(43 "Deploys touch
  the DATA account only")_

## Task Dependency Graph

Phases are mostly sequential on the catalog artifact, with two independent legs (i18n §5 and the
steering/docs §8) that can proceed in parallel once the catalog exists.

```
1 (base groups)
└─> 2 (attribute vocabulary)
      └─> 3 (field inventory + drift guard)   ── depends on 1 (base-group closure) + 2 (vocabulary)
            ├─> 4 (base-group-aware reference validation)   ── depends on 1 + 3
            ├─> 6 (Flask ⇄ catalog conformance test)        ── depends on 2 (authorable attrs)
            └─> 7 (display-ordering contract)                ── depends on 1 (group order) + 3

5 (i18n Option b)        ── independent leg; depends on 1 (base-group labels) + 3 (field inventory)
8 (module-neutral + steering 38)  ── independent leg; depends on 2 + 3 existing (reviews the shape)

9 (verification + close-out)   ── depends on ALL of 1–8
10 (CI/CD + ship)              ── depends on 9 (green locally) before any PR/deploy
```

Critical path: **1 → 2 → 3 → 4 → 9 → 10**. Legs **5** and **8** join at **9**. No task in a later
phase may be checked done before its listed dependencies.

## Notes

### Requirements coverage

| Requirement | Tasks |
|---|---|
| R1 (catalog exists, first-class) | 2.1, 2.2, 2.3, 3.1, 3.3, 3.4 |
| R2 (additive, non-breaking) | 4.2, 9.1, 9.2, 9.3 |
| R3 (i18n = Option b: resource keys + tenant inline override) | 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7 |
| R4 (functional group = first-class) | 1.1, 4.1, 4.3, 4.4 |
| R5 (base functional-group set) | 1.1, 1.2, 1.3, 4.1, 4.3, 4.4 |
| R6 (explicit display ordering) | 7.1, 7.2 |
| R7 (self-validating, drift-guarded) | 3.2, 3.3, 3.4, 3.5, 6.1 |
| R8 (scope-binding + alias declared) | 2.2, 2.4 |
| R9 (module-neutral shape + steering `38`) | 8.1, 8.2, 8.3, 8.4, 8.5, 8.6 |

### Deferred to later phases (recorded, not done here)

- Serving the catalog to the authoring UI + building the group → field → attribute UI — **Phase 3**
  (`impact-analysis.md` §9 step 11).
- Wiring `scope_binding` into the resolver + folding `alias`/analytics into field attributes at
  runtime — **Phase 3** (steps 9–10).
- Collapsing fixed/overlay → one list + provenance badge; "only `member_id` is fixed" (4.1) —
  **Phase 3** (high blast radius).
- Retiring `view_contexts` + the pagination model — **Phase 2**.
- Role-gating of a functional group; letting a tenant hide a base group — deferred (design D8).

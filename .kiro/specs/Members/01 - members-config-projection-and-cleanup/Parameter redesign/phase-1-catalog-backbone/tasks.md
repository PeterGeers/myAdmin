# Implementation Plan

## Overview

Phase 1 — Catalog Backbone of the Members config redesign (`impact-analysis.md` §9 steps 4+5).
Produces ONE new domain artifact — a canonical attribute catalog derived from the existing SAM
registries — settles functional-group identity + base set + ordering, and sets the i18n label
model. Every task is additive and non-breaking (R2): `FieldResolver.resolve` output and the
`GET /members/field-config` contract stay unchanged.

Planes: SAM = `sam/members/...` (pytest via `sam/pytest.ini`); Flask = `backend/src` +
`backend/tests` (pytest via `backend/pytest.ini`). Do NOT import `sam.*` into `backend/src`
(steering 30/31 cross-plane boundary) — Flask-side conformance tests read JSON + a transcribed view
and compare. Tests follow `34-backend-testing.md` (naming `test_{function}_{scenario}_{expected}`,
`mock_db`/`mock_env` isolation) and `33-frontend-testing.md`; the Change-With-Tests Contract
(`30`/`32`) applies. The implementation is organized in waves — tasks within a wave can proceed in
parallel; each wave completes before the next starts.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 1, "tasks": ["1", "2"] },
    { "id": 2, "tasks": ["3"] },
    { "id": 3, "tasks": ["4", "5", "6", "7"] },
    { "id": 4, "tasks": ["8"] },
    { "id": 5, "tasks": ["9", "10"] }
  ]
}
```

Critical path: 1 → 2 → 3 → 4 → 9 → 10. Wave 3 fans out (reference validation, i18n, Flask
conformance, ordering) once the catalog inventory (task 3) exists; the steering/docs task (8) and
i18n (5) are independent legs that converge at verification (9); ship (10) follows green local tests.

## Tasks

### Wave 1: Catalog foundations (base groups + attribute vocabulary)

---

- [x] 1. Base functional-group set (R4, R5)
  - [x] 1.1 Define `BASE_FUNCTIONAL_GROUPS` in the SAM domain (`attribute_catalog.py` or a small sibling): frozen tuple of `FunctionalGroup(key,label{nl,en},order)` for personal(1), address(2), membership(3), administrative(4) (design §4). Pure, import-time safe. _(R5.1)_
  - [x] 1.2 Reconcile the seed fixture so `seed_overlay.SEED_FUNCTIONAL_GROUPS` is defined in terms of `BASE_FUNCTIONAL_GROUPS` (seed-only extras like `group_a` stay seed/test data). One base-group definition, not two. _(R5.2)_
  - [x] 1.3 Base-group closure test (`sam/tests/test_attribute_catalog.py`): every `FIXED_FIELDS` + `CALCULATED_FIELDS` field's `default_functional_group()` is a key in `BASE_FUNCTIONAL_GROUPS`. _(R5.2)_

---

- [x] 2. The attribute vocabulary (R1)
  - [x] 2.1 Define `AttributeApplies`, `AttributeSpec`, `CatalogField`, `AttributeCatalog` dataclasses in `sam/members/domain/attribute_catalog.py` (design §2). Frozen, pure. _(R1.1)_
  - [x] 2.2 Author the attribute vocabulary — one `AttributeSpec` per attribute the model carries today (design §2 table): key, type, required, label, visible, order, functional_group, choices, options, show_when, member_number_format, calculated_from, plus the Phase-3-declared scope_binding + alias. _(R1.1, R1.2, R1.5, R8.1)_
  - [x] 2.3 Encode the enum rule — `choices`/`options` carry `required_when=(("type","enum"),)` so an enum field must declare values, mirroring `_reject_invalid_overlay` (document the scope-dimension-backed exception). _(R1.3)_
  - [x] 2.4 Mark `scope_binding` + `alias` as declared-only — a `note` stating they are wired in Phase 3 (resolver/render), not Phase 1. _(R8.1, R8.2, R8.3)_

---

### Wave 2: The field inventory (computed, drift-guarded)

---

- [x] 3. Build + guard the field inventory (R1.4, R7)
  - [x] 3.1 Implement `build_attribute_catalog()` — iterate `FIXED_FIELDS` then `CALCULATED_FIELDS`, projecting each into a `CatalogField` via the SAME accessors the resolver uses (`dotted_key()`, `type.value`, `required`, `label`, `default_functional_group()`, `order`, `read_only`). Re-type NO field names/labels. Assemble `AttributeCatalog(..., label_convention="i18n-keys+tenant-inline-override")`. _(R1.4, R1.6, R3.4)_
  - [x] 3.2 Import-time self-validation in `build_attribute_catalog()`: raise `ValueError` on a duplicate `AttributeSpec.key`, a `CatalogField.functional_group` not in the base group keys, or an enum-rule inconsistency — same fail-fast discipline as `fixed_fields.py`. _(R7.1)_
  - [x] 3.3 Drift-guard test (`test_attribute_catalog.py`): catalog field inventory == `{f.dotted_key() for f in FIXED_FIELDS} | {c.dotted_key() for c in CALCULATED_FIELDS}`; each `CatalogField`'s platform-fixed attributes == the registry's. _(R1.4, R7.2)_
  - [x] 3.4 Vocabulary-completeness test: every attribute the `FixedField`/`CalculatedField`/`OverlayField`/`FixedFieldOverride` dataclasses expose has a matching `AttributeSpec`. _(R1.1, R7.2)_
  - [x] 3.5 Self-validation raises test: inject an inconsistent catalog (dup key / dangling group) and assert `build_attribute_catalog()` raises. _(R7.1)_

---

### Wave 3: Resolver validation, i18n, conformance, ordering (parallel)

---

- [x] 4. Base-group-aware reference validation — the one resolver-adjacent change (R4.2, R5.4)
  - [x] 4.1 Extend the group set used for reference validation so the resolver validates a field's `functional_group` against `BASE_FUNCTIONAL_GROUPS` ⊕ the tenant's authored catalog (design §4). A base-key reference is valid even with no authored catalog. Keep the empty-catalog path non-raising for everything that passes today. _(R4.2, R5.3, R5.4)_
  - [x] 4.2 Resolver regression test (`test_field_resolver.py`): `resolve()` output is byte-for-byte identical to before for existing fixtures. _(R2.1, R2.4)_
  - [x] 4.3 Base-key-resolves test: a tenant with NO authored catalog but a field/override referencing a base key resolves WITHOUT `OverlayError`; a dangling non-base key still raises. _(R4.2, R5.4)_
  - [x] 4.4 Group merge-rule test: resolved groups = base ⊕ tenant, tenant key wins on collision, base keys fill the rest; a base group is always present. _(R5.3)_

---

- [x] 5. The i18n label model — Option (b) (R3)
  - [x] 5.1 Define the shipped-label key scheme (conform to the i18n convention) + seed the resource namespace — keys under the `admin` namespace per `TRANSLATION_KEY_CONVENTIONS.md`/`32`: `admin:membersConfig.field.<fieldKey>` / `.group.<groupKey>` / `.enum.<fieldKey>.<optionValue>`. CONFIRM the exact namespace/category before coding. Seed the `admin` i18n files (nl+en) from the existing `{nl,en}` registry values; keep those dicts as the fallback. _(R3.1, R3.7, R2)_
  - [x] 5.2 Implement the resolve-with-precedence rule — label = `tenant_inline[locale] ?? resource(key)[locale] ?? fallback(locale)`. Served label stays an inline `{nl,en,…}` dict so the response shape + `resolveLabel` are unchanged. _(R3.3, R2.2)_
  - [x] 5.3 Enum value/label split guardrail — an enum option's canonical `value` is never translated or language-keyed; only its `label` is per-language. Test a stored `value` is stable across locales. _(R3.4)_
  - [x] 5.4 Tenant-label save: per-locale inputs → inline dict — the Flask save folds per-locale inputs into the stored `{nl,en,…}` dict. Round-trip test: inputs → stored → served. _(R3.2)_
  - [x] 5.5 Missing-locale fallback test — a label with no value for the active locale falls back `active → en → nl → key`, never blank. _(R3.5)_
  - [x] 5.6 Add-a-language proof test — add a `de` resource entry for ONE base key and assert it resolves with NO domain code change; a tenant field with no `de` label falls back per 5.5. _(R3.6)_
  - [x] 5.7 Record the convention in the artifact — `label_convention="i18n-keys+tenant-inline-override"` + the fallback order + key scheme on the catalog. _(R3.7)_

---

- [x] 6. Flask ⇄ catalog conformance (no cross-plane import) (R7.2)
  - [x] 6.1 Editor-schema conformance test (`backend/tests/unit/`): read `backend/src/config/members_parameters.json` and a locally-transcribed view of the catalog's `tenant_authorable` attribute keys (NOT imported from `sam.*`); assert the editor field-def attribute keys ⊆ the authorable catalog attributes. The `36` rule-5 cross-plane vocabulary guard. _(R7.2, R7.3)_
you start 
---

- [x] 7. Display-ordering contract (R6)
  - [x] 7.1 Document the display-ordering contract in `design.md`/the catalog note: display position = `(functional_group.order, field.order, field.key)`; distinct from the resolver's storage-bucket sort; derived by the consumer, no new response field. _(R6.1, R6.2, R6.3, R6.5)_
  - [x] 7.2 Ordering determinism test: computing display position by `(group.order, field.order, key)` is stable and ties break by `key`. _(R6.4)_

---

### Wave 4: Module-neutral shape + steering 38

---

- [x] 8. Module-neutral shape + the `38` steering file (R9)
  - [x] 8.1 Shaping review — confirm NO Members-only concept is baked into the catalog model SHAPE (Members-specific DATA stays Members-specific). Record in the design decision log. _(R9.1)_
  - [x] 8.2 Confirm no shared library is built — the catalog stays in `sam/members/domain/`; no `sam/shared` extraction in Phase 1. _(R9.2)_
  - [x] 8.3 Write `38-sam-module-field-config.md` — new steering file, front-matter `inclusion: auto`. A THIN guidance file: catalog-first; group→field→attribute + ordering; no view/analytics param objects; first-class versioned+observable projection; single authoring surface; i18n Option (b); + the rule-of-three extraction boundary. Point at Members as the reference impl. _(R9.3)_
  - [x] 8.4 Register `38` in `00-index.md` — add to the `3x` row + the `auto` load-behavior table with a one-line rationale. _(R9.4)_
  - [x] 8.5 Cross-reference from `35`/`37` (light) — a one-line pointer to `38`, no duplicated content. _(R9.4)_
  - [x] 8.6 Confirm R9 adds no runtime surface — only the steering file + a design note, no code behavior change. _(R9.5)_

---

### Wave 5: Verification + ship

---

- [x] 9. Verification + close-out
  - [x] 9.1 Run the SAM suite: `cd sam && pytest tests/test_attribute_catalog.py tests/test_field_resolver.py tests/test_members_resolved_field_surface.py -q`. All green. _(R2.4)_
  - [x] 9.2 Run the Flask suite for the touched files: the fold round-trip + the schema-conformance test + `test_members_config_validation.py`. All green. _(R2.4)_
  - [x] 9.3 Confirm non-breaking — `GET /members/field-config` response shape unchanged (diff a serialized sample); stored `members.field_overlay` shape unchanged; no data migration. _(R2.1, R2.2, R2.3)_
  - [x] 9.4 Update the impact analysis — tick `impact-analysis.md` §9 Phase 1 steps 4 + 5 as done, pointer to this spec folder; note R9 added steering `38`.
  - [x] 9.5 End-user-documentation close-out (per `Common/end-user-documentation/`): Phase 1 has NO end-user-visible surface (UI is Phase 3), so no manual page is due; record the obligation as carried forward to the Phase 3 authoring-UI spec. Deliberate deferral, not an omission.
    - **Close-out (DONE — deliberate deferral, tracked):** Phase 1 is a backbone/model change (the derived attribute catalog + base functional-group set + i18n label model) with NO end-user-visible surface of its own — the tenant-facing authoring UI is Phase 3 (`impact-analysis.md` §9 step 11). So NO end-user manual page (`docs/docs/**`) is due this phase; the "every feature needs a manual section" obligation (`40-spec-workflow.md` / `Common/end-user-documentation/`) is DEFERRED to the Phase 3 authoring-UI spec, which owns the surface the manual would document. Checked: `.kiro/specs/Common/end-user-documentation/` has no pending-obligations register to log into, so the close-out is recorded in design.md decision log **D15** + here. No manual was fabricated for an unbuilt UI. _(deliberate deferral, tracked — not an omission)_
  - [x] 9.6 Governance definition-of-done (per `00-index.md`/`40-spec-workflow.md`): confirm `38-sam-module-field-config.md` added + registered in `00-index.md` (8.3/8.4) with `35`/`37` cross-refs (8.5). A phase is not complete until its steering is updated.
    - **Governance DoD — MET (verified 2026-10-13, read-the-files evidence).** All four checks pass; the phase's steering changes are in place, satisfying the `00-index.md` "Governance discipline" clause ("a step isn't done until the steering it changes is updated") / the `40-spec-workflow.md` definition-of-done:
      1. **`38` exists + thin guidance (8.3) ✓** — `.kiro/steering/38-sam-module-field-config.md` is present with valid front-matter `inclusion: auto` and the thin "proven tenant-configurable field pattern" content (7 rules: catalog-first + drift guard, group→field→attribute with derived ordering, no view/analytics param objects, versioned/observable projection, one authoring surface, i18n Option (b), rule-of-three extraction boundary) + a Reference-implementation section pointing at `sam/members/domain/attribute_catalog.py`, `field_resolver.py`, and this spec folder — it points, it does not restate.
      2. **`00-index.md` registers `38` three ways (8.3/8.4) ✓** — (a) the `3x` "Coding conventions" layer-table row lists `38-sam-module-field-config.md`; (b) the `auto` load-behavior table row lists `38`; (c) the "Rationale for the non-obvious modes" list carries the one-line `38` rationale bullet ("thin cross-module guidance … relevant whenever a SAM module's field config is designed … thin pointer file, so the always-on cost is low").
      3. **`35`/`37` carry light one-line cross-refs to `38` (8.5) ✓** — `35-sam-module-architecture-sam.md` (fixed-vs-variable-fields bullet) points to `38` for the "tenant-configurable field-model pattern (catalog-first, group→field→attribute, derived ordering, i18n)"; `37-shared-building-blocks.md` ("Relationship to the other steering files") points to `38` for the same pattern + the module-neutral/rule-of-three extraction note. Both are genuine one-line pointers, no duplicated content.
      4. **DoD satisfied ✓** — new file (8.3) + index registration 3× (8.3/8.4) + cross-refs from `35`/`37` (8.5) are all present, so Phase 1's steering IS updated. Recorded in design.md decision log **D16** + here. _(verification only; no code/tests)_

---

- [ ] 10. CI/CD + ship (per `43-cicd-deploys.md`)
  - [x] 10.1 Feature branch `spec/members-config-phase1-catalog`, never push to `test`/`main` directly. A feature branch never deploys; only CodeQL + GitGuardian run per-PR today (Backend/Frontend CI `disabled_manually`; nightly `full-test-suite.yml` is the standing gate). _(43 branch→env + non-negotiables)_
  - [x] 10.2 Run the paired tests locally before the PR (scoped, not a full-suite run) — the SAM + Flask tests from wave 5. _(43 bugfix-scope note; `34`)_
  - [x] 10.3 PR into `test`; clear security gates (CodeQL + GitGuardian green, fix root cause). On merge to `test`, confirm `deploy-sam-members.yml` runs `--config-env test` and `test-sam-members` settles `UPDATE_COMPLETE`. _(43 deploy workflows)_
  - [x] 10.4 Verify in live TEST, not just units — exercise `GET /members/field-config` on the deployed TEST stack; confirm response unchanged (R2.2) and base-group-aware resolution behaves (R5.4). _(43 promote step 1)_
  - [x] 10.5 Preview the prod changeset — `sam deploy --config-env prod --no-execute-changeset`; confirm NO unexpected `Replacement: True` (this phase adds no infra/table change). _(43 promote step 3)_
  - [x] 10.6 Promote `test → main` via ONE PR, MERGE COMMIT (not squash) — the merge fires `deploy-sam-members.yml` (`--config-env prod`, stack `sam-members`) and, for the `frontend/**` i18n file, `deploy-frontend.yml`. Watch each run to `success`/`UPDATE_COMPLETE`. _(43 promote steps 2, 5, 6)_
  - [x] 10.7 Pool trigger is NOT touched — no PreTokenGen/Cognito wiring change, so no identity-account manual step applies. _(43 "Deploys touch the DATA account only")_

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
| R9 (module-neutral shape + steering 38) | 8.1, 8.2, 8.3, 8.4, 8.5, 8.6 |

### Deferred to later phases (recorded, not done here)

- Serving the catalog to the authoring UI + building the group → field → attribute UI — Phase 3 (`impact-analysis.md` §9 step 11).
- Wiring `scope_binding` into the resolver + folding `alias`/analytics into field attributes at runtime — Phase 3 (steps 9–10).
- Collapsing fixed/overlay → one list + provenance badge; "only `member_id` is fixed" (4.1) — Phase 3 (high blast radius).
- Retiring `view_contexts` + the pagination model — Phase 2.
- Role-gating of a functional group; letting a tenant hide a base group — deferred (design D8).

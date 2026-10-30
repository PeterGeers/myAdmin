# Old-Paths Inventory — Enum-Vocabulary Round-Trip & No-Silent-Fallbacks (task 0.1)

> **Purpose (task 0.1).** The fallback-removal list **F1–F8** in `design.md` was built from the
> seams traced during design, NOT an exhaustive codebase sweep. This document is the sweep that
> PROVES the list complete before any removal (tasks 4–9), so no old path slips through. It is a
> **read-only** discovery artifact — no product code was changed.
>
> **Planes swept:** `sam/**/*.py` (SAM plane), `frontend/src/**/*.{ts,tsx}`, and the DynamoDB
> `config#fields` stored shapes (via the committed fixtures that mirror the real `h-dcn` row).
>
> **Method:** `grep`/`ripgrep` for every pattern named in the task, then each hit was read in
> context and classified. Build-artifact copies under `sam/members/.aws-sam/build/**` are
> excluded from the live-source analysis (see the note at the end) — they are generated copies of
> the same source files, not independent code paths.
>
> **Requirements:** 2.1, 2.3, 2.6, 2.7 · **Components:** scope-defining input for C1–C6 + C8.

---

## Gate outcome (read this first)

**The sweep found TWO live old-path locations that F1–F8 do NOT explicitly name.** Both are the
same disease (`options → choices` coalesce and/or a per-field-KIND branch in a vocabulary
consumer) but sit in files the design/tasks did not list for removal. Per the task's gate, these
must be surfaced to extend the design before the removals (tasks 4–9) proceed:

| New | Location | Pattern | Proposed disposition |
|-----|----------|---------|----------------------|
| **N1** | `sam/members/domain/_membership_catalog.py` `CatalogMixin._serialize_field` (≈ lines 300–309) | A per-field-KIND branch (`membership_type` special-case) **plus** an `options → choices` fallback (`elif field.choices is not None: payload["options"] = list(field.choices)`) — on the **staff config-editor read serializer**, which is the OUTPUT of the C4/F8 read-assembly seam (`get_field_config` calls `_serialize_field` for every field, `_membership_writes_fieldconfig.py:87`). | **Extend design**: add a new F-item (sibling to F8) and name this file in the C4 + C6 removal tasks (4, 9). This is literally the config-editor read-serializer the bug's "editor reads `options` only" symptom flows through; collapsing the read-assembly seam is incomplete if this per-kind branch + `choices` fallback survives here. |
| **N2** | `sam/members/domain/config_write_service.py` `_field_choice_values` (line 542) | `_collect(spec.get("options")) or _collect(spec.get("choices"))` — an `options → choices` coalesce in a **write-side validation helper** (reads a field's vocabulary to validate an `application_choices` subset). | **Add F-item + task coverage** OR **mark benign-with-reason** (see analysis under N2). It is an `options or choices` coalesce of exactly the F1/C8-rule-(b) shape, so even if its runtime impact is benign after C7, the C8 guard rule (b) would flag it unless it is either migrated to read `options` only or added to the C8 allow-list with a documented reason. **Decision required from the user.** |

**Everything else in the sweep maps cleanly to an existing F-item, to a sanctioned C-component
edit already in the task list, or is benign-with-reason (documented below).** No OTHER unmapped
old path remains.

---

## Section A — SAM plane (`sam/**/*.py`)

### A1. `_fields_overlay_reader.py` — the live reader (F1, F2, F3, F7)

This is the ONE live implementation of the overlay/override field build. (`projection_config_reader.py`
does **not** duplicate it — it imports `_FieldOverlayReadMixin` from this file and composes it, so
there is a single source of truth. The `_build_options` / `_build_override` matches that appeared
under `projection_config_reader.py` in the raw grep were the `.aws-sam/build/**` artifact copies
only.)

| Hit (file:line, live source) | Pattern | F-item / disposition |
|---|---|---|
| `_fields_overlay_reader.py:388–390` `_build_override`: `_build_options(options) or _build_options(choices)` | `options or choices` coalesce on the FIXED-override path | **F1** — seam reads declared source only; legacy `choices` migrated (C7) or loud error (C6). Removed by **task 5 (C5)**. |
| `_fields_overlay_reader.py:331` `choices = spec.get("choices")` + `:317 _build_overlay_field` carries `choices=...` as a separate attr | `_build_overlay_field` carries `choices` as a separate vocabulary attr | **F2** — one `options` via the seam. Removed by **task 5 (C5)**. |
| `_fields_overlay_reader.py:179–228` `_build_options`: coerces a bare string to `EnumOption`; malformed/empty → `None` (degrade-to-None) | bare-string coercion + degrade-malformed-to-`None` | **F3** — canonical entries only; unexpected shape → loud error (C6). Changed by **task 5 (C5)** + **task 9 (C6)**. |
| `_fields_overlay_reader.py:259–270` `_build_field_scope` → `FieldScope(values=...)` (independently stored values) | scope `values` stored as an independent copy | **F7** — `values` becomes the DERIVED projection `[o.value for o in options]` at one seam point. Changed by **task 5 (C5)** (model `_field_models.py` `FieldScope`). |
| `_fields_overlay_reader.py:183` docstring mentioning `options or choices` fallback | comment only | **Benign** — a docstring, not executable code. Will be updated when F1/F2 land (change-with-tests / docs), not an independent old path. The C8 guard explicitly ignores comments/docstrings. |

### A2. `field_resolver.py` — the PURE resolver (F4)

| Hit (file:line) | Pattern | F-item / disposition |
|---|---|---|
| `field_resolver.py:318–367` `_as_variable_field`: sources `options` from inline `of.options` only; the scope-vocab branch sets `choices` from `scope_vocab[key]` | inline `options` only, no other source (silently → `None` for a bare-`choices` variable field) | **F4** — resolver STAYS pure (inline only); the read-assembly seam populates reference/scope; a propagated-but-empty source is loud, not empty. Asserted-not-modified in purity by **task 4 (C4)**; fail-loud by **task 9 (C6)**. |
| `field_resolver.py:183–268` `_apply_override`: `choices = tuple(o.value for o in options)` when `options` present (keeps bare `choices` coherent) | derives `choices` from `options` (coherence) | **F4-adjacent / benign-preserving** — this is the FIXED path deriving the bare list FROM `options` (the correct direction — options is canonical). Stays pure. Not a hiding fallback; no removal needed beyond the `choices` retirement that C5/C7 drive. The resolver continuing to also expose a derived `choices` is acceptable during migration; the C8 rule targets `options or choices` (the WRONG direction), not `choices` derived from `options`. |
| `field_resolver.py:337,444` `of.type is FieldType.ENUM` guards (scope-dimension-backed enum) | per-field-KIND branch (ENUM) | **Benign-with-reason** — this is the resolver's S5j scope-dimension rule (design D1a), a pure-resolver concern that is NOT a vocabulary-source branch in a CONSUMER. The design keeps the resolver pure and unchanged (task 4 asserts, does not modify). The C8 rule (c) targets a per-kind branch in a vocabulary CONSUMER where the uniform seam `options` must be used — not the resolver's internal scope-binding classification. Confirm this stays off the C8 rule-(c) target set. |

### A3. `_membership_writes_fieldconfig.py` — the read-assembly seam (F8)

| Hit (file:line) | Pattern | F-item / disposition |
|---|---|---|
| `_membership_writes_fieldconfig.py:85,232,431–444` `_active_membership_type_options` merged one-off; `get_field_config` resolves then attaches catalog options | reference inline `options` empty, active catalog merged one-off outside a uniform path | **F8** — READ-LAYER assembly populates `options` from the injected `_active_membership_type_options` map (NOT a resolver catalog read). Changed by **task 4 (C4)**. |
| `_membership_writes_fieldconfig.py:370` `_public_field_options`: `if field.type is not FieldType.ENUM` + `membership_type` dotted-key special-case (lines 342–369) | per-field-KIND branch in the PUBLIC-form read serializer | **Maps to C4/C6 intent but on the PUBLIC path.** The public-form read (`_serialize_public_field` / `_public_field_options`) is the OTHER consumer in the bug (the member-form read with the hidden fallback). Task 6 (C1/F5) removes the FRONTEND member-form fallback; this SAM-side public serializer's per-kind branch should be collapsed by the same uniform-seam principle. **Flag for confirmation**: tasks name `_membership_writes_fieldconfig.py` for C4, so this file IS in scope, but the specific `_public_field_options` per-kind branch is not called out. Recommend confirming it is covered by the C4 uniform pass + C8 rule (c), or carve it out with a reason (the public SUBSET is a legitimately different projection per R3.2). |
| `_membership_writes_fieldconfig.py:372,388` `field.options is None and field.choices is None` / `if field.choices is not None` | reads `field.choices` as a fallback vocabulary source in `_public_field_options` | **Same as the N1 disease, public-path variant.** Tie to the C4/C6 collapse; ensure the C8 rule (b) covers it or it is allow-listed with the R3.2 subset reason. Flag for confirmation. |

### A4. Write-surface definition attrs (C2)

| Hit (file:line) | Pattern | F-item / disposition |
|---|---|---|
| `config_fields_crud_service.py:119–128` `FIELD_DEFINITION_ATTRS` contains `"choices"` AND `"options"` | write path accepts BOTH `choices` and `options` | **Sanctioned C2 edit** — **task 7 (C2)** drops `"choices"` from `FIELD_DEFINITION_ATTRS`. Already named in the task list. |
| `config_write_service.py:542` `_field_choice_values`: `_collect(options) or _collect(choices)` | `options or choices` coalesce (write-side validation) | **N2 — NEW, unmapped.** See gate table / N2 analysis below. |

### A5. Benign SAM hits (vocabulary is a DIFFERENT concept, or consumer is fixed-field validation)

These matched the grep but are NOT the config#fields display-vocabulary round-trip under fix:

| Hit | Why benign |
|---|---|
| `application_choices.py:71` `field.choices or ()` | `application_choices` (public-form SUBSET) is explicitly a SEPARATE concept, **R3.2 / out of scope** — NOT retired. The `or ()` is a None-guard on a bare list, not an `options↔choices` name coalesce. |
| `fixed_fields.py:129,662–677` `FixedField.choices` membership-validation (`value not in fld.choices`) | Fixed-field ENUM VALUE validation against the platform base `choices` — a value-correctness check, not a vocabulary-SOURCE read. `FixedField.choices` is the platform base list, not the tenant overlay vocabulary. Unchanged. |
| `_membership_writes_validation.py:385,399` `field.type is not FieldType.ENUM or not field.choices` | Member-record WRITE value validation (is the submitted value in the field's allowed set) — not a config read serializer. Not the round-trip. |
| `_membership_writes_crud.py`, `_membership_writes_application.py`, `membership_type_catalog.py`, `_membership_catalog.py` CRUD methods, `members_repository.py`, `table_design.py`, `hdcn_backfill.py`, `error_codes.py` — the many `membership_type` hits | These are the membership-type CATALOG CRUD + reference-integrity INFRASTRUCTURE (list/get/save/deactivate membership types, record→catalog validation). They are the SOURCE the seam injects for reference fields (F8), not per-kind branches in a display-vocabulary consumer. Unchanged (the catalog is the declared source, correctly external to the pure resolver). |
| `scope_dimensions.py`, `scope_normalization_verify.py`, `handler/app.py:829`, `_membership_reads.py` `.values` | Scope ACCESS resolution / `allowed_scopes` (`config#scope` / `ScopeConfig`) — the design is explicit this boundary is UNCHANGED (DISPLAY-vocabulary fix only). `.values` here is the scope-config dimension / dict `.values()`, NOT `FieldScope.values`. Benign. |
| `fixed_fields.py:373,460,481`, `attribute_catalog.py:710` `FieldType.ENUM` / `type == "enum"` | Fixed-field registry definitions + the attribute-catalog type-token assertion. Platform definitions, not consumer per-kind branches on the read-assembly `options`. Benign. |

### A6. SAM test files

All `*.py` hits under `sam/tests/**` are TEST assertions/fixtures (e.g. `test_field_resolver.py`,
`test_config_fields_crud_service.py`, `test_members_projection_reader.py`, the E2E RED gate
`test_config_fields_roundtrip_red.py`, `test_enum_vocab_roundtrip_e2e.py`). These are the
**paired tests** that the change-with-tests contract (steering 30/34/39) requires to be updated in
the SAME task as their product-code edit — they are NOT product old paths. They are already named
in tasks 1, 2, 4, 5, 7, 8, 9, 11.x. The `_build_override` / `options or choices` references in
`test_config_fields_crud_service.py` (lines 1487–1706) encode the CURRENT (buggy) fallback and
MUST be realigned to the post-fix behavior when F1 lands (not left asserting the old coalesce).

---

## Section B — Frontend (`frontend/src/**/*.{ts,tsx}`)

### B1. Config editor author/read (C1, F5, F6)

| Hit (file:line) | Pattern | F-item / disposition |
|---|---|---|
| `TenantAdmin/MembersConfig/fieldConfigChangeOps.ts:56–65` `DEFINITION_ATTRS` includes `'choices'` AND `'options'` | the WRITE emits `choices` (and `options`) | **C1** — **task 6** drops `'choices'` from `DEFINITION_ATTRS` so the write emits ONLY `options`. Named in the task. |
| `TenantAdmin/MembersConfig/MembersFieldModal.tsx:152–168` `optionsToChoices` (seeds editor from `resolved.options`; absent → `[]`) + `:229` `choices: optionsToChoices(resolved.options)` | `optionsToChoices` empty-on-absent (editor) | **F6** — one `options` is the sole source; a propagated-but-empty source becomes loud/diagnosable (C6), not a silent empty. Changed by **task 6 (C1)** in concert with the SAM seam. |
| `TenantAdmin/MembersConfig/applicationChoiceSource.ts:104–123` `resolveChoiceSource`: explicit `reference` / `scope` / `enum` KIND branch | per-field-KIND branch in a vocabulary consumer | **F6-adjacent / C1 kind-branch (R2.6).** This is exactly the "no field-kind branching in consumers" target — the frontend picker-source adapter branches reference→scope→enum. Task 6 (C1) says "no kind branch (F6)". **Confirm** this file is in the task-6 edit set (the task names `MembersFieldModal.tsx` + `fieldConfigChangeOps.ts` but not `applicationChoiceSource.ts`). Recommend adding it to task 6's file list or confirming the reference→catalog precedence is a legitimate SOURCE selection (mirrors the SAM seam's `declaredSource`) rather than a consumer branch. |

### B2. Member-form / public application read (F5)

| Hit (file:line) | Pattern | F-item / disposition |
|---|---|---|
| `public/application/applicationForm.model.ts:172` `const raw = field.options ?? field.choices ?? []` | member/public-form read `options or choices` fallback | **F5** — read the one `options` the seam returns. This is THE one-sided fallback that HIDES the bug on the member-form path (bugfix.md root cause). Removed by **task 6 (C1/F5)**. |
| `public/application/applicationFieldConfig.ts:162` `const raw = field.options ?? field.choices ?? []` (`applicationChoiceValues`) + `:113–114` the `choices?` type alias | `options or choices` fallback + a legacy `choices` type alias on the public field | **F5** — same disease, the schema-generator side of the public read. Remove the `?? field.choices` fallback and retire the `choices?` alias with task 6 (C1/F5). The type alias `choices?: ... // Legacy alias for options` is the TS surface that lets the fallback exist. |

### B3. Benign / supporting frontend hits

| Hit | Why benign / disposition |
|---|---|
| `MembersTypedField.tsx:239` `if (def.key === 'choices')` | This is a field-DEFINITION-editor branch (the attribute whose KEY is literally `"choices"` renders the `EnumOptionsEditor`). It is editing the enum vocabulary attribute by name. When `choices` is retired on the write (C1), this editor key should move to `options` — **flag as a follow-on of task 6** (the editor control that authors the vocabulary must target `options`). Not a hidden fallback, but part of the `choices` retirement surface. |
| `ApplicationFieldAttributes.tsx:111` comment referencing `optionsToChoices` | comment only — benign. |
| `types/members.ts:545–546` `application_choices?` | the SEPARATE application-subset concept (R3.2) — NOT retired. Benign. |
| `types/members.ts` `FieldConfigField` read type | carries `options?` only (NO `choices` on the resolved read type) — this is already correct; the resolved read surface does not expose `choices`. Good. |
| `applicationMembershipType.ts`, `applicationPreviewFilter.ts`, `EnumOptionsEditor.tsx`, `ApplicationFormBuilder.tsx`, `ApplicationFormPreview.tsx`, `ApplicationFieldModal.tsx`, `flatViewToOverlay.ts`, `overlayModel.ts`, `applicationFormSchema.ts` | `choices` appears as the `application_choices` subset handling, the enum-options editor UI, or overlay-model plumbing — not an `options↔choices` name coalesce on the resolved-read vocabulary. Verify each carries no `options ?? choices` fallback (grep for `options || choices` / `options ?? choices` returned NO hits in these files). Benign unless a `choices` write survives after C1 — covered by the C8-equivalent review of the frontend write. |

### B4. Frontend test files

`__tests__/applicationChoiceSource.test.ts`, `__tests__/fieldConfigChangeOps.test.ts`,
`__tests__/MembersFieldModal.test.tsx` are the paired tests named in **task 6** — update in the
same change (assert `choices` is never written; editor seeds from one `options`). Not product old
paths.

---

## Section C — DynamoDB `config#fields` stored rows (C7 scope)

The real stored shapes are mirrored by the committed fixtures that reconstruct the live `h-dcn`
`config#fields` row (steering 39 "prove round-trips against REAL data"):

| Fixture | Finding | C7 disposition |
|---|---|---|
| `sam/tests/fixtures/hdcn_config_fields_overlay.json` | Carries a `choices` key under `personal.gender` (line 120) — a RICH `[{value,label}]` list stored under the `choices` NAME (the `fixed_overrides` / overlay write map). This is the real bare-`choices`/options-absent legacy shape the bug is about: the vocabulary lives under `choices`, `options` is absent on that row. | **C7 scope — in.** Task 3 (C7) rewrites `choices`→value-only `options` and drops `choices`. The design calls out the `h-dcn` `referral_source` row as the canonical live case; `personal.gender` in this fixture is the same shape (vocabulary under `choices`). Enumerate ALL `config#fields` rows carrying a bare/standalone `choices` at migration time — the fixture confirms the shape exists; the live sweep (read→count on the local-DynamoDB / Railway `test_governance_projection` seed) is the migration's own precise enumeration step (task 3's read→migrate→read). |
| `sam/tests/fixtures/hdcn_config_fields_overlay_legacy_groups_list.json` | Legacy groups-list variant — same overlay shape, also contains `choices`-named vocabulary. | **C7 scope — in** (same rewrite). |

**C7 scoping note:** the design states real usage is LIMITED (essentially the one `h-dcn`
`referral_source` row), so C7 is a SMALL idempotent targeted backfill (or fix-forward). The
fixtures confirm the `choices`-named shape is real and present on the `h-dcn` overlay; task 3's
live read→migrate→read against the local-DynamoDB `h-dcn` seed is the authoritative per-row
enumeration (a fixture is not a substitute for the live count — spec-11 "trust runs, not
inference"). **Action for task 3:** before migrating, run the live read to enumerate EVERY
`config#fields` row/field carrying a standalone `choices` (not just `gender`/`referral_source`) so
the backfill scope is exact.

---

## Section D — Reconciliation summary vs F1–F8

| F-item | Design location | Confirmed live hit(s) | Covered by task |
|--------|-----------------|------------------------|-----------------|
| F1 | `_fields_overlay_reader._build_override` `options or choices` | `_fields_overlay_reader.py:388–390` ✅ | task 5 (C5) |
| F2 | `_build_overlay_field` carries `choices` separately | `_fields_overlay_reader.py:317–350` (`choices=...`) ✅ | task 5 (C5) |
| F3 | `_build_options` bare-string coerce / degrade→None | `_fields_overlay_reader.py:179–228` ✅ | task 5 (C5) + task 9 (C6) |
| F4 | `_as_variable_field` inline-only → None | `field_resolver.py:318–367` ✅ | task 4 (C4 purity) + task 9 (C6) |
| F5 | member-form read `options or choices` | `applicationForm.model.ts:172` ✅ + `applicationFieldConfig.ts:162` ✅ | task 6 (C1) |
| F6 | `optionsToChoices` empty-on-absent (editor) | `MembersFieldModal.tsx:152,229` ✅ | task 6 (C1) |
| F7 | scope `FieldScope.values` as a second copy | `_field_models.py:234–249` (`values: Sequence[str]`) + `_fields_overlay_reader.py:259–270` (`FieldScope(values=...)`) ✅ | task 5 (C5) |
| F8 | reference catalog merged one-off outside uniform path | `_membership_writes_fieldconfig.py:85,232,431–444` ✅ | task 4 (C4) |

**Every F1–F8 item is confirmed by at least one live hit — the design list is grounded (no
F-item is speculative).**

### NEW old paths NOT covered by F1–F8 (the gate)

| New | Location | Pattern | Needs |
|-----|----------|---------|-------|
| **N1** | `_membership_catalog.py` `_serialize_field` ≈300–309 | per-kind branch (`membership_type`) + `options → choices` fallback, on the STAFF config-editor read serializer (the C4/F8 seam's output) | **New F-item (sibling to F8)** + name this file in tasks 4 (C4) & 9 (C6) + a C8 rule-(b)/(c) target. |
| **N2** | `config_write_service.py:542` `_field_choice_values` | `_collect(options) or _collect(choices)` write-side coalesce | **New F-item + task coverage** OR **C8 allow-list entry with reason**. User decision. |
| **N1b** | `_membership_writes_fieldconfig.py` `_public_field_options` ≈342–390 | per-kind branch + reads `field.choices` on the PUBLIC-form read | Confirm covered by C4 uniform pass / C8 rule, or carve out with the R3.2 subset reason (the public SUBSET is a legitimately different projection). |
| **N3 (frontend)** | `applicationChoiceSource.ts` `resolveChoiceSource` 104–123 | explicit reference/scope/enum KIND branch in the picker-source adapter | Add `applicationChoiceSource.ts` to task 6 (C1) file set, or confirm the reference→catalog precedence is a legitimate SOURCE selection mirroring the SAM seam's `declaredSource` (not a forbidden consumer branch). |

---

## VERIFY (task 0.1 acceptance)

- The inventory lists every grep hit with its F-mapping or an explicit disposition (mapped /
  new-old-path / benign-with-reason). ✅
- Cross-check against F1–F8: **all eight** F-items are each backed by at least one confirmed live
  hit (Section D). ✅
- Zero UNMAPPED old paths remain silently: the unmapped ones (**N1, N1b, N2, N3**) are explicitly
  surfaced here with a proposed new-F-item / task-coverage disposition. ✅ (**Gate tripped** — see
  below.)

## GATE — STOP and surface before removals (tasks 4–9)

The sweep found old paths NOT covered by F1–F8 (**N1, N1b, N2, N3**). Per task 0.1's gate, the
design's fallback-removal list + removal tasks must be EXTENDED to cover 100% of the confirmed
inventory before the removals proceed:

1. **N1** (`_membership_catalog._serialize_field`) — the staff config-editor read serializer's
   per-kind branch + `choices` fallback. This is the strongest finding: it is literally the
   serializer the "editor reads `options` only" symptom flows through, and collapsing the
   read-assembly seam (C4) is incomplete if this survives. **Recommend adding a new F-item and
   naming `_membership_catalog.py` in tasks 4 and 9.**
2. **N1b** (`_public_field_options`) — same disease on the SAM public-form read; may be legitimately
   a different projection (R3.2 subset) but still carries `field.choices` — confirm C4/C8 coverage
   or carve out with a reason.
3. **N3** (`applicationChoiceSource.resolveChoiceSource`) — frontend per-kind branch; add to task 6
   or confirm as a SOURCE selection (not a consumer branch).
4. **N2** (`config_write_service._field_choice_values`) — write-side `options or choices` coalesce;
   even if benign at runtime after C7, the C8 rule (b) will flag it — decide: migrate to `options`
   only, or add to the C8 allow-list with a documented reason.

These should be resolved (new F-items + task edits, or documented carve-outs) before tasks 4–9
remove the mapped fallbacks, so the removals cover 100% of the confirmed inventory and the C8
guard (task 10/12) has a complete, non-contradictory rule set.

---

## Note on `.aws-sam/build/**` artifacts

The raw grep surfaced a parallel set of matches under
`sam/members/.aws-sam/build/MembersLayer/python/sam/members/**`. These are the SAM-built COPIES of
the same source files (the layer build vendored the domain package). They are NOT independent old
paths — they are regenerated from source on every `sam build`. They are excluded from the live
analysis above. (They should not be committed/edited by hand; the fix lands in `sam/members/**`
source and the build copy follows.)

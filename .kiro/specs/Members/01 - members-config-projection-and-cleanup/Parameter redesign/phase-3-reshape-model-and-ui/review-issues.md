# Phase 3 — review issues log (this version)

> **Status: LOG, not fixes.** Issues found while reviewing the built Phase 3 drill-down UI on branch
> `spec/members-config-phase3-reshape` (pre-PR). We LOG first, triage, then fix as a batch — no code
> changes land from this file until an issue is explicitly scheduled. Add new issues as they surface.

## Legend
- **Severity:** blocker (must fix before ship) / major / minor / nit
- **Status:** open / decided (resolution agreed, not yet implemented) / fixed / won't-fix

---

## I-1 — Field modal exposed a resurrected "analytics role" attribute
- **Severity:** major · **Status:** FIXED (2026-xx, this branch)
- **Where:** `MembersFieldModal.tsx` (task 4.6) + its test.
- **What:** The field modal had an "Analytics role (alias)" input (placeholder `cancellation_date`)
  writing a plain-string `alias`. That revived the analytics-field-ROLE concept the
  `members-analytics-role-removal` cleanup had deliberately deleted (it duplicated the generic
  Dynamic Pivot Views mechanism).
- **Resolution (done):** removed the input entirely. The catalog `alias` attribute
  (`attribute_catalog.py`) is a Phase-1 **declared-only** stub with NO runtime consumer, so it is not
  authored here either; wiring it would be a separate deliberate change. Test updated to assert
  neither an analytics-role nor an alias control exists.

## I-2 — i18n label model (Option-b resource keys) is unsustainable for tenant-editable labels
- **Severity:** blocker · **Status:** SPA half FIXED (remediated in `members-config-drilldown-remediation`, tasks 1.2/1.3); steering `38` rule-6 text + any residual follow-up tracked separately
- **Where:** `useMembersLabels.ts` + `resolveShippedLabel`/`LABEL_KEY_SCHEME` in
  `membersConfigService.ts` (task 4.1); consumed by the drill-down tables/modal; mandated by steering
  `38-sam-module-field-config.md` **rule 6**; echoed in phase-3 `design.md` (§0, step 11) + `tasks.md`
  (4.1, grounding note). Original decision: `phase-1-catalog-backbone/design.md` §3.
- **What:** Option (b) resolves shipped labels from resource keys in `locales/{nl,en}/admin.json`.
  Those files are **baked into the SPA build** and are **global, not per-tenant** — so a tenant
  admin's label edit could only land there via code change → rebuild → **redeploy**, and could never
  be tenant-specific. Not viable for runtime, per-tenant, tenant-editable labels.
- **Decision — revert to Option (B) (KISS):**
  - A field's label is a **plain per-language map `{nl, en, …}` stored ON the field in the overlay**
    (the current stored shape minus the resource-key resolver). h-dcn → `{nl: "Voornaam"}` (Dutch
    only is fine).
  - The field `key` stays the **stable, language-neutral, English-ish technical identifier**
    (`first_name`, `personal.first_name`) — never shown, never translated (member records / scope /
    calculated fields key off it). "The label is the key" applies to tenant-ADDED fields; FIXED
    fields keep their technical key and get a **seeded default label** in the tenant's language.
  - **Shipped `locales` content keeps ONE narrow role:** a one-time **seed of the default label for
    fixed/base fields at onboarding** (so h-dcn sees "Voornaam", not "first_name"), NOT a runtime
    resolution layer. After seeding, the label lives on the overlay field and is edited there.
  - **Viewer language** = the language selector (`i18n.language`, nl/en). It selects which label
    variant to show; fallback to any present label, never blank. **Tenant preferred language** =
    implicit (the admin's current UI language at authoring) or a future parameter — not a new hard
    setting now.
  - **Remove** the task-4.1 resolver layer (`useMembersLabels`, `resolveShippedLabel`,
    `LABEL_KEY_SCHEME`) as the resolution authority — net code REDUCTION. Keep a plain
    `label[lang] ?? label.en ?? label.nl ?? key` resolve helper.
- **Steering impact (governance DoD, R9.5):** rewrite `38` rule 6 away from "Option (b) resource
  keys" to "tenant labels are plain per-language values stored in config; shipped resource files are
  a seed/default for base fields only, never a runtime resolution source for tenant-editable labels."
  Also update phase-3 `design.md` + `tasks.md` references.
- **Blast radius to fix:** `useMembersLabels.ts` (+ test), the three drill-down components that call
  it (`MembersGroupsTable`, `MembersFieldsTable`, `MembersFieldModal` via `MembersFieldActions`),
  `MembersGroupFieldHierarchy.tsx`, possibly `membersConfigService.ts` (keep/trim the resolver),
  steering `38`, phase-3 `design.md`/`tasks.md`/`requirements.md` (the Option-b mentions), and a check
  that onboarding seeds fixed-field default labels into the overlay `{nl,en}` shape.

## I-3 — Drill-down tables show only overlay-authored fields, not the full resolved catalog
- **Severity:** blocker · **Status:** FIXED (remediated in `members-config-drilldown-remediation`, task 1.1)
- **Where:** `overlayModel.ts` (`listGroups`/`listAllFields`/`listFieldsInGroup`/`listUngroupedFields`)
  + `MembersGroupsTable.tsx` + `MembersFieldsTable.tsx` + the editor wiring (`MembersConfigEditor.tsx`,
  tasks 4.4/4.5/4.8).
- **Symptom (observed):** a group (e.g. `personal`) shows only ONE field (`gender`) even though it
  has many functional fields (overlay + calculated + fixed). Some groups look complete, others
  nearly empty — depending on how many fields the tenant happened to overlay.
- **Root cause:** the drill-down tables read the **raw `field_overlay`** only (`overlayModel`
  operates on `field_overlay.fields` + `fixed_overrides`). That object contains ONLY the tenant's
  authored variable fields + fixed-field overrides — NOT the platform **fixed** and **calculated**
  base fields, which live in the module registries and appear ONLY in the **resolved** `FieldConfig`
  (`GET /members/field-config`). So the complete base/calculated/fixed catalog is invisible; you see
  only the overlay deltas (`gender` was overridden → it shows). The groups that "look complete" are
  just the ones with more overlay entries.
- **Why I introduced it:** when I rebuilt the drill-down around `overlayModel` (raw overlay) to make
  the single-save contract structural (I-less), I conflated "what to DISPLAY" with "what to WRITE".
  The superseded read-only `MembersGroupFieldHierarchy` was actually CORRECT on this point — it read
  `groupResolvedFields(config)` (the resolved `FieldConfig`), so it showed the full set.
- **Correct model (two sources, two roles):**
  - **Display** the full field set from the **resolved `FieldConfig`** (base ⊕ overlay ⊕ calculated,
    carrying provenance + the derived `(group.order, field.order, key)` order) — the groups table,
    fields table, and field counts must come from here, not the raw overlay.
  - **Write** maps back to the right overlay slice: editing/relabelling/moving a **fixed/base** field
    creates or updates its `fixed_overrides` entry; editing a **tenant-added** field edits its
    `fields` entry; a **calculated** field is read-only (no overlay write). The single-save contract
    stays (one Save → one `field_overlay` commit) — only the WRITE target per field is provenance-
    dependent.
- **Interaction with other actions:** `groupFieldCount` (delete-group-only-when-empty) must count the
  RESOLVED fields in a group, not just overlay entries — else a group that looks empty in the overlay
  but holds base fields could be wrongly deletable. Move-to-group / provenance actions already key off
  the resolved provenance (good), but their overlay write must create an override for a base field.
- **Blast radius:** `overlayModel.ts` (or a new resolved-config read layer beside it),
  `MembersGroupsTable`/`MembersFieldsTable` (read resolved config, write overlay), `MembersConfigEditor`
  (pass the resolved `FieldConfig` into the tables, not just the overlay), the field modal save
  (route base-field edits to `fixed_overrides`), and all their tests. This is a rework of tasks
  4.4/4.5/4.8, not a small patch.
- **Confirming instances (all ONE bug — overlay read instead of resolved config):**
  - **I-3 proper:** fixed/calculated base fields missing from a group (e.g. personal shows only
    `gender`).
  - **I-4:** `region`'s scope-derived enum values gone (overlay stores empty `choices`).
  - **I-5:** `region` scope attribute "not selected" (scope lives on resolved config / `config#scope`,
    not the overlay) — compounded by I-6 (resolver never populates it).
  - **`status` shows as `string` (NEW confirming instance):** in the registry `status` is
    `type=ENUM` with 6 options (application/pending/active/suspended/lapsed/left + nl/en labels),
    carried on the resolved `FieldConfig`. The config modal shows it as `string` with no values
    because (a) `status` is a FIXED field with no `fixed_overrides` entry, so it is absent from / typeless
    in the raw overlay the modal reads, and (b) the field modal's `formFromField` **defaults `type`
    to `'string'`** when the overlay field has no `type` (`type: typeof field.type === 'string' ?
    field.type : 'string'`) — so a typeless/absent field silently renders as a plain string. The
    resolved config has the correct `type=enum` + 6 options. **Aggravator to fix with I-3:** the
    modal must take type/choices from the resolved field, and must NOT silently default an unknown
    type to `string`.

## I-4 — Enum field values gone in the modal (`region` shows type=enum but 0 of its 10 values)
- **Severity:** blocker · **Status:** FIXED (remediated in `members-config-drilldown-remediation`, task 2.1) · **Related:** I-3
- **Where:** `MembersFieldModal.tsx` (`formFromField` reads `field.choices`; the enum editor binds
  `form.choices`), the fields table, and the overlay-vs-resolved source problem of I-3.
- **Symptom (observed):** the `region` field shows `type = enum` but its 10 enum values are gone.
- **Root cause (exact, confirmed in `field_resolver.py`):** `region` is a scope-dimension-backed
  enum. By DESIGN its enum values are **NOT stored on the overlay** — the overlay stores `region` as
  an enum with EMPTY `choices` because `scope_dimensions.values` is the single source of truth
  (no duplicated list). At RESOLVE time, `_as_variable_field` sees an enum with no inline
  choices/options whose key is in `scope_vocab` (the `{field: values}` map derived from the tenant's
  enabled scope dimensions) and sets `choices = tuple(scope_vocab[key])` → the 10 regions. So the
  values exist ONLY on the **resolved `FieldConfig`** (`ResolvedField.choices`), injected by the
  resolver from the scope dimension. The modal reads `field.choices` from the **raw overlay**, which
  is intentionally empty for `region` → zero values shown. (This is the I-3 overlay-vs-resolved
  defect, in its sharpest form: for a scope-backed enum the overlay has NOTHING to show by design.)
- **Design rule this implies (important):** a scope-backed enum's values are **scope-owned**, not
  hand-authored. The modal must present them as **read-from-scope** (tied to the field's scope
  dimension / step-9 `scope.values`), NOT as an editable `choices` list. Editing them as overlay
  `choices` would be actively harmful: the resolver only sources from `scope_vocab` WHEN overlay
  choices are empty, so a hand-edited `choices` would SHADOW the scope dimension and drift from it.
  So enum-vocabulary has three sources that the modal must distinguish: (a) tenant-authored `choices`
  (freely editable), (b) **scope-derived** (read-only, owned by the scope dimension), (c) shipped
  enum like `status` (resource/base). The `options` vs `choices` key duality is secondary — the
  resolver keeps them coherent (`choices = [o.value for o in options]`); the real fix is sourcing +
  the scope-owned read-only rule.
- **Blast radius:** overlaps I-3 (tables/modal must read the resolved `FieldConfig`). I-4 adds: the
  field modal's enum section must classify the vocabulary source and render scope-derived values
  read-only (sourced from the scope dimension), reserving the `choices` editor for tenant-authored
  enums. Fix with I-3 as one source rework. Tests for all three enum sources.

## I-5 — Scope attribute reads "not selected" for a scope field (`region`); scope source + type gap
- **Severity:** blocker · **Status:** FIXED (remediated in `members-config-drilldown-remediation`, tasks 3.1/3.2/3.3) · **Related:** I-3
- **Where:** `MembersFieldModal.tsx` (`formFromField` reads `field.scope` off the raw overlay);
  `frontend/src/types/members.ts` (no `scope` on `FieldConfigField`); the SAM read re-presentation in
  `field_resolver.py` (`FieldScope` on `ResolvedField`/`FixedFieldOverride`).
- **Symptom (observed):** opening the `region` field (which IS a scope axis for h-dcn), the modal
  shows the scope attribute as unset / **"Not selected"**, when scope should be enabled with values.
- **Root cause (confirmed in `field_resolver.py`) — two problems:**
  1. **Scope source of truth is `config#scope`, NOT the overlay field.** Phase-3 step 9 makes the
     field's `scope` a **SAM READ-ONLY re-presentation** (`FieldScope` on `ResolvedField`): the
     resolver docstring says *"Carried verbatim; the resolver does not read it... scope RESOLUTION
     stays on `config#scope`/`ScopeConfig` (R2.3)."* For h-dcn, `region`'s scope is authored as a
     **scope dimension** (`config#scope` / the `scope_dimensions` param), and the field's `scope`
     attribute is DERIVED from it at resolve time. So the **raw overlay field has no `scope`
     attribute** → the modal (reading the overlay) shows "not selected." The real state is on the
     resolved config's `FieldScope` (and ultimately on `config#scope`). This is the I-3
     overlay-vs-resolved defect again.
  2. **Frontend type gap:** `FieldConfigField` in `types/members.ts` has **no `scope` member**. The
     resolved config exposes `dimensions?: ScopeDimension[]` (the OLD scope-dimension shape) but the
     served per-field `FieldScope` is not modelled on the SPA at all. My modal reads `field.scope`
     via a loose cast, so it compiles but finds nothing. The SPA type must model the served field
     `scope` before the modal can read/show it.
- **Design question the fix MUST answer (not just "read resolved config"):** the field `scope`
  attribute is explicitly a **read-only re-presentation**; the authoritative store is `config#scope`.
  So CAN a tenant edit scope from the field modal, and if so WHERE does the write go?
  - Option (i): the field modal shows scope **read-only** (sourced from the resolved `FieldScope`),
    and scope is still AUTHORED via the scope-dimension mechanism / Flask builder — i.e. step 9 is a
    display re-presentation, not an authoring move. (Matches the resolver's "read-only" stance and
    R2.3 "resolver unchanged".)
  - Option (ii): the field modal AUTHORS scope as a field attribute that the Flask builder DERIVES
    `config#scope` from (the design's §Data-Models step-9 "whether a derived config#scope row or an
    equivalent projection"). Then the write target + the Flask builder path must be confirmed to
    exist and be wired — currently the SPA writes `scope` into the overlay field, but it is unclear
    the Flask builder reads an overlay-field `scope` to produce `config#scope`.
  - This determines whether the modal's scope control is editable or read-only, and whether the
    overlay even carries `scope`. MUST be settled before coding.
- **Blast radius:** overlaps I-3 (read resolved config). Plus: add a `scope` type to
  `FieldConfigField`; decide authoring vs read-only (Option i/ii) and confirm the Flask
  builder/validator path for a field-attribute `scope` write; align `MembersFieldModal` + its scope
  tests; reconcile with the step-9 server work (tasks 2.1/2.3) that was done in the earlier build.

## I-6 — `ResolvedField.scope` is declared but NEVER populated; docstring is wrong (step-9 SAM gap)
- **Severity:** blocker · **Status:** FIXED (remediated in `members-config-drilldown-remediation`, task 3.1) · **Related:** I-5
- **Where:** `sam/members/domain/field_resolver.py` — `ResolvedField.scope`, `FixedFieldOverride.scope`
  (declared `FieldScope | None`), and the resolve builders `_apply_override`, `_as_variable_field`,
  `_as_calculated_field`.
- **What (confirmed by reading the builders):** the `scope` field attribute (step 9) is **declared in
  the dataclasses but DEAD** — no code populates it:
  - `_apply_override` (fixed fields incl. `region`): constructs `ResolvedField(...)` copying label /
    required / visible / order / functional_group / options / show_when / member_number_format from
    the override, but **never sets `scope=`** and never reads `override.scope`.
  - `_as_variable_field`: constructs `ResolvedField(...)` and **never sets `scope=`**.
  - `_as_calculated_field`: no scope.
  So `ResolvedField.scope` is ALWAYS `None` in the served config; `FixedFieldOverride.scope` is never
  read. The scope-as-field-attribute re-presentation is not actually produced by the resolver.
- **The docstring is MISLEADING/WRONG vs the code:** `ResolvedField.scope`'s comment says *"when this
  field is authored as a scope axis, its scope config (FieldScope)… Carried verbatim; the resolver
  does not read it."* But the resolver does not CARRY it either — it is never assigned. "Carried
  verbatim" is false. The docstring describes an intended wiring that was not implemented.
- **Consequence / reframes I-5:** the SPA modal shows scope "not selected" for `region` not merely
  because of overlay-vs-resolved (I-3) — it is because **the server never emits a field `scope`
  attribute at all**, anywhere. Step 9's SAM read representation is incomplete.
- **Contradicts tasks.md:** task **2.1** ("Author scope-binding as a field attribute on the Flask
  writer + the SAM read representation") is marked `[x]`, but the SAM read representation is a dead
  field. Either 2.1 was over-claimed, or population was intended on the Flask builder only and the
  SAM dataclass docstring over-promised.
- **To verify (do before fixing):** whether the **Flask builder** (`_projection_config_builders.py`)
  actually derives/serves a field `scope` (so step 9's authoring exists on the Flask plane and only
  the SAM `ResolvedField` carry is dead), OR whether step 9 field-attribute scope is unwired on BOTH
  planes. That determines whether the fix is "wire the resolver to populate `ResolvedField.scope`
  from `override.scope` / scope_vocab" + fix docstring, or a larger step-9 completion.
- **Blast radius:** `field_resolver.py` (populate `scope` in `_apply_override`/`_as_variable_field`
  OR delete the dead field + correct the docstring, per the design decision in I-5 Option i/ii),
  possibly the Flask builder, `test_field_resolver.py` / `test_scope_access.py`, and the SPA type
  gap + modal from I-5. Resolve together with I-5 (same scope-authoring question).

## I-7 — Per-field validation/format options (IBAN, date/time, …) are absent from the model + modal
- **Severity:** major · **Status:** open (needs decision provenance)
- **Where:** `sam/members/domain/attribute_catalog.py` (`ATTRIBUTE_VOCABULARY`), the field model
  (`field_resolver.py`), and `MembersFieldModal.tsx`.
- **What (user report):** "We decided ONCE to have validation options for some fields (iban,
  date/time, …). I do not see these options." Confirmed: the field modal shows no such options.
- **Findings (confirmed in code + specs):**
  - The attribute vocabulary has **NO general validation/format attribute** — no `format`, `regex`,
    `pattern`, or `validation`. The ONLY validation-ish attribute is **`member_number_format`**
    (prefix/width/regex), and it is **field-specific to `member_number`** (`required_when
    key==member_number`). An `iban` field (h-dcn has one) is just a `string` with no validation.
  - `type` (string/date/enum/reference) is only a formatting HINT ("drives cell/input formatting"),
    not a validation constraint — there is no date-format or IBAN-check attribute.
  - A grep of ALL Members specs (`analysis.md`, impact-analysis, phase 1/2/3, member-analytics,
    role-removal) finds **no recorded decision** for iban/date/time validation options. The
    `analysis.md` catalog-seed attribute list is "key, label, type, enum choices, required, visible,
    permission_roles, calculated?, scope-binding?, …" — no validation attribute.
  - So this is NOT merely "the modal omits an existing attribute": the capability is **absent from the
    attribute model itself**. (By contrast `member_number_format` DOES exist but is also not surfaced
    in the modal — a smaller modal-completeness gap, noted below.)
- **Two sub-issues:**
  - **I-7a (missing feature):** a general per-field validation/format attribute (IBAN / date-time /
    email / numeric-range …) was decided but never built into the catalog/field model. Needs the
    decision pinned down (where/when, intended shape) before design — I could not locate it in the
    specs, so scope + semantics are unconfirmed. This is likely a **new deliverable**, possibly
    beyond Phase 3 (Phase 3 is reshaping, not adding a validation subsystem).
  - **I-7b (member_number_format: enforced + served, but NO runtime tenant-authoring path):**
    `member_number_format` is modeled as **tenant-specific** (dataclass docstring: "its format is
    tenant Parameter config"; prefix+width OR regex) and works on the READ/ENFORCE side end-to-end —
    a model example of a correctly-wired attribute (contrast the dead `scope`, I-6): modeled
    (`MemberNumberFormat` + catalog `AttributeSpec`), **populated by the resolver** (`_apply_override`
    carries it, from `FixedFieldOverride.member_number_format`), built by the projection reader
    (`_build_member_number_format` from a projected spec), serialized onto `GET /members/field-config`,
    **server-enforced** on the write path (`validate_member_number_format` + `MEMBER_NUMBER_FORMAT` +
    passing write-gate test), and surfaced for live feedback in the member Add/Edit FORM.
    **BUT there is NO runtime tenant-authoring surface for the value:**
    - NOT in the Phase-3 config field modal (`MembersFieldModal` has no prefix/width/regex control);
    - NOT in the Flask param schema — a grep of `backend/src/**` for `member_number_format` /
      `prefix` / `width` finds NOTHING; the Flask parameter editor does not author it either;
    - the only place a concrete value appears is a **test fixture** (and presumably an onboarding
      seed). So in practice a tenant's member-number format is **fixed at onboarding** — a tenant
      cannot change it at runtime without a config/seed change (the SAME "needs a new version to
      change" footgun as the I-2 label problem).
    So the structure is "tenant-specific by DESIGN but effectively onboarding-fixed" — not literally
    hardcoded-same-for-all, but not runtime-tenant-editable. Fix = provide a runtime authoring path:
    add the control to the field modal (prefix/width/regex/example → write to the overlay as a fixed
    field override) AND confirm the Flask builder/validator projects it to `config#fields`. Larger
    than a pure modal tweak because the Flask authoring/projection side for this attribute is also
    absent.
- **Needed from the user / to verify:** where the iban/date-time validation decision was captured
  (another spec? a chat? a steering doc?), and the intended model: a per-field `validation`/`format`
  attribute with a fixed set of validators (iban, date, email, regex) vs. per-type built-in
  validation. Until that's confirmed, treat I-7a as design-pending, not a straight bug.
- **Blast radius (if built):** new attribute(s) in `attribute_catalog.py` + the drift guard, the SAM
  field model + resolver carry, the Flask param schema + validator, the field modal UI + save, and
  the member-record validation path (server authoritative). Non-trivial — likely its own spec/phase.

## I-8 — Move-to-group reverts on save (modal re-pins `functional_group` to the opened group)
- **Severity:** blocker · **Status:** FIXED (remediated in `members-config-drilldown-remediation`, task 5.1)
- **Where:** `MembersFieldModal.tsx` (`buildField` hardcodes `functional_group: groupKey`; `handleSave`
  → `editField`), `MembersFieldActions.tsx` (`handleMove` → `moveFieldToGroup`), `MembersConfigEditor`
  (passes `groupKey={openGroupKey}` to the modal, never updated after a move).
- **Symptom (user):** created + stored a field; tried to move it to another group — it DISAPPEARED
  from the current group (looked moved), but after Save it was BACK in the original group.
- **Root cause (confirmed):** TWO authoring paths write `functional_group` for the same field from
  un-synchronized state, and the modal's STALE value wins:
  1. `MembersFieldActions.handleMove` → `moveFieldToGroup(overlay, key, target)` → `onChange`:
     correctly updates the overlay so the field moves to `target` (hence it drops out of the current
     group's table — the "disappeared" step is correct behaviour).
  2. The field modal stays open, holding `groupKey = openGroupKey` (the ORIGINAL group — the editor
     passes `groupKey={openGroupKey}` and never updates it after a move). Its `buildField()`
     UNCONDITIONALLY sets `functional_group: groupKey` (original). On the modal's Save
     (`handleSave` → `editField(overlay, key, patch)` with `patch.functional_group = groupKey`), it
     **overwrites the move**, re-pinning the field to the original group → it "comes back".
- **Compounding:** both components build their `onChange` from the `overlay` PROP snapshot in their
  closure; a move followed by a modal save derived from a pre-move snapshot silently discards the
  move even aside from the hardcoded `groupKey`.
- **Fix direction:** `functional_group` must have ONE writer / source of truth per field. Options:
  (a) the modal should NOT re-author `functional_group` at all unless the user changed it in the
  modal (read the field's CURRENT group from the working overlay, not the opened-group prop); move
  stays the only mutator. (b) make move-to-group update the modal's `groupKey`/form so a subsequent
  save writes the new group. Prefer (a) — the modal authors the field's own attributes; group
  membership is owned by the move action (and by the field's stored `functional_group`), read live
  from the overlay, never from the stale `openGroupKey` prop.
- **Blast radius:** `MembersFieldModal.buildField`/`handleSave` (stop hardcoding `groupKey`; derive
  the field's group from the working overlay), the editor's modal wiring, and the move/save tests
  (add a regression: move → editor Save → field persists in the TARGET group). Independent of I-3
  but should be fixed in the same modal/editor rework.

## I-9 — Flask `config#fields` builder DROPS scope/options/choices/member_number_format on fixed overrides
- **Severity:** major · **Status:** FIXED (remediated in `members-config-drilldown-remediation`, task 4.1 — `options`/`choices`/`scope` carried; `member_number_format` deferred to the follow-up spec per R5.2)
- **Where:** `backend/src/services/_projection_config_builders.py` — `_map_fixed_override` /
  `_FIXED_OVERRIDE_FIELDS` carries ONLY `label` / `visible` / `required` / `order` /
  `functional_group`. A `fixed_overrides` entry's `options`, `choices`, `scope`, and
  `member_number_format` are DROPPED from the `config#fields` row.
- **Consequence:** a tenant who re-authors a FIXED field's enum options (e.g. relabels `status`'s 6
  values) or sets `member_number_format` via `fixed_overrides` loses it in the projection
  (`config#fields`). Scope on a fixed override is NOT lost for scope resolution (the SEPARATE
  `config#scope` builder still reads it via `_scope_dimensions_from_overlay`), but it is absent from
  `config#fields`, so the resolved FIELD never carries it (compounds I-6).
- **Note:** the h-dcn seed authors `status`/`gender` rich options as `fixed_overrides.choices` and
  relies on the SEED SCRIPT (not the generic builder) to land them — which is why prod `status` has
  6 options despite this builder gap. A tenant editing via the generic path would NOT get that.
- **Blast radius:** `_map_fixed_override` + `_FIXED_OVERRIDE_FIELDS` (carry the dropped attrs through,
  honouring the "fixed override is presentation-only, cannot weaken invariants" rule), the SAM
  reader/`_apply_override` (already applies `options`/`member_number_format` from the override — good),
  `test_projection_sync` / builder tests. Needed for I-7b (member_number_format authoring) and for
  tenant-editable fixed-field enum options.

---

## I-5 + I-6 MERGED — scope is an editable field attribute in the field modal (CONFIRMED POSSIBLE)
- **Severity:** blocker · **Status:** decided (one unit of work; I-5 and I-6 are the same requirement)
- **Requirement (user):** scope must be CONFIGURABLE in the field modal — the admin can mark a field a
  scope axis AND edit its value vocabulary (add a value, remove a value). Scope management must then
  actually work with whatever is defined. No separate scope-dimensions editor. "Unless not possible."
- **It IS possible — the write path is already built:** the Flask param schema accepts a `scope`
  attribute on a field (`{enabled, values, required_for}`); the validator checks it
  (`_validate_field_scope`); and `build_config_scope_row` DERIVES the authoritative `config#scope`
  from it (`_scope_dimensions_from_overlay`). So editing `scope.values` in the modal → saved on the
  overlay field → projected to `config#scope` → consumed by scope RESOLUTION + grants. Authoring →
  projection → enforcement already round-trips.
- **The only gaps (both bounded):**
  1. **Read-back (I-6):** `ResolvedField` has no `scope`; `_apply_override`/`_as_variable_field` never
     populate it; the serializer never emits it (dead; docstring wrong). → wire + serialize
     `ResolvedField.scope` (server), fix the docstring, so the modal can show the CURRENT scope state.
     This is option (ii) — the right call given the requirement (per-field `scope` as a first-class
     served attribute), not the zero-change `dimensions`-array workaround.
  2. **Modal UI (I-5):** the modal's scope section must read the served `scope` back and offer a real
     add/remove **value-list editor** (not the current comma-separated string), writing `scope.values`.
- **Critical correctness rule (ONE vocabulary = the field's enum values; user-confirmed):** for a
  scope-backed field, the scope values ARE the field's ENUM VALUES — there is NO separate "scope
  values" list anywhere (not in the modal, not in the stored `scope` object). The field modal shows
  the field's single enum-values editor; the scope section is reduced to the scope-ness facts that are
  NOT the values: the **enabled** toggle and **required_for** roles. Editing the enum values IS editing
  the scope vocabulary (add an enum value → new scope value; remove one → gone from scope). This flips
  my earlier framing: the ENUM-values editor is the one editor; `scope` merely REFERENCES it.
- **Data-model consequence (confirmed feasible):** `scope` on a field becomes `{enabled, required_for}`
  only — DROP `scope.values`. The Flask scope builder `_scope_dimensions_from_overlay` must take the
  field's ENUM VALUES (`choices` / `options[].value`) as the dimension's `values` when `scope.enabled`
  is true, instead of reading `scope.get("values")`. It has the full field spec at build time (it
  reads the `spec` dict which carries `choices`/`options`), so this is feasible. The param schema's
  `scope` object drops its `values` subfield; the validator's `_validate_field_scope` stops requiring
  `scope.values` and instead requires the field to be an enum WITH values when scope is enabled.
  (Back-compat: a legacy stored `scope.values` can still be honoured as a fallback during migration,
  but the authoring model is one list.)
- **Round-trip acceptance:** enable scope on a field, ADD a value, REMOVE a value, save → `config#scope`
  reflects the edited vocabulary → the field's resolved enum options reflect it → scope resolution
  honours it. Add this as the regression test.
- **Blast radius:** SAM `field_resolver.py` (populate+serialize `ResolvedField.scope`; docstring),
  `_membership_catalog._serialize_field` (emit `scope`), frontend `types/members.ts` (add `scope` to
  `FieldConfigField`), `MembersFieldModal` scope section (enabled + value-list editor; one-vocabulary
  rule vs the `choices` editor), tests on all planes. Supersedes the separate I-5 and I-6 entries
  above (kept for history).

## Verification-pass corrections (server-truth confirmed) — read before triage

A read-only server-truth pass (SAM resolver + serializer + Flask builders + h-dcn seed) corrected
several assumptions above:
- **I-3/I-4/status:** the resolved `FieldConfig` served by `GET /members/field-config` is CORRECT and
  COMPLETE — it carries all fixed/calculated fields, `status` with 6 `options`, `region` with its 10
  values (via `scope_vocab`, which IS wired at the handler), and `provenance` per field. So the ENTIRE
  I-3 family fix is SPA-only: **read the resolved config, not the raw overlay.** No server change for
  I-3/I-4/status.
- **Enum values are served ONLY under `options`** (rich `{value,label,roles?}` OR a bare string
  list) — there is NO `choices` key in the served JSON. The modal must read `options` (it currently
  reads `choices` — wrong key). Scope-backed `region`'s 10 values arrive as `options` (bare list) AND
  in the top-level `dimensions` array.
- **I-6 scope — read path dead, WRITE path complete:** the Flask param schema DOES allow authoring a
  `scope` attribute on fields/overrides, the validator checks it, and `build_config_scope_row` DERIVES
  `config#scope` from it (`_scope_dimensions_from_overlay`). What's missing is only the SAM READ carry:
  `ResolvedField` has no `scope`, the resolver never populates it, the serializer never emits it. Fix
  is bounded: either populate+serialize `ResolvedField.scope`, or have the SPA read scope state from
  the served top-level `dimensions` array (already present). NOT a step-9 rebuild.
- **I-2 labels:** CONFIRMED there is NO resource-key/i18n indirection on the SAM/Flask planes — labels
  are plain inline `{nl,en}` dicts, stored and served. The Flask schema takes flat `label_en`/`label_nl`
  and FOLDS them to `label{}` on save. So the Option-(b) resource-key layer exists ONLY in the SPA
  (task 4.1, `useMembersLabels`/`LABEL_KEY_SCHEME`) — the server already does exactly what I-2 decided
  (plain stored per-language label). The I-2 fix is SPA-only: drop the resource-key resolver, read the
  served `label{}` dict directly. Steering `38` rule 6 still needs the wording change, but the server
  needs NO change.

---

## (add further issues below as they are found)

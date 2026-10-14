# Members Analytics Role Removal — Bugfix Design

## Overview

This design is a **removal plan**, not a feature build. The Members codebase carries an analytics
**"role" machinery** — analytics field roles, the jubilee rule, the address-mapping label path, and
the **entire hardcoded preset subsystem** (all eight presets) — that duplicates capability the
generic **Dynamic Pivot Views** mechanism already provides. It compiles, it is wired end to end, and
it is fully tested, so it reads as a live feature and invites maintainers (human and AI) to extend a
parallel, redundant analytics vocabulary. Per the product owner's Option A, **no predefined pivots
are baked in at all**: every view is built generically by grouping/filtering on field names.

The fix removes the machinery and its paired tests, retires the `member-analytics` acceptance
criteria/tasks that mandate it, and leaves **no stubs** — after proving at code level (the
EQUIVALENCE GATE) that every removed capability is reachable through the generic pivot.

The removal spans four planes (SAM → Flask → frontend → specs/fixtures) and one DynamoDB
projection slice. The strategy is to **order the deletion so the build stays green at every step**:
each step compiles and its paired suites pass before the next begins. The ordering is derived from
the real inter-module dependency direction confirmed in code (below), not from the module list order.

Two hard invariants frame everything:

1. **Member-data non-destructiveness.** The `sam-members` table is never read-for-mutation or
   written. The only data touched is the `config#fields` projection row's `analytics` role-config
   slice, cleaned by a single re-projection through the existing `projection_sync` path.
2. **Scope boundary.** The generic analytics-SET feature (`analytics_set.py` /
   `_membership_analytics.py`, saved pivot/list sets, the Pivot Views surface itself, CSV/mail/
   template-label exports, Overview + violin distributions, the SAM `RouteGroup.ANALYTICS` routes,
   `log_analytics_output` / `members_analytics_audit.py`) is **out of scope and preserved**. The
   token `.analytics` matches both; the removal targets only the role-config members of
   `FieldConfig.analytics` and the constructs named in the manifest — never the analytics-set feature.

## Glossary

- **Bug_Condition (C)**: an artifact (source, test, fixture, served payload, or stored set) that
  exposes, stores, serves, authors, or tests the role / jubilee-rule / address-mapping / preset
  machinery that duplicates the generic pivot. Formalized in `isBugCondition` below (verbatim from
  bugfix.md §Bug Condition).
- **Property (P)**: after removal the machinery is gone, no stub remains, and `C(X)` holds nowhere
  (the grep manifest returns zero non-historical hits; drift guard + touched suites green).
- **Preservation**: everything a non-buggy input provides — the generic pivot (incl.
  `applyDefinitionFilters`), CSV/mail/template-label exports, Overview + violins, the resolved field
  config minus only the `analytics` role-config member, scope resolution, and member records — must
  be bit-for-bit unchanged.
- **EQUIVALENCE GATE** (bugfix 2.8): a code-level artifact proving each removed capability
  (including each of the eight presets) is reachable in the generic pivot, checked **before** deletion.
- **Role machinery**: `AnalyticsRole`, `AnalyticsConfig.field_roles`, and the role targets
  (`cancellation_date`, `referral_source`, `clubblad_paper`, `clubblad_digital`, `country_detail`).
- **Jubilee machinery**: `JubileeRule` / `jubilee_rule` and the jubilee selector/filter
  (`candidateJubileeYears`, `selectedJubileeYear`, `applyJubileeYearFilter`, `isJubileeYear`,
  `DEFAULT_JUBILEE_MULTIPLE`, `MAX_JUBILEE_YEAR`, `JUBILEE_YEAR_FILTER_KEY`).
- **Address-mapping machinery**: `AddressMapping` / `address_mapping`, `resolveAddressMapping`,
  `composeAddresses`, `generateAddressLabelPdf`, and `AddressLabelGenerator`.
- **Preset subsystem**: the whole of `memberPivotPresets.ts` (the `MemberPivotPreset` type, the
  `PRESETS` table of all eight presets, `getAllPresets` / `getAvailablePresets` /
  `getPresetsWithAvailability` / `materializePreset` / `presetFieldsPresent`) and the Pivot Views
  preset-dropdown wiring.
- **Template-label path (surviving)**: `composeLabelLines` / `generateLabelTemplatePdf` /
  `MemberLabelsPanel` / `MemberTemplateManager`, which read **no** `analytics.*`.
- **F / F'**: the Members code *with* the machinery / *after* removal.
- **ODI-2**: the one-directional projection of the analytics slice off the overlay onto
  `FieldConfig.analytics`, served on `GET /members/field-config`.

## Bug Details

### Bug Condition

The bug manifests whenever an artifact exposes, stores, serves, authors, or tests any of the
role/jubilee/address-mapping/preset machinery that duplicates the generic pivot. `C(X)` holds for
any **non-historical** grep-manifest hit — excluding build artifacts under `**/.aws-sam/build/**`,
vendored `**/node_modules/**` / `**/.venv/**`, Vitest caches, and prose in spec/history docs that
records the removal.

**Formal Specification** (verbatim from bugfix.md):

```
FUNCTION isBugCondition(X)
  INPUT:  X of type MembersCodeArtifact        // source/test file, config fixture,
                                               // served field-config payload, or stored set
  OUTPUT: boolean

  RETURN  exposes_analytics_role_machinery(X)        // AnalyticsRole / field_roles / role targets
       OR exposes_jubilee_rule_machinery(X)          // JubileeRule / jubilee_rule / jubilee selector+filter
       OR exposes_address_mapping_machinery(X)       // AddressMapping / address_mapping / resolveAddressMapping
                                                     //   / composeAddresses / generateAddressLabelPdf
       OR exposes_preset_subsystem(X)                 // ANY of memberPivotPresets: the type, the PRESETS
                                                     //   table (all 8), the serving functions, or the
                                                     //   Pivot Views preset-dropdown wiring
       OR exposes_analytics_role_config(X)           // AnalyticsConfig / _build_analytics / _serialize_analytics
                                                     //   / FieldConfig.analytics role members / Analytics tab
END FUNCTION
```

The removal checklist is the four grep patterns (bugfix.md §Known footprint):

- `AnalyticsRole|field_roles|fieldRoles|cancellation_date|referral_source|clubblad_paper|clubblad_digital|country_detail`
- `JubileeRule|jubilee_rule|jubileeRule|usesJubileeRule|candidateJubileeYears|selectedJubileeYear|applyJubileeYearFilter|DEFAULT_JUBILEE|JUBILEE_YEAR|jubileeYear`
- `AddressMapping|address_mapping|addressMapping|resolveAddressMapping|composeAddresses|generateAddressLabelPdf`
- `AnalyticsConfig|_build_analytics|_serialize_analytics|analyticsConfig|hasAnalyticsConfig` (role-config members of `.analytics` only)

### Examples (bug manifestation)

- `GET /members/field-config` serves an `analytics` role-config block built by
  `ProjectionConfigReader._build_analytics` and serialized by `_membership_writes._serialize_analytics`.
- `MemberPivotViews` renders a preset dropdown off `getAvailablePresets(fieldConfig)` and shows a
  jubilee-year selector driven by `candidateJubileeYears(fieldConfig.analytics.jubilee_rule)`.
- `MemberMailCompose` resolves the recipient email through `resolveEmailField`'s `field_roles`
  branch, and gates the "Attach PDF labels" toggle on `resolveAddressMapping(fieldConfig)`.
- `AddressLabelGenerator` composes labels via `resolveAddressMapping` / `composeAddresses` /
  `generateAddressLabelPdf`, in parallel with the template path that already supersedes it.
- The grep manifest returns many non-historical hits (edge case: `members_analytics_audit.py`,
  `analytics_audit.py`, and the SAM `analytics-sets` routes match the token `analytics` but are the
  generic analytics-SET feature — **not** targets; see the Scope boundary).

### Code-confirmed footprint and dependency direction

Confirmed by reading the code (this grounds the ordering in §Fix Implementation):

- **SAM domain** (`sam/members/domain/field_resolver.py`): `AnalyticsRole`, `JubileeRule`,
  `AddressMapping`, `AnalyticsConfig` are defined here; `FieldConfig.analytics: AnalyticsConfig | None`
  and `TenantOverlay.analytics` carry them; `__all__` re-exports all four. `domain/__init__.py`
  re-exports `AddressMapping` / `AnalyticsConfig` / `AnalyticsRole`.
- **SAM reader** (`repository/projection_config_reader.py`): `_build_analytics` (+ `_build_jubilee_rule`
  / `_build_address_mapping`) and the `analytics=` wiring on `get_overlay`. **Depends on** the domain
  classes.
- **SAM writer** (`domain/_membership_writes.py`): `_serialize_analytics` and the `"analytics"` key on
  the served field-config payload. **Depends on** `AnalyticsConfig`. (Distinct from
  `_membership_analytics._serialize_analytics_set`, which is the preserved set feature.)
- **SAM catalog** (`domain/attribute_catalog.py`): a `note=` on the field-role-alias attribute that
  describes the analytics role meaning — prose/metadata only, no behavior.
- **Flask plane**: the ONLY footprint is the declarative `analytics` object slice in
  `backend/src/config/members_parameters.json` (the param-schema that authors `jubilee_rule` /
  `field_roles` / `address_mapping`). **Confirmed during design: there is NO Flask service
  builder/validator** for this slice — a grep of `backend/src/services/**` and `backend/src/**` for
  `jubilee|field_roles|address_mapping|AnalyticsRole|analytics_config` returns zero hits.
  `members_analytics_audit.py` / `analytics_audit.py` are the generic set-output audit (preserved);
  `signup_service.py`'s `referral_source` is unrelated signup data (preserved). The bugfix's
  "to-be-confirmed non-target" note resolves to **non-target**.
- **Frontend — sliced (NOT deleted) modules** (removed symbols coexist with surviving ones):
  - `analytics/analyticsConfig.ts` — remove `resolveRole`, `isJubileeYear`, `candidateJubileeYears`,
    `selectedJubileeYear`, `applyJubileeYearFilter`, `JUBILEE_YEAR_FILTER_KEY`,
    `DEFAULT_JUBILEE_MULTIPLE`, `MAX_JUBILEE_YEAR`, `resolveAddressMapping`, `hasAnalyticsConfig`,
    the `field_roles` branch of `resolveEmailField`; **keep** `applyDefinitionFilters`,
    `CONVENTIONAL_EMAIL_KEYS`, and the surviving `resolveEmailField` body (field-config only). The
    `new-members` joined-after selector (`candidateJoinedYears` / `selectedJoinedAfterYear` /
    `applyJoinedAfterFilter` / `JOINED_AFTER_FILTER_KEY`) is a preset-specific selector removed with
    the preset (bugfix 2.3); the generic `joined_date` filter is reached via `applyDefinitionFilters`.
  - `analytics/addressLabelService.ts` — remove `composeAddresses`, `generateAddressLabelPdf`,
    `LabelSortOrder`, `ComposedAddress`, `ComposeResult`; **keep** `composeLabelLines`,
    `generateLabelTemplatePdf`, Avery formats/geometry (`AVERY_LABEL_FORMATS`, `getLabelFormat`,
    `labelsPerPage`, `cellPosition`, `pageCount`, `clampFontSize`, `MIN/MAX_FONT_SIZE`,
    `LabelAlignment`, `LabelStyleOptions`, `GenerateResult`).
  - `analytics/index.ts` barrel — drop the removed re-exports (the C-CONFIG role helpers block, the
    C4 preset block, the C5 `composeAddresses` / `generateAddressLabelPdf` / `AddressLabelGenerator`
    block), keep the surviving ones.
  - `types/members.ts` — remove `AnalyticsRole`, `MemberAnalyticsConfig`, and the `analytics?` member
    of `FieldConfig`; **keep** the analytics-SET types (`MemberAnalyticsSetSummary`,
    `MemberAnalyticsSet`, preferred-list types).
- **Frontend — deleted-in-full modules**: `memberPivotPresets.ts` + `memberPivotPresets.test.ts`;
  `AddressLabelGenerator.tsx` + `AddressLabelGenerator.test.tsx`; `addressLabelService.test.ts`'s
  address-path assertions realigned (the file survives for the template path).
- **Frontend — consumers to re-wire**: `MemberPivotViews.tsx` (imports `getAvailablePresets`,
  `MemberPivotPreset`, jubilee helpers, `generateAddressLabelPdf`, `resolveAddressMapping`),
  `MemberMailCompose.tsx` (imports `resolveEmailField` **and** `resolveAddressMapping`),
  `MemberAnalyticsPage.tsx`.
- **Config tab**: `TenantAdmin/MembersConfig/membersAnalyticsFold.ts` + the `MembersConfigEditor`
  Analytics slice, and locale strings in `locales/{nl,en}/members.json` (analytics-role / jubilee /
  address-mapping keys **and** `analytics.pivotViews.presetNames.*`).
- **Fixtures**: `scripts/onboarding/members/h-dcn/members_config.json`. **Confirmed during design:
  this fixture does NOT currently author a `jubilee_rule` / `field_roles` / `address_mapping` slice**
  (grep returns no analytics-block hits). The fixture step is therefore a **verify-and-assert-clean**
  no-op, not a deletion — but it is kept in the plan so the grep gate explicitly covers it.
- **`member-analytics` spec**: `requirements.md` (R9.1–R9.4; role/jubilee/address clauses of
  R4.2/R4.3/R4.10/R4.12; the fixed/calculated preset clauses of R4.2/R4.3), `tasks.md` (6.1–6.4, 7.6,
  role parts of 7.2/8.2/8.3/9.2, the preset-table/serving-fn/dropdown tasks), `design.md` (C4 preset
  table), `tasks.meta.json`.

## Expected Behavior

### Preservation Requirements (what must stay unchanged — the non-buggy inputs)

**Unchanged behaviors (bit-for-bit):**

- Building, saving, reloading, and rerunning a **generic pivot/list set** — group-by aggregates and
  filtered lists with their own `applyDefinitionFilters` equality filters (e.g. `{ clubblad: 'Papier' }`).
  The generic Dynamic Pivot Views feature and the Members-owned saved-set DynamoDB store are untouched.
- **CSV export** (`csvExport.ts`), **SES mail send** (`POST /members/mail/send`, worker send), and
  **template-driven labels** (`composeLabelLines` / `MemberLabelsPanel` / `generateLabelTemplatePdf`)
  — identical output, recipient email resolved from the field config.
- The **Overview** summary and the **age / years-member violin distributions** over the filtered
  dataset.
- The resolved **field config** for every tenant: the identical set of fixed ⊕ overlay ⊕ calculated
  fields, functional groups, scope config, lifecycle/mail config, field ordering — only the
  `analytics` role-config member is removed.
- **Server-side scope** (`resolve_scope_access` / `_in_scope`) — the removal touches no scope path.
- **STR BNB** and all other reporting that reuses the shared violin / pivot / PlotlyChart toolkits.
- **Member records** in `sam-members` — a hard invariant; never read-for-mutation, never written.

**Scope — inputs completely unaffected by the fix:**

- Any artifact that does not exposes/store/serve/author/test the role/jubilee/address-mapping/preset
  machinery.
- The generic analytics-SET feature in all its forms (routes, services, audit, saved sets).

> The actual *correct* post-removal behavior (the manifest clean, equivalences reachable) is in the
> Correctness Properties below. This section fixes what must NOT change. Note explicitly: the
> **predefined presets themselves are NOT preserved** — they are removed, so no preset is a non-buggy
> input (bugfix 3.2). The surviving guarantee is only that each subset remains *reachable generically*.

## Hypothesized Root Cause

This is a deliberate dead-but-alive feature, not a defect from a single faulty line, so the "root
cause" is architectural duplication rather than a bug to re-hypothesize. The analysis the removal
relies on:

1. **Redundant vocabulary.** The role/jubilee/address-mapping config is a second way to express what
   the generic pivot already does with field-name group/filter + user-chosen columns. Its mere
   presence (served, tested, spec-mandated) is the defect.
2. **Cross-plane entanglement.** The role-config slice is authored on the Flask param plane
   (`members_parameters.json`), projected through DynamoDB, read by the SAM reader, served by the SAM
   writer, and consumed by the frontend. A naïve top-down delete breaks the build mid-way; the fix
   must sever leaves first.
3. **Mixed modules.** `analyticsConfig.ts`, `addressLabelService.ts`, `index.ts`, and `types/members.ts`
   each contain BOTH removed and surviving symbols — so they are sliced, not deleted, and the slicing
   must not touch the surviving template-label path (confirmed to read no `analytics.*`).
4. **Token collision.** `analytics` names both the removed role-config and the preserved analytics-SET
   feature; an over-broad delete would gut a shipped feature. The manifest's four specific patterns,
   not the bare word, bound the removal.

## Correctness Properties

Property 1: Bug Condition — Role/Jubilee/Address/Preset Machinery Fully Removed

_For any_ artifact where the bug condition holds (`isBugCondition` returns true), after the removal
(F') there SHALL be no such artifact: the role/jubilee/address-mapping machinery and the entire
preset subsystem are gone with no stubs, the served `GET /members/field-config` payload omits the
`analytics` role-config key, and the four grep-manifest patterns return **zero non-historical hits**
(excluding build artifacts, vendored deps, caches, and removal-recording prose). Operationally:
`grep(P, non_historical) = ∅` AND the catalog drift guard is GREEN AND every touched suite is GREEN.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.9**

Property 2: Preservation — Non-Machinery Behavior Identical

_For any_ input where the bug condition does NOT hold (`isBugCondition` returns false), the fixed
code SHALL produce the same result as the original — `F(X) = F'(X)` — preserving the generic pivot
(incl. `applyDefinitionFilters`, through which every removed-preset subset is rebuilt), CSV/mail/
template-label exports, Overview + violins, the resolved field config (minus only the `analytics`
role-config member), scope resolution, and all `sam-members` records.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9**

Property 3: Equivalence Gate — Every Removed Capability Reachable Generically

_For any_ removed capability — including each of the eight presets and each removed export path —
there SHALL exist a documented generic-pivot equivalent (the EQUIVALENCE GATE table below), verified
at code level **before** deletion, so no capability is lost by the removal.

**Validates: Requirements 2.8**

## Fix Implementation

### EQUIVALENCE GATE (checked at code level BEFORE any deletion — bugfix 2.8)

Each row names the removed construct and the concrete generic-pivot equivalent, with the surviving
code that provides it. The gate is a review artifact; a removal step for a construct is unblocked
only once its row is confirmed.

| # | Removed capability | Generic-pivot equivalent | Surviving mechanism (confirmed in code) |
|---|---|---|---|
| 1 | preset `membership-types` (count) | group-by aggregate on `membership_type` | `MemberFieldPicker` groupColumns + `executeMemberPivot` COUNT |
| 2 | preset `birthday-birth-month` (list) | filtered list on `birth_month` + user columns | `applyDefinitionFilters({ birth_month })` + list columns |
| 3 | preset `jubilees` (list) + jubilee-rule selector | filter the calculated `years_member` field | `applyDefinitionFilters` equality on `years_member` (calculated field unchanged) |
| 4 | preset `new-members` (list) + joined-after selector | filter `joined_date` (user applies joined-after) | `applyDefinitionFilters` on `joined_date` |
| 5 | preset `cancellations` (role `cancellation_date`) | equality filter on the field directly | `applyDefinitionFilters({ <field>: ... })` |
| 6 | preset `clubblad-paper-country` (role `clubblad_paper`) | `applyDefinitionFilters({ clubblad: 'Papier' })` + group-by `country` | `applyDefinitionFilters` + groupColumns |
| 7 | preset `clubblad-digital` (role `clubblad_digital`) | equality filter on the field + list columns | `applyDefinitionFilters` |
| 8 | preset `referral-source` (role `referral_source`) | group-by aggregate on the field | groupColumns + COUNT |
| 9 | `AddressLabelGenerator` / `composeAddresses` / `generateAddressLabelPdf` / `resolveAddressMapping` | template-driven labels | `composeLabelLines` / `generateLabelTemplatePdf` / `MemberLabelsPanel` — reads **no** `analytics.*` (confirmed) |
| 10 | `resolveEmailField` `field_roles` branch | email resolved from the field config | `resolveEmailField` typed-`email`-then-`CONVENTIONAL_EMAIL_KEYS` body (surviving) |
| 11 | CSV/mail recipient columns via roles | user's own column selection on the pivot result | `csvExport.ts` + `MemberMailCompose` field-config resolution |

### Empty Pivot Views entry point (bugfix §3 — minimal, composed from existing blocks)

With the preset subsystem gone, the Pivot Views dropdown's **preset `<optgroup>` disappears**; only
the saved-member-set `<optgroup>` remains, which is empty for a tenant with no saved sets. To keep
the generic view-building surface **discoverable** (not a dead dropdown), the design:

- Removes the preset-sourced `SelectableSet` entries and the `getAvailablePresets` memo from
  `MemberPivotViews.tsx`; the `sets` list becomes saved-models-only.
- When there are **no saved sets**, renders the existing shared `AnalyticsStateNotice` (already
  imported in the panel, steering 32/37 reuse) in an **empty-state hint** variant: a bilingual line
  (new `analytics.pivotViews.emptyHint.*` locale keys, replacing the removed `presetNames.*`) telling
  the user to build a view by picking fields to group/filter, with the existing **New set** button
  (`MemberFieldPicker`) as the single call to action. No new component, no dead control.
- Keeps the Execute button, `MemberFieldPicker` compose/save lifecycle, `PivotResultTable`, and the
  export slot (CSV / mail / template-labels) exactly as-is — these are the generic surface.
- Removes the jubilee-year and joined-after-year selectors and their state
  (`showsJubileeSelector` / `jubileeYearOptions` / `showsJoinedAfterSelector` / `joinedYearOptions`
  and the `usesJubileeRule` / `usesJoinedAfterFilter` plumbing), since no preset flags them anymore;
  the generic equivalents are user-authored filters.

### Removal ordering (sequenced to keep the build green at every step)

Ordering follows the confirmed dependency direction: **consumers before definitions**. The frontend
consumes the served payload and its own leaf modules; the SAM writer/reader consume the domain
classes; the domain classes are consumed by everything. Deleting a definition before its consumers
would red the build, so definitions go last. Within the frontend, leaf data modules
(`memberPivotPresets.ts`) and the mixed-module slices are severed before the consumers that import
them are re-wired — but because an unused export does not break compilation, the practical sequence
is: **re-wire consumers to stop importing the removed symbols, then delete the now-unreferenced
symbols/files, then verify the slice.**

**Step A — Frontend leaves + consumers (no plane below depends on the frontend).**

1. Re-wire `MemberPivotViews.tsx`: drop the preset import/memo and the jubilee/joined-after
   selectors; make `sets` saved-models-only; add the empty-state hint; drop the
   `generateAddressLabelPdf` + `resolveAddressMapping` imports and the old-address-path branch
   (the template `MemberLabelsPanel` already covers labels).
2. Re-wire `MemberMailCompose.tsx`: drop the `resolveAddressMapping` import and the
   address-mapping-gated "Attach PDF labels" toggle's dependency on it (keep the toggle gated on the
   presence of a label template, consistent with `MemberLabelsPanel`); switch `resolveEmailField`
   usage to the field-config-only resolution.
3. Delete `memberPivotPresets.ts` and `memberPivotPresets.test.ts`; delete `AddressLabelGenerator.tsx`
   and `AddressLabelGenerator.test.tsx`.
4. Slice `analyticsConfig.ts` (remove role/jubilee/address helpers + the `resolveEmailField` role
   branch; keep `applyDefinitionFilters` / `CONVENTIONAL_EMAIL_KEYS`); update `__tests__/analyticsConfig.test.ts`.
5. Slice `addressLabelService.ts` (remove `composeAddresses` / `generateAddressLabelPdf` / address
   types; keep the template path + Avery geometry); realign `addressLabelService.test.ts`.
6. Slice `analytics/index.ts` barrel re-exports.
7. Remove the Members config **Analytics** tab: `membersAnalyticsFold.ts` + the `MembersConfigEditor`
   Analytics slice; realign the `MembersConfig` suites.
8. Slice `types/members.ts` (`AnalyticsRole`, `MemberAnalyticsConfig`, `FieldConfig.analytics`).
9. Remove the preset / role / jubilee / address-mapping locale keys from `locales/{nl,en}/members.json`
   (incl. `analytics.pivotViews.presetNames.*`); add the `analytics.pivotViews.emptyHint.*` keys.
10. Realign the preset assertions in `MemberPivotViews.test.tsx`, `MemberMailCompose.test.tsx`,
    `labelOptions.test.ts`, `MemberAnalyticsPage.test.tsx`.
    *Green gate A: `cd frontend && npx vitest run src/components/members/analytics src/components/TenantAdmin/MembersConfig`.*

**Step B — SAM read/serve + Flask param slice (depends on the domain classes, consumed by the
frontend payload removed in A).**

11. SAM writer: remove `_serialize_analytics` and the `"analytics"` key from the served field-config
    payload in `_membership_writes.py`.
12. SAM reader: remove `_build_analytics` / `_build_jubilee_rule` / `_build_address_mapping` and the
    `analytics=` wiring on `get_overlay` in `projection_config_reader.py`.
13. Flask param schema: remove the `analytics` object slice from `members_parameters.json`.
    *(No Flask service builder/validator exists — confirmed — so there is nothing else on this plane.)*
    *Green gate B: `cd backend && source .venv/bin/activate && python -m pytest sam/tests/test_field_config_endpoint.py sam/tests/test_members_projection_reader.py -q` (run from the SAM test root per repo layout).*

**Step C — SAM domain classes last (consumed by B; delete only once B stops referencing them).**

14. Remove `AnalyticsRole`, `AnalyticsConfig`, `JubileeRule`, `AddressMapping`, the
    `FieldConfig.analytics` + `TenantOverlay.analytics` members, and their `__all__` entries from
    `field_resolver.py`; remove the `domain/__init__.py` re-exports.
15. Remove the analytics role/alias `note=` prose from `attribute_catalog.py` (metadata only).
    *Green gate C: `python -m pytest sam/tests/test_field_resolver.py sam/tests/test_attribute_catalog.py sam/tests/test_field_classification_traceability.py sam/tests/test_members_modal_mapping_preservation.py -q`.*

**Step D — Fixtures + spec retirement (no code depends on these).**

16. `scripts/onboarding/members/h-dcn/members_config.json` — **verify no role-config slice is
    authored** (confirmed clean during design); assert it stays clean under the grep gate. No edit
    expected; if a slice is found, delete it in this step.
17. Retire the `member-analytics` ACs/tasks (bugfix 2.9): annotate R9.1–R9.4, the
    role/jubilee/address clauses of R4.2/R4.3/R4.10/R4.12, the fixed/calculated preset clauses of
    R4.2/R4.3, the design C4 preset table, and tasks 6.1–6.4 / 7.6 / role parts of 7.2/8.2/8.3/9.2 /
    the preset-table-and-dropdown tasks as **removed by `members-analytics-role-removal`** — so no
    AC/task still mandates any predefined preset.
    *Green gate D: the full grep manifest returns zero non-historical hits.*

### Why this order (justified against inter-module dependencies)

- **A before B**: the frontend is the top consumer; nothing on the SAM or Flask plane imports it.
  Removing the frontend's consumption of the `analytics` payload first means Step B can drop the
  served key without a live consumer breaking.
- **B before C**: `_build_analytics` / `_serialize_analytics` *reference* the domain classes
  (`AnalyticsConfig` et al.). Deleting the classes first would red the reader/writer at import time;
  removing their call sites first makes the classes genuinely unreferenced.
- **C before D**: fixtures and spec prose reference no code symbols for compilation; they are safe to
  do last and serve as the final grep-gate sweep.
- **Mixed modules sliced, not deleted**: `analyticsConfig.ts`, `addressLabelService.ts`, `index.ts`,
  `types/members.ts` each retain surviving symbols (the generic-filter helper, the template-label
  path, the analytics-SET types). The template-label path's independence from `analytics.*` is
  **confirmed in code** (`MemberLabelsPanel` + `composeLabelLines` read no `analytics.*`), so slicing
  the address path cannot regress labels.

## Testing Strategy

### Validation Approach

Two phases, mapped to the bugfix.md Fix-Checking / Preservation-Checking pseudocode. Because this is
a removal, "exploratory" means confirming the current manifest hits exist and the equivalences hold
*before* deleting; fix-checking means the manifest is clean after; preservation-checking means the
surviving suites and the generic pivot behave identically.

### Exploratory Bug Condition Checking (before deletion)

**Goal**: confirm the footprint and the EQUIVALENCE GATE on the UNFIXED code.

**Test Plan / cases**:

1. Run the four grep patterns across `{source ∪ tests}` (excluding build artifacts / node_modules /
   .venv / caches) and confirm the hits match the §Known footprint (expected: non-zero).
2. Walk the EQUIVALENCE GATE table at code level: for each of the 8 presets and the address/mail
   paths, confirm the surviving generic mechanism (`applyDefinitionFilters`, groupColumns + COUNT,
   `composeLabelLines`, field-config `resolveEmailField` body) exists and produces the subset.
3. Confirm `MemberLabelsPanel` / `composeLabelLines` read no `analytics.*` (template-label independence).

**Expected counterexamples**: the manifest returns hits; the Analytics tab, preset dropdown, and
jubilee selector are present — i.e. `C(X)` holds, as designed.

### Fix Checking

**Goal**: `FOR ALL X WHERE isBugCondition(X): NOT exists_after_fix(X)`.

```
FOR ALL X WHERE isBugCondition(X) DO
  ASSERT NOT exists_after_fix(X)
END FOR
ASSERT grep(P, non_historical) = ∅
   AND catalog_drift_guard = GREEN
   AND touched_suites = GREEN
```

**Named suites / checks** (steering 43 "done" gate):

- Grep manifest (four patterns) returns zero non-historical hits.
- Catalog drift guard (SAM `attribute_catalog` traceability): `sam/tests/test_attribute_catalog.py`,
  `sam/tests/test_field_classification_traceability.py` GREEN.
- SAM: `sam/tests/test_field_resolver.py`, `test_members_projection_reader.py`,
  `test_field_config_endpoint.py`, `test_members_modal_mapping_preservation.py` GREEN.
- Frontend: `analyticsConfig.test.ts`, `MemberPivotViews.test.tsx`, `MemberMailCompose.test.tsx`,
  `labelOptions.test.ts`, `MemberAnalyticsPage.test.tsx`, the `MembersConfig` suites GREEN; the
  deleted-in-full tests (`memberPivotPresets.test.ts`, `AddressLabelGenerator.test.tsx`) are gone.

### Preservation Checking

**Goal**: `FOR ALL X WHERE NOT isBugCondition(X): F(X) = F'(X)`.

```
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR
```

Property-based testing is the right tool here (it exercises many inputs across the preserved domain).

**Named suites / observations** (what must stay GREEN, aligned to post-removal behavior):

- Generic pivot incl. `applyDefinitionFilters`: the surviving `analyticsConfig.test.ts` property/example
  cases for `applyDefinitionFilters` (equality narrowing, reserved-key skip, blank-value no-narrow).
- CSV: `csvExport` suite; mail: `MemberMailCompose.test.tsx` (field-config recipient resolution);
  template labels: `MemberLabelsPanel.test.tsx`, `composeLabelLines.test.ts`,
  `MemberTemplateManager.test.tsx`.
- Overview + violins: `MemberOverviewStats.test.tsx`, `MemberDistributions.test.tsx`.
- Scope: `scopeSafety.test.ts` and the SAM scope suites unchanged.
- Field config served shape minus only `analytics`: `test_field_config_endpoint.py` asserts the
  payload omits the `analytics` key and is otherwise identical.
- Member-data invariant: no suite reads/writes `sam-members`; the inventory + re-projection path
  (below) touches only `config#fields`.

### Unit Tests

- Frontend: the sliced `analyticsConfig.ts` keeps only `applyDefinitionFilters` / `resolveEmailField`
  (field-config body) / `CONVENTIONAL_EMAIL_KEYS` tests; the sliced `addressLabelService.ts` keeps
  the template-path + Avery geometry tests.
- SAM: `test_field_resolver.py` loses the `AnalyticsConfig`/role/jubilee/address assertions; the
  served-payload test asserts no `analytics` key.

### Property-Based Tests

- Preservation PBT on `applyDefinitionFilters`: generate random member rows + equality filter maps
  and assert the narrowing matches the pre-removal behavior (the generic path through which every
  removed-preset subset is rebuilt).
- Field-config PBT: generate random overlays WITHOUT an analytics slice and assert the resolved
  field SET / ordering / other slices are unchanged.

### Integration Tests

- `GET /members/field-config` end-to-end: the served payload omits `analytics` and is otherwise
  identical (`test_field_config_endpoint.py`).
- Pivot Views empty-state: with no saved sets, the panel renders the empty-hint + New set CTA and the
  generic compose/execute/export flow works (CSV / mail / template-labels) — `MemberPivotViews.test.tsx`.

## Data Flow (lean) — stored-reference inventory + single re-projection

**Read-only inventory (bugfix 2.11, Validation Honesty gate).** Before any PROD change, run a
read-only inventory across the h-dcn **TEST** and **PROD** DynamoDB tables to report which saved
pivots / analytics-sets reference the removed constructs (a role name, `jubilee_rule`-driven filter
key `years_member`, or an address-mapping slot). This is reporting only — it touches **no** member
records (`sam-members` is never queried) and writes nothing.

- Run through the documented wrapper (steering 41 + `#database`): the DynamoDB read goes against the
  correct account/profile; **identity is sanity-checked** before any PROD read (`aws sts
  get-caller-identity` must print the infra/data account `506221081911`, not `344561557829`), with
  the env-strip belt-and-suspenders if stale static keys linger. The config re-projection goes via
  `PYTHONPATH=backend/src backend/scripts/railway-db.sh python <script>` against the `finance` schema.
- Output: a human-readable report (written under the repo-root `.agent-output/`, git-ignored) listing
  each referencing set by `set_id`/name and the construct it references — the checklist a human
  re-runs manually.

**Single re-projection (bugfix 2.11).** Clean the `config#fields` role-config slice with **one**
re-projection through the existing `projection_sync` path (`backend/src/services/projection_sync.py`)
— the same mechanism that already projects the overlay onto `config#fields`. No staged
production-migration apparatus is introduced; the `analytics` slice simply no longer projects once
Step B/C land, and a single projection run rewrites the row without it. Member records are never read
or written.

**Explicit human sign-off gate (Validation Honesty).** The automation proves only *code-level
equivalence* (the EQUIVALENCE GATE) and produces the *read-only inventory*. It does NOT and cannot
prove every live user-created pivot/set still returns its author's intended result. Therefore a
**person manually re-runs the inventoried pivots/sets in TEST and confirms each still produces the
intended result BEFORE any PROD promotion.** This design asserts code-level equivalence + the
inventory only; it never claims stored user pivots are "validated" by an automated step.

## Cross-plane & steering compliance

- **30/31 (Flask plane)**: the only Flask-plane change is the declarative `analytics` slice in
  `members_parameters.json`; no route/service business logic, `administration` tenant key, or service
  layer is touched. (No Flask service builder exists — confirmed.)
- **35 (SAM plane)**: changes stay within API GW → Lambda → domain → repository → DynamoDB and the
  `tenant_id` key; the `sam/shared` edge is untouched. The reader/writer/domain removals keep each
  plane's conventions and never cross into the Flask plane.
- **33/34 (Change-With-Tests)**: every product-file edit updates its paired test(s) in the SAME step
  (per the green gates A–D); committed fixtures live under their proper paths; no git-ignored scratch
  is substituted for a committed fixture (the inventory report is scratch under `.agent-output/`, not
  a fixture). Paired suites run before each step is "done".
- **41 (shell/DB) + #database**: WSL/bash + POSIX paths; the inventory read and the single
  re-projection go through `backend/scripts/railway-db.sh` / the documented DynamoDB read; identity
  is sanity-checked before PROD; member records never touched.
- **43 (CI/CD)**: the removal is "done" only when the grep manifest is clean, the catalog drift guard
  is green, and the touched suites stay green in the Full Test Suite.
- **Member-data invariant**: `sam-members` is never read-for-mutation or written; only the
  `config#fields` role-config slice is re-projected.

# Bugfix Requirements Document

## Introduction

The Members codebase carries a layer of analytics **"role" machinery** that the product owner
has superseded with the generic **Dynamic Pivot Views** mechanism. It is live, wired end to end,
and fully tested, so it *reads as a real feature* and invites maintainers (human and AI) to
extend it — but it provides **no capability the generic pivot does not already provide** by letting
the user group/filter on fields directly, pick their own columns for CSV/mail, and compose labels
through the template-driven label path.

The machinery in scope:

- **Analytics field roles** — `AnalyticsRole` + `AnalyticsConfig.field_roles` (the generic
  analytics-role → tenant-field-key indirection) and the overlay-only role targets it names
  (`cancellation_date`, `referral_source`, `clubblad_paper`, `clubblad_digital`, `country_detail`);
- **Jubilee rule** — `JubileeRule` / `jubilee_rule` and the jubilee year-selector/filter
  machinery (`candidateJubileeYears`, `selectedJubileeYear`, `applyJubileeYearFilter`,
  `isJubileeYear`, `DEFAULT_JUBILEE_MULTIPLE`, `MAX_JUBILEE_YEAR`, `JUBILEE_YEAR_FILTER_KEY`);
- **Address mapping** — `AddressMapping` / `address_mapping` and
  `resolveAddressMapping` / `composeAddresses` / `generateAddressLabelPdf` and the
  address-mapping-driven `AddressLabelGenerator` (superseded by the template-driven
  `composeLabelLines` / `MemberLabelsPanel` path, which reads **no** `analytics.*`);
- the **entire hardcoded preset subsystem** in `memberPivotPresets.ts` — not just the role-based
  presets but **all eight** predefined presets (the role-backed cancellations / clubblad-paper /
  clubblad-digital / referral-source built on `requiresRoles`, **and** the fixed/calculated
  membership-types / birthday-birth-month / jubilees / new-members) together with the serving
  functions and the Pivot Views preset-dropdown wiring. Per the product owner's decision (Option A),
  no predefined pivots are baked in at all: "in the pivot section the user can define any view based
  on field names and create the subset he needs" — every view is built in the generic Dynamic Pivot
  Views mechanism;
- the whole config read/serve path that carries the above: `AnalyticsConfig` as a slice of the
  resolved `FieldConfig.analytics`, the SAM reader's `_build_analytics` /
  `_build_jubilee_rule` / `_build_address_mapping`, the SAM writer's `_serialize_analytics`,
  the frontend `MemberAnalyticsConfig` type and `analyticsConfig.ts` consumer helpers, the
  Members config **Analytics** authoring tab, and the h-dcn fixture / `members_parameters.json`
  entries that author it.

This is a **dead-but-alive feature**: it executes, it passes its tests, and leaving it in place
misleads future work into enhancing a parallel, redundant analytics vocabulary instead of the one
generic pivot. The fix removes the machinery and its paired tests **and** retires the
`member-analytics` acceptance criteria/tasks that mandate it — **no stubs left behind** — after
proving, at code level, that every capability it provided is reachable through the generic pivot.

> **Scope boundary note.** The generic analytics-SET feature (`analytics_set.py`,
> `_membership_analytics.py`, saved pivot/list sets, the generic Pivot Views surface itself,
> CSV/mail/template-label exports, the Overview + violin distributions) is **NOT** in scope and
> MUST be preserved. Only the *role / jubilee-rule / address-mapping / preset-subsystem* layer is
> removed — and within the Pivot Views surface that means only the **preset dropdown/availability
> wiring** is removed; the generic view-building surface (group/filter on field names) stays. The
> grep token `.analytics` matches both; the removal targets only the role-config members of
> `FieldConfig.analytics` and the constructs listed above, never the analytics-set feature.

### Bug Condition — C(X)

```pascal
FUNCTION isBugCondition(X)
  INPUT:  X of type MembersCodeArtifact        // a source or test file, a config fixture,
                                               // a served field-config payload, or a stored set
  OUTPUT: boolean

  // X triggers the bug when it exposes, stores, serves, authors, or tests any of the
  // role/jubilee/address-mapping/role-based-preset machinery that duplicates the generic pivot.
  RETURN  exposes_analytics_role_machinery(X)        // AnalyticsRole / field_roles / role targets
       OR exposes_jubilee_rule_machinery(X)          // JubileeRule / jubilee_rule / jubilee selector+filter
       OR exposes_address_mapping_machinery(X)       // AddressMapping / address_mapping / resolveAddressMapping
                                                     //   / composeAddresses / generateAddressLabelPdf
       OR exposes_preset_subsystem(X)                 // ANY of memberPivotPresets: MemberPivotPreset type,
                                                     //   PRESETS table (all 8), getAllPresets/getAvailablePresets/
                                                     //   getPresetsWithAvailability/materializePreset/presetFieldsPresent,
                                                     //   or the Pivot Views preset-dropdown wiring
       OR exposes_analytics_role_config(X)           // AnalyticsConfig / _build_analytics / _serialize_analytics
                                                     //   / FieldConfig.analytics role-config members / Analytics authoring tab
END FUNCTION
```

Concretely, the removal checklist is the full-codebase grep manifest below. `C(X)` holds for any
**non-historical** hit (excluding build artifacts under `**/.aws-sam/build/**`, vendored
`**/node_modules/**`, `**/.venv/**`, Vitest caches, and prose in spec/history docs that *records*
the removal):

- `AnalyticsRole|field_roles|fieldRoles|cancellation_date|referral_source|clubblad_paper|clubblad_digital|country_detail`
- `JubileeRule|jubilee_rule|jubileeRule|usesJubileeRule|candidateJubileeYears|selectedJubileeYear|applyJubileeYearFilter|DEFAULT_JUBILEE|JUBILEE_YEAR|jubileeYear`
- `AddressMapping|address_mapping|addressMapping|resolveAddressMapping|composeAddresses|generateAddressLabelPdf`
- `AnalyticsConfig|_build_analytics|_serialize_analytics|analyticsConfig|hasAnalyticsConfig` (and the role-config members of `.analytics`)

### Known footprint (removal checklist, from the full-codebase scan)

**SAM plane (`sam/members`)** — `domain/field_resolver.py` (`AnalyticsRole`, `AnalyticsConfig`,
`JubileeRule`, `AddressMapping`, and `FieldConfig.analytics` + its `__all__`/`TenantOverlay.analytics`
wiring), `repository/projection_config_reader.py` (`_build_analytics` / `_build_jubilee_rule` /
`_build_address_mapping` and the `analytics=` wiring on `get_overlay`), `domain/_membership_writes.py`
(`_serialize_analytics` + the `"analytics"` key on the served field-config payload),
`domain/attribute_catalog.py` (the role/alias notes), `domain/__init__.py` re-exports; and the paired
SAM suites (`sam/tests/test_field_resolver.py`, `test_members_projection_reader.py`,
`test_field_config_endpoint.py`, and the role/analytics assertions inside
`test_attribute_catalog.py` / `test_field_classification_traceability.py` /
`test_members_modal_mapping_preservation.py`).

**Flask plane (`backend/src`)** — the analytics-config slice in `config/members_parameters.json`,
and any analytics-config builder/validator in `backend/src/services/` that authors/validates
`jubilee_rule` / `field_roles` / `address_mapping` onto the `config#fields` projection.
(`backend/src/routes/members_analytics_audit.py` and `signup_service.py` matched only on the
generic word "analytics" / an unrelated `referral_source` — to be confirmed non-target during design.)

**Frontend (`frontend/src`)** — `components/members/analytics/analyticsConfig.ts` (all role /
jubilee / address-mapping / email-role helpers), **the entire `memberPivotPresets.ts` subsystem**
(the `MemberPivotPreset` type + its `requiresRoles` / `usesJubileeRule` / `requiresFields` fields,
the `PRESETS` table of all **eight** presets — the role-backed cancellations / clubblad-paper /
clubblad-digital / referral-source **and** the fixed/calculated membership-types /
birthday-birth-month / jubilees / new-members — the serving functions `getAllPresets` /
`getAvailablePresets` / `getPresetsWithAvailability` / `materializePreset` / `presetFieldsPresent`,
and the `new-members` joined-after-year preset-specific selector), `MemberMailCompose.tsx`
(`resolveEmailField` via `field_roles`), `AddressLabelGenerator.tsx` + `addressLabelService.ts`'s
`resolveAddressMapping`/`composeAddresses` surface + `labelOptions.ts`, `MemberPivotViews.tsx`
(jubilee selector **and** the Pivot Views panel wiring that renders the preset dropdown/availability
off `getPresetsWithAvailability`) / `MemberAnalyticsPage.tsx`, `types/members.ts` (`MemberAnalyticsConfig` /
`AnalyticsRole` / the `analytics` member of `FieldConfig`), the Members config **Analytics** tab
(`TenantAdmin/MembersConfig/membersAnalyticsFold.ts` + the `MembersConfigEditor` Analytics slice),
locale strings (`locales/{nl,en}/members.json` analytics-role / jubilee / address-mapping keys
**and the preset locale strings `analytics.pivotViews.presetNames.*`**);
and the paired tests (`__tests__/analyticsConfig.test.ts`, `MemberAnalyticsPage.test.tsx`,
`memberPivotPresets.test.ts` (deleted in full), the preset assertions in `MemberPivotViews.test.tsx`,
`AddressLabelGenerator.test.tsx`,
`addressLabelService.test.ts`, `MemberMailCompose.test.tsx`, `labelOptions.test.ts`, and the
analytics-tab assertions in the `MembersConfig` suites).

**Fixtures** — `scripts/onboarding/members/h-dcn/members_config.json` (the authored
`jubilee_rule` / `field_roles` / `address_mapping` slice).

**`member-analytics` spec** — tasks **6.1, 6.2, 6.3, 6.4, 7.6**, the role-based parts of **7.2** and
**8.2/8.3**, and the `field_roles` recipient-resolution part of **9.2**; acceptance criteria
**R9.1–R9.4** in full and the role/jubilee/address-mapping clauses of **R4.2 / R4.3 / R4.10 / R4.12**.
Because the **whole** preset subsystem is removed (not only the role-backed presets), the
`member-analytics` ACs/tasks that defined the **fixed/calculated** presets are **also** retired —
the C4 preset-table definitions and the R4.2/R4.3 clauses covering membership-types /
birthday-birth-month / jubilees / new-members (and the task(s) that built `memberPivotPresets.ts`,
`getAvailablePresets` / `getPresetsWithAvailability` / `materializePreset`, and the Pivot Views
preset dropdown) — so no AC/task still mandates any predefined preset.

## Bug Analysis

### Current Behavior (Defect)

> Each clause describes the live, redundant machinery whose presence IS the defect.

1.1 WHEN the Members field config is resolved and served THEN the system **exposes a
`FieldConfig.analytics` role-config block** (`AnalyticsConfig` with `field_roles` / `jubilee_rule`
/ `address_mapping`) built by the SAM reader's `_build_analytics` and serialized by the writer's
`_serialize_analytics`, duplicating configuration the generic pivot does not need.

1.2 WHEN a tenant admin opens the Members configurator THEN the system **presents an "Analytics"
authoring tab** that lets them map `AnalyticsRole`s to field keys, author a `jubilee_rule`, and
author an `address_mapping` — a parallel configuration vocabulary with no counterpart need in the
generic pivot.

1.3 WHEN the Pivot Views area lists predefined sets THEN the system **offers a whole hardcoded
preset subsystem** (`memberPivotPresets.ts` — the `MemberPivotPreset` type, the `PRESETS` table of
all eight presets, and the serving functions `getAllPresets` / `getAvailablePresets` /
`getPresetsWithAvailability` / `materializePreset` / `presetFieldsPresent`, plus the Pivot Views
preset dropdown wiring): the role-backed presets (cancellations, clubblad-paper, clubblad-digital,
referral-source) materialized from `requiresRoles` via `field_roles`, **and** the fixed/calculated
presets (membership-types, birthday-birth-month, jubilees, new-members) baked in with hardcoded
field keys — all duplicating what a user achieves by building the same view (group/filter on field
names) in the generic pivot directly, against the product owner's "user defines any view" principle.

1.4 WHEN a user runs the Jubilees set THEN the system **drives it through dedicated jubilee-rule
machinery** (`candidateJubileeYears` / `selectedJubileeYear` / `applyJubileeYearFilter` /
`isJubileeYear`, keyed by `JUBILEE_YEAR_FILTER_KEY`), duplicating a generic filter on a calculated
years field.

1.5 WHEN a user generates address labels THEN the system **retains the `address_mapping`-driven
label path** (`AddressLabelGenerator` → `resolveAddressMapping` / `composeAddresses` /
`generateAddressLabelPdf`) in parallel with the template-driven `composeLabelLines` /
`MemberLabelsPanel` path that already supersedes it and reads no `analytics.*`.

1.6 WHEN the mail compose UI resolves the recipient email field THEN the system **consults
`analytics.field_roles`** (`resolveEmailField`'s role branch) before falling back to the field
config, coupling mail to the role machinery.

1.7 WHEN the full-codebase grep manifest is run across source and tests THEN the system **returns
many non-historical hits** for the role / jubilee-rule / address-mapping / role-based-preset tokens
— the machinery is present, wired, and tested.

1.8 WHEN a maintainer reads the `member-analytics` spec THEN the system's **acceptance criteria and
tasks still mandate** the role config (R9.1–R9.4), the **predefined presets** — both the role-based
and the fixed/calculated ones (R4.2/R4.3, design C4), the address-mapping labels (R4.10), and the
role-based email resolution (R4.12) — so the "feature" reads as required and invites extension.

### Expected Behavior (Correct)

> After the fix the machinery is gone, no stubs remain, and `C(X)` no longer holds anywhere.

2.1 WHEN the Members field config is resolved and served THEN the system SHALL **no longer carry
any role-config block** — `AnalyticsConfig`, `AnalyticsRole`, `JubileeRule`, `AddressMapping`, the
`FieldConfig.analytics` role members, `_build_analytics` (+ `_build_jubilee_rule` /
`_build_address_mapping`), and `_serialize_analytics` SHALL be removed, and the served field-config
payload SHALL omit the `analytics` role-config key.

2.2 WHEN a tenant admin opens the Members configurator THEN the system SHALL **present no Analytics
role-config tab** — the `membersAnalyticsFold` and the `MembersConfigEditor` Analytics slice (and
their locale strings) SHALL be removed, with the configurator's save-once / reference-validation
behavior for the surviving slices unchanged.

2.3 WHEN the Pivot Views area lists predefined sets THEN the system SHALL **offer no predefined
preset pivots at all** — the *entire* preset subsystem SHALL be removed: `memberPivotPresets.ts`
(the `MemberPivotPreset` type with its `requiresRoles` / `usesJubileeRule` / `requiresFields`
fields, the `PRESETS` table of all eight presets, and the serving functions `getAllPresets` /
`getAvailablePresets` / `getPresetsWithAvailability` / `materializePreset` / `presetFieldsPresent`
/ the `new-members` joined-after-year preset-specific selector), the Pivot Views panel wiring that
renders the preset dropdown/availability, and the preset locale strings. No predefined set — neither
the role-backed ones (cancellations / clubblad-paper / clubblad-digital / referral-source) nor the
fixed/calculated ones (membership-types / birthday-birth-month / jubilees / new-members) — SHALL be
baked in; the equivalent subsets SHALL be reachable by the user building the view in the generic
Dynamic Pivot Views mechanism (group/filter on field names directly, see 2.8).

2.4 WHEN a user wants a jubilee / anniversary list THEN the system SHALL **provide it through the
generic pivot** by filtering a calculated years-member field — the dedicated jubilee-rule selector
and filter machinery (`candidateJubileeYears` / `selectedJubileeYear` / `applyJubileeYearFilter` /
`isJubileeYear` / `JUBILEE_YEAR_FILTER_KEY` / `jubilee_rule`) SHALL be removed.

2.5 WHEN a user generates address labels THEN the system SHALL **retain only the template-driven
path** (`composeLabelLines` / `generateLabelTemplatePdf` / `MemberLabelsPanel`); the
`address_mapping`-driven `AddressLabelGenerator` / `resolveAddressMapping` / `composeAddresses` /
`generateAddressLabelPdf` surface SHALL be removed.

2.6 WHEN the mail compose UI resolves the recipient email field THEN the system SHALL **resolve it
from the field config alone** (typed-`email` field, then conventional email keys); the
`analytics.field_roles` branch of `resolveEmailField` SHALL be removed.

2.7 WHEN the full-codebase grep manifest is run across source and tests THEN the system SHALL
return **zero non-historical hits** for every token in all four manifest patterns (excluding build
artifacts, vendored dependencies, caches, and prose that records the removal).

2.8 WHEN each removed capability — **including every one of the eight presets** — is checked against
the generic pivot (the EQUIVALENCE GATE, code level, before deletion) THEN the system SHALL
demonstrate that every one is reachable generically, specifically:
- **role-backed subsets** (cancellations / clubblad-paper / clubblad-digital / referral-source) → a
  generic pivot group/filter on that field via `applyDefinitionFilters` (equality filter, e.g.
  `{ clubblad: 'Papier' }`) with user-selected list columns;
- **membership-types** → a generic group-by aggregate on `membership_type`;
- **birthday / birth-month** → a generic filter on `birth_month` (with user-selected list columns);
- **jubilee / anniversary lists** → a generic filter on the calculated years-member field;
- **new-members** → a generic filter on `joined_date` (the joined-after-year filter the user applies
  themselves);
- **address labels** → the template-driven `composeLabelLines` / `MemberLabelsPanel` path (verified
  to read **no** `analytics.*`), with user-selected result columns;
- **CSV / mail recipient columns** → the user's own column selection on the pivot result, email
  field resolved from the field config.

2.9 WHEN a tenant admin, a reviewer, or an AI reads the `member-analytics` spec after the fix THEN
the system's acceptance criteria and tasks SHALL **no longer mandate the removed machinery** —
R9.1–R9.4, the role/jubilee/address-mapping clauses of R4.2/R4.3/R4.10/R4.12, **and the
fixed/calculated preset definitions of R4.2/R4.3 (design C4)** (and tasks 6.1–6.4, 7.6, the role
parts of 7.2/8.2/8.3/9.2, **plus the task(s) that defined the full preset table / serving functions
/ Pivot Views preset dropdown**) SHALL be retired/annotated as removed, so **no predefined preset**
reads as a feature inviting extension.

2.10 WHEN the removed code's paired tests, committed fixtures, and the h-dcn
`members_config.json` are considered THEN the system SHALL **delete or realign them in the same
change** (no test left asserting the old role/jubilee/address-mapping behavior, no fixture still
authoring the removed slice, no git-ignored scratch substituted for a committed fixture), per the
Change-With-Tests contract.

2.11 WHEN the stored-reference inventory is run (read-only) THEN the system SHALL **report** which
saved pivots / analytics-sets in the h-dcn TEST and PROD DynamoDB tables reference the removed
constructs — via the `#database` skill / `backend/scripts/railway-db.sh`, touching **no**
member records (`sam-members`) — and SHALL perform **one** re-projection via the existing
`projection_sync` path to clean the `config#fields` role-config slice; it SHALL NOT introduce a
staged production-migration apparatus.

### Unchanged Behavior (Regression Prevention)

> The non-buggy inputs — everything the removal must leave working, bit-for-bit where it is
> behavior the generic pivot or the surviving module provides.

3.1 WHEN a user builds, saves, reloads, and reruns a **generic pivot/list set** (group-by
aggregate or filtered list with its own definition filters, e.g. `{ clubblad: 'Papier' }` via
`applyDefinitionFilters`) THEN the system SHALL CONTINUE TO behave exactly as before — the generic
Dynamic Pivot Views feature and the Members-module-owned saved-set storage are untouched.

3.2 WHEN a user wants the subsets the fixed/calculated presets used to offer (membership-types,
birthday / birth-month, jubilees / anniversary, new-members) THEN the system SHALL CONTINUE TO let
the user **rebuild each one in the generic Dynamic Pivot Views mechanism** — group by
`membership_type`; filter by `birth_month`; filter the calculated years-member field for
jubilee/anniversary; filter `joined_date` (joined-after-year) for new-members. The surviving
guarantee is only that these subsets remain reachable generically — **no predefined set is offered
any longer** (the fixed/calculated presets are removed too, per the "remove all presets" scope in
2.3), so this clause does NOT preserve any baked-in preset.

3.3 WHEN a user exports a pivot/list result to **CSV**, sends it by **mail** (server-side SES send
with optional attachment), or composes **template-driven labels** (`composeLabelLines` /
`MemberLabelsPanel`) THEN the system SHALL CONTINUE TO produce identical output, with the recipient
email field resolved from the field config.

3.4 WHEN the Overview summary and the age / years-member **violin distributions** are shown over
the filtered dataset THEN the system SHALL CONTINUE TO compute and render them exactly as before.

3.5 WHEN the field config is resolved and served for any tenant THEN the system SHALL CONTINUE TO
return the identical set of fixed ⊕ overlay ⊕ calculated fields, functional groups, scope config,
and lifecycle/mail config — only the `analytics` **role-config** member is removed; the resolved
field SET, ordering, and every other served slice are unchanged.

3.6 WHEN any request resolves scope THEN the system SHALL CONTINUE TO enforce server-side scope
(`resolve_scope_access` / `_in_scope`) identically — the removal touches no scope path.

3.7 WHEN member records are read or written THEN the system SHALL CONTINUE TO leave `sam-members`
entirely untouched — member-data non-destructiveness is a hard invariant; the removal reads
stored references and re-projects config only, never a member record.

3.8 WHEN STR BNB and all other reporting that reuses the shared violin / pivot / PlotlyChart
toolkits render THEN the system SHALL CONTINUE TO render unchanged (the removal does not touch the
shared toolkits).

3.9 WHEN the catalog drift guard and the touched unit/API/SAM/frontend suites run THEN the system
SHALL CONTINUE TO be green, with every surviving test aligned to the post-removal behavior.

## Deriving the Bug Condition (summary for Design)

**Fix Checking** — the bug is fixed for all buggy inputs:

```pascal
// Property: Fix Checking — the role machinery is gone and the manifest is clean.
FOR ALL X WHERE isBugCondition(X) DO
  // After F' (the removal) there SHOULD BE no such X.
  ASSERT NOT exists_after_fix(X)
END FOR

// Operationally, with the four grep patterns P over {source ∪ tests}, excluding
// build artifacts / node_modules / .venv / caches / removal-recording prose:
ASSERT grep(P, non_historical) = ∅
   AND catalog_drift_guard = GREEN
   AND touched_suites = GREEN
```

**Preservation Checking** — non-buggy inputs behave identically:

```pascal
// Property: Preservation Checking
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR
// i.e. generic pivot (incl. applyDefinitionFilters) — through which the user rebuilds every
// subset the removed presets used to offer — CSV/mail/template-label exports, Overview + violins,
// resolved field config (minus the analytics role-config member only), scope resolution, and
// member records are all unchanged. (The predefined presets themselves are NOT preserved; they are
// removed, so no preset is a non-buggy input.)
```

- **F** — the Members code *with* the role/jubilee/address-mapping machinery and the full preset subsystem.
- **F'** — the Members code *after* removal: the machinery gone, paired tests/fixtures realigned,
  the `member-analytics` ACs/tasks retired, the generic-pivot equivalences in place.

## Validation Honesty (explicit human sign-off gate)

The automation in this spec validates **code-level equivalence** (the EQUIVALENCE GATE, 2.8) and
produces a **read-only inventory** of stored references in TEST/PROD (2.11). It does **not**, and
cannot, prove that every live user-created pivot/analytics-set in TEST or PROD still returns the
result its author intended after the role machinery is removed. Therefore:

- **Live stored pivots/sets in TEST and PROD can only be validated by a MANUAL human checklist** —
  a person re-runs the inventoried pivots/sets and confirms each still produces the intended
  result — **before any PROD promotion**. This is an explicit human sign-off gate, not an
  automated claim. The spec MUST NOT assert that stored user pivots are "validated" by any
  automated step; it asserts only code-level equivalence and the stored-reference inventory.

## Steering compliance (hard constraints the Design must honor)

- **Cross-plane boundaries** — respect `30`/`31` (Flask plane: routes/services, `administration`
  tenant key, service layer) and `35` (SAM plane: API GW → Lambda → domain → repository →
  DynamoDB, `tenant_id` tenant key, `sam/shared` edge). The role-config slice spans both planes;
  the removal must stay within each plane's conventions and not cross them.
- **Testing** — `33`/`34`: paired tests updated in the SAME change (Change-With-Tests contract),
  committed fixtures under the proper fixtures path, no git-ignored scratch substituted; run the
  paired suites before "done".
- **Shell / DB** — `41` + `#database` skill: WSL/bash + POSIX paths; the TEST/PROD inventory and
  the single re-projection go through the documented wrappers (`backend/scripts/railway-db.sh`,
  DynamoDB read), identity sanity-checked where it matters; member records never touched.
- **CI/CD** — `43`: the removal is "done" only when the grep manifest is clean, the catalog drift
  guard is green, and the touched suites stay green in the Full Test Suite.

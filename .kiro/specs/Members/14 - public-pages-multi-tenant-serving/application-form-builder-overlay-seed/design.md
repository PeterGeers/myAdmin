# Application Form Builder Overlay-Seed Bugfix Design

## Overview

The Application Form Builder authors ONE in-memory working `field_overlay` object and commits it
once via an identity-keyed Change-Op list (`deriveFieldConfigChangeOps` →
`saveFieldConfigChangeOps` → `PUT /members/config/fields`). The builder must seed that working
overlay — and the diff baseline it compares against — from the authoritative stored state on load.

The bug: `ApplicationFormBuilder.load()` seeds from `cfg.field_overlay`, the RAW stored
`config#fields` overlay. Per steering 39 and the `FieldConfig` doc in
`frontend/src/types/members.ts`, the current SAM module read NO LONGER surfaces that raw key — it
resolves the overlay into each `fields[]` entry (carrying `application_required`, `format`,
`functional_group`, `origin`, etc.) and leaves `field_overlay` `undefined`. So the builder seeds
both the working overlay AND the baseline to `{}`, and every per-field panel falls back to
platform defaults even though the attributes are stored and served.

The sibling editor already solved this. `MembersConfigEditor.tsx` (load, ~line 132) seeds via
`flatViewToOverlay(resolvedConfig)`, reconstructing the authoring overlay from the resolved
`fields[]` / `functional_groups`. The fix mirrors that single call in `ApplicationFormBuilder`.

The fix is minimal and local: swap the overlay/baseline seed in `load()` to
`flatViewToOverlay(cfg)` and correct the now-wrong comment that claims the reader serves
`field_overlay` in wire shape. `flatViewToOverlay` already exists and is unit-tested; we import it,
never duplicate it.

### Deployment note (FRONTEND-only)

This change is FRONTEND-only. It ships through the frontend deploy (`deploy-frontend.yml`, `main`
→ GitHub Pages). There is NO SAM/backend change and NO Lambda/layer redeploy — the module read
already serves the attributes. The user's TEST admin SPA is the local Vite dev server
(`VITE_APP_ENV=test`, `localhost:3000`), so after the fix lands the user must RELOAD the dev
server to pick up the new bundle; no `sam deploy` is involved.

## Glossary

- **Bug_Condition (C)**: The builder loads a resolved field config whose `field_overlay` key is
  absent (the current module read) and whose resolved `fields[]` carry application attributes.
- **Property (P)**: The builder's working overlay and diff baseline reflect the stored/served
  per-field application attributes (reconstructed from `fields[]`), so the per-field panels show
  the authored values and a fresh load is not dirty.
- **Preservation**: Seeding behavior for configs with no authored application attrs, the
  one-object/one-save contract (fresh load not dirty; one edit → one `set_field_application` op),
  and the form-shell seeding — all must remain unchanged.
- **flatViewToOverlay(cfg)**: Pure function in `./flatViewToOverlay` that reconstructs the
  authoring overlay (`{ fields, fixed_overrides, functional_groups }`) from the resolved
  `FieldConfig` (`fields[]` + `functional_groups`). Seeds working AND baseline from the same
  reconstruction, so the fresh-load diff is empty by construction.
- **field_overlay**: The RAW stored `config#fields` overlay key. On the current SAM module build
  it is `undefined` on the field-config read (steering 39) — it must no longer be used as the seed.
- **getMembersFieldConfig()**: Returns the resolved `FieldConfig` (`fields[]`, `functional_groups`,
  `slug`, `mail_config`). It is the SAME source `MembersConfigEditor` consumes — the shape
  `flatViewToOverlay` is built for.
- **FieldConfigField.origin**: `'fixed' | 'variable' | 'calculated'`. A tenant-added field is
  `'variable'` (bucketed into `fields[bareKey]` by `flatViewToOverlay`).

## Bug Details

### Bug Condition

The bug manifests when `ApplicationFormBuilder.load()` seeds its working overlay from
`cfg.field_overlay` while the resolved config does NOT carry that raw key (the current module read)
but DOES carry resolved `fields[]` entries with authored application attributes. The seed resolves
to `{}`, so the per-field panels fall back to platform defaults and the diff baseline is wrong.

**Formal Specification:**
```
FUNCTION isBugCondition(cfg)
  INPUT: cfg of type FieldConfig (the resolved field config from getMembersFieldConfig)
  OUTPUT: boolean

  RETURN cfg.field_overlay IS undefined
         AND EXISTS f IN cfg.fields WHERE
               (f.application_required = true
                OR f.application_visible = true
                OR f.format IS NOT empty
                OR f.application_choices IS NOT empty)
END FUNCTION
```

### Examples

- Resolved config with no `field_overlay`, `fields[]` containing `iban` with
  `origin: 'variable'`, `application_required: true`, `format: {checker: 'IBAN'}`,
  `functional_group: 'financial'`. Expected: IBAN panel shows required CHECKED, format select =
  `IBAN`. Actual (unfixed): required unchecked, format empty.
- Same config with a `payment_method` field `application_required: true`. Expected: required
  CHECKED. Actual (unfixed): required unchecked.
- A fresh load of the above. Expected: builder is NOT dirty (empty save diff). Actual (unfixed):
  baseline is `{}` while the panels (if they read resolved `fields[]`) diverge — the diff baseline
  no longer reflects the stored attributes.
- Edge: resolved config with no authored application attrs. Expected AND actual: panels at
  platform defaults, load not dirty (this case already works and must stay working).

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- A config with NO authored application attributes continues to seed panels at platform defaults
  and a fresh load is NOT dirty.
- The one-object/one-save contract: a fresh unedited load produces an EMPTY save diff; editing one
  field produces EXACTLY one `set_field_application` Change-Op for that field.
- Form-shell seeding (slug/URL display from `cfg.slug`, embed origins, consent from `config#mail`)
  is unchanged — this fix touches only the field-overlay seed, not `mailConfigToShellValues`.
- A failed field-config fetch still resolves to `null`, shows "unavailable", and NEVER blocks
  authoring.

**Scope:**
All loads that do NOT satisfy the bug condition should be unaffected by this fix. This includes:
- Configs with no authored application attributes.
- The form-shell / slug / readiness seeding path.
- The save/Change-Op derivation path (the differ is unchanged; only its baseline input changes to
  the correct reconstruction).

## Hypothesized Root Cause

This is not a hypothesis — the root cause is verified end to end. It is recorded here as the
confirmed cause:

1. **Wrong seed source (CONFIRMED root cause)**: `ApplicationFormBuilder.load()` does
   `const overlayValue = (cfg?.field_overlay as MembersConfigValue) ?? {}` then
   `setOverlay(overlayValue); setBaseline(JSON.stringify(overlayValue))`. Because the current SAM
   module read leaves `cfg.field_overlay` `undefined` (steering 39; `FieldConfig` doc), the seed is
   always `{}`. The resolved attributes live in `cfg.fields[]`, which this path ignores.

2. **Stale comment**: the adjacent comment block asserts the reader serves the overlay in authoring
   wire shape (`fields` / `fixed_overrides` / `functional_groups`) with no translation. That is no
   longer true and misleads future readers; it must be corrected.

3. **Confirmed NOT the cause**: the write path (`config#fields` row persists the attributes), the
   module read (`_serialize_field` emits `application_required` + `format` per field), and the
   per-field panel components are all correct. The sibling `MembersConfigEditor` already seeds via
   `flatViewToOverlay` and works.

## Correctness Properties

Property 1: Bug Condition - Resolved application attributes seed the builder panels

_For any_ input where the bug condition holds (isBugCondition returns true: `field_overlay` absent
and `fields[]` carries authored application attributes), the fixed `load()` SHALL seed the working
overlay via `flatViewToOverlay(cfg)` so that selecting an affected field shows its per-field
application attributes at the stored/served values (e.g. required toggle CHECKED, format select =
the stored `format.checker`).

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Unauthored configs, one-save contract, and form-shell seeding

_For any_ input where the bug condition does NOT hold (isBugCondition returns false), the fixed
`load()` SHALL produce the same observable result as the original: panels at platform defaults for
configs with no authored attrs, a fresh unedited load that is NOT dirty (empty save diff), exactly
one `set_field_application` op per single edit, and unchanged form-shell/slug seeding.

**Validates: Requirements 3.1, 3.2, 3.3**

## Fix Implementation

### Changes Required

**File**: `frontend/src/components/TenantAdmin/MembersConfig/ApplicationFormBuilder.tsx`

**Function**: `load()` (the overlay-seed block, ~lines 143-148)

**Specific Changes**:
1. **Import `flatViewToOverlay`**: add `import { flatViewToOverlay } from './flatViewToOverlay';`
   (reuse the existing module — do NOT duplicate it). `MembersConfigEditor` imports it the same way.

2. **Seed working overlay + baseline from the reconstruction**: replace
   ```ts
   const overlayValue = (cfg?.field_overlay as MembersConfigValue) ?? {};
   setOverlay(overlayValue);
   setBaseline(JSON.stringify(overlayValue));
   ```
   with
   ```ts
   const overlayValue = flatViewToOverlay(cfg);
   setOverlay(overlayValue);
   setBaseline(JSON.stringify(overlayValue));
   ```
   Working overlay and baseline are seeded from the SAME reconstruction, preserving the
   one-object/one-save contract (fresh load not dirty; one edit → one op — see `flatViewToOverlay`
   docstring "Safety: why a fat reconstruction is harmless").

3. **Correct the stale comment**: rewrite the comment block that claims the reader serves
   `field_overlay` in authoring wire shape. The new comment states that the SAM read resolves the
   overlay into `fields[]` / `functional_groups` and no longer surfaces the raw `field_overlay`
   (steering 39), so the builder reconstructs the authoring overlay from the resolved config via
   `flatViewToOverlay`, mirroring `MembersConfigEditor`.

No other files change. `getMembersFieldConfig()` already returns the resolved `FieldConfig`
(`fields[]`, `functional_groups`) that `flatViewToOverlay` consumes — the same source
`MembersConfigEditor` uses — so no service change is needed.

## Testing Strategy

### Validation Approach

Two phases: first surface a counterexample that demonstrates the bug on the unfixed builder, then
verify the fix restores the seeded attributes and preserves the unauthored-config / one-save /
form-shell behavior. Frontend tests run under vitest per steering `33-frontend-testing`, reusing
the existing `ApplicationFormBuilder.test.tsx` harness and mocks (the `getMembersFieldConfig` mock,
the real `saveFieldConfigChangeOps`, the `applyFieldConfigChangeOps` spy).

### Exploratory Bug Condition Checking

**Goal**: Surface a counterexample demonstrating the bug BEFORE the fix, confirming the root cause.

**Test Plan**: Render `ApplicationFormBuilder` with a mocked `getMembersFieldConfig` returning a
REALISTIC resolved config that has NO `field_overlay` key and a tenant-added `iban` field in
`fields[]` carrying `origin: 'variable'`, `application_visible: true`, `application_required: true`,
`format: {checker: 'IBAN'}`, `functional_group: 'financial'`, plus a `payment_method` field with
`application_required: true`. Select the IBAN field (open its per-field attribute modal/panel) and
assert the required toggle is CHECKED and the format select value is `IBAN`; assert `payment_method`
required is CHECKED. Reuse the existing builder test harness/mocks (grep
`ApplicationFormBuilder.test.tsx`, `renderWithLiveOverlay`, the Phase-3 matrix fixtures). Prove
against the resolved-config shape the real GET returns, NOT a hand-built `field_overlay`.

**Test Cases**:
1. **IBAN required toggle**: select IBAN, assert required CHECKED (will fail on unfixed code).
2. **IBAN format select**: select IBAN, assert format value = `IBAN` (will fail on unfixed code).
3. **payment_method required toggle**: assert required CHECKED (will fail on unfixed code).

**Expected Counterexamples**:
- On unfixed code the toggles are unchecked and the format select is empty because the working
  overlay seeded from `cfg.field_overlay` (undefined) is `{}`, so the panels fall back to defaults.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed `load()` seeds the
panels from the resolved attributes.

**Pseudocode:**
```
FOR ALL cfg WHERE isBugCondition(cfg) DO
  overlay := flatViewToOverlay(cfg)
  render ApplicationFormBuilder seeded with overlay
  ASSERT panel(affectedField).required == cfg.fields[affectedField].application_required
  ASSERT panel(affectedField).format   == cfg.fields[affectedField].format.checker
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed builder
behaves the same as the original.

**Pseudocode:**
```
FOR ALL cfg WHERE NOT isBugCondition(cfg) DO
  ASSERT seedingBehavior_original(cfg) = seedingBehavior_fixed(cfg)
END FOR
```

**Testing Approach**: Property-based / matrix testing is preferred for preservation because it
exercises many config shapes and catches edge cases a single example would miss, giving a stronger
guarantee that unauthored-config seeding, the one-save contract, and form-shell seeding are
unchanged.

**Test Plan**: Observe behavior on UNFIXED code for non-bug configs first, then write tests capturing
that behavior and confirm they pass before the fix.

**Test Cases**:
1. **Unauthored config seeds defaults**: a config with no authored application attrs seeds panels
   at platform defaults (passes on unfixed code, must still pass).
2. **Fresh load not dirty**: the save diff from an unedited fresh load is EMPTY (Save disabled).
3. **One edit → one op**: editing one field yields exactly one `set_field_application` op.
4. **Form-shell seeding unchanged**: slug/embed/consent seed from `config#mail` + `cfg.slug` as
   before.

### Unit Tests

- `load()` overlay/baseline seeding from a resolved config (bug-condition and non-bug-condition).
- Per-field panel reflects seeded `application_required` / `format` for a tenant-added field.
- Save disabled on a fresh unedited load.

### Property-Based Tests

- Across generated resolved configs with varying authored attributes, the seeded panel values
  equal the resolved `fields[]` attributes (fix check).
- Across generated non-bug configs, the fresh-load diff is empty (preservation).

### Integration Tests

- Full builder load → select affected field → observe attributes; then edit one field → Save fires
  exactly one Change-Op write (`applyFieldConfigChangeOps`), with no whole-overlay write.

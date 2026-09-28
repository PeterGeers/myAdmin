# Implementation Plan

## Overview

Build the shared `LazySelect` component + `useLazyOptions` hook (foundation, fully tested), then
validate the concept stepwise in three real screens — Members, the FIN Transaction modal, and the FIN
Import Invoice modal — each proving a different options shape, before publishing the guide and
registering the block. Frontend-only; follows `32-frontend-ui.md`, `33-frontend-testing.md`, and the
building-block template in `37-shared-building-blocks.md`.

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"], "dependsOn": [] },
    { "wave": 2, "tasks": ["2"], "dependsOn": ["1"] },
    { "wave": 3, "tasks": ["3"], "dependsOn": ["2"] },
    { "wave": 4, "tasks": ["4"], "dependsOn": ["3"] },
    { "wave": 5, "tasks": ["5"], "dependsOn": ["4"] },
    { "wave": 6, "tasks": ["6"], "dependsOn": ["5"] },
    { "wave": 7, "tasks": ["7"], "dependsOn": ["6"] },
    { "wave": 8, "tasks": ["8"], "dependsOn": ["7"] },
    { "wave": 9, "tasks": ["9"], "dependsOn": ["8"] }
  ]
}
```

Sequential by design: the hook underpins the component; the component underpins each validation
screen; the three validation screens run in the agreed order (Members → Transaction → Import Invoice)
so each proves a different options shape before the next.

## Tasks

- [x] 1. Types and foundation
  - Create `frontend/src/components/common/lazySelect.types.ts` with `LazyOption<V>`,
    `LazyOptionsSource<V>` (array | async fn), `LazySelectProps<V>`, `UseLazyOptionsResult<V>`
  - Add a `resolveOptionLabel(opt, getOptionLabel?, lang?)` helper matching the Members
    `resolveLabel` convention (localized map or string → string)
  - _Requirements: 1.2, 4.1, 5.1_

- [x] 2. Implement useLazyOptions hook
  - [x] 2.1 Create `frontend/src/hooks/useLazyOptions.ts`
    - Accept `LazyOptionsSource<V>` + optional `depKey`; return
      `{ options, isLoading, error, ensureLoaded, reload }`
    - Array source → passthrough, `ensureLoaded` no-op; function source → resolve on first
      `ensureLoaded`, cache, expose loading/error; changed `depKey` invalidates cache; `reload` forces
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [x] 2.2 Unit tests `frontend/src/hooks/__tests__/useLazyOptions.test.ts`
    - array passthrough; resolve-on-ensureLoaded (loading→settled); rejection sets error + options=[];
      cache reuse on re-open; `reload` re-resolves; `depKey` change re-resolves
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [x] 2.3 Property test `frontend/src/hooks/__tests__/useLazyOptions.property.test.ts`
    - For any array, `options` equals the input; for any resolver returning array X, post-ensureLoaded
      `options` equals X (fast-check ≥100 iters, `{ timeout: 30000 }`)
    - _Requirements: 9.5_

- [x] 3. Implement LazySelect component
  - [x] 3.1 Create `frontend/src/components/common/LazySelect.tsx`
    - Rest: option label for in-set, raw value (`renderMissingValue`) for out-of-set, placeholder only
      when value empty; disabled/read-only → plain non-interactive text
    - Always-searchable: open on click/Enter/Space/ArrowDown (`ensureLoaded`); type-to-filter
      (case-insensitive substring on label); close on Escape/outside/blur with NO value change (Escape
      restores focus); pick → `onChange(value)` + close; never coerce value
    - Self-owned `role="listbox"`/`role="option"` popup (not a Chakra Menu → test-mock safe); apply
      `filterOption`; never inject the out-of-set value as a selectable option; loading + error rows
    - ARIA combobox (`role`, `aria-expanded`, `aria-controls`, `aria-selected`, `aria-activedescendant`);
      keyboard ArrowUp/Down/Home/End/Enter/Escape; dark-theme defaults + `size` + overrides
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.4, 4.2, 4.3, 5.1, 5.2, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3_
  - [x] 3.2 Unit tests `frontend/src/components/common/__tests__/LazySelect.test.tsx`
    - rest label in-set / raw out-of-set / placeholder empty; disabled+read-only no open; open
      triggers; type-to-filter; close-without-change; pick emits value + closes; `filterOption` hides
      options; out-of-set value absent from list; async loading + error rows; ARIA attributes
    - Import `render` from `@/test-utils`; Chakra auto-mocked
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 4.2, 4.3, 5.1, 5.2, 6.1, 6.2_
  - [x] 3.3 Property test `frontend/src/components/common/__tests__/LazySelect.property.test.tsx`
    - Value Preservation, No Silent Coercion, Pick Fidelity, Filter Soundness (fast-check ≥100 iters,
      `{ timeout: 30000 }`)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 4. Checkpoint — foundation complete
  - LazySelect + useLazyOptions compile (`npx tsc -b`); all new unit + property tests pass
    (`npx vitest run`)
  - Ask the user if questions arise

- [x] 5. Validation 1 — Members app (eager enum + async feed; remove s5j stopgap)
  - [x] 5.1 Adopt LazySelect in `frontend/src/components/members/MembersFieldFormBody.tsx`
    - Replace the SINGLE generic dropdown code path in `FieldRow` — the
      `if (isScope || field.type === 'reference' || rich)` branch that today renders a `<Select>` via
      `renderOptions` — with `LazySelect`. Because the form is parameter-driven (one `FieldRow` renders
      every resolved field), this ONE change covers EVERY enum/reference/scope dropdown in the Members
      modal, not a fixed list: e.g. Gender, Clubblad, Motorbrand, region, membership_type, and any
      other rich-enum / reference field the tenant's field config defines now or later. Do NOT
      enumerate fields in code.
    - Options wiring by source shape (all fit `LazyOptionsSource`):
      - scope dimension (region) and rich/`reference` enums (Gender, Clubblad, Motorbrand, …) → eager
        `LazyOption[]` derived from the resolved field config (`richEnumOptions` / `regionValues`);
      - membership_type → async source (`listMembershipTypes()`), the on-open fetch case;
      - pass `filterOption` for value-level role gating (`optionsForCaller`); keep read-only/calculated
        fields disabled (never editable).
    - REMOVE the synthetic-current-value prepend in `renderOptions` (its job — keep an out-of-set value
      visible — is now LazySelect's Requirement 1); leave a comment pointing to
      `.kiro/specs/Common/Frameworks/lazy-select/`
    - _Requirements: 8.1, 8.4, 8.5_
  - [x] 5.2 Update paired Members tests (Change-With-Tests Contract)
    - Update `MembersFieldFormBody.currentValue.test.tsx` and `.membershipType.test.tsx` to the
      LazySelect behavior: out-of-set current value still displayed, not offered as an option; do NOT
      weaken assertions; surface any contradiction
    - _Requirements: 8.1, 9.1, 9.2_
  - [x] 5.3 Validation checkpoint
    - Members modals compile; Members tests pass; stopgap removed with pointer; verify a legacy region
      value renders (not blank) and is preserved on an unrelated edit
    - _Requirements: 8.1, 8.4_

- [x] 6. Validation 2 — FIN Transaction modal (query-backed source)
  - [x] 6.1 Adopt LazySelect in `frontend/src/components/BankingTransactionModal.tsx`
    - Replace `AccountSelect` for Debet/Credit with LazySelect fed by an async chart-of-accounts
      source (via `useAccountLookup`); confirm typeahead over the account list and tolerate-legacy for
      an account no longer present
    - _Requirements: 8.2, 8.4, 8.5_
  - [x] 6.2 Update paired test `frontend/src/__tests__/BankingTransactionModal.test.tsx`
    - Assert the LazySelect behavior for Debet/Credit; keep existing modal behavior assertions
    - _Requirements: 8.2_
  - [x] 6.3 Validation checkpoint — modal compiles; test passes; an out-of-list account displays and
    is preserved
    - _Requirements: 8.2, 8.4_

- [x] 7. Validation 3 — FIN Import Invoice modal (long external list + query-backed)
  - [x] 7.1 Adopt LazySelect in `frontend/src/components/PDFUploadForm.tsx`
    - Replace the account selectors (`AccountSelect`) and the folder `<datalist id="folder-options">`
      with LazySelect fed by async sources: chart of accounts, and Google-Drive folder names (the long
      external list)
    - _Requirements: 8.3, 8.4, 8.5_
  - [x] 7.2 Update the paired PDFUploadForm test(s)
    - Assert LazySelect behavior for accounts + folder; keep upload-flow assertions
    - _Requirements: 8.3_
  - [x] 7.3 Validation checkpoint — modal compiles; tests pass; a long folder list is searchable and a
    pre-set folder/account not in the list displays and is preserved
    - _Requirements: 8.3, 8.4_

- [x] 8. Documentation and steering registry
  - [x] 8.1 Create the guide `.kiro/specs/Common/Frameworks/lazy-select/LAZY_SELECT.md`
    - Architecture (component + hook), prop/option interfaces, array-vs-async-function usage, Formik
      usage pattern, dark-theme defaults, ARIA/keyboard contract, adoption checklist, accepted
      exceptions (table filters, multi-select), reference impl (`MembersFieldFormBody.tsx`)
    - Regular markdown, no steering front-matter
    - _Requirements: 8.6_
  - [x] 8.2 Update `.kiro/steering/37-shared-building-blocks.md`
    - Advance the "Lazy edit-on-click dropdown" row: fill Guide path, set Status (In-progress→Stable),
      Reference impl `MembersFieldFormBody.tsx`; add a short block description under "The blocks"
    - _Requirements: 8.6_
  - [x] 8.3 Update `.kiro/steering/32-frontend-ui.md`
    - Add a brief "Dropdowns / editable selects" pointer to the guide, sized like the Filters pointer
    - _Requirements: 8.6_

- [ ] 9. Final checkpoint
  - Foundation + all three validation screens compile (`npx tsc -b`); full frontend suite passes
    (`npx vitest run`)
  - s5j stopgap removed; steering registry + UI pointer updated; guide published
  - Confirm the three options shapes are proven (Members enum+feed, FIN accounts query, GDrive folder
    external) and no regressions in migrated screens
  - Ask the user if questions arise; push to a feature branch and open a PR

## Notes

- All tasks are required — no optional tasks
- Each task references specific requirements for traceability
- Property tests use fast-check with ≥100 iterations and `{ timeout: 30000 }` (`33-frontend-testing.md`)
- Each screen adoption updates its paired test in the same change (Change-With-Tests Contract,
  `32-frontend-ui.md`)
- The modal open/edit-mode standard is a SEPARATE deferred spec — not in scope here
- Server remains authoritative; LazySelect is presentation/convenience only

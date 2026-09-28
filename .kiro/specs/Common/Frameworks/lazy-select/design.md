# Design Document

## Overview

`LazySelect` is a single-value, always-searchable dropdown for forms and modals. At rest it renders
the CURRENT value as a closed, read-looking control; the option list is revealed only on interaction
and can be narrowed by typing. Options are supplied as an array OR a function that returns (a Promise
of) an array — the component is agnostic to whether the data is an enum, a SAM/DynamoDB feed, a MySQL
query, or an external service. The "tolerate legacy, enforce on change" rule guarantees a stored
value is never blanked and never silently coerced.

It is a shared building block per `.kiro/steering/37-shared-building-blocks.md`, living at a
discoverable path beside its peers, and it replaces the s5j stopgap in
`MembersFieldFormBody.renderOptions`.

Design principles (KISS): ONE control with ONE interaction model (always searchable — no mode
toggle); ONE options prop with two shapes (array or async function); no source taxonomy baked into
the API. The server stays authoritative; LazySelect is presentation + convenience only.

## Architecture

Three layers, mirroring the Table Filter Framework v2 shape (hook + component + guide):

```
LazySelect building block
├── frontend/src/components/common/LazySelect.tsx        # the always-searchable combobox
├── frontend/src/hooks/useLazyOptions.ts                 # normalize array|async-fn → {options,loading,error}
├── frontend/src/components/common/lazySelect.types.ts   # shared prop/option types
└── (guide) .kiro/specs/Common/Frameworks/lazy-select/LAZY_SELECT.md  # produced in tasks
```

Placement rationale: `frontend/src/components/common/` already holds cross-cutting components
(`AccountSelect.tsx`, `AssetPicker/`), and `frontend/src/hooks/` holds the shared hooks
(`useColumnFilters`, `useTableSort`, `useFilterableTable`). This keeps LazySelect discoverable and
beside its peers, consistent with steering 37's "shared code at a discoverable path".

Interaction flow:

```
rest (closed)  ──click / Enter / Space / ArrowDown──▶  open
   │  shows displayLabel(value):                          │  ensureLoaded() runs the source once
   │   • in-set  → option label                           │  render listbox (filtered by typed text)
   │   • out-of-set → raw value (tolerate legacy)         │
   │   • empty   → placeholder                            ▼
   │                                              pick option ─▶ onChange(value); close
   ▼                                              Esc / outside / blur ─▶ close (value unchanged)
disabled/readOnly → plain text, never opens
```

## Components and Interfaces

### LazySelect (component)

Props (see Data Models for the full type). Behavior by requirement:

- **Rest display (R1).** Compute `displayLabel`:
  - value empty → `placeholder`;
  - value matches a known option → `getOptionLabel(option)` (default: option label or its value);
  - value not in the set (or options not yet loaded) → `renderMissingValue(value)` (default: the raw
    value). This is the generic version of the s5j prepend.
  - `isDisabled`/`isReadOnly` → plain, non-interactive text; no open affordance (R1.5, R2.5).
- **Open + search (R2).** Open on click / Enter / Space / ArrowDown (calls `ensureLoaded`). A search
  input filters the visible options by case-insensitive substring on the display label. Close on
  outside click / blur / Escape without changing the value; Escape restores focus to the trigger.
- **Selection (R3).** Pick → `onChange(option.value)` + close. No code path coerces `value` (no
  default-to-first, no reset-to-placeholder). Out-of-list value is preserved until a pick.
- **Options source (R4).** Sourced via `useLazyOptions`; loading shows a spinner row, error shows a
  non-blocking error row inside the open list; the rest-state value is unaffected.
- **Filtering (R5).** `filterOption` (e.g. by caller roles) restricts which options are offered; the
  out-of-list current value is NEVER injected as a selectable option.
- **A11y (R6).** ARIA combobox: trigger with `role="combobox"`, `aria-expanded`, `aria-controls`; a
  `role="listbox"` popup with `role="option"` children, `aria-selected` on the current value, and
  `aria-activedescendant` tracking the keyboard-active option. Keyboard: ArrowUp/Down, Home/End,
  Enter, Escape.
- **Styling (R7).** Chakra primitives, dark-theme defaults (`bg="gray.700"`, `color="white"`,
  `borderColor="gray.600"`) with prop overrides; `size` variants; renders a self-owned listbox (not a
  Chakra Menu) so it is test-mock safe.

### useLazyOptions (hook)

Normalizes an options source into `{ options, isLoading, error, ensureLoaded, reload }`:

- array source → `options` is the array, `isLoading=false`, `ensureLoaded` is a no-op (R4.1);
- function source → first `ensureLoaded()` invokes it; `isLoading` true until settle; success caches
  the result; rejection sets `error` and leaves `options=[]` (R4.2, R4.3);
- a changed `depKey` invalidates the cache so the next open re-resolves (R4.4); `reload` forces it;
- usable independently of the component (R4.5).

### Formik usage (integration pattern, not baked in)

A thin wrapper documented in the guide binds LazySelect inside a Formik `<Field>`:
`value={field.value}`, `onChange={(v) => { form.setFieldValue(name, v); form.setFieldTouched(name, true); }}`.
No Formik coupling lives in the component, keeping it reusable outside Formik.

## Data Models

```typescript
// lazySelect.types.ts

/** A single selectable option. `label` may be a plain string or a localized map. */
export interface LazyOption<V extends string = string> {
  value: V;
  label?: string | Record<string, string>;
  /** Optional roles permitted to SELECT this option (convenience filter; server authoritative). */
  roles?: string[];
  /** Optionally disable an individual option. */
  disabled?: boolean;
}

/** Options are EITHER an array OR a function returning (a Promise of) an array. That is the whole
 *  source model — enum, API feed, SQL query, and external service all fit these two shapes. */
export type LazyOptionsSource<V extends string = string> =
  | LazyOption<V>[]
  | (() => Promise<LazyOption<V>[]> | LazyOption<V>[]);

export interface LazySelectProps<V extends string = string> {
  value: V | '';                                   // always displayed at rest (R1)
  onChange: (value: V) => void;                    // called on pick (R3)
  options: LazyOptionsSource<V>;                   // array or async fn (R4)
  optionsDepKey?: string;                          // re-resolve when this changes (R4.4)

  label: string;                                   // accessible + field label (R6.4)
  placeholder?: string;                            // shown only when value empty (R1.4)
  filterOption?: (opt: LazyOption<V>) => boolean;  // convenience filter, e.g. by role (R5)
  getOptionLabel?: (opt: LazyOption<V>) => string; // default: label/localized/value
  renderMissingValue?: (value: V) => React.ReactNode; // default: raw value text (R1.3)

  isDisabled?: boolean;
  isReadOnly?: boolean;
  isInvalid?: boolean;
  size?: 'sm' | 'md' | 'lg';
  bg?: string; color?: string; borderColor?: string;   // dark-theme defaults otherwise (R7)
  width?: string | Record<string, string>;
  name?: string;                                       // test id / Formik binding
}

export interface UseLazyOptionsResult<V extends string = string> {
  options: LazyOption<V>[];
  isLoading: boolean;
  error: Error | null;
  ensureLoaded: () => void;   // idempotent; resolves on first call (or after depKey change)
  reload: () => void;         // force re-resolve
}
```

Options-shape mapping for the three validation screens (all fit `LazyOptionsSource`):

| Screen | Field | Source shape |
| --- | --- | --- |
| Members | region | eager `LazyOption[]` (enum from field config) |
| Members | membership_type | async fn → `listMembershipTypes()` (SAM/DynamoDB feed) |
| FIN Transaction modal | Debet / Credit | async fn → chart of accounts (MySQL query, today `AccountSelect`) |
| FIN Import Invoice modal | Debet / Credit | async fn → chart of accounts (MySQL) |
| FIN Import Invoice modal | folder | async fn → Google-Drive folder names (external, long) |

## Correctness Properties

These invariants are validated with fast-check (≥100 iterations, `{ timeout: 30000 }`) per `33-frontend-testing.md`.

### Property 1: Value Preservation

For any non-empty `value` and any option set, the rest-state displayed text is non-empty (never the
placeholder for a non-empty value).

**Validates: Requirements 9.1, 1.1**

### Property 2: No Silent Coercion

For any `value` and option set, rendering then closing without a user selection leaves the emitted
value equal to the input `value`.

**Validates: Requirements 9.2, 3.2**

### Property 3: Pick Fidelity

For any option the caller may select, selecting it emits exactly that option's value.

**Validates: Requirements 9.3, 3.1**

### Property 4: Filter Soundness

For any option set and caller filter, every option offered in the open list satisfies the filter,
and the current out-of-list value never appears as a selectable option.

**Validates: Requirements 9.4, 5.2**

## Error Handling

- **Async source rejection (R4.3).** `useLazyOptions` catches the rejection, sets `error`, and leaves
  `options=[]`. LazySelect renders a non-blocking error row inside the open list; the rest-state
  current value continues to display (R1 unaffected). `reload` lets the user retry.
- **Malformed / empty options.** An empty resolved array opens an empty list (with an optional
  "no options" row) but never blanks the current value. Options lacking a `label` fall back to their
  `value` for display.
- **Never throw on an out-of-list value.** An unknown current value is displayed via
  `renderMissingValue`, never treated as an error and never coerced.
- **Disabled/read-only.** No open, no fetch, no change events; renders plain text.
- **Test-mock safety.** Because the listbox is self-owned (not a Chakra Menu), open/close/keyboard
  paths are exercisable under the Chakra test mock (`33-frontend-testing.md`); a small Playwright
  smoke covers real AT/keyboard if needed.

## Testing Strategy

Per `33-frontend-testing.md` (Vitest + RTL + fast-check; `render` from `@/test-utils`; Chakra
auto-mocked).

- **Unit (`LazySelect.test.tsx`):** rest label for in-set / raw for out-of-set / placeholder for
  empty; disabled+read-only no open; open triggers; type-to-filter; close-without-change; pick emits
  value + closes; `filterOption` hides options; out-of-set value absent from list; async loading and
  error rows; ARIA attributes.
- **Hook (`useLazyOptions.test.ts`):** array passthrough; resolve-on-ensureLoaded; error path; cache
  reuse; `reload`; `depKey` invalidation.
- **Property (`LazySelect.property.test.tsx`, `useLazyOptions.property.test.ts`):** the four
  properties above.
- **Adoption checkpoints:** after each of the three validation screens, run the migrated screen's
  paired tests and the foundation tests.

## Migration and Stepwise Validation

Incremental, one screen at a time, each a validation checkpoint proving a different options shape:

1. **Members (first adopter).** Region enum array + membership-type async feed render through
   LazySelect; remove the `renderOptions` synthetic-value prepend and leave a pointer comment.
2. **FIN Transaction modal.** Replace `AccountSelect` (Debet/Credit) with LazySelect fed by an async
   chart-of-accounts source; confirm typeahead + tolerate-legacy.
3. **FIN Import Invoice modal.** Replace the account selectors and the folder `<datalist>` with
   LazySelect fed by async sources (accounts + Google-Drive folders).

Table filters stay on Table Filter Framework v2 (out of scope). The modal open/edit-mode standard is
a separate deferred spec. Calculated/read-only fields remain non-editable.

## Steering & Registry Updates

- `.kiro/steering/37-shared-building-blocks.md`: advance the "Lazy edit-on-click dropdown" row from
  Planned → In-progress → Stable, fill the guide path, set the reference impl to
  `MembersFieldFormBody.tsx`, and add a short block description under "The blocks".
- `.kiro/steering/32-frontend-ui.md`: add a brief "Dropdowns / editable selects" pointer to the
  guide, sized to match the existing Filters pointer (no significant expansion).

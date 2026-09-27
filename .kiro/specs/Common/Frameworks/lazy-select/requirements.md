# Requirements Document

## Introduction

`LazySelect` is a shared frontend building block: ONE reusable, Chakra-consistent dropdown that
replaces the assorted always-open `<select>` controls and ad-hoc `<Input>`+`<datalist>` selectors
used across the platform for editing a field that already holds a value.

The problem it solves (raised 2026-09-24 during s5j): a native/Chakra `<Select>` bound to a value
only shows that value as preselected when it EXACTLY matches one of the rendered options. When it
does not, the control falls back to the placeholder and the stored value looks BLANK. This bites on
(1) a LEGACY value retired from the option set, (2) a role-gated option the caller may not pick, or
(3) a value simply absent from the list. s5j shipped a narrow stopgap in
`frontend/src/components/members/MembersFieldFormBody.tsx` (`renderOptions` prepends the current
value as a synthetic option); `LazySelect` is the generic, platform-wide replacement.

Design decisions (KISS, agreed with the owner):

- **One control, one interaction model.** LazySelect is ALWAYS searchable (type-to-filter). There is
  no "closed vs searchable" mode toggle — a short enum and a long external list render the same
  control. This maximizes look-and-feel consistency and removes per-field configuration.
- **One options prop, two shapes.** Options are supplied EITHER as an array OR as a function that
  returns (a Promise of) an array. The component does not know or care whether the data came from an
  enum, a DynamoDB/SAM API feed, a MySQL query, or an external service (e.g. Google Drive) — they
  are all just "an array, or a function that fetches one."
- **Tolerate legacy, enforce on change.** The current value is always displayed at rest and never
  blanked or coerced; the server remains authoritative over what is valid.

This block follows the shared-building-block template in `.kiro/steering/37-shared-building-blocks.md`
(Frameworks spec + discoverable shared code + steering registry row + a named reference impl). It is
frontend-only and aligns with `32-frontend-ui.md` (Chakra dark theme, Formik, i18n) and
`33-frontend-testing.md`.

### Stepwise validation

The concept is validated incrementally, each step exercising a different options SHAPE and plane:

1. **Members app** — eager enum arrays (region) + an async API feed (membership-type) on the
   SAM/DynamoDB plane; retires the s5j stopgap. (No SQL involved.)
2. **FIN Transaction modal** — a query-backed source (chart of accounts, today `AccountSelect`) on
   the Flask/MySQL plane; typeahead over a longer list, tolerate-legacy.
3. **FIN Import Invoice modal** — a long/external list (Google-Drive folder names) plus the same
   query-backed accounts.

### Non-goals

- NOT a multi-select or a table filter — the Table Filter Framework v2 owns table filtering.
- NOT the modal open/edit-mode standard (read-only-then-Bewerken vs. straight-to-edit). That is a
  separate, deferred building block; LazySelect does not decide how a modal opens.
- NOT an authority boundary — the server (Flask/SAM domain) re-validates every value authoritatively.
- Does NOT make calculated/derived or read-only fields editable.

## Glossary

- **LazySelect**: the reusable, always-searchable dropdown component this spec defines.
- **useLazyOptions**: the hook that normalizes an options source (array or async function) into a
  loaded/loading/error state, resolving on first open.
- **Options source**: either an array of options OR a function returning (a Promise of) an array.
- **Tolerate legacy**: the rule that a stored value not present in the option set is still displayed
  and preserved until the user deliberately picks another value.
- **Out-of-list value**: a current value absent from the resolved option set (legacy, role-gated, or
  otherwise missing).
- **s5j stopgap**: the narrow workaround in `MembersFieldFormBody.renderOptions` that prepends the
  current value as a synthetic `<option>`; removed once Members adopts LazySelect.

## Requirements

### Requirement 1: Always display the current value (never blank it)

**User Story:** As a user editing a record whose stored value is not in the current option set, I
want to still see that value, so that the field never looks empty and I do not accidentally erase it.

#### Acceptance Criteria
1. WHEN LazySelect renders with a non-empty value THEN the system SHALL display that value's label at
   rest, whether or not the value is present in the resolved option set.
2. WHEN the value is present in the option set THEN the system SHALL display the option's label via
   the caller-provided label resolver, defaulting to the option's own label or its raw value.
3. WHEN the value is NOT present in the option set THEN the system SHALL display the raw value and
   SHALL NOT show the placeholder in its place.
4. WHEN the value is empty, null, or undefined THEN the system SHALL display the placeholder.
5. WHEN the field is disabled or read-only THEN the system SHALL display the current value as plain
   non-interactive text with no open affordance.

### Requirement 2: Reveal and search options only on interaction

**User Story:** As a user, I want the list to stay closed showing the current value until I open it,
and then to let me type to narrow it, so that both short and long lists are usable and calm.

#### Acceptance Criteria
1. WHEN the component is at rest THEN the system SHALL NOT render the option list.
2. WHEN the user clicks the control OR focuses it and presses Enter, Space, or ArrowDown THEN the
   system SHALL open and render the option list.
3. WHILE the list is open WHEN the user types THEN the system SHALL filter the visible options by a
   case-insensitive substring match against each option's display label.
4. WHEN the list is open AND the user clicks outside, presses Escape, or blurs the control THEN the
   system SHALL close the list without changing the value, and Escape SHALL restore focus to the
   control.
5. WHEN the control is disabled or read-only THEN the system SHALL NOT open on interaction.

### Requirement 3: Pick replaces; legacy is tolerated until changed

**User Story:** As a user, I want picking an option to replace the value while a value not in the
list is kept until I deliberately change it, so that legacy data survives an edit that does not touch
this field.

#### Acceptance Criteria
1. WHEN the user selects an option THEN the system SHALL call the change handler with the selected
   option's value and SHALL close the list.
2. IF the current value is not in the option set AND the user opens the list without selecting a new
   option THEN the system SHALL leave the value unchanged on close.
3. WHEN integrated with Formik THEN selecting an option SHALL update the bound field value and mark
   the field touched via the standard Formik field contract.
4. The system SHALL NOT auto-coerce an out-of-list value to a placeholder or to the first option at
   any point.

### Requirement 4: Options as an array or an async function

**User Story:** As a developer, I want to feed options either eagerly as an array or lazily via a
function that fetches them on open, so that enums, API feeds, queries, and external sources all use
the same control without special-casing.

#### Acceptance Criteria
1. WHEN options are provided as an array THEN the system SHALL render them on open with no loading
   state.
2. WHEN options are provided as a function THEN the system SHALL invoke it the first time the list
   opens and SHALL show a loading indicator until it resolves.
3. IF the options function rejects THEN the system SHALL show a non-blocking error state inside the
   open list AND SHALL still display the current value at rest.
4. WHEN the list re-opens after a successful resolve THEN the system SHALL reuse the resolved options
   UNLESS a caller-supplied dependency key changed, in which case the system SHALL re-resolve.
5. The `useLazyOptions` hook SHALL expose options, loading, error, an `ensureLoaded` trigger, and a
   `reload` action, and SHALL be usable independently of the component.

### Requirement 5: Role/permission-aware option filtering

**User Story:** As a caller with a limited role, I want to only be offered options I may select while
still seeing a stored value I cannot pick, so that convenience filtering never hides real data.

#### Acceptance Criteria
1. WHEN a caller-supplied option filter is provided THEN the system SHALL only render options that
   satisfy the filter in the open list.
2. IF the current value corresponds to an option the caller may NOT pick THEN the system SHALL still
   display that value at rest AND SHALL NOT include it as a selectable option.
3. The system SHALL treat option filtering as convenience only AND SHALL NOT assume the server
   accepts a picked value.

### Requirement 6: Accessibility (ARIA combobox, keyboard)

**User Story:** As a keyboard or screen-reader user, I want the control to behave like a standard
searchable combobox, so that I can operate it without a mouse and understand its state.

#### Acceptance Criteria
1. The control SHALL expose the ARIA combobox pattern: a labelled trigger with an expanded-state
   indicator and a reference to the listbox it controls.
2. The open list SHALL be a listbox whose entries expose the option role and a selected-state
   indicator on the current value.
3. WHILE the list is open THEN ArrowUp and ArrowDown SHALL move the active option, Enter SHALL select
   the active option, Escape SHALL close without change, and Home and End SHALL jump to first and
   last.
4. The control SHALL be reachable and operable via Tab and Shift-Tab AND SHALL have an accessible
   name derived from its label per the i18n conventions in `32-frontend-ui.md`.
5. The component SHALL target WCAG 2.1 AA for keyboard operability and name/role/value; full
   conformance requires manual assistive-technology testing.

### Requirement 7: Chakra-consistent, dark-theme styling

**User Story:** As a user, I want the dropdown to match the rest of the platform, so that it looks
native to every page it appears on.

#### Acceptance Criteria
1. The component SHALL be built with Chakra UI primitives AND SHALL honor the platform dark-theme
   defaults used by existing selects, while allowing style overrides via props.
2. The component SHALL support Chakra size variants and responsive width props.
3. The component SHALL be render-safe under the Chakra test mock so it can be unit-tested without a
   real ChakraProvider.

### Requirement 8: Stepwise validation and incremental adoption

**User Story:** As a maintainer, I want the concept validated in three concrete screens before wider
rollout, so that the single component is proven against each options shape and the s5j stopgap is
retired.

#### Acceptance Criteria
1. WHEN the Members modal adopts LazySelect THEN the region enum array and the async membership-type
   feed SHALL both render through it, AND the synthetic-current-value prepend in `renderOptions`
   SHALL be removed and replaced with a pointer comment referencing this block.
2. WHEN the FIN Transaction modal adopts LazySelect THEN the query-backed chart-of-accounts source
   (currently `AccountSelect`) SHALL render through it with typeahead and tolerate-legacy behavior.
3. WHEN the FIN Import Invoice modal adopts LazySelect THEN the long external Google-Drive folder
   list AND the query-backed accounts SHALL both render through it.
4. Each adoption step SHALL preserve the migrated field's existing behavior for values already in the
   option set AND SHALL additionally fix the out-of-list "looks blank" case.
5. Calculated/derived and read-only fields SHALL remain non-editable after each adoption.
6. The block SHALL be registered in `.kiro/steering/37-shared-building-blocks.md` (status advanced
   from Planned as it lands) and referenced from `32-frontend-ui.md`.

### Requirement 9: Correctness properties

**User Story:** As a maintainer, I want universal invariants captured as property tests, so that the
"never blank the value" and "tolerate legacy, enforce on change" guarantees hold for arbitrary input.

#### Acceptance Criteria
1. WHEN rendering any non-empty value with any option set THEN the rest-state displayed text SHALL be
   non-empty (never the placeholder for a non-empty value).
2. WHEN rendering then closing without a user selection THEN the emitted value SHALL equal the input
   value for any value and option set.
3. WHEN selecting any option the caller may pick THEN the change handler SHALL emit exactly that
   option's value.
4. WHEN filtering options with any caller filter THEN every option offered SHALL satisfy the filter
   AND the current out-of-list value SHALL never appear as a selectable option.
5. Property-based tests SHALL use fast-check with a minimum of 100 iterations and the 30000ms timeout
   convention from `33-frontend-testing.md`.

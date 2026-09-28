# LazySelect — usage guide

A reference guide for the `LazySelect` shared building block. For the full rationale see the
`requirements.md` and `design.md` beside this file; this guide is the practical "how do I use it"
companion. Where this guide and `design.md` disagree, the **shipped code is the source of truth** and
this guide follows it.

## Overview

`LazySelect` is a single-value, **always-searchable** dropdown (combobox) for forms and modals. At
rest it renders the current value as a closed, read-looking control; the option list is revealed only
on interaction and can be narrowed by typing.

It exists to fix one recurring bug: a native/Chakra `<Select>` bound to a value only shows that value
as preselected when it **exactly** matches a rendered option. When it does not — a legacy value
retired from the set, a role-gated option the caller may not pick, or a value simply absent from the
list — the control falls back to the placeholder and the stored value **looks blank**. LazySelect
follows "**tolerate legacy, enforce on change**": the current value is always displayed at rest and is
never blanked or silently coerced; the server stays authoritative over what is valid.

One control, one interaction model (no "closed vs searchable" toggle) and one options prop with two
shapes (array or async function). A short enum and a long external list render the same control.

## Architecture

Three layers, discoverable beside their peers in `frontend/src/components/common/` and
`frontend/src/hooks/`:

```
frontend/src/components/common/LazySelect.tsx        # the always-searchable combobox
frontend/src/hooks/useLazyOptions.ts                 # normalize array|async-fn → {options,loading,error,...}
frontend/src/components/common/lazySelect.types.ts   # shared prop/option types + resolveOptionLabel
.kiro/specs/Common/Frameworks/lazy-select/LAZY_SELECT.md   # this guide
```

`LazySelect` is exported both **named and default** (`import LazySelect from …` or
`import { LazySelect } from …`). The component consumes `useLazyOptions` internally, but the hook is
usable on its own.

Interaction flow:

```
rest (closed)  ──click / Enter / Space / ArrowDown──▶  open
   shows the current value:                              ensureLoaded() runs the source once
     • in-set     → option label                         render self-owned listbox (filtered by typed text)
     • out-of-set → raw value (tolerate legacy)          pick option ─▶ onChange(value); close
     • empty      → placeholder                          Esc / outside / blur ─▶ close, value unchanged
   disabled/readOnly → plain text, never opens
```

## Prop / option interfaces

All types live in `lazySelect.types.ts`.

### `LazyOption<V>`

```typescript
interface LazyOption<V extends string = string> {
  value: V;
  label?: string | Record<string, string>;  // plain string OR localized map ({ nl, en, … })
  roles?: string[];                          // optional: roles permitted to SELECT (convenience only)
  disabled?: boolean;                        // optionally disable a single option
}
```

### `LazyOptionsSource<V>` — array OR (async) function

```typescript
type LazyOptionsSource<V extends string = string> =
  | LazyOption<V>[]
  | (() => Promise<LazyOption<V>[]> | LazyOption<V>[]);
```

That is the whole source model. An enum, a SAM/DynamoDB feed, a MySQL query, and an external service
all fit these two shapes — the component neither knows nor cares which.

### `LazySelectProps<V>`

| Prop | Type | Notes |
| --- | --- | --- |
| `value` | `V \| ''` | Always displayed at rest (R1). Empty string means "no value". |
| `onChange` | `(value: V) => void` | Called on pick with the exact option value (R3). |
| `options` | `LazyOptionsSource<V>` | Array or (async) function (R4). |
| `optionsDepKey` | `string?` | Re-resolve a function source when this changes (R4.4). |
| `label` | `string` | Accessible name + field label (R6.4). Required. |
| `placeholder` | `string?` | Shown **only** when `value` is empty (R1.4). |
| `filterOption` | `(opt) => boolean` | Convenience filter, e.g. by role — restricts which options are offered (R5). |
| `getOptionLabel` | `(opt) => string` | Overrides the built-in label resolution. |
| `renderMissingValue` | `(value) => ReactNode` | Renders an out-of-set value; defaults to the raw value text (R1.3). |
| `isDisabled` / `isReadOnly` | `boolean?` | Either one renders plain, non-interactive text and never opens (R1.5/R2.5). |
| `isInvalid` | `boolean?` | Red border / `aria-invalid`. |
| `size` | `'sm' \| 'md' \| 'lg'` | Chakra size variant; default `md`. |
| `bg` / `color` / `borderColor` | `string?` | Override the dark-theme defaults. |
| `width` | `string \| Record<string,string>` | Responsive width. |
| `name` | `string?` | Drives the test id (`{name}-lazyselect`) and ARIA ids; handy for Formik binding. |

### `UseLazyOptionsResult<V>`

```typescript
interface UseLazyOptionsResult<V extends string = string> {
  options: LazyOption<V>[];
  isLoading: boolean;
  error: Error | null;
  ensureLoaded: () => void;   // idempotent; resolves on first call (or after depKey change)
  reload: () => void;         // force a re-resolve
}
```

### `resolveOptionLabel` convention

The built-in label resolver (used unless you pass `getOptionLabel`) mirrors the Members `resolveLabel`
convention:

```typescript
resolveOptionLabel(opt, getOptionLabel?, lang?): string
// getOptionLabel (if supplied) wins;
// label is a localized map → label[lang] || label.nl || label.en || value;
// label is a plain string → the string;
// no label → the raw value.
```

## Array vs async-function usage

### Eager array

```tsx
const accountOptions: LazyOption[] = chartAccounts.map((a) => ({ value: a.code, label: a.name }));

<LazySelect
  value={record.Debet || ''}
  onChange={(v) => setRecord((r) => ({ ...r, Debet: v }))}
  options={accountOptions}
  label={t('table.debit')}
/>
```

An array source renders on open with **no loading state**; `ensureLoaded` is a no-op.

### Async function (with `optionsDepKey`)

```tsx
<LazySelect
  value={field.value ?? ''}
  onChange={(v) => form.setFieldValue(name, v)}
  options={async () => membershipTypeOptions(await listMembershipTypes(true))}
  optionsDepKey="membership_type"   // changing this invalidates the cache → next open re-resolves
  label={label}
  size="sm"
/>
```

A function source is invoked on the **first open** (`ensureLoaded`); the open list shows a **loading**
row until it settles, and a non-blocking **error** row if it rejects (the rest-state value is
unaffected). The resolved list is cached and reused on re-open unless `optionsDepKey` changed;
`reload` (from the hook) forces a fresh resolve.

## Formik usage pattern

No Formik coupling lives in the component, so it stays reusable outside Formik. The documented binding
is a thin wrapper:

```tsx
<LazySelect
  name={name}
  label={label}
  value={field.value ?? ''}
  onChange={(v) => {
    form.setFieldValue(name, v);
    form.setFieldTouched(name, true);
  }}
  options={optionsSource}
/>
```

That is exactly how `MembersFieldFormBody.tsx` binds it.

## Dark-theme defaults

Built on Chakra primitives with platform dark-theme defaults, all overridable via props:

- `bg="gray.700"`, `color="white"`, `borderColor="gray.600"`.
- `size` supports `sm` / `md` / `lg` (default `md`) and responsive `width`.

On a light card, override the defaults — e.g. `PDFUploadForm.tsx` runs on a white card and passes
`bg`/`color` overrides on the account selectors so the control reads native to that surface.

## ARIA / keyboard contract

- **Trigger** — `role="combobox"`, `tabIndex=0`, with `aria-haspopup="listbox"`, `aria-expanded`,
  `aria-controls` (the listbox id), `aria-label` (from `label`), and `aria-invalid` when invalid.
- **Popup** — a self-owned `role="listbox"` containing `role="option"` children; the current value's
  option carries `aria-selected`, and `aria-activedescendant` (on the search input) tracks the
  keyboard-active option.
- **Keys** — `ArrowUp` / `ArrowDown` move the active option, `Home` / `End` jump to first / last,
  `Enter` selects the active option, `Escape` closes without change **and restores focus to the
  trigger**. Open on click, `Enter`, `Space`, or `ArrowDown`.
- **Disabled / read-only** — render plain text with no combobox role and **never open**, fetch, or
  emit change events.

Targets WCAG 2.1 AA for keyboard operability and name/role/value; full conformance requires manual
assistive-technology testing.

## i18n

The caller supplies `label` and `placeholder`. Internal status/UX text is resolved via
`useTypedTranslation('common')`:

| Text | Key |
| --- | --- |
| loading row | `status.loading` |
| error row | `messages.error` |
| empty list row | `placeholders.noOptions` |
| search box placeholder | `placeholders.typeToSearch` |

## Adoption checklist

Migrating an existing `<select>`, `<Input>`+`<datalist>`, or `AccountSelect`:

1. Map the current data to a `LazyOption[]` (eager) or wrap the fetch in an async function
   (`() => Promise<LazyOption[]>`), setting `optionsDepKey` if the fetch depends on some key.
2. Wire `value` (fall back to `''` for empty) and `onChange`. In Formik use the wrapper above.
3. Pass `filterOption` for value-level role gating; an out-of-set / role-gated current value still
   shows at rest but is never offered as a selectable option.
4. Keep calculated / read-only fields disabled — LazySelect renders them as plain text and does not
   make them editable.
5. Remove any synthetic-current-value stopgap (the old "prepend the current value as an option"
   trick) — LazySelect owns that now (Requirement 1).
6. Update the paired test in the **same change** (Change-With-Tests Contract, `32-frontend-ui.md`):
   assert the out-of-set value still displays and is not offered as an option; don't weaken existing
   assertions.

## Accepted exceptions / non-goals

- **Not multi-select.** Single value only.
- **Not table filtering.** The Table Filter Framework v2 owns table filters.
- **Not the modal open / edit-mode standard** (read-only-then-Bewerken vs. straight-to-edit) — that
  is a separate, deferred building block. LazySelect does not decide how a modal opens.
- **Not an authority boundary.** The server (Flask/SAM domain) re-validates every value;
  `filterOption`/`roles` are convenience only.

## Reference implementations

- **`frontend/src/components/members/MembersFieldFormBody.tsx`** — the primary reference (registry
  reference impl). Parameter-driven: the single generic dropdown branch routes **every**
  enum/reference/scope field through LazySelect. It exercises **eager arrays** (region scope, rich
  enums like Gender/Clubblad/Motorbrand, bare `string[]`) **and** an **async function**
  (`membership_type` → `listMembershipTypes()`, with `optionsDepKey="membership_type"`). It also
  retired the s5j `renderOptions` synthetic-value stopgap.
- **`frontend/src/components/BankingTransactionModal.tsx`** — Debet / Credit fed by an **eager
  `LazyOption[]`** mapped from the parent-fetched chart of accounts (`useAccountLookup`), on a
  `gray.600` surface.
- **`frontend/src/components/PDFUploadForm.tsx`** — folder selector fed by an **eager array** of
  Google-Drive folder names (`allFolders`); its `onChange` drives `handleSearch`, so picking a folder
  resolves the existing Upload gate. Account (Debet/Credit) selectors also route through LazySelect on
  the white card (with `bg`/`color` overrides).

> Note: `design.md`'s options-shape table sketched the FIN account and GDrive-folder sources as async
> functions. The shipped screens supply them as **eager arrays** (the parent already fetched the data
> and maps it to `LazyOption[]`), which is fully valid under `LazyOptionsSource`. The array shape is
> the source of truth here.

## Testing note

Foundation is covered by unit and property tests:

- `frontend/src/components/common/__tests__/LazySelect.test.tsx` and `LazySelect.property.test.tsx`
- `frontend/src/hooks/__tests__/useLazyOptions.test.ts` and `useLazyOptions.property.test.ts`

Property tests use fast-check (≥100 iterations, `{ timeout: 30000 }`) and cover Value Preservation, No
Silent Coercion, Pick Fidelity, and Filter Soundness. Because the listbox is **self-owned** (plain
Chakra `Box`es, not a Chakra `Menu`), the open/close/keyboard paths are exercisable under the Chakra
auto-mock — no real `ChakraProvider` needed (`render` from `@/test-utils`, per `33-frontend-testing.md`).

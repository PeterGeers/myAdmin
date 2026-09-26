---
inclusion: fileMatch
fileMatchPattern: "frontend/src/**/*.tsx,frontend/src/**/*.ts"
---

# UI Patterns

## Action Buttons

Follow the BankingProcessor pattern:

- No action buttons in table rows — keep rows clean
- Click a row to open a modal for edit/delete/detail actions
- Place primary actions (Add, Export, Import) in the page header row, right-aligned
- Use `colorScheme="orange"` for primary actions, `variant="ghost"` for secondary
- Reference: `.kiro/specs/Common/parameter-driven-config/frontend-tasks.md`

## Table Layout

- Use Chakra UI `Table` with `variant="simple"` on dark background (`bg="gray.800"`)
- Sortable column headers where applicable
- Hover-highlighted rows (`_hover={{ bg: 'gray.700', cursor: 'pointer' }}`)
- Row click opens detail/edit Modal — no per-row buttons
- Status shown as `Badge` components, read-only data only in cells
- Use responsive `overflowX="auto"` wrapper for mobile

## Modal Layout

- Chakra UI `Modal` for all CRUD operations
- Form inside modal uses Formik + Yup validation
- Standard button layout: Cancel (left, ghost) + Save/Submit (right, orange solid)
- Loading state on submit button
- Close on overlay click disabled for edit modals (`closeOnOverlayClick={false}`)

## Responsive Design

- Use Chakra responsive props: `size={{ base: 'sm', md: 'lg' }}`
- Headers: `Flex wrap="wrap"` instead of rigid `HStack` for mobile wrapping
- Hide non-essential columns on mobile with `display={{ base: 'none', md: 'table-cell' }}`
- TenantSelector: keep `minW="120px"` on mobile, `minW="150px"` on desktop

## Translation (i18n)

- Use `useTypedTranslation(namespace)` from `hooks/useTypedTranslation.ts` — typed wrapper for `useTranslation` with namespace support
- All user-facing text uses namespaced keys
- Key pattern: `{namespace}:{category}.{key}` (e.g., `common:buttons.save`)
- Categories: `buttons` (actions), `labels` (form fields), `messages` (feedback), `titles` (headings)
- Never hardcode user-visible strings
- Conventions: `.kiro/specs/Common/Internationalization/TRANSLATION_KEY_CONVENTIONS.md`

## Filters

Use the Table Filter Framework v2 — a hybrid approach: text search filters in column headers (`FilterableHeader`), dropdowns/multi-select above the table (`FilterPanel`).

- Key hooks: `useColumnFilters`, `useTableSort`, `useFilterableTable`
- Parameter-driven config for complex tables: `useTableConfig`
- Components: `FilterPanel` (above table), `FilterableHeader` (in `<Th>`)
- Clear all / reset button to return to default view

When implementing or modifying tables or filters, read the full framework guide at `.kiro/specs/Common/Frameworks/table-filter-framework-v2/design.md`

This is one of the platform's shared building blocks — see `37-shared-building-blocks.md` for the full registry (and reach for a registered block before inventing a local variant).

## Reference Implementation

`frontend/src/pages/ZZPInvoices.tsx` correctly demonstrates all patterns above (dark theme, FilterableHeader, row-click modal, orange primary actions, i18n, responsive wrapping). Use it as a concrete example when building new pages.

## Change-With-Tests Contract (component ⇄ allocated tests)

**When you change a component's behavior or rendered markup, update its allocated test(s) in the SAME change.** Leaving the paired test asserting the old behavior is incomplete — it passes locally by luck and breaks the nightly Full Test Suite days later (the most common recurring CI failure; see `.kiro/specs/code-quality-maintenance/`). Two real examples that bit us: de-badging the MembersPage region cell (`<span>` Badge → plain `<td>`) and adding the Lidnummer column first broke `MembersPage.test.tsx`; changing Revolut account-resolution to open the popup-with-all-known-accounts broke `BankingFileUpload.account-resolution-preservation.test.tsx`.

Applies to any observable change: rendered element/tag (a `<Badge>`/`<span>` → `<td>` change breaks `tagName`/role queries), column order, a dialog/error path, an API/response shape the component reads.

Required steps for every behavior/markup change:
1. **Find the allocated test(s).** `src/pages/Foo.tsx` / `src/components/**/Foo.tsx` → `src/**/__tests__/Foo*.test.tsx`. Also grep the test tree for the changed component/testid/label — look for `*.preservation`, `*-bug`, and `*props` tests that encode intended behavior.
2. **Update the test(s)** to the intended new behavior, in the same change.
3. **Do not weaken or delete assertions to go green.** If two tests now contradict (e.g. a `preservation` test asserts the old path while a `-bug` test asserts the new), STOP and surface the conflict — do not pick a side silently.
4. **Run the paired test(s)**: `npx vitest run <paths>`.

The `test-sync-on-source-change` hook (`.kiro/hooks/`) reminds you of this on every product-file save; the rule here is the source of truth even when the hook does not fire.

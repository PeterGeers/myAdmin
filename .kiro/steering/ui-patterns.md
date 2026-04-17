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

- Use `useTypedTranslation(namespace)` from `hooks/useTypedTranslation.ts` — NOT `useTranslation` directly (CRA TypeScript workaround)
- All user-facing text uses namespaced keys
- Key pattern: `{namespace}:{category}.{key}` (e.g., `common:buttons.save`)
- Categories: `buttons` (actions), `labels` (form fields), `messages` (feedback), `titles` (headings)
- Never hardcode user-visible strings
- Conventions: `.kiro/specs/Common/Internationalization/TRANSLATION_KEY_CONVENTIONS.md`

## Filters

Use the generic filter framework for consistent filtering across all list views.

- Filter bar sits between page header and table
- Filters are dropdowns, date pickers, or text inputs — never inline in the table
- Filter state managed via URL query params for shareable/bookmarkable views
- Clear all / reset button to return to default view
- Reference: `.kiro/specs/Common/Filters a generic approach/`

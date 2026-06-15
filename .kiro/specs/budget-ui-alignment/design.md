# Design Document: Budget UI Alignment

## Overview

This design covers the refactoring of four budget module pages (`BudgetVersionsPage`, `BudgetTemplatesPage`, `BudgetLinesPage`, `BudgetDashboard`) to align with the project's established UI patterns. The reference implementation is `ZZPInvoices.tsx`. No backend changes are required — this is purely a frontend styling, i18n, and component consistency effort.

## Architecture

The refactoring applies a consistent layer of UI patterns across existing page components without altering their data flow or business logic. Each page retains its current API calls, state management, and routing — only the presentation layer changes.

```
┌──────────────────────────────────────────────────────────────┐
│                     Budget Module Pages                        │
├──────────────┬──────────────┬─────────────┬──────────────────┤
│ VersionsPage │ TemplatesPage│  LinesPage  │    Dashboard     │
└──────┬───────┴──────┬───────┴──────┬──────┴───────┬──────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌──────────────────────────────────────────────────────────────┐
│              Shared UI Layer (applied by refactoring)          │
├──────────────────────────────────────────────────────────────┤
│  useTypedTranslation('budget')                                │
│  useFilterableTable + FilterableHeader                        │
│  Formik + Yup (modals with forms)                            │
│  Dark theme: gray.800/gray.700/white                         │
│  Responsive: Flex wrap, hidden columns, responsive sizes      │
│  Button styling: orange primary, ghost cancel, red delete     │
└──────────────────────────────────────────────────────────────┘
```

## Components & Interfaces

### 1. Translation Integration

Each page calls `useTypedTranslation('budget')` at the top of the component and replaces all hardcoded strings with `t('category.key')` calls.

```typescript
// In each budget page component
const { t } = useTypedTranslation('budget');

// Usage examples
<Text>{t('titles.versions')}</Text>
<Button>{t('buttons.createVersion')}</Button>
<Text>{t('messages.noVersions')}</Text>
```

Shared labels (Save, Cancel, Delete, loading states) use the `common` namespace:

```typescript
const { t: tc } = useTypedTranslation('common');

<Button variant="ghost">{tc('buttons.cancel')}</Button>
<Button colorScheme="orange">{tc('buttons.save')}</Button>
```

### 2. FilterableHeader + useFilterableTable Integration

Each table page defines an `INITIAL_FILTERS` record and wires `useFilterableTable`:

```typescript
// BudgetVersionsPage example
const INITIAL_FILTERS: Record<string, string> = {
  name: '',
  fiscal_year: '',
  status: '',
  is_active: '',
};

const {
  filters,
  setFilter,
  handleSort,
  sortField,
  sortDirection,
  processedData,
} = useFilterableTable<BudgetVersion>(versions, {
  initialFilters: INITIAL_FILTERS,
  defaultSort: { field: 'fiscal_year', direction: 'desc' },
});

// Column headers use FilterableHeader
<FilterableHeader
  label={t('columns.name')}
  filterValue={filters.name}
  onFilterChange={(v) => setFilter('name', v)}
  sortable
  sortDirection={sortField === 'name' ? sortDirection : null}
  onSort={() => handleSort('name')}
/>
```

For `BudgetDashboard`, the FilterableHeader replaces the static `<Th>` elements. The dashboard's drill-down behavior remains unchanged — FilterableHeader provides text filtering on the currently visible rows.

### 3. Modal Pattern (Formik + Yup)

Modals with forms (BudgetVersionsPage create, BudgetTemplatesPage create/edit, BudgetLinesPage line edit) adopt Formik + Yup:

```typescript
import { Formik, Form, Field } from 'formik';
import * as Yup from 'yup';

// BudgetVersionsPage create modal schema
const createVersionSchema = Yup.object({
  name: Yup.string().required(t('validation.nameRequired')).max(100),
  fiscal_year: Yup.number()
    .required(t('validation.yearRequired'))
    .min(2000)
    .max(2100),
});

// Inside Modal
<Formik
  initialValues={{ name: '', fiscal_year: new Date().getFullYear() }}
  validationSchema={createVersionSchema}
  onSubmit={handleCreate}
>
  {({ isSubmitting }) => (
    <Form>
      <ModalBody>
        <VStack spacing={4}>
          <Field name="name">
            {({ field, meta }) => (
              <FormControl isInvalid={!!(meta.touched && meta.error)}>
                <FormLabel>{t('labels.versionName')}</FormLabel>
                <Input {...field} />
                <FormErrorMessage>{meta.error}</FormErrorMessage>
              </FormControl>
            )}
          </Field>
        </VStack>
      </ModalBody>
      <ModalFooter>
        <Button variant="ghost" mr={3} onClick={onClose}>
          {tc('buttons.cancel')}
        </Button>
        <Button colorScheme="orange" type="submit" isLoading={isSubmitting}>
          {tc('buttons.save')}
        </Button>
      </ModalFooter>
    </Form>
  )}
</Formik>
```

Modal props include `closeOnOverlayClick={false}` and dark theme styling:

```typescript
<Modal isOpen={isOpen} onClose={onClose} closeOnOverlayClick={false}>
  <ModalOverlay />
  <ModalContent bg="gray.800" color="white">
    ...
  </ModalContent>
</Modal>
```

### 4. Table Styling

All tables follow the same pattern:

```typescript
<Box overflowX="auto">
  <Table variant="simple" size="sm" bg="gray.800" color="white">
    <Thead>
      <Tr>
        <FilterableHeader ... />
      </Tr>
    </Thead>
    <Tbody>
      {processedData.map((row) => (
        <Tr
          key={row.id}
          _hover={{ bg: 'gray.700', cursor: 'pointer' }}
          onClick={() => handleRowClick(row)}
        >
          <Td>{row.name}</Td>
          <Td display={{ base: 'none', md: 'table-cell' }}>{row.hiddenOnMobile}</Td>
        </Tr>
      ))}
    </Tbody>
  </Table>
</Box>
```

### 5. Responsive Design

Headers use `Flex wrap="wrap"` with gap for mobile wrapping:

```typescript
<Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
  <Text fontSize="xl" fontWeight="bold" color="white">{t('titles.versions')}</Text>
  <HStack spacing={2}>
    <Button size={{ base: 'sm', md: 'sm' }} ...>...</Button>
  </HStack>
</Flex>
```

Hidden columns per page:

- **BudgetVersionsPage**: Active column hidden on mobile
- **BudgetTemplatesPage**: Created column hidden on mobile
- **BudgetLinesPage**: Dimension column hidden on mobile
- **BudgetDashboard**: Name column hidden on mobile

### 6. Action Button Styling

| Button type                                           | Style                                    |
| ----------------------------------------------------- | ---------------------------------------- |
| Primary actions (Create, Add, Save, Generate, Export) | `colorScheme="orange"`                   |
| Cancel (modal footer)                                 | `variant="ghost"`                        |
| Delete (modal footer)                                 | `colorScheme="red" variant="outline"`    |
| Secondary header actions (Copy, AI Suggest)           | `colorScheme="orange" variant="outline"` |

## Data Models

### Translation File Structure

**Path**: `frontend/src/locales/en/budget.json` and `frontend/src/locales/nl/budget.json`

```typescript
interface BudgetTranslations {
  titles: {
    versions: string;
    templates: string;
    lines: string;
    dashboard: string;
  };
  columns: {
    name: string;
    fiscalYear: string;
    status: string;
    active: string;
    lines: string;
    created: string;
    accountCode: string;
    periodMode: string;
    dimension: string;
    total: string;
    code: string;
    budget: string;
    actual: string;
    variance: string;
  };
  buttons: {
    createVersion: string;
    createTemplate: string;
    addLine: string;
    generateDraft: string;
    copyBudget: string;
    aiRecommend: string;
    aiSuggestions: string;
    generateSummary: string;
    ask: string;
    addToTemplate: string;
    addAll: string;
    approve: string;
    revise: string;
    activate: string;
    accept: string;
    reject: string;
    export: string;
    addTemplateLine: string;
  };
  labels: {
    versionName: string;
    fiscalYear: string;
    templateName: string;
    accountCode: string;
    periodMode: string;
    monthly: string;
    annual: string;
    dimensionType: string;
    dimensionValue: string;
    sourceVersion: string;
    targetYear: string;
    template: string;
    year: string;
    period: string;
    referenceNumber: string;
    contextNotes: string;
    monthlyAmounts: string;
    annualAmount: string;
    detailDimension: string;
  };
  messages: {
    noVersions: string;
    noTemplates: string;
    noLines: string;
    noData: string;
    versionCreated: string;
    versionApproved: string;
    versionRevised: string;
    versionActivated: string;
    versionDeleted: string;
    templateCreated: string;
    templateUpdated: string;
    templateDeleted: string;
    lineCreated: string;
    lineUpdated: string;
    lineDeleted: string;
    draftGenerated: string;
    budgetCopied: string;
    loadError: string;
    saveError: string;
    nameRequired: string;
    yearRequired: string;
    accountRequired: string;
    selectTemplate: string;
    noRecommendations: string;
    noSuggestions: string;
    accountsSelected: string;
    activeVersion: string;
  };
}
```

### Yup Validation Schemas

```typescript
// BudgetVersionsPage - Create Version
const createVersionSchema = Yup.object({
  name: Yup.string().required().max(100),
  fiscal_year: Yup.number().required().min(2000).max(2100),
});

// BudgetTemplatesPage - Create/Edit Template
const templateSchema = Yup.object({
  name: Yup.string().required().max(100),
  lines: Yup.array()
    .of(
      Yup.object({
        account_code: Yup.string().required(),
        period_mode: Yup.string().oneOf(["Monthly", "Annual"]).required(),
        has_detail_dimension: Yup.boolean(),
        dimension_type: Yup.string()
          .nullable()
          .when("has_detail_dimension", {
            is: true,
            then: (schema) => schema.required(),
          }),
      }),
    )
    .min(1),
});

// BudgetLinesPage - Add/Edit Line
const lineSchema = Yup.object({
  account_code: Yup.string().required(),
  period_mode: Yup.string().oneOf(["Monthly", "Annual"]).required(),
  amounts: Yup.array()
    .of(Yup.number())
    .when("period_mode", {
      is: "Monthly",
      then: (schema) => schema.length(12),
    }),
  annual_amount: Yup.number().when("period_mode", {
    is: "Annual",
    then: (schema) => schema.required().min(0),
  }),
  dimension_type: Yup.string().nullable(),
  dimension_value: Yup.string().nullable(),
});

// BudgetLinesPage - Generate Draft
const generateDraftSchema = Yup.object({
  template_id: Yup.number().required().positive(),
  fiscal_year: Yup.number().required().min(2000).max(2100),
  version_name: Yup.string().required().max(100),
});

// BudgetLinesPage - Copy Budget
const copyBudgetSchema = Yup.object({
  source_version_id: Yup.number().required().positive(),
  target_fiscal_year: Yup.number().required().min(2000).max(2100),
  version_name: Yup.string().required().max(100),
});
```

## Error Handling

Error handling remains unchanged from the current implementation:

- API errors are caught in try/catch blocks and displayed via Chakra `useToast`
- Form validation errors are shown inline via Formik's `FormErrorMessage` (replacing the current manual validation in BudgetTemplatesPage)
- Loading states prevent double-submission via `isSubmitting` from Formik or `isLoading` on buttons

## Page-by-Page Change Summary

### BudgetVersionsPage

- Add `useTypedTranslation('budget')` + replace all hardcoded strings
- Add `useFilterableTable` with filters for name, fiscal_year, status, is_active
- Replace `<Th>` with `<FilterableHeader>` components
- Add `bg="gray.800" color="white"` to Table
- Change row hover from `bg: 'whiteAlpha.100'` to `bg: 'gray.700', cursor: 'pointer'`
- Add `display={{ base: 'none', md: 'table-cell' }}` to Active column
- Convert create modal to Formik + Yup with `closeOnOverlayClick={false}`
- Add `bg="gray.800" color="white"` to ModalContent
- Change header `Flex` to use `wrap="wrap"` and `gap={2}`

### BudgetTemplatesPage

- Add `useTypedTranslation('budget')` + replace all hardcoded strings
- Add `useFilterableTable` with filters for name, line_count, created_at
- Replace `<Th>` with `<FilterableHeader>` components
- Add `bg="gray.800" color="white"` to Table
- Replace `_hover={{ bg: 'gray.50' }}` with `_hover={{ bg: 'gray.700', cursor: 'pointer' }}`
- Replace all light backgrounds (gray.50, purple.50, white, red.50, green.50) with dark equivalents
- Add `display={{ base: 'none', md: 'table-cell' }}` to Created column
- Convert template modal to Formik + Yup with `closeOnOverlayClick={false}`
- Replace `colorScheme="blue"` and `colorScheme="green"` on Create Template buttons with `colorScheme="orange"`
- Add `bg="gray.800" color="white"` to ModalContent
- Change modal Save from blue to orange, Delete to red outline
- Add `wrap="wrap"` to header Flex

### BudgetLinesPage

- Add `useTypedTranslation('budget')` + replace all hardcoded strings
- Add `useFilterableTable` with filters for account_code, period_mode, dimension, total
- Replace `<Th>` with `<FilterableHeader>` components
- Add `bg="gray.800" color="white"` to Table
- Replace `_hover={{ bg: 'whiteAlpha.100' }}` with `_hover={{ bg: 'gray.700', cursor: 'pointer' }}`
- Add `display={{ base: 'none', md: 'table-cell' }}` to Dimension column
- Convert line modal to Formik + Yup with `closeOnOverlayClick={false}`
- Add `bg="gray.800" color="white"` to all ModalContent elements
- Ensure Generate Draft and Copy Budget modals also get dark theme + Formik + closeOnOverlayClick
- Change Generate button from teal to orange, Copy button from purple to orange
- Delete button already has red outline — keep as-is

### BudgetDashboard

- Add `useTypedTranslation('budget')` + replace hardcoded strings
- Add `useFilterableTable` with filters for code, name, budget, actual, variance
- Replace `<Th>` with `<FilterableHeader>` components
- Add `bg="gray.800" color="white"` to Table
- Replace `_hover={{ bg: 'whiteAlpha.100' }}` with `_hover={{ bg: 'gray.700', cursor: 'pointer' }}`
- Add `display={{ base: 'none', md: 'table-cell' }}` to Name column
- No Formik needed (dashboard has no CRUD modals, only filter controls)
- Already uses `wrap="wrap"` — verify gap prop

## Correctness Properties

_A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees._

### Property 1: Translation key completeness (EN/NL parity)

For any key present in the English budget translation file (`en/budget.json`), the Dutch translation file (`nl/budget.json`) SHALL also contain a corresponding non-empty string value at the same path.

**Validates: Requirements 2.3, 2.4**

### Property 2: Translation key structure conformance

For any key path in the budget translation files, the top-level category SHALL be one of `titles`, `columns`, `buttons`, `labels`, or `messages`, and the key path SHALL have exactly two segments (`{category}.{key}`).

**Validates: Requirements 2.6**

### Property 3: Column filtering produces matching rows

For any dataset of budget rows and any non-empty filter string applied to a column, all rows in the filtered output SHALL contain the filter string (case-insensitive) in the value of that column.

**Validates: Requirements 3.6**

### Property 4: Column sorting produces ordered output

For any dataset of budget rows and any sortable column, after applying a sort in ascending direction, each consecutive pair of rows SHALL have the sorted column value in non-decreasing order (and non-increasing for descending).

**Validates: Requirements 3.7**

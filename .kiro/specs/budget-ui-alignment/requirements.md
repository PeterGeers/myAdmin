# Requirements Document

## Introduction

Align the four budget module frontend pages (`BudgetVersionsPage`, `BudgetTemplatesPage`, `BudgetLinesPage`, `BudgetDashboard`) with the project's established UI patterns documented in `.kiro/steering/ui-patterns.md`. The reference implementation is `ZZPInvoices.tsx`. This covers seven deviation areas: dark theme consistency, i18n integration, FilterableHeader usage, table styling, modal patterns, responsive design, and action button styling.

## Glossary

- **Budget_Pages**: The set of four React page components: `BudgetVersionsPage.tsx`, `BudgetTemplatesPage.tsx`, `BudgetLinesPage.tsx`, `BudgetDashboard.tsx`
- **UI_Pattern_Standard**: The established UI conventions defined in `.kiro/steering/ui-patterns.md` and demonstrated by `ZZPInvoices.tsx`
- **FilterableHeader**: A reusable column header component providing inline text filter and sort indicators for table columns
- **useFilterableTable**: A custom hook combining column filtering and sorting logic for table data
- **useTypedTranslation**: A typed wrapper hook for `react-i18next` accepting a namespace parameter for scoped translations
- **Dark_Theme**: The application's dark color scheme using `bg="gray.800"`/`bg="gray.900"` backgrounds with `color="white"` text
- **Formik_Yup_Validation**: Form validation pattern using Formik for form state management and Yup for schema-based validation
- **Translation_Namespace**: An i18n namespace scoping translation keys to a module (e.g., `budget`, `common`)

## Requirements

### Requirement 1: Dark Theme Consistency

**User Story:** As a user, I want the budget pages to match the dark theme used throughout the application, so that the interface has a consistent visual appearance.

#### Acceptance Criteria

1. THE Budget_Pages SHALL apply `bg="gray.800"` and `color="white"` on all Table components.
2. THE Budget_Pages SHALL apply `color="white"` on page title Text components.
3. THE BudgetTemplatesPage SHALL replace light-theme backgrounds (`bg="gray.50"`, `bg="purple.50"`, `bg="white"`) with dark-theme equivalents (`bg="gray.700"`, `bg="whiteAlpha.100"`).
4. THE BudgetTemplatesPage SHALL apply `color="white"` on all user-facing text within the page body.
5. WHEN a Modal is rendered on Budget_Pages, THE Modal content SHALL use `bg="gray.800"` and `color="white"` to match the Dark_Theme.

### Requirement 2: Internationalization (i18n) Integration

**User Story:** As a user operating in a Dutch or English locale, I want all budget page text to be translated, so that the interface displays in my preferred language.

#### Acceptance Criteria

1. THE Budget_Pages SHALL use `useTypedTranslation('budget')` for all module-specific user-facing strings.
2. THE Budget_Pages SHALL use keys from the `common` Translation_Namespace for shared UI labels (buttons like Save, Cancel, Delete; messages like loading, no data).
3. WHEN the budget pages are loaded, THE translation system SHALL resolve keys from a `budget` namespace JSON file containing English translations.
4. WHEN the budget pages are loaded, THE translation system SHALL resolve keys from a `budget` namespace JSON file containing Dutch translations.
5. THE Budget_Pages SHALL never render hardcoded user-visible strings directly in JSX.
6. THE translation key structure SHALL follow the pattern `{category}.{key}` where categories include `titles`, `labels`, `buttons`, `messages`, and `columns`.

### Requirement 3: FilterableHeader and Table Filtering

**User Story:** As a user, I want sortable and filterable columns in budget tables, so that I can quickly find specific budget data.

#### Acceptance Criteria

1. THE BudgetVersionsPage SHALL use FilterableHeader components for all column headers (Name, Fiscal Year, Status, Active).
2. THE BudgetTemplatesPage SHALL use FilterableHeader components for all column headers (Name, Lines, Created).
3. THE BudgetLinesPage SHALL use FilterableHeader components for all column headers (Account Code, Period Mode, Dimension, Total).
4. THE BudgetDashboard SHALL use FilterableHeader components for all column headers (Code, Name, Budget, Actual, Variance).
5. THE Budget_Pages SHALL use the `useFilterableTable` hook to combine column filtering and sorting logic.
6. WHEN a user types in a column filter input, THE table SHALL display only rows matching the filter text.
7. WHEN a user clicks a sortable column header, THE table SHALL sort rows by that column in ascending or descending order.

### Requirement 4: Table Styling Standards

**User Story:** As a user, I want consistent table hover and background styling across budget pages, so that the interface feels polished and interactive.

#### Acceptance Criteria

1. THE Budget_Pages SHALL apply `bg="gray.800"` and `color="white"` on all Table components.
2. THE Budget_Pages SHALL apply `_hover={{ bg: 'gray.700', cursor: 'pointer' }}` on all clickable table rows.
3. THE BudgetTemplatesPage SHALL replace `_hover={{ bg: 'gray.50' }}` with `_hover={{ bg: 'gray.700', cursor: 'pointer' }}` on table rows.
4. THE BudgetDashboard and BudgetLinesPage SHALL replace `_hover={{ bg: 'whiteAlpha.100' }}` with `_hover={{ bg: 'gray.700', cursor: 'pointer' }}` on clickable table rows.
5. THE Budget_Pages SHALL wrap tables in a `Box` with `overflowX="auto"` for horizontal scrolling on narrow viewports.

### Requirement 5: Modal Pattern Alignment

**User Story:** As a user, I want modals in budget pages to follow the same validation and interaction patterns used elsewhere, so that forms behave predictably.

#### Acceptance Criteria

1. WHEN an edit modal is opened on Budget_Pages, THE Modal SHALL set `closeOnOverlayClick={false}` to prevent accidental data loss.
2. THE Budget_Pages edit modals SHALL use Formik for form state management.
3. THE Budget_Pages edit modals SHALL use Yup schemas for field validation.
4. THE Modal footer SHALL display a Cancel button with `variant="ghost"` on the left and a Save/Submit button with `colorScheme="orange"` on the right.
5. WHILE a form submission is in progress, THE Save button SHALL display a loading state.
6. THE Modal content SHALL use `bg="gray.800"` and `color="white"` consistent with Dark_Theme.

### Requirement 6: Responsive Design

**User Story:** As a user on a mobile device, I want budget pages to adapt gracefully to smaller screens, so that I can view and manage budget data on any device.

#### Acceptance Criteria

1. THE Budget_Pages headers SHALL use `Flex` with `wrap="wrap"` for action buttons to prevent overflow on narrow viewports.
2. THE BudgetVersionsPage SHALL hide the Active column on mobile viewports using `display={{ base: 'none', md: 'table-cell' }}`.
3. THE BudgetLinesPage SHALL hide the Dimension column on mobile viewports using `display={{ base: 'none', md: 'table-cell' }}`.
4. THE BudgetDashboard SHALL hide the Name column on mobile viewports using `display={{ base: 'none', md: 'table-cell' }}`.
5. THE BudgetTemplatesPage SHALL hide the Created column on mobile viewports using `display={{ base: 'none', md: 'table-cell' }}`.
6. THE Budget_Pages SHALL use responsive size props (e.g., `size={{ base: 'sm', md: 'md' }}`) for buttons and inputs where applicable.

### Requirement 7: Action Button Styling

**User Story:** As a user, I want primary action buttons to be visually consistent across all budget pages, so that I can easily identify key actions.

#### Acceptance Criteria

1. THE Budget_Pages SHALL use `colorScheme="orange"` for all primary action buttons (Create, Add, Save, Generate, Export).
2. THE BudgetTemplatesPage SHALL replace `colorScheme="blue"` and `colorScheme="green"` on primary Create Template buttons with `colorScheme="orange"`.
3. THE BudgetLinesPage SHALL keep `colorScheme="orange"` for the Add Line button and change the Save button in modals from `colorScheme="orange"` to align with standard modal footer pattern (right-aligned, `colorScheme="orange"`).
4. THE Budget_Pages SHALL use `variant="ghost"` for Cancel buttons in modal footers.
5. WHEN a destructive action button (Delete) is present in a modal, THE button SHALL use `colorScheme="red"` with `variant="outline"`.

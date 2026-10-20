# Requirements Document

## Introduction

This feature improves the SAM Member Analytics "Dynamic Pivot Views" field-picker/filter UX with two changes, both frontend-first and derived from the approved design:

1. A shared grouped single-select control (`GroupedFieldSelect`) so the filter-field and measure-column surfaces are grouped and consistent with the existing field checklist, instead of flat ungrouped native dropdowns.
2. Type-adaptive, backward-compatible filter operators so a saved-set filter can express comparisons beyond string equality, while every legacy equality set keeps loading, running, and re-saving identically.

The persisted saved-set `definition.filters` remains OPAQUE to the SAM Members module and the change is READ-ONLY w.r.t. member data (it composes a view definition, never mutates a member).

## Glossary

- **Grouped_Field_Select**: The shared single-select field control that renders candidate fields grouped by functional group (native `<optgroup>`), deriving its grouping from the same `sectionFields()` the field checklist uses.
- **Field_Picker**: The `MemberFieldPicker` modal that composes/edits a saved pivot/list set definition.
- **Filter_Engine**: The pure client function `applyDefinitionFilters` that narrows member rows by a saved set's definition filters at execute time.
- **Picker_Helpers**: The pure transforms `toFilterDrafts` / `fromFilterDrafts` that round-trip the editor's filter rows to/from the persisted filters map.
- **Filter_Clause**: The new persisted object form of a single filter entry, `{ op, value? }`.
- **Legacy_Scalar_Filter**: The pre-feature flat filter entry form `{ fieldKey: value }` meaning case-insensitive trimmed string equality.
- **Filter_Operator**: One of `eq, ne, gt, gte, lt, lte, contains, notContains, regex, notRegex, empty, notEmpty`.
- **Field_Type**: The resolved `FieldConfigField.type` (`string`, `number`, `date`, `enum`, `reference`, `email`, or absent) that drives the offered operator list.
- **Analytics_Set_Store**: The SAM Members DynamoDB saved-set store whose `definition` is validated as an opaque mapping (`sam/members/domain/analytics_set.py`).

## Requirements

### Requirement 1: Shared grouped single-select control

**User Story:** As an analytics user, I want the filter-field and measure-column pickers to be grouped by functional group like the field checklist, so that choosing a field is consistent across the whole picker.

#### Acceptance Criteria

1. THE Grouped_Field_Select SHALL derive its option groups and in-group ordering from the same `sectionFields()` the field checklist uses, producing the same catalog section order and the same alphabetical-within-group order for the same inputs.
2. WHERE a candidate field has no functional group or one absent from the catalog, THE Grouped_Field_Select SHALL render that field in the ungrouped fallback section rather than omitting it.
3. THE Grouped_Field_Select SHALL render each field label resolved to the active language, falling back to Dutch, then English, then the field key.
4. WHERE a placeholder label is supplied, THE Grouped_Field_Select SHALL render it as the first option with an empty-string value.
5. THE Grouped_Field_Select SHALL expose an accessible label on the native select control.
6. WHEN the user selects an option, THE Grouped_Field_Select SHALL invoke its change handler with the selected field key, or with an empty string when the placeholder option is chosen.

### Requirement 2: Reuse the grouped control at both ungrouped surfaces

**User Story:** As a maintainer, I want the three field surfaces to share one grouping rule, so that the filter-field, measure-column, and checklist selectors never drift apart again.

#### Acceptance Criteria

1. THE Field_Picker SHALL render the filter-field selector using the Grouped_Field_Select.
2. THE Field_Picker SHALL render the measure-column selector using the Grouped_Field_Select, with a placeholder option whose empty-string value represents the COUNT-all sentinel.
3. THE Field_Picker SHALL continue to render the group-by and list-column surfaces through the existing shared field checklist.
4. THE Grouped_Field_Select and the field checklist SHALL both consume the same `sectionFields()` grouping function.

### Requirement 3: Type-adaptive operator list

**User Story:** As an analytics user, I want each filter row to offer only the operators that make sense for the chosen field's type, so that I am not offered a substring match on a number or a numeric comparison on free text.

#### Acceptance Criteria

1. WHERE the Field_Type is `number`, THE Field_Picker SHALL offer the operators `eq, ne, gt, gte, lt, lte, empty, notEmpty`.
2. WHERE the Field_Type is `date`, THE Field_Picker SHALL offer the operators `eq, ne, gt, gte, lt, lte, empty, notEmpty`.
3. WHERE the Field_Type is `string`, `enum`, `reference`, `email`, or absent, THE Field_Picker SHALL offer the operators `eq, ne, contains, notContains, regex, notRegex, empty, notEmpty`.
4. THE Field_Picker SHALL offer the operators `eq, ne, empty, notEmpty` for every Field_Type.
5. WHEN a new filter row is added, THE Field_Picker SHALL default its operator to `eq`.
6. WHEN the user changes a filter row's field to a Field_Type whose offered operators exclude the row's current operator, THE Field_Picker SHALL reset that row's operator to `eq`.

### Requirement 4: Operator value input

**User Story:** As an analytics user, I want the value box to disappear for presence checks, so that the row reflects whether a value is needed.

#### Acceptance Criteria

1. WHILE a filter row's operator is `empty` or `notEmpty`, THE Field_Picker SHALL hide or disable that row's value input.
2. WHILE a filter row's operator is any operator other than `empty` or `notEmpty`, THE Field_Picker SHALL show that row's value input.
3. THE Field_Picker SHALL render each filter row as a field selector, an operator selector, and a value input, in that order.

### Requirement 5: Filter engine operator semantics

**User Story:** As an analytics user, I want each operator to narrow the executed set correctly, so that saved views return the members I intend.

#### Acceptance Criteria

1. WHEN the Filter_Engine applies an `eq` clause, THE Filter_Engine SHALL include a row only when the row's value for the key equals the clause value under trimmed, case-insensitive string comparison.
2. WHEN the Filter_Engine applies a `ne` clause, THE Filter_Engine SHALL include a row only when the row's value for the key does not equal the clause value under trimmed, case-insensitive string comparison.
3. WHEN the Filter_Engine applies a `contains` clause, THE Filter_Engine SHALL include a row only when the row's value for the key contains the clause value as a case-insensitive substring.
4. WHERE the Field_Type is `number` and both the row value and the clause value parse as finite numbers, THE Filter_Engine SHALL compare `gt, gte, lt, lte` clauses numerically.
5. WHERE the Field_Type is `date` and both the row value and the clause value parse as valid dates, THE Filter_Engine SHALL compare `gt, gte, lt, lte` clauses by date.
6. IF a comparison operator's row value or clause value does not parse to the typed form, THEN THE Filter_Engine SHALL compare the trimmed values as locale strings.
7. WHEN the Filter_Engine applies an `empty` clause, THE Filter_Engine SHALL include a row only when the row's trimmed string value for the key is empty or the value is absent.
8. WHEN the Filter_Engine applies a `notEmpty` clause, THE Filter_Engine SHALL include a row only when the row's trimmed string value for the key is non-empty.
9. WHEN the Filter_Engine applies multiple active clauses, THE Filter_Engine SHALL include a row only when the row matches every active clause.
10. WHEN the Filter_Engine reads a row value, THE Filter_Engine SHALL resolve the value through the shared nested-or-flat accessor using the field's storage group from the field config.
11. THE Filter_Engine SHALL return a new array and SHALL preserve the input row order.
12. WHEN the Filter_Engine applies a `notContains` clause to a present row value, THE Filter_Engine SHALL include the row only when the row's value for the key does NOT contain the clause value as a case-insensitive substring.
13. IF a `notContains` clause is applied and the row's value for the key is absent, THEN THE Filter_Engine SHALL exclude that row.

### Requirement 6: Blank value and absent clause behavior

**User Story:** As an analytics user, I want an empty value box to mean "no filter", so that an unfinished row never hides every member.

#### Acceptance Criteria

1. WHERE a value-taking operator clause has a blank value, THE Filter_Engine SHALL treat that clause as inactive and apply no narrowing for it.
2. WHEN the filters map is absent or empty, THE Filter_Engine SHALL return all rows.
3. IF a filters entry is null or undefined, THEN THE Filter_Engine SHALL treat that entry as no narrowing.
4. IF the rows input is not an array, THEN THE Filter_Engine SHALL return an empty array.

### Requirement 7: Regex operator with invalid-pattern guard

**User Story:** As an analytics user, I want a regex filter that never crashes the view, so that a typo in a pattern produces an error I can fix instead of a broken page.

#### Acceptance Criteria

1. WHEN the Filter_Engine applies a `regex` clause with a valid pattern, THE Filter_Engine SHALL include a row only when the row's value for the key matches the pattern compiled case-insensitively.
2. IF a `regex` clause pattern is invalid, THEN THE Filter_Engine SHALL match no row for that clause and SHALL complete without throwing.
3. IF a filter row's operator is `regex` and its value is an invalid pattern, THEN THE Field_Picker SHALL display an inline bilingual invalid-pattern message on that row.
4. THE Field_Picker SHALL allow saving a set that contains a filter row with an invalid regex pattern.
5. WHEN the Filter_Engine applies a `notRegex` clause with a valid pattern to a present row value, THE Filter_Engine SHALL include the row only when the row's value for the key does NOT match the pattern compiled case-insensitively.
6. IF a `notRegex` clause pattern is invalid, THEN THE Filter_Engine SHALL match no row for that clause and SHALL complete without throwing, consistent with the `regex` guard.
7. IF a filter row's operator is `notRegex` and its value is an invalid pattern, THEN THE Field_Picker SHALL display the same inline bilingual invalid-pattern message on that row as for `regex`.

### Requirement 8: Backward compatibility and round-trip

**User Story:** As an existing user, I want my previously saved filtered sets to keep working unchanged, so that upgrading does not break any saved view.

#### Acceptance Criteria

1. WHEN the Filter_Engine reads a Legacy_Scalar_Filter entry, THE Filter_Engine SHALL interpret it as an `eq` clause whose value is the stringified scalar.
2. WHEN the Picker_Helpers read a Legacy_Scalar_Filter entry, THE Picker_Helpers SHALL produce a filter row with operator `eq` and the stringified scalar value.
3. IF a stored Filter_Clause carries an operator outside the Filter_Operator set, THEN THE Filter_Engine SHALL interpret that clause as `eq`.
4. WHEN the Picker_Helpers compose filter rows into the persisted map, THE Picker_Helpers SHALL emit the Filter_Clause object form, including `value` only for value-taking operators.
5. WHEN the Picker_Helpers read a filters map, THE Picker_Helpers SHALL produce an editable filter row for every non-null entry, excluding no key, including the keys `years_member` and `joined_after_year`.
6. WHEN the Picker_Helpers compose filter rows, THE Picker_Helpers SHALL drop a row with an empty field key, and SHALL drop a value-taking row with a blank value, while keeping `empty` and `notEmpty` rows that carry no value.
7. FOR ALL editor filter rows, composing them to the persisted map then reading them back SHALL produce rows equivalent on field, operator, and value for every kept row, excluding no key (round-trip property).
8. WHEN a saved set created before this feature is loaded, run, and re-saved, THE Field_Picker and Filter_Engine SHALL yield the same narrowing result after re-save as before (equivalent behavior).
9. WHEN the Picker_Helpers read a Legacy_Scalar_Filter entry whose key is `years_member` or `joined_after_year`, THE Picker_Helpers SHALL produce an editable filter row with operator `eq` and the stringified scalar value, and THE Filter_Engine SHALL narrow that entry identically to any other `eq` clause.

### Requirement 9: Opaque backend definition round-trip

**User Story:** As a maintainer, I want the richer filter structure to persist without a backend change, so that the saved-set store stays agnostic to the filter shape.

#### Acceptance Criteria

1. THE Analytics_Set_Store SHALL continue to validate the saved-set `definition` as a mapping without inspecting the `filters` entry shape.
2. WHEN a saved set's `definition.filters` contains an object-valued Filter_Clause entry, THE Analytics_Set_Store SHALL round-trip that entry unchanged through its item serialization and deserialization.
3. THE feature SHALL NOT require any change to the SAM Members module to persist object-valued filter entries.

### Requirement 10: Internationalization

**User Story:** As a Dutch or English user, I want every new control labeled in my language, so that the picker stays fully bilingual.

#### Acceptance Criteria

1. THE Field_Picker SHALL render the operator selector label and every operator option label from the `analytics.pivotViews.fieldPicker.*` keys in the members namespace.
2. THE Field_Picker SHALL render the invalid-pattern message from the members namespace keys.
3. THE feature SHALL add every new key to both the Dutch and the English members translation files.
4. THE feature SHALL NOT introduce hardcoded English strings in the Field_Picker or the Grouped_Field_Select.

### Requirement 11: Scope boundaries

**User Story:** As a maintainer, I want this feature confined to the filter and field-selector UX, so that it does not alter unrelated analytics behavior.

#### Acceptance Criteria

1. THE feature SHALL NOT change aggregate-measure semantics.
2. THE feature SHALL NOT change group-column or list-column behavior.
3. THE feature SHALL NOT change saved-set scheduling or delivery.
4. THE feature SHALL compose a saved view definition and SHALL NOT mutate any member record.
5. THE Field_Picker and Grouped_Field_Select SHALL remain keyboard accessible and dark-theme consistent.

/**
 * GroupedFieldSelect — the shared, grouped single-select field control
 * (member-analytics-pivot-filter-operators C1, task 5.1; R1.1–R1.6, R11.5).
 *
 * The native `<optgroup>` analogue of {@link FieldChecklist}: a dark-theme
 * Chakra `Select` whose options are bucketed into functional-group sections,
 * deriving its grouping from the SAME `sectionFields()` the checklist uses so
 * the three field surfaces (checklist, filter-field, measure-column) stay
 * consistent and never drift (R2.4). It is the checklist's single-select
 * sibling, reused by `MemberFieldPicker` at both of its previously-flat
 * `<Select>` surfaces (filter-field and measure-column).
 *
 * Behaviour (mirrors the checklist's grouping rule, as a single-select):
 *   - `sectionFields()` grouping — functional-group sections in the tenant's
 *     `functional_groups` catalog `order`, alphabetical within each section by
 *     the resolved (active-language) label; a field with no group — or one not
 *     in the catalog — falls into a single ungrouped fallback section appended
 *     last, rendered WITHOUT an enclosing `<optgroup>` so such a field never
 *     disappears (R1.1, R1.2).
 *   - bilingual labels via `resolveLabel` (active language → `nl` → `en` → key)
 *     for both the `<optgroup label>` headings and every `<option>` (R1.3).
 *   - an optional placeholder rendered as the first `value=''` option, so a
 *     caller that must allow an empty value (e.g. the COUNT-all sentinel) can
 *     offer it (R1.4).
 *   - an always-present `aria-label` on the native `<select>` (R1.5), and a
 *     change handler invoked with the selected field key — or `''` when the
 *     placeholder is chosen (R1.6).
 *
 * This component is PRESENTATION + selection only — it owns no selection state;
 * the parent passes the current `value` and receives the newly-selected key via
 * `onChange`. It introduces no English of its own: `ariaLabel` and the optional
 * `placeholder` are passed in already-resolved by the caller (R10.4).
 *
 * @module components/members/GroupedFieldSelect
 * @see .kiro/specs/Members/member-analytics-pivot-filter-operators (design C1; R1.1–R1.6, R2.4, R11.5)
 */

import React, { useMemo } from 'react';
import { Select } from '@chakra-ui/react';
import type { FieldConfigField, FunctionalGroup } from '../../types/members';
import { resolveLabel, sectionFields, DEFAULT_FG_SECTION_KEY } from './FieldChecklist';

// Native <option>/<optgroup> elements render with the OS dropdown palette and do
// NOT inherit the Chakra Select's bg/color — so without an explicit inline style
// they show as white-on-orange options and white-on-white group headers. Pin the
// same dark palette the control (and the pivot field selectors) use. (member-
// analytics-pivot-filter-operators styling fix.)
const OPTION_STYLE: React.CSSProperties = { backgroundColor: '#171923', color: 'white' }; // gray.900 / white
const OPTGROUP_STYLE: React.CSSProperties = { backgroundColor: '#1A202C', color: '#CBD5E0' }; // gray.800 / gray.300

export interface GroupedFieldSelectProps {
  /** The candidate fields to offer — already filtered to the caller's set (e.g. pickableFields). */
  fields: FieldConfigField[];
  /** The currently-selected field key, or '' for the no-selection sentinel. */
  value: string;
  /** Fired with the newly-selected field key (or '' when the placeholder is chosen). */
  onChange: (key: string) => void;
  /** The tenant's functional-group catalog (drives optgroup order + headings). */
  functionalGroups: FunctionalGroup[] | undefined;
  /** Active language for bilingual label resolution. */
  lang: string;
  /** Accessible label for the native <select> (required — no visible <label> at some call sites). */
  ariaLabel: string;
  /**
   * The placeholder option label shown as the first, value='' entry (e.g.
   * "Field" / "All rows"). When omitted, no placeholder option is rendered and
   * the first real field is the default — callers that must allow an empty
   * value MUST pass this.
   */
  placeholder?: string;
  /** data-testid for the rendered <select>. */
  testId?: string;
  /** Optional max width passthrough for dark-theme layout parity with existing selects. */
  maxW?: string;
}

/**
 * The shared grouped single-select: `<optgroup>`s of per-field `<option>`s with
 * bilingual labels, grouped by the same `sectionFields()` rule the checklist
 * uses. Selection is driven by the parent (`value`) and reported back through
 * `onChange(key)` (key, or '' for the placeholder).
 */
export const GroupedFieldSelect: React.FC<GroupedFieldSelectProps> = ({
  fields,
  value,
  onChange,
  functionalGroups,
  lang,
  ariaLabel,
  placeholder,
  testId,
  maxW,
}) => {
  const sections = useMemo(
    () => sectionFields(fields, functionalGroups, lang),
    [fields, functionalGroups, lang],
  );

  return (
    <Select
      aria-label={ariaLabel}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      bg="gray.900"
      color="white"
      {...(maxW ? { maxW } : {})}
      {...(testId ? { 'data-testid': testId } : {})}
    >
      {/* Placeholder as the first, empty-value option when supplied (R1.4). */}
      {placeholder !== undefined && (
        <option value="" style={OPTION_STYLE}>
          {placeholder}
        </option>
      )}
      {sections.map((section) =>
        // The ungrouped fallback renders its options WITHOUT an enclosing
        // <optgroup> so a field with no (or a dangling) functional group never
        // disappears (R1.2). Grouped sections wrap their options in an
        // <optgroup> whose label is the resolved (bilingual) heading (R1.3).
        section.key === DEFAULT_FG_SECTION_KEY ? (
          <React.Fragment key={section.key}>
            {section.fields.map((f) => (
              <option key={f.key} value={f.key} style={OPTION_STYLE}>
                {resolveLabel(f.label, lang, f.key)}
              </option>
            ))}
          </React.Fragment>
        ) : (
          <optgroup
            key={section.key}
            label={resolveLabel(section.label, lang, section.key)}
            style={OPTGROUP_STYLE}
          >
            {section.fields.map((f) => (
              <option key={f.key} value={f.key} style={OPTION_STYLE}>
                {resolveLabel(f.label, lang, f.key)}
              </option>
            ))}
          </optgroup>
        ),
      )}
    </Select>
  );
};

export default GroupedFieldSelect;

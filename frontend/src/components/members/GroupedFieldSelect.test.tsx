/**
 * Component tests for GroupedFieldSelect
 * (components/members/GroupedFieldSelect.tsx).
 *
 * The shared, grouped single-select sibling of FieldChecklist built in
 * member-analytics-pivot-filter-operators C1 (task 5.2). These tests pin the
 * five behaviours MemberFieldPicker relies on at its filter-field and
 * measure-column surfaces, all exercised THROUGH the rendered native
 * `<select>`:
 *
 *   1. a supplied placeholder renders FIRST as an empty-string (`value=''`)
 *      option, ahead of every grouped option (R1.4);
 *   2. the native `<select>` always carries the `aria-label` passed by the
 *      caller (R1.5);
 *   3. selecting a field option fires `onChange` with that field's KEY;
 *      selecting the placeholder fires `onChange` with `''` (R1.6);
 *   4. labels resolve to the active language through `resolveLabel`
 *      (active → nl → en → key) for both `<optgroup>` headings and `<option>`s
 *      (R1.3);
 *   5. the ungrouped fallback (a field with no, or a dangling, functional
 *      group) renders its `<option>` WITHOUT an enclosing `<optgroup>` so it
 *      never disappears (R1.2).
 *
 * HARNESS NOTE: the suite renders through the centralized Chakra mock
 * (`src/__mocks__/chakra-ui-react.tsx`, aliased in vite.config.ts), whose
 * `Select` renders a native `<select>` and passes `aria-label` / `data-testid`
 * straight through (its style props — e.g. `maxW` — are stripped by the shared
 * prop filter). The component renders its OWN `value=''` placeholder option as
 * the first child (it never passes Chakra's `placeholder` prop), so there is no
 * double placeholder. `<optgroup>`/`<option>` children render natively, so the
 * DOM structure (optgroups, option order, option values) is directly
 * assertable.
 *
 * GroupedFieldSelect is presentation-only and resolves labels through
 * `resolveLabel` (no i18n namespace), so assertions are locale-independent and
 * need no i18n mock.
 */
import { vi, describe, it, expect } from 'vitest';
import React from 'react';

import { render, screen, fireEvent } from '@/test-utils';
import GroupedFieldSelect from './GroupedFieldSelect';
import type { FieldConfigField, FunctionalGroup } from '../../types/members';

/** The rendered native <select> (addressed by its testid). */
function selectEl(testid = 'grouped-select'): HTMLSelectElement {
  return screen.getByTestId(testid) as HTMLSelectElement;
}

/** The ordered `<option>` elements inside the rendered <select>. */
function optionEls(testid = 'grouped-select'): HTMLOptionElement[] {
  return Array.from(selectEl(testid).querySelectorAll('option'));
}

/** The ordered [value] of every rendered option, placeholder first. */
function optionValues(testid = 'grouped-select'): string[] {
  return optionEls(testid).map((o) => o.value);
}

function makeProps(
  overrides: Partial<React.ComponentProps<typeof GroupedFieldSelect>> = {},
): React.ComponentProps<typeof GroupedFieldSelect> {
  return {
    fields: [],
    value: '',
    onChange: vi.fn(),
    functionalGroups: undefined,
    lang: 'en',
    ariaLabel: 'Field',
    testId: 'grouped-select',
    ...overrides,
  };
}

describe('GroupedFieldSelect', () => {
  // --- (1) placeholder renders first as an empty-value option (R1.4) ---
  describe('placeholder option (R1.4)', () => {
    const fields: FieldConfigField[] = [
      { key: 'email', label: { en: 'Email' } },
      { key: 'region', label: { en: 'Region' } },
    ];

    it('renders a supplied placeholder as the first option with an empty-string value', () => {
      render(
        <GroupedFieldSelect
          {...makeProps({ fields, placeholder: 'All rows' })}
        />,
      );

      const options = optionEls();
      // First option is the placeholder: empty-string value, placeholder text.
      expect(options[0]).toHaveValue('');
      expect(options[0]).toHaveTextContent('All rows');
      // … and it precedes every real field option.
      expect(optionValues()).toEqual(['', 'email', 'region']);
    });

    it('renders NO empty-value option when no placeholder is supplied', () => {
      render(<GroupedFieldSelect {...makeProps({ fields })} />);
      // Only the two real field options — no leading value='' entry.
      expect(optionValues()).toEqual(['email', 'region']);
    });
  });

  // --- (2) accessible label on the native select (R1.5) ---
  describe('accessible label (R1.5)', () => {
    it('exposes the supplied aria-label on the native select', () => {
      render(
        <GroupedFieldSelect
          {...makeProps({
            fields: [{ key: 'email', label: { en: 'Email' } }],
            ariaLabel: 'Measure column',
          })}
        />,
      );
      // Addressable by its accessible name — the aria-label the caller passed.
      expect(screen.getByLabelText('Measure column')).toBe(selectEl());
    });
  });

  // --- (3) onChange fires the field key, or '' for the placeholder (R1.6) ---
  describe('onChange reports the selected key (R1.6)', () => {
    const fields: FieldConfigField[] = [
      { key: 'email', label: { en: 'Email' } },
      { key: 'region', label: { en: 'Region' } },
    ];

    it('invokes onChange with the selected field key', () => {
      const onChange = vi.fn();
      render(
        <GroupedFieldSelect
          {...makeProps({ fields, placeholder: 'Field', value: '', onChange })}
        />,
      );

      fireEvent.change(selectEl(), { target: { value: 'region' } });
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenCalledWith('region');
    });

    it('invokes onChange with an empty string when the placeholder is chosen', () => {
      const onChange = vi.fn();
      // Start on a real field, then select the placeholder → '' is reported.
      render(
        <GroupedFieldSelect
          {...makeProps({ fields, placeholder: 'Field', value: 'region', onChange })}
        />,
      );

      fireEvent.change(selectEl(), { target: { value: '' } });
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenCalledWith('');
    });
  });

  // --- (4) bilingual labels for optgroups + options (R1.3) ---
  describe('bilingual labels (R1.3)', () => {
    const functionalGroups: FunctionalGroup[] = [
      { key: 'contact', label: { en: 'Contact', nl: 'Contactgegevens' }, order: 1 },
    ];
    const fields: FieldConfigField[] = [
      { key: 'name', functional_group: 'contact', label: { nl: 'Naam', en: 'Name' } },
      // nl-only label → en falls back to nl (fallback chain).
      { key: 'phone', functional_group: 'contact', label: { nl: 'Telefoon' } },
      // no label at all → falls back to the key.
      { key: 'raw', functional_group: 'contact' },
    ];

    it('resolves option + optgroup labels to Dutch when lang=nl', () => {
      render(
        <GroupedFieldSelect {...makeProps({ fields, functionalGroups, lang: 'nl' })} />,
      );

      const group = selectEl().querySelector('optgroup') as HTMLOptGroupElement;
      expect(group).toHaveAttribute('label', 'Contactgegevens');

      const byValue = (v: string) =>
        optionEls().find((o) => o.value === v) as HTMLOptionElement;
      expect(byValue('name')).toHaveTextContent('Naam');
      expect(byValue('phone')).toHaveTextContent('Telefoon');
      expect(byValue('raw')).toHaveTextContent('raw');
    });

    it('resolves labels to English when lang=en, falling back nl then key', () => {
      render(
        <GroupedFieldSelect {...makeProps({ fields, functionalGroups, lang: 'en' })} />,
      );

      const group = selectEl().querySelector('optgroup') as HTMLOptGroupElement;
      expect(group).toHaveAttribute('label', 'Contact');

      const byValue = (v: string) =>
        optionEls().find((o) => o.value === v) as HTMLOptionElement;
      expect(byValue('name')).toHaveTextContent('Name');
      // No en label → nl fallback.
      expect(byValue('phone')).toHaveTextContent('Telefoon');
      // No label at all → key fallback.
      expect(byValue('raw')).toHaveTextContent('raw');
    });
  });

  // --- (5) ungrouped fallback renders no-group fields without an optgroup (R1.2) ---
  describe('ungrouped fallback (R1.2)', () => {
    it('renders a field with no/dangling functional group WITHOUT an optgroup', () => {
      const functionalGroups: FunctionalGroup[] = [
        { key: 'contact', label: { en: 'Contact' }, order: 1 },
      ];
      const fields: FieldConfigField[] = [
        { key: 'email', functional_group: 'contact', label: { en: 'Email' } },
        // No functional group → ungrouped fallback.
        { key: 'notes', label: { en: 'Notes' } },
        // Dangling group (not in the catalog) → ungrouped fallback.
        { key: 'ghost', functional_group: 'nope', label: { en: 'Ghost' } },
      ];

      render(
        <GroupedFieldSelect {...makeProps({ fields, functionalGroups, lang: 'en' })} />,
      );

      // Exactly one optgroup (the catalog "contact" section) …
      const groups = Array.from(selectEl().querySelectorAll('optgroup'));
      expect(groups).toHaveLength(1);
      // … and it holds ONLY the grouped field.
      expect(
        Array.from(groups[0].querySelectorAll('option')).map((o) => o.value),
      ).toEqual(['email']);

      // The ungrouped fields render as options NOT nested in any optgroup, and
      // after the grouped section (fallback appended last).
      const topLevelOptions = Array.from(selectEl().children).filter(
        (c): c is HTMLOptionElement => c.tagName === 'OPTION',
      );
      expect(topLevelOptions.map((o) => o.value)).toEqual(['ghost', 'notes']);
    });

    it('renders all fields ungrouped when no functional-group catalog is given', () => {
      const fields: FieldConfigField[] = [
        { key: 'region', label: { en: 'Region' } },
        { key: 'email', label: { en: 'Email' } },
      ];
      render(<GroupedFieldSelect {...makeProps({ fields, functionalGroups: undefined })} />);

      // No optgroups at all; both fields are top-level options, alphabetical by
      // resolved label (Email < Region).
      expect(selectEl().querySelectorAll('optgroup')).toHaveLength(0);
      expect(optionValues()).toEqual(['email', 'region']);
    });
  });
});

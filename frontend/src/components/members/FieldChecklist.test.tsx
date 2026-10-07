/**
 * Component tests for FieldChecklist (components/members/FieldChecklist.tsx).
 *
 * The shared checklist core extracted from MemberFieldPicker (session-columns
 * C1, task 1.3). These tests pin the four behaviours the column chooser + the
 * pivot picker both rely on:
 *
 *   1. functional-group sections render in the catalog `order`, with fields
 *      sorted ALPHABETICALLY (by resolved label) WITHIN each section, and a
 *      field with no/dangling group falling into an unlabelled "ungrouped"
 *      section appended last (R1.1 — the chooser's grouping/ordering contract);
 *   2. `disabledKeys` render CHECKED and LOCKED, regardless of the `selectedKeys`
 *      set (R1.4 / R7.2 — member_number always-on, not toggleable);
 *   3. `onToggle` fires with the field KEY when a checkbox is toggled (R1.4);
 *   4. bilingual labels resolve for `nl` and `en` via `resolveLabel`, with the
 *      documented fallback chain (active language → nl → en → key) (R5.2).
 *
 * FieldChecklist is presentation-only and resolves labels through `resolveLabel`
 * (no i18n namespace), so assertions are locale-independent and need no i18n
 * mock. Checkboxes are addressed by their testid (`field-checklist-<key>`) and
 * the underlying <input> is read for checked state, mirroring the
 * MemberFieldPicker.test.tsx pattern for Chakra Checkbox wrappers.
 *
 * HARNESS NOTE (the "locked" assertions): the whole suite renders through the
 * centralized Chakra mock (`src/__mocks__/chakra-ui-react.tsx`, aliased in
 * vite.config.ts), whose `Checkbox` passes `isChecked`/`onChange` to the native
 * <input> but DROPS `isDisabled` (it never lands on the input). So the LOCK is
 * not observable as a DOM `disabled` attribute here, and a click on a locked
 * input still fires `onChange`. The real `@chakra-ui/react` Checkbox honours
 * `isDisabled` (and the component DOES pass `isDisabled={isLocked}` — see
 * FieldChecklist.tsx). We therefore pin the ALWAYS-ON half of R7.2 that the
 * harness CAN express: a `disabledKeys` entry renders CHECKED even when it is
 * absent from `selectedKeys` — the behaviour the column chooser depends on for
 * member_number. The disabled-attribute lock is covered at the integration
 * level (ColumnChooser / MembersPage) against the real toggle flow.
 */
import { vi, describe, it, expect } from 'vitest';
import React from 'react';

import { render, screen, fireEvent } from '@/test-utils';
import FieldChecklist, { resolveLabel } from './FieldChecklist';
import type { FieldConfigField, FunctionalGroup } from '../../types/members';

/** The checkbox <input> inside a testid'd Chakra Checkbox wrapper. */
function checkboxInput(testid: string): HTMLInputElement {
  return screen.getByTestId(testid).querySelector('input') as HTMLInputElement;
}

/** The ordered per-field checkbox testids rendered inside the checklist. */
function renderedFieldOrder(): string[] {
  const root = screen.getByTestId('field-checklist-fields');
  return Array.from(root.querySelectorAll('[data-testid^="field-checklist-"]'))
    .map((el) => el.getAttribute('data-testid'))
    // Keep only the per-field checkbox testids (drop the section wrappers +
    // the root `-fields` container).
    .filter(
      (id): id is string =>
        !!id && !id.includes('-section-') && id !== 'field-checklist-fields',
    );
}

function makeProps(
  overrides: Partial<React.ComponentProps<typeof FieldChecklist>> = {},
): React.ComponentProps<typeof FieldChecklist> {
  return {
    fields: [],
    selectedKeys: [],
    functionalGroups: undefined,
    lang: 'en',
    onToggle: vi.fn(),
    ...overrides,
  };
}

describe('FieldChecklist', () => {
  // --- (1) functional-group sections in catalog order, alpha within (R1.1) ---
  describe('sectioning + ordering (R1.1)', () => {
    // Two groups, catalog order contact (1) THEN membership (2); fields are
    // deliberately out of alphabetical order within each group, and one field
    // has no functional group (→ ungrouped fallback, appended last).
    const functionalGroups: FunctionalGroup[] = [
      { key: 'contact', label: { en: 'Contact', nl: 'Contact' }, order: 1 },
      { key: 'membership', label: { en: 'Membership', nl: 'Lidmaatschap' }, order: 2 },
    ];
    const fields: FieldConfigField[] = [
      { key: 'phone', functional_group: 'contact', label: { en: 'Phone' } },
      { key: 'email', functional_group: 'contact', label: { en: 'Email' } },
      { key: 'tier', functional_group: 'membership', label: { en: 'Tier' } },
      { key: 'joined', functional_group: 'membership', label: { en: 'Joined' } },
      // No functional group → appended last in an unlabelled "ungrouped" section.
      { key: 'notes', label: { en: 'Notes' } },
    ];

    it('renders sections in catalog order with fields alphabetical within each', () => {
      render(<FieldChecklist {...makeProps({ fields, functionalGroups, lang: 'en' })} />);

      // contact first (Email < Phone), then membership (Joined < Tier), then
      // the ungrouped fallback (Notes) — sections in catalog order, fields
      // alphabetical (by resolved label) within each.
      expect(renderedFieldOrder()).toEqual([
        'field-checklist-email',
        'field-checklist-phone',
        'field-checklist-joined',
        'field-checklist-tier',
        'field-checklist-notes',
      ]);
    });

    it('renders a heading per catalog section (resolved to the active language)', () => {
      render(<FieldChecklist {...makeProps({ fields, functionalGroups, lang: 'nl' })} />);

      // Section wrappers exist for both catalog groups, headings in the active
      // language (nl → "Lidmaatschap" for membership).
      expect(screen.getByTestId('field-checklist-section-contact')).toHaveTextContent('Contact');
      expect(screen.getByTestId('field-checklist-section-membership')).toHaveTextContent(
        'Lidmaatschap',
      );
    });

    it('orders sections by catalog order, not by catalog array position', () => {
      // Catalog listed membership-first but with a HIGHER order → it must still
      // render AFTER contact (order drives section order, not array position).
      const outOfOrderCatalog: FunctionalGroup[] = [
        { key: 'membership', label: { en: 'Membership' }, order: 2 },
        { key: 'contact', label: { en: 'Contact' }, order: 1 },
      ];
      render(
        <FieldChecklist
          {...makeProps({ fields, functionalGroups: outOfOrderCatalog, lang: 'en' })}
        />,
      );
      expect(renderedFieldOrder()).toEqual([
        'field-checklist-email',
        'field-checklist-phone',
        'field-checklist-joined',
        'field-checklist-tier',
        'field-checklist-notes',
      ]);
    });
  });

  // --- (2) disabledKeys render checked + locked (R1.4 / R7.2) ---
  describe('disabledKeys render checked + locked (R1.4)', () => {
    const fields: FieldConfigField[] = [
      { key: 'member_number', label: { en: 'Member number' } },
      { key: 'email', label: { en: 'Email' } },
    ];

    it('renders a disabled key as checked even when it is NOT in selectedKeys', () => {
      // The always-on contract (R7.2): a locked key shows checked regardless of
      // the selection set, so member_number stays visibly present in the chooser
      // even though the parent never lists it among selectedKeys.
      render(
        <FieldChecklist
          {...makeProps({
            fields,
            selectedKeys: [], // member_number is NOT selected …
            disabledKeys: ['member_number'],
            lang: 'en',
          })}
        />,
      );

      // … yet it renders checked (always-on). (The disabled LOCK itself is not
      // observable through the shared Chakra mock — see the HARNESS NOTE above.)
      expect(checkboxInput('field-checklist-member_number')).toBeChecked();

      // A non-disabled, non-selected field is unchecked.
      expect(checkboxInput('field-checklist-email')).not.toBeChecked();
    });

    it('reflects selectedKeys for non-disabled fields', () => {
      render(
        <FieldChecklist
          {...makeProps({
            fields,
            selectedKeys: ['email'],
            disabledKeys: ['member_number'],
            lang: 'en',
          })}
        />,
      );
      expect(checkboxInput('field-checklist-email')).toBeChecked();
    });
  });

  // --- (3) onToggle fires with the field key (R1.4) ---
  describe('onToggle fires with the field key (R1.4)', () => {
    const fields: FieldConfigField[] = [
      { key: 'member_number', label: { en: 'Member number' } },
      { key: 'email', label: { en: 'Email' } },
    ];

    it('calls onToggle with the field key when a free checkbox is toggled', () => {
      const onToggle = vi.fn();
      render(
        <FieldChecklist
          {...makeProps({ fields, disabledKeys: ['member_number'], onToggle, lang: 'en' })}
        />,
      );

      fireEvent.click(checkboxInput('field-checklist-email'));
      expect(onToggle).toHaveBeenCalledTimes(1);
      expect(onToggle).toHaveBeenCalledWith('email');
    });

    it('reports the exact key for each toggled field (not a stale/shared key)', () => {
      // Toggling two different fields must report each field's OWN key — pins
      // that onToggle is keyed per-checkbox (`f.key`), not a closed-over value.
      const onToggle = vi.fn();
      const multi: FieldConfigField[] = [
        { key: 'email', label: { en: 'Email' } },
        { key: 'phone', label: { en: 'Phone' } },
      ];
      render(<FieldChecklist {...makeProps({ fields: multi, onToggle, lang: 'en' })} />);

      fireEvent.click(checkboxInput('field-checklist-phone'));
      fireEvent.click(checkboxInput('field-checklist-email'));
      expect(onToggle.mock.calls).toEqual([['phone'], ['email']]);
    });
  });

  // --- (4) bilingual labels resolve for nl and en (R5.2) ---
  describe('bilingual labels (R5.2)', () => {
    const fields: FieldConfigField[] = [
      { key: 'name', label: { nl: 'Naam', en: 'Name' } },
      // nl-only label → en falls back to nl (fallback chain).
      { key: 'phone', label: { nl: 'Telefoon' } },
      // no label at all → falls back to the key.
      { key: 'raw' },
    ];

    it('resolves labels to Dutch when lang=nl', () => {
      render(<FieldChecklist {...makeProps({ fields, lang: 'nl' })} />);
      expect(screen.getByTestId('field-checklist-name')).toHaveTextContent('Naam');
      expect(screen.getByTestId('field-checklist-phone')).toHaveTextContent('Telefoon');
      expect(screen.getByTestId('field-checklist-raw')).toHaveTextContent('raw');
    });

    it('resolves labels to English when lang=en, falling back nl then key', () => {
      render(<FieldChecklist {...makeProps({ fields, lang: 'en' })} />);
      expect(screen.getByTestId('field-checklist-name')).toHaveTextContent('Name');
      // No en label → nl fallback.
      expect(screen.getByTestId('field-checklist-phone')).toHaveTextContent('Telefoon');
      // No label at all → key fallback.
      expect(screen.getByTestId('field-checklist-raw')).toHaveTextContent('raw');
    });

    it('resolveLabel follows the active-language → nl → en → fallback chain', () => {
      expect(resolveLabel({ nl: 'Naam', en: 'Name' }, 'nl', 'k')).toBe('Naam');
      expect(resolveLabel({ nl: 'Naam', en: 'Name' }, 'en', 'k')).toBe('Name');
      // Active language absent → nl, then en.
      expect(resolveLabel({ en: 'Name' }, 'nl', 'k')).toBe('Name');
      expect(resolveLabel({ nl: 'Naam' }, 'en', 'k')).toBe('Naam');
      // Plain string passes through; empty/undefined → fallback.
      expect(resolveLabel('Plain', 'en', 'k')).toBe('Plain');
      expect(resolveLabel(undefined, 'en', 'k')).toBe('k');
    });
  });
});

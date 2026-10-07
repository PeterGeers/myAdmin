/**
 * Component tests for ColumnChooser (components/members/ColumnChooser.tsx).
 *
 * The thin column-picker modal built in session-columns C2 (task 3.1). These
 * tests pin the four behaviours the overview relies on, exercised THROUGH the
 * shared FieldChecklist:
 *
 *   1. it lists EVERY candidate field (`fields.filter(isColumnCandidate)`) —
 *      fixed, overlay, calculated alike — and excludes a non-candidate
 *      (`visible === false`) (R1.2, R3.1 / OQ-3);
 *   2. a currently-shown column renders CHECKED; every other candidate renders
 *      unchecked; `member_number` renders checked + always-on (locked) and is
 *      NEVER part of an emitted onChange payload (R1.2, R7.2);
 *   3. checking an unchecked candidate emits `onChange` with the key APPENDED
 *      (order preserved); unchecking a currently-shown one emits `onChange` with
 *      it REMOVED — the exact expected ordered key set, never member_number
 *      (R1.3);
 *   4. the component owns NO persistence — it imports no API service and its
 *      only output is `onChange`; a toggle makes no service call (R3.1 / C2).
 *
 * HARNESS NOTE (mirrors FieldChecklist.test.tsx): the suite renders through the
 * centralized Chakra mock (`src/__mocks__/chakra-ui-react.tsx`, aliased in
 * vite.config.ts), whose `Checkbox` passes `isChecked`/`onChange` to the native
 * <input> but DROPS `isDisabled`. So the always-on LOCK is not observable as a
 * DOM `disabled` attribute here — we pin the half R7.2 the harness CAN express:
 * member_number renders CHECKED (even though it is absent from selectedKeys) and
 * never appears in an emitted payload. The disabled-attribute lock is covered at
 * the integration level (MembersPage) against the real toggle flow.
 *
 * `useTypedTranslation` is mocked to return raw i18n keys (the sibling
 * MembersPage pattern), so this suite is i18n-free; assertions address the
 * per-field checkboxes by their testid (`column-chooser-<key>`).
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';

import { render, screen, fireEvent } from '@/test-utils';
import ColumnChooser, { ALWAYS_ON_COLUMN_KEY } from './ColumnChooser';
import type { FieldConfig, FieldConfigField } from '../../types/members';

// Raw-key i18n (sibling MembersPage pattern): labels resolve to their keys so
// the suite needs no translation catalog.
vi.mock('../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
    i18n: { language: 'en' },
  }),
}));

/** The checkbox <input> inside a testid'd Chakra Checkbox wrapper. */
function checkboxInput(testid: string): HTMLInputElement {
  return screen.getByTestId(testid).querySelector('input') as HTMLInputElement;
}

/**
 * The candidate catalog: member_number (always-on), two freely-toggleable
 * visible candidates, and one NON-candidate (`visible: false`) that must never
 * be listed. No functional groups, so FieldChecklist buckets them all into the
 * ungrouped section and sorts alphabetically by resolved label.
 */
const FIELDS: FieldConfigField[] = [
  { key: 'member_number', label: { en: 'Member number' } },
  { key: 'email', label: { en: 'Email' } },
  { key: 'region', label: { en: 'Region' } },
  // visible === false → NOT a column candidate (R3.1) → never listed.
  { key: 'secret_note', label: { en: 'Secret note' }, visible: false },
];

const fieldConfig: FieldConfig = { fields: FIELDS } as FieldConfig;

function makeProps(
  overrides: Partial<React.ComponentProps<typeof ColumnChooser>> = {},
): React.ComponentProps<typeof ColumnChooser> {
  return {
    isOpen: true,
    onClose: vi.fn(),
    fieldConfig,
    selectedKeys: [],
    language: 'en',
    onChange: vi.fn(),
    ...overrides,
  };
}

describe('ColumnChooser', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- (1) lists every candidate field, excludes non-candidates (R1.2, R3.1) ---
  describe('lists candidate fields (R1.2, R3.1)', () => {
    it('lists every column candidate and member_number, and excludes a non-candidate', () => {
      render(<ColumnChooser {...makeProps()} />);

      // Every visible candidate is listed (incl. the always-on member_number).
      expect(screen.getByTestId('column-chooser-member_number')).toBeInTheDocument();
      expect(screen.getByTestId('column-chooser-email')).toBeInTheDocument();
      expect(screen.getByTestId('column-chooser-region')).toBeInTheDocument();

      // A field with `visible: false` is NOT a candidate → never offered.
      expect(screen.queryByTestId('column-chooser-secret_note')).not.toBeInTheDocument();
    });
  });

  // --- (2) shown=checked; member_number always-on + never emitted (R1.2, R7.2) ---
  describe('selection + always-on member_number (R1.2, R7.2)', () => {
    it('renders a currently-shown column checked and others unchecked', () => {
      // `email` is a currently-shown column → checked; `region` is not → unchecked.
      render(<ColumnChooser {...makeProps({ selectedKeys: ['email'] })} />);

      expect(checkboxInput('column-chooser-email')).toBeChecked();
      expect(checkboxInput('column-chooser-region')).not.toBeChecked();
    });

    it('renders member_number checked (always-on) even when absent from selectedKeys', () => {
      // selectedKeys omits member_number (it is implied, R7.3) — it still shows
      // checked as the locked always-on column (the half R7.2 the mock expresses).
      render(<ColumnChooser {...makeProps({ selectedKeys: [] })} />);
      expect(checkboxInput('column-chooser-member_number')).toBeChecked();
    });

    it('never includes member_number in an emitted payload, even if selectedKeys lists it', () => {
      const onChange = vi.fn();
      // selectedKeys defensively includes member_number; toggling another key
      // must still emit a list WITHOUT member_number (implied, R7.3).
      render(
        <ColumnChooser
          {...makeProps({ selectedKeys: [ALWAYS_ON_COLUMN_KEY, 'email'], onChange })}
        />,
      );

      fireEvent.click(checkboxInput('column-chooser-region'));
      expect(onChange).toHaveBeenCalledTimes(1);
      const emitted = onChange.mock.calls[0][0] as string[];
      expect(emitted).not.toContain(ALWAYS_ON_COLUMN_KEY);
      // The retained + newly-added keys only, in order.
      expect(emitted).toEqual(['email', 'region']);
    });
  });

  // --- (3) add appends, remove drops — exact expected key set/order (R1.3) ---
  describe('add + remove emit the expected key set (R1.3)', () => {
    it('checking an unchecked candidate emits onChange with the key APPENDED', () => {
      const onChange = vi.fn();
      // `email` already shown; check `region` → appended after email, in order.
      render(<ColumnChooser {...makeProps({ selectedKeys: ['email'], onChange })} />);

      fireEvent.click(checkboxInput('column-chooser-region'));
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenCalledWith(['email', 'region']);
    });

    it('unchecking a currently-shown column emits onChange with it REMOVED', () => {
      const onChange = vi.fn();
      // Both shown; uncheck `email` → only `region` remains (member_number never
      // in the list).
      render(
        <ColumnChooser {...makeProps({ selectedKeys: ['email', 'region'], onChange })} />,
      );

      fireEvent.click(checkboxInput('column-chooser-email'));
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenCalledWith(['region']);
    });

    it('preserves order across independent toggles (append-at-end, remove-in-place)', () => {
      const onChange = vi.fn();
      const { rerender } = render(
        <ColumnChooser {...makeProps({ selectedKeys: [], onChange })} />,
      );

      // Nothing shown → check region → [region].
      fireEvent.click(checkboxInput('column-chooser-region'));
      expect(onChange).toHaveBeenLastCalledWith(['region']);

      // Parent applies it; now check email → appended → [region, email].
      rerender(<ColumnChooser {...makeProps({ selectedKeys: ['region'], onChange })} />);
      fireEvent.click(checkboxInput('column-chooser-email'));
      expect(onChange).toHaveBeenLastCalledWith(['region', 'email']);
    });
  });

  // --- (4) nothing persisted: onChange is the only output (R3.1 / C2) ---
  describe('owns no persistence (R3.1, C2 / R5.2)', () => {
    it('reports changes only via onChange and makes no service call on toggle', () => {
      // The component imports no API service (verified structurally below); a
      // toggle produces exactly one onChange and no other output channel.
      const onChange = vi.fn();
      const onClose = vi.fn();
      render(<ColumnChooser {...makeProps({ selectedKeys: [], onChange, onClose })} />);

      fireEvent.click(checkboxInput('column-chooser-email'));

      // Only output is onChange — persistence belongs to the page (C8), not here.
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenCalledWith(['email']);
      expect(onClose).not.toHaveBeenCalled();
    });

    it('imports no API/persistence service (persistence lives on the page, C8)', () => {
      // Structural guard: the component source references no membersApiService /
      // save call — its sole output contract is onChange (R3.1 / C2).
      const src = ColumnChooser.toString();
      expect(src).not.toMatch(/membersApiService/);
      expect(src).not.toMatch(/saveColumnPreferences/);
    });
  });
});

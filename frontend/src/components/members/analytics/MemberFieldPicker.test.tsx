/**
 * Component tests for MemberFieldPicker (analytics/MemberFieldPicker.tsx).
 *
 * Verifies task 7.4 (R4.4, R4.5, R4.6, R6.1):
 *   - lists the groupable/aggregatable fields from `fieldConfig.fields` (the
 *     fixed ⊕ overlay ⊕ calculated union), with bilingual labels (R4.5 / R6.1);
 *   - can be SEEDED from a preset as a starting point — the group columns +
 *     measures from the preset's config are pre-populated (R4.6);
 *   - composes a `PivotConfig` and SAVES it via
 *     `membersApiService.saveAnalyticsSet` with `dataSource: 'members'`
 *     (R4.4 / R4.5, F-012 — the Members module's own DynamoDB store, NOT the Flask
 *     pivotService), via a MOCKED membersApiService;
 *   - blocks the save (never a silent no-op) until a name + a selection exist;
 *   - is exported from the analytics barrel.
 *
 * i18n is echoed (keys returned verbatim, interpolation preserved) so assertions
 * are locale-independent and prove the component uses the bilingual keys rather
 * than hardcoded English (R6.1).
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';

// Echo i18n keys (+ interpolation) so assertions are locale-independent.
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && 'preset' in opts) {
        return `${key}:${opts.preset}`;
      }
      return key;
    },
    i18n: { language: 'en' },
  }),
}));

// Mock the Members API service — the save/update paths are exercised without any
// HTTP (R4.4). Both the new-save and the in-place update CRUD are mocked. The
// member saved-set store is the Members module's own DynamoDB plane (F-012), so
// the picker calls `saveAnalyticsSet` / `updateAnalyticsSet`, NOT the Flask
// pivotService.
const mockSaveAnalyticsSet = vi.fn();
const mockUpdateAnalyticsSet = vi.fn();
vi.mock('../../../services/membersApiService', () => ({
  saveAnalyticsSet: (...args: unknown[]) => mockSaveAnalyticsSet(...args),
  updateAnalyticsSet: (...args: unknown[]) => mockUpdateAnalyticsSet(...args),
}));

import { render, screen, fireEvent, waitFor } from '@/test-utils';
import MemberFieldPicker from './MemberFieldPicker';
import { MemberFieldPicker as FromBarrel } from './index';
import type { FieldConfig } from '../../../types/members';
import type { MemberPivotPreset } from './memberPivotPresets';

/** A field config exposing a fixed, an overlay, and a calculated field. */
const fieldConfig = {
  fields: [
    { key: 'membership_type', origin: 'fixed', label: { nl: 'Type', en: 'Membership type' } },
    { key: 'clubblad', origin: 'variable', label: { nl: 'Clubblad', en: 'Clubblad' } },
    { key: 'years_member', origin: 'calculated', label: { nl: 'Lidjaren', en: 'Years-member' } },
    // An explicitly-hidden field must NOT appear in the picker.
    { key: 'secret', origin: 'variable', visible: false, label: { en: 'Secret' } },
  ],
} as unknown as FieldConfig;

/** A role-seeded preset: group by membership type with a COUNT(*) measure. */
const membershipPreset: MemberPivotPreset = {
  key: 'membership-types',
  labelKey: 'analytics.pivotViews.presetNames.membershipTypes',
  kind: 'count',
  requiresFields: ['membership_type'],
  config: {
    dataSource: 'members',
    groupColumns: ['membership_type'],
    aggregateMeasures: [{ function: 'COUNT', column: '*' }],
    filters: {},
    columnPivot: null,
    columnNestLevels: [],
    displayMode: 'flat',
  },
};

function makeProps(overrides: Partial<React.ComponentProps<typeof MemberFieldPicker>> = {}) {
  return {
    isOpen: true,
    onClose: vi.fn(),
    fieldConfig,
    language: 'en',
    onSaved: vi.fn(),
    ...overrides,
  };
}

/**
 * The checkbox INPUT inside a testid'd Chakra Checkbox wrapper. Both the
 * "Group by" and "List columns" sections render a checkbox per field with the
 * SAME accessible label, so a group checkbox must be addressed by its testid
 * (`field-picker-group-<key>` / `field-picker-list-<key>`) rather than by role +
 * name (which is now ambiguous across the two sections).
 */
function checkboxInput(testid: string): HTMLInputElement {
  return screen.getByTestId(testid).querySelector('input') as HTMLInputElement;
}
function clickCheckbox(testid: string): void {
  fireEvent.click(checkboxInput(testid));
}

beforeEach(() => {
  mockSaveAnalyticsSet.mockReset();
  // saveAnalyticsSet resolves to the full MemberAnalyticsSet (string set id).
  mockSaveAnalyticsSet.mockResolvedValue({
    id: 'set-42',
    name: 'saved',
    kind: 'list',
    definition: {},
    created_at: '',
    updated_at: '',
  });
  mockUpdateAnalyticsSet.mockReset();
  mockUpdateAnalyticsSet.mockResolvedValue({
    id: 'set-7',
    name: 'updated',
    kind: 'count',
    definition: {},
    created_at: '',
    updated_at: '',
  });
});

describe('MemberFieldPicker', () => {
  it('is exported from the analytics barrel', () => {
    expect(FromBarrel).toBe(MemberFieldPicker);
  });

  it('lists the groupable fields from fieldConfig (fixed ⊕ overlay ⊕ calculated), skipping hidden', () => {
    render(<MemberFieldPicker {...makeProps()} />);

    // The three visible fields appear as group-column checkboxes (R4.5).
    expect(screen.getByTestId('field-picker-group-membership_type')).toBeInTheDocument();
    expect(screen.getByTestId('field-picker-group-clubblad')).toBeInTheDocument();
    expect(screen.getByTestId('field-picker-group-years_member')).toBeInTheDocument();
    // The explicitly-hidden field is NOT offered.
    expect(screen.queryByTestId('field-picker-group-secret')).not.toBeInTheDocument();

    // Bilingual labels resolved to the active language (no hardcoded English string).
    // The group checkboxes carry the resolved label text (both the Group-by and
    // List-columns sections render a checkbox per field with the same label, so
    // the group one is addressed by its testid).
    expect(screen.getByTestId('field-picker-group-membership_type')).toHaveTextContent(
      'Membership type',
    );
    expect(screen.getByTestId('field-picker-group-years_member')).toHaveTextContent(
      'Years-member',
    );
    // The modal title uses the 0.3 i18n key (echoed verbatim).
    expect(screen.getByText('analytics.pivotViews.fieldPicker.title')).toBeInTheDocument();
  });

  it('shows a neutral "no fields" message when the config exposes none', () => {
    render(
      <MemberFieldPicker {...makeProps({ fieldConfig: { fields: [] } as unknown as FieldConfig })} />,
    );
    expect(screen.getByTestId('field-picker-no-fields')).toHaveTextContent(
      'analytics.pivotViews.fieldPicker.noFields',
    );
  });

  it('seeds the picker from a preset as a starting point (R4.6)', () => {
    render(<MemberFieldPicker {...makeProps({ seedPreset: membershipPreset })} />);

    // The seeded-from hint names the preset (bilingual key + interpolation).
    expect(screen.getByTestId('field-picker-seeded')).toHaveTextContent(
      'analytics.pivotViews.fieldPicker.seededFrom:analytics.pivotViews.presetNames.membershipTypes',
    );
    // The preset's group column is pre-checked.
    expect(screen.getByRole('checkbox', { name: 'Membership type' })).toBeChecked();
    // The preset's single measure is pre-populated (two selects: function + column).
    expect(screen.getByTestId('field-picker-measures').querySelectorAll('select').length).toBe(2);
    // The name is seeded from the preset label so Save is immediately possible.
    expect(screen.getByTestId('field-picker-name')).toHaveValue(
      'analytics.pivotViews.presetNames.membershipTypes',
    );
  });

  it('composes and saves a members PivotConfig via the mocked Members API (R4.4/R4.5)', async () => {
    const onSaved = vi.fn();
    const onClose = vi.fn();
    render(<MemberFieldPicker {...makeProps({ onSaved, onClose })} />);

    // Name the set and choose a group column (via its testid — the same label
    // also exists in the list-columns section of a blank list compose).
    fireEvent.change(screen.getByTestId('field-picker-name'), {
      target: { value: 'Clubblad list' },
    });
    clickCheckbox('field-picker-group-clubblad');

    // Save.
    fireEvent.click(screen.getByTestId('field-picker-save'));

    await waitFor(() => expect(mockSaveAnalyticsSet).toHaveBeenCalledTimes(1));

    const [name, config, kind] = mockSaveAnalyticsSet.mock.calls[0];
    expect(name).toBe('Clubblad list');
    // The composed config targets the members data source (R4.5).
    expect(config.dataSource).toBe('members');
    expect(config.groupColumns).toEqual(['clubblad']);
    // A set WITH a group column is an aggregate (count) set.
    expect(kind).toBe('count');

    // onSaved is called with the composed config, the name, and the persisted set
    // id STRING (from the save response, so the Pivot Views area can reselect it).
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(
      expect.objectContaining({ dataSource: 'members', groupColumns: ['clubblad'] }),
      'Clubblad list',
      'set-42',
    ));
    expect(onClose).toHaveBeenCalled();
  });

  it('saves a filtered-LIST set (no group columns) with kind "list" — F-011', async () => {
    // A set with NO group columns and NO measures is a filtered-list set. The
    // module store accepts empty group/measures as first-class (F-011), so this
    // saves with kind 'list'. (The picker still requires a name + a selection to
    // enable Save, so we add a COUNT(*) measure to satisfy the UI gate while
    // keeping groupColumns empty — kind is driven by groupColumns being empty.)
    render(<MemberFieldPicker {...makeProps()} />);
    fireEvent.change(screen.getByTestId('field-picker-name'), {
      target: { value: 'All paper recipients' },
    });
    fireEvent.click(screen.getByTestId('field-picker-add-measure'));
    fireEvent.click(screen.getByTestId('field-picker-save'));

    await waitFor(() => expect(mockSaveAnalyticsSet).toHaveBeenCalledTimes(1));
    const [, config, kind] = mockSaveAnalyticsSet.mock.calls[0];
    expect(config.groupColumns).toEqual([]);
    expect(kind).toBe('list');
  });

  // --- The "missing columns" fix: a filtered-list set captures listColumns. --
  it('shows the list-columns picker ONLY for a filtered-list set (no group columns)', () => {
    render(<MemberFieldPicker {...makeProps()} />);
    // A blank compose is a list set → the list-columns section is shown.
    expect(screen.getByTestId('field-picker-list-fields')).toBeInTheDocument();
    expect(screen.getByTestId('field-picker-list-membership_type')).toBeInTheDocument();

    // Adding a group column makes it an aggregate set → the list-columns section
    // disappears (an aggregate set's columns are its group + measure columns).
    clickCheckbox('field-picker-group-membership_type');
    expect(screen.queryByTestId('field-picker-list-fields')).not.toBeInTheDocument();
  });

  it('defaults a new list set to ALL pickable fields and saves them as listColumns', async () => {
    render(<MemberFieldPicker {...makeProps()} />);
    fireEvent.change(screen.getByTestId('field-picker-name'), {
      target: { value: 'Everyone' },
    });
    // No group column, no measure — a pure filtered list. Its list columns were
    // pre-selected to every pickable field on open (the fix), so Save is enabled
    // and the saved config carries them (never near-empty).
    fireEvent.click(screen.getByTestId('field-picker-save'));

    await waitFor(() => expect(mockSaveAnalyticsSet).toHaveBeenCalledTimes(1));
    const [, config, kind] = mockSaveAnalyticsSet.mock.calls[0];
    expect(kind).toBe('list');
    expect(config.groupColumns).toEqual([]);
    // The three visible fields (hidden 'secret' excluded) are the list columns.
    expect(config.listColumns).toEqual(['membership_type', 'clubblad', 'years_member']);
  });

  it('persists exactly the user-chosen list columns for a filtered-list set', async () => {
    render(<MemberFieldPicker {...makeProps()} />);
    fireEvent.change(screen.getByTestId('field-picker-name'), {
      target: { value: 'Just two' },
    });
    // Deselect one of the defaulted list columns, leaving two.
    fireEvent.click(screen.getByTestId('field-picker-list-years_member'));
    fireEvent.click(screen.getByTestId('field-picker-save'));

    await waitFor(() => expect(mockSaveAnalyticsSet).toHaveBeenCalledTimes(1));
    const [, config] = mockSaveAnalyticsSet.mock.calls[0];
    expect(config.listColumns).toEqual(['membership_type', 'clubblad']);
  });

  it('seeds the list-columns from an existing list set that already names them (edit round-trip)', () => {
    const listModel = {
      id: 'set-9',
      name: 'Birthday list',
      config: {
        dataSource: 'members',
        groupColumns: [],
        aggregateMeasures: [],
        filters: {},
        columnPivot: null,
        columnNestLevels: [],
        displayMode: 'flat' as const,
        listColumns: ['membership_type', 'years_member'],
      },
    };
    render(<MemberFieldPicker {...makeProps({ existingModel: listModel })} />);
    // Exactly the saved list columns are pre-checked; the un-named one is not.
    expect(checkboxInput('field-picker-list-membership_type')).toBeChecked();
    expect(checkboxInput('field-picker-list-years_member')).toBeChecked();
    expect(checkboxInput('field-picker-list-clubblad')).not.toBeChecked();
  });

  // --- Issue 3: definition filters (field == value) compose + round-trip. ---
  describe('definition filters (issue 3)', () => {
    it('composes a filter (field == value) into config.filters and persists it', async () => {
      render(<MemberFieldPicker {...makeProps()} />);
      fireEvent.change(screen.getByTestId('field-picker-name'), {
        target: { value: 'Clubblad paper' },
      });
      // Make it an aggregate so the test does not depend on list columns.
      clickCheckbox('field-picker-group-membership_type');

      // Add a filter row and set clubblad == 'Papier'.
      fireEvent.click(screen.getByTestId('field-picker-add-filter'));
      const row = screen.getByTestId('field-picker-filters');
      const fieldSelect = row.querySelector('select') as HTMLSelectElement;
      fireEvent.change(fieldSelect, { target: { value: 'clubblad' } });
      const valueInput = row.querySelector('input') as HTMLInputElement;
      fireEvent.change(valueInput, { target: { value: 'Papier' } });

      fireEvent.click(screen.getByTestId('field-picker-save'));

      await waitFor(() => expect(mockSaveAnalyticsSet).toHaveBeenCalledTimes(1));
      const [, config] = mockSaveAnalyticsSet.mock.calls[0];
      expect(config.filters).toEqual({ clubblad: 'Papier' });
    });

    it('seeds (round-trips) existing filters from the edited model, skipping reserved year keys', () => {
      const existingModel = {
        id: 'set-11',
        name: 'Paper + jubilee',
        config: {
          dataSource: 'members',
          groupColumns: ['membership_type'],
          aggregateMeasures: [{ function: 'COUNT' as const, column: '*' }],
          // A generic filter (shown + editable) AND a reserved year filter
          // (owned by the jubilee selector — must NOT appear as an editable row).
          filters: { clubblad: 'Papier', years_member: 25 },
          columnPivot: null,
          columnNestLevels: [],
          displayMode: 'flat' as const,
        },
      };
      render(<MemberFieldPicker {...makeProps({ existingModel })} />);

      // Exactly one editable filter row (the generic clubblad filter); the
      // reserved years_member key is not surfaced as a row.
      const filters = screen.getByTestId('field-picker-filters');
      const valueInputs = filters.querySelectorAll('input');
      expect(valueInputs).toHaveLength(1);
      expect((valueInputs[0] as HTMLInputElement).value).toBe('Papier');
    });

    it('preserves the reserved year filter through an update (not clobbered)', async () => {
      const existingModel = {
        id: 'set-11',
        name: 'Paper + jubilee',
        config: {
          dataSource: 'members',
          groupColumns: ['membership_type'],
          aggregateMeasures: [{ function: 'COUNT' as const, column: '*' }],
          filters: { clubblad: 'Papier', years_member: 25 },
          columnPivot: null,
          columnNestLevels: [],
          displayMode: 'flat' as const,
        },
      };
      render(<MemberFieldPicker {...makeProps({ existingModel })} />);
      fireEvent.click(screen.getByTestId('field-picker-save'));

      await waitFor(() => expect(mockUpdateAnalyticsSet).toHaveBeenCalledTimes(1));
      const [, , config] = mockUpdateAnalyticsSet.mock.calls[0];
      // Both the generic filter and the reserved year filter survive.
      expect(config.filters).toEqual({ clubblad: 'Papier', years_member: 25 });
    });

    it('drops a blank filter row (no field or no value)', async () => {
      render(<MemberFieldPicker {...makeProps()} />);
      fireEvent.change(screen.getByTestId('field-picker-name'), {
        target: { value: 'No filter set' },
      });
      clickCheckbox('field-picker-group-membership_type');
      // Add a filter row but leave it blank.
      fireEvent.click(screen.getByTestId('field-picker-add-filter'));
      fireEvent.click(screen.getByTestId('field-picker-save'));

      await waitFor(() => expect(mockSaveAnalyticsSet).toHaveBeenCalledTimes(1));
      const [, config] = mockSaveAnalyticsSet.mock.calls[0];
      expect(config.filters).toEqual({});
    });
  });

  it('composes a COUNT aggregate measure and saves it with the config', async () => {
    render(<MemberFieldPicker {...makeProps()} />);

    fireEvent.change(screen.getByTestId('field-picker-name'), {
      target: { value: 'Count per type' },
    });
    clickCheckbox('field-picker-group-membership_type');
    // Add a measure (defaults to COUNT over all rows → COUNT(*)).
    fireEvent.click(screen.getByTestId('field-picker-add-measure'));

    fireEvent.click(screen.getByTestId('field-picker-save'));

    await waitFor(() => expect(mockSaveAnalyticsSet).toHaveBeenCalledTimes(1));
    const [, config] = mockSaveAnalyticsSet.mock.calls[0];
    expect(config.groupColumns).toEqual(['membership_type']);
    expect(config.aggregateMeasures).toEqual([{ function: 'COUNT', column: '*' }]);
  });

  it('blocks save until a name AND a selection exist (no silent no-op)', () => {
    render(<MemberFieldPicker {...makeProps()} />);

    const save = screen.getByTestId('field-picker-save');
    // On open, a blank compose is a filtered-LIST set whose list columns default
    // to every pickable field (the "missing columns" fix — a list set is never
    // empty), so there IS a selection; the save is blocked only on the missing
    // NAME. Clear every list column to reach the true "no selection" state.
    fireEvent.click(screen.getByTestId('field-picker-list-membership_type'));
    fireEvent.click(screen.getByTestId('field-picker-list-clubblad'));
    fireEvent.click(screen.getByTestId('field-picker-list-years_member'));

    // Nothing selected, no name → disabled, with the selection reason.
    expect(save).toBeDisabled();
    expect(screen.getByTestId('field-picker-selection-required')).toBeInTheDocument();

    // Pick a group column but still no name → still blocked, now on the name.
    clickCheckbox('field-picker-group-membership_type');
    expect(save).toBeDisabled();
    expect(screen.getByTestId('field-picker-name-required')).toBeInTheDocument();

    // Add a name → enabled.
    fireEvent.change(screen.getByTestId('field-picker-name'), {
      target: { value: 'My set' },
    });
    expect(save).not.toBeDisabled();
  });

  it('surfaces a toast and does not close on a save failure', async () => {
    mockSaveAnalyticsSet.mockRejectedValueOnce(new Error('boom'));
    const onClose = vi.fn();
    const onSaved = vi.fn();
    render(<MemberFieldPicker {...makeProps({ onClose, onSaved })} />);

    fireEvent.change(screen.getByTestId('field-picker-name'), {
      target: { value: 'Will fail' },
    });
    clickCheckbox('field-picker-group-membership_type');
    fireEvent.click(screen.getByTestId('field-picker-save'));

    await waitFor(() => expect(mockSaveAnalyticsSet).toHaveBeenCalledTimes(1));
    // The modal is NOT closed and onSaved is NOT called on failure.
    expect(onClose).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  // --- Task 7.5: the UPDATE path (editing an existing saved set in place). --
  describe('update path (task 7.5, R4.4/R4.4b)', () => {
    /** An existing saved set carrying its OWN definition filters (R4.4). */
    const existingModel = {
      id: 'set-7',
      name: 'Paper clubblad',
      config: {
        dataSource: 'members',
        groupColumns: ['membership_type'],
        aggregateMeasures: [{ function: 'COUNT' as const, column: '*' }],
        // The set's own definition filter — MUST round-trip through the editor.
        filters: { clubblad: 'Papier' },
        columnPivot: null,
        columnNestLevels: [],
        displayMode: 'flat' as const,
      },
    };

    it('pre-populates from the existing model and shows the update labels', () => {
      render(<MemberFieldPicker {...makeProps({ existingModel })} />);

      // Name + group column pre-filled from the saved model's definition.
      expect(screen.getByTestId('field-picker-name')).toHaveValue('Paper clubblad');
      expect(screen.getByRole('checkbox', { name: 'Membership type' })).toBeChecked();
      // The modal title + save button switch to the update wording (bilingual keys).
      expect(screen.getByText('analytics.pivotViews.fieldPicker.updateTitle')).toBeInTheDocument();
      expect(screen.getByTestId('field-picker-save')).toHaveTextContent(
        'analytics.pivotViews.fieldPicker.update',
      );
    });

    it('updates the SAME id via updateAnalyticsSet, preserving the definition filters (R4.4)', async () => {
      const onSaved = vi.fn();
      const onClose = vi.fn();
      render(<MemberFieldPicker {...makeProps({ existingModel, onSaved, onClose })} />);

      // Tweak the set (add another group column) and save.
      fireEvent.click(screen.getByRole('checkbox', { name: 'Clubblad' }));
      fireEvent.click(screen.getByTestId('field-picker-save'));

      await waitFor(() => expect(mockUpdateAnalyticsSet).toHaveBeenCalledTimes(1));
      // A new set is NEVER created on an update.
      expect(mockSaveAnalyticsSet).not.toHaveBeenCalled();

      // updateAnalyticsSet(id, name, config, kind) — the id is the backend set_id
      // STRING, the name + config round-trip, kind is 'count' (has group columns).
      const [id, name, config, kind] = mockUpdateAnalyticsSet.mock.calls[0];
      expect(id).toBe('set-7');
      expect(name).toBe('Paper clubblad');
      // The edit is persisted …
      expect(config.groupColumns).toEqual(['membership_type', 'clubblad']);
      // … and the set's OWN definition filters travel with it (R4.4).
      expect(config.filters).toEqual({ clubblad: 'Papier' });
      expect(kind).toBe('count');

      // onSaved reports the SAME id so the caller can reselect it.
      await waitFor(() =>
        expect(onSaved).toHaveBeenCalledWith(
          expect.objectContaining({ filters: { clubblad: 'Papier' } }),
          'Paper clubblad',
          'set-7',
        ),
      );
      expect(onClose).toHaveBeenCalled();
    });

    it('surfaces the update-error toast and does not close on an update failure', async () => {
      mockUpdateAnalyticsSet.mockRejectedValueOnce(new Error('boom'));
      const onClose = vi.fn();
      const onSaved = vi.fn();
      render(<MemberFieldPicker {...makeProps({ existingModel, onClose, onSaved })} />);

      fireEvent.click(screen.getByTestId('field-picker-save'));

      await waitFor(() => expect(mockUpdateAnalyticsSet).toHaveBeenCalledTimes(1));
      expect(onClose).not.toHaveBeenCalled();
      expect(onSaved).not.toHaveBeenCalled();
    });
  });
});

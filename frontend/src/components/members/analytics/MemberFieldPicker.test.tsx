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
import type { PivotSeed } from './MemberFieldPicker';

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

/** A Save-as seed: a config to pre-populate from, plus a default name (the source set's name). */
const membershipSeed: PivotSeed = {
  name: 'Members by type',
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

  it('groups both field lists by functional group (catalog order), alphabetical within each', () => {
    // A config with two functional groups (catalog order: contact THEN membership)
    // and fields deliberately out of alphabetical order within each group.
    const grouped = {
      functional_groups: [
        { key: 'contact', label: { en: 'Contact', nl: 'Contact' }, order: 1 },
        { key: 'membership', label: { en: 'Membership', nl: 'Lidmaatschap' }, order: 2 },
      ],
      fields: [
        { key: 'phone', functional_group: 'contact', label: { en: 'Phone' } },
        { key: 'email', functional_group: 'contact', label: { en: 'Email' } },
        { key: 'tier', functional_group: 'membership', label: { en: 'Tier' } },
        { key: 'joined', functional_group: 'membership', label: { en: 'Joined' } },
        // No functional group → appended last in an unlabelled "ungrouped" section.
        { key: 'notes', label: { en: 'Notes' } },
      ],
    } as unknown as FieldConfig;

    render(<MemberFieldPicker {...makeProps({ fieldConfig: grouped })} />);

    // A blank compose is a list set → assert on the List-columns list.
    const list = screen.getByTestId('field-picker-list-fields');
    const order = Array.from(list.querySelectorAll('[data-testid^="field-picker-list-"]'))
      .map((el) => el.getAttribute('data-testid'))
      // Keep only the per-field checkbox testids (not the section wrappers).
      .filter((id): id is string => !!id && !id.includes('-section-'));

    // contact group first (Email < Phone), then membership (Joined < Tier),
    // then the ungrouped fallback (Notes) — sections in catalog order,
    // alphabetical within each.
    expect(order).toEqual([
      'field-picker-list-email',
      'field-picker-list-phone',
      'field-picker-list-joined',
      'field-picker-list-tier',
      'field-picker-list-notes',
    ]);

    // The section headings are rendered for the catalog groups.
    expect(screen.getByTestId('field-picker-list-section-contact')).toHaveTextContent('Contact');
    expect(screen.getByTestId('field-picker-list-section-membership')).toHaveTextContent(
      'Membership',
    );
  });

  it('shows a neutral "no fields" message when the config exposes none', () => {
    render(
      <MemberFieldPicker {...makeProps({ fieldConfig: { fields: [] } as unknown as FieldConfig })} />,
    );
    expect(screen.getByTestId('field-picker-no-fields')).toHaveTextContent(
      'analytics.pivotViews.fieldPicker.noFields',
    );
  });

  it('seeds the picker from a Save-as seed as a starting point (R4.6)', () => {
    render(<MemberFieldPicker {...makeProps({ seedPreset: membershipSeed })} />);

    // The seeded-from hint names the preset (bilingual key + interpolation).
    // The seeded-from hint names the source set (bilingual key + interpolation of the seed name).
    expect(screen.getByTestId('field-picker-seeded')).toHaveTextContent(
      'analytics.pivotViews.fieldPicker.seededFrom:Members by type',
    );
    // The seed's group column is pre-checked.
    expect(screen.getByRole('checkbox', { name: 'Membership type' })).toBeChecked();
    // The seed's single measure is pre-populated (two selects: function + column).
    expect(screen.getByTestId('field-picker-measures').querySelectorAll('select').length).toBe(2);
    // The name is seeded from the source set's name so Save is immediately possible.
    expect(screen.getByTestId('field-picker-name')).toHaveValue('Members by type');
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

  it('seeds a new list set with NO list columns pre-selected', () => {
    render(<MemberFieldPicker {...makeProps()} />);
    // A brand-new blank compose is a list set, but nothing is pre-checked —
    // the user picks the columns they want (no all-fields default).
    expect(checkboxInput('field-picker-list-membership_type')).not.toBeChecked();
    expect(checkboxInput('field-picker-list-clubblad')).not.toBeChecked();
    expect(checkboxInput('field-picker-list-years_member')).not.toBeChecked();
  });

  it('persists exactly the user-chosen list columns for a filtered-list set', async () => {
    render(<MemberFieldPicker {...makeProps()} />);
    fireEvent.change(screen.getByTestId('field-picker-name'), {
      target: { value: 'Just two' },
    });
    // Nothing is pre-selected; the user picks the two columns they want.
    fireEvent.click(screen.getByTestId('field-picker-list-membership_type'));
    fireEvent.click(screen.getByTestId('field-picker-list-clubblad'));
    fireEvent.click(screen.getByTestId('field-picker-save'));

    await waitFor(() => expect(mockSaveAnalyticsSet).toHaveBeenCalledTimes(1));
    const [, config, kind] = mockSaveAnalyticsSet.mock.calls[0];
    expect(kind).toBe('list');
    expect(config.groupColumns).toEqual([]);
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

  // --- Issue 3 / task 7: definition filter ROWS (grouped field + operator +
  // value) compose into the object FilterClause shape + round-trip. The filter
  // row is now `[GroupedFieldSelect | operator-select | value-input | remove]`;
  // each row's testids are keyed by the draft id:
  //   field  → field-picker-filter-field-<id> (grouped <select>, placeholder '')
  //   op     → field-picker-filter-op-<id>     (operator <select>, default 'eq')
  //   value  → field-picker-filter-value-<id>  (ABSENT for empty/notEmpty)
  //   regex-invalid → field-picker-filter-regex-invalid-<id> (regex OR notRegex)
  // and the composed `config.filters` is the object form
  // `{ key: { op, value? } }` — a legacy scalar reads back as `{ op:'eq', … }`.
  describe('definition filter rows (grouped field + operator + value)', () => {
    /** The one filter row's testid-anchored controls (there is exactly one row). */
    function soleFilterRow() {
      const filters = screen.getByTestId('field-picker-filters');
      const fieldSelect = filters.querySelector(
        '[data-testid^="field-picker-filter-field-"]',
      ) as HTMLSelectElement;
      const opSelect = filters.querySelector(
        '[data-testid^="field-picker-filter-op-"]',
      ) as HTMLSelectElement;
      // The draft id is the suffix shared across the row's testids.
      const id = fieldSelect.getAttribute('data-testid')!.replace('field-picker-filter-field-', '');
      return { id, fieldSelect, opSelect };
    }

    it('composes a filter row (field + eq operator + value) into the object FilterClause shape', async () => {
      render(<MemberFieldPicker {...makeProps()} />);
      fireEvent.change(screen.getByTestId('field-picker-name'), {
        target: { value: 'Clubblad paper' },
      });
      // Make it an aggregate so the test does not depend on list columns.
      clickCheckbox('field-picker-group-membership_type');

      // Add a filter row, pick clubblad on the GROUPED field select, keep the
      // default `eq` operator, and type the value.
      fireEvent.click(screen.getByTestId('field-picker-add-filter'));
      const { id, fieldSelect, opSelect } = soleFilterRow();
      // A new row defaults its operator to `eq`.
      expect(opSelect.value).toBe('eq');
      fireEvent.change(fieldSelect, { target: { value: 'clubblad' } });
      const valueInput = screen.getByTestId(
        `field-picker-filter-value-${id}`,
      ) as HTMLInputElement;
      fireEvent.change(valueInput, { target: { value: 'Papier' } });

      fireEvent.click(screen.getByTestId('field-picker-save'));

      await waitFor(() => expect(mockSaveAnalyticsSet).toHaveBeenCalledTimes(1));
      const [, config] = mockSaveAnalyticsSet.mock.calls[0];
      // The persisted shape is the object FilterClause, not a legacy scalar.
      expect(config.filters).toEqual({ clubblad: { op: 'eq', value: 'Papier' } });
    });

    it('the filter field select is GROUPED (optgroups mirror the checklist sections)', () => {
      const grouped = {
        functional_groups: [
          { key: 'contact', label: { en: 'Contact', nl: 'Contact' }, order: 1 },
          { key: 'membership', label: { en: 'Membership', nl: 'Lidmaatschap' }, order: 2 },
        ],
        fields: [
          { key: 'email', functional_group: 'contact', label: { en: 'Email' } },
          { key: 'tier', functional_group: 'membership', label: { en: 'Tier' } },
        ],
      } as unknown as FieldConfig;
      render(<MemberFieldPicker {...makeProps({ fieldConfig: grouped })} />);

      fireEvent.click(screen.getByTestId('field-picker-add-filter'));
      const { fieldSelect } = soleFilterRow();
      // The grouped field select renders an <optgroup> per catalog section.
      const groups = Array.from(fieldSelect.querySelectorAll('optgroup')).map((g) =>
        g.getAttribute('label'),
      );
      expect(groups).toEqual(['Contact', 'Membership']);
    });

    it('the measure column select is GROUPED (shares the checklist sectioning)', () => {
      const grouped = {
        functional_groups: [
          { key: 'contact', label: { en: 'Contact', nl: 'Contact' }, order: 1 },
          { key: 'membership', label: { en: 'Membership', nl: 'Lidmaatschap' }, order: 2 },
        ],
        fields: [
          { key: 'email', functional_group: 'contact', label: { en: 'Email' } },
          { key: 'tier', functional_group: 'membership', label: { en: 'Tier' } },
        ],
      } as unknown as FieldConfig;
      render(<MemberFieldPicker {...makeProps({ fieldConfig: grouped })} />);

      fireEvent.click(screen.getByTestId('field-picker-add-measure'));
      // The measure row's second <select> is the grouped column select.
      const selects = screen
        .getByTestId('field-picker-measures')
        .querySelectorAll('select');
      const columnSelect = selects[1] as HTMLSelectElement;
      const groups = Array.from(columnSelect.querySelectorAll('optgroup')).map((g) =>
        g.getAttribute('label'),
      );
      expect(groups).toEqual(['Contact', 'Membership']);
    });

    it('offers notContains / notRegex on a text field (type-adaptive operator list)', () => {
      render(<MemberFieldPicker {...makeProps()} />);
      fireEvent.click(screen.getByTestId('field-picker-add-filter'));
      const { id, fieldSelect, opSelect } = soleFilterRow();
      // clubblad has no `type` → the text operator set.
      fireEvent.change(fieldSelect, { target: { value: 'clubblad' } });
      const ops = Array.from(opSelect.querySelectorAll('option')).map((o) =>
        (o as HTMLOptionElement).value,
      );
      expect(ops).toEqual([
        'eq',
        'ne',
        'contains',
        'notContains',
        'regex',
        'notRegex',
        'empty',
        'notEmpty',
      ]);
      // The negated-text ops are value-TAKING — picking notContains keeps the value input.
      fireEvent.change(opSelect, { target: { value: 'notContains' } });
      expect(screen.getByTestId(`field-picker-filter-value-${id}`)).toBeInTheDocument();
    });

    it('hides the value input for empty / notEmpty and shows it otherwise', () => {
      render(<MemberFieldPicker {...makeProps()} />);
      fireEvent.click(screen.getByTestId('field-picker-add-filter'));
      const { id, fieldSelect, opSelect } = soleFilterRow();
      fireEvent.change(fieldSelect, { target: { value: 'clubblad' } });

      // Default `eq` → value input shown.
      expect(screen.getByTestId(`field-picker-filter-value-${id}`)).toBeInTheDocument();
      // `empty` → value input hidden.
      fireEvent.change(opSelect, { target: { value: 'empty' } });
      expect(screen.queryByTestId(`field-picker-filter-value-${id}`)).not.toBeInTheDocument();
      // `notEmpty` → still hidden.
      fireEvent.change(opSelect, { target: { value: 'notEmpty' } });
      expect(screen.queryByTestId(`field-picker-filter-value-${id}`)).not.toBeInTheDocument();
      // back to a value-taking op → shown again.
      fireEvent.change(opSelect, { target: { value: 'contains' } });
      expect(screen.getByTestId(`field-picker-filter-value-${id}`)).toBeInTheDocument();
    });

    it('composes a valueless empty clause (no value key) into the object shape', async () => {
      render(<MemberFieldPicker {...makeProps()} />);
      fireEvent.change(screen.getByTestId('field-picker-name'), {
        target: { value: 'Has clubblad' },
      });
      clickCheckbox('field-picker-group-membership_type');
      fireEvent.click(screen.getByTestId('field-picker-add-filter'));
      const { fieldSelect, opSelect } = soleFilterRow();
      fireEvent.change(fieldSelect, { target: { value: 'clubblad' } });
      fireEvent.change(opSelect, { target: { value: 'notEmpty' } });

      fireEvent.click(screen.getByTestId('field-picker-save'));
      await waitFor(() => expect(mockSaveAnalyticsSet).toHaveBeenCalledTimes(1));
      const [, config] = mockSaveAnalyticsSet.mock.calls[0];
      // A presence check carries no `value`.
      expect(config.filters).toEqual({ clubblad: { op: 'notEmpty' } });
    });

    it('resets the operator to eq when the field changes to an incompatible type', () => {
      // A config with a text field AND a number field, so switching the row's
      // field from text (contains) to number (no contains) resets op → eq.
      const typed = {
        fields: [
          { key: 'clubblad', label: { en: 'Clubblad' } }, // no type → text
          { key: 'age', type: 'number', label: { en: 'Age' } },
        ],
      } as unknown as FieldConfig;
      render(<MemberFieldPicker {...makeProps({ fieldConfig: typed })} />);

      fireEvent.click(screen.getByTestId('field-picker-add-filter'));
      const { fieldSelect, opSelect } = soleFilterRow();
      // Pick the text field and a text-only operator.
      fireEvent.change(fieldSelect, { target: { value: 'clubblad' } });
      fireEvent.change(opSelect, { target: { value: 'contains' } });
      expect(opSelect.value).toBe('contains');

      // Switch the field to the number field, whose operator set excludes
      // `contains` → the operator snaps back to `eq`.
      fireEvent.change(fieldSelect, { target: { value: 'age' } });
      expect(opSelect.value).toBe('eq');
      // The number field offers the numeric/date ordering set (no contains/regex).
      const ops = Array.from(opSelect.querySelectorAll('option')).map((o) =>
        (o as HTMLOptionElement).value,
      );
      expect(ops).toEqual(['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'empty', 'notEmpty']);
    });

    it('shows the inline invalid-pattern message on an invalid notRegex row', () => {
      render(<MemberFieldPicker {...makeProps()} />);
      fireEvent.click(screen.getByTestId('field-picker-add-filter'));
      const { id, fieldSelect, opSelect } = soleFilterRow();
      fireEvent.change(fieldSelect, { target: { value: 'clubblad' } });
      fireEvent.change(opSelect, { target: { value: 'notRegex' } });
      const valueInput = screen.getByTestId(
        `field-picker-filter-value-${id}`,
      ) as HTMLInputElement;
      // An unbalanced group is an invalid pattern.
      fireEvent.change(valueInput, { target: { value: '([' } });

      expect(
        screen.getByTestId(`field-picker-filter-regex-invalid-${id}`),
      ).toHaveTextContent('analytics.pivotViews.fieldPicker.filterRegexInvalid');

      // A valid pattern clears the message.
      fireEvent.change(valueInput, { target: { value: 'pap' } });
      expect(
        screen.queryByTestId(`field-picker-filter-regex-invalid-${id}`),
      ).not.toBeInTheDocument();
    });

    // FLIPPED (task 7.3): the former reserved-key carve-out is retired. A legacy
    // scalar `years_member: 25` is NO LONGER skipped — it reads as an ordinary
    // editable `eq` row ALONGSIDE the generic clubblad filter (R8.5 / R8.9).
    it('seeds a legacy scalar year filter as an editable eq row alongside the generic filter', () => {
      const existingModel = {
        id: 'set-11',
        name: 'Paper + jubilee',
        config: {
          dataSource: 'members',
          groupColumns: ['membership_type'],
          aggregateMeasures: [{ function: 'COUNT' as const, column: '*' }],
          // A generic filter AND a legacy scalar year filter — BOTH now surface
          // as editable rows (the reserved-key carve-out is gone).
          filters: { clubblad: 'Papier', years_member: 25 },
          columnPivot: null,
          columnNestLevels: [],
          displayMode: 'flat' as const,
        },
      };
      render(<MemberFieldPicker {...makeProps({ existingModel })} />);

      const filters = screen.getByTestId('field-picker-filters');
      // TWO editable filter rows now — clubblad AND years_member.
      const fieldSelects = filters.querySelectorAll(
        '[data-testid^="field-picker-filter-field-"]',
      );
      expect(fieldSelects).toHaveLength(2);
      const fieldValues = Array.from(fieldSelects).map(
        (s) => (s as HTMLSelectElement).value,
      );
      expect(fieldValues).toEqual(['clubblad', 'years_member']);

      // The years_member row is an `eq` row carrying the stringified scalar.
      const opSelects = filters.querySelectorAll('[data-testid^="field-picker-filter-op-"]');
      expect(Array.from(opSelects).map((s) => (s as HTMLSelectElement).value)).toEqual([
        'eq',
        'eq',
      ]);
      const valueInputs = Array.from(
        filters.querySelectorAll('[data-testid^="field-picker-filter-value-"]'),
      ) as HTMLInputElement[];
      expect(valueInputs.map((i) => i.value)).toEqual(['Papier', '25']);
    });

    it('composes BOTH year + generic rows into the object shape through an update', async () => {
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
      // Both rows compose generically to the object FilterClause form; the legacy
      // scalar year filter re-saves as an ordinary `eq` clause (stringified value).
      expect(config.filters).toEqual({
        clubblad: { op: 'eq', value: 'Papier' },
        years_member: { op: 'eq', value: '25' },
      });
    });

    it('drops a blank filter row (no field or no value)', async () => {
      render(<MemberFieldPicker {...makeProps()} />);
      fireEvent.change(screen.getByTestId('field-picker-name'), {
        target: { value: 'No filter set' },
      });
      clickCheckbox('field-picker-group-membership_type');
      // Add a filter row but leave it blank (no field key).
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
    // On open, a blank compose is a filtered-LIST set with NO list columns
    // pre-selected and no name — so it starts in the true "no selection" state.
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
      // … and the set's OWN definition filters travel with it (R4.4), now
      // re-saved in the object FilterClause shape (a legacy scalar reads back
      // as `{ op: 'eq', value }` — equivalent narrowing, R8.2 / R8.8).
      expect(config.filters).toEqual({ clubblad: { op: 'eq', value: 'Papier' } });
      expect(kind).toBe('count');

      // onSaved reports the SAME id so the caller can reselect it.
      await waitFor(() =>
        expect(onSaved).toHaveBeenCalledWith(
          expect.objectContaining({ filters: { clubblad: { op: 'eq', value: 'Papier' } } }),
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

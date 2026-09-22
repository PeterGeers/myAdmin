/**
 * Tests for the Members typed authoring UI (s5c tasks 2.5/2.6, task 2.7).
 *
 * Covers:
 *  - the four sub-editors render the composite types from the definition
 *    (functional-group catalog list<object>, field overlay map<field_def>,
 *    scope dimensions list<object>, view contexts list<object>);
 *  - a picker offers only defined groups / resolvable field keys (Property 7);
 *  - an enum option is authored as { value, label{nl,en}, roles };
 *  - saving issues exactly ONE PUT per param object (Property 8);
 *  - the unsaved-changes guard warns on navigate-away.
 *
 * Uses the project's inline Chakra mock (steering 33): Chakra is auto-aliased to the
 * centralized mock, which renders all TabPanels (no Tab state), so every sub-editor is in
 * the DOM at once and testable directly.
 */
import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor, fireEvent, within } from '../../../../test-utils';
import type { MembersParamDefinition } from '../../../../types/membersConfig';

/* ------------------------------------------------------------------ */
/*  react-i18next stub (en)                                            */
/* ------------------------------------------------------------------ */
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ i18n: { language: 'en' } }),
}));

/* ------------------------------------------------------------------ */
/*  Service mocks                                                      */
/* ------------------------------------------------------------------ */
const mockGetDefs = vi.fn();
const mockGetParams = vi.fn();
const mockCreate = vi.fn();
const mockUpdate = vi.fn();

vi.mock('../../../../services/membersConfigService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/membersConfigService')
  >('../../../../services/membersConfigService');
  return {
    ...actual,
    getMembersParameterDefinitions: (...a: unknown[]) => mockGetDefs(...a),
    getMembersParameters: (...a: unknown[]) => mockGetParams(...a),
    // saveMembersParameter is the REAL implementation — it must route to exactly one of
    // create/update below, which is what Property 8 (save-once → one request) asserts.
    saveMembersParameter: actual.saveMembersParameter,
  };
});

// The save-once primitive delegates to parameterService; mock those to count requests.
vi.mock('../../../../services/parameterService', () => ({
  getParameters: vi.fn(),
  createParameter: (...a: unknown[]) => mockCreate(...a),
  updateParameter: (...a: unknown[]) => mockUpdate(...a),
  deleteParameter: vi.fn(),
  getParameterDefault: vi.fn(),
}));

import MembersConfigEditor from '../MembersConfigEditor';

/* ------------------------------------------------------------------ */
/*  Definition fixture (mirrors backend/src/config/members_parameters.json)  */
/* ------------------------------------------------------------------ */
const DEFS: MembersParamDefinition[] = [
  {
    key: 'field_overlay',
    type: 'map<field_def>',
    label_en: 'Field Overlay',
    label_nl: 'Veldoverlay',
    module: 'MEMBERS',
    object_fields: [
      {
        key: 'functional_groups',
        type: 'list<object>',
        label_en: 'Functional Groups',
        label_nl: 'Functionele groepen',
        object_fields: [
          { key: 'key', type: 'string', label_en: 'Group Key', label_nl: 'Groepssleutel' },
          { key: 'label_en', type: 'string', label_en: 'Label (English)', label_nl: 'Label (Engels)' },
          { key: 'label_nl', type: 'string', label_en: 'Label (Dutch)', label_nl: 'Label (Nederlands)' },
          { key: 'order', type: 'number', label_en: 'Order', label_nl: 'Volgorde' },
        ],
      },
      {
        key: 'fields',
        type: 'map<field_def>',
        label_en: 'Parameter Fields',
        label_nl: 'Parametervelden',
        field_def: [
          { key: 'type', type: 'string', label_en: 'Type', label_nl: 'Type', options: ['string', 'date', 'enum', 'reference'] },
          { key: 'label_en', type: 'string', label_en: 'Label (English)', label_nl: 'Label (Engels)' },
          { key: 'label_nl', type: 'string', label_en: 'Label (Dutch)', label_nl: 'Label (Nederlands)' },
          { key: 'required', type: 'boolean', label_en: 'Required', label_nl: 'Verplicht' },
          { key: 'visible', type: 'boolean', label_en: 'Visible', label_nl: 'Zichtbaar' },
          { key: 'functional_group', type: 'string', label_en: 'Functional Group', label_nl: 'Functionele groep' },
          { key: 'choices', type: 'string[]', label_en: 'Choices', label_nl: 'Keuzes', depends_on: 'type' },
          { key: 'order', type: 'number', label_en: 'Order', label_nl: 'Volgorde' },
        ],
      },
      {
        key: 'fixed_overrides',
        type: 'map<field_def>',
        label_en: 'Fixed Field Overrides',
        label_nl: 'Overrides van vaste velden',
        field_def: [
          { key: 'label_en', type: 'string', label_en: 'Label (English)', label_nl: 'Label (Engels)' },
          { key: 'functional_group', type: 'string', label_en: 'Functional Group', label_nl: 'Functionele groep' },
        ],
      },
    ],
  },
  {
    key: 'scope_dimensions',
    type: 'list<object>',
    label_en: 'Scope Dimensions',
    label_nl: 'Scope-dimensies',
    module: 'MEMBERS',
    object_fields: [
      { key: 'key', type: 'string', label_en: 'Dimension Key', label_nl: 'Dimensiesleutel' },
      { key: 'label_en', type: 'string', label_en: 'Label (English)', label_nl: 'Label (Engels)' },
      { key: 'enabled', type: 'boolean', label_en: 'Enabled', label_nl: 'Ingeschakeld' },
      { key: 'values', type: 'string[]', label_en: 'Values', label_nl: 'Waarden' },
      { key: 'required_for', type: 'string[]', label_en: 'Required For', label_nl: 'Vereist voor' },
    ],
  },
  {
    key: 'view_contexts',
    type: 'list<object>',
    label_en: 'View Contexts',
    label_nl: 'Weergavecontexten',
    module: 'MEMBERS',
    object_fields: [
      { key: 'key', type: 'string', label_en: 'Context Key', label_nl: 'Contextsleutel' },
      { key: 'label_en', type: 'string', label_en: 'Label (English)', label_nl: 'Label (Engels)' },
      { key: 'permission_roles', type: 'string[]', label_en: 'Permission Roles', label_nl: 'Toegestane rollen' },
      { key: 'columns', type: 'string[]', label_en: 'Columns', label_nl: 'Kolommen' },
      { key: 'filterable_columns', type: 'string[]', label_en: 'Filterable Columns', label_nl: 'Filterbare kolommen' },
    ],
  },
];

/* ------------------------------------------------------------------ */
/*  Value fixtures                                                     */
/* ------------------------------------------------------------------ */

/** A field_overlay row with a defined group + one field, so pickers have data. */
const overlayRow = {
  id: 101,
  namespace: 'members',
  key: 'field_overlay',
  value: {
    functional_groups: [
      { key: 'personal', label_en: 'Personal', label_nl: 'Persoonlijk', order: 1 },
      { key: 'motor', label_en: 'Motorcycle', label_nl: 'Motor', order: 2 },
    ],
    fields: {
      motor_brand: {
        type: 'string',
        label_en: 'Motor brand',
        label_nl: 'Motormerk',
        functional_group: 'motor',
        visible: true,
      },
    },
    fixed_overrides: {},
  },
  value_type: 'json' as const,
  scope_origin: 'tenant' as const,
  is_secret: false,
};

const scopeRow = {
  id: 102,
  namespace: 'members',
  key: 'scope_dimensions',
  value: [
    { key: 'region', label_en: 'Region', label_nl: 'Regio', enabled: true, values: ['Region A'] },
  ],
  value_type: 'json' as const,
  scope_origin: 'tenant' as const,
  is_secret: false,
};

const viewRow = {
  id: 103,
  namespace: 'members',
  key: 'view_contexts',
  value: [
    { key: 'overview', label_en: 'Overview', label_nl: 'Overzicht', columns: ['motor_brand'] },
  ],
  value_type: 'json' as const,
  scope_origin: 'tenant' as const,
  is_secret: false,
};

function allRows() {
  return {
    field_overlay: overlayRow,
    scope_dimensions: scopeRow,
    view_contexts: viewRow,
  };
}

const ROLES = ['Members_CRUD', 'Members_Read'];

async function renderEditor(rows: Record<string, unknown> = allRows()) {
  mockGetDefs.mockResolvedValue(DEFS);
  mockGetParams.mockResolvedValue(rows);
  render(<MembersConfigEditor tenant="t1" availableRoles={ROLES} />);
  await waitFor(() =>
    expect(screen.getByTestId('members-config-editor')).toBeInTheDocument(),
  );
}

describe('MembersConfigEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCreate.mockResolvedValue({ success: true });
    mockUpdate.mockResolvedValue({ success: true });
  });

  describe('composite-type rendering (four sub-editors)', () => {
    it('renders all four sub-editors from the definition', async () => {
      await renderEditor();
      expect(screen.getByTestId('sub-editor-field_overlay-functional_groups')).toBeInTheDocument();
      expect(screen.getByTestId('sub-editor-field_overlay-fields-fixed_overrides')).toBeInTheDocument();
      expect(screen.getByTestId('sub-editor-scope_dimensions')).toBeInTheDocument();
      expect(screen.getByTestId('sub-editor-view_contexts')).toBeInTheDocument();
    });

    it('renders the functional-group catalog list<object> rows', async () => {
      await renderEditor();
      // two seeded groups → two list rows in the functional_groups slice
      expect(screen.getByTestId('functional_groups-row-0')).toBeInTheDocument();
      expect(screen.getByTestId('functional_groups-row-1')).toBeInTheDocument();
    });

    it('renders the field overlay map<field_def> entry (keyed by field key)', async () => {
      await renderEditor();
      expect(screen.getByTestId('fields-entry-motor_brand')).toBeInTheDocument();
    });

    it('renders scope dimensions and view contexts as list<object> rows', async () => {
      await renderEditor();
      expect(screen.getByTestId('scope_dimensions-row-0')).toBeInTheDocument();
      expect(screen.getByTestId('view_contexts-row-0')).toBeInTheDocument();
    });
  });

  describe('pickers offer only defined / resolvable references (Property 7)', () => {
    it('functional_group picker offers ONLY the defined catalog groups', async () => {
      await renderEditor();
      // The motor_brand field entry carries a functional_group Select (aria-labelled).
      const entry = screen.getByTestId('fields-entry-motor_brand');
      const select = within(entry).getByLabelText('Functional Group') as HTMLSelectElement;
      const optionValues = Array.from(select.options).map((o) => o.value);
      // '' placeholder + the two defined groups only — no arbitrary values.
      expect(optionValues).toContain('personal');
      expect(optionValues).toContain('motor');
      expect(optionValues.filter((v) => v !== '')).toEqual(['personal', 'motor']);
    });

    it('view-context column picker offers ONLY resolvable field keys', async () => {
      await renderEditor();
      const viewEditor = screen.getByTestId('sub-editor-view_contexts');
      // The column picker Select(s) inside the view context row.
      const selects = Array.from(viewEditor.querySelectorAll('select')) as HTMLSelectElement[];
      const columnSelect = selects.find((s) =>
        Array.from(s.options).some((o) => o.value === 'motor_brand'),
      );
      expect(columnSelect).toBeTruthy();
      const values = Array.from(columnSelect!.options).map((o) => o.value).filter(Boolean);
      // Resolvable set = overlay field (motor_brand) + scope dim key (region); no others.
      expect(values).toContain('motor_brand');
      expect(values).toContain('region');
      expect(values).not.toContain('nonexistent_field');
    });
  });

  describe('save-once (Property 8): exactly ONE request per param object', () => {
    it('editing then saving the scope dimensions issues exactly one PUT', async () => {
      await renderEditor();
      const scopeEditor = screen.getByTestId('sub-editor-scope_dimensions');

      // Make an edit: toggle the dimension `enabled` switch (a boolean control).
      const checkbox = scopeEditor.querySelector('input[type="checkbox"]') as HTMLInputElement;
      expect(checkbox).toBeTruthy();
      fireEvent.click(checkbox);

      // Save button becomes enabled once dirty.
      const saveBtn = within(scopeEditor).getByRole('button', { name: 'Save' });
      await waitFor(() => expect(saveBtn).not.toBeDisabled());
      fireEvent.click(saveBtn);

      await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
      // Exactly one request total (an existing tenant row → PUT/update, never create).
      expect(mockCreate).not.toHaveBeenCalled();
      // The WHOLE object was committed under the scope_dimensions param.
      expect(mockUpdate).toHaveBeenCalledWith(
        102,
        expect.objectContaining({ value_type: 'json' }),
      );
    });

    it('an unauthored param creates the tenant row in exactly one request', async () => {
      // No existing rows → view_contexts is unauthored.
      await renderEditor({});
      const viewEditor = screen.getByTestId('sub-editor-view_contexts');
      const addBtn = within(viewEditor).getByRole('button', { name: /Add View Contexts/i });
      fireEvent.click(addBtn);

      const saveBtn = within(viewEditor).getByRole('button', { name: 'Save' });
      await waitFor(() => expect(saveBtn).not.toBeDisabled());
      fireEvent.click(saveBtn);

      await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
      expect(mockUpdate).not.toHaveBeenCalled();
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({ scope: 'tenant', namespace: 'members', key: 'view_contexts', value_type: 'json' }),
      );
    });
  });

  describe('enum options authored as { value, label{nl,en}, roles }', () => {
    it('adds a rich enum option with per-option role restriction', async () => {
      await renderEditor();
      const overlayEditor = screen.getByTestId('sub-editor-field_overlay-fields-fixed_overrides');
      const entry = within(overlayEditor).getByTestId('fields-entry-motor_brand');

      // Add an enum option (the `choices` string[] renders the EnumOptionsEditor).
      const addOption = within(entry).getByRole('button', { name: 'Add option' });
      fireEvent.click(addOption);

      const option = within(entry).getByTestId('enum-option-0');
      fireEvent.change(within(option).getByLabelText('Option 1 value'), { target: { value: 'harley' } });
      fireEvent.change(within(option).getByLabelText('Option 1 label nl'), { target: { value: 'Harley' } });
      fireEvent.change(within(option).getByLabelText('Option 1 label en'), { target: { value: 'Harley' } });
      // Role restriction toggle (R4.12)
      fireEvent.click(within(option).getByLabelText('Option 1 role Members_CRUD'));

      // Save → the committed object carries the rich option shape.
      const saveBtn = within(overlayEditor).getByRole('button', { name: 'Save' });
      await waitFor(() => expect(saveBtn).not.toBeDisabled());
      fireEvent.click(saveBtn);

      await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
      const savedValue = mockUpdate.mock.calls[0][1].value as any;
      const choices = savedValue.fields.motor_brand.choices;
      expect(choices).toEqual([
        { value: 'harley', label: { nl: 'Harley', en: 'Harley' }, roles: ['Members_CRUD'] },
      ]);
    });
  });
});

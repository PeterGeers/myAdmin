/**
 * Deliverable-11 close-out — single save path + convergence integration suite
 * (Members config redesign Phase 3 — task 4.3, R4.7 / R8.4; `38-sam-module-field-config.md`
 * rule 5, `33-frontend-testing.md`).
 *
 * Tasks 1.3 / 2.2 / 3.2 / 4.1 / 4.2 each landed one slice of the rebuilt authoring UI and its
 * paired per-slice cases (in `MembersConfigEditor.test.tsx` / `MembersGroupFieldHierarchy.test.tsx`).
 * Task 4.3 is the Deliverable-11 CLOSE-OUT: it LOCKS the one contract those slices converge on —
 * the SINGLE SAVE PATH. The new UI must save through ONE typed save → ONE re-projection, and the
 * surviving authoring deliverables that ride it — the provenance badge (step 8) and
 * scope-as-attribute (step 9) — must author through that one path, committing the WHOLE
 * `field_overlay` object (scope attribute carried, NO analytics slice) in EXACTLY ONE request
 * (`38` rule 5, Property 8). (The analytics-as-fields `alias` deliverable was removed —
 * members-analytics-role-removal.)
 *
 * This file adds integration coverage at the mounted-editor boundary for the four things task 4.3
 * names, as a dedicated close-out suite rather than re-editing the per-slice cases (so no existing
 * assertion is weakened — Change-With-Tests, `30`/`32`):
 *
 *   (a) the group → field → attribute flow — the hierarchy nests catalog groups → fields →
 *       per-field attribute chips off the single resolved config the one save re-projects;
 *   (b) the provenance badge — base / tenant_added / base_overridden shown per field in the one
 *       unified list the collapse produced (step 8);
 *   (c) the picker-resolvability guard — pickers offer ONLY catalog-resolvable references, and an
 *       already-authored UNRESOLVABLE reference is SURFACED (never silently dropped), both in the
 *       functional-group picker and in the hierarchy's trailing "ungrouped" bucket (R4.3);
 *   (d) the single-save path — editing provenance-authored fields + a scope attribute + an
 *       analytics alias and saving issues EXACTLY ONE request that commits the whole
 *       `field_overlay` object with the scope attribute carried and the alias folded into
 *       `analytics.field_roles` (one save → one re-projection, R4.7 / Property 8), AND both
 *       sub-editors route through the SAME save-once primitive (`saveMembersParameter`), so there
 *       is genuinely ONE authoring door, not two.
 *
 * Uses the project's inline Chakra mock (steering 33): Chakra is auto-aliased to the centralized
 * mock (vite.config `test.alias`), which renders ALL TabPanels (no Tab state), so both the
 * presentation views and both sub-editors are in the DOM at once and testable directly without
 * tab navigation. The save-once primitive (`saveMembersParameter`) is the REAL implementation; it
 * delegates to the mocked `parameterService.create/updateParameter`, so counting those calls is a
 * faithful count of the HTTP requests the one save path issues.
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
/*  Service mocks — mirror MembersConfigEditor.test.tsx so the save    */
/*  primitive and ordering helpers remain REAL and the HTTP boundary   */
/*  (parameterService.create/update) is the counted request edge.      */
/* ------------------------------------------------------------------ */
const mockGetDefs = vi.fn();
const mockGetParams = vi.fn();
const mockCreate = vi.fn();
const mockUpdate = vi.fn();
const mockGetFieldConfig = vi.fn();

vi.mock('../../../../services/membersConfigService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/membersConfigService')
  >('../../../../services/membersConfigService');
  return {
    ...actual,
    getMembersParameterDefinitions: (...a: unknown[]) => mockGetDefs(...a),
    getMembersParameters: (...a: unknown[]) => mockGetParams(...a),
    getMembersFieldConfig: (...a: unknown[]) => mockGetFieldConfig(...a),
    // REAL ordering/grouping helpers — the derived (group.order, field.order, key) order and the
    // group → field hierarchy are part of what this suite exercises, so they are not mocked.
    orderResolvedFields: actual.orderResolvedFields,
    groupResolvedFields: actual.groupResolvedFields,
    // REAL save-once primitive — Property 8 (one save → one request) is asserted through it.
    saveMembersParameter: actual.saveMembersParameter,
  };
});

// The save-once primitive delegates to parameterService; mock those to COUNT requests — the one
// save path must hit exactly ONE of create/update, exactly once.
vi.mock('../../../../services/parameterService', () => ({
  getParameters: vi.fn(),
  createParameter: (...a: unknown[]) => mockCreate(...a),
  updateParameter: (...a: unknown[]) => mockUpdate(...a),
  deleteParameter: vi.fn(),
  getParameterDefault: vi.fn(),
}));

import MembersConfigEditor from '../MembersConfigEditor';

/* ------------------------------------------------------------------ */
/*  Definition fixture — the field_overlay param with the scope +      */
/*  alias per-field attributes (the shape tasks 2.2 / 3.2 authored).   */
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
          // Scope-binding is a per-field attribute (step 9, R2) — it rides the single save path.
          {
            key: 'scope',
            type: 'object',
            label_en: 'Scope Axis',
            label_nl: 'Scope-as',
            object_fields: [
              { key: 'enabled', type: 'boolean', label_en: 'Enabled', label_nl: 'Ingeschakeld' },
              { key: 'values', type: 'string[]', label_en: 'Values', label_nl: 'Waarden' },
              { key: 'required_for', type: 'string[]', label_en: 'Required For', label_nl: 'Vereist voor' },
            ],
          },
          // (members-analytics-role-removal) the analytics `alias` attribute was removed.
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
          {
            key: 'scope',
            type: 'object',
            label_en: 'Scope Axis',
            label_nl: 'Scope-as',
            object_fields: [
              { key: 'enabled', type: 'boolean', label_en: 'Enabled', label_nl: 'Ingeschakeld' },
              { key: 'values', type: 'string[]', label_en: 'Values', label_nl: 'Waarden' },
              { key: 'required_for', type: 'string[]', label_en: 'Required For', label_nl: 'Vereist voor' },
            ],
          },
          // (members-analytics-role-removal) the analytics `alias` attribute was removed.
        ],
      },
    ],
  },
];

/* ------------------------------------------------------------------ */
/*  Value fixture — the single field_overlay tenant row (id 202).      */
/*                                                                      */
/*  Two defined groups + three overlay fields, chosen so this one row   */
/*  exercises all three deliverables through the one object:            */
/*   - `motor_brand` — a plain tenant-added field under group `motor`;  */
/*   - `region`      — a SCOPE-AXIS field (step 9) carrying a `scope`   */
/*                     attribute, AND the `country_detail` analytics    */
/*                     ALIAS (step 10) — one field, two attributes;     */
/*   - `legacy_pin`  — a field whose functional_group references the    */
/*                     NON-catalog group `ghost` → the picker-          */
/*                     resolvability guard must SURFACE it, not drop it  */
/*                     (R4.3). It is still an overlay KEY, so it rides   */
/*                     the same single save.                            */
/* ------------------------------------------------------------------ */
const overlayRow = {
  id: 202,
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
      region: {
        type: 'string',
        label_en: 'Region',
        label_nl: 'Regio',
        functional_group: 'personal',
        visible: true,
        scope: { enabled: true, values: ['Region A'] },
      },
      legacy_pin: {
        type: 'string',
        label_en: 'Legacy pin',
        label_nl: 'Oude pin',
        functional_group: 'ghost', // NOT a defined catalog group → surfaced, never dropped (R4.3)
        visible: true,
      },
    },
    fixed_overrides: {},
  },
  value_type: 'json' as const,
  scope_origin: 'tenant' as const,
  is_secret: false,
};

function allRows() {
  return { field_overlay: overlayRow };
}

/**
 * The module's RESOLVED field-config (`GET /members/field-config`) the editor re-presents — the
 * ONE field set the single save re-projects. Deliberately NOT in display order on the wire so the
 * suite proves the DERIVED (group.order, field.order, key) order (R1.3 / R4.2):
 *   - `motor_brand`         → group `motor` (order 2), field order 1 → tenant_added
 *   - `personal.last_name`  → group `personal` (order 1), field order 2 → base
 *   - `personal.first_name` → group `personal` (order 1), field order 1 → base_overridden
 *   - `region`              → group `personal` (order 1), field order 3 → tenant_added, scope+alias
 *   - `legacy_pin`          → group `ghost` (NOT defined) → the trailing "ungrouped" bucket (R4.3)
 */
const FIELD_CONFIG = {
  fields: [
    {
      key: 'motor_brand',
      functional_group: 'motor',
      order: 1,
      origin: 'variable' as const,
      provenance: 'tenant_added' as const,
      type: 'string',
      label: { en: 'Motor brand', nl: 'Motormerk' },
      visible: true,
    },
    {
      key: 'personal.last_name',
      functional_group: 'personal',
      order: 2,
      origin: 'fixed' as const,
      provenance: 'base' as const,
      type: 'string',
      label: { en: 'Last name', nl: 'Achternaam' },
      visible: true,
    },
    {
      key: 'personal.first_name',
      functional_group: 'personal',
      order: 1,
      origin: 'fixed' as const,
      provenance: 'base_overridden' as const,
      type: 'string',
      label: { en: 'First name', nl: 'Voornaam' },
      visible: true,
    },
    {
      key: 'region',
      functional_group: 'personal',
      order: 3,
      origin: 'variable' as const,
      provenance: 'tenant_added' as const,
      type: 'string',
      label: { en: 'Region', nl: 'Regio' },
      visible: true,
      ...({ scope: { enabled: true, values: ['Region A'] } } as object),
    },
    {
      key: 'legacy_pin',
      functional_group: 'ghost',
      origin: 'variable' as const,
      provenance: 'tenant_added' as const,
      type: 'string',
      label: { en: 'Legacy pin', nl: 'Oude pin' },
      visible: true,
    },
  ],
  functional_groups: [
    { key: 'personal', label: { en: 'Personal', nl: 'Persoonlijk' }, order: 1 },
    { key: 'motor', label: { en: 'Motorcycle', nl: 'Motor' }, order: 2 },
  ],
  config_status: {
    fields: '2026-10-12T09:00:00',
    scope: 3,
    views: null,
    mail: null,
  },
};

const ROLES = ['Members_CRUD', 'Members_Read'];

async function renderEditor(
  rows: Record<string, unknown> = allRows(),
  fieldConfig: unknown = FIELD_CONFIG,
) {
  mockGetDefs.mockResolvedValue(DEFS);
  mockGetParams.mockResolvedValue(rows);
  mockGetFieldConfig.mockResolvedValue(fieldConfig);
  render(<MembersConfigEditor tenant="t1" availableRoles={ROLES} />);
  await waitFor(() =>
    expect(screen.getByTestId('members-config-editor')).toBeInTheDocument(),
  );
}

describe('MembersConfig Deliverable-11 close-out — single save path (task 4.3, R4.7/R8.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCreate.mockResolvedValue({ success: true });
    mockUpdate.mockResolvedValue({ success: true });
  });

  /* ---------------------------------------------------------------- */
  /*  (a) the group → field → attribute flow                           */
  /* ---------------------------------------------------------------- */
  describe('(a) group → field → attribute flow', () => {
    it('renders catalog groups as sections with their fields nested, in derived order', async () => {
      await renderEditor();
      // Groups personal (order 1) then motor (order 2) — defined-catalog sections in derived order.
      const groups = screen
        .getAllByTestId(/^members-hierarchy-group-/)
        .map((n) => n.getAttribute('data-testid'));
      expect(groups).toEqual([
        'members-hierarchy-group-personal',
        'members-hierarchy-group-motor',
        // legacy_pin's unresolvable group bucket trails the defined groups (see guard test (c)).
        'members-hierarchy-group-__ungrouped__',
      ]);
      // personal nests first_name (order 1), last_name (order 2), region (order 3) — derived.
      const personal = screen.getByTestId('members-hierarchy-group-personal');
      const personalFields = within(personal)
        .getAllByTestId(/^members-hierarchy-field-/)
        .map((n) => n.getAttribute('data-testid'));
      expect(personalFields).toEqual([
        'members-hierarchy-field-personal.first_name',
        'members-hierarchy-field-personal.last_name',
        'members-hierarchy-field-region',
      ]);
    });

    it('shows the per-field scope-axis attribute chip on the field row', async () => {
      await renderEditor();
      // The `region` field carries the step-9 scope attribute, shown as a chip in the hierarchy.
      // (The analytics-role `alias` attribute was removed — members-analytics-role-removal.)
      expect(screen.getByTestId('members-hierarchy-attr-scope-region')).toHaveTextContent(
        'scope axis',
      );
      expect(screen.queryByTestId('members-hierarchy-attr-alias-region')).not.toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  (b) the provenance badge                                         */
  /* ---------------------------------------------------------------- */
  describe('(b) provenance badge', () => {
    it('shows one unified list with a base / tenant_added / base_overridden badge per field', async () => {
      await renderEditor();
      // ONE unified list (the step-8 collapse), every resolved field present with its badge.
      expect(screen.getByTestId('members-field-provenance-list')).toBeInTheDocument();
      expect(
        screen.getByTestId('members-field-provenance-personal.last_name'),
      ).toHaveTextContent('Base');
      expect(
        screen.getByTestId('members-field-provenance-personal.first_name'),
      ).toHaveTextContent('Base (overridden)');
      expect(
        screen.getByTestId('members-field-provenance-motor_brand'),
      ).toHaveTextContent('Tenant-added');
    });

    it('orders the unified list by the derived (group.order, field.order, key), no stored position', async () => {
      await renderEditor();
      const order = screen
        .getAllByTestId(/^members-field-row-/)
        .map((r) => r.getAttribute('data-testid'));
      // personal(1): first_name(1), last_name(2), region(3); motor(2): motor_brand; then legacy_pin
      // (group `ghost` sorts last via MAX_SAFE_INTEGER group order, key tiebreak).
      expect(order).toEqual([
        'members-field-row-personal.first_name',
        'members-field-row-personal.last_name',
        'members-field-row-region',
        'members-field-row-motor_brand',
        'members-field-row-legacy_pin',
      ]);
    });
  });

  /* ---------------------------------------------------------------- */
  /*  (c) the picker-resolvability guard                               */
  /* ---------------------------------------------------------------- */
  describe('(c) picker-resolvability guard', () => {
    it('the functional-group picker offers ONLY the defined catalog groups (no free text)', async () => {
      await renderEditor();
      const entry = screen.getByTestId('fields-entry-motor_brand');
      const select = within(entry).getByLabelText('Functional Group') as HTMLSelectElement;
      const optionValues = Array.from(select.options)
        .map((o) => o.value)
        .filter(Boolean);
      // Exactly the two defined catalog groups — never an arbitrary / non-existent group key.
      expect(optionValues).toEqual(['personal', 'motor']);
      expect(optionValues).not.toContain('ghost');
    });

    it('presents no per-field analytics role picker (removed with the role config layer)', async () => {
      await renderEditor();
      const entry = screen.getByTestId('fields-entry-motor_brand');
      // The analytics-role alias picker was removed — only the surviving reference pickers remain.
      expect(within(entry).queryByLabelText('Analytics Role')).not.toBeInTheDocument();
    });

    it('SURFACES an already-authored unresolvable group reference, never silently drops it (R4.3)', async () => {
      await renderEditor();
      // `legacy_pin` references the non-catalog group `ghost`; the guard keeps it VISIBLE in the
      // trailing "ungrouped" bucket (the picker-resolvability guard made observable) …
      const ungrouped = screen.getByTestId('members-hierarchy-group-__ungrouped__');
      expect(
        within(ungrouped).getByTestId('members-hierarchy-field-legacy_pin'),
      ).toBeInTheDocument();
      expect(screen.getByTestId('members-hierarchy-unresolved-badge')).toBeInTheDocument();
      // … and the field is NOT lost from the unified provenance list either.
      expect(screen.getByTestId('members-field-row-legacy_pin')).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  (d) the single-save path — the Deliverable-11 close-out contract */
  /* ---------------------------------------------------------------- */
  describe('(d) single save path (one save → one re-projection, R4.7 / Property 8)', () => {
    it('one save commits the WHOLE field_overlay in EXACTLY one request with scope carried (no analytics slice)', async () => {
      await renderEditor();
      const overlayEditor = screen.getByTestId(
        'sub-editor-field_overlay-fields-fixed_overrides',
      );

      // Author on the one object before saving (the analytics-alias deliverable was removed):
      //  - step 9: toggle the `region` scope-axis `enabled` switch (scope attribute edit).
      const regionEntry = within(overlayEditor).getByTestId('fields-entry-region');
      const enabledSwitch = within(regionEntry).getByLabelText('Enabled') as HTMLInputElement;
      fireEvent.click(enabledSwitch); // true → false

      // ONE typed save.
      const saveBtn = within(overlayEditor).getByRole('button', { name: 'Save' });
      await waitFor(() => expect(saveBtn).not.toBeDisabled(), { timeout: 5000 });
      fireEvent.click(saveBtn);

      // EXACTLY ONE request — a PUT to the existing tenant row, never a second request / a create.
      await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
      expect(mockCreate).not.toHaveBeenCalled();
      expect(mockUpdate).toHaveBeenCalledWith(
        202,
        expect.objectContaining({ value_type: 'json' }),
      );

      const savedValue = mockUpdate.mock.calls[0][1].value as any;
      // step 9 — the scope attribute is carried on the field, toggled true → false;
      expect(savedValue.fields.region.scope.enabled).toBe(false);
      // NO analytics slice is derived/written anymore (the fold was removed).
      expect(savedValue.analytics).toBeUndefined();
      // step 8 — every provenance-authored sibling (groups + the unresolvable field) rides the
      // same single whole-object commit, nothing split out to a second request.
      expect(savedValue.functional_groups).toHaveLength(2);
      expect(savedValue.fields.legacy_pin).toBeTruthy();
    });

    it('routes BOTH sub-editors through the SAME save-once primitive — one authoring door, not two', async () => {
      await renderEditor();
      // The functional-group sub-editor and the fields/fixed_overrides sub-editor are two VIEWS of
      // the ONE field_overlay object. Saving EITHER must issue exactly one request against the one
      // row (202) — proving there is a single save path, not a per-sub-editor door.

      // Save from the functional-group sub-editor.
      const groupEditor = screen.getByTestId('sub-editor-field_overlay-functional_groups');
      const groupRow = within(groupEditor).getByTestId('functional_groups-row-0');
      const labelInput = within(groupRow).getByLabelText('Label (English)') as HTMLInputElement;
      fireEvent.change(labelInput, { target: { value: 'Personal (edited)' } });
      const groupSave = within(groupEditor).getByRole('button', { name: 'Save' });
      await waitFor(() => expect(groupSave).not.toBeDisabled(), { timeout: 5000 });
      fireEvent.click(groupSave);
      await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
      expect(mockUpdate).toHaveBeenCalledWith(202, expect.objectContaining({ value_type: 'json' }));

      // Save from the fields sub-editor → still the SAME single row, one more request (not a
      // different endpoint / a create). Both doors fan into saveMembersParameter → one PUT each.
      const overlayEditor = screen.getByTestId('sub-editor-field_overlay-fields-fixed_overrides');
      const motorEntry = within(overlayEditor).getByTestId('fields-entry-motor_brand');
      const visibleSwitch = within(motorEntry).getByLabelText('Visible') as HTMLInputElement;
      fireEvent.click(visibleSwitch);
      const overlaySave = within(overlayEditor).getByRole('button', { name: 'Save' });
      await waitFor(() => expect(overlaySave).not.toBeDisabled(), { timeout: 5000 });
      fireEvent.click(overlaySave);
      await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(2));

      // Every request went to the one field_overlay row via the one primitive; none created a row.
      expect(mockCreate).not.toHaveBeenCalled();
      expect(mockUpdate.mock.calls.every((c) => c[0] === 202)).toBe(true);
    });

    it('an unauthored tenant creates the single field_overlay row in exactly one request', async () => {
      // No existing rows → the one save path creates the tenant row (one POST), never two requests.
      await renderEditor({});
      const groupEditor = screen.getByTestId('sub-editor-field_overlay-functional_groups');
      const addBtn = within(groupEditor).getByRole('button', { name: /Add Functional Groups/i });
      fireEvent.click(addBtn);

      const saveBtn = within(groupEditor).getByRole('button', { name: 'Save' });
      await waitFor(() => expect(saveBtn).not.toBeDisabled(), { timeout: 5000 });
      fireEvent.click(saveBtn);

      await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
      expect(mockUpdate).not.toHaveBeenCalled();
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          scope: 'tenant',
          namespace: 'members',
          key: 'field_overlay',
          value_type: 'json',
        }),
      );
    });
  });
});

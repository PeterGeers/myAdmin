/**
 * Tests for the Members typed authoring UI (s5c tasks 2.5/2.6, task 2.7).
 *
 * Covers:
 *  - the sub-editors render the composite types from the definition
 *    (functional-group catalog list<object>, field overlay map<field_def>);
 *  - the UNIFIED field list + provenance badge that replaced the two-section
 *    fixed/overlay split (Members config redesign Phase 3 step 8, R1);
 *  - scope-binding authored as a per-field `scope` ATTRIBUTE on a field_overlay entry
 *    (Members config redesign Phase 3 step 9, R2) — the standalone scope_dimensions
 *    sub-editor is retired;
 *  - the analytics role config layer (standalone sub-editor AND the per-field `alias`
 *    attribute that folded into `field_overlay.analytics`) is REMOVED
 *    (members-analytics-role-removal) — superseded by the generic Dynamic Pivot Views;
 *  - a picker offers only defined groups / resolvable field keys (Property 7);
 *  - an enum option is authored as { value, label{nl,en}, roles };
 *  - saving issues exactly ONE PUT per param object (Property 8);
 *  - the unsaved-changes guard warns on navigate-away.
 *
 * NOTE (Members config redesign Phase 2, step b — task 3.3): the `view_contexts`
 * sub-editor was retired, so its definition/fixture/cases were removed here per the
 * Change-With-Tests contract.
 *
 * NOTE (Members config redesign Phase 3 step 9 — task 2.2, Change-With-Tests): the standalone
 * `scope_dimensions` sub-editor TAB is RETIRED. Scope-binding is now authored as a FIELD
 * ATTRIBUTE: a `fields` / `fixed_overrides` entry carries a `scope` sub-object
 * `{enabled, values, required_for?}` declaring that the field IS a scope axis bound to itself.
 * The former scope sub-editor cases (`renders scope dimensions as list<object> rows`, the scope
 * save-once case, the unauthored-scope create case) are REWRITTEN to the field-attribute
 * authoring. The save-once / one-PUT property is UNCHANGED and still asserted — the scope
 * attribute now rides on the SINGLE `field_overlay` whole-object commit (Property 8). The analytics
 * role-picker resolvability case now draws the scope-axis field key from the overlay fields (the
 * standalone scope_dimensions param no longer widens the picker set — see `deriveResolvableKeys`).
 *
 * NOTE (members-analytics-role-removal, Change-With-Tests): the analytics role / jubilee /
 * address-mapping config layer is REMOVED — both the standalone analytics sub-editor AND the
 * per-field `alias` attribute that folded into `field_overlay.analytics`. It duplicated the
 * generic Dynamic Pivot Views mechanism. The former "analytics config slice" / "Property 3
 * folding" describe blocks are replaced by a single block asserting the analytics authoring
 * surface is GONE and that save-once still commits the field_overlay with NO analytics slice.
 * The configurator authors only functional groups + the field overlay (incl. the scope
 * attribute); the surviving save-once / one-PUT behavior (Property 8) is UNCHANGED.
 *
 * NOTE (Members config redesign Phase 3 step 8 — task 1.3, Change-With-Tests): the Field
 * Overlay tab now RE-PRESENTS the former fixed/overlay two-section split as ONE ordered
 * field list (ordered `(group.order, field.order, key)`, R1.3 — no new position field) with a
 * provenance badge per field (base / tenant_added / base_overridden, R1.2). The resolved field
 * list is read from the module's `GET /members/field-config` (now mocked via
 * `getMembersFieldConfig`, which also carries the `config_status` the status banner reads).
 * Authoring is UNCHANGED — the `field_overlay` fields/fixed_overrides sub-editor still commits
 * the single object in one PUT (R1.4 / Property 8), so those cases are kept intact.
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
const mockGetFieldConfig = vi.fn();

vi.mock('../../../../services/membersConfigService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/membersConfigService')
  >('../../../../services/membersConfigService');
  return {
    ...actual,
    getMembersParameterDefinitions: (...a: unknown[]) => mockGetDefs(...a),
    getMembersParameters: (...a: unknown[]) => mockGetParams(...a),
    // The resolved field-config fetch (`GET /members/field-config`) feeds BOTH the
    // delivered/loaded status banner (Phase 0 step 3, via `config_status`) AND the unified
    // field list + provenance badge (Phase 3 step 8, R1, via `fields` + `functional_groups`).
    // Mocked so the editor test does not hit the module endpoint.
    getMembersFieldConfig: (...a: unknown[]) => mockGetFieldConfig(...a),
    // `orderResolvedFields` is the REAL implementation — the editor relies on it to derive the
    // `(group.order, field.order, key)` display order (R1.3) with no new position field.
    orderResolvedFields: actual.orderResolvedFields,
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
          // Phase 3 step 9 (R2): scope-binding is a per-field attribute `{enabled, values,
          // required_for?}` declaring the field is a scope axis bound to itself. Authored HERE
          // (within the field overlay), not in a standalone scope_dimensions sub-editor.
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
        ],
      },
      // NOTE (members-analytics-role-removal): the analytics role / jubilee / address-mapping
      // config layer — and the per-field `alias` attribute that folded into it — were REMOVED
      // (superseded by the generic Dynamic Pivot Views mechanism). There is no `analytics` object
      // slice and no `alias` attribute in the authoring definition.
    ],
  },
];

/* ------------------------------------------------------------------ */
/*  Value fixtures                                                     */
/* ------------------------------------------------------------------ */

/**
 * A field_overlay row with a defined group + two fields, so pickers have data:
 *  - `motor_brand` — a plain (non-scoping) overlay field;
 *  - `region`      — an overlay field authored as a SCOPE AXIS (Phase 3 step 9, R2): it carries a
 *                    `scope` attribute `{enabled, values}` declaring it is a scope axis bound to
 *                    itself. This is the authoring representation that REPLACED the standalone
 *                    scope_dimensions param. It is also an overlay field KEY, so the picker-
 *                    resolvability set still includes `region` (via `deriveResolvableKeys`).
 */
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
      region: {
        type: 'string',
        label_en: 'Region',
        label_nl: 'Regio',
        functional_group: 'personal',
        visible: true,
        scope: { enabled: true, values: ['Region A'] },
      },
    },
    fixed_overrides: {},
  },
  value_type: 'json' as const,
  scope_origin: 'tenant' as const,
  is_secret: false,
};

function allRows() {
  return {
    field_overlay: overlayRow,
  };
}

/**
 * The module's RESOLVED field-config (`GET /members/field-config`) the editor reads to render
 * the unified field list + provenance badge (Phase 3 step 8, R1) AND to drive the status banner
 * (via `config_status`). Deliberately NOT in `(group.order, field.order, key)` order on the wire,
 * so the test proves the editor DERIVES the order (R1.3) via `orderResolvedFields`:
 *   - `motor_brand`  → group `motor` (order 2), field order 1  → tenant_added
 *   - `last_name`    → group `personal` (order 1), field order 2 → base
 *   - `first_name`   → group `personal` (order 1), field order 1 → base_overridden
 * Expected derived order: first_name, last_name, motor_brand.
 */
const FIELD_CONFIG = {
  fields: [
    {
      key: 'motor_brand',
      functional_group: 'motor',
      order: 1,
      origin: 'variable' as const,
      provenance: 'tenant_added' as const,
      label: { en: 'Motor brand', nl: 'Motormerk' },
      visible: true,
    },
    {
      key: 'personal.last_name',
      functional_group: 'personal',
      order: 2,
      origin: 'fixed' as const,
      provenance: 'base' as const,
      label: { en: 'Last name', nl: 'Achternaam' },
      visible: true,
    },
    {
      key: 'personal.first_name',
      functional_group: 'personal',
      order: 1,
      origin: 'fixed' as const,
      provenance: 'base_overridden' as const,
      label: { en: 'First name', nl: 'Voornaam' },
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

describe('MembersConfigEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCreate.mockResolvedValue({ success: true });
    mockUpdate.mockResolvedValue({ success: true });
  });

  describe('projection status banner (Phase 0 step 3)', () => {
    it('renders the delivered/loaded status from the module config_status', async () => {
      await renderEditor();
      const banner = await screen.findByTestId('members-config-status');
      // fields was delivered → a Delivered badge; views was never delivered → Not yet delivered.
      expect(
        within(screen.getByTestId('members-config-status-fields')).getByText('Delivered'),
      ).toBeInTheDocument();
      expect(
        within(screen.getByTestId('members-config-status-views')).getByText(
          'Not yet delivered',
        ),
      ).toBeInTheDocument();
      expect(banner).toBeInTheDocument();
    });

    it('hides the banner when status is unavailable (older module build)', async () => {
      // No config_status on the resolved field-config → status map is empty → banner hides.
      await renderEditor(allRows(), { fields: [], functional_groups: [] });
      expect(screen.queryByTestId('members-config-status')).not.toBeInTheDocument();
    });

    it('hides the banner when the field-config fetch fails (null)', async () => {
      await renderEditor(allRows(), null);
      expect(screen.queryByTestId('members-config-status')).not.toBeInTheDocument();
    });
  });

  describe('composite-type rendering (sub-editors)', () => {
    it('renders the kept sub-editors from the definition', async () => {
      await renderEditor();
      expect(screen.getByTestId('sub-editor-field_overlay-functional_groups')).toBeInTheDocument();
      expect(screen.getByTestId('sub-editor-field_overlay-fields-fixed_overrides')).toBeInTheDocument();
      // The standalone scope_dimensions sub-editor is RETIRED (Phase 3 step 9, R2.2) — scope is
      // now a per-field attribute within the field overlay, so there is no scope sub-editor.
      expect(screen.queryByTestId('sub-editor-scope_dimensions')).not.toBeInTheDocument();
      // The standalone analytics sub-editor is RETIRED (Phase 3 step 10, R3.3) — analytics
      // field-role aliases are now a per-field attribute, folded into field_overlay.analytics on
      // Save, so there is no separate analytics object sub-editor.
      expect(screen.queryByTestId('sub-editor-field_overlay-analytics')).not.toBeInTheDocument();
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

    it('renders a field_overlay entry for the scope-axis field', async () => {
      await renderEditor();
      // Phase 3 step 9 (R2): scope is a per-field attribute. The `region` field (a scope axis)
      // is just another field_overlay entry — no standalone scope_dimensions list rows exist.
      expect(screen.getByTestId('fields-entry-region')).toBeInTheDocument();
      expect(screen.queryByTestId('scope_dimensions-row-0')).not.toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Scope-binding authored as a per-field attribute                  */
  /*  (Members config redesign Phase 3 step 9 — task 2.2, R2)         */
  /*                                                                   */
  /*  REWRITES the former standalone scope_dimensions sub-editor cases */
  /*  to the field-attribute authoring. A field carries a `scope`      */
  /*  sub-object { enabled, values, required_for? } declaring it IS a  */
  /*  scope axis bound to itself. The save-once / one-PUT property is  */
  /*  unchanged — the scope attribute rides on the SINGLE field_overlay */
  /*  whole-object commit (Property 8), asserted below.                */
  /* ---------------------------------------------------------------- */
  describe('scope-binding as a per-field attribute (Phase 3 step 9, R2)', () => {
    it('retires the standalone scope_dimensions sub-editor (R2.2)', async () => {
      await renderEditor();
      expect(screen.queryByTestId('sub-editor-scope_dimensions')).not.toBeInTheDocument();
    });

    it('authors the scope axis as a `scope` attribute within the field entry (R2.1)', async () => {
      await renderEditor();
      const overlayEditor = screen.getByTestId('sub-editor-field_overlay-fields-fixed_overrides');
      const entry = within(overlayEditor).getByTestId('fields-entry-region');
      // The field's scope attribute renders its own enabled toggle + values list — the scope
      // axis is authored HERE, on the field, not in a separate scope_dimensions editor.
      expect(within(entry).getByLabelText('Enabled')).toBeInTheDocument();
    });

    it('editing a field scope attribute + saving commits the WHOLE field_overlay in one PUT (Property 8)', async () => {
      await renderEditor();
      const overlayEditor = screen.getByTestId('sub-editor-field_overlay-fields-fixed_overrides');
      const entry = within(overlayEditor).getByTestId('fields-entry-region');

      // Toggle the scope axis `enabled` switch (a boolean control on the field's scope attribute).
      const enabledSwitch = within(entry).getByLabelText('Enabled') as HTMLInputElement;
      fireEvent.click(enabledSwitch);

      // Save-once: exactly ONE request, routed to update (an existing field_overlay tenant row).
      const saveBtn = within(overlayEditor).getByRole('button', { name: 'Save' });
      await waitFor(() => expect(saveBtn).not.toBeDisabled(), { timeout: 5000 });
      fireEvent.click(saveBtn);

      await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
      expect(mockCreate).not.toHaveBeenCalled();
      // The WHOLE field_overlay object was committed under the single field_overlay row (id 101),
      // the scope attribute riding on the same whole-object PUT as the field it annotates.
      expect(mockUpdate).toHaveBeenCalledWith(
        101,
        expect.objectContaining({ value_type: 'json' }),
      );
      const savedValue = mockUpdate.mock.calls[0][1].value as any;
      // The scope attribute is serialized on the field (toggled from true → false here); the
      // sibling non-scoping field and the functional-group catalog ride the same single commit.
      expect(savedValue.fields.region.scope.enabled).toBe(false);
      expect(savedValue.fields.motor_brand).toBeTruthy();
      expect(savedValue.functional_groups).toHaveLength(2);
      // No analytics slice is derived/written — the authoring layer no longer folds one
      // (members-analytics-role-removal).
      expect(savedValue.analytics).toBeUndefined();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Unified field list + provenance badge                           */
  /*  (Members config redesign Phase 3 step 8 — task 1.3, R1)         */
  /*                                                                   */
  /*  Rewrites the former fixed/overlay TWO-SECTION split into ONE     */
  /*  ordered list with a per-field provenance badge. Authoring is     */
  /*  unchanged (the fields/fixed_overrides sub-editor still commits   */
  /*  the single field_overlay object — covered by the save-once case).*/
  /* ---------------------------------------------------------------- */
  describe('unified field list + provenance badge (Phase 3 step 8, R1)', () => {
    it('renders ONE unified field list in place of the two-section split (R1.1)', async () => {
      await renderEditor();
      const list = screen.getByTestId('members-field-provenance-list');
      expect(list).toBeInTheDocument();
      // Every resolved field — base ⊕ tenant — appears in the SINGLE list.
      expect(screen.getByTestId('members-field-row-personal.first_name')).toBeInTheDocument();
      expect(screen.getByTestId('members-field-row-personal.last_name')).toBeInTheDocument();
      expect(screen.getByTestId('members-field-row-motor_brand')).toBeInTheDocument();
    });

    it('shows a provenance badge per field (base / tenant_added / base_overridden) (R1.2)', async () => {
      await renderEditor();
      // base — an untouched platform field
      expect(
        screen.getByTestId('members-field-provenance-personal.last_name'),
      ).toHaveTextContent('Base');
      // base_overridden — a base field the tenant re-presents (still immovable, R1.5)
      expect(
        screen.getByTestId('members-field-provenance-personal.first_name'),
      ).toHaveTextContent('Base (overridden)');
      // tenant_added — a tenant-authored overlay field
      expect(
        screen.getByTestId('members-field-provenance-motor_brand'),
      ).toHaveTextContent('Tenant-added');
    });

    it('orders the unified list by (group.order, field.order, key) with no new position field (R1.3)', async () => {
      await renderEditor();
      // The wire order is motor_brand, last_name, first_name; the derived display order is
      // first_name (group 1 / order 1), last_name (group 1 / order 2), motor_brand (group 2).
      const rows = screen.getAllByTestId(/^members-field-row-/);
      const order = rows.map((r) => r.getAttribute('data-testid'));
      expect(order).toEqual([
        'members-field-row-personal.first_name',
        'members-field-row-personal.last_name',
        'members-field-row-motor_brand',
      ]);
    });

    it('still exposes the SINGLE field_overlay authoring sub-editor (one save path, R1.4)', async () => {
      await renderEditor();
      // The two-section presentation collapsed, but authoring remains ONE field_overlay object:
      // the fields + fixed_overrides sub-editor is still the single authoring door.
      expect(
        screen.getByTestId('sub-editor-field_overlay-fields-fixed_overrides'),
      ).toBeInTheDocument();
    });

    it('degrades to a "no resolved fields" note when the field list is empty', async () => {
      await renderEditor(allRows(), { fields: [], functional_groups: [] });
      expect(screen.getByTestId('members-field-provenance-empty')).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Group → field → attribute authoring hierarchy                    */
  /*  (Members config redesign Phase 3 step 11 — task 4.1, R4)         */
  /*                                                                   */
  /*  Change-With-Tests: the Field Overlay tab now LEADS with the      */
  /*  group → field → attribute hierarchy on the Phase 1 catalog —     */
  /*  functional groups (key/label/order) as sections, fields nested   */
  /*  within their group, per-field attributes on each field, in       */
  /*  DERIVED `(group.order, field.order, key)` order (no stored       */
  /*  position). Authoring is UNCHANGED — the single field_overlay     */
  /*  sub-editor still commits the one object (covered by save-once).  */
  /* ---------------------------------------------------------------- */
  describe('group → field → attribute authoring hierarchy (Phase 3 step 11, R4)', () => {
    it('renders the hierarchy on the Field Overlay tab (R4.1)', async () => {
      await renderEditor();
      expect(screen.getByTestId('members-group-field-hierarchy')).toBeInTheDocument();
      // Both defined catalog groups from the resolved config are sections.
      expect(screen.getByTestId('members-hierarchy-group-personal')).toBeInTheDocument();
      expect(screen.getByTestId('members-hierarchy-group-motor')).toBeInTheDocument();
    });

    it('nests each field under its functional group (R4.1/R4.2)', async () => {
      await renderEditor();
      // motor_brand is authored under the `motor` group; the base fields under `personal`.
      const motor = screen.getByTestId('members-hierarchy-group-motor');
      expect(
        within(motor).getByTestId('members-hierarchy-field-motor_brand'),
      ).toBeInTheDocument();
      const personal = screen.getByTestId('members-hierarchy-group-personal');
      expect(
        within(personal).getByTestId('members-hierarchy-field-personal.first_name'),
      ).toBeInTheDocument();
      expect(
        within(personal).getByTestId('members-hierarchy-field-personal.last_name'),
      ).toBeInTheDocument();
    });

    it('orders groups then fields by the DERIVED (group.order, field.order, key) rule (R4.2)', async () => {
      await renderEditor();
      // Groups: personal (order 1) before motor (order 2).
      const groups = screen
        .getAllByTestId(/^members-hierarchy-group-/)
        .map((n) => n.getAttribute('data-testid'));
      expect(groups).toEqual([
        'members-hierarchy-group-personal',
        'members-hierarchy-group-motor',
      ]);
      // Within personal: first_name (order 1) before last_name (order 2) — derived, not stored.
      const personal = screen.getByTestId('members-hierarchy-group-personal');
      const personalFields = within(personal)
        .getAllByTestId(/^members-hierarchy-field-/)
        .map((n) => n.getAttribute('data-testid'));
      expect(personalFields).toEqual([
        'members-hierarchy-field-personal.first_name',
        'members-hierarchy-field-personal.last_name',
      ]);
    });

    it('still authors through the SINGLE field_overlay sub-editor (one save path, R4.7)', async () => {
      await renderEditor();
      // The hierarchy is presentation; the one authoring door remains the field_overlay sub-editor.
      expect(
        screen.getByTestId('sub-editor-field_overlay-fields-fixed_overrides'),
      ).toBeInTheDocument();
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
  });

  describe('save-once (Property 8): exactly ONE request per param object', () => {
    it('editing then saving the functional-group catalog issues exactly one PUT', async () => {
      await renderEditor();
      // The functional-group sub-editor edits the SAME single field_overlay object; one Save =
      // one whole-object PUT (the save-once invariant that formerly rode the scope_dimensions
      // param now rides field_overlay, since scope_dimensions is no longer authored here).
      const groupEditor = screen.getByTestId('sub-editor-field_overlay-functional_groups');

      // Make an edit: change the first functional group's label (a text control).
      const groupRow = within(groupEditor).getByTestId('functional_groups-row-0');
      const labelInput = within(groupRow).getByLabelText('Label (English)') as HTMLInputElement;
      fireEvent.change(labelInput, { target: { value: 'Personal (edited)' } });

      // Save button becomes enabled once dirty.
      const saveBtn = within(groupEditor).getByRole('button', { name: 'Save' });
      await waitFor(() => expect(saveBtn).not.toBeDisabled(), { timeout: 5000 });
      fireEvent.click(saveBtn);

      await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
      // Exactly one request total (an existing tenant row → PUT/update, never create).
      expect(mockCreate).not.toHaveBeenCalled();
      // The WHOLE object was committed under the single field_overlay param (id 101).
      expect(mockUpdate).toHaveBeenCalledWith(
        101,
        expect.objectContaining({ value_type: 'json' }),
      );
    });

    it('an unauthored field_overlay creates the tenant row in exactly one request', async () => {
      // No existing rows → field_overlay is unauthored.
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
        expect.objectContaining({ scope: 'tenant', namespace: 'members', key: 'field_overlay', value_type: 'json' }),
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
      await waitFor(() => expect(saveBtn).not.toBeDisabled(), { timeout: 5000 });
      fireEvent.click(saveBtn);

      await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
      const savedValue = mockUpdate.mock.calls[0][1].value as any;
      const choices = savedValue.fields.motor_brand.choices;
      expect(choices).toEqual([
        { value: 'harley', label: { nl: 'Harley', en: 'Harley' }, roles: ['Members_CRUD'] },
      ]);
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Analytics role config REMOVED (members-analytics-role-removal)   */
  /*                                                                   */
  /*  The standalone analytics sub-editor AND the per-field `alias`    */
  /*  attribute that folded into `field_overlay.analytics` were        */
  /*  removed — superseded by the generic Dynamic Pivot Views          */
  /*  mechanism. The configurator authors only functional groups + the */
  /*  field overlay (scope attribute). The surviving save-once /       */
  /*  one-PUT behavior is asserted above; here we assert the analytics */
  /*  authoring surface is GONE.                                       */
  /* ---------------------------------------------------------------- */
  describe('analytics role config removed (members-analytics-role-removal)', () => {
    it('presents no analytics sub-editor and no per-field analytics role control', async () => {
      await renderEditor();
      // No standalone analytics sub-editor section.
      expect(
        screen.queryByTestId('sub-editor-field_overlay-analytics'),
      ).not.toBeInTheDocument();
      // No per-field "Analytics Role" alias control on any field entry.
      expect(screen.queryByLabelText('Analytics Role')).not.toBeInTheDocument();
      // No standalone jubilee / role / address-mapping controls remain.
      expect(screen.queryByLabelText('Every Nth year')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Cancellation date field')).not.toBeInTheDocument();
    });
    // The "save-once commits with NO analytics slice" assertion lives on the scope
    // save-once case above (`savedValue.analytics` is undefined there), so it is not
    // duplicated here.
  });
});

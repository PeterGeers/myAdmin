/**
 * Tests for the Members config editor — the group → field → attribute DRILL-DOWN integration
 * (Members config redesign Phase 3, task 4.9, rebuilt from the superseded slice-editor suite).
 *
 * The editor wires the drill-down together and owns the ONE save path. These assert the
 * integration seams (the per-tier behaviour is covered by the groups-table / fields-table /
 * field-modal / field-actions suites):
 *  - the projection STATUS banner renders from the module `config_status` (Phase 0 step 3);
 *  - the drill-down navigates groups table → (open group) → fields table → field modal, and back;
 *  - provenance from the resolved field-config GOVERNS the field modal's actions (R1.3 — delete vs
 *    reset/hide, never a badge);
 *  - every edit flows through the SINGLE save path: one Save → exactly one create/update request
 *    (Property 8 / R4.8), the real `saveMembersParameter` un-mocked.
 *
 * Uses the project's real i18n + test-utils render (the drill-down resolves shipped labels via the
 * `admin` namespace, so a stubbed translator would hide label behaviour).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, within, fireEvent, waitFor } from '../../../../test-utils';
import i18n from '../../../../i18n';
import type { Parameter } from '../../../../types/parameterTypes';
import type { FieldConfig } from '../../../../types/members';

/* ------------------------------------------------------------------ */
/*  Service mocks — the data edges; the real save-once primitive runs. */
/* ------------------------------------------------------------------ */
const mockGetParams = vi.fn();
const mockGetFieldConfig = vi.fn();
const mockCreate = vi.fn();
const mockUpdate = vi.fn();
// field_overlay is SAM-owned (`config#fields`): the save goes through the Members API write path,
// not parameterService. Capture it to COUNT and inspect the authored body.
const mockWriteFieldConfig = vi.fn();

vi.mock('../../../../services/membersConfigService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/membersConfigService')
  >('../../../../services/membersConfigService');
  return {
    ...actual,
    getMembersParameters: (...a: unknown[]) => mockGetParams(...a),
    getMembersFieldConfig: (...a: unknown[]) => mockGetFieldConfig(...a),
    // REAL save-once primitive — Property 8 (one save → one request) is asserted through it.
    saveMembersParameter: actual.saveMembersParameter,
  };
});

// The field_overlay save delegates to the Members API SAM write path (`PUT /members/config/fields`);
// mock it to COUNT requests. getFieldConfig stays real-ish (the editor fetch is mocked above).
vi.mock('../../../../services/membersApiService', () => ({
  writeFieldConfig: (...a: unknown[]) => mockWriteFieldConfig(...a),
  getFieldConfig: vi.fn(),
}));

// The scope_dimensions save (still Flask) delegates to parameterService; mock to COUNT requests.
vi.mock('../../../../services/parameterService', () => ({
  getParameters: vi.fn(),
  createParameter: (...a: unknown[]) => mockCreate(...a),
  updateParameter: (...a: unknown[]) => mockUpdate(...a),
  deleteParameter: vi.fn(),
  getParameterDefault: vi.fn(),
}));

import MembersConfigEditor from '../MembersConfigEditor';

/* ------------------------------------------------------------------ */
/*  Fixtures — one field_overlay row (id 202) + the resolved config.   */
/* ------------------------------------------------------------------ */
const overlayRow: Parameter = {
  id: 202,
  namespace: 'members',
  key: 'field_overlay',
  value: {
    functional_groups: [
      { key: 'personal', label_en: 'Personal', label_nl: 'Persoonlijk', order: 1 },
      { key: 'motor', label_en: 'Motorcycle', label_nl: 'Motor', order: 2 },
    ],
    fields: {
      motor_brand: { type: 'string', label_en: 'Motor brand', functional_group: 'motor', visible: true },
      region: {
        type: 'string',
        label_en: 'Region',
        functional_group: 'personal',
        scope: { enabled: true, values: ['A'] },
      },
    },
    fixed_overrides: {},
  },
  value_type: 'json',
  scope_origin: 'tenant',
  is_secret: false,
} as unknown as Parameter;

const FIELD_CONFIG: FieldConfig = {
  fields: [
    { key: 'motor_brand', functional_group: 'motor', provenance: 'tenant_added', type: 'string', label: { en: 'Motor brand', nl: 'Motormerk' } },
    { key: 'region', functional_group: 'personal', provenance: 'tenant_added', type: 'string', label: { en: 'Region', nl: 'Regio' } },
    { key: 'personal.first_name', functional_group: 'personal', provenance: 'base', type: 'string', label: { en: 'First name', nl: 'Voornaam' } },
  ],
  functional_groups: [
    { key: 'personal', order: 1 },
    { key: 'motor', order: 2 },
  ],
  config_status: { fields: '2026-10-12T09:00:00', scope: 3, mail: null },
  // The RAW stored config#fields overlay — the editor now SEEDS its one working object from THIS
  // (the same SAM row it writes back), not the retired Flask members.field_overlay param (spec 11
  // bugfix: GET/PUT symmetric so a save is loss-free).
  field_overlay: (overlayRow.value as Record<string, unknown>),
};

function seed(rows: Record<string, Parameter> = { field_overlay: overlayRow }, cfg: FieldConfig | null = FIELD_CONFIG) {
  // The editor seeds its working overlay from the SAM field-config's `field_overlay` (same row it
  // writes). The `rows` arg still carries the intended overlay for the call sites that vary it
  // (override / unauthored); project it onto cfg.field_overlay so those scenarios keep working.
  const seededOverlay = (rows.field_overlay?.value as Record<string, unknown>) ?? {};
  const cfgWithOverlay =
    cfg == null ? null : { ...cfg, field_overlay: seededOverlay };
  mockGetParams.mockResolvedValue(rows); // defensive: the editor must NOT call this anymore
  mockGetFieldConfig.mockResolvedValue(cfgWithOverlay);
  mockCreate.mockResolvedValue({ success: true });
  mockUpdate.mockResolvedValue({ success: true });
  // The SAM write is authoritative: it returns the authored row version (Requirement 13.2).
  mockWriteFieldConfig.mockResolvedValue({ success: true, configId: 'fields', version: '2026-10-12T10:00:00+00:00' });
}

async function renderEditor(
  rows: Record<string, Parameter> = { field_overlay: overlayRow },
  cfg: FieldConfig | null = FIELD_CONFIG,
) {
  seed(rows, cfg);
  i18n.changeLanguage('en');
  const utils = render(
    <I18nextProvider i18n={i18n}>
      <MembersConfigEditor tenant="t-1" />
    </I18nextProvider>,
  );
  await screen.findByTestId('members-config-editor');
  // wait for the async load() to settle (groups table rendered)
  await screen.findByTestId('members-groups-table');
  return utils;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('MembersConfigEditor — status banner', () => {
  it('renders the delivered/loaded status from the module config_status', async () => {
    await renderEditor();
    expect(screen.getByTestId('members-config-status')).toBeInTheDocument();
    expect(screen.getByTestId('members-config-status-fields-badge')).toHaveTextContent('Delivered');
    expect(screen.getByTestId('members-config-status-mail-badge')).toHaveTextContent('Not yet delivered');
  });

  it('hides the banner when the field-config fetch fails (null)', async () => {
    await renderEditor({ field_overlay: overlayRow }, null);
    expect(screen.queryByTestId('members-config-status')).not.toBeInTheDocument();
    // authoring still works — the groups table is present
    expect(screen.getByTestId('members-groups-table')).toBeInTheDocument();
  });
});

describe('MembersConfigEditor — drill-down navigation', () => {
  it('starts on the groups table and drills into a group\'s fields and back', async () => {
    await renderEditor();
    // groups table is the entry point
    expect(screen.getByTestId('members-groups-row-personal')).toBeInTheDocument();
    // open the group modal → Fields → fields table of `personal`
    fireEvent.click(screen.getByTestId('members-groups-row-personal'));
    fireEvent.click(screen.getByTestId('members-group-modal-fields-btn'));
    expect(await screen.findByTestId('members-fields-table-personal')).toBeInTheDocument();
    expect(screen.getByTestId('members-fields-row-region')).toBeInTheDocument();
    // back to the groups table
    fireEvent.click(screen.getByTestId('members-drilldown-back'));
    expect(screen.getByTestId('members-groups-table')).toBeInTheDocument();
  });

  it('opens the field modal from a field row with provenance-driven actions (R1.3)', async () => {
    await renderEditor();
    fireEvent.click(screen.getByTestId('members-groups-row-personal'));
    fireEvent.click(screen.getByTestId('members-group-modal-fields-btn'));
    fireEvent.click(await screen.findByTestId('members-fields-row-region'));
    // field modal open; region is tenant_added → the actions offer destructive Delete, not reset
    expect(screen.getByTestId('members-field-modal')).toBeInTheDocument();
    expect(screen.getByTestId('members-field-action-delete')).toBeInTheDocument();
    expect(screen.queryByTestId('members-field-action-reset')).not.toBeInTheDocument();
  });

  it('a base field offers reset/hide, never destructive delete (R1.3)', async () => {
    // personal.first_name is a base field in the resolved config; author an override entry so it
    // is editable in the overlay, then open it.
    const withOverride = {
      field_overlay: {
        ...overlayRow,
        value: {
          ...(overlayRow.value as Record<string, unknown>),
          fixed_overrides: {
            'personal.first_name': { functional_group: 'personal', label_en: 'First name' },
          },
        },
      } as unknown as Parameter,
    };
    await renderEditor(withOverride);
    fireEvent.click(screen.getByTestId('members-groups-row-personal'));
    fireEvent.click(screen.getByTestId('members-group-modal-fields-btn'));
    fireEvent.click(await screen.findByTestId('members-fields-row-personal.first_name'));
    // base → reset + hide, no destructive delete
    expect(screen.getByTestId('members-field-action-reset')).toBeInTheDocument();
    expect(screen.getByTestId('members-field-action-hide')).toBeInTheDocument();
    expect(screen.queryByTestId('members-field-action-delete')).not.toBeInTheDocument();
  });
});

describe('MembersConfigEditor — single save path (Property 8 / R4.8, SAM config#fields write — R13)', () => {
  it('one Save commits the WHOLE field_overlay in EXACTLY one SAM PUT (/members/config/fields)', async () => {
    await renderEditor();
    // Author an edit through the drill-down: add a new group.
    fireEvent.click(screen.getByTestId('members-groups-add-btn'));
    fireEvent.change(screen.getByLabelText('Group key'), { target: { value: 'address' } });
    fireEvent.click(screen.getByTestId('members-group-modal-save-btn'));

    // The Save button is now enabled (unsaved changes); click it.
    const save = screen.getByTestId('members-config-save');
    await waitFor(() => expect(save).not.toBeDisabled());
    fireEvent.click(save);

    // config#fields is SAM-owned: EXACTLY one SAM write (upsert — no Flask create/update split).
    await waitFor(() => expect(mockWriteFieldConfig).toHaveBeenCalledTimes(1));
    expect(mockCreate).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();
    // The whole object was committed as the config#fields body (fields/overrides/functional_groups).
    const saved = mockWriteFieldConfig.mock.calls[0][0] as Record<string, any>;
    expect(saved.functional_groups.some((g: any) => g.key === 'address')).toBe(true);
    expect(saved.fields.region).toBeTruthy();
  });

  it('an unauthored tenant authors the config#fields row in exactly one SAM PUT (upsert, no create/update split)', async () => {
    await renderEditor({}); // no existing row — SAM put_item upserts regardless
    fireEvent.click(screen.getByTestId('members-groups-add-btn'));
    fireEvent.change(screen.getByLabelText('Group key'), { target: { value: 'personal' } });
    fireEvent.click(screen.getByTestId('members-group-modal-save-btn'));

    const save = screen.getByTestId('members-config-save');
    await waitFor(() => expect(save).not.toBeDisabled());
    fireEvent.click(save);

    // Still exactly one SAM write — there is no "create vs update" distinction for a SAM upsert,
    // and no Flask parameter call is made for field_overlay anymore.
    await waitFor(() => expect(mockWriteFieldConfig).toHaveBeenCalledTimes(1));
    expect(mockCreate).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it('Save is disabled until there is an unsaved edit', async () => {
    await renderEditor();
    expect(screen.getByTestId('members-config-save')).toBeDisabled();
    expect(screen.queryByTestId('members-unsaved-indicator')).not.toBeInTheDocument();
  });
});

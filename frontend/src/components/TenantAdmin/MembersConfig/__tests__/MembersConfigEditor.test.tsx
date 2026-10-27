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
// config#fields is SAM-owned and now written by IDENTITY (spec 03, Phase 5): the save derives a
// Change-Op list and calls `applyFieldConfigChangeOps` (`PUT /members/config/fields` with `{ops}`).
// The whole-overlay `writeFieldConfig` writer was RETIRED (spec 03 task 5.2) and no longer exists.
// Capture the Change-Op seam to COUNT requests + inspect the ops.
const mockApplyChangeOps = vi.fn();

vi.mock('../../../../services/membersConfigService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/membersConfigService')
  >('../../../../services/membersConfigService');
  return {
    ...actual,
    getMembersParameters: (...a: unknown[]) => mockGetParams(...a),
    getMembersFieldConfig: (...a: unknown[]) => mockGetFieldConfig(...a),
    // REAL Change-Op save primitive — the identity-keyed write is asserted through it (it calls
    // the mocked `applyFieldConfigChangeOps` on the Members API below).
    saveFieldConfigChangeOps: actual.saveFieldConfigChangeOps,
  };
});

// The config#fields save delegates to the Members API Change-Op write path
// (`applyFieldConfigChangeOps` → `PUT /members/config/fields` with `{ops}`); mock it to COUNT
// requests + inspect the derived ops. getFieldConfig stays real-ish (the editor fetch is mocked above).
vi.mock('../../../../services/membersApiService', () => ({
  applyFieldConfigChangeOps: (...a: unknown[]) => mockApplyChangeOps(...a),
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
  // The SAM Change-Op write is authoritative: it returns the authored row version.
  mockApplyChangeOps.mockResolvedValue({ success: true, configId: 'fields', version: '2026-10-12T10:00:00+00:00' });
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

describe('MembersConfigEditor — Change-Op save path (spec 03 Phase 5 / task 5.1)', () => {
  it('one Save issues a Change-Op write by IDENTITY — set_group for the added group (no whole overlay)', async () => {
    await renderEditor();
    // Author an edit through the drill-down: add a new group (key + a label, the realistic flow).
    fireEvent.click(screen.getByTestId('members-groups-add-btn'));
    fireEvent.change(screen.getByLabelText('Group key'), { target: { value: 'address' } });
    fireEvent.change(screen.getByLabelText('Label (English)'), { target: { value: 'Address' } });
    fireEvent.click(screen.getByTestId('members-group-modal-save-btn'));

    // The Save button is now enabled (unsaved changes); click it.
    const save = screen.getByTestId('members-config-save');
    await waitFor(() => expect(save).not.toBeDisabled());
    fireEvent.click(save);

    // config#fields is written BY IDENTITY via the Change-Op path — EXACTLY one call, and the
    // retired whole-overlay writer is GONE (steering 39 — no whole catalog crosses the wire).
    await waitFor(() => expect(mockApplyChangeOps).toHaveBeenCalledTimes(1));
    expect(mockCreate).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();

    // The derived ops name the ADDED group by its bare identity (set_group), and carry NO
    // whole-catalog / `{group}.{key}` shape — the server owns placement.
    const ops = mockApplyChangeOps.mock.calls[0][0] as Array<Record<string, any>>;
    const addGroupOp = ops.find((o) => o.op === 'set_group' && o.group === 'address');
    expect(addGroupOp).toBeTruthy();
    // An unchanged group/field is NOT re-sent — only the edited identity.
    expect(ops.some((o) => o.op === 'set_group' && o.group === 'motor')).toBe(false);
  });

  it('an unauthored tenant authors by identity in a single Change-Op write (no whole-overlay body)', async () => {
    await renderEditor({}); // no existing row — the first Change-Op write creates the entry server-side
    fireEvent.click(screen.getByTestId('members-groups-add-btn'));
    // Author a GENUINELY NEW group (`address` is NOT in the seeded Flat_View catalog of
    // {personal, motor}). The editor now seeds its working buffer from the resolved Flat_View
    // (spec 03 bugfix — the 5.1↔5.3 seam), so re-adding an ALREADY-RESOLVED group (e.g. `personal`)
    // is correctly a no-op; a brand-new key is the real "author by identity" case this test pins.
    fireEvent.change(screen.getByLabelText('Group key'), { target: { value: 'address' } });
    fireEvent.change(screen.getByLabelText('Label (English)'), { target: { value: 'Address' } });
    fireEvent.click(screen.getByTestId('members-group-modal-save-btn'));

    const save = screen.getByTestId('members-config-save');
    await waitFor(() => expect(save).not.toBeDisabled());
    fireEvent.click(save);

    // Exactly one Change-Op write; the Flask parameter path is untouched (the retired whole-overlay
    // writer no longer exists to be called).
    await waitFor(() => expect(mockApplyChangeOps).toHaveBeenCalledTimes(1));
    expect(mockCreate).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();
    const ops = mockApplyChangeOps.mock.calls[0][0] as Array<Record<string, any>>;
    expect(ops.some((o) => o.op === 'set_group' && o.group === 'address')).toBe(true);
  });

  it('Save is disabled until there is an unsaved edit', async () => {
    await renderEditor();
    expect(screen.getByTestId('members-config-save')).toBeDisabled();
    expect(screen.queryByTestId('members-unsaved-indicator')).not.toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/*  Task 5.4 — no raw overlay shape CONSUMED + base-group edit persists */
/*  via Change-Op + the two named bugs, PROVEN end-to-end through the   */
/*  editor (the integration the unit/builder suites don't exercise).    */
/*  Design C3 + requirements R2/R3 + root-cause-analysis (blank-form +   */
/*  silent-no-op occurrences).                                          */
/* ------------------------------------------------------------------ */
describe('MembersConfigEditor — Change-Op integration (spec 03 task 5.4; design C3 / R2 / R3)', () => {
  /**
   * The RESOLVED field-config WITHOUT any `field_overlay` key — the real post-5.3 response shape
   * (task 5.3 stopped the server surfacing `field_overlay`; steering 39 guard). The editor must
   * seed its working buffer from the Flat_View (`fields` + `functional_groups`) and NOT depend on
   * consuming a raw `field_overlay`. `personal`/`motor` are PLATFORM BASE groups: present in the
   * resolved catalog, ABSENT from any tenant overlay (there is none).
   */
  const FIELD_CONFIG_NO_OVERLAY: FieldConfig = {
    fields: [
      { key: 'motor_brand', functional_group: 'motor', provenance: 'tenant_added', type: 'string', label: { en: 'Motor brand', nl: 'Motormerk' } },
      { key: 'personal.first_name', functional_group: 'personal', provenance: 'base', type: 'string', label: { en: 'First name', nl: 'Voornaam' } },
    ],
    functional_groups: [
      { key: 'personal', label: { en: 'Personal', nl: 'Persoonlijk' }, order: 1 },
      { key: 'motor', label: { en: 'Motorcycle', nl: 'Motor' }, order: 2 },
    ],
    config_status: { fields: '2026-10-12T09:00:00', scope: 3, mail: null },
    // NO `field_overlay` key — deliberately absent (the post-5.3 response shape).
  };

  /** Seed the editor directly with a resolved config (no `field_overlay` projection by `seed`). */
  async function renderWithResolvedConfig(cfg: FieldConfig) {
    mockGetParams.mockResolvedValue({});
    mockGetFieldConfig.mockResolvedValue(cfg);
    mockCreate.mockResolvedValue({ success: true });
    mockUpdate.mockResolvedValue({ success: true });
    mockApplyChangeOps.mockResolvedValue({
      success: true,
      configId: 'fields',
      version: '2026-10-12T10:00:00+00:00',
    });
    i18n.changeLanguage('en');
    render(
      <I18nextProvider i18n={i18n}>
        <MembersConfigEditor tenant="t-1" />
      </I18nextProvider>,
    );
    await screen.findByTestId('members-config-editor');
    await screen.findByTestId('members-groups-table');
  }

  it('renders the group catalog from the Flat_View when the response carries NO field_overlay (nothing raw consumed)', async () => {
    await renderWithResolvedConfig(FIELD_CONFIG_NO_OVERLAY);
    // The groups table is populated from the resolved `functional_groups` (the Flat_View), NOT from
    // a raw `field_overlay` the server no longer sends — the editor seeds its buffer from the flat
    // resolved view and never depends on the retired raw shape (R3 / steering 39).
    expect(screen.getByTestId('members-groups-row-personal')).toBeInTheDocument();
    expect(screen.getByTestId('members-groups-row-motor')).toBeInTheDocument();
    // Clean load → no write at all.
    expect(mockApplyChangeOps).not.toHaveBeenCalled();
    // Nothing dirty on load (the Flat_View seed is the baseline, not an edit).
    expect(screen.getByTestId('members-config-save')).toBeDisabled();
  });

  it('opening a BASE group whose entry is only in the Flat_View shows its seeded values, NOT a blank form (blank-base-group-form bug)', async () => {
    await renderWithResolvedConfig(FIELD_CONFIG_NO_OVERLAY);
    // Open the `motor` base group — it lives only in the resolved catalog (no overlay entry).
    fireEvent.click(screen.getByTestId('members-groups-row-motor'));
    const modal = await screen.findByTestId('members-group-modal');
    // The form is SEEDED from the resolved catalog (key + bilingual label + order), not blank — the
    // exact bug this spec fixes (editing a base group opened an empty edit form). Root-cause-analysis.
    expect((within(modal).getByLabelText('Group key') as HTMLInputElement).value).toBe('motor');
    expect((within(modal).getByLabelText('Label (English)') as HTMLInputElement).value).toBe('Motorcycle');
    expect((within(modal).getByLabelText('Label (Dutch)') as HTMLInputElement).value).toBe('Motor');
  });

  it('editing a BASE group persists as ONE set_group Change-Op by its key — materialize, NOT a silent no-op', async () => {
    await renderWithResolvedConfig(FIELD_CONFIG_NO_OVERLAY);
    // Open the base `personal` group (Flat_View-only) and change its order — the precise edit the
    // silent-no-op bug dropped on the floor (modal closed, nothing written, nothing saved).
    fireEvent.click(screen.getByTestId('members-groups-row-personal'));
    await screen.findByTestId('members-group-modal');
    fireEvent.change(screen.getByLabelText('Order'), { target: { value: '7' } });
    fireEvent.click(screen.getByTestId('members-group-modal-save-btn'));

    // The edit MATERIALIZED a real overlay change → the editor is dirty and Save enables (the edit
    // did NOT silently do nothing).
    const save = screen.getByTestId('members-config-save');
    await waitFor(() => expect(save).not.toBeDisabled());
    expect(screen.getByTestId('members-unsaved-indicator')).toBeInTheDocument();
    fireEvent.click(save);

    // Exactly ONE Change-Op write — no whole-overlay body, no Flask parameter path.
    await waitFor(() => expect(mockApplyChangeOps).toHaveBeenCalledTimes(1));
    expect(mockCreate).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();

    const ops = mockApplyChangeOps.mock.calls[0][0] as Array<Record<string, any>>;
    // The base group persists via a set_group op KEYED BY ITS GROUP KEY, carrying the changed order
    // (materialize — R4.1). The server owns storage placement; the client sends intent by identity.
    const setGroup = ops.find((o) => o.op === 'set_group' && o.group === 'personal');
    expect(setGroup).toBeTruthy();
    expect((setGroup!.attrs as Record<string, unknown>).order).toBe(7);
    // The UNTOUCHED base group is NEVER addressed — no sibling/catalog clobber (R1/R4.2, structural).
    expect(ops.some((o) => 'group' in o && o.group === 'motor')).toBe(false);
    // Nothing raw crosses the wire: no `field_overlay`, no dotted `{group}.{key}` key.
    const wire = JSON.stringify(ops);
    expect(wire).not.toContain('field_overlay');
    expect(wire).not.toContain('personal.');
  });
});

/**
 * PRESERVATION tests for the Application Form Builder overlay-seed bugfix
 * (spec `application-form-builder-overlay-seed`, task 2; Property 2 — Preservation).
 *
 * ## Why these exist (observation-first, BEFORE the fix)
 *
 * The fix (task 3.1) swaps `ApplicationFormBuilder.load()`'s overlay/baseline seed from
 * `cfg.field_overlay ?? {}` to `flatViewToOverlay(cfg)`. These tests pin the behaviors that must
 * NOT regress across that swap — so they are written against, and MUST PASS on, the CURRENT
 * (UNFIXED) code, and must still pass after the fix lands (task 3.3 re-runs them unchanged).
 *
 * They encode the design's Preservation Requirements (bugfix.md §3.1/§3.2/§3.3, design "Preservation
 * Requirements" / Property 2) over configs where the bug condition does NOT hold:
 *
 *  - P2.a  Unauthored config → per-field panels seed at PLATFORM DEFAULTS (required unchecked,
 *          format empty, off-form badge). Holds on unfixed code (overlay seeded `{}`) AND after the
 *          fix (`flatViewToOverlay` carries no application attrs for an unauthored field).
 *  - P2.b  Fresh unedited load is NOT dirty — Save disabled, no unsaved indicator. This is the
 *          phantom-diff guard: the fix changes the baseline SOURCE, so this proves working overlay
 *          and baseline stay seeded from the SAME value (no spurious change ops on a clean load).
 *  - P2.c  One edit → EXACTLY one `set_field_application` Change-Op for the touched field on Save.
 *  - P2.d  Form-shell seeding (public URL from `cfg.slug`, consent from `config#mail`) is unchanged
 *          — the fix touches ONLY the field-overlay seed, never `mailConfigToShellValues`.
 *  - P2.e  A failed field-config fetch (null) still renders the panels and NEVER blocks authoring.
 *
 * Mirrors the harness/mocks of the sibling `ApplicationFormBuilder.test.tsx` and the just-written
 * `ApplicationFormBuilder.overlaySeed.bug.test.tsx` (the `getMembersFieldConfig` mock, the real
 * `saveFieldConfigChangeOps`, the mocked `applyFieldConfigChangeOps` / `membersConfigApi`), per
 * steering 33-frontend-testing + the bugfix change-with-tests contract.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, fireEvent, waitFor } from '../../../../test-utils';
import i18n from '../../../../i18n';
import type { FieldConfig } from '../../../../types/members';

/* ------------------------------------------------------------------ */
/*  Service mocks — same edges the bug test + scaffold suite mock.     */
/*  The real saveFieldConfigChangeOps runs (one-save contract proven   */
/*  end to end through the service), delegating to the mocked API.     */
/* ------------------------------------------------------------------ */
const mockGetFieldConfig = vi.fn();
const mockApplyChangeOps = vi.fn();
const mockWriteMailConfig = vi.fn();

vi.mock('../../../../services/membersConfigService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/membersConfigService')
  >('../../../../services/membersConfigService');
  return {
    ...actual,
    getMembersFieldConfig: (...a: unknown[]) => mockGetFieldConfig(...a),
    saveFieldConfigChangeOps: actual.saveFieldConfigChangeOps,
    saveMembersMailConfig: actual.saveMembersMailConfig,
  };
});

vi.mock('../../../../services/membersApiService', () => ({
  applyFieldConfigChangeOps: (...a: unknown[]) => mockApplyChangeOps(...a),
  writeMailConfig: (...a: unknown[]) => mockWriteMailConfig(...a),
  getFieldConfig: vi.fn(),
}));

const mockListMembershipTypes = vi.fn();
const mockPublishApplicationForm = vi.fn();
const mockSetApplicationFormSlug = vi.fn();
const mockSetApplicationFormPrefix = vi.fn();
const mockGetLookAndFeel = vi.fn();
const mockSetLookAndFeel = vi.fn();
vi.mock('../../../../services/members/membersConfigApi', () => ({
  listMembershipTypes: (...a: unknown[]) => mockListMembershipTypes(...a),
  publishApplicationForm: (...a: unknown[]) => mockPublishApplicationForm(...a),
  setApplicationFormSlug: (...a: unknown[]) => mockSetApplicationFormSlug(...a),
  setApplicationFormPrefix: (...a: unknown[]) => mockSetApplicationFormPrefix(...a),
  getLookAndFeelSettings: (...a: unknown[]) => mockGetLookAndFeel(...a),
  setLookAndFeelSetting: (...a: unknown[]) => mockSetLookAndFeel(...a),
}));

import { ApplicationFormBuilder } from '../ApplicationFormBuilder';

/* ------------------------------------------------------------------ */
/*  Fixtures — NON-bug configs (bug condition does NOT hold):          */
/*  resolved configs whose fields[] carry NO authored application      */
/*  attrs, so defaults + one-save + form-shell seeding are observable  */
/*  and identical before/after the fix.                                */
/* ------------------------------------------------------------------ */

/**
 * An UNAUTHORED resolved config: a tenant-added `nickname` field with NO application attrs
 * (no application_visible / application_required / format / application_choices), a certified
 * mail_config carrying a consent notice, and a form slug. No `field_overlay` key — the current
 * SAM read never surfaces it. isBugCondition(this) === false (no field carries authored app attrs).
 */
const UNAUTHORED_CONFIG: FieldConfig = {
  slug: 'h-dcn',
  field_format_tokens: ['EMAIL', 'IBAN'],
  functional_groups: [{ key: 'personal', order: 1 }],
  fields: [
    {
      key: 'nickname',
      functional_group: 'personal',
      origin: 'variable',
      provenance: 'tenant_added',
      type: 'string',
      label: { en: 'Nickname', nl: 'Bijnaam' },
      // NO application_* attributes, NO format — a plain unauthored field.
    },
  ],
  config_status: { fields: '2026-10-21T09:00:00', scope: 1, mail: null },
  mail_config: {
    mail_enabled: true,
    mail_certified: true,
    mail_domain: 'h-dcn.nl',
    mail_local_part: 'noreply',
    consent_notice: {
      version: 'v20261021-090000',
      text: { en: 'I consent.', nl: 'Ik ga akkoord.' },
    },
  },
} as FieldConfig;

function seed(cfg: FieldConfig | null) {
  mockGetFieldConfig.mockResolvedValue(cfg);
  mockApplyChangeOps.mockResolvedValue({ success: true, configId: 'fields', version: 'v1' });
  mockWriteMailConfig.mockResolvedValue({ success: true, configId: 'mail', version: 'v1' });
  mockListMembershipTypes.mockResolvedValue([]);
  mockSetApplicationFormSlug.mockResolvedValue({ success: true, slug: 'h-dcn', version: 'v1' });
  mockSetApplicationFormPrefix.mockResolvedValue({ success: true, prefix: 'h-dcn', version: 'v1' });
  mockPublishApplicationForm.mockResolvedValue({ success: true, slug: 'h-dcn' });
  mockGetLookAndFeel.mockResolvedValue({ settings: {} });
  mockSetLookAndFeel.mockResolvedValue({ settings: {} });
}

async function renderBuilder(cfg: FieldConfig | null = UNAUTHORED_CONFIG) {
  seed(cfg);
  i18n.changeLanguage('en');
  const utils = render(
    <I18nextProvider i18n={i18n}>
      <ApplicationFormBuilder tenant="t-1" />
    </I18nextProvider>,
  );
  await screen.findByTestId('application-form-builder');
  return utils;
}

beforeEach(() => {
  vi.clearAllMocks();
});

/* ------------------------------------------------------------------ */
/*  P2.a — an unauthored field seeds its per-field panel at PLATFORM    */
/*  DEFAULTS (design Preservation Req / bugfix 3.1).                     */
/* ------------------------------------------------------------------ */
describe('ApplicationFormBuilder overlay-seed preservation — unauthored config seeds defaults (P2.a / 3.1)', () => {
  it('a field with no authored application attrs shows required UNCHECKED and format EMPTY', async () => {
    await renderBuilder(UNAUTHORED_CONFIG);

    // Open the unauthored field's per-field modal.
    fireEvent.click(screen.getByTestId('application-field-row-nickname'));
    expect(screen.getByTestId('application-field-modal')).toBeInTheDocument();

    // No authored application_required → the required toggle is at its platform default (unchecked).
    const requiredToggle = screen.getByTestId(
      'application-field-modal-required-toggle',
    ) as HTMLInputElement;
    expect(requiredToggle.checked).toBe(false);

    // No authored format → the format select is empty ("— none —").
    const formatSelect = screen.getByTestId(
      'application-field-modal-format-select',
    ) as HTMLSelectElement;
    expect(formatSelect.value).toBe('');
  });

  it('an unauthored field is OFF the form by default (off-form badge)', async () => {
    await renderBuilder(UNAUTHORED_CONFIG);
    // The read-only on-the-form badge reflects default-off for an unauthored field.
    expect(screen.getByTestId('application-field-status-nickname')).toHaveTextContent('off form');
  });
});

/* ------------------------------------------------------------------ */
/*  P2.b — a fresh unedited load is NOT dirty (the phantom-diff guard). */
/*  The fix changes the baseline SOURCE; this proves working overlay    */
/*  and baseline stay seeded from the SAME value (no spurious ops).      */
/* ------------------------------------------------------------------ */
describe('ApplicationFormBuilder overlay-seed preservation — fresh load not dirty (P2.b / 3.1)', () => {
  it('Save is DISABLED and there is NO unsaved indicator on a clean load', async () => {
    await renderBuilder(UNAUTHORED_CONFIG);
    // The Fields group's own Save (grouped per-group-save redesign) is disabled on a clean load.
    expect(screen.getByTestId('application-form-builder-fields-savebar-save')).toBeDisabled();
    expect(
      screen.queryByTestId('application-form-builder-unsaved-indicator'),
    ).not.toBeInTheDocument();
  });

  it('a clean load writes NOTHING — no Change-Op request fires without an edit', async () => {
    await renderBuilder(UNAUTHORED_CONFIG);
    await waitFor(() => expect(mockGetFieldConfig).toHaveBeenCalledTimes(1));
    expect(mockApplyChangeOps).not.toHaveBeenCalled();
  });
});

/* ------------------------------------------------------------------ */
/*  P2.c — one edit → EXACTLY one set_field_application Change-Op for    */
/*  the touched field (design Preservation Req / bugfix 3.2).            */
/* ------------------------------------------------------------------ */
describe('ApplicationFormBuilder overlay-seed preservation — one edit → one op (P2.c / 3.2)', () => {
  it('toggling one field on the form and saving yields exactly one set_field_application op for it', async () => {
    await renderBuilder(UNAUTHORED_CONFIG);

    // Open the field, toggle it on the form, then Save.
    fireEvent.click(screen.getByTestId('application-field-row-nickname'));
    fireEvent.click(screen.getByTestId('application-field-modal-on-form-toggle'));
    // The edit makes the Fields group dirty → its Save enables.
    await waitFor(() =>
      expect(screen.getByTestId('application-form-builder-fields-savebar-save')).toBeEnabled(),
    );
    fireEvent.click(screen.getByTestId('application-form-builder-fields-savebar-save'));

    // EXACTLY one Change-Op write, carrying a single set_field_application op for the edited
    // identity — no whole-overlay write, no phantom ops for untouched fields.
    await waitFor(() => expect(mockApplyChangeOps).toHaveBeenCalledTimes(1));
    const ops = mockApplyChangeOps.mock.calls[0][0] as Array<Record<string, any>>;
    const appOps = ops.filter((o) => o.op === 'set_field_application');
    expect(appOps).toHaveLength(1);
    expect(appOps[0].key).toBe('nickname');
    expect(appOps[0].attrs.application_visible).toBe(true);
  });
});

/* ------------------------------------------------------------------ */
/*  P2.d — form-shell seeding (public URL from cfg.slug, consent from   */
/*  config#mail) is UNCHANGED — the fix touches only the field-overlay  */
/*  seed, never mailConfigToShellValues (design Preservation / 3.3).    */
/* ------------------------------------------------------------------ */
describe('ApplicationFormBuilder overlay-seed preservation — form-shell seeding unchanged (P2.d / 3.3)', () => {
  it('seeds the public URL from the SAM cfg.slug', async () => {
    await renderBuilder(UNAUTHORED_CONFIG);
    // The public URL now renders in the Public-address group (derived from the stored slug).
    expect(screen.getByTestId('application-form-address-public-url')).toHaveTextContent(
      'https://h-dcn.jabaki.nl',
    );
    expect(screen.queryByTestId('application-form-address-no-url')).not.toBeInTheDocument();
  });

  it('seeds the consent notice text from config#mail', async () => {
    await renderBuilder(UNAUTHORED_CONFIG);
    const consentEn = screen.getByTestId('application-form-shell-consent-en') as HTMLTextAreaElement;
    const consentNl = screen.getByTestId('application-form-shell-consent-nl') as HTMLTextAreaElement;
    expect(consentEn.value).toBe('I consent.');
    expect(consentNl.value).toBe('Ik ga akkoord.');
  });

  it('shows "no public address yet" when cfg.slug is absent (SAM state, independent of the overlay seed)', async () => {
    await renderBuilder({ ...UNAUTHORED_CONFIG, slug: null });
    expect(screen.getByTestId('application-form-address-no-url')).toBeInTheDocument();
    expect(screen.queryByTestId('application-form-address-public-url')).not.toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/*  P2.e — a failed field-config fetch (null) still renders + never     */
/*  blocks authoring (design Preservation Req).                         */
/* ------------------------------------------------------------------ */
describe('ApplicationFormBuilder overlay-seed preservation — null config never blocks authoring (P2.e)', () => {
  it('renders the panels when the field-config fetch resolves to null', async () => {
    await renderBuilder(null);
    expect(screen.getByTestId('application-form-builder-group-fields')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-builder-panel-preview')).toBeInTheDocument();
    // A null config is not dirty — nothing to save, no phantom diff.
    expect(screen.getByTestId('application-form-builder-fields-savebar-save')).toBeDisabled();
  });
});

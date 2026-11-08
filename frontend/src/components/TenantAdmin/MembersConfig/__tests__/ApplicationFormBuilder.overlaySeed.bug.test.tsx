/**
 * Bug-condition EXPLORATION test for the Application Form Builder overlay-seed bugfix
 * (spec `application-form-builder-overlay-seed`, task 1; Property 1 — Bug Condition).
 *
 * ## The bug (FRONTEND-only)
 *
 * `ApplicationFormBuilder.load()` seeds its ONE working `field_overlay` object (and the diff
 * baseline) from `cfg.field_overlay`. Per steering 39 + the `FieldConfig` doc in
 * `types/members.ts`, the current SAM module read NO LONGER surfaces that raw key — it resolves
 * the overlay into each `fields[]` entry (carrying `application_required`, `format`,
 * `functional_group`, `origin`, …) and leaves `field_overlay` `undefined`. So the builder seeds
 * both the working overlay AND the baseline to `{}`, and every per-field modal panel falls back to
 * platform defaults even though the attributes are stored AND served inside `fields[]`.
 *
 * The sibling `MembersConfigEditor.load()` already solved this by seeding via
 * `flatViewToOverlay(cfg)` (reconstructing the authoring overlay from the resolved `fields[]`).
 * The fix (task 3.1) mirrors that single call here; this test ENCODES the expected post-fix
 * behavior.
 *
 * ## This test is EXPECTED TO FAIL on the UNFIXED code
 *
 * It renders the builder with a mocked `getMembersFieldConfig` returning the REALISTIC resolved
 * config the real GET serves — NO `field_overlay` key, and a tenant-added `iban` field
 * (`origin:'variable'`, `application_visible:true`, `application_required:true`,
 * `format:{checker:'IBAN'}`, `functional_group:'financial'`) plus a `payment_method` field with
 * `application_required:true`. It opens the IBAN field's per-field modal and asserts the required
 * toggle is CHECKED and the format select value is `IBAN`; it asserts `payment_method` required is
 * CHECKED too.
 *
 * On the UNFIXED builder the working overlay seeded from `cfg.field_overlay` (undefined) is `{}`,
 * so `ApplicationFieldModal` finds no authored entry → the required toggle is UNCHECKED and the
 * format select is EMPTY. The assertions FAIL — which is the SUCCESS case for an exploration test:
 * it demonstrates the bug (the builder shows stored/served attributes at defaults).
 *
 * Mirrors the existing `ApplicationFormBuilder.test.tsx` harness/mocks (the `getMembersFieldConfig`
 * mock, the SAM-plane membersConfigApi mock), per steering 33-frontend-testing + the bugfix
 * change-with-tests contract.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, fireEvent } from '../../../../test-utils';
import i18n from '../../../../i18n';
import type { FieldConfig } from '../../../../types/members';

/* ------------------------------------------------------------------ */
/*  Service mocks — same edges the scaffold suite mocks.               */
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
vi.mock('../../../../services/members/membersConfigApi', () => ({
  listMembershipTypes: (...a: unknown[]) => mockListMembershipTypes(...a),
  publishApplicationForm: (...a: unknown[]) => mockPublishApplicationForm(...a),
  setApplicationFormSlug: (...a: unknown[]) => mockSetApplicationFormSlug(...a),
  setApplicationFormPrefix: (...a: unknown[]) => mockSetApplicationFormPrefix(...a),
}));

import { ApplicationFormBuilder } from '../ApplicationFormBuilder';

/* ------------------------------------------------------------------ */
/*  Fixture — the REALISTIC resolved config the real GET serves:       */
/*  NO `field_overlay` key; the authored attributes live in fields[].  */
/* ------------------------------------------------------------------ */
const RESOLVED_WITHOUT_FIELD_OVERLAY: FieldConfig = {
  slug: 'h-dcn',
  field_format_tokens: ['EMAIL', 'IBAN'],
  functional_groups: [{ key: 'financial', order: 1 }],
  fields: [
    // Tenant-added IBAN field, on the form, REQUIRED, with an IBAN format check — exactly the
    // stored/served shape (`test_governance_projection` h-dcn config#fields row).
    {
      key: 'iban',
      functional_group: 'financial',
      origin: 'variable',
      provenance: 'tenant_added',
      type: 'string',
      label: { en: 'IBAN', nl: 'IBAN' },
      application_visible: true,
      application_required: true,
      format: { checker: 'IBAN' },
    },
    // A second tenant-added field also marked required on the form.
    {
      key: 'payment_method',
      functional_group: 'financial',
      origin: 'variable',
      provenance: 'tenant_added',
      type: 'string',
      label: { en: 'Payment method', nl: 'Betaalmethode' },
      application_visible: true,
      application_required: true,
    },
  ],
  config_status: { fields: '2026-10-21T09:00:00', scope: 1, mail: null },
  mail_config: {
    mail_enabled: true,
    mail_certified: true,
    mail_domain: 'h-dcn.nl',
    mail_local_part: 'noreply',
  },
  // NOTE: deliberately NO `field_overlay` key — this is what the current SAM module read returns.
} as FieldConfig;

function seed(cfg: FieldConfig) {
  mockGetFieldConfig.mockResolvedValue(cfg);
  mockApplyChangeOps.mockResolvedValue({ success: true, configId: 'fields', version: 'v1' });
  mockWriteMailConfig.mockResolvedValue({ success: true, configId: 'mail', version: 'v1' });
  mockListMembershipTypes.mockResolvedValue([]);
  mockSetApplicationFormSlug.mockResolvedValue({ success: true, slug: 'h-dcn', version: 'v1' });
  mockSetApplicationFormPrefix.mockResolvedValue({ success: true, prefix: 'h-dcn', version: 'v1' });
  mockPublishApplicationForm.mockResolvedValue({ success: true, slug: 'h-dcn' });
}

async function renderBuilder(cfg: FieldConfig = RESOLVED_WITHOUT_FIELD_OVERLAY) {
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
/*  Property 1 — Bug Condition: resolved application attributes seed    */
/*  the builder panels.  EXPECTED TO FAIL on unfixed code.              */
/* ------------------------------------------------------------------ */
describe('ApplicationFormBuilder — overlay-seed bug (Property 1, exploration — FAILS on unfixed code)', () => {
  it('seeds the IBAN per-field panel from the resolved fields[] — required CHECKED, format = IBAN', async () => {
    await renderBuilder();

    // Open the IBAN field's per-field modal (row-click opens the modal).
    fireEvent.click(screen.getByTestId('application-field-row-iban'));
    expect(screen.getByTestId('application-field-modal')).toBeInTheDocument();

    // The stored/served `application_required: true` must seed the required toggle CHECKED. On the
    // UNFIXED builder the overlay seeded from `cfg.field_overlay` (undefined) is `{}`, so the
    // modal finds no authored entry and the toggle is UNCHECKED → this assertion FAILS (bug proven).
    const requiredToggle = screen.getByTestId(
      'application-field-modal-required-toggle',
    ) as HTMLInputElement;
    expect(requiredToggle.checked).toBe(true);

    // The stored/served `format: { checker: 'IBAN' }` must seed the format select value to `IBAN`.
    // On the UNFIXED builder it is empty ("none") → this assertion FAILS (bug proven).
    const formatSelect = screen.getByTestId(
      'application-field-modal-format-select',
    ) as HTMLSelectElement;
    expect(formatSelect.value).toBe('IBAN');
  });

  it('seeds the payment_method per-field panel from the resolved fields[] — required CHECKED', async () => {
    await renderBuilder();

    fireEvent.click(screen.getByTestId('application-field-row-payment_method'));
    expect(screen.getByTestId('application-field-modal')).toBeInTheDocument();

    // `payment_method` carries `application_required: true` in the resolved config. On the UNFIXED
    // builder the seeded overlay is `{}`, so the required toggle is UNCHECKED → assertion FAILS.
    const requiredToggle = screen.getByTestId(
      'application-field-modal-required-toggle',
    ) as HTMLInputElement;
    expect(requiredToggle.checked).toBe(true);
  });
});

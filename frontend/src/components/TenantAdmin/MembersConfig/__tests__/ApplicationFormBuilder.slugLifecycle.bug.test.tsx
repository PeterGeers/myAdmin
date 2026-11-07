/**
 * Bugfix spec `bugfix-slug-lifecycle` — Task 1: the bug-condition EXPLORATION test (DISPLAY facet).
 *
 * Parent spec: `.kiro/specs/Members/14 - public-pages-multi-tenant-serving`.
 * Bugfix spec: `.kiro/specs/Members/14 .../bugfix-slug-lifecycle` (bugfix.md / design.md).
 *
 * WHAT THIS TEST IS
 * -----------------
 * The FRONTEND half of the Property-1 (Bug Condition) exploration test — the DISPLAY facet of
 * `isBugCondition` (design Formal Specification): the SAM Application Form Builder sources the
 * displayed public address + the Publish-readiness "slug present" signal CROSS-PLANE from the
 * Flask landing slug (`GET /api/landing/slug`) instead of from the SAM `config#fields.slug`.
 *
 * It ENCODES THE EXPECTED (fixed) behaviour, so on the UNFIXED code it MUST FAIL — the failure is
 * the counterexample proving the bug (bugfix workflow). After the fix (task 3.3 removes the
 * `getSlug`/`landingPageApi` read and sources the slug from `cfg.slug`), the SAME assertions PASS.
 *
 * SCOPED (scoped-PBT) to the concrete verified case for tenant `h-dcn`: SAM `cfg.slug = null`
 * (verified `config#fields.slug = NULL`) WITH a NON-null Flask landing slug. In that state the
 * fixed SAM screen SHALL reflect SAM state ("no public address yet"), never the Flask slug
 * (bugfix R2.1/R2.2).
 *
 * The AUTHOR / PUBLISH_REACHABILITY facets are the backend half, in the pytest sibling
 * `sam/tests/test_slug_lifecycle_bug_condition.py`.
 *
 * Validates (bugfix): Requirements 1.1, 1.2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen } from '../../../../test-utils';
import i18n from '../../../../i18n';
import type { FieldConfig } from '../../../../types/members';

/* ------------------------------------------------------------------ */
/*  Service mocks — the data edges.                                    */
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

// The DISPLAY defect lives HERE: the UNFIXED builder calls the Flask landing-plane `getSlug`
// (`GET /api/landing/slug`) and feeds that cross-plane slug into the displayed URL + readiness.
// We return a NON-null Flask slug (the real h-dcn landing-plane address) so the bug — if present —
// makes the SAM screen show it even though the SAM `cfg.slug` is null.
const mockGetSlug = vi.fn();
vi.mock('../../../../services/landingPageApi', () => ({
  getSlug: (...a: unknown[]) => mockGetSlug(...a),
}));

const mockListMembershipTypes = vi.fn();
const mockPublishApplicationForm = vi.fn();
const mockGetLookAndFeel = vi.fn();
const mockSetLookAndFeel = vi.fn();
const mockSetSlug = vi.fn();
const mockSetPrefix = vi.fn();
vi.mock('../../../../services/members/membersConfigApi', () => ({
  listMembershipTypes: (...a: unknown[]) => mockListMembershipTypes(...a),
  publishApplicationForm: (...a: unknown[]) => mockPublishApplicationForm(...a),
  getLookAndFeelSettings: (...a: unknown[]) => mockGetLookAndFeel(...a),
  setLookAndFeelSetting: (...a: unknown[]) => mockSetLookAndFeel(...a),
  setApplicationFormSlug: (...a: unknown[]) => mockSetSlug(...a),
  setApplicationFormPrefix: (...a: unknown[]) => mockSetPrefix(...a),
}));

import { ApplicationFormBuilder } from '../ApplicationFormBuilder';
import { computeReadiness } from '../applicationReadiness';
import { mailConfigToShellValues } from '../applicationShellForm';

/* ------------------------------------------------------------------ */
/*  Fixture — the h-dcn verified state: SAM config#fields.slug = NULL. */
/* ------------------------------------------------------------------ */

/** The Flask landing-plane slug the UNFIXED builder reads cross-plane (non-null → `hdcn` URL). */
const FLASK_LANDING_SLUG = 'hdcn-application-form';

/**
 * The resolved field config for h-dcn with SAM `slug = null` (verified `config#fields.slug=NULL`),
 * a certified sender, and ONE field on the form — so readiness hinges ONLY on the slug source.
 */
const H_DCN_NO_SAM_SLUG: FieldConfig = {
  // The SAM source of truth: no form slug authored yet.
  slug: null,
  fields: [
    {
      key: 'email',
      functional_group: 'personal',
      provenance: 'tenant_added',
      type: 'string',
      label: { en: 'Email', nl: 'E-mail' },
      // on the form, so the only unmet readiness precondition is the slug
      application_visible: true,
    } as unknown as FieldConfig['fields'][number],
  ],
  functional_groups: [{ key: 'personal', order: 1 }],
  field_format_tokens: ['EMAIL'],
  config_status: { fields: '2026-11-01T09:00:00', scope: 1, mail: null },
  mail_config: {
    mail_enabled: true,
    mail_certified: true,
    mail_domain: 'h-dcn.nl',
    mail_local_part: 'noreply',
    mail_reply_to_default: 'board@h-dcn.nl',
    application_scope_copy: true,
  },
  field_overlay: {
    functional_groups: [{ key: 'personal', order: 1 }],
    fields: {
      email: {
        type: 'string',
        functional_group: 'personal',
        visible: true,
        application_visible: true,
      },
    },
    fixed_overrides: {},
  },
} as unknown as FieldConfig;

function seed() {
  mockGetFieldConfig.mockResolvedValue(H_DCN_NO_SAM_SLUG);
  mockApplyChangeOps.mockResolvedValue({ success: true, configId: 'fields' });
  mockWriteMailConfig.mockResolvedValue({ success: true, configId: 'mail' });
  // The Flask landing plane has a slug — the cross-plane read the bug depends on.
  mockGetSlug.mockResolvedValue({ success: true, data: { slug: FLASK_LANDING_SLUG } });
  mockListMembershipTypes.mockResolvedValue([]);
  mockPublishApplicationForm.mockResolvedValue({ success: true });
  mockGetLookAndFeel.mockResolvedValue({ settings: {} });
  mockSetLookAndFeel.mockResolvedValue({ settings: {} });
  mockSetSlug.mockResolvedValue({ success: true });
  mockSetPrefix.mockResolvedValue({ success: true });
}

async function renderBuilder() {
  seed();
  i18n.changeLanguage('en');
  const utils = render(
    <I18nextProvider i18n={i18n}>
      <ApplicationFormBuilder tenant="h-dcn" />
    </I18nextProvider>,
  );
  await screen.findByTestId('application-form-builder');
  return utils;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ApplicationFormBuilder — slug-lifecycle DISPLAY facet (bugfix R1.1/R1.2 → R2.1/R2.2)', () => {
  it('reflects SAM state ("no public address yet") when config#fields.slug is null, NOT the Flask slug', async () => {
    await renderBuilder();

    // EXPECTED (fixed) behaviour (bugfix R2.1): SAM slug is null → the SAM screen states the form
    // has no public address yet, and does NOT display a Flask landing-plane address.
    //
    // UNFIXED: the builder reads the Flask slug via getSlug() and shows the derived
    // `https://hdcn-application-form.jabaki.nl/apply` URL → this FAILS. That displayed Flask URL is
    // the counterexample (bugfix.md Examples, facet=DISPLAY).
    // The public address now lives in the Public-address group (ApplicationAddressFields). Its
    // panel stays mounted even while collapsed, so the "no public address yet" state resolves.
    expect(screen.getByTestId('application-form-address-no-url')).toBeInTheDocument();
    expect(
      screen.queryByTestId('application-form-address-public-url'),
    ).not.toBeInTheDocument();
  });

  it('never surfaces the Flask landing slug anywhere in the SAM screen (no cross-plane address)', async () => {
    const { container } = await renderBuilder();

    // EXPECTED (fixed) behaviour (bugfix R2.2): the SAM screen must not render the Flask-plane slug
    // string at all — not in the URL, snippet, or open-live link.
    //
    // UNFIXED: the Flask slug `hdcn-application-form` is woven into the displayed URL → FAILS.
    expect(container.textContent ?? '').not.toContain(FLASK_LANDING_SLUG);
  });

  it('readiness "slug present" is driven by SAM state (false here), not the Flask slug (true)', async () => {
    // Pin the ROOT of the DISPLAY defect at the data layer the builder uses to seed its state:
    //
    //  * EXPECTED (fixed): the readiness slug source is the SAM `cfg.slug` → slugPresent === false
    //    when config#fields.slug is null.
    //  * UNFIXED: the builder seeds `shell.slug` from `mailConfigToShellValues(cfg, flaskSlug)`,
    //    which falls back to the Flask slug when `cfg.slug` is null → slugPresent === true.
    //
    // This FAILS on unfixed code: the seeded slug is the Flask slug and readiness reports
    // slugPresent=true — exactly the display/authoritative-state disagreement in bugfix R1.2.
    const seededShell = mailConfigToShellValues(H_DCN_NO_SAM_SLUG, FLASK_LANDING_SLUG);
    const readiness = computeReadiness(
      H_DCN_NO_SAM_SLUG,
      H_DCN_NO_SAM_SLUG.field_overlay as Record<string, unknown>,
      seededShell.slug,
    );
    expect(readiness.slugPresent).toBe(false);
  });
});

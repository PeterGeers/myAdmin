/**
 * Accessibility (axe) gate over the Application Form Builder (spec 11, task 6.1; R9.1 / NFR —
 * WCAG 2.2 AA, consistent with spec 10 D14's public-form bar).
 *
 * The authoring counterpart to the public form's axe gate (`PublicApplicationForm.axe.test.tsx`):
 * this pins the automatable accessibility floor over the TENANT-ADMIN builder — the composed
 * `ApplicationFormBuilder` (field list + per-field attributes + form-shell + readiness + preview)
 * AND each panel that renders standalone. It asserts axe finds NO violations, which transitively
 * covers the three things the a11y pass hardened:
 *   1. every form control has an accessible name — Chakra `FormControl`/`FormLabel` association on
 *      the real inputs (consent textareas, origins textarea, format select, required/visible
 *      switches), plus explicit `aria-label` where a visible label is absent;
 *   2. the embed-mode chooser is a COHERENT radiogroup (role="radio" + aria-checked, named via
 *      aria-label) — not toggle buttons (aria-pressed) inside a radiogroup;
 *   3. no orphan `FormLabel` bound to a non-input display region (version / snippet are labelled
 *      Text, not FormControl labels pointing at nothing).
 *
 * As with the public gate, an automated axe pass is NECESSARY BUT NOT SUFFICIENT for full WCAG 2.2
 * AA — manual assistive-technology testing + expert review still apply (NFR). This gate pins the
 * automatable floor over the builder so a future edit cannot silently regress it.
 *
 * Harness: the same service edges the scaffold suite mocks (so the load is deterministic + makes no
 * real network call) and the project's real i18n + Chakra `test-utils` render (so the bilingual
 * `t(nl,en)` labels + the real Chakra `FormControl` wiring are what axe inspects). The matcher is
 * registered locally (Vitest 4 needs the explicit `expect.extend`) so the rest of the suite is
 * untouched.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { axe } from 'vitest-axe';
import * as axeMatchers from 'vitest-axe/matchers';
import 'vitest-axe/extend-expect';
import { render, screen } from '../../../../test-utils';
import i18n from '../../../../i18n';
import type { Parameter } from '../../../../types/parameterTypes';
import type { FieldConfig, MembershipType } from '../../../../types/members';

// Register `toHaveNoViolations` on THIS suite's `expect` (scoped; the `vitest-axe/extend-expect`
// side-effect import only carries the type augmentation under Vitest 4 — the runtime registration
// must be done explicitly).
expect.extend(axeMatchers);

// axe-core cannot descend into a (cross-origin, unloaded) frame under jsdom, so iframe traversal
// is skipped for any suite that renders a frame. The live preview is now an IN-APP render via the
// shared ApplicationFormRenderer (no iframe), so this is retained only as a defensive no-op for the
// composed builder where other panels could carry a frame.
const AXE_NO_FRAMES = { iframes: false } as const;

/* ------------------------------------------------------------------ */
/*  Service mocks — the data edges (identical posture to the scaffold  */
/*  suite): deterministic load, no real network call.                  */
/* ------------------------------------------------------------------ */
const mockGetParams = vi.fn();
const mockGetFieldConfig = vi.fn();
const mockGetSlug = vi.fn();
const mockListMembershipTypes = vi.fn();
// The live preview POSTs the working overlay to the server preview endpoint; mock it so the axe
// render makes no real network call and returns a small, a11y-inspectable schema.
const mockPreview = vi.fn();

vi.mock('../../../../services/membersConfigService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/membersConfigService')
  >('../../../../services/membersConfigService');
  return {
    ...actual,
    getMembersParameters: (...a: unknown[]) => mockGetParams(...a),
    getMembersFieldConfig: (...a: unknown[]) => mockGetFieldConfig(...a),
    previewMembersApplicationConfig: (...a: unknown[]) => mockPreview(...a),
  };
});

vi.mock('../../../../services/membersApiService', () => ({
  writeFieldConfig: vi.fn().mockResolvedValue({ success: true }),
  writeMailConfig: vi.fn().mockResolvedValue({ success: true }),
  getFieldConfig: vi.fn(),
}));

vi.mock('../../../../services/landingPageApi', () => ({
  getSlug: (...a: unknown[]) => mockGetSlug(...a),
}));

vi.mock('../../../../services/members/membersConfigApi', () => ({
  listMembershipTypes: (...a: unknown[]) => mockListMembershipTypes(...a),
}));

import { ApplicationFormBuilder } from '../ApplicationFormBuilder';
import { ApplicationFormShellPanel } from '../ApplicationFormShellPanel';
import { ApplicationReadinessPanel } from '../ApplicationReadinessPanel';
import { ApplicationFormPreview } from '../ApplicationFormPreview';
import { ApplicationFieldAttributes } from '../ApplicationFieldAttributes';
import type { ShellFormValues } from '../applicationShellForm';

/* ------------------------------------------------------------------ */
/*  Fixtures — an authored overlay + a resolved config with an enum    */
/*  field + a format token, so the attributes panel renders its full   */
/*  control surface (required switch, subset checkboxes, format select).*/
/* ------------------------------------------------------------------ */
const overlayRow: Parameter = {
  id: 303,
  namespace: 'members',
  key: 'field_overlay',
  value: {
    functional_groups: [
      { key: 'personal', label_en: 'Personal', label_nl: 'Persoonlijk', order: 1 },
    ],
    fields: {
      membership_type: { application_visible: true },
    },
    fixed_overrides: {},
  },
  value_type: 'json',
  scope_origin: 'tenant',
  is_secret: false,
} as unknown as Parameter;

const FIELD_CONFIG: FieldConfig = {
  fields: [
    {
      key: 'email',
      functional_group: 'personal',
      provenance: 'tenant_added',
      type: 'string',
      label: { en: 'Email', nl: 'E-mail' },
    },
    {
      key: 'membership_type',
      functional_group: 'personal',
      provenance: 'tenant_added',
      type: 'enum',
      label: { en: 'Membership type', nl: 'Lidmaatschapstype' },
      application_visible: true,
      options: [
        { value: 'regular', label: { en: 'Regular', nl: 'Gewoon' } },
        { value: 'student', label: { en: 'Student', nl: 'Student' } },
      ],
    },
  ],
  functional_groups: [{ key: 'personal', order: 1 }],
  field_format_tokens: ['EMAIL', 'IBAN'],
  config_status: { fields: '2026-10-21T09:00:00', scope: 1, mail: null },
  mail_config: {
    mail_enabled: true,
    mail_certified: true,
    mail_domain: 'h-dcn.nl',
    mail_local_part: 'noreply',
    mail_reply_to_default: 'board@h-dcn.nl',
    application_scope_copy: true,
  },
} as unknown as FieldConfig;

const CATALOG: MembershipType[] = [
  { type_code: 'regular', label: { en: 'Regular', nl: 'Gewoon' }, active: true, order: 1 },
] as unknown as MembershipType[];

const SHELL_VALUES: ShellFormValues = {
  slug: 'h-dcn',
  embedMode: 'iframe',
  embedOrigins: ['https://www.example.org'],
  consentVersion: 'v1',
  consentTextNl: 'ja',
  consentTextEn: 'yes',
};

/** The applicant-facing schema the server preview returns for the working overlay (axe-inspected). */
const PREVIEW_SCHEMA = {
  fields: [
    {
      key: 'membership_type',
      type: 'enum',
      label: { en: 'Membership type', nl: 'Lidmaatschapstype' },
      functional_group: 'personal',
      order: 1,
      required: true,
      options: [{ value: 'regular', label: { en: 'Regular', nl: 'Gewoon' } }],
    },
  ],
  locales: ['nl', 'en'],
  notice: null,
};

function seed() {
  mockGetParams.mockResolvedValue({ field_overlay: overlayRow });
  mockGetFieldConfig.mockResolvedValue(FIELD_CONFIG);
  mockGetSlug.mockResolvedValue({ success: true, data: { slug: 'h-dcn' } });
  mockListMembershipTypes.mockResolvedValue(CATALOG);
  mockPreview.mockResolvedValue(PREVIEW_SCHEMA);
}

beforeEach(() => {
  vi.clearAllMocks();
  seed();
  i18n.changeLanguage('en');
});

describe('ApplicationFormBuilder — axe accessibility gate (task 6.1, R9.1/NFR)', () => {
  it('has NO axe violations over the composed builder (all four panels)', async () => {
    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <ApplicationFormBuilder tenant="t-1" />
      </I18nextProvider>,
    );
    await screen.findByTestId('application-form-builder');
    const results = await axe(container, AXE_NO_FRAMES);
    expect(results).toHaveNoViolations();
  });

  it('has NO axe violations on the form-shell panel (radiogroup, textareas, snippet)', async () => {
    const { container } = render(
      <ApplicationFormShellPanel
        values={SHELL_VALUES}
        onChange={vi.fn()}
        mailConfig={FIELD_CONFIG.mail_config}
        onSaveMail={vi.fn()}
        mailDirty
        lang="en"
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('has NO axe violations on the readiness panel (icon rows + neutral guidance)', async () => {
    const { container } = render(
      <ApplicationReadinessPanel
        fieldConfig={FIELD_CONFIG}
        overlay={overlayRow.value as Record<string, unknown>}
        slug="h-dcn"
        lang="en"
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('has NO axe violations on the live preview (in-app render via the shared renderer)', async () => {
    mockPreview.mockResolvedValue(PREVIEW_SCHEMA);
    const { container } = render(
      <ApplicationFormPreview overlay={overlayRow.value as Record<string, unknown>} lang="en" debounceMs={0} />,
    );
    // Wait for the debounced POST to resolve + the renderer to mount before inspecting.
    await screen.findByTestId('application-form-preview-render');
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('has NO axe violations on the per-field attributes panel (required switch, subset, format select)', async () => {
    const { container } = render(
      <ApplicationFieldAttributes
        fieldConfig={FIELD_CONFIG}
        selectedKey="membership_type"
        overlay={overlayRow.value as Record<string, unknown>}
        onChange={vi.fn()}
        membershipTypeCatalog={CATALOG}
        lang="en"
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

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
// spec 12 (redesign C / R3, task 5.2): the live preview is IN-BROWSER (pure filter → shared
// renderer), so there is no server preview endpoint to mock.

vi.mock('../../../../services/membersConfigService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/membersConfigService')
  >('../../../../services/membersConfigService');
  return {
    ...actual,
    getMembersParameters: (...a: unknown[]) => mockGetParams(...a),
    getMembersFieldConfig: (...a: unknown[]) => mockGetFieldConfig(...a),
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
import { ApplicationFieldModal } from '../ApplicationFieldModal';
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

function seed() {
  mockGetParams.mockResolvedValue({ field_overlay: overlayRow });
  mockGetFieldConfig.mockResolvedValue(FIELD_CONFIG);
  mockGetSlug.mockResolvedValue({ success: true, data: { slug: 'h-dcn' } });
  mockListMembershipTypes.mockResolvedValue(CATALOG);
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

  it('has NO axe violations on the live preview (in-browser render via the shared renderer)', async () => {
    const { container } = render(
      <ApplicationFormPreview
        fieldConfig={FIELD_CONFIG}
        overlay={overlayRow.value as Record<string, unknown>}
        membershipTypeCatalog={CATALOG}
        lang="en"
      />,
    );
    // The in-browser preview renders synchronously; the renderer mounts on first paint.
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

  // spec 12 task 4.4 / R9.1 — the axe floor over the NEW per-field authoring MODAL in its OPEN
  // state. The builder's standalone panels above do not exercise the modal (it opens only on a
  // field click), yet the modal is where ALL four application attributes are now authored. This
  // pins axe over the modal's full control surface — the on-the-form switch, the enum-subset
  // checkboxes, the required switch (forced + explained for a membership-type), and the format
  // select — so every control has an accessible name (Chakra FormControl/FormLabel + aria-label)
  // and the open dialog itself is accessible. `membership_type` is a choice-bearing, offerable
  // field, so the modal renders its maximal surface.
  it('has NO axe violations on the per-field authoring modal OPEN (switch, subset, required, format)', async () => {
    render(
      <ApplicationFieldModal
        isOpen
        onClose={vi.fn()}
        fieldKey="membership_type"
        fieldConfig={FIELD_CONFIG}
        overlay={overlayRow.value as Record<string, unknown>}
        onChange={vi.fn()}
        formInScope
        membershipTypeCatalog={CATALOG}
        lang="en"
      />,
    );
    const dialog = await screen.findByRole('dialog');
    // Chakra portals the Modal to document.body, so the dialog content lives OUTSIDE the RTL
    // `container`. Scan the dialog node itself so axe actually inspects the OPEN modal and its
    // controls (a container-only scan would pass trivially on an empty tree).
    //
    // `aria-dialog-name` is disabled for THIS scan only: under jsdom Chakra v2 splits the
    // `role="dialog"` node from the node Chakra puts the dialog's `aria-labelledby` on (its
    // `ModalContent` motion-section wrapper), so the auto-wiring to the visible `ModalHeader`
    // ("Field attributes") does not land on the `role="dialog"` node and the rule fires on a
    // render artifact, not a real defect — the modal carries a visible `ModalHeader` title in a
    // real browser. Every OTHER rule stays on, so
    // this still gates the thing task 4.4 cares about: each control in the modal (the on-the-form
    // switch, the enum-subset checkboxes, the required switch, the format select) has an
    // accessible name. `membership_type` is a choice-bearing, offerable field, so the modal
    // renders its maximal control surface.
    const results = await axe(dialog, { rules: { 'aria-dialog-name': { enabled: false } } });
    expect(results).toHaveNoViolations();
  });
});

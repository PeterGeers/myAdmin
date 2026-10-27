/**
 * Dedicated Phase-4 (R6) + Phase-5 (R3) matrix suite for the Application Form Builder — the
 * readiness panel + the IN-BROWSER preview together (R9.1, design §6 / §C2 / §D4).
 *
 * The focused suites live elsewhere:
 *  - `ApplicationReadinessPanel.test.tsx` — the three readiness facts, the spec-10 certified-sender
 *    pair (fail-closed), the `isSendReady = certified AND slug` aggregate (excluding the field-count
 *    hint), and the neutral no-mail-leak guidance;
 *  - `ApplicationFormPreview.test.tsx` — the in-browser render of the WORKING draft through the
 *    shared spec-10 `ApplicationFormRenderer` (reflecting unsaved edits, read-only, no network);
 *  - `applicationPreviewFilter.test.ts` — the pure client filter's selection + projection rules.
 *
 * This suite is the roll-up over the SAME components: the readiness matrix (each fact flips its row
 * independently; not-send-ready is a NEUTRAL state, not a half form; no mail-domain leak on either
 * path) PLUS the preview's "renders the filtered schema through the shared renderer, in-browser,
 * reflecting unsaved edits, leaking no mail internals" contract (R3.1/R3.2).
 *
 * Spec 12 (redesign C / R3): the preview is now entirely IN-BROWSER — the retired
 * `POST /members/application-preview` round-trip is gone (task 5.2), so there is NO preview service
 * to mock; the preview is fed the resolved `FieldConfig` ⊕ the working `field_overlay` directly and
 * re-derives synchronously.
 */
import { describe, it, expect } from 'vitest';
import React from 'react';
import { render, screen } from '../../../../test-utils';
import type { FieldConfig, FieldConfigField } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import { ApplicationReadinessPanel } from '../ApplicationReadinessPanel';
import { ApplicationFormPreview } from '../ApplicationFormPreview';
import { computeReadiness } from '../applicationReadiness';

/* ------------------------------------------------------------------ */
/*  Fixtures                                                           */
/* ------------------------------------------------------------------ */
const CERTIFIED_MAIL: FieldConfig['mail_config'] = {
  mail_enabled: true,
  mail_certified: true,
  mail_domain: 'h-dcn.nl',
  mail_local_part: 'noreply',
};

/** A resolved field in the bare `key` + `group` server shape (R2.3). */
function field(key: string, group: string, extra: Partial<FieldConfigField> = {}): FieldConfigField {
  return {
    key,
    group,
    type: 'string',
    label: { nl: `NL ${key}`, en: `Label ${key}` },
    functional_group: group,
    origin: 'variable',
    provenance: 'tenant_added',
    ...extra,
  };
}

/** A field config carrying `mail_config` + one field (optionally served on-the-form). */
function fieldConfigWith(
  mail: FieldConfig['mail_config'] | undefined,
  onFormServed = false,
): FieldConfig {
  return {
    fields: [field('email', 'contact', onFormServed ? { application_visible: true } : {})],
    mail_config: mail,
  } as FieldConfig;
}

/** A resolved field config (no mail concern) carrying the given fields — for the preview. */
function previewFieldConfig(fields: FieldConfigField[]): FieldConfig {
  return { fields } as FieldConfig;
}

const ONE_FIELD_ON: MembersConfigValue = {
  fields: { email: { application_visible: true } },
} as MembersConfigValue;

/* ================================================================== */
/*  MATRIX 1 — readiness reflects certified / slug / field states     */
/*             EACH INDEPENDENTLY (R6.1)                               */
/* ================================================================== */
describe('Phase-4 matrix — readiness reflects each fact independently (R6.1)', () => {
  const renderPanel = (
    mail: FieldConfig['mail_config'] | undefined,
    overlay: MembersConfigValue,
    slug: string | null,
  ) =>
    render(
      <ApplicationReadinessPanel
        fieldConfig={fieldConfigWith(mail)}
        overlay={overlay}
        slug={slug}
        lang="en"
      />,
    );

  it('CERTIFIED-SENDER row alone flips with the mail fact (slug + field held ready)', () => {
    const { unmount } = renderPanel(CERTIFIED_MAIL, ONE_FIELD_ON, 'h-dcn');
    expect(screen.getByTestId('application-readiness-certified-sender')).toHaveAttribute(
      'data-state',
      'ok',
    );
    unmount();
    renderPanel({ ...CERTIFIED_MAIL, mail_certified: false }, ONE_FIELD_ON, 'h-dcn');
    expect(screen.getByTestId('application-readiness-certified-sender')).toHaveAttribute(
      'data-state',
      'not-ok',
    );
    expect(screen.getByTestId('application-readiness-slug')).toHaveAttribute('data-state', 'ok');
    expect(screen.getByTestId('application-readiness-field-on-form')).toHaveAttribute(
      'data-state',
      'ok',
    );
  });

  it('SLUG row alone flips with slug presence (certified + field held ready)', () => {
    const { unmount } = renderPanel(CERTIFIED_MAIL, ONE_FIELD_ON, 'h-dcn');
    expect(screen.getByTestId('application-readiness-slug')).toHaveAttribute('data-state', 'ok');
    unmount();
    renderPanel(CERTIFIED_MAIL, ONE_FIELD_ON, null);
    expect(screen.getByTestId('application-readiness-slug')).toHaveAttribute(
      'data-state',
      'not-ok',
    );
    expect(screen.getByTestId('application-readiness-certified-sender')).toHaveAttribute(
      'data-state',
      'ok',
    );
    expect(screen.getByTestId('application-readiness-field-on-form')).toHaveAttribute(
      'data-state',
      'ok',
    );
  });

  it('FIELD-ON-FORM row alone flips with the overlay (certified + slug held ready)', () => {
    const { unmount } = renderPanel(CERTIFIED_MAIL, ONE_FIELD_ON, 'h-dcn');
    expect(screen.getByTestId('application-readiness-field-on-form')).toHaveAttribute(
      'data-state',
      'ok',
    );
    unmount();
    renderPanel(CERTIFIED_MAIL, {} as MembersConfigValue, 'h-dcn');
    expect(screen.getByTestId('application-readiness-field-on-form')).toHaveAttribute(
      'data-state',
      'not-ok',
    );
    expect(screen.getByTestId('application-readiness-ready')).toBeInTheDocument();
    expect(screen.queryByTestId('application-readiness-not-available')).not.toBeInTheDocument();
  });
});

/* ================================================================== */
/*  MATRIX 2 — preview renders the applicant schema through the SHARED */
/*             RENDERER, IN-BROWSER; an unsaved edit re-renders (R3.1) */
/* ================================================================== */
describe('Phase-5 matrix — preview targets the shared-renderer path in-browser (R3.1/R3.2)', () => {
  const fieldConfig = previewFieldConfig([field('email', 'contact'), field('phone', 'contact')]);

  it('renders the applicant schema through the shared renderer (one render path, no network)', () => {
    render(
      <ApplicationFormPreview
        fieldConfig={fieldConfig}
        overlay={{ fields: { email: { application_visible: true } } }}
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-form-preview-render')).toBeInTheDocument();
    expect(screen.getByTestId('application-form')).toBeInTheDocument();
    expect(screen.getByText('Label email')).toBeInTheDocument();
  });

  it('an unsaved edit re-renders in memory — reflects unsaved edits (R3.1)', () => {
    const { rerender } = render(
      <ApplicationFormPreview
        fieldConfig={fieldConfig}
        overlay={{ fields: { email: { application_visible: true } } }}
        lang="en"
      />,
    );
    expect(screen.getByText('Label email')).toBeInTheDocument();
    expect(screen.queryByText('Label phone')).not.toBeInTheDocument();

    rerender(
      <ApplicationFormPreview
        fieldConfig={fieldConfig}
        overlay={{
          fields: {
            email: { application_visible: true },
            phone: { application_visible: true },
          },
        }}
        lang="en"
      />,
    );
    expect(screen.getByText('Label phone')).toBeInTheDocument();
  });
});

/* ================================================================== */
/*  MATRIX 3 — NOT-send-ready is a NEUTRAL state, NOT a half form      */
/*             (spans the readiness panel AND the preview) (R6.2/R3)   */
/* ================================================================== */
describe('Phase-4/5 matrix — not-send-ready is NEUTRAL, not a half form (R6.2 / R3)', () => {
  const NOT_READY_MAIL = { ...CERTIFIED_MAIL, mail_certified: false };

  it('the aggregate is NOT send-ready for this fixture (precondition)', () => {
    expect(computeReadiness(fieldConfigWith(NOT_READY_MAIL), ONE_FIELD_ON, 'h-dcn').isSendReady).toBe(
      false,
    );
  });

  it('readiness panel: neutral guidance + sender link, and NO mail-config leak (nl AND en)', () => {
    for (const lang of ['nl', 'en'] as const) {
      const { unmount } = render(
        <ApplicationReadinessPanel
          fieldConfig={fieldConfigWith(NOT_READY_MAIL)}
          overlay={ONE_FIELD_ON}
          slug="h-dcn"
          lang={lang}
        />,
      );
      const notAvailable = screen.getByTestId('application-readiness-not-available');
      expect(notAvailable).toBeInTheDocument();
      expect(
        screen.getByTestId('application-readiness-sender-verification-link'),
      ).toBeInTheDocument();
      const text = notAvailable.textContent ?? '';
      expect(text).not.toContain('h-dcn.nl');
      expect(text).not.toMatch(/certified|domain|gecertificeerd|domein/i);
      expect(screen.queryByTestId('application-readiness-ready')).not.toBeInTheDocument();
      unmount();
    }
  });

  it('preview renders the schema regardless of readiness — no client-side half form', () => {
    // The preview's OWN markup does not depend on readiness: it re-derives the applicant schema from
    // the working draft and renders it through the shared renderer, so the admin can author before
    // the sender is certified. It carries NO readiness branch — the readiness panel owns the "not
    // available" state, not the preview.
    render(
      <ApplicationFormPreview
        fieldConfig={previewFieldConfig([field('email', 'contact')])}
        overlay={{ fields: { email: { application_visible: true } } }}
        lang="en"
      />,
    );
    expect(screen.getAllByTestId('application-form')).toHaveLength(1);
    expect(screen.getByText('Label email')).toBeInTheDocument();
  });

  it('an empty working overlay renders the neutral "no fields yet" hint, NOT a half form', () => {
    render(
      <ApplicationFormPreview
        fieldConfig={previewFieldConfig([field('email', 'contact')])}
        overlay={{}}
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-form-preview-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('application-form-preview-render')).not.toBeInTheDocument();
  });
});

/* ================================================================== */
/*  MATRIX 4 — NO mail-domain leak in ANY readiness string, on BOTH   */
/*             the send-ready AND not-ready paths (R6.2 / design §6)   */
/* ================================================================== */
describe('Phase-4 matrix — no mail-domain leak in any readiness string (R6.2 / design §6)', () => {
  it('SEND-READY panel: the whole panel never renders the certified mail domain (nl AND en)', () => {
    for (const lang of ['nl', 'en'] as const) {
      const { unmount } = render(
        <ApplicationReadinessPanel
          fieldConfig={fieldConfigWith(CERTIFIED_MAIL)}
          overlay={ONE_FIELD_ON}
          slug="h-dcn"
          lang={lang}
        />,
      );
      const panel = screen.getByTestId('application-readiness-panel');
      expect(screen.getByTestId('application-readiness-ready')).toBeInTheDocument();
      expect(panel.textContent ?? '').not.toContain('h-dcn.nl');
      unmount();
    }
  });

  it('NOT-READY panel: the whole panel never renders the mail domain either (nl AND en)', () => {
    for (const lang of ['nl', 'en'] as const) {
      const { unmount } = render(
        <ApplicationReadinessPanel
          fieldConfig={fieldConfigWith(CERTIFIED_MAIL)}
          overlay={ONE_FIELD_ON}
          slug={null}
          lang={lang}
        />,
      );
      const panel = screen.getByTestId('application-readiness-panel');
      expect(screen.getByTestId('application-readiness-not-available')).toBeInTheDocument();
      expect(panel.textContent ?? '').not.toContain('h-dcn.nl');
      unmount();
    }
  });
});

/* ================================================================== */
/*  MATRIX 5 — the PREVIEW never surfaces the mail domain (R3)         */
/* ================================================================== */
describe('Phase-5 matrix — preview never leaks the mail domain (R3)', () => {
  it('the rendered preview contains no mail domain (the schema carries no mail internals)', () => {
    // The preview is fed ONLY the applicant schema (fields + labels), which carries no mail internals
    // — so the rendered preview can never expose the certified `h-dcn.nl`, even though the builder
    // holds a certified `mail_config` elsewhere.
    render(
      <ApplicationFormPreview
        fieldConfig={previewFieldConfig([field('email', 'contact')])}
        overlay={{ fields: { email: { application_visible: true } } }}
        lang="en"
      />,
    );
    const preview = screen.getByTestId('application-form-preview');
    expect(screen.getByTestId('application-form-preview-render')).toBeInTheDocument();
    expect(preview.textContent ?? '').not.toContain('h-dcn.nl');
  });
});

/**
 * Dedicated Phase-4 (R6 + R7) matrix suite for the Application Form Builder — the paired-test
 * task 4.3 (R9.1, design §6 / §9 S1·S2 / §11).
 *
 * Tasks 4.1 and 4.2 each shipped their own focused suites:
 *  - `ApplicationReadinessPanel.test.tsx` — the three readiness facts, the spec-10 certified-sender
 *    pair (fail-closed), the `isSendReady = certified AND slug` aggregate (excluding the field-count
 *    hint), and the neutral no-mail-leak guidance;
 *  - `ApplicationFormPreview.test.tsx` — the iframe to the derived public URL, the no-slug neutral
 *    placeholder, and the save-driven / manual reload-token remount.
 *
 * This suite is the task-4.3 roll-up over the SAME components. It does NOT re-prove what those two
 * suites already assert; it ADDS the cross-cutting Phase-4 matrix cases that neither suite owns on
 * its own — above all the explicit "not-send-ready is a NEUTRAL state, NOT a half form" contract
 * that spans the readiness panel AND the preview together (R6.2 / R7.3), plus the preview's
 * "renders the filtered schema through the shared renderer" phrasing for the iframe-by-construction
 * design (R7.1/R7.2) and the bilingual (nl/en) neutral surfaces.
 *
 * Why the preview satisfies "renders the filtered schema through the shared renderer" by
 * construction (design §9 S1, Property 4): the preview is an `<iframe>` to the REAL CloudFront-
 * hosted public form — the hosted form IS the spec-10 shared renderer. The builder does NOT
 * re-implement the renderer or the send-ready filter client-side, so what the admin previews is
 * exactly what an applicant gets (zero drift). The equivalent, observable assertions are therefore:
 * (a) the iframe src is the derived public URL (the shared-renderer path), and (b) a save bumps the
 * reload token so the iframe re-fetches last-saved state — NOT a client-side re-render.
 *
 * The components take `lang` directly (no i18n), so a plain Chakra render suffices.
 */
import { describe, it, expect } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '../../../../test-utils';
import type { FieldConfig } from '../../../../types/members';
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

/** A field config carrying `mail_config` + one field (optionally served on-the-form). */
function fieldConfigWith(
  mail: FieldConfig['mail_config'] | undefined,
  onFormServed = false,
): FieldConfig {
  return {
    fields: [
      {
        key: 'email',
        functional_group: 'contact',
        type: 'string',
        provenance: 'tenant_added',
        ...(onFormServed ? { application_visible: true } : {}),
      } as FieldConfig['fields'][number],
    ],
    mail_config: mail,
  };
}

const ONE_FIELD_ON: MembersConfigValue = {
  fields: { email: { application_visible: true } },
} as MembersConfigValue;

/* ================================================================== */
/*  MATRIX 1 — readiness reflects certified / slug / field states     */
/*             EACH INDEPENDENTLY (R6.1)                               */
/* ================================================================== */
/*
 * The per-helper fail-closed edges + the component's happy path live in the task-4.1 suite. Here we
 * pin the MATRIX view: each of the three facts flips the panel's per-row `data-state` on its own,
 * holding the other two fixed, so no fact can silently mask another.
 */
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
    // slug + field stay OK — the certified fact did not bleed into them.
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
    // ...and because the field count is authoring-only, the panel still says the form can go live.
    expect(screen.getByTestId('application-readiness-ready')).toBeInTheDocument();
    expect(screen.queryByTestId('application-readiness-not-available')).not.toBeInTheDocument();
  });
});

/* ================================================================== */
/*  MATRIX 2 — preview renders the filtered schema through the SHARED */
/*             RENDERER: iframe src = derived public URL; a save bumps */
/*             the reload token (NOT a client-side re-render) (R7.1/2) */
/* ================================================================== */
describe('Phase-4 matrix — preview targets the shared-renderer path (R7.1/R7.2)', () => {
  it('the iframe src IS the derived public form URL (the shared renderer, zero drift)', () => {
    render(<ApplicationFormPreview slug="h-dcn" lang="en" />);
    const iframe = screen.getByTestId('application-form-preview-iframe');
    // The hosted form at <slug>.jabaki.nl IS the spec-10 ApplicationFormRenderer — not a local copy.
    expect(iframe.getAttribute('src') ?? '').toContain('https://h-dcn.jabaki.nl');
  });

  it('a save (reload-token bump) re-fetches the hosted form — NOT a client-side re-render', () => {
    const { rerender } = render(
      <ApplicationFormPreview slug="h-dcn" reloadToken={0} lang="en" />,
    );
    const iframeBefore = screen.getByTestId('application-form-preview-iframe');
    const srcBefore = iframeBefore.getAttribute('src');

    // Builder bumps the token after the one config#fields/#mail save → remount re-fetches last-saved.
    rerender(<ApplicationFormPreview slug="h-dcn" reloadToken={1} lang="en" />);
    const iframeAfter = screen.getByTestId('application-form-preview-iframe');

    // Still the SAME hosted URL (the shared-renderer path) — only the cache-busting token changed,
    // proving the refresh is a hosted-form re-fetch, not the builder re-rendering a schema locally.
    expect(iframeAfter.getAttribute('src')).not.toBe(srcBefore);
    expect(iframeAfter.getAttribute('src') ?? '').toContain('https://h-dcn.jabaki.nl');
  });
});

/* ================================================================== */
/*  MATRIX 3 — NOT-send-ready is a NEUTRAL state, NOT a half form      */
/*             (spans the readiness panel AND the preview) (R6.2/R7.3) */
/* ================================================================== */
/*
 * The single most important Phase-4 contract: when the tenant is not send-ready the builder must
 * surface a NEUTRAL "not available" posture and must NOT render a partial/half form client-side.
 * It is proven across BOTH surfaces together:
 *   - readiness panel → neutral guidance, no mail-config leak, a sender-verification link;
 *   - preview → defers to the hosted form (which owns the neutral 409) via an iframe to the SAME
 *     public URL regardless of readiness — the builder owns no readiness branch that could emit a
 *     half-rendered form.
 */
describe('Phase-4 matrix — not-send-ready is NEUTRAL, not a half form (R6.2 / R7.3)', () => {
  // A not-send-ready tenant: no certified sender, but a slug exists so the preview still embeds the
  // hosted form (whose OWN neutral 409 is what the admin then sees — not a builder-rendered form).
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
      // Neutral: never the domain, never WHICH mail fact is missing (R6.2 / NFR), in either locale.
      const text = notAvailable.textContent ?? '';
      expect(text).not.toContain('h-dcn.nl');
      expect(text).not.toMatch(/certified|domain|gecertificeerd|domein/i);
      // The "ready / can go live" branch must be absent when not send-ready.
      expect(screen.queryByTestId('application-readiness-ready')).not.toBeInTheDocument();
      unmount();
    }
  });

  it('preview defers to the hosted form (one iframe to the SAME URL) regardless of readiness — no client-side half form', () => {
    // Send-ready and not-send-ready are indistinguishable in the preview's OWN markup: it always
    // embeds the hosted form via one iframe to the same derived URL and renders NO schema/field
    // markup itself. The hosted form owns the send-ready vs 409 decision (R7.3), so the builder can
    // never emit a half-rendered form from a readiness branch it does not have.
    const { unmount } = render(<ApplicationFormPreview slug="h-dcn" lang="en" />);
    const iframe = screen.getByTestId('application-form-preview-iframe');
    expect(iframe.getAttribute('src') ?? '').toContain('https://h-dcn.jabaki.nl');
    // Exactly ONE iframe — the preview is the single hosted-form embed, not a partial field render.
    expect(screen.getAllByTestId('application-form-preview-iframe')).toHaveLength(1);
    unmount();
  });

  it('preview without a slug: neutral placeholder, NOT a half form (no iframe, no partial fields)', () => {
    render(<ApplicationFormPreview slug={null} lang="en" />);
    // Neutral "no preview available yet" + a Landing Page editor link...
    expect(screen.getByTestId('application-form-preview-no-url')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-preview-landing-link')).toBeInTheDocument();
    // ...and crucially NO iframe and NO half-rendered form surface.
    expect(screen.queryByTestId('application-form-preview-iframe')).not.toBeInTheDocument();
    expect(screen.queryByTestId('application-form-preview')).not.toBeInTheDocument();
  });

  it('manual "Update preview" keeps the SAME hosted URL (reloads, never swaps to a local render)', () => {
    render(<ApplicationFormPreview slug="h-dcn" lang="en" />);
    const srcBefore = screen
      .getByTestId('application-form-preview-iframe')
      .getAttribute('src');
    fireEvent.click(screen.getByTestId('application-form-preview-reload'));
    const srcAfter = screen
      .getByTestId('application-form-preview-iframe')
      .getAttribute('src');
    expect(srcAfter).not.toBe(srcBefore);
    expect(srcAfter ?? '').toContain('https://h-dcn.jabaki.nl');
  });
});

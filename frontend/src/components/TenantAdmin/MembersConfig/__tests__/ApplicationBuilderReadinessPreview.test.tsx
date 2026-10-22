/**
 * Dedicated Phase-4 (R6 + R7) matrix suite for the Application Form Builder — the paired-test
 * task 4.3 (R9.1, design §6 / §9 S1·S2 / §11).
 *
 * Tasks 4.1 and 4.2 each shipped their own focused suites:
 *  - `ApplicationReadinessPanel.test.tsx` — the three readiness facts, the spec-10 certified-sender
 *    pair (fail-closed), the `isSendReady = certified AND slug` aggregate (excluding the field-count
 *    hint), and the neutral no-mail-leak guidance;
 *  - `ApplicationFormPreview.test.tsx` — the debounced POST of the WORKING overlay to
 *    `POST /members/application-preview` and the in-app render of the returned schema through the
 *    shared spec-10 `ApplicationFormRenderer` (reflecting unsaved edits, read-only).
 *
 * This suite is the task-4.3 roll-up over the SAME components. It does NOT re-prove what those two
 * suites already assert; it ADDS the cross-cutting Phase-4 matrix cases that neither suite owns on
 * its own — above all the explicit "not-send-ready is a NEUTRAL state, NOT a half form" contract
 * that spans the readiness panel AND the preview together (R6.2 / R7.3), plus the preview's
 * "renders the filtered schema through the shared renderer" assertion (R7.1/R7.2) and the bilingual
 * (nl/en) neutral surfaces.
 *
 * Why the preview satisfies "renders the filtered schema through the shared renderer" (design §9
 * S1/S2, Property 4): the preview POSTs the admin's WORKING `field_overlay` to the server preview
 * endpoint, which runs the EXACT `get_public_field_config` filter, and feeds the returned schema to
 * the spec-10 `ApplicationFormRenderer`. So it shares a SINGLE filtering authority (server) AND a
 * SINGLE rendering path (the shared renderer) — no client mirror, zero drift — and reflects unsaved
 * edits. The server preview is MOCKED here so the matrix asserts the wiring without a network.
 *
 * The components take `lang` directly (no i18n), so a plain Chakra render suffices.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen } from '../../../../test-utils';
import type { FieldConfig } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import type { PublicFieldConfig } from '../../../public/application/applicationFieldConfig';
import { ApplicationReadinessPanel } from '../ApplicationReadinessPanel';
import { ApplicationFormPreview } from '../ApplicationFormPreview';
import { computeReadiness } from '../applicationReadiness';
import { previewMembersApplicationConfig } from '../../../../services/membersConfigService';

vi.mock('../../../../services/membersConfigService', () => ({
  previewMembersApplicationConfig: vi.fn(),
}));
const mockPreview = vi.mocked(previewMembersApplicationConfig);

/** A minimal applicant-facing schema the server preview returns for a working overlay. */
function previewSchema(fieldKeys: string[]): PublicFieldConfig {
  return {
    fields: fieldKeys.map((key, i) => ({
      key,
      type: 'string',
      label: { nl: `NL ${key}`, en: `Label ${key}` },
      functional_group: 'contact',
      order: i,
      required: false,
    })),
    locales: ['nl', 'en'],
    notice: null,
  };
}

beforeEach(() => {
  mockPreview.mockReset();
});

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
/*             RENDERER: POST the working overlay → render the server  */
/*             schema; an unsaved edit re-POSTs and re-renders (R7.1/2)*/
/* ================================================================== */
describe('Phase-4 matrix — preview targets the shared-renderer path (R7.1/R7.2)', () => {
  it('renders the server-filtered schema through the shared renderer (zero drift)', async () => {
    mockPreview.mockResolvedValue(previewSchema(['email']));
    render(<ApplicationFormPreview overlay={{ fields: { email: { application_visible: true } } }} lang="en" debounceMs={0} />);

    // The returned schema is rendered through the spec-10 ApplicationFormRenderer — not a local copy.
    await screen.findByTestId('application-form-preview-render');
    expect(screen.getByTestId('application-form')).toBeInTheDocument();
    expect(screen.getByText('Label email')).toBeInTheDocument();
  });

  it('an unsaved edit re-POSTs the working overlay and re-renders — reflects unsaved edits (§9 S2)', async () => {
    mockPreview.mockResolvedValueOnce(previewSchema(['email']));
    const { rerender } = render(
      <ApplicationFormPreview overlay={{ fields: { email: { application_visible: true } } }} lang="en" debounceMs={0} />,
    );
    await screen.findByText('Label email');

    // The admin toggles another field ON (UNSAVED) → the preview re-POSTs + renders the new schema,
    // with no save / round-trip to the hosted form — proving it reflects the WORKING overlay live.
    mockPreview.mockResolvedValueOnce(previewSchema(['email', 'phone']));
    rerender(
      <ApplicationFormPreview
        overlay={{ fields: { email: { application_visible: true }, phone: { application_visible: true } } }}
        lang="en"
        debounceMs={0}
      />,
    );
    await screen.findByText('Label phone');
    expect(mockPreview).toHaveBeenCalledTimes(2);
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
 *   - preview → still renders the schema (the server preview endpoint BYPASSES the send-ready gate
 *     so the admin can author before the sender is certified, R6.2) — it carries NO readiness
 *     branch, so it can never emit a half-rendered form; the readiness panel owns the "not
 *     available" state, not the preview.
 */
describe('Phase-4 matrix — not-send-ready is NEUTRAL, not a half form (R6.2 / R7.3)', () => {
  // A not-send-ready tenant: no certified sender.
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

  it('preview renders the schema regardless of readiness (server bypasses the send-ready gate) — no client-side half form', async () => {
    // The preview's OWN markup does not depend on readiness: it POSTs the working overlay and the
    // server preview endpoint — which BYPASSES the send-ready gate (R6.2) — returns the schema, so
    // the admin can author before the sender is certified. The preview carries NO readiness branch,
    // so it can never emit a half-rendered form; the readiness panel owns the "not available" state.
    mockPreview.mockResolvedValue(previewSchema(['email']));
    render(<ApplicationFormPreview overlay={{ fields: { email: { application_visible: true } } }} lang="en" debounceMs={0} />);

    await screen.findByTestId('application-form-preview-render');
    // One rendered form, via the shared renderer — not a partial/ad-hoc field render.
    expect(screen.getAllByTestId('application-form')).toHaveLength(1);
    expect(screen.getByText('Label email')).toBeInTheDocument();
  });

  it('an empty working overlay renders the neutral "no fields yet" hint, NOT a half form', async () => {
    // The server filter returns an empty field set for an overlay with nothing on the form; the
    // preview shows a neutral "turn fields on" hint rather than a blank/half form.
    mockPreview.mockResolvedValue(previewSchema([]));
    render(<ApplicationFormPreview overlay={{}} lang="en" debounceMs={0} />);

    await screen.findByTestId('application-form-preview-empty');
    expect(screen.queryByTestId('application-form-preview-render')).not.toBeInTheDocument();
  });
});

/* ================================================================== */
/*  MATRIX 4 — NO mail-domain leak in ANY readiness string, on BOTH   */
/*             the send-ready AND not-ready paths (R6.2 / NFR;         */
/*             design §6 "no domain leak in ANY public-facing string")*/
/* ================================================================== */
/*
 * The task-4.1 suite + MATRIX 3 already pin the NOT-send-ready "not available" box as neutral (no
 * `h-dcn.nl`, no WHICH-fact-is-missing wording). What neither owns is the SEND-READY path: a
 * certified tenant's `mail_domain` (`h-dcn.nl`) is in the loaded `config#mail`, and design §6
 * requires the panel never surface it in ANY string — not just the not-available branch. These
 * cases pin the WHOLE panel's rendered text as domain-free on BOTH readiness outcomes, so the
 * certified sender's mail posture can never be probed from the builder.
 */
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
      // Precondition: this IS the send-ready "can go live" branch...
      expect(screen.getByTestId('application-readiness-ready')).toBeInTheDocument();
      // ...and NOWHERE in the rendered panel — rows, badges, ready message — does the domain leak.
      expect(panel.textContent ?? '').not.toContain('h-dcn.nl');
      unmount();
    }
  });

  it('NOT-READY panel: the whole panel never renders the mail domain either (nl AND en)', () => {
    // Not send-ready via a MISSING slug, so the certified mail_domain (`h-dcn.nl`) IS still loaded —
    // the leak surface is live, yet no string may expose it.
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
/*  MATRIX 5 — the PREVIEW never surfaces the mail domain, and an      */
/*             end-to-end unsaved edit flows overlay → render (R7.1/2) */
/* ================================================================== */
/*
 * The task bullet calls out that the preview must not leak the mail domain: the preview is fed ONLY
 * the server-filtered applicant schema (fields + labels + notice), which carries no mail internals,
 * so the rendered preview can never expose `h-dcn.nl`. We pin that explicitly, plus an end-to-end
 * "an unsaved edit is reflected" flow that watches the EXACT overlay reach the endpoint and the
 * returned field appear in the render (the single filter authority + single render path, §9 S1/S2).
 */
describe('Phase-4 matrix — preview never leaks the mail domain; unsaved edit flows end-to-end (R7.1/R7.2)', () => {
  it('the rendered preview contains no mail domain (the schema carries no mail internals)', async () => {
    mockPreview.mockResolvedValue(previewSchema(['email']));
    render(
      <ApplicationFormPreview
        overlay={{ fields: { email: { application_visible: true } } }}
        lang="en"
        debounceMs={0}
      />,
    );
    const preview = await screen.findByTestId('application-form-preview');
    await screen.findByTestId('application-form-preview-render');
    // The whole preview subtree — hint text, renderer output — never surfaces the certified domain.
    expect(preview.textContent ?? '').not.toContain('h-dcn.nl');
  });

  it('end-to-end: the exact WORKING overlay reaches the endpoint and its field appears unsaved', async () => {
    mockPreview.mockResolvedValueOnce(previewSchema(['email']));
    const edited = {
      fields: { email: { application_visible: true }, phone: { application_visible: true } },
    };
    const { rerender } = render(
      <ApplicationFormPreview
        overlay={{ fields: { email: { application_visible: true } } }}
        lang="en"
        debounceMs={0}
      />,
    );
    await screen.findByText('Label email');

    // An unsaved toggle of `phone` ON → the EXACT edited overlay is POSTed (not a saved/round-tripped
    // copy) and the server-returned field renders — proving the preview reflects the working overlay.
    mockPreview.mockResolvedValueOnce(previewSchema(['email', 'phone']));
    rerender(<ApplicationFormPreview overlay={edited} lang="en" debounceMs={0} />);

    await screen.findByText('Label phone');
    expect(mockPreview).toHaveBeenLastCalledWith(edited);
  });
});

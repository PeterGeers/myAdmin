/**
 * Tests for the Application readiness panel + its pure helpers (spec 11, task 4.1; R6.1–R6.3,
 * design §6 / §10).
 *
 * The change-with-tests pairing for the new `ApplicationReadinessPanel` + `applicationReadiness`
 * behavior (the full dedicated suite is task 4.3). It asserts the R6 contract this task owns:
 *  - the three readiness facts (certified sender / slug / >=1 field on the form) reflect the
 *    loaded `config#mail` + slug + the working overlay (R6.1);
 *  - the certified-sender fact IS the spec-10 send-ready pair (`mail_certified` + non-blank
 *    `mail_domain`), fail-closed on every missing fact (R6.3 / design §6);
 *  - NOT send-ready → NEUTRAL "not available" guidance that NEVER leaks the mail domain / which
 *    fact is missing, plus a link to sender verification (R6.2 / R6.3);
 *  - the panel is a pure view — no network, no save.
 *
 * The component takes `lang` directly (no i18n), so a plain Chakra render suffices.
 */
import { describe, it, expect } from 'vitest';
import React from 'react';
import { render, screen } from '../../../../test-utils';
import type { FieldConfig } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import { ApplicationReadinessPanel } from '../ApplicationReadinessPanel';
import {
  computeReadiness,
  countFieldsOnForm,
  hasCertifiedSender,
  hasSlug,
} from '../applicationReadiness';

/* ------------------------------------------------------------------ */
/*  Fixtures                                                           */
/* ------------------------------------------------------------------ */
const CERTIFIED_MAIL: FieldConfig['mail_config'] = {
  mail_enabled: true,
  mail_certified: true,
  mail_domain: 'h-dcn.nl',
  mail_local_part: 'noreply',
};

/** A field config with one served on-the-form field + mail config. */
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

/* ------------------------------------------------------------------ */
/*  Pure helpers (applicationReadiness)                                */
/* ------------------------------------------------------------------ */
describe('applicationReadiness — certified sender (spec-10 pair, fail-closed, R6.3)', () => {
  it('is true only with mail_certified AND a non-blank mail_domain', () => {
    expect(hasCertifiedSender(CERTIFIED_MAIL)).toBe(true);
  });
  it('is false when not certified', () => {
    expect(hasCertifiedSender({ ...CERTIFIED_MAIL, mail_certified: false })).toBe(false);
  });
  it('is false when the domain is blank/absent (fail-closed)', () => {
    expect(hasCertifiedSender({ ...CERTIFIED_MAIL, mail_domain: '   ' })).toBe(false);
    expect(hasCertifiedSender({ ...CERTIFIED_MAIL, mail_domain: undefined })).toBe(false);
  });
  it('is false with no mail config at all', () => {
    expect(hasCertifiedSender(null)).toBe(false);
    expect(hasCertifiedSender(undefined)).toBe(false);
  });
});

describe('applicationReadiness — slug + field count (R6.1)', () => {
  it('hasSlug is true only for a non-blank slug', () => {
    expect(hasSlug('h-dcn')).toBe(true);
    expect(hasSlug('  ')).toBe(false);
    expect(hasSlug(null)).toBe(false);
  });

  it('counts a field on the form from the WORKING overlay (unsaved toggle wins)', () => {
    const overlay: MembersConfigValue = {
      fields: { email: { application_visible: true } },
    } as MembersConfigValue;
    expect(countFieldsOnForm(fieldConfigWith(CERTIFIED_MAIL), overlay)).toBe(1);
  });

  it('counts a field on the form from the SERVED application_visible when the overlay is silent', () => {
    expect(countFieldsOnForm(fieldConfigWith(CERTIFIED_MAIL, true), {})).toBe(1);
  });

  it('counts zero when neither overlay nor served marks any field on the form', () => {
    expect(countFieldsOnForm(fieldConfigWith(CERTIFIED_MAIL), {})).toBe(0);
  });
});

describe('applicationReadiness — computeReadiness aggregate (design §6)', () => {
  it('isSendReady = certified sender AND slug; EXCLUDES the field-count hint', () => {
    // Certified + slug but NO field on the form → still send-ready (field count is authoring-only).
    const state = computeReadiness(fieldConfigWith(CERTIFIED_MAIL), {}, 'h-dcn');
    expect(state.certifiedSender).toBe(true);
    expect(state.slugPresent).toBe(true);
    expect(state.hasFieldOnForm).toBe(false);
    expect(state.isSendReady).toBe(true);
  });

  it('is NOT send-ready without a slug', () => {
    expect(computeReadiness(fieldConfigWith(CERTIFIED_MAIL), {}, null).isSendReady).toBe(false);
  });

  it('is NOT send-ready without a certified sender', () => {
    const notCertified = { ...CERTIFIED_MAIL, mail_certified: false };
    expect(computeReadiness(fieldConfigWith(notCertified), {}, 'h-dcn').isSendReady).toBe(false);
  });

  it('prefers a served application_readiness.is_send_ready boolean when present (back-compat)', () => {
    const cfg = {
      ...fieldConfigWith(undefined),
      application_readiness: { is_send_ready: true },
    } as FieldConfig;
    // No mail_config at all, but the served signal says ready → certifiedSender follows it.
    expect(computeReadiness(cfg, {}, 'h-dcn').certifiedSender).toBe(true);
  });
});

/* ------------------------------------------------------------------ */
/*  Component (ApplicationReadinessPanel)                              */
/* ------------------------------------------------------------------ */
describe('ApplicationReadinessPanel — shows the three readiness states (R6.1)', () => {
  it('shows all three states OK and the "can go live" message when fully ready', () => {
    const overlay: MembersConfigValue = {
      fields: { email: { application_visible: true } },
    } as MembersConfigValue;
    render(
      <ApplicationReadinessPanel
        fieldConfig={fieldConfigWith(CERTIFIED_MAIL)}
        overlay={overlay}
        slug="h-dcn"
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-readiness-certified-sender')).toHaveAttribute(
      'data-state',
      'ok',
    );
    expect(screen.getByTestId('application-readiness-slug')).toHaveAttribute('data-state', 'ok');
    expect(screen.getByTestId('application-readiness-field-on-form')).toHaveAttribute(
      'data-state',
      'ok',
    );
    expect(screen.getByTestId('application-readiness-ready')).toBeInTheDocument();
    expect(screen.queryByTestId('application-readiness-not-available')).not.toBeInTheDocument();
  });
});

describe('ApplicationReadinessPanel — not send-ready guidance (R6.2 / R6.3)', () => {
  it('shows neutral "not available" guidance + a sender-verification link when not ready', () => {
    render(
      <ApplicationReadinessPanel
        fieldConfig={fieldConfigWith({ ...CERTIFIED_MAIL, mail_certified: false })}
        overlay={{}}
        slug="h-dcn"
        lang="en"
      />,
    );
    const notAvailable = screen.getByTestId('application-readiness-not-available');
    expect(notAvailable).toBeInTheDocument();
    expect(
      screen.getByTestId('application-readiness-sender-verification-link'),
    ).toBeInTheDocument();
    // The certified-sender row reflects the failing fact as a boolean...
    expect(screen.getByTestId('application-readiness-certified-sender')).toHaveAttribute(
      'data-state',
      'not-ok',
    );
    // ...but the guidance NEVER leaks the mail domain or WHICH fact is missing (R6.2 / NFR).
    expect(notAvailable.textContent ?? '').not.toContain('h-dcn.nl');
    expect(notAvailable.textContent ?? '').not.toMatch(/certified|domain|gecertificeerd|domein/i);
  });
});

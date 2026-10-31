/**
 * Tests for the PUBLIC member-application SUBMIT container (task 9.3).
 *
 * Pins the behaviours task 9.3 adds on top of the 9.1 renderer + 9.2 schema:
 *  - a server 422 `errors[]` is mapped into Formik BY the dotted `field` key, rendering through the
 *    SAME `FormErrorMessage` as a client error (R10a.3), and the SERVER error WINS (R6.6);
 *  - an ARIA live-region error SUMMARY (role="alert"/aria-live) lists the errors (R10a.5);
 *  - the LOCALE selector switches the rendered labels AND the submitted `locale` (R6b);
 *  - the CONSENT checkbox is required to submit and, once ticked, the submit sends
 *    `consent={accepted:true, notice_version}` (R12.1 / D26 / 2.6).
 *
 * The public submit endpoint is faked with MSW; Chakra is auto-mocked (vite test alias);
 * `render` comes from `@/test-utils`.
 */

import React from 'react';
import { describe, it, expect, beforeAll, afterEach, afterAll, beforeEach, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { render, screen, within, waitFor } from '@/test-utils';
import userEvent from '@testing-library/user-event';

import { ApplicationFormPage } from '../components/public/application/ApplicationFormPage';
import type { PublicFieldConfig } from '../components/public/application/applicationFieldConfig';

// ---------------------------------------------------------------------------
// A representative public field-config: two required text fields + a required enum, bilingual
// labels, and a versioned consent notice (design §3.1).
// ---------------------------------------------------------------------------
const CONFIG: PublicFieldConfig = {
  fields: [
    {
      key: 'personal.first_name',
      type: 'string',
      label: { nl: 'Voornaam', en: 'First name' },
      functional_group: 'personal',
      order: 10,
      required: true,
    },
    {
      key: 'personal.email',
      type: 'string',
      label: { nl: 'E-mailadres', en: 'Email' },
      functional_group: 'personal',
      order: 20,
      required: true,
      format: { checker: 'EMAIL' },
    },
    {
      key: 'membership.membership_type',
      type: 'enum',
      label: { nl: 'Type', en: 'Type' },
      functional_group: 'membership',
      order: 10,
      required: true,
      options: [
        { value: 'gewoon', label: { nl: 'Gewoon lid', en: 'Ordinary member' } },
        { value: 'student', label: { nl: 'Student', en: 'Student' } },
      ],
    },
  ],
  locales: ['nl', 'en'],
  notice: { version: 'notice-v3', text: { nl: 'de privacyverklaring', en: 'the privacy notice' } },
};

const BASE = 'https://public-api.test';
const SUBMIT_URL = `${BASE}/public/members/:slug/applications`;
// The branding-logo read (spec 13, R5) is a Flask-plane GET fired on mount. These submit-focused
// tests don't exercise the logo, so stub it as "no logo" (`logo: null`) to keep the mount quiet —
// the dedicated logo render test (task 5.3) asserts the configured/absent branding behaviour.
const LOGO_URL = `*/api/public/landing/:slug/logo`;

/** The last body the submit endpoint received (asserted per test). */
let lastBody: Record<string, unknown> | null = null;

const server = setupServer(
  http.post(SUBMIT_URL, async ({ request }) => {
    lastBody = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({ success: true, data: { received: true } }, { status: 202 });
  }),
  http.get(LOGO_URL, () =>
    HttpResponse.json({ success: true, data: { logo: null } }, { status: 200 }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  lastBody = null;
});
afterAll(() => server.close());

/** The inner checkbox input of the consent control (the Chakra mock wraps it in a label). */
function consentInput(): HTMLInputElement {
  return within(screen.getByTestId('consent-checkbox')).getByRole('checkbox') as HTMLInputElement;
}

/** Fill the three required fields with VALID values (so only the behaviour under test differs). */
async function fillValidly(user: ReturnType<typeof userEvent.setup>, locale: 'nl' | 'en' = 'nl') {
  const firstName = locale === 'nl' ? 'Voornaam' : 'First name';
  await user.type(screen.getByLabelText(firstName), 'Ada');
  await user.type(screen.getByLabelText(locale === 'nl' ? 'E-mailadres' : 'Email'), 'ada@example.com');
  await user.selectOptions(screen.getByLabelText('Type'), 'gewoon');
}

describe('ApplicationFormPage — consent (R12.1)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('refuses to submit without affirmative consent and shows a required error', async () => {
    const user = userEvent.setup();
    render(<ApplicationFormPage tenantSlug="hdcn" config={CONFIG} apiBaseUrl={BASE} />);

    await fillValidly(user);
    // Consent NOT ticked.
    await user.click(screen.getByTestId('submit-button'));

    expect(await screen.findByTestId('consent-error')).toBeInTheDocument();
    // Nothing was POSTed.
    expect(lastBody).toBeNull();
  });

  it('submits consent={accepted:true, notice_version} once ticked (D26/2.6)', async () => {
    const user = userEvent.setup();
    render(<ApplicationFormPage tenantSlug="hdcn" config={CONFIG} apiBaseUrl={BASE} />);

    await fillValidly(user);
    await user.click(consentInput());
    await user.click(screen.getByTestId('submit-button'));

    await screen.findByTestId('application-accepted');
    expect(lastBody).toMatchObject({
      locale: 'nl',
      consent: { accepted: true, notice_version: 'notice-v3' },
    });
    // The submit shape is the flat dotted-key map (design §3.2).
    expect((lastBody as any).fields).toMatchObject({
      'personal.first_name': 'Ada',
      'personal.email': 'ada@example.com',
      'membership.membership_type': 'gewoon',
    });
  });
});

describe('ApplicationFormPage — server 422 → Formik by dotted key (R10a.3/R6.6)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('maps each server error to its dotted field and renders it through FormErrorMessage', async () => {
    server.use(
      http.post(SUBMIT_URL, () =>
        HttpResponse.json(
          {
            code: 'errors.validation.failed',
            errors: [
              { field: 'personal.email', code: 'errors.field.email', detail: 'E-mail is ongeldig' },
              {
                field: 'membership.membership_type',
                code: 'errors.field.required',
                detail: 'Type is verplicht',
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );

    const user = userEvent.setup();
    render(<ApplicationFormPage tenantSlug="hdcn" config={CONFIG} apiBaseUrl={BASE} />);

    await fillValidly(user);
    await user.click(consentInput());
    await user.click(screen.getByTestId('submit-button'));

    // Each server error renders against its OWN dotted field via the renderer's FormErrorMessage —
    // the per-field error element id is derived from the dotted key (same wiring as a client error).
    await waitFor(() =>
      expect(document.getElementById('app-field-personal-email-error')).toHaveTextContent(
        'E-mail is ongeldig',
      ),
    );
    expect(
      document.getElementById('app-field-membership-membership_type-error'),
    ).toHaveTextContent('Type is verplicht');

    // The email field's control is marked invalid + wired to its error (same mechanism as client).
    const emailInput = screen.getByLabelText('E-mailadres');
    expect(emailInput).toHaveAttribute('aria-invalid', 'true');
    expect(emailInput).toHaveAttribute('aria-describedby', 'app-field-personal-email-error');
  });

  it('server error WINS over the client Yup error on the same field (R6.6)', async () => {
    // Server rejects the email with a DIFFERENT message than the client would; the server wins.
    server.use(
      http.post(SUBMIT_URL, () =>
        HttpResponse.json(
          {
            code: 'errors.validation.failed',
            errors: [
              {
                field: 'personal.email',
                code: 'errors.field.email.taken',
                detail: 'Dit e-mailadres is al in gebruik',
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );

    const user = userEvent.setup();
    render(<ApplicationFormPage tenantSlug="hdcn" config={CONFIG} apiBaseUrl={BASE} />);

    await fillValidly(user); // client-valid email
    await user.click(consentInput());
    await user.click(screen.getByTestId('submit-button'));

    // The SERVER message is what shows on the email field — not a client "invalid email" message.
    await waitFor(() =>
      expect(document.getElementById('app-field-personal-email-error')).toHaveTextContent(
        'Dit e-mailadres is al in gebruik',
      ),
    );
  });
});

describe('ApplicationFormPage — ARIA error summary (R10a.5)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('surfaces a live-region summary listing the server errors with links to the fields', async () => {
    server.use(
      http.post(SUBMIT_URL, () =>
        HttpResponse.json(
          {
            code: 'errors.validation.failed',
            errors: [
              { field: 'personal.first_name', code: 'errors.field.required', detail: 'Voornaam is verplicht' },
              { field: 'personal.email', code: 'errors.field.email', detail: 'E-mail is ongeldig' },
            ],
          },
          { status: 422 },
        ),
      ),
    );

    const user = userEvent.setup();
    render(<ApplicationFormPage tenantSlug="hdcn" config={CONFIG} apiBaseUrl={BASE} />);

    await fillValidly(user);
    await user.click(consentInput());
    await user.click(screen.getByTestId('submit-button'));

    const summary = await screen.findByTestId('error-summary');
    expect(summary).toHaveAttribute('role', 'alert');
    expect(summary).toHaveAttribute('aria-live', 'assertive');

    // Announces the count (2) and links each offending field.
    expect(within(summary).getByTestId('error-summary-title')).toHaveTextContent('2');
    const links = within(summary).getAllByRole('link');
    const hrefs = links.map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('#app-field-personal-first_name');
    expect(hrefs).toContain('#app-field-personal-email');
  });

  it('includes the consent requirement in the summary when consent is missing', async () => {
    const user = userEvent.setup();
    render(<ApplicationFormPage tenantSlug="hdcn" config={CONFIG} apiBaseUrl={BASE} />);

    await fillValidly(user);
    await user.click(screen.getByTestId('submit-button')); // no consent

    const summary = await screen.findByTestId('error-summary');
    expect(within(summary).getAllByRole('link').some((a) => a.getAttribute('href') === '#application-consent')).toBe(true);
  });
});

describe('ApplicationFormPage — locale selector (R6b)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('defaults to nl and renders Dutch labels', () => {
    render(<ApplicationFormPage tenantSlug="hdcn" config={CONFIG} apiBaseUrl={BASE} />);
    expect(screen.getByLabelText('Voornaam')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-page')).toHaveAttribute('lang', 'nl');
  });

  it('switches the rendered labels to English when en is selected', async () => {
    const user = userEvent.setup();
    render(<ApplicationFormPage tenantSlug="hdcn" config={CONFIG} apiBaseUrl={BASE} />);

    await user.selectOptions(screen.getByTestId('locale-select'), 'en');

    expect(screen.getByLabelText('First name')).toBeInTheDocument();
    expect(screen.queryByLabelText('Voornaam')).not.toBeInTheDocument();
    expect(screen.getByTestId('application-form-page')).toHaveAttribute('lang', 'en');
  });

  it('submits the selected locale (en)', async () => {
    const user = userEvent.setup();
    render(<ApplicationFormPage tenantSlug="hdcn" config={CONFIG} apiBaseUrl={BASE} />);

    await user.selectOptions(screen.getByTestId('locale-select'), 'en');
    await fillValidly(user, 'en');
    await user.click(consentInput());
    await user.click(screen.getByTestId('submit-button'));

    await screen.findByTestId('application-accepted');
    expect((lastBody as any).locale).toBe('en');
  });
});

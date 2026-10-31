/**
 * Accessibility (axe) gate over the COMPOSED public member-application form (task 9.5, R14.16 / R10a).
 *
 * The parity ("Yup generated-from-config", `applicationFormSchema.test.ts`, task 9.2) and the
 * "422 → Formik by dotted key" mapping (`ApplicationFormPage.test.tsx`, task 9.3) halves of R14.16
 * are already covered by those paired tests; this file adds the one genuine GAP — the automated
 * accessibility gate (R10a.7) over the whole public form as the applicant actually sees it:
 * `PublicApplicationPage` success arm (task 9.4, field-config 200 over MSW) → `ApplicationFormPage`
 * (task 9.3) → `ApplicationFormRenderer` (task 9.1).
 *
 * It asserts the three accessibility pillars R14.16 names explicitly:
 *   1. axe finds NO violations over the rendered public form — clean on first paint AND after a
 *      failed submit surfaces per-field errors + the summary (R10a.7);
 *   2. LABEL ASSOCIATION — every `FormLabel htmlFor` resolves to a control with the same `id`, and
 *      every form control is labelled (R10a.4);
 *   3. ARIA-INVALID binding — a field rejected by the server (422) carries `aria-invalid="true"`
 *      and `aria-describedby` pointing at its `FormErrorMessage` element (R10a.3/R10a.4);
 *   4. the error summary is an ARIA LIVE REGION (`role="alert"` + `aria-live`), the one piece
 *      Chakra's per-field wiring does not provide (R10a.5).
 *
 * The spec is explicit that an automated axe pass is NECESSARY BUT NOT SUFFICIENT — full WCAG 2.2
 * AA conformance still needs manual assistive-technology testing and expert review (R10a.7); this
 * gate pins the automatable floor.
 *
 * Harness notes: Chakra is auto-mocked (vite test alias) but the mock forwards `id` / `htmlFor` /
 * `aria-*` / `role` / `hidden` / `lang` verbatim (see `src/__mocks__/chakra-prop-filter.ts`), and
 * the renderer wires those EXPLICITLY (not via Chakra's `FormControl` context), so the accessible
 * markup axe inspects is the same association the real component ships. `render` comes from
 * `@/test-utils`; the matcher is extended locally so the rest of the suite is untouched.
 */

import React from 'react';
import { describe, it, expect, beforeAll, afterEach, afterAll, beforeEach, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { render, screen, within, waitFor } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { axe } from 'vitest-axe';
import * as axeMatchers from 'vitest-axe/matchers';
// Type augmentation for the registered matcher (scoped to this file).
import 'vitest-axe/extend-expect';

// Register the `toHaveNoViolations` matcher on THIS suite's `expect`. (The side-effect import of
// `vitest-axe/extend-expect` only carries the type augmentation under Vitest 4 — the runtime
// registration must be done explicitly.) Scoped here so the rest of the suite is untouched.
expect.extend(axeMatchers);

import { PublicApplicationPage } from '../components/public/application/PublicApplicationPage';
import { ApplicationFormPage } from '../components/public/application/ApplicationFormPage';
import type { PublicFieldConfig } from '../components/public/application/applicationFieldConfig';

// ---------------------------------------------------------------------------
// A representative public field-config (design §3.1): two groups, bilingual labels, a required
// text + email, a required enum with a public subset, and a show_when-gated IBAN — enough surface
// for axe to judge label association, control labelling, and the invalid-field wiring.
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
        { value: 'incasso', label: { nl: 'Incasso', en: 'Direct debit' } },
      ],
    },
  ],
  locales: ['nl', 'en'],
  notice: { version: 'notice-v3', text: { nl: 'de privacyverklaring', en: 'the privacy notice' } },
};

const BASE = 'https://public-api.test';
const FIELD_CONFIG_URL = `${BASE}/public/members/:slug/field-config`;
const SUBMIT_URL = `${BASE}/public/members/:slug/applications`;
// The branding-logo read (spec 13 R5) is a Flask-plane GET fired on mount. The axe harness does
// not exercise the logo, so stub it as "no logo" to keep the mount quiet (no unhandled-request
// noise); the logo render behaviour is covered by ApplicationFormPage.logo.test.tsx.
const LOGO_URL = `*/api/public/landing/:slug/logo`;

const server = setupServer(
  http.get(FIELD_CONFIG_URL, () => HttpResponse.json({ data: CONFIG })),
  http.get(LOGO_URL, () =>
    HttpResponse.json({ success: true, data: { logo: null } }, { status: 200 }),
  ),
  http.post(SUBMIT_URL, () =>
    HttpResponse.json({ success: true, data: { received: true } }, { status: 202 }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

/**
 * Render the WHOLE public form the applicant sees: the 9.4 page loads the field-config (200 arm)
 * then hands the config to the 9.3 submit container via the `renderForm` slot. Waits until the
 * form has mounted (the config fetch resolved) before returning the container.
 */
async function renderPublicForm(): Promise<HTMLElement> {
  render(
    <PublicApplicationPage
      tenantSlug="hdcn"
      baseUrl={BASE}
      renderForm={(config) => (
        <ApplicationFormPage tenantSlug="hdcn" config={config} apiBaseUrl={BASE} />
      )}
    />,
  );
  return screen.findByTestId('application-form-page');
}

describe('Public application form — axe accessibility gate (task 9.5, R14.16/R10a.7)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('has NO axe violations on the freshly rendered public form', async () => {
    const page = await renderPublicForm();
    const results = await axe(page);
    expect(results).toHaveNoViolations();
  });

  it('associates every field label with its control (FormLabel htmlFor ↔ input id)', async () => {
    const page = await renderPublicForm();

    // Every <label htmlFor> must resolve to a control carrying the SAME id.
    const labels = Array.from(page.querySelectorAll<HTMLLabelElement>('label[for]'));
    expect(labels.length).toBeGreaterThan(0);
    for (const label of labels) {
      const forId = label.getAttribute('for')!;
      const control = page.querySelector(`#${CSS.escape(forId)}`);
      expect(control, `no control with id="${forId}" for label "${label.textContent}"`).toBeTruthy();
      expect(['INPUT', 'SELECT', 'TEXTAREA']).toContain(control!.tagName);
    }

    // And conversely every real form control is reachable by its accessible label. The renderer's
    // config-driven fields plus the locale selector are all queryable by their visible label text.
    expect(screen.getByLabelText('Voornaam')).toBeInTheDocument();
    expect(screen.getByLabelText('E-mailadres')).toBeInTheDocument();
    expect(screen.getByLabelText('Type')).toBeInTheDocument();
    expect(screen.getByLabelText('Taal')).toBeInTheDocument(); // locale selector
  });

  it('binds aria-invalid + aria-describedby on a server-rejected field, and stays axe-clean', async () => {
    // The server rejects the email field with a 422 — the one field we drive into the error state.
    server.use(
      http.post(SUBMIT_URL, () =>
        HttpResponse.json(
          {
            code: 'errors.validation.failed',
            errors: [
              { field: 'personal.email', code: 'errors.field.email', detail: 'E-mail is ongeldig' },
            ],
          },
          { status: 422 },
        ),
      ),
    );

    const user = userEvent.setup();
    const page = await renderPublicForm();

    // Fill validly + consent so the ONLY error surfaced is the server's one on the email field.
    await user.type(screen.getByLabelText('Voornaam'), 'Ada');
    await user.type(screen.getByLabelText('E-mailadres'), 'ada@example.com');
    await user.selectOptions(screen.getByLabelText('Type'), 'gewoon');
    await user.click(within(screen.getByTestId('consent-checkbox')).getByRole('checkbox'));
    await user.click(screen.getByTestId('submit-button'));

    // The error renders through the SAME FormErrorMessage element the renderer wires to the control.
    const errorEl = await waitFor(() => {
      const el = document.getElementById('app-field-personal-email-error');
      expect(el).toHaveTextContent('E-mail is ongeldig');
      return el!;
    });

    const emailInput = screen.getByLabelText('E-mailadres');
    expect(emailInput).toHaveAttribute('aria-invalid', 'true');
    // aria-describedby points AT the FormErrorMessage element that holds the message.
    expect(emailInput).toHaveAttribute('aria-describedby', errorEl.id);

    // A valid field is NOT marked invalid (no spurious aria-invalid noise).
    expect(screen.getByLabelText('Voornaam')).toHaveAttribute('aria-invalid', 'false');

    // The invalid STATE (per-field error + summary live region visible) is still axe-clean.
    const results = await axe(page);
    expect(results).toHaveNoViolations();
  });

  it('exposes the failed-submit error summary as an ARIA live region', async () => {
    const user = userEvent.setup();
    await renderPublicForm();

    // Submit with nothing filled → client validation fails → the summary surfaces.
    await user.click(screen.getByTestId('submit-button'));

    const summary = await screen.findByTestId('error-summary');
    expect(summary).toHaveAttribute('role', 'alert');
    expect(summary).toHaveAttribute('aria-live', 'assertive');
    // It is a genuine live region holding the error list, not an empty shell.
    expect(within(summary).getByTestId('error-summary-title')).toBeInTheDocument();
    expect(within(summary).getAllByRole('link').length).toBeGreaterThan(0);
  });
});

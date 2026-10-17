/**
 * Tests for the PUBLIC member-application page non-form states (task 9.4).
 *
 * Covers the task's required behaviours, driving the page through the field-config read over MSW
 * so the branch on the discriminated `FieldConfigResult` is exercised end to end:
 *  - 409 → a NEUTRAL, bilingual (nl + en) "not accepting applications yet" message, with NO
 *    mail-config / `code` leak (D15/R5.4);
 *  - 404 → a bilingual "no such form" message, indistinguishable from an unknown endpoint (R1a.4);
 *  - transport/parse failure → a generic bilingual error state;
 *  - 200 → the SUCCESS slot (task 9.3's form) renders instead of any non-form state.
 *
 * Chakra is auto-mocked (vite test alias); `render` comes from `@/test-utils`. i18n self-initializes
 * on import of the page component, so the `members:publicApplication.*` copy resolves per locale.
 */

import React from 'react';
import { describe, it, expect, afterEach, afterAll, beforeAll } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { render, screen, waitFor, within } from '@/test-utils';

import { PublicApplicationPage } from '../components/public/application/PublicApplicationPage';
import type { PublicFieldConfig } from '../services/applicationApi';

const BASE = 'https://public-api.test';
const FIELD_CONFIG_URL = `${BASE}/public/members/:slug/field-config`;

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
  ],
  locales: ['nl', 'en'],
  notice: { version: 'v1', text: { nl: 'Toestemming', en: 'Consent' } },
};

/** A stand-in for task 9.3's success slot: proves the form path renders, not a non-form state. */
const renderForm = (config: PublicFieldConfig) => (
  <div data-testid="success-form">form with {config.fields.length} field(s)</div>
);

const server = setupServer(http.get(FIELD_CONFIG_URL, () => HttpResponse.json({ data: CONFIG })));

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

/** The non-form state wrapper and its two per-locale blocks. */
function stateEl() {
  return screen.getByTestId('application-state');
}

describe('PublicApplicationPage — non-form states (task 9.4)', () => {
  it('renders the SUCCESS slot (9.3 form) on 200, not any non-form state', async () => {
    render(<PublicApplicationPage tenantSlug="hdcn" baseUrl={BASE} renderForm={renderForm} />);

    expect(await screen.findByTestId('success-form')).toHaveTextContent('form with 1 field(s)');
    expect(screen.queryByTestId('application-state')).not.toBeInTheDocument();
  });

  it('on 409 shows a NEUTRAL bilingual "not available" message and leaks no mail-config', async () => {
    server.use(
      http.get(FIELD_CONFIG_URL, () =>
        HttpResponse.json(
          // The server envelope — the page must surface NONE of this detail.
          { code: 'errors.application.notAvailable', detail: 'mail_certified=false mail_domain missing' },
          { status: 409 },
        ),
      ),
    );

    render(<PublicApplicationPage tenantSlug="hdcn" baseUrl={BASE} renderForm={renderForm} />);

    await waitFor(() => expect(stateEl()).toHaveAttribute('data-state', 'not_available'));

    // Bilingual: both the Dutch and the English neutral copy are present.
    expect(within(stateEl()).getByText('Aanmeldingen zijn nog niet beschikbaar')).toBeInTheDocument();
    expect(within(stateEl()).getByText('Applications are not available yet')).toBeInTheDocument();
    expect(
      within(stateEl()).getByText('Deze organisatie accepteert nog geen aanmeldingen. Probeer het later opnieuw.'),
    ).toBeInTheDocument();

    // NO mail-config / code leak anywhere in the rendered page.
    const text = stateEl().textContent ?? '';
    expect(text).not.toContain('mail_certified');
    expect(text).not.toContain('mail_domain');
    expect(text).not.toContain('errors.application.notAvailable');
    expect(screen.queryByTestId('success-form')).not.toBeInTheDocument();
  });

  it('on 404 shows a bilingual not-found message (non-probeable, R1a.4)', async () => {
    server.use(http.get(FIELD_CONFIG_URL, () => new HttpResponse(null, { status: 404 })));

    render(<PublicApplicationPage tenantSlug="nope" baseUrl={BASE} renderForm={renderForm} />);

    await waitFor(() => expect(stateEl()).toHaveAttribute('data-state', 'not_found'));
    expect(within(stateEl()).getByText('Pagina niet gevonden')).toBeInTheDocument();
    expect(within(stateEl()).getByText('Page not found')).toBeInTheDocument();
    expect(screen.queryByTestId('success-form')).not.toBeInTheDocument();
  });

  it('on a transport/parse failure shows a generic bilingual error state', async () => {
    server.use(http.get(FIELD_CONFIG_URL, () => HttpResponse.error()));

    render(<PublicApplicationPage tenantSlug="hdcn" baseUrl={BASE} renderForm={renderForm} />);

    await waitFor(() => expect(stateEl()).toHaveAttribute('data-state', 'error'));
    expect(within(stateEl()).getByText('Er is iets misgegaan')).toBeInTheDocument();
    expect(within(stateEl()).getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.queryByTestId('success-form')).not.toBeInTheDocument();
  });
});

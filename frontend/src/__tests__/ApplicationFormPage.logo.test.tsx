/**
 * Render test for the tenant branding logo at the TOP of the public application form
 * (spec `Members/13 - application-form-rendering-polish`, task 5.3 — R5.1/R5.2/R5.3/R5.4).
 *
 * Task 5.2 wired `ApplicationFormPage` to fetch the ONE branding logo on mount via
 * `fetchPublicLogo(tenantSlug, { baseUrl: logoBaseUrl, signal })` — a PUBLIC Flask-plane read
 * (`GET /api/public/landing/<slug>/logo`, body `{ success, data: { logo } }`) that resolves the
 * tenant's `branding.company_logo_s3_key` as an inline data URI (NOT `landing.json`, NOT gated on
 * a published landing page). When a logo comes back the page renders
 * `<Image data-testid="application-logo" src={logo} alt={tenantName ?? 'logo'}>` ABOVE the
 * `<Heading>`; when the read yields null / a non-ok status it renders NOTHING (graceful absence,
 * no broken-image placeholder — R5.3).
 *
 * This is the PAGE-level render test the client-unit test (`applicationApi`) does not give: it
 * drives the real mount → `fetchPublicLogo` → `<Image>` path over MSW. It asserts:
 *  - configured logo → the image renders ABOVE the heading, `src` = the data URI, accessible
 *    `alt` = the tenantName (and falls back to 'logo' when no tenantName is given);
 *  - `{ logo: null }` OR a non-ok status → NO `application-logo`, and the heading/form still
 *    render normally (R5.3);
 *  - the logo read is independent of any landing page — it resolves the same regardless of slug.
 *
 * The public submit endpoint is stubbed so the form mounts cleanly; Chakra is auto-mocked (vite
 * test alias); `render` comes from `@/test-utils`.
 */

import React from 'react';
import { describe, it, expect, beforeAll, afterEach, afterAll, beforeEach, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { render, screen, waitFor } from '@/test-utils';

import { ApplicationFormPage } from '../components/public/application/ApplicationFormPage';
import type { PublicFieldConfig } from '../components/public/application/applicationFieldConfig';

// ---------------------------------------------------------------------------
// A minimal public field-config — just enough for the page to render its chrome; the logo
// behaviour under test is orthogonal to the field model.
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
  ],
  locales: ['nl', 'en'],
  notice: { version: 'notice-v3', text: { nl: 'de privacyverklaring', en: 'the privacy notice' } },
};

const BASE = 'https://public-api.test';
const SUBMIT_URL = `${BASE}/public/members/:slug/applications`;
// The Flask base the logo read is pointed at (injected via the page's `logoBaseUrl` prop).
const LOGO_BASE = 'https://flask-api.test';
const LOGO_URL = `${LOGO_BASE}/api/public/landing/:slug/logo`;

// A tiny inline data-URI standing in for the resolved `branding.company_logo_s3_key` object.
const LOGO_DATA_URI =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';

const server = setupServer(
  // Default logo handler: configured logo for any slug. Individual tests override with `server.use`.
  http.get(LOGO_URL, () =>
    HttpResponse.json({ success: true, data: { logo: LOGO_DATA_URI } }, { status: 200 }),
  ),
  // The submit endpoint is irrelevant to these tests but must not be an unhandled request.
  http.post(SUBMIT_URL, () =>
    HttpResponse.json({ success: true, data: { received: true } }, { status: 202 }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ApplicationFormPage — tenant branding logo (R5)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the configured logo ABOVE the heading with the tenantName as alt (R5.1/R5.2/R5.4)', async () => {
    render(
      <ApplicationFormPage
        tenantSlug="hdcn"
        config={CONFIG}
        apiBaseUrl={BASE}
        logoBaseUrl={LOGO_BASE}
        tenantName="Hondenschool DCN"
      />,
    );

    // The logo appears once the on-mount read resolves.
    const logo = await screen.findByTestId('application-logo');

    // Source is the resolved data URI (R5.2).
    expect(logo).toHaveAttribute('src', LOGO_DATA_URI);
    // Accessible alt = the tenant display name (R5.3).
    expect(logo).toHaveAttribute('alt', 'Hondenschool DCN');

    // The logo sits ABOVE the form heading (R5.1): the heading follows the logo in document order.
    // (The Chakra `Heading` is auto-mocked in the test env and renders as an <h2>; match it by its
    // text rather than an <h1> role so the assertion pins ORDER, not the mocked element level.)
    const heading = screen.getByText('Aanmeldformulier');
    expect(
      logo.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('falls back to alt="logo" when no tenantName is provided (R5.3)', async () => {
    render(
      <ApplicationFormPage
        tenantSlug="hdcn"
        config={CONFIG}
        apiBaseUrl={BASE}
        logoBaseUrl={LOGO_BASE}
      />,
    );

    const logo = await screen.findByTestId('application-logo');
    expect(logo).toHaveAttribute('alt', 'logo');
  });

  it('renders NO logo (graceful absence) when the read returns { logo: null }, and the form still renders (R5.3)', async () => {
    server.use(
      http.get(LOGO_URL, () =>
        HttpResponse.json({ success: true, data: { logo: null } }, { status: 200 }),
      ),
    );

    render(
      <ApplicationFormPage
        tenantSlug="hdcn"
        config={CONFIG}
        apiBaseUrl={BASE}
        logoBaseUrl={LOGO_BASE}
        tenantName="Hondenschool DCN"
      />,
    );

    // The heading/form render normally…
    expect(await screen.findByText('Aanmeldformulier')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-page')).toBeInTheDocument();

    // …and there is NO logo image (no broken-image placeholder).
    // Give the on-mount read time to settle, then confirm the logo never appears.
    await waitFor(() => expect(screen.getByLabelText('Voornaam')).toBeInTheDocument());
    expect(screen.queryByTestId('application-logo')).not.toBeInTheDocument();
  });

  it('renders NO logo when the read returns a non-ok status (R5.3)', async () => {
    server.use(http.get(LOGO_URL, () => new HttpResponse(null, { status: 404 })));

    render(
      <ApplicationFormPage
        tenantSlug="unknown-slug"
        config={CONFIG}
        apiBaseUrl={BASE}
        logoBaseUrl={LOGO_BASE}
      />,
    );

    expect(await screen.findByText('Aanmeldformulier')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText('Voornaam')).toBeInTheDocument());
    expect(screen.queryByTestId('application-logo')).not.toBeInTheDocument();
  });

  it('resolves the logo independently of any landing page (same result across slugs) (R5.2)', async () => {
    // A tenant with NO published landing page must still get its branding logo — the read is
    // addressed by slug against `branding.company_logo_s3_key`, not a landing page.
    render(
      <ApplicationFormPage
        tenantSlug="tenant-without-landing-page"
        config={CONFIG}
        apiBaseUrl={BASE}
        logoBaseUrl={LOGO_BASE}
        tenantName="No Landing Tenant"
      />,
    );

    const logo = await screen.findByTestId('application-logo');
    expect(logo).toHaveAttribute('src', LOGO_DATA_URI);
    expect(logo).toHaveAttribute('alt', 'No Landing Tenant');
  });
});

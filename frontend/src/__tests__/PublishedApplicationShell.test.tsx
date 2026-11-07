/**
 * Paired frontend tests for the PUBLISHED application-form shell — the thin self-contained client
 * (spec 14 Tasks 5.1 + 5.2, R5.4).
 *
 * Task 5.1 (the first `describe`) pins the one wiring it adds: the published shell FETCHES
 * `GET {slug}` (the public field-config read over MSW) and, on success, renders the form through
 * the EXISTING `ApplicationFormRenderer` (asserted by the renderer's own
 * `data-testid="application-form"` + the rendered field control) — reusing the one renderer rather
 * than forking a second one. It also pins the non-probeable not-found arm when no slug resolves,
 * so a published page without a resolvable slug never blanks.
 *
 * Task 5.2 (the two later `describe`s) rounds out the paired coverage WITHOUT re-proving 5.1:
 *  - the shell resolves the slug from the HOST (`{slug}.jabaki.nl`) through `resolveApplicationSlug`
 *    — exercising the deployed host-based path, not just the explicit `slug` test seam;
 *  - all FOUR `PublicApplicationPage` arms are now pinned THROUGH the shell: 5.1 covered success +
 *    404; 5.2 adds the 409 publication-gate (`not_available`) and the generic error arm;
 *  - the standalone boot entry (`mountPublishedApplicationShell`) mounts into `#app-root` and
 *    degrades to `null` (never a throw) when the mount point is absent.
 *
 * The deeper renderer internals (submit, consent, locale, per-field validation) are NOT re-proven
 * here — those have their own tests (`PublicApplicationPage.test.tsx`, `ApplicationFormPage.test.tsx`,
 * `ApplicationFormRenderer.test.tsx`); this file stays on the published-shell surface.
 *
 * Chakra is auto-mocked (vite test alias); `render` comes from `@/test-utils`.
 */

import React from 'react';
import { describe, it, expect, afterEach, afterAll, beforeAll } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { render, screen, waitFor } from '@/test-utils';

import { PublishedApplicationShell } from '../pages/public/PublishedApplicationShell';
import type { PublicFieldConfig } from '../services/applicationApi';

const BASE = 'https://public-api.test';
const FIELD_CONFIG_URL = `${BASE}/public/members/:slug/field-config`;
// The published shell shows the tenant branding logo via a Flask-plane read on mount; stub it as
// "no logo" so the mount stays quiet (no unhandled-request noise) — logo behaviour is covered
// elsewhere (ApplicationFormPage.logo.test.tsx).
const LOGO_URL = `*/api/public/landing/:slug/logo`;

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

const server = setupServer(
  http.get(FIELD_CONFIG_URL, () => HttpResponse.json({ data: CONFIG })),
  http.get(LOGO_URL, () => HttpResponse.json({ data: { logo: null } })),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('PublishedApplicationShell — thin published shell (task 5.1)', () => {
  it('fetches GET {slug} and renders the form through the one ApplicationFormRenderer', async () => {
    let requestedSlug: string | null = null;
    server.use(
      http.get(FIELD_CONFIG_URL, ({ params }) => {
        requestedSlug = params.slug as string;
        return HttpResponse.json({ data: CONFIG });
      }),
    );

    render(<PublishedApplicationShell slug="hdcn" apiBaseUrl={BASE} logoBaseUrl={BASE} />);

    // The field-config read was fired for the resolved slug (GET {slug} — spec 14 Task 3).
    await waitFor(() => expect(requestedSlug).toBe('hdcn'));

    // The EXISTING ApplicationFormRenderer rendered the config-driven form (its own test id +
    // the config's single field control) — proving the one renderer is reused, not forked.
    expect(await screen.findByTestId('application-form')).toBeInTheDocument();
    expect(screen.getByTestId('published-application-shell')).toBeInTheDocument();
    expect(screen.getByLabelText(/Voornaam/)).toBeInTheDocument();
  });

  it('renders the non-probeable not-found state when no slug resolves (never a blank page)', async () => {
    // An unresolvable slug → PublicApplicationPage fetches with a forged slug; the 404 arm renders.
    server.use(
      http.get(FIELD_CONFIG_URL, () => new HttpResponse(null, { status: 404 })),
    );

    render(<PublishedApplicationShell slug={null} apiBaseUrl={BASE} logoBaseUrl={BASE} />);

    await waitFor(() =>
      expect(screen.getByTestId('application-state')).toHaveAttribute('data-state', 'not_found'),
    );
    expect(screen.queryByTestId('application-form')).not.toBeInTheDocument();
  });
});

// ============================================================================
// Task 5.2 — rounds out the paired coverage beyond the 5.1 smoke.
// ============================================================================

/**
 * Override the hostname jsdom reports so the shell's real slug resolution path
 * (`resolveApplicationSlug()` → `window.location.hostname`) is exercised, not just the explicit
 * `slug` prop seam. jsdom forbids assigning `window.location.hostname` directly, so redefine the
 * getter (the project convention — see `aws-exports.test.ts`). Returns a restore fn.
 */
function withHostname(hostname: string): () => void {
  const original = window.location;
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...original, hostname, href: `https://${hostname}/`, pathname: '/' },
  });
  return () => {
    Object.defineProperty(window, 'location', { configurable: true, value: original });
  };
}

describe('PublishedApplicationShell — host-based slug resolution + the remaining arms (task 5.2)', () => {
  it('resolves the slug from the host ({slug}.jabaki.nl) and renders through the one renderer', async () => {
    // Deployed published-pages pattern: the slug is the left-most host label. No `slug` prop is
    // passed, so the shell must resolve it from `window.location` via `resolveApplicationSlug`.
    const restore = withHostname('hdcn.jabaki.nl');
    try {
      let requestedSlug: string | null = null;
      server.use(
        http.get(FIELD_CONFIG_URL, ({ params }) => {
          requestedSlug = params.slug as string;
          return HttpResponse.json({ data: CONFIG });
        }),
      );

      render(<PublishedApplicationShell apiBaseUrl={BASE} logoBaseUrl={BASE} />);

      // The field-config read fired for the slug taken from the HOST label — not a prop.
      await waitFor(() => expect(requestedSlug).toBe('hdcn'));
      expect(await screen.findByTestId('application-form')).toBeInTheDocument();
      expect(screen.getByLabelText(/Voornaam/)).toBeInTheDocument();
    } finally {
      restore();
    }
  });

  it('renders the neutral publication-gate (not_available) state when GET {slug} is a 409', async () => {
    // 409 = the tenant is not accepting applications yet (D15/R5.4). The shell must surface the
    // neutral `not_available` state via ApplicationStateMessage — never the form, never the code.
    server.use(
      http.get(FIELD_CONFIG_URL, () =>
        HttpResponse.json({ code: 'errors.application.notAvailable' }, { status: 409 }),
      ),
    );

    render(<PublishedApplicationShell slug="hdcn" apiBaseUrl={BASE} logoBaseUrl={BASE} />);

    await waitFor(() =>
      expect(screen.getByTestId('application-state')).toHaveAttribute('data-state', 'not_available'),
    );
    expect(screen.queryByTestId('application-form')).not.toBeInTheDocument();
  });

  it('renders the generic error state when GET {slug} fails (5xx)', async () => {
    // A transport/server failure (500) must land on the generic error arm — a published page that
    // cannot load its config shows a failure state, never a blank page or the form.
    server.use(
      http.get(FIELD_CONFIG_URL, () => new HttpResponse(null, { status: 500 })),
    );

    render(<PublishedApplicationShell slug="hdcn" apiBaseUrl={BASE} logoBaseUrl={BASE} />);

    await waitFor(() =>
      expect(screen.getByTestId('application-state')).toHaveAttribute('data-state', 'error'),
    );
    expect(screen.queryByTestId('application-form')).not.toBeInTheDocument();
  });
});

describe('mountPublishedApplicationShell — the standalone boot entry (task 5.2)', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('mounts into the page_shell #app-root mount point and returns a root', async () => {
    // The server-rendered page_shell carries a single `#app-root` div; the entry fills it.
    // `PUBLISHED_SHELL_MOUNT_ID` is owned by the shell module (the entry imports it but does not
    // re-export it), so pull the id from its source of truth.
    const { mountPublishedApplicationShell } = await import('../pages/public/publishedShellEntry');
    const { PUBLISHED_SHELL_MOUNT_ID } = await import('../pages/public/PublishedApplicationShell');
    const mount = document.createElement('div');
    mount.id = PUBLISHED_SHELL_MOUNT_ID;
    document.body.appendChild(mount);

    const root = mountPublishedApplicationShell();

    expect(root).not.toBeNull();
    // Clean up the React root to avoid an act() warning leaking into later tests.
    root?.unmount();
  });

  it('returns null (degrades to blank, never throws) when the mount point is absent', async () => {
    // A scaffold missing `#app-root` must not crash the published artifact — just no mount.
    const { mountPublishedApplicationShell } = await import(
      '../pages/public/publishedShellEntry'
    );

    expect(mountPublishedApplicationShell('definitely-not-present')).toBeNull();
  });
});

/**
 * Bug Condition Exploration Test — tenant-switch-stale-roles-menu
 *
 * Property 1: Roles Re-resolved For Active Tenant On Switch.
 *
 * CRITICAL: This test MUST FAIL on the current (unfixed) code. The failure
 * CONFIRMS the bug: an in-app tenant switch (no reload) does not re-resolve
 * `user.roles`, so `MainMenu` keeps gating on the previous tenant's roles.
 *
 * It encodes the EXPECTED (fixed) behavior and will pass once the fix
 * re-resolves roles on `currentTenant` change.
 *
 * Scenario (verified root cause / concrete h-dcn reproduction):
 *   - Global JWT groups include `Tenant_Admin` (present only globally, not on h-dcn).
 *   - `GET /api/auth/me` returns DIFFERENT effective roles per `X-Tenant`:
 *       origin tenant `goodwin` -> includes `Tenant_Admin`, no Members role
 *       `h-dcn`                 -> OMITS `Tenant_Admin`, INCLUDES `Members_CRUD`
 *   - The user switches to `h-dcn` in-app (setCurrentTenant), no reload.
 *
 * Assertions (SHOULD FAIL on unfixed code):
 *   - Over-show (1.2): after switch, `Tenant Administration` (Tenant_Admin) is HIDDEN.
 *   - Under-show (1.3): after switch, `Members Overview` (Members) is SHOWN.
 *   - No refetch on switch (1.1, 1.4): `GET /api/auth/me` is invoked with
 *     `X-Tenant: h-dcn` after the switch.
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4
 */

import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach, vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../i18n';
import { AuthProvider, useAuth } from '../AuthContext';
import { TenantProvider, useTenant } from '../TenantContext';
import { MainMenu } from '../../components/MainMenu';
import { useTenantRoleSync } from '../../hooks/useTenantRoleSync';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ORIGIN_TENANT = 'goodwin';
const HDCN_TENANT = 'h-dcn';
const API_BASE = 'http://localhost:5000';

// Global JWT groups: include Tenant_Admin + SysAdmin (present only globally).
const GLOBAL_GROUPS = ['Tenant_Admin', 'SysAdmin', 'Finance_CRUD'];

// Effective (merged) roles the backend returns per active tenant.
const ROLES_BY_TENANT: Record<string, string[]> = {
  // Origin tenant: user holds Tenant_Admin here (over-shown entry is legit here).
  [ORIGIN_TENANT]: ['Tenant_Admin', 'SysAdmin', 'Finance_CRUD'],
  // h-dcn: NO Tenant_Admin, but a tenant-scoped Members role NOT in the JWT.
  [HDCN_TENANT]: ['SysAdmin', 'Finance_CRUD', 'Members_CRUD'],
};

/** Build a minimal valid base64url JWT carrying the given cognito:groups. */
function makeJwt(groups: string[]): string {
  const b64url = (obj: unknown) =>
    Buffer.from(JSON.stringify(obj))
      .toString('base64')
      .replace(/=/g, '')
      .replace(/\+/g, '-')
      .replace(/\//g, '_');
  const header = b64url({ alg: 'none', typ: 'JWT' });
  const payload = b64url({
    'cognito:groups': groups,
    'custom:tenants': JSON.stringify([ORIGIN_TENANT, HDCN_TENANT]),
    email: 'peter@pgeers.nl',
    name: 'Peter',
    sub: 'user-sub-123',
    exp: Math.floor(Date.now() / 1000) + 3600,
    iat: Math.floor(Date.now() / 1000),
  });
  return `${header}.${payload}.sig`;
}

const ID_TOKEN = makeJwt(GLOBAL_GROUPS);
const ACCESS_TOKEN = makeJwt(GLOBAL_GROUPS);

// ---------------------------------------------------------------------------
// aws-amplify/auth mock — authenticated session so getCurrentUserRoles()
// reaches the GET /api/auth/me fetch (setupTests globally mocks it as
// unauthenticated; we override it here for this file).
// ---------------------------------------------------------------------------

vi.mock('aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(() =>
    Promise.resolve({
      tokens: {
        idToken: { toString: () => ID_TOKEN },
        accessToken: { toString: () => ACCESS_TOKEN },
      },
    })
  ),
  getCurrentUser: vi.fn(() =>
    Promise.resolve({ username: 'peter@pgeers.nl', userId: 'user-sub-123' })
  ),
  signOut: vi.fn(() => Promise.resolve()),
}));

// ---------------------------------------------------------------------------
// Presentational top-bar children that are irrelevant to the role-gated menu
// entries under test. Stubbing them keeps the render focused on the roles
// dimension and avoids unrelated gaps in the shared Chakra test mock
// (e.g. useBreakpointValue used by HelpButton).
// ---------------------------------------------------------------------------

vi.mock('../../components/help', () => ({
  HelpButton: () => null,
}));
vi.mock('../../components/UserMenu', () => ({
  __esModule: true,
  default: () => null,
}));
vi.mock('../../components/LanguageSelector', () => ({
  LanguageSelector: () => null,
}));

// ---------------------------------------------------------------------------
// msw server — GET /api/auth/me keyed on the X-Tenant request header.
// Records the tenants it was asked about so we can assert on the switch fetch.
// ---------------------------------------------------------------------------

const authMeCalls: string[] = [];

const server = setupServer(
  http.get(`${API_BASE}/api/auth/me`, ({ request }) => {
    const tenant = request.headers.get('X-Tenant') || '';
    authMeCalls.push(tenant);
    const roles = ROLES_BY_TENANT[tenant] ?? GLOBAL_GROUPS;
    return HttpResponse.json({ roles });
  })
);

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// Harness: bridges context into MainMenu. Module flags are forced true so the
// compound (module-flag AND role) gate is driven purely by user.roles — the
// dimension this bug is about. A button drives an in-app tenant switch.
// ---------------------------------------------------------------------------

function Harness() {
  const { user, logout } = useAuth();
  const { setCurrentTenant } = useTenant();

  // Wire in the real production bridge (the same hook AppContent uses) so this
  // harness exercises the actual role re-resolution on tenant switch.
  useTenantRoleSync();

  return (
    <>
      <button data-testid="switch-hdcn" onClick={() => setCurrentTenant(HDCN_TENANT)}>
        switch
      </button>
      <MainMenu
        currentPage={'default' as never}
        setCurrentPage={() => { }}
        user={user}
        status={{ mode: 'Test', database: 'testfinance', folder: 'testFacturen' }}
        logout={logout}
        hasFIN={true}
        hasSTR={true}
        hasZZP={true}
        hasMEMBERS={true}
        hasFunction={() => true}
        modulesLoading={false}
        showPasskeyPrompt={false}
        setShowPasskeyPrompt={() => { }}
        dismissPasskeyPrompt={() => { }}
      />
    </>
  );
}

function renderApp() {
  return render(
    <I18nextProvider i18n={i18n}>
      <AuthProvider>
        <TenantProvider>
          <Harness />
        </TenantProvider>
      </AuthProvider>
    </I18nextProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Bug condition: stale roles after in-app tenant switch (h-dcn)', () => {
  beforeEach(() => {
    authMeCalls.length = 0;
    localStorage.clear();
    // Start on the origin tenant, where the user legitimately holds Tenant_Admin.
    localStorage.setItem('selectedTenant', ORIGIN_TENANT);
    i18n.changeLanguage('en');
  });

  it('re-resolves roles on switch to h-dcn: hides Tenant Administration, shows Members Overview, refetches with X-Tenant: h-dcn', async () => {
    const user = userEvent.setup();
    renderApp();

    // Menu labels carry an emoji prefix and are split across text nodes
    // (`{emoji} {t(...)}`), so match on the button's accessible name via regex.
    //
    // The Members entry is a BUTTON labelled `members:overview.navLabel`
    // ("Overview") sitting under a separate "Members" section header
    // (`members:nav.sectionTitle`) — see MainMenu, commit 3a351af96 which
    // deliberately split the shared "Members Overview" name so the header and
    // the item no longer collide. The combined "Members Overview" string now
    // lives only as the page title (`members:overview.title`), not the nav
    // button, so match the button on its real accessible name "Overview".
    const tenantAdminRe = /Tenant Administration/;
    const membersRe = /^👥\s*Overview$/;

    // Baseline: on the origin tenant the user holds Tenant_Admin, so
    // "Tenant Administration" is shown and "Members Overview" is not.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: tenantAdminRe })).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: membersRe })).not.toBeInTheDocument();

    // Act: switch to h-dcn in-app (no reload).
    await user.click(screen.getByTestId('switch-hdcn'));

    // No-refetch-on-switch (1.1, 1.4): /api/auth/me must be re-invoked with
    // X-Tenant: h-dcn after the switch. FAILS on unfixed code (never called).
    await waitFor(() => {
      expect(authMeCalls).toContain(HDCN_TENANT);
    });

    // Over-show (1.2): Tenant Administration must be HIDDEN on h-dcn (user has
    // no Tenant_Admin there). FAILS on unfixed code (stays visible).
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: tenantAdminRe })).not.toBeInTheDocument();
    });

    // Under-show (1.3): Members Overview must be SHOWN on h-dcn (tenant-scoped
    // Members role held there). FAILS on unfixed code (missing).
    expect(screen.getByRole('button', { name: membersRe })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Regression: no infinite render loop (unstable refreshRolesForTenant ref)
//
// Root cause (pre-existing, from commit 6cc86fc "Fix stale roles in menu after
// in-app tenant switch"): `refreshRolesForTenant` in AuthContext was a plain
// function recreated every render, and it calls setUser(...). useTenantRoleSync's
// effect depends on [currentTenant, refreshRolesForTenant], so each render handed
// it a NEW function reference -> effect re-ran -> getCurrentUserRoles() (GET
// /api/auth/me) + setUser -> re-render -> new reference -> ... unbounded loop.
//
// With refreshRolesForTenant wrapped in useCallback([]), its reference is stable
// across renders, so the effect fires only on a REAL currentTenant change. This
// test mounts WITHOUT any tenant switch, lets renders settle, then asserts the
// /api/auth/me call count does NOT keep growing. On the unfixed (looping) code
// the count climbs without bound; on the fixed code it stays flat.
// ---------------------------------------------------------------------------

describe('Regression: no infinite /api/auth/me loop without a tenant switch', () => {
  beforeEach(() => {
    authMeCalls.length = 0;
    localStorage.clear();
    localStorage.setItem('selectedTenant', ORIGIN_TENANT);
    i18n.changeLanguage('en');
  });

  it('does not refetch /api/auth/me unboundedly after mount settles (no switch)', async () => {
    renderApp();

    // Let mount + the mount-tenant role resolution settle: the origin menu
    // (gated on the mount-tenant roles) is rendered once roles are resolved.
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Tenant Administration/ })
      ).toBeInTheDocument();
    });

    // Capture the call count once things have settled.
    const settledCount = authMeCalls.length;

    // Allow any pending renders/effects to flush. On the looping code each flush
    // triggers another refreshRolesForTenant -> /api/auth/me, so the count would
    // keep climbing. Flush several microtask/render cycles deterministically
    // (no real timers/sleeps).
    for (let i = 0; i < 5; i++) {
      await Promise.resolve();
    }
    await waitFor(() => {
      // A stable condition that is already true — gives React a chance to flush
      // any queued state updates/effects before we read the count.
      expect(
        screen.getByRole('button', { name: /Tenant Administration/ })
      ).toBeInTheDocument();
    });

    // The count must NOT have grown — no self-sustaining render loop.
    expect(authMeCalls.length).toBe(settledCount);
  });
});

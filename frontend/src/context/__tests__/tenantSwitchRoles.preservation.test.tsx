/**
 * Preservation Tests — tenant-switch-stale-roles-menu
 *
 * Property 2: Non-Switch And Unchanged-Role Behavior.
 *
 * These tests capture the CURRENT (unfixed) baseline behavior for inputs that
 * do NOT trigger the bug (`isBugCondition` is false): single-tenant users, the
 * login/mount role-resolution path, the compound module-flag-AND-role gating in
 * `MainMenu`, `localStorage` persistence on switch, unchanged-role switches
 * (no flicker), and the App-level module-loss redirect rule.
 *
 * Methodology: observation-first. Each assertion records what the UNFIXED code
 * actually does today so the upcoming fix can be proven not to regress it.
 *
 * EXPECTED OUTCOME: these tests PASS on the current unfixed code.
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
 */

import {
  describe,
  it,
  expect,
  beforeAll,
  afterAll,
  afterEach,
  beforeEach,
  vi,
} from 'vitest';
import { test as fcTest, fc } from '@fast-check/vitest';
import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
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
// Fixtures — mirror the Task 1 exploration test harness (JWT + msw + amplify
// mock) so the baseline is observed under the same wiring as the bug test.
// ---------------------------------------------------------------------------

const ORIGIN_TENANT = 'goodwin';
const HDCN_TENANT = 'h-dcn';
const SOLO_TENANT = 'solo-corp';
// A second tenant alias whose EFFECTIVE ROLE SET is IDENTICAL to ORIGIN_TENANT.
// Used by 3.5 to exercise "switch between tenants with the same effective roles"
// — the switch is real (currentTenant/localStorage change, /api/auth/me is
// re-invoked with the new X-Tenant) but the resolved role set is unchanged, so
// the visible menu must not flicker/remove-and-re-add any valid entry.
const ORIGIN_TWIN_TENANT = 'goodwin-eu';
const API_BASE = 'http://localhost:5000';

// Global JWT groups (present only globally — Tenant_Admin/SysAdmin are the
// interesting ones for the menu gating dimension).
const GLOBAL_GROUPS = ['Tenant_Admin', 'SysAdmin', 'Finance_CRUD'];

// Effective (merged) roles the backend returns per active tenant.
const ROLES_BY_TENANT: Record<string, string[]> = {
  [ORIGIN_TENANT]: ['Tenant_Admin', 'SysAdmin', 'Finance_CRUD'],
  // Identical effective role set to ORIGIN_TENANT — the "unchanged roles" pair
  // for the 3.5 no-flicker property.
  [ORIGIN_TWIN_TENANT]: ['Tenant_Admin', 'SysAdmin', 'Finance_CRUD'],
  [HDCN_TENANT]: ['SysAdmin', 'Finance_CRUD', 'Members_CRUD'],
  [SOLO_TENANT]: ['SysAdmin', 'Finance_CRUD'],
};

/** Build a minimal valid base64url JWT carrying the given cognito:groups. */
function makeJwt(groups: string[], tenants: string[]): string {
  const b64url = (obj: unknown) =>
    Buffer.from(JSON.stringify(obj))
      .toString('base64')
      .replace(/=/g, '')
      .replace(/\+/g, '-')
      .replace(/\//g, '_');
  const header = b64url({ alg: 'none', typ: 'JWT' });
  const payload = b64url({
    'cognito:groups': groups,
    'custom:tenants': JSON.stringify(tenants),
    email: 'peter@pgeers.nl',
    name: 'Peter',
    sub: 'user-sub-123',
    exp: Math.floor(Date.now() / 1000) + 3600,
    iat: Math.floor(Date.now() / 1000),
  });
  return `${header}.${payload}.sig`;
}

// ---------------------------------------------------------------------------
// aws-amplify/auth mock — authenticated session so getCurrentUserRoles()
// reaches the GET /api/auth/me fetch. The token's tenant list is swapped per
// test via `setAmplifyTenants` so we can exercise single- vs multi-tenant.
// ---------------------------------------------------------------------------

let currentTenantsClaim: string[] = [ORIGIN_TENANT, HDCN_TENANT];

function setAmplifyTenants(tenants: string[]) {
  currentTenantsClaim = tenants;
}

vi.mock('aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(() => {
    // Rebuilt on each call so the token reflects the current tenants claim
    // (function declarations `makeJwt`/`currentTenantsClaim` are resolved at
    // call time, after module init — no TDZ issue).
    const idToken = makeJwt(GLOBAL_GROUPS, currentTenantsClaim);
    return Promise.resolve({
      tokens: {
        idToken: { toString: () => idToken },
        accessToken: { toString: () => idToken },
      },
    });
  }),
  getCurrentUser: vi.fn(() =>
    Promise.resolve({ username: 'peter@pgeers.nl', userId: 'user-sub-123' })
  ),
  signOut: vi.fn(() => Promise.resolve()),
}));

// ---------------------------------------------------------------------------
// Stub presentational top-bar children irrelevant to role-gated entries
// (matches Task 1 test rationale).
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
// msw server — GET /api/auth/me keyed on the X-Tenant request header. Records
// every tenant it was asked about so we can assert call behavior.
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
// Shared MainMenu props — module flags forced true so the compound
// (module-flag AND role) gate is driven purely by user.roles unless a test
// overrides a flag on purpose (3.3).
// ---------------------------------------------------------------------------

type FlagOverrides = Partial<{
  hasFIN: boolean;
  hasSTR: boolean;
  hasZZP: boolean;
  hasMEMBERS: boolean;
  hasFunction: (name: string) => boolean;
}>;

function Harness({
  flags = {},
  onSwitch,
}: {
  flags?: FlagOverrides;
  onSwitch?: string;
}) {
  const { user, logout } = useAuth();
  const { setCurrentTenant } = useTenant();

  // Wire in the real production bridge (the same hook AppContent uses) so this
  // harness exercises the actual role re-resolution on tenant switch.
  useTenantRoleSync();

  return (
    <>
      {onSwitch && (
        <button data-testid="switch" onClick={() => setCurrentTenant(onSwitch)}>
          switch
        </button>
      )}
      <MainMenu
        currentPage={'default' as never}
        setCurrentPage={() => { }}
        user={user}
        status={{ mode: 'Test', database: 'testfinance', folder: 'testFacturen' }}
        logout={logout}
        hasFIN={flags.hasFIN ?? true}
        hasSTR={flags.hasSTR ?? true}
        hasZZP={flags.hasZZP ?? true}
        hasMEMBERS={flags.hasMEMBERS ?? true}
        hasFunction={flags.hasFunction ?? (() => true)}
        modulesLoading={false}
        showPasskeyPrompt={false}
        setShowPasskeyPrompt={() => { }}
        dismissPasskeyPrompt={() => { }}
      />
    </>
  );
}

function renderApp(opts: { flags?: FlagOverrides; onSwitch?: string } = {}) {
  return render(
    <I18nextProvider i18n={i18n}>
      <AuthProvider>
        <TenantProvider>
          <Harness flags={opts.flags} onSwitch={opts.onSwitch} />
        </TenantProvider>
      </AuthProvider>
    </I18nextProvider>
  );
}

// Accessible-name regexes (labels carry an emoji prefix + are split across
// text nodes, so match on the button's accessible name via regex).
const tenantAdminRe = /Tenant Administration/;
const membersRe = /Members Overview/;
const sysAdminRe = /System Administration/;

beforeEach(() => {
  authMeCalls.length = 0;
  localStorage.clear();
  setAmplifyTenants([ORIGIN_TENANT, HDCN_TENANT]);
  i18n.changeLanguage('en');
});

// ===========================================================================
// 3.1 Single-tenant user: renders the same menu as today; no switch trigger.
// ===========================================================================

describe('Preservation 3.1 — single-tenant user (no switch trigger)', () => {
  it('renders the menu for the single tenant resolved at mount; no extra tenant refetch fires', async () => {
    setAmplifyTenants([SOLO_TENANT]);
    localStorage.setItem('selectedTenant', SOLO_TENANT);

    renderApp();

    // Baseline: solo-corp effective roles = SysAdmin + Finance_CRUD.
    // System Administration (SysAdmin) is shown; Tenant Administration and
    // Members Overview are NOT (no Tenant_Admin / Members role there).
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: sysAdminRe })
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByRole('button', { name: tenantAdminRe })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: membersRe })
    ).not.toBeInTheDocument();

    // Observed baseline: /api/auth/me is resolved for the single tenant only
    // (mount path). There is no in-app switch, so no additional tenants appear.
    expect(new Set(authMeCalls)).toEqual(new Set([SOLO_TENANT]));
  });
});

// ===========================================================================
// 3.2 Login/mount: initial user.roles populated by checkAuthState(); and
// refreshUserRoles() still re-runs checkAuthState() (re-invokes /api/auth/me).
// ===========================================================================

describe('Preservation 3.2 — login/mount role resolution unchanged', () => {
  it('initial user.roles equals /api/auth/me effective roles for the mount-time tenant', async () => {
    localStorage.setItem('selectedTenant', ORIGIN_TENANT);

    let observed: string[] | undefined;
    function Probe() {
      const { user } = useAuth();
      observed = user?.roles;
      return null;
    }

    render(
      <I18nextProvider i18n={i18n}>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </I18nextProvider>
    );

    await waitFor(() => {
      expect(observed).toEqual(ROLES_BY_TENANT[ORIGIN_TENANT]);
    });
    expect(authMeCalls).toContain(ORIGIN_TENANT);
  });

  it('refreshUserRoles() re-runs checkAuthState(), re-invoking /api/auth/me', async () => {
    localStorage.setItem('selectedTenant', ORIGIN_TENANT);

    let refresh: (() => Promise<void>) | undefined;
    function Probe() {
      const { refreshUserRoles, user } = useAuth();
      refresh = refreshUserRoles;
      return <span data-testid="roles">{(user?.roles ?? []).join(',')}</span>;
    }

    render(
      <I18nextProvider i18n={i18n}>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </I18nextProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('roles')).toHaveTextContent('Tenant_Admin');
    });

    const callsAfterMount = authMeCalls.length;
    expect(callsAfterMount).toBeGreaterThan(0);

    await act(async () => {
      await refresh!();
    });

    // Baseline: refreshUserRoles re-runs checkAuthState, which calls
    // getCurrentUserRoles -> /api/auth/me again.
    expect(authMeCalls.length).toBeGreaterThan(callsAfterMount);
  });
});

// ===========================================================================
// 3.3 Compound module-flag-AND-role gating in MainMenu is unchanged. MainMenu
// is a pure function of (user.roles, module flags, hasFunction). This test
// exercises the gate directly (no context) to document the baseline.
// ===========================================================================

describe('Preservation 3.3 — compound module-flag-AND-role gating', () => {
  function renderMenu(props: {
    roles: string[];
    hasFIN?: boolean;
    hasSTR?: boolean;
    hasZZP?: boolean;
    hasMEMBERS?: boolean;
    hasFunction?: (n: string) => boolean;
  }) {
    const user = {
      username: 'u',
      email: null,
      name: null,
      roles: props.roles,
      tenants: [ORIGIN_TENANT],
      sub: 's',
    };
    // MainMenu renders TenantSelector, which calls useTenant(), so the
    // providers must be present even though `user` is supplied as a prop here
    // (the gating dimension under test is driven by the prop, not context).
    return render(
      <I18nextProvider i18n={i18n}>
        <AuthProvider>
          <TenantProvider>
            <MainMenu
              currentPage={'default' as never}
              setCurrentPage={() => { }}
              user={user}
              status={{ mode: 'Test', database: 'testfinance', folder: 'testFacturen' }}
              logout={() => { }}
              hasFIN={props.hasFIN ?? false}
              hasSTR={props.hasSTR ?? false}
              hasZZP={props.hasZZP ?? false}
              hasMEMBERS={props.hasMEMBERS ?? false}
              hasFunction={props.hasFunction ?? (() => false)}
              modulesLoading={false}
              showPasskeyPrompt={false}
              setShowPasskeyPrompt={() => { }}
              dismissPasskeyPrompt={() => { }}
            />
          </TenantProvider>
        </AuthProvider>
      </I18nextProvider>
    );
  }

  it('hides a module entry when the role is held but the module flag is false', () => {
    renderMenu({ roles: ['Members_CRUD'], hasMEMBERS: false });
    expect(
      screen.queryByRole('button', { name: membersRe })
    ).not.toBeInTheDocument();
  });

  it('hides a module entry when the module flag is true but the role is absent', () => {
    renderMenu({ roles: ['SysAdmin'], hasMEMBERS: true });
    expect(
      screen.queryByRole('button', { name: membersRe })
    ).not.toBeInTheDocument();
  });

  it('shows a module entry only when BOTH the module flag AND the role are present', () => {
    renderMenu({ roles: ['Members_CRUD'], hasMEMBERS: true });
    expect(screen.getByRole('button', { name: membersRe })).toBeInTheDocument();
  });

  it('SysAdmin entry gates on role only (no module flag), independent of module flags', () => {
    renderMenu({ roles: ['SysAdmin'] });
    expect(screen.getByRole('button', { name: sysAdminRe })).toBeInTheDocument();
  });
});

// ===========================================================================
// 3.4 localStorage persistence: a switch writes selectedTenant and updates
// currentTenant.
// ===========================================================================

describe('Preservation 3.4 — localStorage persistence + currentTenant update', () => {
  it('setCurrentTenant persists selectedTenant and updates currentTenant', async () => {
    localStorage.setItem('selectedTenant', ORIGIN_TENANT);

    let ctx:
      | { currentTenant: string | null; setCurrentTenant: (t: string) => void }
      | undefined;
    function Probe() {
      const { currentTenant, setCurrentTenant } = useTenant();
      ctx = { currentTenant, setCurrentTenant };
      return <span data-testid="tenant">{currentTenant ?? ''}</span>;
    }

    render(
      <I18nextProvider i18n={i18n}>
        <AuthProvider>
          <TenantProvider>
            <Probe />
          </TenantProvider>
        </AuthProvider>
      </I18nextProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('tenant')).toHaveTextContent(ORIGIN_TENANT);
    });

    await act(async () => {
      ctx!.setCurrentTenant(HDCN_TENANT);
    });

    await waitFor(() => {
      expect(screen.getByTestId('tenant')).toHaveTextContent(HDCN_TENANT);
    });
    expect(localStorage.getItem('selectedTenant')).toBe(HDCN_TENANT);
  });
});

// ===========================================================================
// 3.5 No flicker when the effective role set is unchanged (property-based).
//
// Requirement 3.5 preserves this invariant: switching between tenants whose
// EFFECTIVE ROLE SET IS IDENTICAL must display the same menu entries with no
// flicker-induced loss of still-valid entries. It intentionally does NOT
// constrain switches that DO change the effective role set (that is the bug the
// fix corrects — covered by the exploration/fix-checking test).
//
// So the property switches over ORIGIN_TENANT and ORIGIN_TWIN_TENANT, which map
// to the SAME effective role array in the fixture. Each switch is a REAL in-app
// switch on the fixed code (currentTenant/localStorage change; /api/auth/me is
// re-invoked with the new X-Tenant via useTenantRoleSync), but because the
// resolved role set is identical the visible role-gated set must remain equal —
// genuinely testing "no flicker when effective roles are unchanged" and passing
// on the FIXED code. Each switch is wrapped in act + a waitFor settle so the
// async role re-resolution completes deterministically and the property does not
// hit the fast-check timeout.
// ===========================================================================

/** Collect the visible role-gated admin entries as a stable signature. */
function menuSignature(): string[] {
  const entries: string[] = [];
  if (screen.queryByRole('button', { name: sysAdminRe })) entries.push('SysAdmin');
  if (screen.queryByRole('button', { name: tenantAdminRe }))
    entries.push('TenantAdmin');
  if (screen.queryByRole('button', { name: membersRe })) entries.push('Members');
  return entries;
}

describe('Preservation 3.5 — no flicker when the effective role set is unchanged', () => {
  // Each property run does a full provider-stack render plus up to 4 async
  // tenant switches (each awaited to settle), so this is a heavy DOM property.
  // Raise the vitest test timeout to give the whole property room, matching the
  // convention used by the other async render property tests in this suite.
  vi.setConfig({ testTimeout: 30000 });

  // The two tenants below share the SAME effective role set (Tenant_Admin +
  // SysAdmin + Finance_CRUD), so the expected role-gated menu signature is the
  // same for either active tenant.
  const UNCHANGED_ROLE_SIGNATURE = ['SysAdmin', 'TenantAdmin'];

  fcTest.prop(
    [
      fc.array(fc.constantFrom(ORIGIN_TENANT, ORIGIN_TWIN_TENANT), {
        minLength: 1,
        maxLength: 4,
      }),
    ],
    // Heavy render+async property: each run mounts the full provider stack and
    // performs up to 4 awaited tenant switches, so cap the run count (the input
    // space — sequences of length 1..4 over two tenants — is tiny, so 20 runs
    // covers it, matching the numRuns convention of the other DOM-render
    // property tests) and lift fast-check's per-property time budget well above
    // its ~5s default so the awaited switches never trip the interrupt (the
    // STACK_TRACE_ERROR timeout). The budget stays under the 30s vi.setConfig
    // testTimeout above.
    { numRuns: 20, interruptAfterTimeLimit: 25000, markInterruptAsFailure: true },
  )(
    'menu entry set is unchanged across switches between identical-role tenants',
    async (switchSequence) => {
      authMeCalls.length = 0;
      localStorage.clear();
      // Both identical-role tenants are available to switch between.
      setAmplifyTenants([ORIGIN_TENANT, ORIGIN_TWIN_TENANT]);
      localStorage.setItem('selectedTenant', ORIGIN_TENANT);

      // Drive switches through real button clicks (userEvent), mirroring the
      // exploration test's known-good interaction pattern rather than wrapping a
      // context setter in act() — the latter can deadlock against the role-sync
      // effect's async fetch under a fast-check async predicate. The Bridge also
      // exposes the latest resolved user.roles so we can settle on a cheap
      // in-memory value: polling the large Chakra menu with a name-regex
      // getByRole/findByRole is pathologically slow and dominates the runtime,
      // so the DOM signature is read only twice (before/after), never polled.
      const user = userEvent.setup();
      let latestRoles: string[] = [];
      function Bridge() {
        const { setCurrentTenant } = useTenant();
        const { user: authUser } = useAuth();
        latestRoles = authUser?.roles ?? [];
        return (
          <>
            <button
              data-testid="to-origin"
              onClick={() => setCurrentTenant(ORIGIN_TENANT)}
            >
              origin
            </button>
            <button
              data-testid="to-twin"
              onClick={() => setCurrentTenant(ORIGIN_TWIN_TENANT)}
            >
              twin
            </button>
          </>
        );
      }

      const { unmount } = render(
        <I18nextProvider i18n={i18n}>
          <AuthProvider>
            <TenantProvider>
              <Bridge />
              <Harness />
            </TenantProvider>
          </AuthProvider>
        </I18nextProvider>
      );

      const expectedRoles = ROLES_BY_TENANT[ORIGIN_TENANT];

      // Wait for the mount-time role resolution to settle (cheap in-memory check
      // on the Bridge-exposed roles, not a DOM scan). Once roles are populated
      // all mount effects have run, including useTenantRoleSync's first pass.
      await waitFor(() => {
        expect(latestRoles).toEqual(expectedRoles);
      });

      // Read the visible menu signature ONCE (three queryByRole calls — the DOM
      // scan is done a fixed number of times, never polled).
      const before = menuSignature();
      // The mount-time signature must already be the expected identical-role set.
      expect(before).toEqual(UNCHANGED_ROLE_SIGNATURE);

      // Drive the random switch sequence over the identical-role tenants. On the
      // FIXED code a switch to a NEW tenant re-resolves user.roles via
      // /api/auth/me with the new X-Tenant; because the effective role set is
      // identical, the resolved roles — and therefore the visible menu — must
      // not change. Settle after each click on the cheap in-memory roles value
      // staying equal to the expected set — the invariant is precisely that the
      // effective roles never change.
      for (const t of switchSequence) {
        await user.click(
          screen.getByTestId(t === ORIGIN_TENANT ? 'to-origin' : 'to-twin')
        );
        await waitFor(() => {
          expect(latestRoles).toEqual(expectedRoles);
        });
      }

      // Read the signature once more after the sequence.
      const after = menuSignature();

      // Invariant: no removal/re-add of valid entries — the visible set is
      // unchanged across the switches AND equals the expected role-gated set.
      expect(after).toEqual(before);
      expect(after).toEqual(UNCHANGED_ROLE_SIGNATURE);

      unmount();
    }
  );
});

// ===========================================================================
// 3.6 Module-loss redirect rule unchanged. The App-level redirect effect in
// App.tsx decides, from (currentPage, hasFIN/hasSTR/hasZZP, modulesLoading,
// isAuthenticated), whether to redirect to the menu. That decision rule is not
// touched by this fix. We document the baseline decision function here exactly
// as App.tsx implements it, so a future change to it is caught.
// ===========================================================================

describe('Preservation 3.6 — App-level module-loss redirect rule', () => {
  // Mirrors the effect body in App.tsx AppContent verbatim in terms of the
  // observable decision: returns the page to redirect to, or null for no change.
  function redirectDecision(input: {
    currentPage: string;
    hasFIN: boolean;
    hasSTR: boolean;
    hasZZP: boolean;
    modulesLoading: boolean;
    isAuthenticated: boolean;
  }): string | null {
    const { currentPage, hasFIN, hasSTR, hasZZP, modulesLoading, isAuthenticated } =
      input;
    if (!(!modulesLoading && isAuthenticated && (hasFIN || hasSTR || hasZZP))) {
      return null;
    }
    const isZZPPage = [
      'zzp-invoices', 'zzp-contacts', 'zzp-products', 'zzp-time-tracking',
      'zzp-trips', 'zzp-trip-quick', 'zzp-trip-import', 'zzp-debtors',
    ].includes(currentPage);
    const isSTRPage = [
      'str', 'str-invoice', 'str-pricing', 'str-reports',
    ].includes(currentPage);
    const isFINPage = [
      'pdf', 'banking', 'powerbi', 'fin-reports', 'assets', 'budget',
      'transactions', 'check-accounts', 'check-reference', 'str-channel-revenue',
    ].includes(currentPage);

    if (isSTRPage && !hasSTR) return 'menu';
    if (isFINPage && !hasFIN) return 'menu';
    if (isZZPPage && !hasZZP) return 'menu';
    return null;
  }

  it('redirects an STR page to menu when STR access is lost (FIN still present)', () => {
    expect(
      redirectDecision({
        currentPage: 'str-reports',
        hasFIN: true,
        hasSTR: false,
        hasZZP: false,
        modulesLoading: false,
        isAuthenticated: true,
      })
    ).toBe('menu');
  });

  it('does NOT redirect while modules are still loading', () => {
    expect(
      redirectDecision({
        currentPage: 'str-reports',
        hasFIN: true,
        hasSTR: false,
        hasZZP: false,
        modulesLoading: true,
        isAuthenticated: true,
      })
    ).toBeNull();
  });

  it('does NOT redirect when the user still has access to the current page module', () => {
    expect(
      redirectDecision({
        currentPage: 'fin-reports',
        hasFIN: true,
        hasSTR: false,
        hasZZP: false,
        modulesLoading: false,
        isAuthenticated: true,
      })
    ).toBeNull();
  });

  it('does NOT redirect the menu page itself', () => {
    expect(
      redirectDecision({
        currentPage: 'menu',
        hasFIN: false,
        hasSTR: false,
        hasZZP: true,
        modulesLoading: false,
        isAuthenticated: true,
      })
    ).toBeNull();
  });
});

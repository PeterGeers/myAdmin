/**
 * TenantAdminDashboard — "Application form" Members sub-tab wiring
 * (application-form-builder task 2.2 — paired test, per `33-frontend-testing`).
 *
 * Task 2.2 wires a FOURTH sub-tab into the Members nested <Tabs> inside the
 * `hasMembers` TabPanel: a <Tab data-testid="members-admin-application-form-tab">
 * with a bilingual label ("Aanmeldformulier" / "Application form") and a matching
 * <TabPanel> rendering <ApplicationFormBuilder tenant={currentTenant} />.
 *
 * These assertions cover the OBSERVABLE wiring this task owns (R1.1 / R1.4):
 *   1. the 4th tab renders (with its testid) as a SIBLING of the existing
 *      Field-configuration / Mail sub-tabs, ONLY under `hasMembers`;
 *   2. its label is bilingual — "Application form" (en) / "Aanmeldformulier" (nl);
 *   3. selecting it mounts the ApplicationFormBuilder with the current tenant;
 *   4. when the tenant does NOT have MEMBERS, the whole Members area (and thus the
 *      application-form tab) is absent.
 *
 * House pattern: the dashboard pulls in many heavy children + an auth/session load, so
 * this test MOCKS at the module boundary (mirroring the sibling TenantAdmin/Members
 * component tests): the `./MembersConfig` barrel (incl. `ApplicationFormBuilder`, whose
 * real component is authored by the concurrent task 2.1) and the other panel children are
 * stubbed to lightweight markers; `aws-amplify/auth`, the tenant context, the api service
 * and i18n are stubbed so the admin-guard + module-gate resolve deterministically.
 *
 * **Validates: Requirements 1.1, 1.4**
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '../../../test-utils';

/* ------------------------------------------------------------------ */
/*  i18n — deterministic language + a passthrough `t`.                 */
/*  `membersLang` in the dashboard is driven by i18n.language.         */
/* ------------------------------------------------------------------ */
let mockLanguage = 'en';
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    // The top-level tab labels use the `t(key, fallback)` form; return the fallback
    // when present so labels are stable, else echo the key.
    t: (key: string, fallback?: string) => fallback ?? key,
    i18n: { language: mockLanguage },
  }),
}));

/* ------------------------------------------------------------------ */
/*  Tenant context — a fixed current tenant.                           */
/* ------------------------------------------------------------------ */
vi.mock('../../../context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 't-1' }),
}));

/* ------------------------------------------------------------------ */
/*  Auth session — a Tenant_Admin id token; the dashboard decodes the  */
/*  JWT for custom:tenants then calls /api/auth/me for merged roles.   */
/* ------------------------------------------------------------------ */
function makeIdToken(tenants: string[]): string {
  const header = btoa(JSON.stringify({ alg: 'none', typ: 'JWT' }));
  const payload = btoa(JSON.stringify({ 'custom:tenants': JSON.stringify(tenants) }));
  return `${header}.${payload}.sig`;
}

vi.mock('aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(() =>
    Promise.resolve({
      tokens: { idToken: { toString: () => makeIdToken(['t-1']) } },
    }),
  ),
}));

/* ------------------------------------------------------------------ */
/*  API service — /api/auth/me returns Tenant_Admin; /api/tenant/modules*/
/*  returns the available-modules set that drives hasMembers.          */
/* ------------------------------------------------------------------ */
let mockAvailableModules: string[] = ['MEMBERS'];
vi.mock('../../../services/apiService', () => ({
  buildEndpoint: (endpoint: string) => endpoint,
  authenticatedGet: vi.fn((endpoint: string) => {
    if (endpoint.startsWith('/api/auth/me')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ roles: ['Tenant_Admin'] }),
      });
    }
    if (endpoint.startsWith('/api/tenant/modules')) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            tenant: 't-1',
            available_modules: mockAvailableModules,
            user_module_permissions: [],
            tenant_enabled_modules: mockAvailableModules,
          }),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  }),
}));

/* ------------------------------------------------------------------ */
/*  Child stubs — mark each surface so we can assert which one mounts   */
/*  without pulling its real tree (and its own network) into scope.     */
/*  The `./MembersConfig` barrel is stubbed INCLUDING ApplicationFormBuilder*/
/*  (authored by the concurrent task 2.1) so this test asserts the WIRING.*/
/* ------------------------------------------------------------------ */
vi.mock('../MembersConfig', () => ({
  MembersConfigEditor: () => <div data-testid="stub-members-config-editor" />,
  MembersMailConfigEditor: () => <div data-testid="stub-members-mail-editor" />,
  ApplicationFormBuilder: ({ tenant }: { tenant: string }) => (
    <div data-testid="stub-application-form-builder">builder:{tenant}</div>
  ),
}));

vi.mock('../UserManagement', () => ({ default: () => <div data-testid="stub-users" /> }));
vi.mock('../FunctionsTab', () => ({ default: () => <div data-testid="stub-functions" /> }));
vi.mock('../FinancialTab', () => ({ default: () => <div data-testid="stub-financial" /> }));
vi.mock('../StorageTab', () => ({ default: () => <div data-testid="stub-storage" /> }));
vi.mock('../TenantInfoTab', () => ({ default: () => <div data-testid="stub-tenant-info" /> }));
vi.mock('../SenderSettingsTab', () => ({ default: () => <div data-testid="stub-sender" /> }));
vi.mock('../MemberSenderIdentitiesTab', () => ({
  default: () => <div data-testid="stub-member-sender" />,
}));
vi.mock('../AdvancedTab', () => ({ default: () => <div data-testid="stub-advanced" /> }));
vi.mock('../TemplateManagement/TemplateManagement', () => ({
  default: () => <div data-testid="stub-templates" />,
}));
vi.mock('../LandingPage', () => ({ LandingPageEditor: () => <div data-testid="stub-landing" /> }));
vi.mock('../../pivot/PivotBuilderWithPreview', () => ({
  PivotBuilderWithPreview: () => <div data-testid="stub-pivot" />,
}));
vi.mock('../../../pages/MediaAssetAdminPage', () => ({
  default: () => <div data-testid="stub-media" />,
}));

import { TenantAdminDashboard } from '../TenantAdminDashboard';

beforeEach(() => {
  mockLanguage = 'en';
  mockAvailableModules = ['MEMBERS'];
  vi.clearAllMocks();
});

describe('TenantAdminDashboard — Application form Members sub-tab (task 2.2, R1.1/R1.4)', () => {
  it('renders the 4th sub-tab with the testid + English label, alongside the existing three', async () => {
    render(<TenantAdminDashboard />);

    // Admin guard + module gate resolve → the Members sub-tabs mount.
    const appFormTab = await screen.findByTestId('members-admin-application-form-tab');
    expect(appFormTab).toBeInTheDocument();
    expect(appFormTab).toHaveTextContent('Application form');

    // It is a SIBLING of the existing Field-configuration + Mail sub-tabs (R1.1).
    expect(screen.getByTestId('members-admin-mail-tab')).toBeInTheDocument();
  });

  it('uses the Dutch label when the language is nl (bilingual — R1.4)', async () => {
    mockLanguage = 'nl';
    render(<TenantAdminDashboard />);

    const appFormTab = await screen.findByTestId('members-admin-application-form-tab');
    expect(appFormTab).toHaveTextContent('Aanmeldformulier');
  });

  it('selecting the tab mounts ApplicationFormBuilder with the current tenant', async () => {
    render(<TenantAdminDashboard />);

    const appFormTab = await screen.findByTestId('members-admin-application-form-tab');
    fireEvent.click(appFormTab);

    const builder = await screen.findByTestId('stub-application-form-builder');
    expect(builder).toBeInTheDocument();
    // The current tenant from context is passed through (one-tenant isolation).
    expect(builder).toHaveTextContent('builder:t-1');
  });

  it('does NOT render the application-form tab when the tenant lacks MEMBERS (hasMembers gate)', async () => {
    mockAvailableModules = ['FIN']; // no MEMBERS
    render(<TenantAdminDashboard />);

    // Wait for the dashboard to settle (a non-Members top-level surface is present).
    await screen.findByTestId('stub-storage');
    expect(
      screen.queryByTestId('members-admin-application-form-tab'),
    ).not.toBeInTheDocument();
  });
});

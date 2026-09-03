import { lazy } from 'react';

// Lazily-loaded page/route components and the shared PageType union.
// Extracted from App.tsx to keep the root component focused on layout and
// navigation wiring. Import paths and component identities are unchanged.

// FIN module pages
export const PDFUploadForm = lazy(() => import('./components/PDFUploadForm'));
export const BankingProcessor = lazy(() => import('./components/BankingProcessor'));
export const FINReports = lazy(() => import('./components/FINReports'));
export const AssetList = lazy(() => import('./components/Assets/AssetList'));
export const BudgetPage = lazy(() => import('./pages/BudgetPage'));
export const TransactionsPage = lazy(() => import('./pages/TransactionsPage'));
export const CheckAccountsPage = lazy(() => import('./pages/CheckAccountsPage'));
export const CheckReferencePage = lazy(() => import('./pages/CheckReferencePage'));
export const STRChannelRevenuePage = lazy(() => import('./pages/STRChannelRevenuePage'));

// STR module pages
export const STRProcessor = lazy(() => import('./components/STRProcessor'));
export const STRInvoice = lazy(() => import('./components/STRInvoice'));
export const STRPricing = lazy(() => import('./components/STRPricing'));
export const STRReports = lazy(() => import('./components/STRReports'));

// ZZP module pages
export const ZZPContacts = lazy(() => import('./pages/ZZPContacts'));
export const ZZPProducts = lazy(() => import('./pages/ZZPProducts'));
export const ZZPInvoices = lazy(() => import('./pages/ZZPInvoices'));
export const ZZPTimeTracking = lazy(() => import('./pages/ZZPTimeTracking'));
export const ZZPTrips = lazy(() => import('./pages/ZZPTrips'));
export const ZZPDebtors = lazy(() => import('./pages/ZZPDebtors'));
export const ZZPTripQuick = lazy(() => import('./pages/ZZPTripQuick'));
export const ZZPTripImport = lazy(() => import('./pages/ZZPTripImport'));

// Admin pages (named exports)
export const TenantAdminDashboard = lazy(() =>
  import('./components/TenantAdmin/TenantAdminDashboard').then(m => ({
    default: m.TenantAdminDashboard,
  }))
);
export const SysAdminDashboard = lazy(() =>
  import('./components/SysAdmin/SysAdminDashboard').then(m => ({
    default: m.SysAdminDashboard,
  }))
);

// Admin pages (default exports)
export const PasskeySettings = lazy(() => import('./components/settings/PasskeySettings'));

// Public pages (no auth required)
export const PublicLandingPage = lazy(() => import('./pages/public/PublicLandingPage'));

export type PageType =
  | 'login'
  | 'menu'
  | 'pdf'
  | 'banking'
  | 'str'
  | 'str-invoice'
  | 'str-pricing'
  | 'powerbi'
  | 'fin-reports'
  | 'str-reports'
  | 'system-admin'
  | 'tenant-admin'
  | 'settings'
  | 'assets'
  | 'zzp-invoices'
  | 'zzp-contacts'
  | 'zzp-products'
  | 'zzp-time-tracking'
  | 'zzp-trips'
  | 'zzp-trip-quick'
  | 'zzp-trip-import'
  | 'zzp-debtors'
  | 'budget'
  | 'transactions'
  | 'check-accounts'
  | 'check-reference'
  | 'str-channel-revenue'
  | 'media-asset-admin';

// URL path → page mapping for PWA deep-link support.
// Supports both dev (/) and production (/myAdmin/) base paths.
export const urlPageMap: Record<string, PageType> = {
  '/zzp/ritten/quick': 'zzp-trip-quick',
  '/zzp/ritten': 'zzp-trips',
  '/zzp/ritten/import': 'zzp-trip-import',
  '/zzp/facturen': 'zzp-invoices',
  '/zzp/contacten': 'zzp-contacts',
  '/zzp/producten': 'zzp-products',
  '/zzp/urenregistratie': 'zzp-time-tracking',
  '/zzp/debiteuren': 'zzp-debtors',
  '/banking': 'banking',
  '/budget': 'budget',
  '/fin/transactions': 'transactions',
  '/fin/check-accounts': 'check-accounts',
  '/fin/check-reference': 'check-reference',
  '/fin/str-channel-revenue': 'str-channel-revenue',
  '/admin/assets': 'media-asset-admin',
};

// Resolve the current window location to a PageType, honoring the base path.
export function resolveInitialPage(): PageType {
  const basePath = import.meta.env.BASE_URL?.replace(/\/$/, '') || '';
  const path = window.location.pathname.startsWith(basePath)
    ? window.location.pathname.slice(basePath.length) || '/'
    : window.location.pathname;
  return urlPageMap[path] || 'menu';
}

/**
 * PageType-to-docs mapping for in-app help.
 * 
 * Documentation is served by MkDocs via the backend at /docs/.
 * The help drawer embeds the MkDocs site in an iframe.
 */

import i18n from 'i18next';

const API_URL = process.env.REACT_APP_API_URL || '';
const DOCS_PATH = '/docs';

/** Maps PageType values to MkDocs documentation sections */
export const helpLinks: Record<string, string> = {
  'banking':      'banking/',
  'bank-connect': 'banking/',
  'pdf':          'invoices/',
  'str':          'str/',
  'str-invoice':  'str/',
  'str-pricing':  'str-pricing/',
  'str-reports':  'str/revenue-summaries/',
  'fin-reports':  'reports/',
  'powerbi':      'reports/dashboards/',
  'assets':       'reports/',
  'system-admin': 'admin/',
  'tenant-admin': 'tenant-admin/',
  'settings':     'tenant-admin/tenant-settings/',
  'migration':    'admin/',
  'zzp-invoices': 'zzp/',
  'zzp-contacts': 'zzp/contacts/',
  'zzp-products': 'zzp/products/',
  'zzp-time':     'zzp/time-tracking/',
  'zzp-debtors':  'zzp/debtors/',
  'menu':         '',
};

/** Get current language from the app's i18n (not browser setting) */
export const getDocsLanguage = (): string => {
  const lang = i18n.language || 'nl';
  return lang.startsWith('nl') ? 'nl' : 'en';
};

/** Get the full MkDocs URL for a given page */
export const getHelpUrl = (page: string): string => {
  const lang = getDocsLanguage();
  const langPrefix = lang === 'nl' ? '' : '/en';
  const section = helpLinks[page] || '';
  return `${API_URL}${DOCS_PATH}${langPrefix}/${section}`;
};

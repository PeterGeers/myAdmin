/**
 * i18n Configuration
 * 
 * Configures internationalization for the myAdmin application using i18next.
 * Supports Dutch (nl) and English (en) with automatic language detection.
 * 
 * @module i18n
 * 
 * Features:
 * - Automatic language detection from localStorage or browser settings
 * - 8 translation namespaces for organized translations
 * - Fallback to English if translation not found
 * - Persistent language preference in localStorage
 * 
 * Namespaces:
 * - common: Shared UI elements (buttons, labels, messages)
 * - auth: Authentication and login
 * - reports: Financial reports and analytics
 * - str: Short-term rental features
 * - banking: Banking and transaction features
 * - admin: Administration and settings
 * - errors: Error messages
 * - validation: Form validation messages
 * 
 * Usage:
 * ```typescript
 * import i18n from './i18n';
 * 
 * // Change language
 * i18n.changeLanguage('nl');
 * 
 * // Get current language
 * const currentLang = i18n.language;
 * ```
 * 
 * @see {@link https://www.i18next.com/|i18next Documentation}
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// Import translation files
import commonNl from './locales/nl/common.json';
import commonEn from './locales/en/common.json';
import authNl from './locales/nl/auth.json';
import authEn from './locales/en/auth.json';
import reportsNl from './locales/nl/reports.json';
import reportsEn from './locales/en/reports.json';
import strNl from './locales/nl/str.json';
import strEn from './locales/en/str.json';
import bankingNl from './locales/nl/banking.json';
import bankingEn from './locales/en/banking.json';
import adminNl from './locales/nl/admin.json';
import adminEn from './locales/en/admin.json';
import financeNl from './locales/nl/finance.json';
import financeEn from './locales/en/finance.json';
import errorsNl from './locales/nl/errors.json';
import errorsEn from './locales/en/errors.json';
import validationNl from './locales/nl/validation.json';
import validationEn from './locales/en/validation.json';
import zzpNl from './locales/nl/zzp.json';
import zzpEn from './locales/en/zzp.json';

/**
 * Initialize i18next with configuration
 * 
 * Configuration:
 * - resources: Translation files for nl and en
 * - fallbackLng: 'en' - Used when translation not found
 * - defaultNS: 'common' - Default namespace if not specified
 * - interpolation.escapeValue: false - React handles escaping
 * - detection: Language detection from localStorage or browser
 */
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      nl: {
        common: commonNl,
        auth: authNl,
        reports: reportsNl,
        str: strNl,
        banking: bankingNl,
        admin: adminNl,
        finance: financeNl,
        errors: errorsNl,
        validation: validationNl,
        zzp: zzpNl,
      },
      en: {
        common: commonEn,
        auth: authEn,
        reports: reportsEn,
        str: strEn,
        banking: bankingEn,
        admin: adminEn,
        finance: financeEn,
        errors: errorsEn,
        validation: validationEn,
        zzp: zzpEn,
      }
    },
    fallbackLng: 'en',
    defaultNS: 'common',
    interpolation: {
      escapeValue: false // React already escapes
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'i18nextLng'
    }
  });

export default i18n;

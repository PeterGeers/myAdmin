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
import errorsNl from './locales/nl/errors.json';
import errorsEn from './locales/en/errors.json';
import validationNl from './locales/nl/validation.json';
import validationEn from './locales/en/validation.json';

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
        errors: errorsNl,
        validation: validationNl,
      },
      en: {
        common: commonEn,
        auth: authEn,
        reports: reportsEn,
        str: strEn,
        banking: bankingEn,
        admin: adminEn,
        errors: errorsEn,
        validation: validationEn,
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

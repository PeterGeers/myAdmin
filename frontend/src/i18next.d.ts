import 'i18next';

// Import translation resources
import common from './locales/en/common.json';
import auth from './locales/en/auth.json';
import reports from './locales/en/reports.json';
import str from './locales/en/str.json';
import banking from './locales/en/banking.json';
import admin from './locales/en/admin.json';
import errors from './locales/en/errors.json';
import validation from './locales/en/validation.json';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'common';
    resources: {
      common: typeof common;
      auth: typeof auth;
      reports: typeof reports;
      str: typeof str;
      banking: typeof banking;
      admin: typeof admin;
      errors: typeof errors;
      validation: typeof validation;
    };
  }
}

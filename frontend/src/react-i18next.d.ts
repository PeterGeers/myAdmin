// TypeScript definitions for react-i18next with namespace support
import 'react-i18next';

declare module 'react-i18next' {
  interface CustomTypeOptions {
    defaultNS: 'common';
    resources: {
      common: any;
      auth: any;
      reports: any;
      str: any;
      banking: any;
      admin: any;
      errors: any;
      validation: any;
    };
  }
}

/**
 * Typed Translation Hook
 * 
 * Type-safe wrapper for react-i18next's useTranslation hook with namespace support.
 * Provides access to translation functions and i18n instance.
 * 
 * @module hooks/useTypedTranslation
 */

import { useTranslation as useTranslationOriginal } from 'react-i18next';

/**
 * Typed wrapper for useTranslation that accepts namespace parameter.
 * 
 * This hook provides type-safe access to translations with namespace support.
 * It's a workaround for TypeScript type definition issues with Create React App.
 * 
 * @param namespace - Translation namespace to use (e.g., 'common', 'auth', 'reports')
 * @returns Translation object with t function and i18n instance
 * 
 * Available namespaces:
 * - common: Shared UI elements (buttons, labels, messages)
 * - auth: Authentication and login
 * - reports: Financial reports and analytics
 * - str: Short-term rental features
 * - banking: Banking and transaction features
 * - admin: Administration and settings
 * - errors: Error messages
 * - validation: Form validation messages
 * 
 * @example
 * ```typescript
 * import { useTypedTranslation } from '../hooks/useTypedTranslation';
 * 
 * function MyComponent() {
 *   const { t, i18n } = useTypedTranslation('common');
 *   
 *   return (
 *     <div>
 *       <h1>{t('welcome.title')}</h1>
 *       <p>{t('welcome.message', { name: 'John' })}</p>
 *       <p>Current language: {i18n.language}</p>
 *     </div>
 *   );
 * }
 * ```
 * 
 * @example
 * ```typescript
 * // With interpolation
 * const { t } = useTypedTranslation('common');
 * t('welcome.message', { name: 'John' }); // "Welcome, John!"
 * 
 * // Change language
 * const { i18n } = useTypedTranslation('common');
 * i18n.changeLanguage('nl');
 * 
 * // Get current language
 * const currentLang = i18n.language; // 'nl' or 'en'
 * ```
 * 
 * @see {@link https://react.i18next.com/latest/usetranslation-hook|useTranslation Documentation}
 */
export function useTypedTranslation(namespace?: string) {
  // @ts-ignore - TypeScript doesn't recognize namespace parameter but it works at runtime
  return useTranslationOriginal(namespace);
}

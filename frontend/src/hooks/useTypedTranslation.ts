import { useTranslation as useTranslationOriginal } from 'react-i18next';

/**
 * Typed wrapper for useTranslation that accepts namespace parameter
 * This is a workaround for TypeScript type definition issues with CRA
 */
export function useTypedTranslation(namespace?: string) {
  // @ts-ignore - TypeScript doesn't recognize namespace parameter but it works at runtime
  return useTranslationOriginal(namespace);
}

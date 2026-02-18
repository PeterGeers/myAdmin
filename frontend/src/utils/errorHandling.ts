/**
 * Error Handling Utilities
 * 
 * Provides functions for handling and translating API errors.
 */

import { TFunction } from 'i18next';

/**
 * Get translated error message based on HTTP status code
 */
export function getErrorMessageByStatus(status: number, t: TFunction): string {
  switch (status) {
    case 400:
      return t('errors:api.badRequest');
    case 401:
      return t('errors:api.unauthorized');
    case 403:
      return t('errors:api.forbidden');
    case 404:
      return t('errors:api.notFound');
    case 408:
      return t('errors:api.timeout');
    case 409:
      return t('errors:api.conflict');
    case 429:
      return t('errors:api.tooManyRequests');
    case 500:
      return t('errors:api.serverError');
    case 503:
      return t('errors:api.serviceUnavailable');
    default:
      return t('errors:api.unknownError');
  }
}

/**
 * Get translated error message from error object
 */
export function getErrorMessage(error: unknown, t: TFunction): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === 'string') {
    return error;
  }
  return t('errors:api.unknownError');
}

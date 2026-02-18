/**
 * Error Handling Utilities
 * 
 * Provides internationalized error handling functions for API errors and exceptions.
 * All error messages are translated using the 'errors' namespace.
 * 
 * @module utils/errorHandling
 */

/**
 * Get translated error message based on HTTP status code.
 * 
 * Maps HTTP status codes to appropriate translated error messages from the 'errors' namespace.
 * 
 * @param status - HTTP status code (e.g., 400, 401, 404, 500)
 * @param t - Translation function from useTranslation hook
 * @returns Translated error message
 * 
 * Supported status codes:
 * - 400: Bad Request
 * - 401: Unauthorized
 * - 403: Forbidden
 * - 404: Not Found
 * - 408: Request Timeout
 * - 409: Conflict
 * - 429: Too Many Requests
 * - 500: Internal Server Error
 * - 503: Service Unavailable
 * - Other: Unknown Error
 * 
 * @example
 * ```typescript
 * import { useTypedTranslation } from '../hooks/useTypedTranslation';
 * import { getErrorMessageByStatus } from '../utils/errorHandling';
 * 
 * function MyComponent() {
 *   const { t } = useTypedTranslation('errors');
 *   
 *   try {
 *     const response = await fetch('/api/data');
 *     if (!response.ok) {
 *       const errorMsg = getErrorMessageByStatus(response.status, t);
 *       console.error(errorMsg); // "Not Found" or "Niet gevonden"
 *     }
 *   } catch (error) {
 *     // Handle error
 *   }
 * }
 * ```
 */
export function getErrorMessageByStatus(status: number, t: (key: string) => string): string {
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
 * Get translated error message from error object.
 * 
 * Extracts error message from various error types (Error, string, unknown).
 * Falls back to generic "Unknown Error" message if error type is not recognized.
 * 
 * @param error - Error object (Error instance, string, or unknown type)
 * @param t - Translation function from useTranslation hook
 * @returns Error message string or translated unknown error message
 * 
 * @example
 * ```typescript
 * import { useTypedTranslation } from '../hooks/useTypedTranslation';
 * import { getErrorMessage } from '../utils/errorHandling';
 * 
 * function MyComponent() {
 *   const { t } = useTypedTranslation('errors');
 *   
 *   try {
 *     throw new Error('Something went wrong');
 *   } catch (error) {
 *     const errorMsg = getErrorMessage(error, t);
 *     console.error(errorMsg); // "Something went wrong"
 *   }
 * }
 * ```
 * 
 * @example
 * ```typescript
 * // With unknown error type
 * const { t } = useTypedTranslation('errors');
 * const errorMsg = getErrorMessage(null, t); // "Unknown Error" or "Onbekende fout"
 * ```
 */
export function getErrorMessage(error: unknown, t: (key: string) => string): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === 'string') {
    return error;
  }
  return t('errors:api.unknownError');
}

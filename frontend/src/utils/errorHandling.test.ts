/**
 * Unit tests for error handling utilities
 */

import { getErrorMessageByStatus, getErrorMessage } from './errorHandling';

// Mock translation function
const mockT = (key: string) => {
  const translations: Record<string, string> = {
    'errors:api.badRequest': 'Bad request',
    'errors:api.unauthorized': 'Unauthorized',
    'errors:api.forbidden': 'Forbidden',
    'errors:api.notFound': 'Not found',
    'errors:api.timeout': 'Request timeout',
    'errors:api.conflict': 'Conflict',
    'errors:api.tooManyRequests': 'Too many requests',
    'errors:api.serverError': 'Server error',
    'errors:api.serviceUnavailable': 'Service unavailable',
    'errors:api.unknownError': 'Unknown error'
  };
  return translations[key] || key;
};

describe('getErrorMessageByStatus', () => {
  test('returns correct message for 400 Bad Request', () => {
    expect(getErrorMessageByStatus(400, mockT)).toBe('Bad request');
  });

  test('returns correct message for 401 Unauthorized', () => {
    expect(getErrorMessageByStatus(401, mockT)).toBe('Unauthorized');
  });

  test('returns correct message for 403 Forbidden', () => {
    expect(getErrorMessageByStatus(403, mockT)).toBe('Forbidden');
  });

  test('returns correct message for 404 Not Found', () => {
    expect(getErrorMessageByStatus(404, mockT)).toBe('Not found');
  });

  test('returns correct message for 408 Timeout', () => {
    expect(getErrorMessageByStatus(408, mockT)).toBe('Request timeout');
  });

  test('returns correct message for 409 Conflict', () => {
    expect(getErrorMessageByStatus(409, mockT)).toBe('Conflict');
  });

  test('returns correct message for 429 Too Many Requests', () => {
    expect(getErrorMessageByStatus(429, mockT)).toBe('Too many requests');
  });

  test('returns correct message for 500 Server Error', () => {
    expect(getErrorMessageByStatus(500, mockT)).toBe('Server error');
  });

  test('returns correct message for 503 Service Unavailable', () => {
    expect(getErrorMessageByStatus(503, mockT)).toBe('Service unavailable');
  });

  test('returns unknown error for unhandled status codes', () => {
    expect(getErrorMessageByStatus(418, mockT)).toBe('Unknown error');
    expect(getErrorMessageByStatus(999, mockT)).toBe('Unknown error');
  });
});

describe('getErrorMessage', () => {
  test('extracts message from Error object', () => {
    const error = new Error('Test error message');
    expect(getErrorMessage(error, mockT)).toBe('Test error message');
  });

  test('returns string error as-is', () => {
    expect(getErrorMessage('String error', mockT)).toBe('String error');
  });

  test('returns unknown error for other types', () => {
    expect(getErrorMessage(null, mockT)).toBe('Unknown error');
    expect(getErrorMessage(undefined, mockT)).toBe('Unknown error');
    expect(getErrorMessage(123, mockT)).toBe('Unknown error');
    expect(getErrorMessage({}, mockT)).toBe('Unknown error');
  });

  test('handles Error objects with empty messages', () => {
    const error = new Error('');
    expect(getErrorMessage(error, mockT)).toBe('');
  });
});

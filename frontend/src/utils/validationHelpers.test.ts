/**
 * Unit tests for validation helper functions
 */

import {
  isValidEmail,
  isValidUrl,
  isValidPhone,
  isValidIBAN
} from './validationHelpers';

describe('isValidEmail', () => {
  test('validates correct email addresses', () => {
    expect(isValidEmail('user@example.com')).toBe(true);
    expect(isValidEmail('test.user@example.co.uk')).toBe(true);
    expect(isValidEmail('user+tag@example.com')).toBe(true);
    expect(isValidEmail('user_name@example-domain.com')).toBe(true);
  });

  test('rejects invalid email addresses', () => {
    expect(isValidEmail('invalid')).toBe(false);
    expect(isValidEmail('invalid@')).toBe(false);
    expect(isValidEmail('@example.com')).toBe(false);
    expect(isValidEmail('user@')).toBe(false);
    expect(isValidEmail('user @example.com')).toBe(false);
    expect(isValidEmail('')).toBe(false);
  });
});

describe('isValidUrl', () => {
  test('validates correct URLs', () => {
    expect(isValidUrl('https://example.com')).toBe(true);
    expect(isValidUrl('http://example.com')).toBe(true);
    expect(isValidUrl('https://example.com/path')).toBe(true);
    expect(isValidUrl('https://sub.example.com')).toBe(true);
    expect(isValidUrl('https://example.com:8080')).toBe(true);
  });

  test('rejects invalid URLs', () => {
    expect(isValidUrl('example.com')).toBe(false);
    expect(isValidUrl('ftp://example.com')).toBe(false);
    expect(isValidUrl('//example.com')).toBe(false);
    expect(isValidUrl('https://')).toBe(false);
    expect(isValidUrl('')).toBe(false);
  });
});

describe('isValidPhone', () => {
  test('validates correct phone numbers', () => {
    expect(isValidPhone('+31612345678')).toBe(true);
    expect(isValidPhone('+31 6 12345678')).toBe(true);
    expect(isValidPhone('06-12345678')).toBe(true);
    expect(isValidPhone('(020) 1234567')).toBe(true);
    expect(isValidPhone('+1-555-123-4567')).toBe(true);
  });

  test('rejects invalid phone numbers', () => {
    expect(isValidPhone('abc')).toBe(false);
    expect(isValidPhone('123abc')).toBe(false);
    expect(isValidPhone('')).toBe(false);
  });

  test('allows various phone formats', () => {
    expect(isValidPhone('1234567890')).toBe(true);
    expect(isValidPhone('+1 (555) 123-4567')).toBe(true);
    expect(isValidPhone('+31 20 1234567')).toBe(true);
  });
});

describe('isValidIBAN', () => {
  test('validates correct IBAN formats', () => {
    expect(isValidIBAN('NL91ABNA0417164300')).toBe(true);
    expect(isValidIBAN('NL 91 ABNA 0417 1643 00')).toBe(true);
    expect(isValidIBAN('DE89370400440532013000')).toBe(true);
    expect(isValidIBAN('GB29NWBK60161331926819')).toBe(true);
  });

  test('rejects invalid IBAN formats', () => {
    expect(isValidIBAN('1234567890')).toBe(false);
    expect(isValidIBAN('ABCD1234')).toBe(false);
    expect(isValidIBAN('NL')).toBe(false);
    expect(isValidIBAN('')).toBe(false);
    expect(isValidIBAN('nl91abna0417164300')).toBe(false); // lowercase
  });

  test('handles IBAN with spaces', () => {
    expect(isValidIBAN('NL 91 ABNA 0417 1643 00')).toBe(true);
    expect(isValidIBAN('DE 89 3704 0044 0532 0130 00')).toBe(true);
  });
});

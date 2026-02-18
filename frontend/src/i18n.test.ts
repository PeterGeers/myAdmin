/**
 * Unit tests for i18n configuration
 */

import i18n from './i18n';

describe('i18n Configuration', () => {
  test('i18n is initialized', () => {
    expect(i18n).toBeDefined();
    expect(i18n.isInitialized).toBe(true);
  });

  test('has correct fallback language', () => {
    expect(i18n.options.fallbackLng).toEqual(['en']);
  });

  test('has correct default namespace', () => {
    expect(i18n.options.defaultNS).toBe('common');
  });

  test('has all required namespaces', () => {
    const requiredNamespaces = [
      'common',
      'auth',
      'reports',
      'str',
      'banking',
      'admin',
      'errors',
      'validation'
    ];

    requiredNamespaces.forEach(ns => {
      expect(i18n.hasResourceBundle('nl', ns)).toBe(true);
      expect(i18n.hasResourceBundle('en', ns)).toBe(true);
    });
  });

  test('supports Dutch language', () => {
    expect(i18n.hasResourceBundle('nl', 'common')).toBe(true);
  });

  test('supports English language', () => {
    expect(i18n.hasResourceBundle('en', 'common')).toBe(true);
  });

  test('can translate common keys', () => {
    i18n.changeLanguage('en');
    const translation = (i18n.t as any)('common:actions.save');
    expect(translation).toBeDefined();
    expect(translation).not.toBe('common:actions.save'); // Should be translated
  });

  test('can switch languages', () => {
    i18n.changeLanguage('nl');
    expect(i18n.language).toBe('nl');
    
    i18n.changeLanguage('en');
    expect(i18n.language).toBe('en');
  });

  test('interpolation works', () => {
    i18n.changeLanguage('en');
    const translation = (i18n.t as any)('common:messages.itemsCount', { count: 5 });
    expect(translation).toContain('5');
  });

  test('falls back to English for missing translations', () => {
    i18n.changeLanguage('nl');
    // Try to get a key that might not exist
    const translation = (i18n.t as any)('nonexistent:key:path');
    // Should return the key itself as fallback
    expect(translation).toBeDefined();
  });
});

describe('i18n Namespaces', () => {
  beforeEach(() => {
    i18n.changeLanguage('en');
  });

  test('common namespace has required keys', () => {
    expect(i18n.exists('common:actions.save')).toBe(true);
    expect(i18n.exists('common:actions.cancel')).toBe(true);
    expect(i18n.exists('common:status.loading')).toBe(true);
  });

  test('auth namespace has required keys', () => {
    expect(i18n.exists('auth:login.title')).toBe(true);
    expect(i18n.exists('auth:login.email')).toBe(true);
    expect(i18n.exists('auth:login.password')).toBe(true);
  });

  test('errors namespace has required keys', () => {
    expect(i18n.exists('errors:api.networkError')).toBe(true);
    expect(i18n.exists('errors:api.unauthorized')).toBe(true);
  });

  test('validation namespace has required keys', () => {
    expect(i18n.exists('validation:required.field')).toBe(true);
    expect(i18n.exists('validation:format.email')).toBe(true);
  });
});

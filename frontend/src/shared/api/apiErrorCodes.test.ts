/**
 * API response & error standard v1.0 — task 3.7 (dt): i18n copy for the new error codes.
 *
 * The backend emits stable machine `code`s (dotted, e.g. `errors.validation.mustBeOneOf`) that the
 * SPA resolves via `t('errors:<path>', params)` — the `namespace:path` form (the first dot becomes
 * the namespace separator). This test pins that EVERY new v1.0 code:
 *   - resolves to real, non-key copy in BOTH nl and en,
 *   - interpolates its `params` where the copy uses `{{param}}`, and
 *   - degrades to a fallback for an UNKNOWN code (the standard's graceful-degradation rule: the
 *     backend English `detail`/`error` is shown when a code has no locale key).
 *
 * All new v1.0 field/summary codes live under the `errors` namespace (field-level validation under
 * its `validation` category, `errors.validation.*`) — a deliberate improvement so one namespace
 * hosts every code (see the spec design "Code namespace").
 */

import i18n from '../../i18n';

/** Resolve a backend dotted code the way `applyApiError` will: first dot → namespace separator. */
function resolveCode(code: string, params?: Record<string, unknown>): string {
  const firstDot = code.indexOf('.');
  const key = firstDot === -1 ? code : `${code.slice(0, firstDot)}:${code.slice(firstDot + 1)}`;
  return (i18n.t as any)(key, params);
}

// Every NEW code introduced by v1.0 (task 3.1 + 3.4 + 3.8), grouped by whether it interpolates.
const PLAIN_CODES = [
  'errors.api.methodNotAllowed',
  'errors.api.notImplemented',
  'errors.validation.failed',
  'errors.validation.mustNotBeBlank',
  'errors.validation.mustBeAString',
  'errors.member.numberFormat',
  'errors.transition.denied',
  'errors.membershiptype.conflict',
  'errors.membershiptype.tenant',
  'errors.membershiptype.typeCode',
  'errors.membershiptype.label',
  'errors.membershiptype.order',
  'errors.invoice.emailMissing',
];

describe('API error codes — v1.0 i18n copy', () => {
  describe.each(['nl', 'en'])('language: %s', (lng) => {
    beforeAll(() => {
      i18n.changeLanguage(lng);
    });

    test.each(PLAIN_CODES)('resolves %s to real copy', (code) => {
      expect(i18n.exists(resolveKey(code))).toBe(true);
      const text = resolveCode(code);
      expect(text).toBeTruthy();
      // A successful resolution never echoes the key back.
      expect(text).not.toContain(':');
      expect(text).not.toBe(code);
    });

    test('mustBeOneOf interpolates params.allowed', () => {
      const text = resolveCode('errors.validation.mustBeOneOf', { allowed: 'active, inactive' });
      expect(text).toContain('active, inactive');
      expect(text).not.toContain('{{allowed}}');
    });

    test('enum.roleRestricted interpolates params.roles', () => {
      const text = resolveCode('errors.enum.roleRestricted', { roles: 'Members_CRUD' });
      expect(text).toContain('Members_CRUD');
      expect(text).not.toContain('{{roles}}');
    });

    test('membershiptype.unknownReference interpolates params.type_code', () => {
      const text = resolveCode('errors.membershiptype.unknownReference', { type_code: 'bogus' });
      expect(text).toContain('bogus');
      expect(text).not.toContain('{{type_code}}');
    });

    test('membershiptype.retired interpolates params.type_code', () => {
      const text = resolveCode('errors.membershiptype.retired', { type_code: 'oud' });
      expect(text).toContain('oud');
    });

    test('reused errors.validation.required still resolves', () => {
      const text = resolveCode('errors.validation.required');
      expect(text).toBeTruthy();
      expect(text).not.toBe('errors.validation.required');
    });
  });

  describe('graceful degradation (unknown code)', () => {
    beforeAll(() => {
      i18n.changeLanguage('en');
    });

    test('an unknown code has no locale key (caller falls back to detail/error)', () => {
      // The standard: when t(code) has no key, applyApiError shows the backend English detail.
      // Here we assert the key genuinely does NOT exist, so the fallback path is exercised.
      expect(i18n.exists(resolveKey('errors.validation.doesNotExist'))).toBe(false);
    });
  });
});

/** The `namespace:path` key form for `i18n.exists` (mirrors resolveCode's transform). */
function resolveKey(code: string): string {
  const firstDot = code.indexOf('.');
  return firstDot === -1 ? code : `${code.slice(0, firstDot)}:${code.slice(firstDot + 1)}`;
}

/**
 * Tests for the Members config API service (s5c tasks 2.5/2.6).
 *
 * Locks the save-once contract (Property 8): each `saveMembersParameter` call issues
 * EXACTLY ONE request — a PUT (update) when a tenant row exists, else a POST (create) —
 * never both, never per-field.
 *
 * S5j: also locks the definitions-fetch URL contract — the request URL must have the API
 * base applied EXACTLY ONCE (regression guard for the "Failed to fetch" double-prepend bug
 * where an absolute buildApiUrl() result was passed back into authenticatedGet()).
 */
import { vi } from 'vitest';
import {
  getMembersParameters,
  saveMembersParameter,
  getMembersParameterDefinitions,
  MEMBERS_NAMESPACE,
  LABEL_KEY_SCHEME,
  resolveShippedLabel,
  type LabelTranslator,
} from './membersConfigService';
import * as parameterService from './parameterService';
import * as apiService from './apiService';

vi.mock('./parameterService', () => ({
  getParameters: vi.fn(),
  createParameter: vi.fn(),
  updateParameter: vi.fn(),
}));

vi.mock('./apiService', () => ({
  authenticatedGet: vi.fn(),
  buildApiUrl: (e: string) => e,
}));

describe('membersConfigService', () => {
  beforeEach(() => vi.clearAllMocks());

  describe('getMembersParameters', () => {
    it('keys the members.* rows by their param key', async () => {
      vi.mocked(parameterService.getParameters).mockResolvedValue({
        success: true,
        tenant: 't1',
        parameters: {
          members: [
            { id: 1, namespace: 'members', key: 'field_overlay', value: {}, value_type: 'json', scope_origin: 'tenant', is_secret: false },
            { id: 2, namespace: 'members', key: 'scope_dimensions', value: [], value_type: 'json', scope_origin: 'tenant', is_secret: false },
          ],
        },
      });
      const byKey = await getMembersParameters();
      expect(Object.keys(byKey).sort()).toEqual(['field_overlay', 'scope_dimensions']);
      expect(byKey.field_overlay.id).toBe(1);
      expect(parameterService.getParameters).toHaveBeenCalledWith(MEMBERS_NAMESPACE);
    });

    it('returns an empty map when no members params exist', async () => {
      vi.mocked(parameterService.getParameters).mockResolvedValue({
        success: true,
        tenant: 't1',
        parameters: {},
      });
      expect(await getMembersParameters()).toEqual({});
    });
  });

  describe('getMembersParameterDefinitions (S5j — single-based URL, no double-prepend)', () => {
    it('calls authenticatedGet with a RELATIVE endpoint (authenticatedGet adds the base once)', async () => {
      // The bug: buildApiUrl() produced an ABSOLUTE url which was then passed to
      // authenticatedGet(), which prepends API_BASE_URL again → "https://hosthttps//host/...".
      // The fix passes the relative path so the base is applied exactly once. Guard it by
      // asserting the argument authenticatedGet receives carries NO scheme (is relative).
      vi.mocked(apiService.authenticatedGet).mockResolvedValue({
        ok: true,
        json: async () => [],
      } as unknown as Response);

      await getMembersParameterDefinitions();

      expect(apiService.authenticatedGet).toHaveBeenCalledTimes(1);
      const [endpointArg, optsArg] = vi.mocked(apiService.authenticatedGet).mock.calls[0];
      // Relative path only — no "http", no doubled host.
      expect(endpointArg).toBe('/api/config/members-parameters');
      expect(String(endpointArg)).not.toMatch(/https?:\/\//);
      // Public endpoint → auth is skipped.
      expect(optsArg).toMatchObject({ skipAuth: true });
    });
  });

  describe('saveMembersParameter (save-once, Property 8)', () => {
    it('issues exactly ONE update (PUT) when a tenant row exists', async () => {
      vi.mocked(parameterService.updateParameter).mockResolvedValue({ success: true });
      const existing = {
        id: 42, namespace: 'members', key: 'scope_dimensions',
        value: [], value_type: 'json' as const, scope_origin: 'tenant' as const, is_secret: false,
      };
      const res = await saveMembersParameter('scope_dimensions', [{ key: 'region' }], existing);

      expect(res.success).toBe(true);
      expect(parameterService.updateParameter).toHaveBeenCalledTimes(1);
      expect(parameterService.updateParameter).toHaveBeenCalledWith(42, {
        value: [{ key: 'region' }],
        value_type: 'json',
      });
      expect(parameterService.createParameter).not.toHaveBeenCalled();
    });

    it('issues exactly ONE create (POST) when no tenant row exists', async () => {
      vi.mocked(parameterService.createParameter).mockResolvedValue({ success: true });
      const res = await saveMembersParameter('view_contexts', [{ key: 'overview' }], null);

      expect(res.success).toBe(true);
      expect(parameterService.createParameter).toHaveBeenCalledTimes(1);
      expect(parameterService.createParameter).toHaveBeenCalledWith({
        scope: 'tenant',
        namespace: 'members',
        key: 'view_contexts',
        value: [{ key: 'overview' }],
        value_type: 'json',
        is_secret: false,
      });
      expect(parameterService.updateParameter).not.toHaveBeenCalled();
    });

    it('creates (does not update) when only a system/code default exists', async () => {
      vi.mocked(parameterService.createParameter).mockResolvedValue({ success: true });
      const systemDefault = {
        id: null, namespace: 'members', key: 'field_overlay',
        value: {}, value_type: 'json' as const, scope_origin: 'system' as const, is_secret: false,
      };
      await saveMembersParameter('field_overlay', { fields: {} }, systemDefault);

      expect(parameterService.createParameter).toHaveBeenCalledTimes(1);
      expect(parameterService.updateParameter).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // i18n Option (b) — task 4.2 (R4.4, `38` rule 6). The shipped-label resource
  // key SCHEME and the resolve-with-precedence rule.
  // -------------------------------------------------------------------------
  describe('LABEL_KEY_SCHEME (shipped-label resource-key scheme, R4.4)', () => {
    it('builds the field / group / enum keys exactly as the SAM catalog pins them', () => {
      // Mirrors `attribute_catalog.LABEL_KEY_SCHEME` byte-for-byte (no sam.* import — the
      // frontend half of the rule-5 shared-vocabulary guard). The key SEGMENT is the
      // canonical snake_case field key / enum value, verbatim (never translated, R3.4).
      expect(LABEL_KEY_SCHEME.fieldKey('first_name')).toBe('admin:membersConfig.field.first_name');
      expect(LABEL_KEY_SCHEME.fieldKey('member_number')).toBe(
        'admin:membersConfig.field.member_number',
      );
      expect(LABEL_KEY_SCHEME.groupKey('administrative')).toBe(
        'admin:membersConfig.group.administrative',
      );
      expect(LABEL_KEY_SCHEME.enumKey('status', 'active')).toBe(
        'admin:membersConfig.enum.status.active',
      );
      expect(LABEL_KEY_SCHEME.namespace).toBe('admin');
    });
  });

  describe('resolveShippedLabel (Option-b precedence: inline ?? resource(key) ?? fallback, R4.4)', () => {
    /** A fake translator over a tiny per-language resource table. */
    function fakeTranslator(table: Record<string, Record<string, string>>): LabelTranslator {
      return {
        exists: (key, options) => {
          const lng = options?.lng ?? 'en';
          return typeof table[key]?.[lng] === 'string';
        },
        t: (key, options) => {
          const lng = options?.lng ?? 'en';
          return table[key]?.[lng] ?? key;
        },
      };
    }

    const RESOURCES = {
      'admin:membersConfig.field.first_name': { en: 'First name', nl: 'Voornaam' },
      'admin:membersConfig.enum.status.active': { en: 'Active', nl: 'Actief' },
    };

    it('resolves the SHIPPED resource-key label for the active locale when there is no override', () => {
      const translator = fakeTranslator(RESOURCES);
      expect(
        resolveShippedLabel({
          resourceKey: LABEL_KEY_SCHEME.fieldKey('first_name'),
          inline: undefined,
          lang: 'nl',
          translator,
          fallback: 'first_name',
        }),
      ).toBe('Voornaam');
      expect(
        resolveShippedLabel({
          resourceKey: LABEL_KEY_SCHEME.fieldKey('first_name'),
          inline: undefined,
          lang: 'en',
          translator,
          fallback: 'first_name',
        }),
      ).toBe('First name');
    });

    it('lets the tenant INLINE per-language override win over the shipped resource key', () => {
      const translator = fakeTranslator(RESOURCES);
      // Tenant relabels the field in NL only; EN still falls through to the resource key.
      const inline = { nl: 'Roepnaam' };
      expect(
        resolveShippedLabel({
          resourceKey: LABEL_KEY_SCHEME.fieldKey('first_name'),
          inline,
          lang: 'nl',
          translator,
          fallback: 'first_name',
        }),
      ).toBe('Roepnaam');
      // EN has no inline entry → shipped resource key supplies it.
      expect(
        resolveShippedLabel({
          resourceKey: LABEL_KEY_SCHEME.fieldKey('first_name'),
          inline,
          lang: 'en',
          translator,
          fallback: 'first_name',
        }),
      ).toBe('First name');
    });

    it('falls back active → en → nl, then to the key, never blank', () => {
      const translator = fakeTranslator(RESOURCES);
      // A `de`-active user over an en/nl-only resource: en wins (the fallback tail head).
      expect(
        resolveShippedLabel({
          resourceKey: LABEL_KEY_SCHEME.fieldKey('first_name'),
          inline: undefined,
          lang: 'de',
          translator,
          fallback: 'first_name',
        }),
      ).toBe('First name');
      // No resource, no inline → the stable key fallback (never blank).
      expect(
        resolveShippedLabel({
          resourceKey: LABEL_KEY_SCHEME.fieldKey('unknown_field'),
          inline: undefined,
          lang: 'en',
          translator,
          fallback: 'unknown_field',
        }),
      ).toBe('unknown_field');
    });

    it('treats an enum option value as language-neutral — only the label resolves', () => {
      const translator = fakeTranslator(RESOURCES);
      // The option VALUE ('active') is the key segment, never translated; its label resolves.
      expect(
        resolveShippedLabel({
          resourceKey: LABEL_KEY_SCHEME.enumKey('status', 'active'),
          inline: undefined,
          lang: 'nl',
          translator,
          fallback: 'active',
        }),
      ).toBe('Actief');
      // An inline per-language override on the option label still wins.
      expect(
        resolveShippedLabel({
          resourceKey: LABEL_KEY_SCHEME.enumKey('status', 'active'),
          inline: { nl: 'Lopend' },
          lang: 'nl',
          translator,
          fallback: 'active',
        }),
      ).toBe('Lopend');
    });

    it('skips the resource lookup when no resource key / translator is supplied', () => {
      // A purely tenant-added field with an inline label and no shipped key.
      expect(
        resolveShippedLabel({
          resourceKey: null,
          inline: { en: 'Nickname', nl: 'Bijnaam' },
          lang: 'en',
          fallback: 'nickname',
        }),
      ).toBe('Nickname');
      // No inline, no key → fallback.
      expect(
        resolveShippedLabel({
          resourceKey: null,
          inline: undefined,
          lang: 'en',
          fallback: 'nickname',
        }),
      ).toBe('nickname');
    });
  });
});

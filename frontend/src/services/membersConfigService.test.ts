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
  resolveFieldConfigLabel,
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
      const res = await saveMembersParameter('scope_dimensions', [{ key: 'overview' }], null);

      expect(res.success).toBe(true);
      expect(parameterService.createParameter).toHaveBeenCalledTimes(1);
      expect(parameterService.createParameter).toHaveBeenCalledWith({
        scope: 'tenant',
        namespace: 'members',
        key: 'scope_dimensions',
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
  // Label resolution — plain per-language value over the served `label{}` (R4).
  // The drill-down resolves labels STRAIGHT from the resolved config's stored
  // `label{nl,en}` dict — there is no resource-key indirection on the server
  // (the retired `useMembersLabels`/`resolveShippedLabel`/`LABEL_KEY_SCHEME`
  // resolver is no longer the drill-down's label authority).
  // -------------------------------------------------------------------------
  describe('resolveFieldConfigLabel (label[lang] ?? label.en ?? label.nl ?? key, R4.1/R4.2/R4.4)', () => {
    const label = { en: 'First name', nl: 'Voornaam' };

    it('reads the served per-language dict for the active language (R4.4 — the selector picks the variant)', () => {
      // The viewer's active UI language selects the variant directly off the served dict.
      expect(resolveFieldConfigLabel(label, 'nl', 'personal.first_name')).toBe('Voornaam');
      expect(resolveFieldConfigLabel(label, 'en', 'personal.first_name')).toBe('First name');
    });

    it('falls through active → en → nl when the active variant is absent', () => {
      // NL-only dict, EN-active viewer → the en→nl fallback tail yields the NL value.
      expect(resolveFieldConfigLabel({ nl: 'Voornaam' }, 'en', 'first_name')).toBe('Voornaam');
      // EN-only dict, NL-active viewer → en supplies it.
      expect(resolveFieldConfigLabel({ en: 'First name' }, 'nl', 'first_name')).toBe('First name');
    });

    it('honours a plain-string label verbatim (language-neutral legacy/flat value)', () => {
      expect(resolveFieldConfigLabel('Region', 'nl', 'region')).toBe('Region');
    });

    it('NEVER returns blank — falls through to the stable key (R4.4)', () => {
      // No dict, empty dict, blank-only entries, and a nullish label all land on the key.
      expect(resolveFieldConfigLabel(undefined, 'en', 'region')).toBe('region');
      expect(resolveFieldConfigLabel(null, 'nl', 'region')).toBe('region');
      expect(resolveFieldConfigLabel({}, 'en', 'region')).toBe('region');
      expect(resolveFieldConfigLabel({ en: '   ', nl: '' }, 'en', 'region')).toBe('region');
      expect(resolveFieldConfigLabel('   ', 'en', 'region')).toBe('region');
    });

    it('ignores the active variant when it is blank and falls through to a non-blank one', () => {
      expect(resolveFieldConfigLabel({ nl: '', en: 'First name' }, 'nl', 'first_name')).toBe(
        'First name',
      );
    });
  });
});

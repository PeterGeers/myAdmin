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
import { ApiError } from '../shared/api/ApiError';
import {
  getMembersParameters,
  saveMembersParameter,
  saveMembersMailConfig,
  getMembersParameterDefinitions,
  MEMBERS_NAMESPACE,
  MEMBERS_PARAM_KEYS,
  resolveFieldConfigLabel,
} from './membersConfigService';
import * as parameterService from './parameterService';
import * as apiService from './apiService';
import * as membersApiService from './membersApiService';

vi.mock('./parameterService', () => ({
  getParameters: vi.fn(),
  createParameter: vi.fn(),
  updateParameter: vi.fn(),
}));

vi.mock('./apiService', () => ({
  authenticatedGet: vi.fn(),
  buildApiUrl: (e: string) => e,
}));

// The `field_overlay` save is repointed to the SAM Members write path (`PUT /members/config/fields`,
// Requirement 13.1); mock that seam so we can assert the PUT target + authoritative handling.
vi.mock('./membersApiService', () => ({
  writeFieldConfig: vi.fn(),
  writeScopeConfig: vi.fn(),
  writeMailConfig: vi.fn(),
  getFieldConfig: vi.fn(),
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

  // -------------------------------------------------------------------------
  // scope_dimensions is the frontend cross-plane MIRROR (Requirement 22.5/26.2): the frontend
  // writes SAM `config#scope` FIRST (authoritative, PUT /members/config/scope), THEN mirrors the
  // same dimension set into Flask `members.scope_dimensions` (best-effort). A failed SAM write
  // mirrors nothing; a failed mirror write surfaces a retry while SAM stays authoritative.
  // Validates: Requirements 22.1, 22.5, 22.6, 26.2, 26.4, 26.5
  // -------------------------------------------------------------------------
  describe('saveMembersParameter — scope_dimensions SAM-first mirror (R22/R26)', () => {
    it('writes SAM config#scope FIRST, THEN mirrors to Flask (update when a tenant row exists)', async () => {
      vi.mocked(membersApiService.writeScopeConfig).mockResolvedValue({
        success: true, configId: 'scope', version: '2026-10-20T10:00:00+00:00',
      });
      vi.mocked(parameterService.updateParameter).mockResolvedValue({ success: true });
      const existing = {
        id: 42, namespace: 'members', key: 'scope_dimensions',
        value: [], value_type: 'json' as const, scope_origin: 'tenant' as const, is_secret: false,
      };
      const dims = [{ key: 'region', values: ['Noord'] }];

      const res = await saveMembersParameter('scope_dimensions', dims, existing);

      expect(res.success).toBe(true);
      expect(res.version).toBe('2026-10-20T10:00:00+00:00');
      // SAM config#scope written first with the dimension set.
      expect(membersApiService.writeScopeConfig).toHaveBeenCalledTimes(1);
      expect(membersApiService.writeScopeConfig).toHaveBeenCalledWith(dims);
      // THEN the Flask mirror (update in place for an existing tenant row).
      expect(parameterService.updateParameter).toHaveBeenCalledTimes(1);
      expect(parameterService.updateParameter).toHaveBeenCalledWith(42, {
        value: dims, value_type: 'json',
      });
      expect(parameterService.createParameter).not.toHaveBeenCalled();
    });

    it('mirrors via create (POST) when no tenant row exists (new tenant auto-mirror, R22.7)', async () => {
      vi.mocked(membersApiService.writeScopeConfig).mockResolvedValue({
        success: true, configId: 'scope', version: '2026-10-20T10:05:00+00:00',
      });
      vi.mocked(parameterService.createParameter).mockResolvedValue({ success: true });
      const dims = [{ key: 'overview' }];

      const res = await saveMembersParameter('scope_dimensions', dims, null);

      expect(res.success).toBe(true);
      expect(membersApiService.writeScopeConfig).toHaveBeenCalledTimes(1);
      expect(parameterService.createParameter).toHaveBeenCalledTimes(1);
      expect(parameterService.createParameter).toHaveBeenCalledWith({
        scope: 'tenant', namespace: 'members', key: 'scope_dimensions',
        value: dims, value_type: 'json', is_secret: false,
      });
      expect(parameterService.updateParameter).not.toHaveBeenCalled();
    });

    it('normalizes a nullish scope value to an empty list for BOTH the SAM write and the mirror', async () => {
      vi.mocked(membersApiService.writeScopeConfig).mockResolvedValue({
        success: true, configId: 'scope', version: '2026-10-20T10:07:00+00:00',
      });
      vi.mocked(parameterService.createParameter).mockResolvedValue({ success: true });

      await saveMembersParameter('scope_dimensions', null, null);

      expect(membersApiService.writeScopeConfig).toHaveBeenCalledWith([]);
      expect(parameterService.createParameter).toHaveBeenCalledWith(
        expect.objectContaining({ value: [] }),
      );
    });

    it('fails WITHOUT mirroring when the authoritative SAM write rejects (R22.5)', async () => {
      vi.mocked(membersApiService.writeScopeConfig).mockRejectedValue(
        new ApiError(403, { error: 'Access denied' }),
      );

      const res = await saveMembersParameter('scope_dimensions', [{ key: 'region' }], null);

      expect(res.success).toBe(false);
      expect(res.error).toBe('Access denied');
      // SAM write failed → nothing authoritative → the Flask mirror must NOT be written.
      expect(parameterService.createParameter).not.toHaveBeenCalled();
      expect(parameterService.updateParameter).not.toHaveBeenCalled();
    });

    it('surfaces a mirror retry (SAM stays authoritative) when the Flask mirror write throws (R22.6/26.5)', async () => {
      vi.mocked(membersApiService.writeScopeConfig).mockResolvedValue({
        success: true, configId: 'scope', version: '2026-10-20T10:10:00+00:00',
      });
      vi.mocked(parameterService.createParameter).mockRejectedValue(
        new ApiError(500, { error: 'Mirror DB unavailable' }),
      );

      const res = await saveMembersParameter('scope_dimensions', [{ key: 'region' }], null);

      // SAM is authoritative (version present) but the mirror failed → surfaced for retry.
      expect(res.success).toBe(false);
      expect(res.version).toBe('2026-10-20T10:10:00+00:00');
      expect(res.mirrorError).toBe('Mirror DB unavailable');
    });

    it('surfaces a mirror retry when the Flask mirror returns success:false', async () => {
      vi.mocked(membersApiService.writeScopeConfig).mockResolvedValue({
        success: true, configId: 'scope', version: '2026-10-20T10:12:00+00:00',
      });
      vi.mocked(parameterService.updateParameter).mockResolvedValue({ success: false, error: 'conflict' });
      const existing = {
        id: 7, namespace: 'members', key: 'scope_dimensions',
        value: [], value_type: 'json' as const, scope_origin: 'tenant' as const, is_secret: false,
      };

      const res = await saveMembersParameter('scope_dimensions', [{ key: 'region' }], existing);

      expect(res.success).toBe(false);
      expect(res.version).toBe('2026-10-20T10:12:00+00:00');
      expect(res.mirrorError).toBe('conflict');
    });
  });

  // -------------------------------------------------------------------------
  // field_overlay is SAM-owned (`config#fields`): the save is repointed to the
  // Members SAM write path `PUT /members/config/fields` (Requirement 13.1), the
  // write is authoritative (Requirement 13.2 — no pending-projection state), and
  // the Flask parameter path is NO LONGER touched for field_overlay.
  // Validates: Requirements 13.1, 13.2, 13.4
  // -------------------------------------------------------------------------
  describe('saveMembersParameter — field_overlay repointed to SAM PUT /members/config/fields (R13)', () => {
    it('PUTs the whole field_overlay object through writeFieldConfig, NOT the Flask parameter path', async () => {
      vi.mocked(membersApiService.writeFieldConfig).mockResolvedValue({
        success: true,
        configId: 'fields',
        version: '2026-10-12T10:00:00+00:00',
      });
      const overlay = {
        fields: { region: { type: 'string', scope: { enabled: true } } },
        overrides: {},
        functional_groups: [{ key: 'personal', order: 1 }],
      };

      const res = await saveMembersParameter('field_overlay', overlay);

      expect(res.success).toBe(true);
      // Exactly one SAM write, with the whole config#fields body (fields/overrides/functional_groups).
      expect(membersApiService.writeFieldConfig).toHaveBeenCalledTimes(1);
      expect(membersApiService.writeFieldConfig).toHaveBeenCalledWith(overlay);
      // The Flask parameter path is never used for field_overlay anymore.
      expect(parameterService.createParameter).not.toHaveBeenCalled();
      expect(parameterService.updateParameter).not.toHaveBeenCalled();
    });

    it('routes through SAM even when a tenant parameter row exists (no Flask create/update)', async () => {
      vi.mocked(membersApiService.writeFieldConfig).mockResolvedValue({
        success: true,
        configId: 'fields',
        version: '2026-10-12T10:05:00+00:00',
      });
      const existing = {
        id: 202, namespace: 'members', key: 'field_overlay',
        value: {}, value_type: 'json' as const, scope_origin: 'tenant' as const, is_secret: false,
      };

      await saveMembersParameter('field_overlay', { fields: {} }, existing);

      // config#fields is a SAM upsert — the presence of a legacy MySQL row does NOT reroute to Flask.
      expect(membersApiService.writeFieldConfig).toHaveBeenCalledTimes(1);
      expect(parameterService.updateParameter).not.toHaveBeenCalled();
      expect(parameterService.createParameter).not.toHaveBeenCalled();
    });

    it('treats the SAM write as authoritative — no pending-projection state (R13.2)', async () => {
      vi.mocked(membersApiService.writeFieldConfig).mockResolvedValue({
        success: true,
        configId: 'fields',
        version: '2026-10-12T10:10:00+00:00',
      });

      const res = await saveMembersParameter('field_overlay', { fields: {} });

      // The returned version IS the authored state; the service surfaces no projection-lag signal.
      expect(res.success).toBe(true);
      expect(res.projected).toBeUndefined();
      expect(res.projection_error).toBeUndefined();
    });

    it('normalizes a nullish field_overlay to an empty object before the SAM write', async () => {
      vi.mocked(membersApiService.writeFieldConfig).mockResolvedValue({
        success: true,
        configId: 'fields',
        version: '2026-10-12T10:15:00+00:00',
      });

      await saveMembersParameter('field_overlay', null);

      expect(membersApiService.writeFieldConfig).toHaveBeenCalledWith({});
    });

    it('surfaces a caller-safe error (success:false) when the SAM write rejects', async () => {
      vi.mocked(membersApiService.writeFieldConfig).mockRejectedValue(
        new ApiError(403, { error: 'Access denied' }),
      );

      const res = await saveMembersParameter('field_overlay', { fields: {} });

      expect(res.success).toBe(false);
      expect(res.error).toBe('Access denied');
      // A failed SAM write must not silently fall back to the Flask parameter path.
      expect(parameterService.createParameter).not.toHaveBeenCalled();
      expect(parameterService.updateParameter).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // config#mail is SAM-owned: saveMembersMailConfig is the single authoring door
  // (task 7.1, Property 8). It PUTs the reader-shaped body through writeMailConfig
  // (`PUT /members/config/mail`), the SAM write is authoritative (the returned
  // version IS the authored state), and it NEVER touches the Flask parameter path.
  // Validates: Requirements 20.1, 20.2, 9.1, 14.4, 15.2
  // -------------------------------------------------------------------------
  describe('saveMembersMailConfig — the single SAM config#mail write door (task 7.1)', () => {
    const body = {
      mail_enabled: true,
      mail_certified: true,
      mail_local_part: 'info',
      mail_domain: 'h-dcn.nl',
    };

    it('PUTs the whole body through writeMailConfig and returns the authoritative version', async () => {
      vi.mocked(membersApiService.writeMailConfig).mockResolvedValue({
        success: true,
        configId: 'mail',
        version: '2026-10-20T11:00:00+00:00',
      });

      const res = await saveMembersMailConfig(body);

      expect(res.success).toBe(true);
      expect(res.version).toBe('2026-10-20T11:00:00+00:00');
      // Exactly one SAM write, with the full body (single authoring door).
      expect(membersApiService.writeMailConfig).toHaveBeenCalledTimes(1);
      expect(membersApiService.writeMailConfig).toHaveBeenCalledWith(body);
      // The Flask parameter path is never used for mail.
      expect(parameterService.createParameter).not.toHaveBeenCalled();
      expect(parameterService.updateParameter).not.toHaveBeenCalled();
    });

    it('surfaces a caller-safe error (success:false) when the SAM write rejects', async () => {
      vi.mocked(membersApiService.writeMailConfig).mockRejectedValue(
        new ApiError(403, { error: 'Access denied' }),
      );

      const res = await saveMembersMailConfig(body);

      expect(res.success).toBe(false);
      expect(res.error).toBe('Access denied');
      // A failed SAM write must not fall back to the Flask parameter path.
      expect(parameterService.createParameter).not.toHaveBeenCalled();
      expect(parameterService.updateParameter).not.toHaveBeenCalled();
    });

    it('treats a success:false result as a failed save (no version claimed)', async () => {
      vi.mocked(membersApiService.writeMailConfig).mockResolvedValue({
        success: false,
        configId: 'mail',
        version: '',
      });

      const res = await saveMembersMailConfig(body);

      expect(res.success).toBe(false);
      expect(res.error).toBe('Mail config write failed');
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

  // -------------------------------------------------------------------------
  // Property 8 — single authoring door / no second writer (task 7.3*).
  //
  // The config#mail concern has EXACTLY ONE authoring door: saveMembersMailConfig ->
  // writeMailConfig -> PUT /members/config/mail (the SAM-owned route). This asserts the
  // two halves of Property 8:
  //   (a) every config#mail write goes through the single SAM route and NEVER through the
  //       Flask parameter path (createParameter/updateParameter), and
  //   (b) no `members.*` MySQL write path remains for any MIGRATED mail key — the Flask
  //       saveMembersParameter surface (MEMBERS_PARAM_KEYS) carries NONE of them, so there
  //       is no second writer that could re-open the retired MySQL door.
  // Validates: Requirements 14.1, 14.3, 14.4
  // -------------------------------------------------------------------------
  describe('Property 8 — single authoring door / no second writer (task 7.3*)', () => {
    const MIGRATED_MAIL_KEYS = [
      'mail_enabled',
      'mail_domain',
      'mail_local_part',
      'mail_certified',
      'mail_reply_to_default',
      'application_consent_notice',
    ] as const;

    it('routes every config#mail write through the single SAM door, never the Flask param path', async () => {
      vi.mocked(membersApiService.writeMailConfig).mockResolvedValue({
        success: true,
        configId: 'mail',
        version: '2026-10-21T09:00:00+00:00',
      });

      await saveMembersMailConfig({
        mail_enabled: true,
        mail_certified: true,
        mail_local_part: 'noreply',
        mail_domain: 'h-dcn.nl',
        mail_reply_to_default: 'replies@h-dcn.nl',
      });

      // (a) Exactly one write, and it is the SAM config#mail route — no Flask parameter write.
      expect(membersApiService.writeMailConfig).toHaveBeenCalledTimes(1);
      expect(parameterService.createParameter).not.toHaveBeenCalled();
      expect(parameterService.updateParameter).not.toHaveBeenCalled();
      // The field/scope SAM doors are not collateral-called by a mail save either.
      expect(membersApiService.writeFieldConfig).not.toHaveBeenCalled();
      expect(membersApiService.writeScopeConfig).not.toHaveBeenCalled();
    });

    it('exposes NO Flask saveMembersParameter door for any migrated mail key (no second writer)', () => {
      // (b) The legacy Flask-plane authoring surface accepts only the field/scope keys; no
      // migrated mail key is a MembersParamKey, so a mail scalar cannot be written to MySQL
      // through saveMembersParameter — the retired members.* door stays closed.
      const paramKeys = new Set<string>(MEMBERS_PARAM_KEYS);
      for (const mailKey of MIGRATED_MAIL_KEYS) {
        expect(paramKeys.has(mailKey)).toBe(false);
      }
      // The Flask surface is exactly field_overlay + scope_dimensions (both SAM-mirrored),
      // which are field/scope keys, not config#mail keys.
      expect([...paramKeys].sort()).toEqual(['field_overlay', 'scope_dimensions']);
    });
  });
});

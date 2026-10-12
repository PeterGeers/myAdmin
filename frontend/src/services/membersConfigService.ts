/**
 * API service for the Members typed authoring UI (s5c C-EDITOR, tasks 2.5/2.6).
 *
 * Three responsibilities, all reusing the existing parameter-admin plumbing:
 *
 *  - `getMembersParameterDefinitions()` — `GET /api/config/members-parameters`, the
 *    typed-editor definitions (what controls to render).
 *  - `getMembersParameters()` — `GET /api/tenant-admin/parameters?namespace=members`,
 *    the current values (each param carries its DB `id`, or `null` for a code default).
 *  - `saveMembersParameter()` — the **save-once** primitive (task 2.6, Property 8):
 *    each call commits the WHOLE object for one `members.*` key in **exactly one** HTTP
 *    request (a PUT when a tenant row exists, else a POST creating the tenant-scope row).
 *    One save → one request → one enqueue_sync → one per-tenant re-projection.
 */
import type { Parameter } from '../types/parameterTypes';
import type { MembersParamDefinition, MembersConfigValue } from '../types/membersConfig';
import type { FieldConfig } from '../types/members';
import { authenticatedGet } from './apiService';
import { getParameters, createParameter, updateParameter } from './parameterService';
import { getFieldConfig } from './membersApiService';

export const MEMBERS_NAMESPACE = 'members';

/** The three authorable member config keys, in editor order. */
export const MEMBERS_PARAM_KEYS = ['field_overlay', 'scope_dimensions', 'view_contexts'] as const;
export type MembersParamKey = (typeof MEMBERS_PARAM_KEYS)[number];

/**
 * Map each authorable `members.*` param key to the projected `config#<id>` row it drives
 * (impact-analysis §4 / Phase 0 step 3). The editor uses this to line a param's delivered/
 * loaded status up with the sub-editor that authors it. `field_overlay` drives the
 * `config#fields` row (its `functional_groups`/`fields`/`fixed_overrides`/`analytics` slices).
 */
export const MEMBERS_PARAM_TO_CONFIG_ID: Record<MembersParamKey, string> = {
  field_overlay: 'fields',
  scope_dimensions: 'scope',
  view_contexts: 'views',
};

/**
 * Fetch the module's projected-config DELIVERED/LOADED status (Phase 0 step 3).
 *
 * Reads the Members module `GET /members/field-config` response and returns its
 * `config_status` map `{config_id: version | null}` — the monotonic version each projected
 * `config#*` row is serving, or `null` when that row has never been delivered. The editor
 * surfaces this so a Tenant Admin can see whether a saved `members.*` edit has actually been
 * projected (delivered) and is what the module reads (loaded).
 *
 * Returns an empty map when the module build predates the field (`config_status` absent) or
 * the fetch fails — the caller treats that as "status unavailable" rather than an error, so a
 * status glitch never blocks authoring.
 */
export async function getMembersConfigStatus(): Promise<Record<string, string | number | null>> {
  try {
    const cfg = await getFieldConfig<FieldConfig>();
    return cfg?.config_status ?? {};
  } catch {
    return {};
  }
}

/**
 * Fetch the typed-editor definitions. Public endpoint (no auth needed — mirrors the
 * ledger-parameters fetch in AccountModal).
 */
export async function getMembersParameterDefinitions(): Promise<MembersParamDefinition[]> {
  // Pass the RELATIVE endpoint: authenticatedGet prepends API_BASE_URL itself. Passing a
  // pre-built absolute URL (from buildApiUrl) would double the base
  // ("https://host" + "https://host/api/...") and fail with "Failed to fetch".
  const resp = await authenticatedGet('/api/config/members-parameters', { skipAuth: true });
  if (!resp.ok) {
    throw new Error(`Failed to load members parameter definitions (${resp.status})`);
  }
  return resp.json();
}

/**
 * Fetch the current `members.*` parameter values for the tenant, keyed by param key.
 * A key absent from the response has never been authored (treat as an empty value).
 */
export async function getMembersParameters(): Promise<Record<string, Parameter>> {
  const data = await getParameters(MEMBERS_NAMESPACE);
  const rows = data.parameters?.[MEMBERS_NAMESPACE] ?? [];
  const byKey: Record<string, Parameter> = {};
  for (const row of rows) {
    byKey[row.key] = row;
  }
  return byKey;
}

/**
 * Save-once: commit the whole `value` object for one `members.<key>` param in a single
 * request (task 2.6 / R3.5 / Property 8).
 *
 * - If an existing tenant-scope row is supplied, issue ONE `PUT` (update in place).
 * - Otherwise (no row, or a system/code default), issue ONE `POST` creating the
 *   tenant-scope row.
 *
 * Never per-field / per-keystroke; the caller passes the entire object exactly once.
 */
export async function saveMembersParameter(
  key: MembersParamKey,
  value: MembersConfigValue,
  existing?: Parameter | null,
): Promise<{ success: boolean; error?: string }> {
  // A members.* object param is always an object or list; never a bare null.
  // Normalize a nullish value to the right empty container so it satisfies the
  // parameter request value type (which does not accept null).
  const normalized: Record<string, unknown> | unknown[] =
    value == null ? (key === 'field_overlay' ? {} : []) : (value as Record<string, unknown> | unknown[]);

  // A row with a real numeric id + tenant origin can be updated in place.
  if (existing && existing.id != null && existing.scope_origin === 'tenant') {
    return updateParameter(existing.id, { value: normalized, value_type: 'json' });
  }
  // No tenant row yet (unauthored, or only a system/code default) → create one.
  return createParameter({
    scope: 'tenant',
    namespace: MEMBERS_NAMESPACE,
    key,
    value: normalized,
    value_type: 'json',
    is_secret: false,
  });
}

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
import type {
  FieldConfig,
  FieldConfigField,
  FunctionalGroup,
  LocalizedLabel,
} from '../types/members';
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
 * Fetch the module's RESOLVED field configuration (`GET /members/field-config`) — the single
 * ordered field list the Members config redesign Phase 3 (step 8, R1) re-presents.
 *
 * The module resolves the platform base ⊕ the tenant `field_overlay` into ONE field set, each
 * field carrying its DERIVED `provenance` badge (`base` / `tenant_added` / `base_overridden`,
 * R1.2) and the `(functional_group, order, key)` facts the editor orders by (R1.3). The typed
 * editor reads this to render the unified field list with a provenance badge per field,
 * replacing the former two-section fixed/overlay split — a presentation change only; authoring
 * still writes the single `field_overlay` object (R1.4).
 *
 * Resolves to `null` when the fetch fails or the module build predates the endpoint, so a
 * glitch degrades to "no provenance view available" rather than blocking the editor (mirrors
 * `getMembersConfigStatus`'s best-effort posture — the field-config fetch never gates authoring).
 */
export async function getMembersFieldConfig(): Promise<FieldConfig | null> {
  try {
    return (await getFieldConfig<FieldConfig>()) ?? null;
  } catch {
    return null;
  }
}

/**
 * Order the resolved field list by the catalog ordering rule `(group.order, field.order, key)`
 * (R1.3, `38-sam-module-field-config.md` rule 2) — NO new position field is introduced; the order
 * is DERIVED on read from facts the module already serves:
 *
 *  - `group.order` — the `order` of the field's `functional_group` in `cfg.functional_groups`
 *    (a field whose group is absent from the catalog sorts after defined groups);
 *  - `field.order` — the field's own `order` (missing → sorts after ordered fields);
 *  - `key`         — the stable field key, the final deterministic tie-breaker.
 *
 * Returns a NEW sorted array; the input is not mutated. The resolved field SET is unchanged — this
 * only derives a stable display order over it (Property 1, R1.6).
 */
export function orderResolvedFields(cfg: FieldConfig | null | undefined): FieldConfigField[] {
  const fields = cfg?.fields ?? [];
  const groupOrderByKey = new Map<string, number>();
  (cfg?.functional_groups ?? []).forEach((g) => {
    if (g?.key != null) groupOrderByKey.set(g.key, typeof g.order === 'number' ? g.order : Number.MAX_SAFE_INTEGER);
  });
  const groupOrderOf = (f: FieldConfigField): number => {
    const gk = f.functional_group ?? f.group;
    if (gk != null && groupOrderByKey.has(gk)) return groupOrderByKey.get(gk) as number;
    return Number.MAX_SAFE_INTEGER;
  };
  const fieldOrderOf = (f: FieldConfigField): number =>
    typeof f.order === 'number' ? f.order : Number.MAX_SAFE_INTEGER;
  return [...fields].sort((a, b) => {
    const ga = groupOrderOf(a);
    const gb = groupOrderOf(b);
    if (ga !== gb) return ga - gb;
    const fa = fieldOrderOf(a);
    const fb = fieldOrderOf(b);
    if (fa !== fb) return fa - fb;
    return a.key.localeCompare(b.key);
  });
}

/**
 * One section of the group → field → attribute authoring hierarchy (Members config redesign
 * Phase 3 step 11, R4.1/R4.2): a functional group together with the resolved fields that belong
 * to it, in DERIVED order.
 */
export interface FieldHierarchyGroup {
  /** The functional-group key the fields are grouped under. */
  key: string;
  /** The catalog group record (its `label` / `order`), or `undefined` for the trailing bucket. */
  group?: FunctionalGroup;
  /** The group's `order` used for the derived `(group.order, …)` sort (absent → sorts last). */
  order: number;
  /**
   * Whether this is a defined catalog group (`true`) or the trailing "other" bucket (`false`)
   * holding fields whose `functional_group` is NOT catalog-resolvable (R4.3 — the picker-
   * resolvability guard surfaced: an unresolvable reference is shown, never silently dropped).
   */
  resolved: boolean;
  /** The group's fields, ordered by `(field.order, key)` within the group. */
  fields: FieldConfigField[];
}

/**
 * Build the group → field → attribute authoring HIERARCHY from the resolved field-config
 * (Members config redesign Phase 3 step 11, R4.1/R4.2/R4.3), on the Phase 1 attribute catalog.
 *
 * The hierarchy is the catalog's own group → field → attribute shape (`38-sam-module-field-config.md`
 * rules 1/2): every defined functional group (`key`/`label`/`order`) is a section, holding the
 * resolved fields whose `functional_group` references it, with each field carrying its per-field
 * attributes (type / required / visible / order / provenance / scope / alias / …) straight off the
 * resolved descriptor. Display order is DERIVED `(group.order, field.order, key)` — NO stored
 * absolute position field is introduced (rule 2); groups sort by `group.order` then `key`, and
 * fields within a group by `(field.order, key)` (both missing orders sort last, deterministically).
 *
 * Catalog-resolvability (R4.3): a group section is emitted for every DEFINED catalog group, even an
 * empty one (so a tenant can author into it). A field whose `functional_group` is absent from the
 * catalog — or has none — is collected into a single trailing bucket (`resolved: false`), so an
 * unresolvable reference is SURFACED rather than silently dropped. The field SET is preserved: the
 * union of every section's fields equals the input field set (nothing added or removed — Property 1
 * is a set/order invariant over the SAME fields).
 *
 * Returns NEW arrays; the input is not mutated. A `null`/absent config yields no sections.
 */
export function groupResolvedFields(cfg: FieldConfig | null | undefined): FieldHierarchyGroup[] {
  const fields = cfg?.fields ?? [];
  const groups = cfg?.functional_groups ?? [];

  const groupByKey = new Map<string, FunctionalGroup>();
  groups.forEach((g) => {
    if (g?.key != null) groupByKey.set(g.key, g);
  });

  const groupKeyOf = (f: FieldConfigField): string | null => {
    const gk = f.functional_group ?? f.group ?? null;
    return gk != null && groupByKey.has(gk) ? gk : null;
  };

  const fieldOrderOf = (f: FieldConfigField): number =>
    typeof f.order === 'number' ? f.order : Number.MAX_SAFE_INTEGER;
  const sortFields = (list: FieldConfigField[]): FieldConfigField[] =>
    [...list].sort((a, b) => {
      const fa = fieldOrderOf(a);
      const fb = fieldOrderOf(b);
      if (fa !== fb) return fa - fb;
      return a.key.localeCompare(b.key);
    });

  // Bucket fields by their resolvable group key (null → the trailing "other" bucket).
  const byGroup = new Map<string | null, FieldConfigField[]>();
  fields.forEach((f) => {
    const gk = groupKeyOf(f);
    const bucket = byGroup.get(gk) ?? [];
    bucket.push(f);
    byGroup.set(gk, bucket);
  });

  // Every DEFINED catalog group is a section (even an empty one — a tenant can author into it),
  // ordered by `(group.order, key)` — the derived group tier of the ordering rule (rule 2).
  const groupOrderOf = (g: FunctionalGroup): number =>
    typeof g.order === 'number' ? g.order : Number.MAX_SAFE_INTEGER;
  const definedSections: FieldHierarchyGroup[] = [...groups]
    .filter((g) => g?.key != null)
    .sort((a, b) => {
      const oa = groupOrderOf(a);
      const ob = groupOrderOf(b);
      if (oa !== ob) return oa - ob;
      return a.key.localeCompare(b.key);
    })
    .map((g) => ({
      key: g.key,
      group: g,
      order: groupOrderOf(g),
      resolved: true,
      fields: sortFields(byGroup.get(g.key) ?? []),
    }));

  // The trailing bucket: fields with no catalog-resolvable group (R4.3 — surfaced, never dropped).
  const sections = [...definedSections];
  const orphan = byGroup.get(null) ?? [];
  if (orphan.length > 0) {
    sections.push({
      key: '',
      group: undefined,
      order: Number.MAX_SAFE_INTEGER,
      resolved: false,
      fields: sortFields(orphan),
    });
  }

  return sections;
}

// ---------------------------------------------------------------------------
// Label resolution — plain per-language value over the served `label{}` (R4).
// ---------------------------------------------------------------------------

/**
 * Resolve a drill-down field/group label straight from the RESOLVED config's stored per-language
 * `label{}` dict (`38-sam-module-field-config.md` rule 6, as rewritten for the stored-config model;
 * remediation R4.1/R4.2/R4.4).
 *
 * The server already serves a plain inline `label{nl,en}` on every resolved field/group — there is
 * NO resource-key indirection on the server (verified server-truth pass, design §Server truth). The
 * drill-down therefore does NOT go through the former shipped-resource-key resolver
 * (`useMembersLabels`/`resolveShippedLabel`/`LABEL_KEY_SCHEME`, retired here); it reads the served
 * dict directly with the plain precedence:
 *
 *     label[lang]  ??  label.en  ??  label.nl  ??  fallbackKey
 *
 * The viewer's active UI language selects the variant (R4.4); when it carries no entry the stable
 * `en` then `nl` fallbacks apply, and when NOTHING resolves the field/group KEY is shown — the
 * fallback is NEVER blank (R4.4). A plain-string `label` (a legacy/flat value) is honoured verbatim
 * as a language-neutral label. The shipped `locales` `admin.json` `membersConfig` entries MAY
 * remain as an onboarding/default seed for base fields, but are NOT the runtime resolution source
 * for a tenant-editable label (R4.3).
 *
 * @param label the served per-language label dict (or a plain string / nullish).
 * @param lang the viewer's active UI language (`'nl' | 'en'`).
 * @param fallbackKey the non-blank fallback shown when nothing resolves (the stable field/group key).
 */
export function resolveFieldConfigLabel(
  label: string | LocalizedLabel | null | undefined,
  lang: 'nl' | 'en',
  fallbackKey: string,
): string {
  // A plain-string label is language-neutral — honour it outright.
  if (typeof label === 'string') {
    return label.trim() ? label : fallbackKey;
  }

  if (label && typeof label === 'object') {
    // Active language first, then the stable en → nl fallback tail (R4.4).
    const active = label[lang];
    if (typeof active === 'string' && active.trim()) return active;
    if (typeof label.en === 'string' && label.en.trim()) return label.en;
    if (typeof label.nl === 'string' && label.nl.trim()) return label.nl;
  }

  // Nothing resolved — the stable key, never blank (R4.4).
  return fallbackKey;
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
    throw new Error(`Failed to load members parameter definitions(${resp.status})`);
  }
  return resp.json();
}

/**
 * Fetch the current `members.* ` parameter values for the tenant, keyed by param key.
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
): Promise<{ success: boolean; error?: string; projected?: boolean | null; projection_error?: string }> {
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

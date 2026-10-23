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
import { ApiError } from '../shared/api/ApiError';
import { authenticatedGet } from './apiService';
import { getParameters, createParameter, updateParameter } from './parameterService';
import {
  getFieldConfig,
  previewApplicationFieldConfig,
  writeFieldConfig,
  writeScopeConfig,
  writeMailConfig,
} from './membersApiService';
import type { PublicFieldConfig } from '../components/public/application/applicationFieldConfig';

export const MEMBERS_NAMESPACE = 'members';

/** The authorable member config keys, in editor order. */
export const MEMBERS_PARAM_KEYS = ['field_overlay', 'scope_dimensions'] as const;
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
 * Preview the PUBLIC application-form schema for the builder's WORKING `field_overlay` (spec 11
 * task 4.2 / R7.1–R7.2; design §4/§6/§9 S1·S2).
 *
 * The in-app live preview of the Application Form Builder: it POSTs the admin's WORKING (in-memory,
 * unsaved) overlay to `POST /members/application-preview`, which runs the EXACT server
 * `get_public_field_config` filter over it and returns the applicant-facing schema
 * (`PublicFieldConfig` — `{ fields, locales, notice }`). The preview panel feeds that schema to the
 * shared spec-10 `ApplicationFormRenderer`, so the preview shares BOTH a single rendering code path
 * AND a single filtering authority (no client-side mirror to drift, correctness property 4), and
 * reflects UNSAVED edits live (R7.1).
 *
 * UNLIKE the other best-effort reads here, this RE-THROWS on failure: the preview panel distinguishes
 * a deliberate authoring error (a 400 on a malformed overlay — an enum subset ⊄ the field's choices)
 * from an empty form, and surfaces it rather than silently rendering a blank preview. The caller owns
 * the try/catch + the debounce.
 */
export async function previewMembersApplicationConfig(
  overlay: MembersConfigValue,
): Promise<PublicFieldConfig> {
  return previewApplicationFieldConfig<PublicFieldConfig>(overlay);
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
 * Save-once: commit the whole `value` object for one `members.<key>` param in a single request
 * (task 2.6 / R3.5 / Property 8).
 *
 * Per-record SAM cutover (Requirement 13): the `field_overlay` save is repointed to the SAM-owned
 * write path `PUT /members/config/fields` (`config#fields` is now SAM's system-of-record). The SAM
 * write is **authoritative** — the returned row `version` IS the authored state, there is no
 * projection step to wait on, so this no longer surfaces a `projected` / `projection_error`
 * pending-projection signal for `field_overlay`.
 *
 * Scope save (`scope_dimensions`) is the frontend cross-plane MIRROR (Requirement 22.5/26.2):
 * SAM `config#scope` is authoritative and written FIRST (`PUT /members/config/scope`), THEN the
 * same dimension set is mirrored into the Flask `members.scope_dimensions` validator copy
 * (best-effort). A failed SAM write returns `{ success: false, error }` and mirrors NOTHING; a
 * failed MIRROR write returns `{ success: false, version, mirrorError }` — SAM is already
 * authoritative, and the UI surfaces the mirror failure and offers retry (Requirement 22.6/26.5).
 *
 * The public signature and `{ success, error? }` return shape are kept stable so the editor
 * (`MembersParamSubEditor`) consumes the service unchanged (Requirement 13.3) — only the save
 * targets move (`field_overlay` → SAM config#fields; `scope_dimensions` → SAM config#scope first,
 * then the Flask mirror).
 *
 * Never per-field / per-keystroke; the caller passes the entire object exactly once.
 */
export async function saveMembersParameter(
  key: MembersParamKey,
  value: MembersConfigValue,
  existing?: Parameter | null,
): Promise<{
  success: boolean;
  error?: string;
  projected?: boolean | null;
  projection_error?: string;
  /**
   * Scope save only (Requirement 22.6 / 26.5): SAM `config#scope` was written authoritatively
   * but the best-effort Flask `members.scope_dimensions` MIRROR write failed. SAM is already the
   * source of truth; the UI surfaces this and offers RETRY of just the mirror. `mirrorError`
   * carries a caller-safe message; `version` is the authoritative SAM write stamp.
   */
  mirrorError?: string;
  version?: string;
}> {
  // A members.* object param is always an object or list; never a bare null.
  // Normalize a nullish value to the right empty container so it satisfies the
  // request value type (which does not accept null).
  const normalized: Record<string, unknown> | unknown[] =
    value == null ? (key === 'field_overlay' ? {} : []) : (value as Record<string, unknown> | unknown[]);

  // `field_overlay` drives `config#fields` — repointed to the SAM write path (Requirement 13.1).
  // The request body is the SAM `config#fields` shape (`fields` / `overrides` / `functional_groups`,
  // which the field_overlay object already carries — NO `default_page_size`, retired per Req 25).
  if (key === 'field_overlay') {
    try {
      const result = await writeFieldConfig(normalized);
      // The SAM write is authoritative (Requirement 13.2): the returned version is the authored
      // state — no pending-projection polling, so no `projected`/`projection_error` is surfaced.
      return { success: result.success !== false };
    } catch (e) {
      // Surface a caller-safe message; the Members API throws a structured ApiError on non-2xx.
      const error = e instanceof ApiError || e instanceof Error ? e.message : String(e);
      return { success: false, error };
    }
  }

  // `scope_dimensions` is the frontend cross-plane bridge (Requirement 22.5 / 26.2/26.4): the
  // two planes never call each other at runtime, so the frontend writes EACH plane separately —
  // SAM `config#scope` FIRST (authoritative), THEN the Flask `members.scope_dimensions` MIRROR.
  if (key === 'scope_dimensions') {
    // `normalized` is the dimension set (a list). Step 1 — write SAM config#scope (authoritative).
    let version: string;
    try {
      const result = await writeScopeConfig(normalized as unknown[]);
      if (result.success === false) {
        return { success: false, error: 'Scope write failed' };
      }
      version = result.version;
    } catch (e) {
      // SAM write failed → nothing is authoritative yet; do NOT mirror a stale set to Flask.
      const error = e instanceof ApiError || e instanceof Error ? e.message : String(e);
      return { success: false, error };
    }

    // Step 2 — mirror the SAME dimension set into Flask members.scope_dimensions (best-effort,
    // Requirement 22.6 / 26.5). SAM stays authoritative; a failed mirror leaves Flask's copy
    // stale until a surfaced RETRY succeeds — it does NOT fail the authoritative SAM write.
    try {
      const mirror =
        existing && existing.id != null && existing.scope_origin === 'tenant'
          ? await updateParameter(existing.id, { value: normalized, value_type: 'json' })
          : await createParameter({
            scope: 'tenant',
            namespace: MEMBERS_NAMESPACE,
            key,
            value: normalized,
            value_type: 'json',
            is_secret: false,
          });
      if (mirror.success === false) {
        return { success: false, version, mirrorError: mirror.error ?? 'Scope mirror write failed' };
      }
      return { success: true, version };
    } catch (e) {
      const mirrorError = e instanceof ApiError || e instanceof Error ? e.message : String(e);
      return { success: false, version, mirrorError };
    }
  }

  // Any other key stays on the Flask parameter-admin path.
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

// ---------------------------------------------------------------------------
// config#mail — the SAM-owned mail scalars save path (task 7.1, single door).
// ---------------------------------------------------------------------------

/**
 * The reader-shaped `config#mail` body authored through `PUT /members/config/mail` (Requirement
 * 9 / 15). The keys match the SAM `MembersProjectionReader` mail accessors and the Flask
 * `build_config_mail_row` builder EXACTLY so the writer and reader cannot drift:
 *
 *  - `mail_enabled` — the "cleared to send" gate (fail-closed bool).
 *  - `mail_domain`  — the tenant's own mail domain (e.g. `h-dcn.nl`); optional, NO safe default.
 *  - `mail_local_part` — the From local-part; defaults to `noreply` when blank.
 *  - `mail_certified` — the SES-verified gate (fail-closed bool).
 *  - `mail_reply_to_default` — the OPTIONAL scheduled/unattended-send Reply-To.
 *  - `consent_notice` — the OPTIONAL versioned bilingual consent notice
 *    (`{ version, text: { nl?, en? } }`); only send it when well-formed (a non-blank version AND
 *    at least one non-blank locale body), else omit the attribute entirely (the server shapes it
 *    the same way, but omitting a half-authored notice keeps the one authored body honest).
 */
export interface MembersMailConfigBody {
  mail_enabled: boolean;
  mail_domain?: string;
  mail_local_part: string;
  mail_certified: boolean;
  mail_reply_to_default?: string;
  consent_notice?: {
    version: string;
    text: Record<string, string>;
  };
  /**
   * OPTIONAL scope-matched copy toggle (spec 10 D9a / spec 11 R5.4). Owned by the Mail sub-tab
   * (one `config#mail` home, spec 11 §0.3); carried on the body so a form-shell mail write from
   * the Application Form Builder PRESERVES it verbatim rather than clobbering it.
   */
  application_scope_copy?: boolean;
  /**
   * OPTIONAL allowed embedding origin(s) (spec 11 R5.2 / S3). ONE tenant-authored list feeding
   * BOTH the CloudFront form's CSP `frame-ancestors` AND the SAM public API CORS. Authored by the
   * Application Form Builder's form-shell panel (`ApplicationFormShellPanel`, task 3.2). Omitted /
   * empty = standalone (no embedding allowed).
   */
  application_embed_origins?: string[];
}

/**
 * Save-once: author the SAM-owned `config#mail` scalars in a single `PUT /members/config/mail`
 * request (task 7.1, Property 8 — the single authoring door for the mail concern).
 *
 * The SAM write is AUTHORITATIVE: on a 200 the returned `version` IS the authored state (the
 * row-level write stamp), there is no projection step to wait on, so this surfaces no
 * pending-projection signal. The stable `{ success, error?, version? }` shape is what the typed
 * Mail editor consumes. A non-2xx (auth/entitlement 401/403, validation 400) is caught and
 * returned as `{ success: false, error }` with a caller-safe message — a failed save never claims
 * success.
 *
 * This writes ONLY the `config#mail` scalars; it does NOT touch the sender-identity Flask route
 * (three-surface model). It deliberately does NOT route through `saveMembersParameter` — that
 * function is keyed on `field_overlay` / `scope_dimensions` Flask-mirror semantics, whereas mail
 * is pure SAM with no Flask mirror.
 */
export async function saveMembersMailConfig(
  body: MembersMailConfigBody,
): Promise<{ success: boolean; error?: string; version?: string }> {
  try {
    const result = await writeMailConfig(body);
    if (result.success === false) {
      return { success: false, error: 'Mail config write failed' };
    }
    return { success: true, version: result.version };
  } catch (e) {
    // The Members API throws a structured ApiError on non-2xx; surface a caller-safe message.
    const error = e instanceof ApiError || e instanceof Error ? e.message : String(e);
    return { success: false, error };
  }
}

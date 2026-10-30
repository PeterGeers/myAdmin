/**
 * Members Module API — config resource group (task 5, pure move).
 *
 * The resolved field configuration/overlay (the membership-type catalog is retired, spec 03b).
 * Extracted verbatim from `membersApiService.ts`; behaviour unchanged.
 *
 * _Requirements: R7.3, R7.4_
 */

import { getJson, postJson, putJson, unwrapData } from './membersApiClient';

/** GET /members/field-config — the resolved field configuration/overlay. */
export async function getFieldConfig<T = unknown>(): Promise<T> {
  return unwrapData<T>(await getJson<unknown>('/members/field-config'));
}

/**
 * The SAM-owned config ids writable through `PUT /members/config/{configId}` (Requirement 2.1).
 * The route rejects any id outside this closed set with a 400/404, so the client surface mirrors it.
 */
export type MembersWritableConfigId = 'fields' | 'scope' | 'mail';

/**
 * The authoritative result the SAM config-write path returns on a 200 (Requirement 1.3). The write
 * IS the authored state — `version` is the row-level monotonic write stamp the row now carries,
 * there is no projection step to wait on.
 */
export interface MembersConfigWriteResult {
  success: boolean;
  configId: MembersWritableConfigId;
  version: string;
}

/**
 * PUT /members/config/{configId} — author a SAM-owned `config#{configId}` row (Requirement 1.1/1.2).
 *
 * The SAM write path is authoritative: on a 200 the returned `version` is the write stamp the row
 * now carries (Requirement 1.3) — there is no projection lag, so callers treat the returned result
 * as the committed state directly. `tenant_id` is resolved from the verified JWT at the edge, never
 * from the body (Requirement 3.2); `body` is the reader-shaped attribute object for that `configId`.
 *
 * Unwraps the module's `{ data }` envelope so the caller receives `{ success, configId, version }`.
 * A non-2xx (auth/entitlement 401/403, unknown-id 400/404, validation 400) propagates as the
 * structured ApiError thrown by `putJson`.
 */
export async function writeConfig(
  configId: MembersWritableConfigId,
  body: unknown
): Promise<MembersConfigWriteResult> {
  return unwrapData<MembersConfigWriteResult>(
    await putJson<unknown>(`/members/config/${encodeURIComponent(configId)}`, body)
  );
}

/**
 * ONE config#fields Change-Op (spec 03 — config-fields-foolproof-crud, design C1; backend task 2.7).
 *
 * The client sends INTENT BY IDENTITY — a bare field `key` / group `group` + the attribute change —
 * and the SERVER owns storage placement (which map, which dotted key). The client NEVER reconstructs
 * `{group}.{key}` or the `fields`/`overrides` split (steering 39). Each op names its KIND:
 *
 *  - `set_field`             — field DEFINITION attrs only (`{type,label,order,required,visible,
 *                              choices,options,scope,functional_group}`), NO `application_*`.
 *  - `set_field_application` — the four form attrs only (`{application_visible,application_required,
 *                              application_choices,format}`).
 *  - `reset_field`           — revert a base/calculated field's override (REMOVE it).
 *  - `delete_field`          — delete a tenant-added variable field.
 *  - `set_group`             — group attrs (`{label,order}`); materializes a base group if absent.
 *  - `delete_group`          — delete an (empty) group.
 *
 * `attrs` is the identity-keyed attribute patch (absent key = leave untouched; explicit `null` =
 * remove that attribute). `client_op_id` is an OPTIONAL idempotency token a lost-response retry may
 * carry so the server recognizes a replay rather than a spurious conflict.
 */
export type FieldConfigChangeOp =
  | { op: 'set_field'; key: string; attrs: Record<string, unknown>; client_op_id?: string }
  | { op: 'set_field_application'; key: string; attrs: Record<string, unknown>; client_op_id?: string }
  | { op: 'reset_field'; key: string; client_op_id?: string }
  | { op: 'delete_field'; key: string; client_op_id?: string }
  | { op: 'set_group'; group: string; attrs: Record<string, unknown>; client_op_id?: string }
  | { op: 'delete_group'; group: string; client_op_id?: string };

/**
 * PUT /members/config/fields — apply a CHANGE-OP list to `config#fields` (spec 03 task 2.7).
 *
 * The authoritative, foolproof write path: the body is `{ ops: [...] }`, a list of identity-keyed
 * Change-Ops (see {@link FieldConfigChangeOp}). The server validates each op, decides storage
 * placement itself, and issues a single version-conditional `update_item` PATH write per op — so a
 * partial payload can NEVER truncate the catalog (spec 03 root cause). This is the ONLY write path
 * to this route — the retired whole-overlay body (`writeFieldConfig`) no longer exists (task 5.2).
 *
 * Unwraps the module's `{ data }` envelope. A non-2xx propagates as the structured ApiError thrown
 * by `putJson`: a validation/malformed-op 400, an auth/entitlement 401/403, and a 409 when the
 * version-conditional write lost the race (the caller surfaces "reload and retry").
 */
export async function applyFieldConfigChangeOps(
  ops: FieldConfigChangeOp[]
): Promise<MembersConfigWriteResult> {
  return unwrapData<MembersConfigWriteResult>(
    await putJson<unknown>('/members/config/fields', { ops })
  );
}

/**
 * PUT /members/config/scope — author the `config#scope` row (Requirement 8 / 22).
 *
 * Thin convenience over {@link writeConfig} pinning the `scope` config id. `body` MUST be the SAM
 * `config#scope` shape — `{ dimensions: [...] }` in the ScopeDimension shape `get_scope_config`
 * reads (empty `dimensions` is valid = tenant-wide). SAM `config#scope` is the AUTHORITATIVE scope
 * source (Requirement 22.1); the frontend writes it FIRST, then mirrors the dimension set into the
 * Flask `members.scope_dimensions` validator copy (Requirement 22.5 / 26.2).
 */
export async function writeScopeConfig(dimensions: unknown[]): Promise<MembersConfigWriteResult> {
  return writeConfig('scope', { dimensions });
}

/**
 * PUT /members/config/mail — author the `config#mail` row (Requirement 9 / 14.4 / 15.2 / 20).
 *
 * Thin convenience over {@link writeConfig} pinning the `mail` config id — the single authoring
 * door for the SAM-owned `config#mail` scalars (Property 8). `body` MUST be the reader-shaped
 * `config#mail` object the SAM mail accessors read back and `ConfigWriteService._validate_mail_body`
 * shapes: `mail_enabled` / `mail_certified` (fail-closed bools), `mail_local_part` (default
 * `"noreply"`), `mail_domain` (optional — omitted server-side when blank; no safe default),
 * `mail_reply_to_default` (optional), and `consent_notice` (the versioned bilingual notice,
 * `{ version, text: { <locale>: body } }` — omitted server-side unless well-formed).
 *
 * This writes ONLY the `config#mail` scalars; the sender-identity surface keeps its own Flask
 * `/api/members/sender-identities` route (three-surface model — the mail config write never folds
 * the sender identities in).
 */
export async function writeMailConfig(body: unknown): Promise<MembersConfigWriteResult> {
  return writeConfig('mail', body);
}

/**
 * The authoritative result the SAM application-form publish route returns on a 200 (spec 12 R5 /
 * design §C4, OQ1 = option 1). Publish RE-RENDERS the live static artifact from the tenant's
 * current `config#fields`/`config#mail` through the single filter authority and REPLACES the prior
 * version, bumping `published_version`/`published_at`. The write IS the published state.
 *
 * NOTE (spec 12 Phase 2, task 2.1): the SAM route itself is NOT built yet, and the live S3 write is
 * DORMANT until the hosting migration (Phase 0.1) + IAM (Phase 3) land. This client caller exists so
 * the frontend Publish button + readiness/save≠publish UX can land on the account-agnostic track
 * now (Phase 6); tests mock it, and it will resolve for real once the route ships.
 */
export interface MembersApplicationPublishResult {
  success: boolean;
  /** The public slug the artifact was published under (`{slug}.jabaki.nl`). */
  slug?: string;
  /** The monotonic published version the row now carries (bumped on each publish). */
  published_version?: number;
  /** ISO-8601 timestamp of this publish. */
  published_at?: string;
}

/**
 * POST /members/application-form/publish — deliberately publish the application form (spec 12 R5 /
 * design §C4, OQ1 = option 1).
 *
 * The EXPLICIT publish action: an admin-gated control that re-renders the live static artifact from
 * the tenant's current `config#fields`/`config#mail` and REPLACES the prior published version.
 * Saving a draft NEVER publishes — only this call does (save ≠ publish). `tenant_id` is resolved
 * from the verified JWT at the edge, never the body, so this takes NO body. The route is
 * readiness-gated server-side (slug + certified sender + ≥1 on-form field, R5.4); the builder also
 * gates the button client-side as a convenience so an unready form never calls it.
 *
 * Unwraps the module's `{ data }` envelope. A non-2xx (auth/entitlement 401/403, readiness-refusal
 * 409/422, unknown-route 404 while the SAM route is not yet deployed) propagates as the structured
 * ApiError thrown by `postJson` — the caller surfaces a caller-safe message.
 */
export async function publishApplicationForm(): Promise<MembersApplicationPublishResult> {
  return unwrapData<MembersApplicationPublishResult>(
    await postJson<unknown>('/members/application-form/publish')
  );
}


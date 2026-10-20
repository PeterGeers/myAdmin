/**
 * Members Module API — config resource group (task 5, pure move).
 *
 * The resolved field configuration/overlay and the membership-type catalog.
 * Extracted verbatim from `membersApiService.ts`; behaviour unchanged.
 *
 * _Requirements: R7.3, R7.4_
 */

import { getJson, postJson, putJson, deleteJson, unwrapData } from './membersApiClient';
import type { MembershipTypeCreateBody, MembershipTypeUpdateBody } from '../../types/members';

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
 * PUT /members/config/fields — author the `config#fields` row (Requirement 7).
 *
 * Thin convenience over {@link writeConfig} pinning the `fields` config id. `body` MUST be the SAM
 * `config#fields` shape — `fields` / `overrides` / `functional_groups` (NO `default_page_size`,
 * retired per Requirement 25) — matching `ConfigWriteService._validate_fields_body`.
 */
export async function writeFieldConfig(body: unknown): Promise<MembersConfigWriteResult> {
  return writeConfig('fields', body);
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
 * GET /membership-types — the membership-type catalog.
 * @param activeOnly - when true, appends `?active_only=true`.
 */
export async function listMembershipTypes<T = unknown>(activeOnly?: boolean): Promise<T> {
  const endpoint = activeOnly ? '/membership-types?active_only=true' : '/membership-types';
  return unwrapData<T>(await getJson<unknown>(endpoint));
}

/**
 * POST /membership-types — create a membership-type catalog entry (members:admin).
 * Unwraps the `{ data }` envelope; a non-2xx (e.g. 409 duplicate `type_code`)
 * propagates as the structured ApiError thrown by `postJson`.
 */
export async function createMembershipType<T = unknown>(
  body: MembershipTypeCreateBody
): Promise<T> {
  return unwrapData<T>(await postJson<unknown>('/membership-types', body));
}

/**
 * PUT /membership-types/{type_code} — update a membership-type entry (members:admin).
 * `type_code` is the stable id (immutable on edit). Unwraps the `{ data }`
 * envelope; a non-2xx (e.g. 404 absent) propagates as the structured ApiError.
 */
export async function updateMembershipType<T = unknown>(
  typeCode: string,
  body: MembershipTypeUpdateBody
): Promise<T> {
  return unwrapData<T>(
    await putJson<unknown>(`/membership-types/${encodeURIComponent(typeCode)}`, body)
  );
}

/**
 * DELETE /membership-types/{type_code} — soft-delete/retire an entry (members:admin).
 * Server sets `active=false` (never a hard delete). Unwraps the `{ data }`
 * envelope; a non-2xx (e.g. 404 absent) propagates as the structured ApiError.
 */
export async function deactivateMembershipType<T = unknown>(typeCode: string): Promise<T> {
  return unwrapData<T>(
    await deleteJson<unknown>(`/membership-types/${encodeURIComponent(typeCode)}`)
  );
}

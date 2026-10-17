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

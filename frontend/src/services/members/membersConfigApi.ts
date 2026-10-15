/**
 * Members Module API — config resource group (task 5, pure move).
 *
 * The resolved field configuration/overlay and the membership-type catalog.
 * Extracted verbatim from `membersApiService.ts`; behaviour unchanged.
 *
 * _Requirements: R7.3, R7.4_
 */

import { getJson, unwrapData } from './membersApiClient';

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

/**
 * Members table pagination precedence (Phase 2 step (a) — the view_contexts.page_size re-home).
 *
 * Phase 2 retires `view_contexts`; its one live residual — the per-context `page_size` —
 * collapses to a SINGLE tenant-level `default_page_size` scalar served on the
 * `GET /members/field-config` response, with a per-user preference override and a platform
 * fallback. The SPA renders ONE Members table, so there is no per-context page size any more.
 *
 * This module is the single, pure home of the precedence rule
 *
 *     userPreference ?? default_page_size ?? platformDefault
 *
 * so `MembersPage.tsx` (task 2.1) consumes it instead of carrying the logic inline. Keeping it
 * here (one exported function) means the property test (task 2.2, Property 1) targets the real
 * resolver — never a duplicate.
 *
 * @see .kiro/specs/Members/Parameter redesign/phase-2-delete-redundant-surface/design.md
 *      — "What the SPA reads after (a)+(b)"
 * @see requirements.md Property 1 / R2.2, R2.3, R2.4
 */

/**
 * The platform table-toolkit fallback rows-per-page.
 *
 * Used when NEITHER a per-user preference NOR a tenant `default_page_size` is set — the same
 * "renderer applies its own default" behaviour `view_context.page_size == null` had before
 * Phase 2 (design §Data Models). A positive integer, by construction.
 */
export const PLATFORM_DEFAULT_PAGE_SIZE = 25;

/** A candidate page-size value as it arrives from a preference or the field-config response. */
export type PageSizeCandidate = number | null | undefined;

/**
 * Return `true` for a value usable as a page size: a positive, finite integer.
 *
 * Mirrors the SAM read-side guard (`get_default_page_size` returns a positive int or `None`):
 * a non-number, `NaN`, non-integer, zero, or negative value is NOT a usable page size and is
 * skipped in the precedence chain. `boolean` is excluded because `true`/`false` are never a
 * legitimate rows-per-page.
 */
function isUsablePageSize(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0;
}

/**
 * Resolve the Members table's rows-per-page by the Phase 2 precedence rule.
 *
 * Precedence (first usable wins):
 *   1. `userPreference` — the user's own per-user column/table preference `page_size`;
 *   2. `tenantDefault`  — the tenant's `default_page_size` from the field-config response;
 *   3. `PLATFORM_DEFAULT_PAGE_SIZE` — the platform table-toolkit fallback.
 *
 * The result is ALWAYS a positive integer (total + deterministic — Property 1): any
 * absent/zero/negative/NaN/non-integer candidate is skipped, and the platform default is a
 * positive int, so the chain can never resolve to blank, zero, or NaN.
 *
 * @param userPreference the user's persisted page-size preference (absent/unusable → skip)
 * @param tenantDefault  the tenant `default_page_size` from field-config (absent/unusable → skip)
 * @param platformDefault the platform fallback (defaults to `PLATFORM_DEFAULT_PAGE_SIZE`)
 */
export function resolvePageSize(
  userPreference: PageSizeCandidate,
  tenantDefault: PageSizeCandidate,
  platformDefault: number = PLATFORM_DEFAULT_PAGE_SIZE,
): number {
  if (isUsablePageSize(userPreference)) return userPreference;
  if (isUsablePageSize(tenantDefault)) return tenantDefault;
  // Guard the fallback too: a caller passing an unusable platformDefault still
  // resolves to the known-good platform constant, so the result is ALWAYS a
  // positive integer (Property 1 — total + deterministic, R2.4/R9.4).
  return isUsablePageSize(platformDefault) ? platformDefault : PLATFORM_DEFAULT_PAGE_SIZE;
}

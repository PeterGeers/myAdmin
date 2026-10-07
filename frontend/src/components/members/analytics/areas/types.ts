/**
 * Shared prop + capability types for the Member Analytics areas.
 *
 * The three areas (Overview / Distributions / Pivot Views) all receive the same
 * prop bundle from `MemberAnalyticsPanel` (task 3.3): the page's OWN filtered
 * dataset (`processedData`), the full scope-authorized `members` set, the
 * resolved `fieldConfig` (incl. analytics config), the active `language`, and
 * the caller's `capabilities`. Keeping one shape here keeps the panel's prop
 * plumbing and each area's signature in lock-step as the real areas land in
 * phases 4/5/7.
 *
 * @module components/members/analytics/areas/types
 * @see .kiro/specs/Members/member-analytics (design C1; requirements R1.3, R1.6)
 */

import type { Member, MemberRow, FieldConfig } from '../../../../types/members';

/**
 * Capability flags the analytics surface honors. `members:read` gates the whole
 * page (checked upstream in `MemberAnalyticsPage`); `canExport` (`members:export`)
 * gates the result exports (CSV / PDF labels / mail) that live in the Pivot
 * Views area (R4.9/R4.11).
 */
export interface MemberAnalyticsCapabilities {
  /** Whether the caller may export analytics results (CSV / PDF labels / mail). */
  canExport: boolean;
  /**
   * Whether the caller holds `members:write` (Members_CRUD). Combined with
   * `canExport` it gates CREATING / editing a shared analytics-set (R11: create =
   * export|write; edit = write|admin). Optional so existing callers that only
   * pass `canExport` keep compiling; treated as `false` when absent.
   */
  canWrite?: boolean;
  /**
   * Whether the caller holds `members:admin` (Tenant_Admin). Combined with
   * `canWrite` it gates DELETING a set from the shared library (R11: delete =
   * write|admin). Optional; treated as `false` when absent.
   */
  isAdmin?: boolean;
}

/**
 * The common prop bundle every analytics area receives from the panel.
 */
export interface MemberAnalyticsAreaProps {
  /**
   * The page's OWN filtered dataset — rows after the analytics page's own
   * filter/sort (`useFilterableTable` → `processedData`). Every figure/chart/set
   * derives from this (Option A, R1.5/R5.1), NOT from the full `members` set.
   */
  processedData: MemberRow[];
  /**
   * The full scope-authorized member set (pre page-filter), for the areas that
   * need the unfiltered-but-scoped baseline (e.g. excluded-count context).
   */
  members: Member[];
  /** Resolved field config (fixed ⊕ overlay ⊕ calculated + analytics config). */
  fieldConfig: FieldConfig | null;
  /**
   * Whether the tenant authored an analytics config block (R1.4 "no analytics
   * config" signal, derived once by the page via `hasAnalyticsConfig`). When
   * `false`, the fixed/calculated areas (Overview, Distributions over
   * age/years_member) still render, but the config-DEPENDENT sets (role-backed
   * presets etc.) degrade with a bilingual reason rather than erroring/crashing.
   * This is NOT an error or empty signal — it is the third, distinct non-happy
   * state (R1.4 / R9.5, design C1 "Error handling").
   */
  hasAnalyticsConfig: boolean;
  /** Active language ('nl' | 'en' …) for bilingual label resolution. */
  language: string;
  /** Caller capabilities (e.g. `canExport`). */
  capabilities: MemberAnalyticsCapabilities;
}

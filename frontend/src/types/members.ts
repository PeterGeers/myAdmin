/**
 * Members module frontend types (minimal).
 *
 * These are the minimal shapes the Members Overzicht page (task 17.2) needs to
 * render the table, drive the compact/full view switch, show the subgroup/region
 * badge, and open the read-only view modal. Task 16.2 can refine/extend these
 * without changing the request plumbing in `membersApiService.ts`.
 *
 * Shapes mirror the projected `config#fields` overlay + the module's member
 * records as described in the S5b design (design.md §C4/C7/C8). The field-config
 * types intentionally cover only what the view switch reads.
 *
 * _Requirements: R7.5, R7.6_
 */

/** A localized label ({ nl, en }) as emitted by the projection/field-config. */
export interface LocalizedLabel {
  nl?: string;
  en?: string;
  [locale: string]: string | undefined;
}

/**
 * A single member as returned by `GET /members/{member_id}` (view modal) and,
 * in a flattened form, by `GET /members` (table rows).
 *
 * The module resolves a fixed base ⊕ tenant overlay, so beyond the known fixed
 * fields a member may carry arbitrary overlay fields keyed by the field-config
 * `key`. We model that with an index signature of `unknown` values.
 */
export interface Member {
  /** Stable member id (module-assigned). */
  member_id: string;
  /** Personal name (fixed base field). */
  name?: string;
  /** Contact email (fixed base field). */
  email?: string;
  /** Lifecycle status of the member/primary membership. */
  status?: string;
  /** Membership type key (see `MembershipType.key`). */
  membership_type?: string;
  /** Membership number (carried through from the nested record; optional). */
  member_number?: string;
  /**
   * The primary membership id (surfaced from the module's nested `membership`
   * record when present). The single lifecycle-transition action targets this
   * id: `POST /members/{member_id}/memberships/{membership_id}/transition`.
   */
  membership_id?: string;
  /** The scope dimension the member belongs to (e.g. region "Noord"). */
  region?: string;
  /** Overlay + any additional module fields keyed by field-config key. */
  [key: string]: unknown;
}

/**
 * A flat row for the table. Extends {@link Member} with any promoted/derived
 * display values the page computes (kept as an index signature so the
 * filter/sort framework — which operates on `Record<string, any>` — is happy).
 */
export interface MemberRow extends Member {
  /** Display value for the subgroup/region badge column. */
  region_display?: string;
}

/**
 * A membership-type catalog entry (`GET /membership-types`). Only the fields the
 * page/dropdowns read are modeled here.
 */
export interface MembershipType {
  /** Stable key used on the member record's `membership_type`. */
  key: string;
  /** Human label (localized or plain). */
  label?: string | LocalizedLabel;
  /** Whether the type is currently active (for active-only dropdowns). */
  active?: boolean;
}

/**
 * One field descriptor from the resolved field config
 * (`GET /members/field-config`). Drives which columns the compact/full view
 * switch shows and how they are labeled.
 */
export interface FieldConfigField {
  /** Field key — matches a property on {@link Member}. */
  key: string;
  /** Field label (localized object or plain string). */
  label?: string | LocalizedLabel;
  /** Value type hint (e.g. "string", "number", "date"). */
  type?: string;
  /** Presentation/sort order. */
  order?: number;
  /**
   * Whether the field belongs to the compact (always-visible) view. When
   * omitted, the page treats the field as full-view-only (overlay column).
   */
  compact?: boolean;
}

/**
 * The resolved field configuration returned by `GET /members/field-config`:
 * the fixed base ⊕ tenant overlay, plus the scope dimensions the tenant
 * configured (used for the region/subgroup badge + filters).
 */
export interface FieldConfig {
  /** Ordered field descriptors (fixed ⊕ overlay). */
  fields: FieldConfigField[];
  /** Configured scope dimensions (e.g. region with its allowed values). */
  dimensions?: ScopeDimension[];
  /**
   * The tenant's membership lifecycle, as described by the MODULE (design C2 —
   * a declarative state machine, never hardcoded in the SPA). Optional: a tenant
   * with no configured lifecycle has no state machine, so no transitions are
   * offered (deny-by-default at the UI). The module remains authoritative — it
   * re-validates every transition and answers 409 with reasons on a denial.
   */
  lifecycle?: LifecycleConfigShape;
}

/**
 * A declarative membership-lifecycle description, as returned by the module.
 *
 * The SPA reads the ALLOWED TRANSITION TARGETS for a member's current state from
 * `allowed_transitions[<currentState>]` (or, equivalently, `transitions`), NEVER
 * from a hardcoded status list. When the module does not describe a lifecycle,
 * no targets are offered. Two interchangeable shapes are accepted so the page is
 * robust to the module's projection:
 *   - `allowed_transitions`: a map `{ <fromState>: [<toState>, ...] }`.
 *   - `transitions`: a flat edge list `[{ from, to }, ...]`.
 */
export interface LifecycleConfigShape {
  /** The states this tenant uses (informational; order kept). */
  allowed_states?: string[];
  /** The initial state a new member starts in (informational). */
  initial_state?: string;
  /** Map of `fromState -> reachable toStates` (preferred). */
  allowed_transitions?: Record<string, string[]>;
  /** Flat edge list `[{ from, to }]` (alternative to `allowed_transitions`). */
  transitions?: { from: string; to: string }[];
  /**
   * States (or `<from>-><to>` edges) that require a guard-context approval flag
   * (h-dcn's `context.approved`). When a chosen target is listed here the
   * transition modal surfaces an approval toggle threaded through as
   * `context.approved`. Optional — absent means no approval facts are needed.
   */
  requires_approval?: string[];
}

/** A configured scope dimension (mirrors the projected `config#scope` shape). */
export interface ScopeDimension {
  /** Dimension key (e.g. "region"). */
  key: string;
  /** Dimension label (localized or plain). */
  label?: string | LocalizedLabel;
  /** Whether the dimension is enabled. */
  enabled?: boolean;
  /** Allowed values (e.g. ["Noord", "Zuid", "Oost", "West"]). */
  values?: string[];
}

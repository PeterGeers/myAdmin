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
  /**
   * The catalog reference code the member record stores in `membership_type`.
   * This is the AUTHORITATIVE field the Members API returns (`GET /membership-types`
   * serializes `type_code`). It is the dropdown option value.
   */
  type_code?: string;
  /**
   * Legacy/alias for {@link type_code}. Older callers/tests used `key`; the API emits
   * `type_code`. Kept optional so both shapes resolve (options prefer `type_code`).
   */
  key?: string;
  /** Human label (localized or plain). */
  label?: string | LocalizedLabel;
  /** Whether the type is currently active (for active-only dropdowns). */
  active?: boolean;
}

/**
 * Where a resolved field came from (mirrors the module's `FieldOrigin`, design
 * C-FIELDS): the platform fixed base, a tenant overlay (parameter-driven), or a
 * derivation (calculated, read-only, never stored — R4.4). The frontend renders
 * all three uniformly; `calculated` fields are surfaced as READ-ONLY values.
 */
export type FieldOrigin = 'fixed' | 'variable' | 'calculated';

/**
 * One field descriptor from the resolved field config
 * (`GET /members/field-config`). Drives which columns a view context / the
 * compact/full view switch shows, how they are labeled, and how their value is
 * rendered (parameter-driven overlay fields + calculated read-only fields are
 * first-class column candidates alongside the fixed base — R5.1, R5.2).
 */
export interface FieldConfigField {
  /** Field key — matches a property on {@link Member}. */
  key: string;
  /**
   * STORAGE bucket (`personal` / `membership` / `overlay`), fixed by origin. Distinct from
   * {@link functional_group} (the parameter-driven display group). Carried through from the
   * resolved config so the modal can shape the nested write payload by storage group.
   */
  group?: string;
  /** Field label (localized object or plain string). */
  label?: string | LocalizedLabel;
  /** Value type hint (e.g. "string", "number", "date", "enum", "reference"). Drives cell/input formatting. */
  type?: string;
  /** Whether the field is required input (server-authoritative; the modal mirrors it for UX). */
  required?: boolean;
  /** Presentation/sort order. */
  order?: number;
  /**
   * Where the field came from (`fixed` ⊕ `variable` overlay ⊕ `calculated`).
   * A `calculated` field is derived + READ-ONLY (never stored, R4.4); the table
   * renders its value like any other field but never offers it for edit.
   */
  origin?: FieldOrigin;
  /**
   * Field-level visibility gate (the authoritative candidate-column gate, R5.1).
   * When explicitly `false` the field is NOT a column candidate (a view context
   * only chooses among visible fields). Omitted/`true` = visible.
   */
  visible?: boolean;
  /**
   * The PARAMETER-DRIVEN display group (R4.9) the modals SECTION by (design C-SURFACE),
   * orthogonal to the storage {@link group}. References a {@link FunctionalGroup.key} in
   * `FieldConfig.functional_groups`; a field whose group is absent from the catalog falls
   * back to a default section at render (Property 7).
   */
  functional_group?: string;
  /**
   * READ-ONLY marker: `true` for calculated (derived) fields, which are never editable (R4.4).
   * The edit/add modals render these as disabled/omit them from the write payload.
   */
  read_only?: boolean;
  /**
   * Per-field conditional-visibility condition (R4.12). A map `{ controllingKey: scalar | [values] }`
   * (implicit AND): the field is shown only when every entry holds for the current form values.
   * A hidden field is not rendered, not required, and not sent — mirrored authoritatively by the
   * server ({@link https} same rule). Absent/empty = always shown.
   */
  show_when?: Record<string, unknown> | null;
  /**
   * The `member_number` tenant format constraint (R4.8) — present only on that field. Drives
   * IMMEDIATE frontend format feedback for the manual-entry string; the server is authoritative.
   */
  member_number_format?: MemberNumberFormat | null;
  /**
   * Enum/reference options as served by the field config. Either a bare value list
   * (`string[]`) or rich `{ value, label{nl,en}, roles? }` entries (R4.11/R4.12). The
   * `roles` on an option is the value-level gate: the modal filters a dropdown to the
   * caller's permitted options as a CONVENIENCE (the domain rejects a disallowed value
   * authoritatively).
   */
  options?: Array<string | EnumOptionConfig> | null;
  /**
   * Whether the field belongs to the compact (always-visible) view. When
   * omitted, the page treats the field as full-view-only (overlay column).
   */
  compact?: boolean;
}

/**
 * A rich enum option from the resolved field config (`{ value, label{nl,en}, roles? }`,
 * R4.11/R4.12). `roles` is the value-level role gate: when present, only a caller holding one
 * of these roles may select the option. An option with no `roles` is open to anyone who may
 * edit the field. Frontend filtering is CONVENIENCE only — the domain is the authoritative gate.
 */
export interface EnumOptionConfig {
  value: string;
  label?: LocalizedLabel;
  roles?: string[] | null;
}

/**
 * The `member_number` tenant format constraint (R4.8). Carries the effective `regex` (the
 * compiled prefix+width or a raw regex), the `prefix`/`width` primitives, and a human-readable
 * `example` for the format hint. Convenience feedback only — the server validates authoritatively.
 */
export interface MemberNumberFormat {
  prefix?: string;
  width?: number;
  regex?: string | null;
  example?: string | null;
}

/**
 * One functional (display) group in the tenant's catalog (R4.9). The modals + view contexts
 * SECTION the resolved field set by these: each section is one entry, ordered by `order`. A
 * field whose `functional_group` is absent from this catalog falls back to a default section.
 */
export interface FunctionalGroup {
  key: string;
  label?: LocalizedLabel;
  order?: number;
}

/**
 * The resolved field configuration returned by `GET /members/field-config`:
 * the fixed base ⊕ tenant overlay, plus the scope dimensions the tenant
 * configured (used for the region/subgroup badge + filters).
 */
export interface FieldConfig {
  /** Ordered field descriptors (fixed ⊕ overlay). */
  fields: FieldConfigField[];
  /**
   * The tenant's functional (display) group catalog (R4.9), ordered by `order`. The modals
   * section the resolved field set by these. Empty/absent = the modals section by the fields'
   * own `functional_group` values (base defaults), with a default section for the rest.
   */
  functional_groups?: FunctionalGroup[];
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
  /**
   * Parameter-driven view contexts (s5c task 3.2/3.3, design C-VIEW). Each context is a
   * named, permission-gated column-set over the resolved field config. A missing/empty
   * value means the module returns exactly one default context (empty columns = all
   * visible fields). The SPA renders a context dropdown (gated by `permission_roles`) and
   * hands the selected context to the existing filterable-table toolkit.
   */
  view_contexts?: ViewContext[];
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

/**
 * A parameter-driven view context (design C-VIEW). `columns`/`filterable_columns` are
 * `field_key`s resolved against `FieldConfig.fields` at render (unresolvable keys are
 * SKIPPED, never a crash — Property 7). Empty `columns` = all visible fields (the
 * default-context sentinel). `permission_roles` gates the dropdown (view convenience
 * only; row scope is always enforced server-side).
 */
export interface ViewContext {
  /** Stable context key (never user-facing). The synthesized default uses `__default__`. */
  key: string;
  /** Bilingual display label. */
  label?: LocalizedLabel;
  /** Roles allowed to select this context in the dropdown. Empty = available to all. */
  permission_roles?: string[];
  /** Ordered field_key columns to show. Empty = all visible fields. */
  columns?: string[];
  /** Subset of field_keys that are filterable. */
  filterable_columns?: string[];
  /** Default sort for this context. */
  default_sort?: { field: string; direction: 'asc' | 'desc' } | null;
  /** Rows per page (renderer applies its own default when null/absent). */
  page_size?: number | null;
}

/**
 * A member-user's SCOPE grant for one module (s5d task 6.1).
 *
 * The Tenant-Admin authoring surface maps each enabled scope dimension key
 * (`region`, `age_group`, …) to the granted list of CANONICAL values, or to the
 * all-access sentinel `["*"]`. An absent dimension / empty list = no grant for
 * that dimension (deny-by-default). This is the exact `scopes` JSON shape the
 * backend stores in `user_tenant_scope` and returns from / accepts on the
 * scope-authoring endpoints (design → Data Models `scopes` JSON; R4.1, R4.3).
 *
 * _Requirements: R4.1, R5.1_
 */
export type ScopeGrant = Record<string, string[]>;

/**
 * One enabled scope dimension as offered to the scope-editor picker
 * (`GET /api/tenant-admin/scope-dimensions/<module>`, D4/R5.1). Distinct from the
 * projected {@link ScopeDimension} (field-config) shape: this is the AUTHORING
 * option — the canonical `values` the multi-select offers, plus the member
 * `field` the dimension binds to when present (design → dimension model, R6.3).
 *
 * _Requirements: R4.1, R5.1_
 */
export interface ScopeDimensionOption {
  /** Dimension key (e.g. "region"). The `ScopeGrant` key this option authors. */
  key: string;
  /** Human label for the picker (localized object or plain string). */
  label?: string | LocalizedLabel;
  /** Canonical values the multi-select offers (never `Regio_` role names). */
  values: string[];
  /** The member field the dimension binds to, when the config carries one (R6.3). */
  field?: string;
}

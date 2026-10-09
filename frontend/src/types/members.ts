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

import type { PivotConfig } from './pivot';
import type { LabelOptions } from '../components/members/analytics/labelOptions';

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
 * Summary of a member analytics-set as returned by `GET /members/analytics-sets`
 * (the list feed). The Members module now OWNS member saved-sets in DynamoDB
 * (F-012), replacing the Flask `/api/pivot/models` store — so the member
 * saved-set path goes through `membersApiService`, not `pivotService`.
 *
 * NOTE: `id` is the backend `set_id` — a STRING (a server-chosen uuid4 hex),
 * NOT the pivot models' numeric id.
 */
export interface MemberAnalyticsSetSummary {
  /** The backend `set_id` (string, server-chosen opaque id). */
  id: string;
  /** The user-authored set name. */
  name: string;
  /** `'count'` (aggregate) or `'list'` (filtered list). */
  kind: 'count' | 'list';
  /**
   * Whether the set carries a stored {@link MemberDelivery} block (R3). Surfaced
   * on the list feed so the UI can gate the "Schedule" action (R5 — a schedule
   * can only be attached to a set that HAS a delivery) without fetching the full
   * set. Absent on a legacy feed → treated as `false` (no delivery known).
   */
  hasDelivery?: boolean;
}

/**
 * The two delivery MODES a saved set's optional {@link MemberDelivery} block may
 * carry (R3, design §2.1), mirroring the SAM entity's `DELIVERY_MODES`:
 *
 * - `per_recipient` — mail each member in the result individually with mail-merge;
 *   recipient addresses are resolved from the dataset at run time and are therefore
 *   NEVER stored on the block (`recipients` is absent/empty).
 * - `to_fixed` — send the result as an attachment to an explicit, stored
 *   `recipients` list (e.g. a handling agent outside the dataset).
 */
export type MemberDeliveryMode = 'per_recipient' | 'to_fixed';

/** The optional attachment a delivery produces (R3, design §2.1); `null`/absent = none. */
export type MemberDeliveryAttachment = 'csv' | 'pdf_labels';

/**
 * The OPTIONAL stored "what to do with the result" block (R3, design §2.1) on a
 * saved set — the camelCase frontend mirror of the SAM entity's snake_case
 * `delivery` block. Absent/`undefined` on a set with no delivery (a legacy set
 * written before the field existed loads without it and keeps working).
 *
 * The mapper (`membersApiService`) converts to/from the stored snake_case block
 * (`{ mode, template_id, attachment, recipients, label_options }`), using the
 * shared label-options model's `toStored`/`fromStored` for the `label_options`
 * sub-block (one label-options model with R6 — task 6.3, no fork).
 *
 * Mode rules (enforced server-side in the SAM entity's `validate()`): `to_fixed`
 * requires a non-empty `recipients` list; `per_recipient` stores no recipients.
 */
export interface MemberDelivery {
  /** The delivery mode discriminator. */
  mode: MemberDeliveryMode;
  /** A stored template ref (`template#<id>`, R2), or `null` for a bare set. */
  templateId: string | null;
  /** The attachment to produce, or `null` for none. */
  attachment: MemberDeliveryAttachment | null;
  /** `to_fixed` ONLY — the explicit recipient addresses; empty for `per_recipient`. */
  recipients: string[];
  /**
   * The shared (camelCase) label-options model — present only for `pdf_labels`,
   * `null` otherwise. The SAME `LabelOptions` R6 uses interactively (task 6.3).
   */
  labelOptions: LabelOptions | null;
}

/**
 * The accepted/queued receipt the deliver route returns (mail-spec R3.2/R3.5),
 * the camelCase mirror of the SAM `/deliver` 202 body
 * (`{ run_id, mode, enqueued, skipped_no_address, job_ids }`). A deliver NEVER
 * blocks on the SES send — the route resolves the set's stored delivery, runs
 * the synchronous pre-send certification gate, builds the send job(s), and
 * ENQUEUES them; a worker performs the actual send. This receipt lets the UI
 * surface a clear "queued, N recipients" acknowledgment (R3.5) without waiting.
 */
export interface DeliveryRunResult {
  /** The logical run id (audit attribution + status drill-down, R9). */
  runId: string;
  /** The delivery mode that ran (`per_recipient` fan-out or one `to_fixed` message). */
  mode: MemberDeliveryMode;
  /** How many send jobs went on the queue (one per `to_fixed`; one per member otherwise). */
  enqueued: number;
  /** `per_recipient` rows skipped for want of a resolvable address (0 for `to_fixed`). */
  skippedNoAddress: number;
  /** The stable job ids enqueued (idempotency / observability). */
  jobIds: string[];
}

/**
 * The lifecycle status of a send-run (R9.1), the camelCase mirror of the SAM
 * `mailrun#` record's `status`: written `queued` at enqueue, advanced to
 * `sending` then `completed` by the worker as it drains the run's jobs.
 */
export type MailRunStatus = 'queued' | 'sending' | 'completed';

/**
 * The status of a single FAILURE sub-record (R9.5), the camelCase mirror of the
 * SAM `mailrecipient#` record's `status`: a send-time `failed`, or a late async
 * `bounced` / `complaint` (R8.4, the layered SES-feedback statuses). A success is
 * NEVER stored per-recipient — it is only counted in the run tally.
 */
export type MailFailureStatus = 'failed' | 'bounced' | 'complaint';

/**
 * One send-run TALLY as surfaced by `GET /members/mail-runs` (mail-spec R9.1/R9.2),
 * the camelCase mirror of the SAM `mailrun#` record after the edge strips the
 * DynamoDB plumbing keys (`tenant_id` / `sk` / `ttl`). This is the aggregated
 * outcome the status/history list renders — "Newsletter — 198 sent, 2 failed"
 * (R9.2) — one row per run, newest first (ordered server-side).
 *
 * HONESTY OF STATUS (R9.4): `sent` means "SES ACCEPTED the message (a MessageId
 * was returned)", which is NOT the same as "delivered to the inbox". The screen
 * MUST NOT claim "delivered" on the strength of this count alone — true
 * delivered/bounced status is the separate, layered SES-feedback concern (R9.5).
 */
export interface MailRunSummary {
  /** The logical run id (the drill-down key for `GET /members/mail-runs/{runId}`). */
  runId: string;
  /** Which mode produced the run (`per_recipient` fan-out or one `to_fixed` message). */
  mode: MemberDeliveryMode;
  /**
   * The verified `sub` of the user who triggered the run (R9.1 attribution), or
   * `null` when the record carries none (e.g. a scheduler-triggered run).
   */
  triggeredBy: string | null;
  /** How many recipients the run targeted (the fan-out size). */
  recipientCount: number;
  /** The run's lifecycle status (`queued` → `sending` → `completed`, R9.1). */
  status: MailRunStatus;
  /** How many messages SES ACCEPTED — NOT "delivered to the inbox" (R9.4). */
  sent: number;
  /** How many recipients failed (send-time reject, no address, or late bounce/complaint). */
  failed: number;
  /** ISO-8601 timestamp the run was created (enqueued). */
  createdAt: string;
  /** ISO-8601 timestamp of the run's last update (last worker increment). */
  updatedAt: string;
}

/**
 * One per-recipient FAILURE in a run's drill-down (mail-spec R9.2/R9.5), the
 * camelCase mirror of a SAM `mailrecipient#` sub-record (plumbing keys stripped).
 * Only FAILURES are stored/returned — a successful recipient is counted in the
 * run tally, never listed here (design "failure-only sub-records"). Metadata
 * only: the mailed address + the failure reason, never member PII beyond that.
 */
export interface MailRunFailure {
  /** The recipient address that failed. */
  address: string;
  /** The failure kind (`failed` at send, or a late `bounced` / `complaint`, R8.4). */
  status: MailFailureStatus;
  /** The captured failure reason (SES error code/message, etc.), or `null` when none. */
  reason: string | null;
  /** The SES MessageId when one was assigned before the failure, else `null`. */
  messageId: string | null;
}

/**
 * One run's TALLY plus its FAILURE drill-down, as returned by
 * `GET /members/mail-runs/{runId}` (mail-spec R9.2) — the camelCase mirror of the
 * SAM single-run read `{ run: {...tally}, failures: [...] }`. The status screen
 * expands a run from the list into this detailed view: the same summary fields
 * plus the per-recipient failure list (empty when the run had no failures).
 */
export interface MailRunDetail {
  /** The run's aggregated tally (the same shape the list row carries). */
  run: MailRunSummary;
  /** The run's FAILURE sub-records (empty when every recipient succeeded). */
  failures: MailRunFailure[];
}

/**
 * A full member analytics-set as returned by `GET /members/analytics-sets/{id}`
 * (and by create/update). Carries the resolved `PivotConfig` definition (the
 * service converts the backend snake_case `definition` to the camelCase
 * `PivotConfig` via `fromBackendConfig`).
 */
export interface MemberAnalyticsSet {
  /** The backend `set_id` (string, server-chosen opaque id). */
  id: string;
  /** The user-authored set name. */
  name: string;
  /** `'count'` (aggregate) or `'list'` (filtered list). */
  kind: 'count' | 'list';
  /** The pivot/list definition (camelCase `PivotConfig`). */
  definition: PivotConfig;
  /**
   * The OPTIONAL stored delivery block (R3), or `undefined` on a set with no
   * delivery (the default; a legacy set loads without it).
   */
  delivery?: MemberDelivery;
  /** ISO-8601 UTC create timestamp. */
  created_at: string;
  /** ISO-8601 UTC last-update timestamp. */
  updated_at: string;
}

/**
 * The friendly cadence choices the schedule editor offers (R5, design §5). A
 * cadence maps to a concrete backend cron/rate expression via
 * `cadenceToCron`/`cronToCadence` in `membersApiService` — the UI never shows a
 * raw cron. `monthly` runs on the 1st of each month; `weekly` runs every Monday.
 */
export type MemberScheduleCadence = 'monthly' | 'weekly';

/**
 * A schedule attached to a saved set that HAS a delivery block (R5, design §2.3
 * / §3), the camelCase frontend mirror of the SAM `schedule#<schedule_id>`
 * record. A schedule can only be attached to a set with a stored `delivery` (the
 * editor is gated on it); the scheduled run reuses the R4 execute-and-deliver
 * path. Scheduling is gated to a tenant-wide-capable caller (`members:admin` OR
 * `members:write` + the all-regions grant) — the backend is authoritative, the
 * client only avoids offering a dead action.
 */
export interface MemberSchedule {
  /** The backend `schedule_id` (string, server-chosen opaque id). */
  scheduleId: string;
  /** The saved set this schedule runs (the set must have a delivery block). */
  setId: string;
  /** The EventBridge schedule expression (cron/rate) the backend persists. */
  cron: string;
  /** Whether the schedule is active; a disabled schedule does not fire. */
  enabled: boolean;
  /** Cognito `sub` of the creator (echoed by the backend; informational). */
  createdBy: string;
  /** ISO-8601 UTC create timestamp. */
  createdAt: string;
  /** ISO-8601 UTC last-update timestamp. */
  updatedAt: string;
}

/**
 * A user's preferred list of analytics-set references (R11.2 layer 2 — one list
 * per user, keyed by the authenticated Cognito `sub`, NOT a member id: user ≠
 * member, R11.1). `refs` is an ORDERED list of TAGGED references, never copies:
 * `preset:<key>` points at a predefined preset (code, `memberPivotPresets.ts`),
 * `set:<id>` points at a tenant-shared analytics-set (`set_id`). Dangling refs
 * (a set another user deleted) are skipped by the UI, not an error.
 */
export interface MemberPreferredList {
  /** The owning user's Cognito `sub` (echoed by the backend; informational). */
  sub: string;
  /** Ordered tagged references: `preset:<key>` or `set:<id>`. */
  refs: string[];
  /** ISO-8601 UTC last-update timestamp (empty string when never saved). */
  updated_at: string;
}

/**
 * A user's chosen overview columns (R6 — Session Columns). Mirrors
 * {@link MemberPreferredList} 1:1 (`columns` ↔ `refs`): a PRIVATE, per-user,
 * tenant-scoped record keyed server-side by the authenticated Cognito `sub`
 * (user ≠ member, R11.1 — the client never sends a `sub`), storing an ORDERED
 * list of field-config KEYS (references, never copies of field/member data —
 * R6.6). `member_number` is implied/always-first and need not be stored (R7.3).
 * A key that no longer resolves (field removed/hidden) is skipped on read by
 * the UI, not an error. An unset list comes back empty (`columns: []`, R6.4).
 */
export interface MemberColumnPreferences {
  /** The owning user's Cognito `sub` (echoed by the backend; informational). */
  sub: string;
  /** Ordered field-config keys the user chose to show as columns. */
  columns: string[];
  /** ISO-8601 UTC last-update timestamp (empty string when never saved). */
  updated_at: string;
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
 * The analytics roles a tenant may map to a resolvable field key (design C-CONFIG,
 * R9.1). Each role names a semantic the analytics surface needs but whose concrete
 * field key varies per tenant: the cancellation date, the referral source, the two
 * clubblad (newsletter) delivery flags, and a detailed country field. An unmapped
 * role → the sets that depend on it are hidden with a bilingual reason (R9.5), never
 * an error.
 */
export type AnalyticsRole =
  | 'cancellation_date'
  | 'referral_source'
  | 'clubblad_paper'
  | 'clubblad_digital'
  | 'country_detail';

/**
 * The tenant's analytics configuration block, served additively on
 * `GET /members/field-config` as {@link FieldConfig.analytics} (design C-CONFIG, R9.1).
 * Authored in the Members configurator "Analytics" tab, projected one-directionally
 * from the `members.*` param schema. Read-only tenant data on the analytics surface.
 *
 * All three members are optional; an absent block (or absent member) falls back to
 * documented defaults (R9.5):
 *   - `jubilee_rule` absent → `{ multiple_of: 5 }` (jubilees are multiples of 5 years).
 *   - a role unmapped in `field_roles` → sets depending on it are hidden with a reason.
 *   - `address_mapping` absent → PDF address labels are unavailable; CSV export still works.
 */
export interface MemberAnalyticsConfig {
  /**
   * How a jubilee (anniversary) year is decided. Either an explicit set of qualifying
   * years-member values (`years`) or an "every Nth year" rule (`multiple_of`). Default
   * when the whole block is absent: `{ multiple_of: 5 }`.
   */
  jubilee_rule?: { years?: number[]; multiple_of?: number };
  /**
   * Maps each {@link AnalyticsRole} to a resolvable field key (a key present in
   * {@link FieldConfig.fields}). Partial — a tenant maps only the roles it has fields for.
   */
  field_roles?: Partial<Record<AnalyticsRole, string>>;
  /**
   * Which resolvable field keys fill each slot of a printed address label. Each slot is
   * optional; an incomplete mapping degrades the label generator (and is reported) rather
   * than crashing.
   */
  address_mapping?: {
    name?: string;
    street?: string;
    postcode?: string;
    city?: string;
    country?: string;
    region?: string;
  };
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
  /**
   * The tenant's analytics configuration (design C-CONFIG, R9.1), served additively by
   * the module. Absent for tenants that have not authored it — the analytics surface then
   * falls back to documented defaults (see {@link MemberAnalyticsConfig}). Mirrors the
   * backend-served shape (task 6.1).
   */
  analytics?: MemberAnalyticsConfig;
  /**
   * The tenant's mail-enabled gate flag (pivot-output-actions R0/R1, design §6.3). `true`
   * when the tenant is cleared to send mail (the per-tenant "mail-enabled / SES-certified"
   * onboarding gate the tenant-admin module owns, projected one-directionally and read by
   * the Members edge). The pivot result's Mail output action is OFFERED only when this is
   * `true`; otherwise the action is hidden with a degradation reason. FAIL-CLOSED: a
   * missing/absent value means NOT enabled (treated as `false`). Presentation-only — the
   * send path re-checks the gate server-side regardless.
   */
  mail_enabled?: boolean;
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

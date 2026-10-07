/**
 * Member Analytics — predefined pivot/list presets (C4, R4.2 / R4.3).
 *
 * The eight predefined "sets" a Members-enabled tenant gets out of the box
 * (design C4 table). Each preset is a *template* that pairs a reusable
 * {@link PivotConfig} with the availability metadata the surface needs to decide
 * whether to offer it:
 *
 *   - `requiresFields` — fixed/calculated field keys that must be present in the
 *     resolved field config. These keys are stable platform conventions
 *     (`membership_type`, `birth_month`, `years_member`, `joined_date`,
 *     `country`), so the sets backed solely by them are **always** available
 *     (R4.3).
 *   - `requiresRoles` — {@link AnalyticsRole}s that must resolve to a *present*
 *     field key via `fieldConfig.analytics.field_roles` (checked with
 *     {@link resolveRole} from task 6.4). A tenant's own overlay keys are
 *     tenant-authored, so a role-backed preset is **materialized** by
 *     substituting the tenant's resolved key into its config, and is **hidden**
 *     when the role is unmapped or its mapped key no longer resolves (R4.3 /
 *     R9.3).
 *   - `usesJubileeRule` — the Jubilees preset reads
 *     `fieldConfig.analytics.jubilee_rule` (default multiples-of-5) at run time
 *     to select jubilee years (R4.2); it is purely informational metadata here —
 *     the preset itself is calculated-field-backed and therefore always present.
 *
 * `getAvailablePresets(fieldConfig)` is the single pure function the Pivot Views
 * panel calls: it returns, in display order, exactly the presets the tenant can
 * run — fixed/calculated presets always, role-backed presets only when their
 * role resolves (with the resolved key substituted into `groupColumns`). Nothing
 * tenant-specific is hardcoded; the generic preset table carries only roles and
 * platform-fixed keys (R6.1).
 *
 * Labels are carried as i18n key paths (`labelKey`) into the `members` namespace
 * (`members:analytics.pivotViews.presetNames.*`, task 0.3) and resolved by the
 * caller via i18n — no hardcoded English (R6.4).
 *
 * Pure + unit-tested. No React, no I/O. Spec:
 * `.kiro/specs/Members/member-analytics` (design C4; R4.2, R4.3, R9.3, R6.1, R6.5).
 */
import type {
  AggregateMeasure,
  PivotConfig,
} from '../../../types/pivot';
import type {
  AnalyticsRole,
  FieldConfig,
} from '../../../types/members';
import { resolveRole } from './analyticsConfig';

/** The data source tag the client pivot adapter resolves member rows against. */
export const MEMBER_PIVOT_DATA_SOURCE = 'members';

/**
 * Whether a preset produces a group-by **aggregate** (count/sum/…) or a
 * **filtered list** of member records (no group-by, R4.8).
 */
export type MemberPivotPresetKind = 'count' | 'list';

/**
 * A predefined pivot/list set template (design C4).
 *
 * A role-backed preset's `config.groupColumns` references the {@link AnalyticsRole}
 * name(s) in `requiresRoles` as *placeholders*; {@link materializePreset} rewrites
 * them to the tenant's resolved field key. Fixed/calculated presets carry their
 * real keys directly and need no materialization.
 */
export interface MemberPivotPreset {
  /** Stable preset identifier (also the saved-set seed key). */
  key: string;
  /**
   * i18n key path for the bilingual display label, under the `members` namespace
   * (`analytics.pivotViews.presetNames.*`, task 0.3). Resolved by the caller — no
   * hardcoded English here (R6.4).
   */
  labelKey: string;
  /** The reusable pivot/list configuration (materialized for role-backed presets). */
  config: PivotConfig;
  /** Aggregate vs. filtered-list output (R4.8). */
  kind: MemberPivotPresetKind;
  /** Fixed/calculated field keys that must be present (R4.3). */
  requiresFields?: string[];
  /** Analytics roles that must resolve via `analytics.field_roles` (R4.3 / R9.3). */
  requiresRoles?: AnalyticsRole[];
  /** The Jubilees preset reads `analytics.jubilee_rule` at run time (R4.2). */
  usesJubileeRule?: boolean;
  /**
   * The New-members preset offers a "joined in or after <year>" selector
   * (findings F-010): the chosen year is written into the set's definition
   * filters and narrows the list to members who joined that year or later.
   * Purely informational metadata — the preset is calculated/fixed-field-backed
   * and always available.
   */
  usesJoinedAfterFilter?: boolean;
}

/** The identity columns every list preset leads with (findings F-009). */
const LIST_IDENTITY_COLUMNS = ['name', 'email'] as const;

/** The `members`-namespace i18n key prefix for preset labels (task 0.3). */
const LABEL_PREFIX = 'analytics.pivotViews.presetNames';

/** A COUNT(*) measure — the group-by aggregate every "count" preset uses. */
const COUNT_ALL: AggregateMeasure = { function: 'COUNT', column: '*' };

/** Build a `PivotConfig` for the member data source with sensible defaults. */
function memberConfig(
  partial: Pick<PivotConfig, 'groupColumns' | 'aggregateMeasures'> &
    Partial<
      Pick<
        PivotConfig,
        'filters' | 'columnPivot' | 'columnNestLevels' | 'displayMode' | 'listColumns'
      >
    >,
): PivotConfig {
  return {
    dataSource: MEMBER_PIVOT_DATA_SOURCE,
    groupColumns: partial.groupColumns,
    aggregateMeasures: partial.aggregateMeasures,
    filters: partial.filters ?? {},
    columnPivot: partial.columnPivot ?? null,
    columnNestLevels: partial.columnNestLevels ?? [],
    displayMode: partial.displayMode ?? 'flat',
    ...(partial.listColumns ? { listColumns: partial.listColumns } : {}),
  };
}

/**
 * Address field keys appended to a list preset's columns (findings F-009). These
 * are the conventional fixed/overlay address keys; the adapter reads each via the
 * nested-or-flat `valueFor` accessor, so a key the tenant does not expose simply
 * renders blank (never `[object Object]`, never a crash). Address *line mapping*
 * for PDF labels remains tenant-authored (R4.10); here they are just extra
 * list columns so birthday/jubilee/new-member lists carry a mailing address.
 */
const ADDRESS_COLUMNS = ['street', 'postal_code', 'city', 'country'] as const;

/**
 * The eight predefined presets (design C4 table), in display order.
 *
 * Role-backed presets use the role name as a `groupColumns` placeholder — it is
 * rewritten to the tenant's resolved field key by {@link materializePreset}. A
 * **filtered-list** preset (`kind: 'list'`) carries `groupColumns: []` so the
 * client adapter emits one row per member (R4.8); it still names the field(s) it
 * needs via `requiresFields` / `requiresRoles` for availability + the field
 * picker seed. The clubblad-paper preset filters to paper recipients (its role
 * key = the configured truthy value) and groups by `country` (R4.2).
 */
const PRESETS: readonly MemberPivotPreset[] = [
  // Fixed — always available: number of members per membership type.
  {
    key: 'membership-types',
    labelKey: `${LABEL_PREFIX}.membershipTypes`,
    kind: 'count',
    requiresFields: ['membership_type'],
    config: memberConfig({
      groupColumns: ['membership_type'],
      aggregateMeasures: [COUNT_ALL],
    }),
  },
  // Calculated — always available: list of members by birth month.
  {
    key: 'birthday-birth-month',
    labelKey: `${LABEL_PREFIX}.birthdayBirthMonth`,
    kind: 'list',
    requiresFields: ['birth_month'],
    config: memberConfig({
      groupColumns: [],
      aggregateMeasures: [],
      // Curated columns (F-009): identity + the birthday fields + mailing address.
      listColumns: [
        ...LIST_IDENTITY_COLUMNS,
        'birthday',
        'birth_month',
        'region',
        ...ADDRESS_COLUMNS,
      ],
    }),
  },
  // Calculated + jubilee rule — always available: jubilee members by years-member.
  {
    key: 'jubilees',
    labelKey: `${LABEL_PREFIX}.jubilees`,
    kind: 'list',
    requiresFields: ['years_member'],
    usesJubileeRule: true,
    config: memberConfig({
      groupColumns: [],
      aggregateMeasures: [],
      // Curated columns (F-009): identity + jubilee-relevant fields + address.
      listColumns: [
        ...LIST_IDENTITY_COLUMNS,
        'years_member',
        'joined_date',
        'age',
        'region',
        ...ADDRESS_COLUMNS,
      ],
    }),
  },
  // Fixed — always available: new members by join date. Offers a "joined in or
  // after <year>" selector (findings F-010).
  {
    key: 'new-members',
    labelKey: `${LABEL_PREFIX}.newMembers`,
    kind: 'list',
    requiresFields: ['joined_date'],
    usesJoinedAfterFilter: true,
    config: memberConfig({
      groupColumns: [],
      aggregateMeasures: [],
      // Curated columns (F-009): identity + join + type + address.
      listColumns: [
        ...LIST_IDENTITY_COLUMNS,
        'joined_date',
        'membership_type',
        'region',
        ...ADDRESS_COLUMNS,
      ],
    }),
  },
  // Role-backed — hidden unless `cancellation_date` resolves.
  {
    key: 'cancellations',
    labelKey: `${LABEL_PREFIX}.cancellations`,
    kind: 'list',
    requiresRoles: ['cancellation_date'],
    config: memberConfig({
      // Placeholder role name — rewritten to the resolved key by materialization.
      groupColumns: [],
      aggregateMeasures: [],
      // Curated columns (F-009). The `cancellation_date` ROLE placeholder is
      // rewritten to the tenant's resolved key by materializePreset (below), the
      // same way groupColumns placeholders are, so the list shows the real field.
      listColumns: [
        ...LIST_IDENTITY_COLUMNS,
        'cancellation_date',
        'joined_date',
        'region',
      ],
    }),
  },
  // Role-backed — hidden unless `clubblad_paper` resolves. Grouped by fixed `country`.
  {
    key: 'clubblad-paper-country',
    labelKey: `${LABEL_PREFIX}.clubbladPaperCountry`,
    kind: 'count',
    requiresFields: ['country'],
    requiresRoles: ['clubblad_paper'],
    config: memberConfig({
      groupColumns: ['country'],
      aggregateMeasures: [COUNT_ALL],
    }),
  },
  // Role-backed — hidden unless `clubblad_digital` resolves.
  {
    key: 'clubblad-digital',
    labelKey: `${LABEL_PREFIX}.clubbladDigital`,
    kind: 'list',
    requiresRoles: ['clubblad_digital'],
    config: memberConfig({
      groupColumns: [],
      aggregateMeasures: [],
      // Curated columns (F-009): identity + the digital-clubblad role field +
      // address. The `clubblad_digital` ROLE placeholder is rewritten to the
      // tenant's resolved key by materializePreset.
      listColumns: [
        ...LIST_IDENTITY_COLUMNS,
        'clubblad_digital',
        'region',
        ...ADDRESS_COLUMNS,
      ],
    }),
  },
  // Role-backed — hidden unless `referral_source` resolves. Count per source.
  {
    key: 'referral-source',
    labelKey: `${LABEL_PREFIX}.referralSource`,
    kind: 'count',
    requiresRoles: ['referral_source'],
    config: memberConfig({
      // Placeholder role name — rewritten to the resolved key by materialization.
      groupColumns: ['referral_source'],
      aggregateMeasures: [COUNT_ALL],
    }),
  },
];

/** All preset templates in display order (role placeholders not yet substituted). */
export function getAllPresets(): readonly MemberPivotPreset[] {
  return PRESETS;
}

/**
 * Materialize a preset's config for a tenant by substituting each required role's
 * placeholder in `groupColumns` with the tenant's resolved field key, or return
 * `undefined` when any required role is unmapped/unresolvable (R4.3 / R9.3).
 *
 * A preset with no `requiresRoles` is returned unchanged (its config already
 * carries real fixed/calculated keys). For a role-backed preset, every role in
 * `requiresRoles` must resolve via {@link resolveRole}; if any does not, the
 * preset is unavailable and `undefined` is returned so the caller hides it with a
 * reason. Any `groupColumns` entry that equals a required role name is rewritten
 * to that role's resolved key; other entries (e.g. the fixed `country` in the
 * clubblad-paper preset) are left intact.
 */
export function materializePreset(
  preset: MemberPivotPreset,
  fieldConfig: FieldConfig | undefined,
): MemberPivotPreset | undefined {
  // Fixed/calculated presets with no required fields missing: always available.
  if (!presetFieldsPresent(preset, fieldConfig)) {
    return undefined;
  }

  const roles = preset.requiresRoles ?? [];
  if (roles.length === 0) {
    return preset;
  }

  // Resolve every required role to a present field key; any failure hides the set.
  const roleToKey = new Map<AnalyticsRole, string>();
  for (const role of roles) {
    const key = resolveRole(fieldConfig, role);
    if (!key) {
      return undefined;
    }
    roleToKey.set(role, key);
  }

  // Substitute role-name placeholders with the resolved keys, in BOTH the
  // groupColumns (aggregate presets) and the listColumns (filtered-list presets,
  // e.g. cancellations' `cancellation_date` / clubblad-digital's
  // `clubblad_digital`), so the materialized set names the tenant's real field.
  const substitute = (col: string): string => {
    const asRole = col as AnalyticsRole;
    return roleToKey.has(asRole) ? (roleToKey.get(asRole) as string) : col;
  };
  const groupColumns = preset.config.groupColumns.map(substitute);
  const listColumns = preset.config.listColumns
    ? preset.config.listColumns.map(substitute)
    : preset.config.listColumns;

  return {
    ...preset,
    config: {
      ...preset.config,
      groupColumns,
      ...(listColumns ? { listColumns } : {}),
    },
  };
}

/** Are all of a preset's `requiresFields` present in the resolved field config? */
function presetFieldsPresent(
  preset: MemberPivotPreset,
  fieldConfig: FieldConfig | undefined,
): boolean {
  const required = preset.requiresFields ?? [];
  if (required.length === 0) {
    return true;
  }
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) {
    return false;
  }
  const present = new Set(
    fields
      .map((field) => field?.key)
      .filter((key): key is string => typeof key === 'string' && key !== ''),
  );
  return required.every((key) => present.has(key));
}

/**
 * The available presets for a tenant, in display order (R4.3).
 *
 * Fixed/calculated presets (membership types, birthday/birth-month, jubilees, new
 * members) are always present. Role-backed presets (cancellations, clubblad
 * paper/digital, referral source) are included only when every required role
 * resolves to a present field key, with the tenant's resolved key substituted
 * into the materialized config; otherwise they are omitted (hidden with a reason
 * by the caller). A preset whose `requiresFields` are absent is likewise omitted.
 *
 * Pure: given the same `fieldConfig` it always returns the same list.
 */
export function getAvailablePresets(
  fieldConfig: FieldConfig | undefined,
): MemberPivotPreset[] {
  const available: MemberPivotPreset[] = [];
  for (const preset of PRESETS) {
    const materialized = materializePreset(preset, fieldConfig);
    if (materialized) {
      available.push(materialized);
    }
  }
  return available;
}

/**
 * One preset entry with its availability for the tenant (findings F-014 / R4.3).
 *
 * `available === true` → `preset` is the MATERIALIZED, runnable preset (role
 * placeholders substituted). `available === false` → the preset is NOT runnable
 * for this tenant; `preset` is the raw template (for its label), and
 * `unresolvedRoles` names the analytics roles whose `field_roles` mapping is
 * missing/unresolvable, so the UI can show it DISABLED with a clear reason
 * ("needs <role(s)> mapped in Members config → Analytics") rather than omitting
 * it silently. Only role-backed presets can be unavailable here — a fixed/
 * calculated preset whose `requiresFields` are genuinely absent is still omitted
 * entirely (it is not a config-the-tenant-can-add situation, so there is no
 * actionable reason to surface).
 */
export interface PresetAvailability {
  /** The preset — materialized when available, the raw template when not. */
  preset: MemberPivotPreset;
  /** Whether the preset is runnable for this tenant. */
  available: boolean;
  /** For an unavailable role-backed preset: the roles that did not resolve. */
  unresolvedRoles?: AnalyticsRole[];
}

/**
 * All presets a tenant should SEE, in display order, each tagged with its
 * availability (findings F-014 / R4.3 — "offered … hidden/**disabled with a
 * clear reason**").
 *
 * - Fixed/calculated presets whose `requiresFields` resolve → available (the
 *   four always-on sets).
 * - Role-backed presets whose every role resolves → available (materialized).
 * - Role-backed presets with one or more UNRESOLVED roles → included but
 *   `available: false`, carrying `unresolvedRoles` so the dropdown can render a
 *   DISABLED entry explaining the Members config → Analytics mapping needed.
 * - A fixed/calculated preset whose `requiresFields` are absent is OMITTED (not
 *   an actionable "map a role" situation) — matching `getAvailablePresets`.
 *
 * Pure: a given `fieldConfig` always yields the same list.
 */
export function getPresetsWithAvailability(
  fieldConfig: FieldConfig | undefined,
): PresetAvailability[] {
  const result: PresetAvailability[] = [];
  for (const preset of PRESETS) {
    const materialized = materializePreset(preset, fieldConfig);
    if (materialized) {
      result.push({ preset: materialized, available: true });
      continue;
    }

    // Unavailable. Only surface a role-backed preset as a disabled entry (with a
    // reason the tenant can act on); a preset missing required FIXED fields has
    // no actionable config to add, so it stays omitted.
    const roles = preset.requiresRoles ?? [];
    const fieldsPresent = presetFieldsPresent(preset, fieldConfig);
    if (roles.length > 0 && fieldsPresent) {
      const unresolvedRoles = roles.filter((role) => !resolveRole(fieldConfig, role));
      result.push({ preset, available: false, unresolvedRoles });
    }
  }
  return result;
}

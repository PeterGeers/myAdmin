/**
 * Member Analytics components.
 *
 * Barrel for the Member Analytics surface (a separate page beside the member
 * table) — Overview summary, violin distributions, and pivot/list views with
 * CSV / template-label / SES-mail exports. Spec:
 * `.kiro/specs/Members/member-analytics`.
 */

// C1 — the analytics view-switch panel (task 3.3).
export { default as MemberAnalyticsPanel } from './MemberAnalyticsPanel';
export type { MemberAnalyticsPanelProps, AnalyticsAreaKey } from './MemberAnalyticsPanel';
export type { MemberAnalyticsCapabilities, MemberAnalyticsAreaProps } from './areas/types';

// C1 — the shared non-happy-state notice (empty / degradation), task 3.4 (R1.4).
export { default as AnalyticsStateNotice } from './areas/AnalyticsStateNotice';
export type { AnalyticsNoticeKind, AnalyticsStateNoticeProps } from './areas/AnalyticsStateNotice';

// C2 — the Overview summary stats (task 4.1).
export { default as MemberOverviewStats } from './MemberOverviewStats';

// C2 — pure numeric-aggregation helpers (task 1.1).
export { toNumber, mean, countExcluded } from './memberAggregations';

// C3 — the violin distributions for age / years_member (tasks 5.1 + 5.2).
export {
    default as MemberDistributions,
    MIN_DISTRIBUTION_POINTS,
    UNGROUPED_SELECT_VALUE,
    discoverGroupByDimensions,
    buildMetricData,
} from './MemberDistributions';
export type { GroupByDimension } from './MemberDistributions';

// Generic analytics-config consumption helpers: email-field + definition-filter
// resolution. The role / jubilee / address-mapping helpers were removed.
export {
    resolveEmailField,
    applyDefinitionFilters,
    CONVENTIONAL_EMAIL_KEYS,
} from './analyticsConfig';

// C4 — client-side pivot/list adapter (task 7.1).
export { executeMemberPivot, aggregateColumnName } from './memberPivotAdapter';

// C4 — field picker modal: compose + save a member PivotConfig (task 7.4). The
// member data-source tag + the Save-as seed shape live here (the removed preset
// subsystem used to own the constant).
export { default as MemberFieldPicker, MEMBER_PIVOT_DATA_SOURCE } from './MemberFieldPicker';
export type { MemberFieldPickerProps, PivotSeed } from './MemberFieldPicker';

// C4 — the pivot/list views sub-panel + full save lifecycle (tasks 7.3 + 7.5).
export { default as MemberPivotViews } from './MemberPivotViews';

// C6 — the SES mail compose modal for a member set (task 9.2).
export { default as MemberMailCompose } from './MemberMailCompose';
export type { MemberMailComposeProps } from './MemberMailCompose';
export { resolveTemplateSeed } from './MemberMailCompose';
export type { TemplateSeed } from './MemberMailCompose';

// R9 (pivot-output-actions/mail, task 3.3) — the mail SEND-STATUS / HISTORY
// screen: a role-scoped list of send-runs + per-run FAILURE drill-down, with
// honest "sent = SES accepted, not delivered" labelling (R9.4).
export { default as MemberMailStatus } from './MemberMailStatus';
export type { MemberMailStatusProps } from './MemberMailStatus';

// R2 + R-L1 (pivot-output-actions + /labels) — the SINGLE stored-template
// management surface for BOTH kinds: mail (CRUD + upload + improve-with-AI) and
// label (ordered lines of result-field keys). "A template is a template."
export { default as MemberTemplateManager } from './MemberTemplateManager';
export type { MemberTemplateManagerProps, ResultField } from './MemberTemplateManager';

// R3 (pivot-output-actions, task 3.4) — the stored-delivery editor on a saved
// set (mode, template, attachment, to_fixed recipients, shared label_options).
export { default as MemberDeliveryEditor, hasValidFixedRecipients } from './MemberDeliveryEditor';
export type { MemberDeliveryEditorProps } from './MemberDeliveryEditor';

// R5 (pivot-output-actions, task 5.4) — attach/manage a recurring schedule on a
// saved set that HAS a delivery block (cadence picker, enable/disable, POST/PUT/
// DELETE the schedule route).
export { default as MemberScheduleEditor } from './MemberScheduleEditor';
export type { MemberScheduleEditorProps } from './MemberScheduleEditor';

// C8 — the data-volume guard: measure the GET /members payload against the
// 6 MiB Lambda ceiling → warning (≥80%) / exceeded (≥100%) states (task 10.2).
export {
    assessDataVolume,
    classifyDataVolume,
    measurePayloadBytes,
    consoleDataVolumeLogger,
    BYTES_PER_MIB,
    LIMIT_BYTES,
    WARNING_FRACTION,
    WARNING_THRESHOLD_BYTES,
} from './dataVolumeGuard';
export type {
    DataVolumeLevel,
    DataVolumeAssessment,
    DataVolumeLogger,
} from './dataVolumeGuard';

// C4 — an existing saved model the field picker edits in place (task 7.5).
export type { ExistingPivotModel } from './MemberFieldPicker';

// The pure label service: Avery formats, template-driven label composition, and
// jsPDF output. The address-mapping-driven path (`composeAddresses` /
// `generateAddressLabelPdf` / the `AddressLabelGenerator` UI) was removed; only
// the template path survives.
export {
    AVERY_LABEL_FORMATS,
    DEFAULT_LABEL_FORMAT_KEY,
    MIN_FONT_SIZE,
    MAX_FONT_SIZE,
    getLabelFormat,
    clampFontSize,
    cellPosition,
    labelsPerPage,
    pageCount,
} from './addressLabelService';
export type {
    LabelFormat,
    LabelAlignment,
    LabelStyleOptions,
    GenerateResult,
} from './addressLabelService';

// R6 + R3 (pivot-output-actions, task 6.3) — the ONE shared label-options model
// used by both the interactive "Generate address labels" action (R6) and the
// stored `to_fixed` + `pdf_labels` delivery (R3). Built on the service's
// LabelStyleOptions/LabelFormat — not a parallel shape.
export {
    DEFAULT_LABEL_FONT_SIZE,
    DEFAULT_LABEL_ALIGNMENT,
    DEFAULT_LABEL_SORT_ORDER,
    defaultLabelOptions,
    normalizeLabelOptions,
    isValidFormatKey,
    toStyleOptions,
    resolveLabelFormat,
    toStored,
    fromStored,
} from './labelOptions';
export type { LabelOptions, StoredLabelOptions } from './labelOptions';

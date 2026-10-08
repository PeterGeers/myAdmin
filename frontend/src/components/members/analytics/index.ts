/**
 * Member Analytics components.
 *
 * Barrel for the Member Analytics surface (a separate page beside the member
 * table) — Overview summary, violin distributions, and pivot/list views with
 * CSV / PDF-label / SES-mail exports. Spec: `.kiro/specs/Members/member-analytics`
 * (design C1–C8 + C-CONFIG).
 *
 * Scaffolding only (task 0.1). Component exports are added by later phases:
 *   - MemberAnalyticsPanel (C1, task 3.3)
 *   - MemberOverviewStats + memberAggregations (C2, tasks 1.1 / 4.1)
 *   - MemberDistributions (C3, task 5.1)
 *   - MemberPivotViews / MemberFieldPicker / memberPivotAdapter / memberPivotPresets (C4, phase 7)
 *   - AddressLabelGenerator + addressLabelService (C5, phase 8)
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

// C-CONFIG — analytics-config consumption helpers (task 6.4).
export {
    resolveRole,
    resolveEmailField,
    isJubileeYear,
    candidateJubileeYears,
    selectedJubileeYear,
    applyJubileeYearFilter,
    resolveAddressMapping,
    hasAnalyticsConfig,
    DEFAULT_JUBILEE_MULTIPLE,
    MAX_JUBILEE_YEAR,
    JUBILEE_YEAR_FILTER_KEY,
    CONVENTIONAL_EMAIL_KEYS,
} from './analyticsConfig';
export type { AddressSlot, ResolvedAddressMapping } from './analyticsConfig';

// C4 — predefined pivot/list presets (task 7.2).
export {
    getAllPresets,
    getAvailablePresets,
    materializePreset,
    MEMBER_PIVOT_DATA_SOURCE,
} from './memberPivotPresets';
export type { MemberPivotPreset, MemberPivotPresetKind } from './memberPivotPresets';

// C4 — client-side pivot/list adapter (task 7.1).
export { executeMemberPivot, aggregateColumnName } from './memberPivotAdapter';

// C4 — field picker modal: compose + save a member PivotConfig (task 7.4).
export { default as MemberFieldPicker } from './MemberFieldPicker';
export type { MemberFieldPickerProps } from './MemberFieldPicker';

// C4 — the pivot/list views sub-panel + full save lifecycle (tasks 7.3 + 7.5).
export { default as MemberPivotViews } from './MemberPivotViews';

// C6 — the SES mail compose modal for a member set (task 9.2).
export { default as MemberMailCompose } from './MemberMailCompose';
export type { MemberMailComposeProps } from './MemberMailCompose';
export { resolveTemplateSeed } from './MemberMailCompose';
export type { TemplateSeed } from './MemberMailCompose';

// R2 (pivot-output-actions) — the stored mail-template management surface
// (CRUD + upload + improve-with-AI).
export { default as MemberTemplateManager } from './MemberTemplateManager';
export type { MemberTemplateManagerProps } from './MemberTemplateManager';

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

// C5 — the address-label generator UI (task 8.2).
export { default as AddressLabelGenerator } from './AddressLabelGenerator';
export type { AddressLabelGeneratorProps } from './AddressLabelGenerator';

// C5 — the pure address-label service: Avery formats, address composition,
// incomplete-address filtering, and jsPDF output (task 8.2).
export {
    AVERY_LABEL_FORMATS,
    DEFAULT_LABEL_FORMAT_KEY,
    MIN_FONT_SIZE,
    MAX_FONT_SIZE,
    getLabelFormat,
    composeAddresses,
    clampFontSize,
    cellPosition,
    labelsPerPage,
    pageCount,
    generateAddressLabelPdf,
} from './addressLabelService';
export type {
    LabelFormat,
    LabelAlignment,
    LabelSortOrder,
    LabelStyleOptions,
    ComposedAddress,
    ComposeResult,
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

/**
 * MemberPivotViews — the Pivot Views sub-panel of the Member Analytics surface
 * (C4, tasks 7.3 + 7.5).
 *
 * Task 7.5 adds the full save lifecycle for MEMBER sets, all through the Members
 * module's OWN `/members/analytics-sets` DynamoDB CRUD (`membersApiService`,
 * tenant-scoped by the Lambda), NOT the Flask `/api/pivot/models` MySQL store —
 * a SAM module owns its data on its own plane (F-012):
 *   - **New set** — compose + save a brand-new set via the field picker (R4.4);
 *   - **Save as** — save the selected preset/set as a NEW variant, its
 *     definition filters carried into the new set (R4.4);
 *   - **Update** — edit the selected saved set in place via `updateAnalyticsSet`
 *     (its own definition filters round-trip, R4.4);
 *   - **Delete** — explicit, confirmed delete via `deleteAnalyticsSet`.
 * After any save/update/delete the saved-set dropdown is refreshed so the
 * change appears immediately. Every one of these is an EXPLICIT user action
 * (R4.4b); the page's live row/scope filter is never baked into a saved set
 * (R4.4a) — the picker is never handed `processedData`.
 *
 * The Pivot Views area lets a user run a member pivot/list *set* against the
 * page's OWN scope-authorized, filtered dataset (`processedData`, Option A /
 * R1.5 / R5.1) and render the result through the framework's existing
 * `PivotResultTable` (REUSE — no bespoke result table, R4.7). A "set" is one of:
 *
 *   - a **predefined preset** (R4.2) — the fixed/calculated + role-backed sets
 *     from `getAvailablePresets(fieldConfig)` (task 7.2), already materialized
 *     for the tenant (role placeholders substituted, unavailable sets omitted);
 *   - a **saved member set** (R4.6 / R5.2) — a tenant-saved analytics set from
 *     the Members API `listAnalyticsSets()`. The Members Lambda returns ONLY this
 *     tenant's member sets, so no client-side data-source filter is needed
 *     (another module's sets can never leak into the member surface).
 *
 * Both kinds are offered in ONE dropdown (R4.6/R5.2). Selecting a set does NOT
 * run anything — running is an EXPLICIT action (R1.6): the user picks a set, then
 * clicks Execute, and only then is `executeMemberPivot(processedData, config,
 * fieldConfig)` (task 7.1, the client adapter) called and its `PivotResult`
 * rendered. Nothing is pivoted/listed on open, and nothing auto-runs on
 * selection (R1.6 — no auto-run).
 *
 * Resolving the chosen set's `PivotConfig`:
 *   - a preset carries its `config` inline (already materialized);
 *   - a saved set carries only summary metadata in the list, so its full
 *     definition is fetched on Execute via `getAnalyticsSet(id)` (which converts
 *     the module's snake_case definition into a camelCase `PivotConfig`). The
 *     saved set's own definition filters travel with it
 *     (R4.4); the page's live filter is NOT baked in (R4.4a) — the adapter runs
 *     over `processedData` as-is.
 *
 * Exports mount into the capability-gated, test-visible `pivot-result-actions`
 * slot (gated by `capabilities.canExport` = members:export). Within the slot the
 * Mail action carries an ADDITIONAL tenant gate (pivot-output-actions R0/R1 task
 * 1.3): the compose/send path is OFFERED only when the tenant is mail-enabled —
 * the R0 `config#mail` flag surfaced on the field config as `mail_enabled`;
 * otherwise the action is HIDDEN with the shared degradation reason (mirroring how
 * the labels action degrades on an absent address mapping). Task 8.1 wires CSV
 * export of the produced `PivotResult` here, REUSING `csvExport.ts` (no bespoke
 * CSV): a result column's `name` is the util's key + header, so the SAME mapping
 * exports an AGGREGATE result (group + aggregate columns) and a filtered-LIST
 * result (one row per member, R4.11). PDF labels / SES mail follow in tasks
 * 8.2 / 9.x into the same slot.
 *
 * No hardcoded English: every label resolves from the `members` namespace
 * (`analytics.pivotViews.*`, `analytics.states.*`, task 0.3), bilingual via the
 * active language. Keyboard-accessible: the dropdown is a native `<select>` and
 * Execute is a native button, each with an associated bilingual label.
 *
 * @module components/members/analytics/MemberPivotViews
 * @see .kiro/specs/Members/member-analytics (design C4; requirements R4.1, R4.6, R4.7, R5.2, R1.6)
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Box,
  Button,
  Checkbox,
  FormControl,
  FormLabel,
  HStack,
  IconButton,
  Input,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalHeader,
  ModalOverlay,
  Select,
  Text,
  Tooltip,
  VStack,
  useToast,
} from '@chakra-ui/react';
import { AddIcon, DeleteIcon, MinusIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import type { PivotConfig, PivotResult } from '../../../types/pivot';
import type {
  MemberRow,
  MemberAnalyticsSetSummary,
  MemberDelivery,
  MemberSchedule,
  MemberScheduleCadence,
} from '../../../types/members';
import PivotResultTable from '../../pivot/PivotResultTable';
import {
  listAnalyticsSets,
  getAnalyticsSet,
  deleteAnalyticsSet,
  getPreferredList,
  savePreferredList,
  putAnalyticsSetDelivery,
  deleteAnalyticsSetDelivery,
  listSchedulesForSet,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  sendAdHocMail,
  type AdHocMailBody,
} from '../../../services/membersApiService';
import { applyApiError } from '../../../shared/api/applyApiError';
import type { MemberAnalyticsAreaProps } from './areas/types';
import { getAvailablePresets } from './memberPivotPresets';
import type { MemberPivotPreset } from './memberPivotPresets';
import { executeMemberPivot } from './memberPivotAdapter';
import { generateCsvFromObjects, downloadCsv } from '../../../utils/csvExport';
import { recordAnalyticsOutput } from '../../../services/memberAnalyticsAuditService';
import MemberFieldPicker, { type ExistingPivotModel } from './MemberFieldPicker';
import MemberMailCompose from './MemberMailCompose';
import MemberMailStatus from './MemberMailStatus';
import MemberDeliveryEditor from './MemberDeliveryEditor';
import MemberScheduleEditor from './MemberScheduleEditor';
import {
  AVERY_LABEL_FORMATS,
  DEFAULT_LABEL_FORMAT_KEY,
  getLabelFormat,
  generateAddressLabelPdf,
} from './addressLabelService';
import { resolveAddressMapping } from './analyticsConfig';
import MemberLabelsPanel from './MemberLabelsPanel';
import {
  listMemberTemplates as realListMemberTemplates,
  type MemberTemplateDto,
} from '../../../services/memberTemplateService';
import AnalyticsStateNotice from './areas/AnalyticsStateNotice';
import {
  candidateJubileeYears,
  selectedJubileeYear,
  applyJubileeYearFilter,
  JUBILEE_YEAR_FILTER_KEY,
  candidateJoinedYears,
  selectedJoinedAfterYear,
  applyJoinedAfterFilter,
  JOINED_AFTER_FILTER_KEY,
  applyDefinitionFilters,
} from './analyticsConfig';
import type { FieldConfigField, LocalizedLabel } from '../../../types/members';
import type { AggregateFunction } from '../../../types/pivot';

/**
 * A selectable set in the dropdown — a materialized preset or a saved member
 * model — flattened to the small shape the dropdown + Execute need.
 */
interface SelectableSet {
  /** Stable, collision-free option value (`preset:<key>` / `model:<id>`). */
  optionValue: string;
  /** Already-resolved display label (bilingual, resolved from i18n / the model name). */
  label: string;
  /** Which group the option belongs to (for the two `<optgroup>`s). */
  source: 'preset' | 'model';
  /** A preset's inline, materialized config (presets only). */
  config?: PivotConfig;
  /** A saved set's id (the backend `set_id` string), loaded on Execute (models only). */
  modelId?: string;
  /**
   * The preset reads `analytics.jubilee_rule` at run time (the Jubilees preset,
   * task 7.2 `usesJubileeRule`). Only such a set shows the jubilee year selector
   * (task 7.6). Saved models never set this.
   */
  usesJubileeRule?: boolean;
  /**
   * The New-members preset offers a "joined in or after <year>" selector
   * (findings F-010). Only such a set shows the join-year selector. Saved models
   * never set this.
   */
  usesJoinedAfterFilter?: boolean;
}

const PRESET_PREFIX = 'preset:';
const MODEL_PREFIX = 'model:';

// The preferred list (R11.2) stores TAGGED references, not copies: a preset is
// `preset:<key>` and a saved tenant-shared set is `set:<id>`. The dropdown's
// internal option scheme uses `model:<id>` for a saved set; these two helpers
// bridge the two so the preferred list speaks the backend's `set:` vocabulary.
const SET_PREFIX = 'set:';

/**
 * Convert a dropdown option value (`preset:<key>` / `model:<id>`) into the
 * backend preferred-list tagged reference (`preset:<key>` / `set:<id>`). Returns
 * null when the option value is not a recognizable set reference.
 */
function optionValueToRef(optionValue: string): string | null {
  if (optionValue.startsWith(PRESET_PREFIX)) {
    return optionValue; // presets share the same `preset:<key>` form
  }
  if (optionValue.startsWith(MODEL_PREFIX)) {
    return `${SET_PREFIX}${optionValue.slice(MODEL_PREFIX.length)}`;
  }
  return null;
}

/**
 * Resolve a localized (`{nl,en}`) or plain-string label to the active language,
 * mirroring the field picker's `resolveLabel` (prefer active language, then
 * `nl`, then `en`, then the fallback). Kept local so the result-header label map
 * is built from the SAME field config the picker lists (no hardcoded English,
 * findings: "result column headers stay English").
 */
function resolveLabel(
  label: string | LocalizedLabel | undefined,
  lang: string,
  fallback: string,
): string {
  if (!label) return fallback;
  if (typeof label === 'string') return label;
  return label[lang] || label.nl || label.en || fallback;
}

/**
 * Parse an aggregate result-column name of the SQL-style form `FUNC(column)`
 * (e.g. `COUNT(*)`, `SUM(age)`) into its function + inner column, or `null` when
 * the name is not an aggregate expression (a plain group/list column key). Used
 * to build a localized aggregate header ("Aantal (Leeftijd)" / "Count (Age)")
 * from the field config + an i18n function label.
 */
function parseAggregateName(
  name: string,
): { fn: AggregateFunction; inner: string } | null {
  const match = /^([A-Z]+)\((.*)\)$/.exec(name);
  if (!match) {
    return null;
  }
  const fn = match[1] as AggregateFunction;
  return { fn, inner: match[2] };
}



/**
 * Resolve the `PivotConfig` for the chosen set. A preset carries its config
 * inline (already materialized by `getAvailablePresets`); a saved set's full
 * definition is fetched via the Members API `getAnalyticsSet` (which converts the
 * module's snake_case `definition` into a camelCase `PivotConfig`), so the saved
 * set's own definition filters travel with it (R4.4), never the page's live
 * filter (R4.4a).
 */
async function resolveConfig(set: SelectableSet): Promise<PivotConfig | undefined> {
  if (set.source === 'preset') {
    return set.config;
  }
  if (typeof set.modelId === 'string') {
    const saved = await getAnalyticsSet(set.modelId);
    return saved.definition;
  }
  return undefined;
}

/**
 * The optional injectable template loader (labels sub-spec R-L2, task 3.1). The
 * labels action gate needs to know whether the tenant has ≥1 `kind:"label"`
 * template; it loads them via `listMemberTemplates`. The prop defaults to the
 * real service and exists only so a test can inject a fake (no network).
 */
interface MemberPivotViewsProps extends MemberAnalyticsAreaProps {
  /** Injectable template-list loader; defaults to the real `listMemberTemplates`. */
  listTemplates?: typeof realListMemberTemplates;
}

const MemberPivotViews: React.FC<MemberPivotViewsProps> = ({
  processedData,
  fieldConfig,
  language,
  capabilities,
  listTemplates = realListMemberTemplates,
}) => {
  const { t } = useTypedTranslation('members');
  const toast = useToast();

  // The materialized, available presets for this tenant (R4.2/R4.3). Pure +
  // memoized on the field config — role-backed presets are already substituted
  // or omitted; nothing tenant-specific is hardcoded.
  const presets: MemberPivotPreset[] = useMemo(
    () => getAvailablePresets(fieldConfig ?? undefined),
    [fieldConfig],
  );

  // Saved member sets (R4.6/R5.2) — fetched from the Members API, which returns
  // ONLY this tenant's member sets (member-owned DynamoDB store, F-012). No
  // client-side data-source filter is needed: the Members Lambda never returns
  // another module's sets.
  const [savedModels, setSavedModels] = useState<MemberAnalyticsSetSummary[]>([]);

  // The tenant's LABEL templates (`kind:"label"`), loaded once on mount (labels
  // sub-spec R-L2, task 3.1). Their mere EXISTENCE (≥1) gates the "Generate
  // address labels" action — see `hasLabelTemplate` / `canGenerateLabels` below.
  // FAIL-CLOSED: a non-ok result or a throw leaves this empty, so the action is
  // simply hidden with the bilingual degradation reason — never a crash.
  const [labelTemplates, setLabelTemplates] = useState<MemberTemplateDto[]>([]);

  // The currently SELECTED option value — selection alone runs nothing (R1.6).
  const [selectedValue, setSelectedValue] = useState<string>('');

  // The chosen jubilee year (empty = all jubilee-eligible members). Shown only
  // for the Jubilees preset (task 7.6). Stored as a string (native <select>
  // value) and parsed to a number when written into the config filter.
  const [jubileeYear, setJubileeYear] = useState<string>('');

  // The chosen "joined in or after" year (empty = all members). Shown only for
  // the New-members preset (findings F-010). Stored as a string (native <select>
  // value), parsed to a number when written into the config filter.
  const [joinedAfterYear, setJoinedAfterYear] = useState<string>('');

  // The produced result (null until the user explicitly Executes). Also tracks
  // the config that produced it so the result table formats correctly.
  const [result, setResult] = useState<PivotResult | null>(null);
  const [resultConfig, setResultConfig] = useState<PivotConfig | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);

  // The rows currently VISIBLE in the result table — i.e. after the user's
  // in-table column filters/sort (reported by PivotResultTable via
  // onVisibleRowsChange). Every export (CSV / PDF labels / mail) operates on
  // THESE rows, so a filtered-down table exports exactly the subset the user
  // sees (findings: "table filters do not limit the export"). Defaults to the
  // full result until the table reports its filtered set.
  const [visibleRows, setVisibleRows] = useState<Record<string, unknown>[]>([]);

  // --- Save lifecycle state (task 7.5). --------------------------------------
  // The field picker's open state + its edit target. `pickerModel` undefined =>
  // the picker composes a NEW set (New set / Save-as); a value => it EDITS that
  // saved model in place (Update). `pickerSeed` seeds a New/Save-as compose from
  // the currently-selected set's config (R4.6). All opening is an explicit user
  // click (R4.4b).
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const [pickerModel, setPickerModel] = useState<ExistingPivotModel | undefined>(undefined);
  const [pickerSeed, setPickerSeed] = useState<MemberPivotPreset | undefined>(undefined);

  // Delete confirmation (explicit, never implicit — R4.4b). Holds the summary of
  // the set pending deletion, or null when no confirmation is open.
  const [pendingDelete, setPendingDelete] = useState<MemberAnalyticsSetSummary | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const cancelDeleteRef = useRef<HTMLButtonElement>(null);

  // --- Mail compose state (task 9.2). ----------------------------------------
  // The SES mail compose modal is opened from the Mail button in the
  // capability-gated `pivot-result-actions` slot (beside the CSV button). It
  // mails the CURRENT result rows; a tenant whose `address_mapping` resolves can
  // additionally attach PDF labels.
  const [isMailOpen, setIsMailOpen] = useState(false);

  // --- Delivery editor state (task 3.4 / R3). --------------------------------
  // The "Delivery" lifecycle action (beside Update, on a selected SAVED set)
  // opens MemberDeliveryEditor to edit the set's optional stored `delivery` block
  // (mode / template / attachment / to_fixed recipients / shared label_options).
  // The editor is seeded from the set's EXISTING delivery, which is only known
  // once the full set is fetched (the list summary carries no delivery) — so
  // opening Delivery loads the full set first, then opens the modal with its
  // resolved delivery (undefined for a set with none yet).
  const [isDeliveryOpen, setIsDeliveryOpen] = useState(false);
  const [deliverySet, setDeliverySet] = useState<{
    id: string;
    name: string;
    delivery?: MemberDelivery;
  } | null>(null);

  // --- "Deliver now" state (mail-spec task 2.4 / R3.1/R3.2). -----------------
  // The "Deliver now" lifecycle action (beside Delivery) RUNS a saved set's
  // STORED `to_fixed` delivery immediately — the interactive trigger for the
  // existing SAM deliver route (`POST /members/analytics-sets/{id}/deliver`),
  // the gap R3.2 closes (the route existed but had no frontend caller). The run
  // enqueues (a worker sends); the UI surfaces the accepted/queued receipt
  // (R3.5) and any refusal (empty recipients / not-certified) as a clear error
  // (R3.4). `isDeliveringNow` disables the action while the enqueue is in flight
  // so a double-click never fires two runs.
  const [isDeliveringNow, setIsDeliveringNow] = useState(false);
  // Deliver now opens a confirm dialog FIRST (so an irreversible send is never
  // fired blind — the redesign Q3 safety follow-up).
  const [isDeliverNowConfirmOpen, setIsDeliverNowConfirmOpen] = useState(false);
  const deliverNowCancelRef = useRef<HTMLButtonElement>(null);

  // --- Schedule editor state (task 5.4 / R5). --------------------------------
  // The "Schedule" lifecycle action (beside Delivery, on a selected SAVED set)
  // opens MemberScheduleEditor to attach/manage the set's recurring run. A
  // schedule can ONLY be attached to a set that HAS a delivery block (R5), so the
  // action is gated on the set's delivery; it is also gated on the R5 ACCESS rule
  // (members:admin OR members:write + all-regions) reflected client-side as
  // `capabilities.isAdmin` (see `canSchedule` below). The set's existing delivery
  // AND its current schedule are only known once the full set is fetched (the
  // list summary carries neither) — so opening Schedule loads the full set +
  // lists the set's schedules first, then opens the modal seeded with them.
  const [isScheduleOpen, setIsScheduleOpen] = useState(false);
  const [scheduleSet, setScheduleSet] = useState<{
    id: string;
    name: string;
    hasDelivery: boolean;
    schedule?: MemberSchedule;
  } | null>(null);

  // --- Address-label generate state (labels sub-spec task 3.2 / R-L2). -------
  // The "Generate address labels" action in the `pivot-result-actions` slot
  // (beside CSV / Mail) opens a modal hosting the TEMPLATE-DRIVEN
  // `MemberLabelsPanel`, which lets the user pick a stored `kind:"label"`
  // template + an Avery format + the shared per-run options and builds the PDF
  // via `generateLabelTemplatePdf` (compose through `composeLabelLines`, NO
  // `analytics.*` — R6). It operates on the CURRENT result rows (`exportRows` —
  // the table's post-filter visible rows, R2/R3). The availability GATE
  // (`canGenerateLabels` = members:export + ≥1 label template) decides whether
  // the modal is reachable (below).
  const [isLabelsOpen, setIsLabelsOpen] = useState(false);

  // The "All sets" library modal (opened from the button beside the set
  // dropdown). The main pane stays clean — the full library (browse / filter /
  // add-to-preferred / reorder) lives in this modal, not inline.
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);

  // --- Mail status/history state (mail-spec task 3.3 / R9). ------------------
  // The "Mail status" entry point opens the send-status/history screen
  // (MemberMailStatus) in a modal: a role-scoped list of send-runs + per-run
  // FAILURE drill-down (R9.2), with honest "sent = SES accepted, not delivered"
  // labelling (R9.4). The read routes it calls (`GET /members/mail-runs[/{id}]`)
  // are gated `members:export` + role-scoped server-side (a user sees own runs,
  // a Tenant_Admin all), so the entry point rides the same `members:export` gate
  // the result-actions slot uses — it is NOT tied to a produced result (a user
  // checks past sends independently of running a pivot).
  const [isMailStatusOpen, setIsMailStatusOpen] = useState(false);

  // --- Preferred list state (R11.2 layer 2). ---------------------------------
  // One ordered list of TAGGED references per USER (keyed server-side on the
  // authenticated Cognito `sub` — user ≠ member, R11.1; the client never sends a
  // sub). `preset:<key>` references a predefined preset (code), `set:<id>` a
  // tenant-shared saved set. Loaded on mount; a load failure degrades to an empty
  // list (never a crash). Saving is a FULL replace (one list per user).
  const [preferredRefs, setPreferredRefs] = useState<string[]>([]);
  const [isSavingPreferred, setIsSavingPreferred] = useState(false);

  // Name-filter input for the "All sets" library list (find-by-name). Substring,
  // case-insensitive; the alphabetical order is preserved.
  const [libraryFilter, setLibraryFilter] = useState('');

  // Whether the caller may MUTATE the preferred list / create a shared set. The
  // backend gates the preferred-list PUT + set create on members:export OR
  // members:write (R11); mirror that here so a read-only caller sees the list but
  // no add/remove/reorder controls and no create-set actions.
  const canManageSets = capabilities.canExport || capabilities.canWrite === true;
  // Deleting a saved set from the shared library is gated by `isAdmin` — the
  // page computes the privileged delete role rule ((Regio_All AND Members_CRUD)
  // OR Tenant_Admin) and passes it as this flag. NOTE: plain members:write
  // (Members_CRUD) alone does NOT grant delete here (unlike add/edit), so this
  // deliberately does not OR in `canWrite`.
  const canDeleteSets = capabilities.isAdmin === true;
  // Whether the caller may SCHEDULE a set (R5): the backend gates schedule CRUD on
  // `members:admin` OR (`members:write` + the `["*"]` all-regions grant). The page
  // computes exactly that tenant-wide rule — ((Regio_All AND Members_CRUD) OR
  // Tenant_Admin) — and passes it as `capabilities.isAdmin` (the same flag that
  // gates set-delete). A region-NARROWED CRUD user therefore does NOT get the
  // Schedule action, matching R5 (an unattended run must never replay a partial
  // regional slice). The backend remains authoritative; this only avoids offering
  // a dead action.
  const canSchedule = capabilities.isAdmin === true;

  // Refresh the saved member sets from the Members API (the module-owned
  // DynamoDB store, F-012). The Lambda returns ONLY this tenant's member sets, so
  // no client-side data-source filter is needed (R5.2 — tenant-safe by
  // construction). A fetch failure degrades to presets-only (the predefined sets
  // stay usable) — never a crash (design C4 "Error handling": saved-set CRUD
  // failure → presets still usable). Called on mount AND after every
  // save/update/delete so lifecycle changes appear in the dropdown immediately
  // (task 7.5).
  const refreshSavedModels = useCallback(async (): Promise<MemberAnalyticsSetSummary[]> => {
    try {
      const sets = await listAnalyticsSets();
      setSavedModels(sets);
      return sets;
    } catch {
      setSavedModels([]);
      return [];
    }
  }, []);

  useEffect(() => {
    let active = true;
    listAnalyticsSets()
      .then((sets) => {
        if (!active) {
          return;
        }
        setSavedModels(sets);
      })
      .catch(() => {
        if (active) {
          setSavedModels([]);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  // Load the user's preferred list on mount (R11.2). Keyed server-side on the
  // authenticated sub; an unset list returns empty refs. A load failure degrades
  // to an empty list — the preferred panel just shows the empty state, never a
  // crash (design C9 "Error handling": preferred-list read failure → empty).
  useEffect(() => {
    let active = true;
    getPreferredList()
      .then((pref) => {
        if (active) {
          setPreferredRefs(pref.refs);
        }
      })
      .catch(() => {
        if (active) {
          setPreferredRefs([]);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  // Load the tenant's LABEL templates on mount (labels sub-spec R-L2, task 3.1).
  // Only `kind:"label"` templates matter here — a mail template never gates the
  // labels action. FAIL-CLOSED: a non-ok result OR a thrown network error leaves
  // the list empty (action hidden with the bilingual reason), never a crash. The
  // loader is injectable via the `listTemplates` prop so a test can supply a fake.
  const reloadLabelTemplates = useCallback(async () => {
    try {
      const res = await listTemplates();
      setLabelTemplates(res.ok ? res.data.filter((tpl) => tpl.kind === 'label') : []);
    } catch {
      setLabelTemplates([]);
    }
  }, [listTemplates]);

  useEffect(() => {
    let active = true;
    listTemplates()
      .then((res) => {
        if (!active) {
          return;
        }
        setLabelTemplates(
          res.ok ? res.data.filter((tpl) => tpl.kind === 'label') : [],
        );
      })
      .catch(() => {
        if (active) {
          setLabelTemplates([]);
        }
      });
    return () => {
      active = false;
    };
  }, [listTemplates]);

  // The flat list of selectable sets, keyed by a collision-free option value.
  const sets: SelectableSet[] = useMemo(() => {
    const presetSets: SelectableSet[] = presets.map((preset) => ({
      optionValue: `${PRESET_PREFIX}${preset.key}`,
      label: t(preset.labelKey),
      source: 'preset',
      config: preset.config,
      usesJubileeRule: preset.usesJubileeRule,
      usesJoinedAfterFilter: preset.usesJoinedAfterFilter,
    }));
    const modelSets: SelectableSet[] = savedModels.map((model) => ({
      optionValue: `${MODEL_PREFIX}${model.id}`,
      // A saved model's name is user-authored tenant data, shown as-is.
      label: model.name,
      source: 'model',
      modelId: model.id,
    }));
    return [...presetSets, ...modelSets];
  }, [presets, savedModels, t]);

  const selectedSet = useMemo(
    () => sets.find((s) => s.optionValue === selectedValue),
    [sets, selectedValue],
  );

  // The jubilee year selector appears ONLY for the Jubilees preset — the set
  // flagged `usesJubileeRule` in task 7.2 (R4.2). Every other preset and every
  // saved model hides it.
  const showsJubileeSelector = selectedSet?.usesJubileeRule === true;

  // The selectable jubilee years come from the tenant's `analytics.jubilee_rule`
  // — a configured `years` set, a `multiple_of` rule, or the default
  // multiples-of-5 (task 6.4 jubilee logic, reused — not reimplemented). Memoized
  // on the rule so the list is stable across renders.
  const jubileeYearOptions = useMemo(
    () => candidateJubileeYears(fieldConfig?.analytics?.jubilee_rule),
    [fieldConfig],
  );

  // The join-year selector appears ONLY for the New-members preset — the set
  // flagged `usesJoinedAfterFilter` (findings F-010). Every other preset and
  // every saved model hides it.
  const showsJoinedAfterSelector = selectedSet?.usesJoinedAfterFilter === true;

  // The selectable "joined in or after" years: current year back ~15 years,
  // descending (findings F-010). Memoized so the list is stable across renders.
  const joinedYearOptions = useMemo(() => candidateJoinedYears(), []);

  // Reset the chosen years whenever the selected set changes, so a year chosen
  // for one set never leaks into a different set's Execute.
  useEffect(() => {
    setJubileeYear('');
    setJoinedAfterYear('');
  }, [selectedValue]);

  // Run a set end-to-end given an EXPLICIT set object (never reading selection
  // from state). This is the single execute core both the Execute button and a
  // preferred/library Run call, so a Run can SELECT and RUN a set in the same
  // tick without waiting for a `selectedSet` state round-trip (findings: "the
  // preferred-list Run button does nothing" — it only set state, and
  // handleExecute then read a stale selection). Returns nothing; it resolves the
  // set's config, applies the set's own definition filters + any selector-driven
  // year filter, runs the client adapter over `processedData` (R4.4a — the
  // page's live filter is not re-baked), and renders the result.
  //
  // `selectors` carries the Jubilees / New-members year choices ONLY for the
  // Execute button path (where the selector UI exists for the currently-selected
  // set). A preferred/library Run has no selector UI, so it passes no selectors
  // and simply runs the set's own saved config (incl. its saved filters, issue
  // 3).
  const executeSet = useCallback(
    async (
      set: SelectableSet,
      selectors?: { jubileeYear?: string; joinedAfterYear?: string },
    ) => {
      setIsExecuting(true);
      try {
        const resolved = await resolveConfig(set);
        if (!resolved) {
          return;
        }

        // For the Jubilees preset with a chosen year (Execute button only), write
        // the year into the config's definition filters (R4.4) so it (a) travels
        // with the set when saved by task 7.5 and (b) narrows the executed rows
        // below. No chosen year → config untouched (all jubilee-eligible members).
        let config = resolved;
        const usesJubilee = set.usesJubileeRule === true;
        const usesJoined = set.usesJoinedAfterFilter === true;

        if (usesJubilee && selectors?.jubileeYear !== undefined) {
          const parsedYear = selectedJubileeYear({
            [JUBILEE_YEAR_FILTER_KEY]: selectors.jubileeYear,
          });
          config = {
            ...config,
            filters: {
              ...config.filters,
              ...(parsedYear !== undefined
                ? { [JUBILEE_YEAR_FILTER_KEY]: parsedYear }
                : {}),
            },
          };
        }

        // For the New-members preset with a chosen join year (Execute button
        // only), write it into the definition filters (findings F-010).
        if (usesJoined && selectors?.joinedAfterYear !== undefined) {
          const parsedJoined = selectedJoinedAfterYear({
            [JOINED_AFTER_FILTER_KEY]: selectors.joinedAfterYear,
          });
          config = {
            ...config,
            filters: {
              ...config.filters,
              ...(parsedJoined !== undefined
                ? { [JOINED_AFTER_FILTER_KEY]: parsedJoined }
                : {}),
            },
          };
        }

        // The client adapter aggregates/lists its input rows as-is and does not
        // itself apply `config.filters`, so every definition filter is applied
        // HERE, narrowing the page's own filtered dataset (R4.4a — the page's
        // live filter is NOT re-baked; we run over processedData as-is):
        //   - the jubilee / joined-after year selectors have their own year-aware
        //     appliers (applied only for their preset);
        //   - every OTHER saved equality filter (e.g. {clubblad:'Papier'}, issue
        //     3) is applied generically via applyDefinitionFilters. That helper
        //     SKIPS the reserved jubilee/joined keys, so applying it for all sets
        //     never double-handles the year filters.
        let rows: MemberRow[] = processedData;
        if (usesJubilee) {
          rows = applyJubileeYearFilter(rows, config.filters, fieldConfig ?? undefined);
        } else if (usesJoined) {
          rows = applyJoinedAfterFilter(rows, config.filters, fieldConfig ?? undefined);
        }
        rows = applyDefinitionFilters(rows, config.filters, fieldConfig ?? undefined);

        const pivotResult = executeMemberPivot(
          rows,
          config,
          fieldConfig ?? undefined,
        );
        setResult(pivotResult);
        setResultConfig(config);
      } finally {
        setIsExecuting(false);
      }
    },
    [processedData, fieldConfig],
  );

  // Execute is the ONLY thing the Execute button runs (R1.6 — explicit action).
  // It runs the currently-SELECTED set, passing the live selector year choices.
  const handleExecute = useCallback(() => {
    if (!selectedSet) {
      return;
    }
    void executeSet(selectedSet, {
      ...(showsJubileeSelector ? { jubileeYear } : {}),
      ...(showsJoinedAfterSelector ? { joinedAfterYear } : {}),
    });
  }, [
    selectedSet,
    executeSet,
    showsJubileeSelector,
    jubileeYear,
    showsJoinedAfterSelector,
    joinedAfterYear,
  ]);

  // The currently-selected saved set's summary (undefined for a preset or when
  // nothing is selected) — gates the Update / Delete actions, which apply only to
  // a tenant-saved member set.
  const selectedModelSummary = useMemo<MemberAnalyticsSetSummary | undefined>(() => {
    if (selectedSet?.source !== 'model' || typeof selectedSet.modelId !== 'string') {
      return undefined;
    }
    return savedModels.find((m) => m.id === selectedSet.modelId);
  }, [selectedSet, savedModels]);

  // --- Preferred list resolution + actions (R11.2). --------------------------

  // Resolve the ordered preferred refs into displayable rows, resolving
  // `preset:<key>` against the materialized presets and `set:<id>` against this
  // tenant's saved sets. A DANGLING ref (a set another user deleted, or a preset
  // no longer available for the tenant) is SKIPPED silently (R11.6) — never an
  // error. The resolved `optionValue` is the dropdown's own scheme so Run can
  // reuse the existing select + execute path.
  const preferredItems = useMemo(() => {
    const items: { ref: string; optionValue: string; label: string }[] = [];
    for (const ref of preferredRefs) {
      if (ref.startsWith(PRESET_PREFIX)) {
        const key = ref.slice(PRESET_PREFIX.length);
        const preset = presets.find((p) => p.key === key);
        if (preset) {
          items.push({ ref, optionValue: ref, label: t(preset.labelKey) });
        }
        continue; // dangling preset ref → skip (R11.6)
      }
      if (ref.startsWith(SET_PREFIX)) {
        const id = ref.slice(SET_PREFIX.length);
        const model = savedModels.find((m) => m.id === id);
        if (model) {
          items.push({
            ref,
            optionValue: `${MODEL_PREFIX}${id}`,
            label: model.name,
          });
        }
        continue; // dangling set ref → skip (R11.6)
      }
    }
    return items;
  }, [preferredRefs, presets, savedModels, t]);

  // The preferred items narrowed by the name filter, PRESERVING the user's saved
  // order (issue 2 — the preferred list stays in the user's own order; the
  // filter only hides non-matching rows).


  // The sets offered in the "Select a set" DROPDOWN: ONLY the user's preferred
  // list (in their saved order) — the everyday launcher. NO prefab/predefined
  // sets appear here unless the user has explicitly added them to the preferred
  // list. The full library (every prefab + custom set) lives behind the "All
  // sets" modal, where any set — including the jubilee/new-members selector
  // presets — can be Run directly or added to the preferred list. Each entry
  // resolves back to its full `SelectableSet` so the existing selection logic
  // (year selectors, Save-as / Update / Delete) is unchanged for a preferred set.
  const dropdownSets: SelectableSet[] = useMemo(() => {
    const byOption = new Map(sets.map((s) => [s.optionValue, s]));
    const result: SelectableSet[] = [];
    const seen = new Set<string>();
    // Preferred sets only, in the user's saved order.
    for (const item of preferredItems) {
      const set = byOption.get(item.optionValue);
      if (set && !seen.has(set.optionValue)) {
        result.push(set);
        seen.add(set.optionValue);
      }
    }
    return result;
  }, [sets, preferredItems]);

  // The FULL LIBRARY (issue 2): every preset + every saved set, ALPHABETICALLY
  // sorted by display label (localeCompare, case-insensitive), each tagged with
  // whether it is already in the preferred list (so Add can disable + show
  // "already added"). The library reuses the dropdown's `sets` (which already
  // flattens presets + saved models to {optionValue,label,source}) so a Run/Add
  // from the library speaks the same option-value scheme as everything else.
  const libraryItems = useMemo(() => {
    const items = sets.map((s) => {
      const ref = optionValueToRef(s.optionValue);
      return {
        optionValue: s.optionValue,
        label: s.label,
        ref,
        alreadyPreferred: ref !== null && preferredRefs.includes(ref),
        // A custom saved set (source 'model') can be permanently DELETED from the
        // library; a prefab/predefined preset (source 'preset') cannot (it lives
        // in code). `savedSetId` is the backend set_id for a saved set, else null.
        savedSetId:
          s.source === 'model' && typeof s.modelId === 'string' ? s.modelId : null,
      };
    });
    return items.sort((a, b) =>
      a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }),
    );
  }, [sets, preferredRefs]);

  // The library narrowed by its own name filter (substring, case-insensitive);
  // the alphabetical order is preserved.
  const filteredLibraryItems = useMemo(() => {
    const needle = libraryFilter.trim().toLowerCase();
    if (needle === '') {
      return libraryItems;
    }
    return libraryItems.filter((item) => item.label.toLowerCase().includes(needle));
  }, [libraryItems, libraryFilter]);

  // The HEADER label map for the result table (issue 4 — "result column headers
  // stay English"). The pivot result's `columns[].name` is the raw field key or
  // an aggregate expression (`COUNT(*)`, `SUM(age)`); PivotResultTable renders it
  // verbatim, so a Dutch tenant sees English keys. Build a name→label map from
  // the field config (bilingual, resolved to the active language) for every
  // group/list column, and a readable localized label for each aggregate column
  // ("Aantal" / "Count", "Som (Leeftijd)" / "Sum (Age)"). Passed ONLY to the
  // member result table — FIN/STR omit the prop and keep raw DB keys unchanged.
  const columnLabels = useMemo<Record<string, string>>(() => {
    if (!resultConfig) {
      return {};
    }
    const lang = (language || 'nl').slice(0, 2);
    const byKey = new Map<string, FieldConfigField>();
    for (const f of fieldConfig?.fields ?? []) {
      if (f && typeof f.key === 'string' && f.key !== '') {
        byKey.set(f.key, f);
      }
    }
    const labelForKey = (key: string): string =>
      resolveLabel(byKey.get(key)?.label, lang, key);

    const map: Record<string, string> = {};
    for (const col of result?.columns ?? []) {
      const agg = parseAggregateName(col.name);
      if (col.type === 'aggregate' && agg) {
        // Localize the function (COUNT → Aantal/Count) and, for a column-scoped
        // aggregate, append the inner field's label: "Som (Leeftijd)".
        const fnLabel = t(`analytics.pivotViews.aggregates.${agg.fn}`);
        map[col.name] =
          agg.inner === '' || agg.inner === '*'
            ? fnLabel
            : `${fnLabel} (${labelForKey(agg.inner)})`;
      } else {
        map[col.name] = labelForKey(col.name);
      }
    }
    return map;
  }, [result, resultConfig, fieldConfig, language, t]);

  // Persist a new ordered ref list (a FULL replace — one list per user, R11.2).
  // Optimistically updates local state, then saves; on failure it reloads the
  // server copy and toasts, so the UI never drifts from the stored list.
  const persistPreferred = useCallback(
    async (nextRefs: string[]) => {
      setIsSavingPreferred(true);
      const previous = preferredRefs;
      setPreferredRefs(nextRefs);
      try {
        const saved = await savePreferredList(nextRefs);
        setPreferredRefs(saved.refs);
        toast({ title: t('analytics.pivotViews.preferred.saved'), status: 'success' });
      } catch {
        setPreferredRefs(previous);
        toast({
          title: t('analytics.pivotViews.preferred.saveError'),
          status: 'error',
        });
      } finally {
        setIsSavingPreferred(false);
      }
    },
    [preferredRefs, toast, t],
  );

  // Add a tagged ref to the preferred list (append, no duplicates). The single
  // mutation both the dropdown's Add button and a library row's "Add to my list"
  // call (issue 2).
  const handleAddRef = useCallback(
    (ref: string | null) => {
      if (!ref || preferredRefs.includes(ref)) {
        return;
      }
      void persistPreferred([...preferredRefs, ref]);
    },
    [preferredRefs, persistPreferred],
  );

  // Remove a ref from the preferred list.
  const handleRemovePreferred = useCallback(
    (ref: string) => {
      void persistPreferred(preferredRefs.filter((r) => r !== ref));
    },
    [preferredRefs, persistPreferred],
  );

  // Reorder a ref one position up (-1) or down (+1) in the preferred list.
  const handleMovePreferred = useCallback(
    (ref: string, delta: -1 | 1) => {
      const index = preferredRefs.indexOf(ref);
      const target = index + delta;
      if (index < 0 || target < 0 || target >= preferredRefs.length) {
        return;
      }
      const next = [...preferredRefs];
      [next[index], next[target]] = [next[target], next[index]];
      void persistPreferred(next);
    },
    [preferredRefs, persistPreferred],
  );

  // Run a preferred/library item: resolve the SelectableSet from its option
  // value and EXECUTE it immediately (issue 1 — the old Run only set selection
  // state, and the Execute path then read a stale/empty selection, so nothing
  // ran). It also selects the set in the dropdown so the selector UI + Update/
  // --- Lifecycle actions (all explicit — R4.4b). -----------------------------

  // New set: open the picker blank (no seed, no edit target) to compose a brand
  // new member set and save it (R4.4).
  const handleNewSet = useCallback(() => {
    setPickerModel(undefined);
    setPickerSeed(undefined);
    setIsPickerOpen(true);
  }, []);

  // Save-as: open the picker as a NEW compose seeded from the selected set's
  // config, so the user saves a variant without touching the original (R4.4 —
  // the seed's definition filters travel into the new set). For a preset, seed
  // from the preset directly; for a saved model, load its definition and wrap it
  // as a one-off seed preset.
  const handleSaveAs = useCallback(async () => {
    if (!selectedSet) {
      return;
    }
    let seed: MemberPivotPreset | undefined;
    if (selectedSet.source === 'preset' && selectedSet.config) {
      seed = {
        key: 'save-as',
        labelKey: 'analytics.pivotViews.newSet',
        kind: 'count',
        config: selectedSet.config,
      };
    } else if (typeof selectedSet.modelId === 'string') {
      const saved = await getAnalyticsSet(selectedSet.modelId);
      seed = {
        key: 'save-as',
        labelKey: 'analytics.pivotViews.newSet',
        kind: 'count',
        config: saved.definition,
      };
    }
    setPickerModel(undefined);
    setPickerSeed(seed);
    setIsPickerOpen(true);
  }, [selectedSet]);

  // Update: open the picker EDITING the selected saved set in place. Its own
  // definition (incl. filters) is loaded from the Members API and round-trips
  // through the picker, so the saved set's filters are preserved (R4.4).
  // Tenant-scoped id only (R5.2).
  const handleUpdate = useCallback(async () => {
    if (!selectedModelSummary) {
      return;
    }
    const saved = await getAnalyticsSet(selectedModelSummary.id);
    setPickerSeed(undefined);
    setPickerModel({
      id: saved.id,
      name: saved.name,
      config: saved.definition,
    });
    setIsPickerOpen(true);
  }, [selectedModelSummary]);

  // Delivery: open the stored-delivery editor on the selected SAVED set (task
  // 3.4 / R3). The list summary carries no delivery, so fetch the full set first
  // and hand the editor the set's EXISTING delivery (undefined for a set that has
  // none yet). Tenant-scoped id only (R5.2). A fetch failure degrades to opening
  // the editor with no existing delivery (the user can still create one) rather
  // than crashing.
  const handleDelivery = useCallback(async () => {
    if (!selectedModelSummary) {
      return;
    }
    try {
      const saved = await getAnalyticsSet(selectedModelSummary.id);
      setDeliverySet({ id: saved.id, name: saved.name, delivery: saved.delivery });
    } catch {
      setDeliverySet({ id: selectedModelSummary.id, name: selectedModelSummary.name });
    }
    setIsDeliveryOpen(true);
  }, [selectedModelSummary]);

  // Persist the edited delivery for the open set (PUT the dedicated route, task
  // 3.3). The editor awaits this; a reject keeps the modal open with an error.
  const handleDeliverySave = useCallback(
    async (delivery: MemberDelivery) => {
      if (!deliverySet) {
        return;
      }
      await putAnalyticsSetDelivery(deliverySet.id, delivery);
      toast({ title: t('analytics.delivery.saved'), status: 'success' });
    },
    [deliverySet, toast, t],
  );

  // Clear the stored delivery for the open set (DELETE the dedicated route).
  const handleDeliveryClear = useCallback(async () => {
    if (!deliverySet) {
      return;
    }
    await deleteAnalyticsSetDelivery(deliverySet.id);
    toast({ title: t('analytics.delivery.cleared'), status: 'success' });
  }, [deliverySet, toast, t]);


  // Schedule: open the schedule editor on the selected SAVED set (task 5.4 / R5).
  // A schedule can only be attached to a set that HAS a delivery block (R5), so
  // the full set is fetched to confirm its delivery AND its existing schedule is
  // listed (the summary carries neither); the editor is seeded with both. The
  // action is only enabled (below) for a set the list feed reports as having a
  // delivery AND for a caller who may schedule — but we re-resolve the delivery
  // from the authoritative full set here. A fetch failure degrades to opening the
  // editor with the summary's `hasDelivery` and no existing schedule (the user can
  // still create one if the set has a delivery) rather than crashing.
  const handleSchedule = useCallback(async () => {
    if (!selectedModelSummary) {
      return;
    }
    try {
      const [saved, schedules] = await Promise.all([
        getAnalyticsSet(selectedModelSummary.id),
        listSchedulesForSet(selectedModelSummary.id),
      ]);
      setScheduleSet({
        id: saved.id,
        name: saved.name,
        hasDelivery: saved.delivery !== undefined,
        schedule: schedules[0],
      });
    } catch {
      setScheduleSet({
        id: selectedModelSummary.id,
        name: selectedModelSummary.name,
        hasDelivery: selectedModelSummary.hasDelivery === true,
      });
    }
    setIsScheduleOpen(true);
  }, [selectedModelSummary]);

  // Create a schedule for the open set (POST /members/schedules, task 5.2). The
  // editor awaits this; a reject keeps the modal open with an error.
  const handleScheduleCreate = useCallback(
    async (cadence: MemberScheduleCadence, enabled: boolean) => {
      if (!scheduleSet) {
        return;
      }
      await createSchedule(scheduleSet.id, cadence, enabled);
      toast({ title: t('analytics.schedule.saved'), status: 'success' });
    },
    [scheduleSet, toast, t],
  );

  // Update the open set's existing schedule (PUT /members/schedules/{id}).
  const handleScheduleUpdate = useCallback(
    async (cadence: MemberScheduleCadence, enabled: boolean) => {
      if (!scheduleSet?.schedule) {
        return;
      }
      await updateSchedule(scheduleSet.schedule.scheduleId, cadence, enabled);
      toast({ title: t('analytics.schedule.saved'), status: 'success' });
    },
    [scheduleSet, toast, t],
  );

  // Delete the open set's schedule (DELETE /members/schedules/{id}).
  const handleScheduleDelete = useCallback(async () => {
    if (!scheduleSet?.schedule) {
      return;
    }
    await deleteSchedule(scheduleSet.schedule.scheduleId);
    toast({ title: t('analytics.schedule.deleted'), status: 'success' });
  }, [scheduleSet, toast, t]);

  // After a save/update, refresh the dropdown so the change appears immediately,
  // and (re)select the saved set so the user can run it. A save returns the new
  // set id; an update reuses the existing id (both are the backend `set_id`
  // string).
  const handlePickerSaved = useCallback(
    async (_config: PivotConfig, _name: string, modelId?: string) => {
      await refreshSavedModels();
      if (typeof modelId === 'string') {
        setSelectedValue(`${MODEL_PREFIX}${modelId}`);
      }
    },
    [refreshSavedModels],
  );

  // Delete: explicit, confirmed (R4.4b). The confirm dialog is opened by the
  // Delete button; this performs the delete, refreshes the list, and clears the
  // selection/result if the deleted set was selected.
  const handleConfirmDelete = useCallback(async () => {
    if (!pendingDelete) {
      return;
    }
    setIsDeleting(true);
    try {
      await deleteAnalyticsSet(pendingDelete.id);
      toast({ title: t('analytics.pivotViews.lifecycle.deleted'), status: 'success' });
      const wasSelected = selectedValue === `${MODEL_PREFIX}${pendingDelete.id}`;
      await refreshSavedModels();
      if (wasSelected) {
        setSelectedValue('');
        setResult(null);
        setResultConfig(null);
      }
      setPendingDelete(null);
    } catch {
      toast({ title: t('analytics.pivotViews.lifecycle.deleteError'), status: 'error' });
    } finally {
      setIsDeleting(false);
    }
  }, [pendingDelete, selectedValue, refreshSavedModels, toast, t]);

  // The rows every export operates on: the table's VISIBLE (post-filter/sort)
  // rows when the table has reported them, else the full result. This is what
  // makes an export honor the in-table column filters (findings: "table filters
  // do not limit the export") — the table reports its filtered rows via
  // onVisibleRowsChange below, and CSV / mail / PDF all read THESE rows.
  const exportRows = useMemo<Record<string, unknown>[]>(
    () => (visibleRows.length > 0 ? visibleRows : (result?.data ?? [])),
    [visibleRows, result],
  );

  // CSV export of the produced result (task 8.1, R4.9/R4.11). REUSES
  // `csvExport.ts` — no bespoke CSV. The produced `PivotResult` is mapped onto
  // the util's `{ key, header }[]` + object-rows shape: a result column's `name`
  // is BOTH the key the util reads from each `data` row AND the header, so the
  // same mapping serves an AGGREGATE result (group + aggregate columns) and a
  // filtered-LIST result (one row per member, R4.11) without special-casing.
  // Gated by `capabilities.canExport` (members:export) at the slot below; this
  // handler is a no-op if there is no result to export.
  const handleExportCsv = useCallback(() => {
    if (!result || result.columns.length === 0) {
      return;
    }
    // The CSV HEADER uses the localized column label (same `columnLabels` map the
    // result table renders — Dutch/English per the active language); the KEY
    // stays the raw result column name so values still read from each data row.
    const columns = result.columns.map((col) => ({
      key: col.name,
      header: columnLabels[col.name] ?? col.name,
    }));
    const csv = generateCsvFromObjects(columns, exportRows);
    downloadCsv(csv, 'member-analytics.csv');

    // Audit the export (C7 / R8.1): metadata only — the set that produced it, the
    // row count, and the output kind. NO member rows / PII leave the client; the
    // `filter_summary` carries only the shape of the result (column count), never
    // the filtered values. Fire-and-forget — never blocks the download (R8.3).
    void recordAnalyticsOutput({
      outputKind: 'csv_export',
      setKey: selectedSet?.optionValue,
      recordCount: exportRows.length,
      filterSummary: { columns: result.columns.length },
    });
  }, [result, selectedSet, exportRows]);

  // --- "Send CSV by email" (Export-CSV menu, pivot-output-actions C5) --------
  // The Export action is a MENU: "Save locally" (handleExportCsv above) OR "Send CSV by email"
  // — the latter mails the current result as a CSV attachment to one or more fixed addresses via
  // the SAME proven SAM `to_fixed` + `attachment:'csv'` path the compose uses (the worker builds
  // the CSV bytes on-plane; the frontend ships only the kind + rows). A small dialog collects the
  // address(es) and confirms before sending (R8.4).
  const [isCsvMailOpen, setIsCsvMailOpen] = useState(false);
  const [csvMailTo, setCsvMailTo] = useState('');
  const [csvMailSending, setCsvMailSending] = useState(false);
  const csvMailCancelRef = useRef<HTMLButtonElement>(null);

  const csvMailRecipients = useMemo(
    () =>
      csvMailTo
        .split(/[\s,;]+/)
        .map((a) => a.trim())
        .filter((a) => a.length > 0),
    [csvMailTo],
  );
  const csvMailValid =
    csvMailRecipients.length > 0 &&
    csvMailRecipients.every((a) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(a));

  const handleOpenCsvMail = useCallback(() => {
    setCsvMailTo('');
    setIsCsvMailOpen(true);
  }, []);

  const handleSendCsvMail = useCallback(async () => {
    if (!csvMailValid || csvMailSending) {
      return;
    }
    setCsvMailSending(true);
    try {
      const body: AdHocMailBody = {
        mode: 'to_fixed',
        result_rows: exportRows as Array<Record<string, unknown>>,
        recipients: csvMailRecipients,
        template_id: null,
        attachment: 'csv',
        ...(selectedSet?.optionValue ? { set_id: selectedSet.optionValue } : {}),
      };
      const res = await sendAdHocMail(body);
      toast({
        title: t('analytics.export.csvMail.queued', { count: res.enqueued }),
        status: 'success',
      });
      // Audit the output (C7 / R8.1): metadata only, mirroring the download path.
      void recordAnalyticsOutput({
        outputKind: 'csv_export',
        setKey: selectedSet?.optionValue,
        recordCount: exportRows.length,
        filterSummary: { columns: result?.columns.length ?? 0, delivery: 'email' },
      });
      setIsCsvMailOpen(false);
    } catch (err) {
      applyApiError(err, { toast, t });
    } finally {
      setCsvMailSending(false);
    }
  }, [csvMailValid, csvMailSending, exportRows, csvMailRecipients, selectedSet, result, toast, t]);

  // Deliver now: send the CURRENT pivot result (on-screen rows) to the set's
  // stored fixed recipients as a CSV — the one-button equivalent of Export CSV
  // -> Email, via the ad-hoc path. (The old saved-set /deliver route recomputed
  // rows server-side and leaked the whole raw member table; it is no longer used
  // here.)
  const handleDeliverNow = useCallback(async () => {
    if (!selectedModelSummary || isDeliveringNow) {
      return;
    }
    // Deliver now sends the CURRENT pivot RESULT (the on-screen rows) — it is the
    // one-button equivalent of Export CSV -> Email, reusing the SAME proven
    // ad-hoc `to_fixed` + `attachment:'csv'` path (`sendAdHocMail`) that carries
    // the frontend's `exportRows`. It does NOT call the saved-set `/deliver`
    // server path, which recomputes rows server-side and (with the interim
    // pass-through runner) would ship the whole raw member table — a data leak.
    // Here the ROWS come from the screen (filtered + projected to the result
    // columns) and only the fixed RECIPIENTS come from the set's stored delivery.
    if (!result) {
      // Nothing on screen to deliver — Deliver now operates on a produced result.
      toast({ title: t('analytics.delivery.deliverNowNeedsResult'), status: 'warning' });
      return;
    }
    setIsDeliveringNow(true);
    try {
      // Read the set's stored fixed recipients (the summary carries only
      // `hasDelivery`, not the recipient list). A fetch failure surfaces below.
      const saved = await getAnalyticsSet(selectedModelSummary.id);
      const delivery = saved.delivery;
      if (!delivery || delivery.mode !== 'to_fixed') {
        toast({ title: t('analytics.delivery.deliverNowNeedsFixed'), status: 'warning' });
        return;
      }
      const recipients = (delivery.recipients ?? []).filter(
        (r): r is string => typeof r === 'string' && r.trim().length > 0,
      );
      if (recipients.length === 0) {
        toast({ title: t('analytics.delivery.deliverNowNeedsFixed'), status: 'warning' });
        return;
      }
      // Send the ON-SCREEN result rows to the stored fixed addresses as a CSV —
      // identical shape to handleSendCsvMail, just with the recipients sourced
      // from the saved delivery instead of a typed-in dialog.
      const body: AdHocMailBody = {
        mode: 'to_fixed',
        result_rows: exportRows as Array<Record<string, unknown>>,
        recipients,
        template_id: null,
        attachment: 'csv',
        ...(selectedSet?.optionValue ? { set_id: selectedSet.optionValue } : {}),
      };
      const res = await sendAdHocMail(body);
      toast({
        title: t('analytics.delivery.deliverNowQueued', { count: res.enqueued }),
        status: 'success',
      });
      void recordAnalyticsOutput({
        outputKind: 'csv_export',
        setKey: selectedSet?.optionValue,
        recordCount: exportRows.length,
        filterSummary: { columns: result.columns.length, delivery: 'deliver_now' },
      });
    } catch (err) {
      // Typed refusal (not-certified) or network error -> clear bilingual toast.
      applyApiError(err, { toast, t });
    } finally {
      setIsDeliveringNow(false);
    }
  }, [selectedModelSummary, isDeliveringNow, result, exportRows, selectedSet, toast, t]);

  // Whether the tenant has a resolvable address mapping — gates the mail
  // compose's "attach PDF labels" toggle (R4.10). Memoized on the field config.
  const hasAddressMapping = useMemo(
    () => Object.keys(resolveAddressMapping(fieldConfig ?? undefined)).length > 0,
    [fieldConfig],
  );

  // Whether the tenant has at least one LABEL template (`kind:"label"`). This —
  // NOT the address mapping — is now the content precondition the labels action
  // depends on (labels sub-spec R-L2 / Property 3; R6 "no analytics config": the
  // action no longer reads any `analytics.*`). Fail-closed: an empty list (a
  // failed/absent load) means no template, so the action stays hidden.
  const hasLabelTemplate = labelTemplates.length > 0;

  // Availability gate for the "Generate address labels" action (labels sub-spec
  // R-L2 / Property 3). The action is OFFERED only when the caller holds
  // `members:export` AND at least one LABEL template exists. This is the NEW
  // gate: it depends ONLY on `capabilities.canExport` + `hasLabelTemplate`, and
  // deliberately NOT on the address mapping / any `analytics.*` config (R6). The
  // mail compose's SEPARATE "attach PDF labels" path keeps using
  // `hasAddressMapping` (below) — that is a different feature, left intact. When
  // either condition is false the action is HIDDEN with a bilingual degradation
  // reason (below). `canGenerateLabels` is the single predicate the labels action
  // and its modal mount render on.
  const canGenerateLabels = capabilities.canExport && hasLabelTemplate;

  // The tenant's mail-enabled gate flag (pivot-output-actions R0/R1 task 1.3, design §6.3).
  // The per-tenant "mail-enabled / SES-certified" onboarding gate is OWNED by the tenant-admin
  // module (Flask writes it to MySQL `parameters`), projected one-directionally as `config#mail`,
  // and READ by the Members edge — surfaced to the SPA on the field config as `mail_enabled`
  // (NO live MySQL at request time). The pivot result's Mail output action (the compose action /
  // send path) is OFFERED only when this is true (R1); otherwise the action is HIDDEN with the
  // shared degradation reason, exactly mirroring how `canGenerateLabels` gates the labels action.
  // FAIL-CLOSED: a missing/absent flag means NOT enabled. This is a tenant onboarding gate, not a
  // capability gate — the surrounding slot still requires `members:export`; CSV + labels stay
  // available regardless. The send path re-checks the gate server-side (design §9).
  const mailEnabled = fieldConfig?.mail_enabled === true;

  // Build the CSV bytes of the CURRENT result, base64-encoded, for the mail
  // compose "attach CSV" toggle (task 9.2). REUSES the same `csvExport.ts`
  // mapping as the download path (a column's name is both key + header), so the
  // attached CSV is byte-identical to the downloaded one. Returns null when
  // there is no result to attach.
  const buildCsvBase64 = useCallback((): string | null => {
    if (!result || result.columns.length === 0) {
      return null;
    }
    // Localized headers, raw-name keys — identical mapping to the download path
    // so the attached CSV is byte-identical to the downloaded one.
    const columns = result.columns.map((col) => ({
      key: col.name,
      header: columnLabels[col.name] ?? col.name,
    }));
    const csv = generateCsvFromObjects(columns, exportRows);
    // Prepend the UTF-8 BOM to match the downloaded file, then base64-encode the
    // UTF-8 bytes (btoa needs a binary string, so encode via encodeURIComponent).
    const withBom = `\uFEFF${csv}`;
    return btoa(unescape(encodeURIComponent(withBom)));
  }, [result, exportRows, columnLabels]);

  // Build the PDF address-label bytes for the CURRENT result rows, base64-encoded,
  // for the mail compose "attach PDF labels" toggle (task 9.2). Uses the jsPDF
  // address-label generator (task 8.2) with the default Avery format; the labels
  // are composed from the tenant's resolved `address_mapping`. Returns null when
  // there is no result or no resolvable address mapping (R4.10).
  const buildPdfBase64 = useCallback((): string | null => {
    if (!result || !hasAddressMapping) {
      return null;
    }
    const format =
      getLabelFormat(DEFAULT_LABEL_FORMAT_KEY) ?? AVERY_LABEL_FORMATS[0];
    const { doc } = generateAddressLabelPdf(
      exportRows as MemberRow[],
      fieldConfig ?? undefined,
      format,
    );
    // jsPDF emits a base64 datauristring (`data:...;base64,<payload>`); strip the
    // prefix so the backend receives raw base64 (task 9.1 base64-decodes it).
    const dataUri = doc.output('datauristring');
    const comma = dataUri.indexOf(',');
    return comma >= 0 ? dataUri.slice(comma + 1) : dataUri;
  }, [result, hasAddressMapping, fieldConfig, exportRows]);

  return (
    <Box data-testid="member-pivot-views">
      <VStack align="stretch" spacing={4}>
        <HStack align="flex-end" spacing={3}>
          <FormControl maxW="sm">
            <FormLabel htmlFor="member-pivot-set-select" color="gray.300" fontSize="sm" mb={1}>
              {t('analytics.pivotViews.selectSet')}
            </FormLabel>
            {/* The dropdown lists ONLY the user's preferred sets (in saved order),
                plus the always-reachable jubilee/new-members selector presets.
                The full library is behind the "All sets" button beside it. */}
            <Select
              id="member-pivot-set-select"
              placeholder={t('analytics.pivotViews.selectSetPlaceholder')}
              value={selectedValue}
              onChange={(e) => setSelectedValue(e.target.value)}
              bg="gray.700"
              color="white"
              data-testid="member-pivot-set-select"
            >
              {dropdownSets.map((s) => (
                <option key={s.optionValue} value={s.optionValue}>
                  {s.label}
                </option>
              ))}
            </Select>
          </FormControl>

          {/* Jubilee year selector — shown ONLY for the Jubilees preset (the set
              flagged usesJubileeRule, task 7.2 / R4.2). The chosen year becomes a
              definition filter on the set (R4.4) and narrows the Execute result
              to members at that jubilee. Native <select> → keyboard-accessible,
              bilingual label from the members namespace (no hardcoded English). */}
          {showsJubileeSelector && (
            <FormControl maxW="xs">
              <FormLabel
                htmlFor="member-pivot-jubilee-year"
                color="gray.300"
                fontSize="sm"
                mb={1}
              >
                {t('analytics.pivotViews.jubileeYear')}
              </FormLabel>
              <Select
                id="member-pivot-jubilee-year"
                placeholder={t('analytics.pivotViews.jubileeYearPlaceholder')}
                value={jubileeYear}
                onChange={(e) => setJubileeYear(e.target.value)}
                bg="gray.700"
                color="white"
                data-testid="member-pivot-jubilee-year"
              >
                {jubileeYearOptions.map((year) => (
                  <option key={year} value={String(year)}>
                    {year}
                  </option>
                ))}
              </Select>
            </FormControl>
          )}

          {/* Join-year selector — shown ONLY for the New-members preset (the set
              flagged usesJoinedAfterFilter, findings F-010). The chosen year
              becomes a definition filter on the set (R4.4) and narrows the
              Execute result to members who joined in or after that year. Native
              <select> → keyboard-accessible, bilingual label from the members
              namespace (no hardcoded English). */}
          {showsJoinedAfterSelector && (
            <FormControl maxW="xs">
              <FormLabel
                htmlFor="member-pivot-joined-after"
                color="gray.300"
                fontSize="sm"
                mb={1}
              >
                {t('analytics.pivotViews.joinedAfter')}
              </FormLabel>
              <Select
                id="member-pivot-joined-after"
                placeholder={t('analytics.pivotViews.joinedAfterPlaceholder')}
                value={joinedAfterYear}
                onChange={(e) => setJoinedAfterYear(e.target.value)}
                bg="gray.700"
                color="white"
                data-testid="member-pivot-joined-after"
              >
                {joinedYearOptions.map((year) => (
                  <option key={year} value={String(year)}>
                    {year}
                  </option>
                ))}
              </Select>
            </FormControl>
          )}

          {/* Execute — sits right next to the selected pivot (R1.6: nothing runs
              until clicked; disabled until a set is chosen). */}
          <Button
            colorScheme="orange"
            onClick={handleExecute}
            isDisabled={!selectedSet}
            isLoading={isExecuting}
            data-testid="member-pivot-execute"
          >
            {t('analytics.pivotViews.execute')}
          </Button>

          {/* Secondary navigation collapsed into a quiet "More" menu (redesign
              Q2): the library browser ("All sets") + the send-status/history
              screen ("Mail status"). Neither is part of the run flow, so they
              sit behind one overflow control instead of competing with Execute.
              Mail status is export-gated (its read routes are, R9.3); All sets is
              always available. The item testids are preserved so existing flows
              (and tests) reach them unchanged — just open the menu first. */}
          <Menu>
            <MenuButton
              as={Button}
              variant="outline"
              colorScheme="orange"
              ml={2}
              data-testid="member-pivot-more"
            >
              {t('analytics.pivotViews.more')}
            </MenuButton>
            <MenuList bg="gray.800" borderColor="gray.600">
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={() => setIsLibraryOpen(true)}
                data-testid="member-pivot-open-library"
              >
                {t('analytics.pivotViews.library.open')}
              </MenuItem>
              {capabilities.canExport && (
                <MenuItem
                  bg="gray.800"
                  _hover={{ bg: 'gray.700' }}
                  onClick={() => setIsMailStatusOpen(true)}
                  data-testid="member-pivot-open-mail-status"
                >
                  {t('analytics.mailRuns.action')}
                </MenuItem>
              )}
            </MenuList>
          </Menu>
        </HStack>

        {/* Save lifecycle actions (task 7.5) — all EXPLICIT user actions (R4.4b):
              - New set: compose + save a brand-new member set (R4.4);
              - Save as: save the selected set as a NEW variant (R4.4);
              - Update / Delete: act on the selected SAVED model only.
            Nothing here is auto-saved; the page's live filter is never baked into
            a saved set (R4.4a — the picker is never handed the page filter). */}
        {/* Create/edit a shared set needs members:export OR members:write (R11);
            delete needs members:write OR members:admin. A read-only caller sees
            no set-mutation actions at all (the whole HStack is gated). */}
        {/* Set-management actions collapsed into ONE "Manage set" menu
            (redesign Q1): New set / Save as / Update / Delivery / Deliver now /
            Schedule. They are occasional, admin-ish actions contextual to a
            selected saved set and rarely all needed at once, so a menu removes
            the wall of six buttons without changing any gate. Every item keeps
            its EXACT testid, onClick, and disabled rule, so existing flows and
            tests reach them unchanged — just open the menu first. */}
        {canManageSets && (
          <Menu>
            <MenuButton
              as={Button}
              variant="outline"
              colorScheme="orange"
              data-testid="member-pivot-manage-set"
            >
              {t('analytics.pivotViews.manageSet')}
            </MenuButton>
            <MenuList bg="gray.800" borderColor="gray.600" data-testid="member-pivot-set-actions">
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={handleNewSet}
                data-testid="member-pivot-new-set"
              >
                {t('analytics.pivotViews.newSet')}
              </MenuItem>
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={handleSaveAs}
                isDisabled={!selectedSet}
                data-testid="member-pivot-save-as"
              >
                {t('analytics.pivotViews.saveAs')}
              </MenuItem>
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={handleUpdate}
                isDisabled={!selectedModelSummary}
                data-testid="member-pivot-update"
              >
                {t('analytics.pivotViews.update')}
              </MenuItem>
              {/* Delivery — edit the SAVED set's stored delivery block (R3). */}
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={handleDelivery}
                isDisabled={!selectedModelSummary}
                data-testid="member-pivot-delivery"
              >
                {t('analytics.delivery.action')}
              </MenuItem>
              {/* Deliver now — send the on-screen result to the set's stored fixed
                  recipients (R3.1/R3.2). A confirm dialog opens first so the send
                  is never fired blind. */}
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={() => {
                  // Guard the open so a disabled item can never surface the
                  // confirm (Chakra's isDisabled does not always suppress the
                  // click handler in every environment).
                  if (!selectedModelSummary || isDeliveringNow) {
                    return;
                  }
                  setIsDeliverNowConfirmOpen(true);
                }}
                isDisabled={!selectedModelSummary || isDeliveringNow}
                data-testid="member-pivot-deliver-now"
              >
                {t('analytics.delivery.deliverNow')}
              </MenuItem>
              {/* Schedule — attach/manage a recurring run (R5). Offered only when
                  the caller may schedule; disabled (with a reason) for a set with
                  no delivery block. */}
              {canSchedule &&
                (selectedModelSummary && selectedModelSummary.hasDelivery !== true ? (
                  <Tooltip label={t('analytics.schedule.needsDelivery')}>
                    {/* A disabled MenuItem does not fire pointer events, so the
                        Tooltip wraps a focusable span to still surface the reason. */}
                    <MenuItem
                      bg="gray.800"
                      _hover={{ bg: 'gray.700' }}
                      isDisabled
                      data-testid="member-pivot-schedule"
                    >
                      {t('analytics.schedule.action')}
                    </MenuItem>
                  </Tooltip>
                ) : (
                  <MenuItem
                    bg="gray.800"
                    _hover={{ bg: 'gray.700' }}
                    onClick={handleSchedule}
                    isDisabled={!selectedModelSummary}
                    data-testid="member-pivot-schedule"
                  >
                    {t('analytics.schedule.action')}
                  </MenuItem>
                ))}
            </MenuList>
          </Menu>
        )}

        {/* The produced result (REUSE PivotResultTable, R4.7). Rendered only
            AFTER an explicit Execute — null until then (R1.6). */}
        {result && resultConfig && (
          <Box data-testid="member-pivot-result">
            <PivotResultTable
              data={result.data}
              columns={result.columns}
              config={resultConfig}
              isLoading={isExecuting}
              hideExportMenu
              onVisibleRowsChange={setVisibleRows}
              columnLabels={columnLabels}
            />

            {capabilities.canExport && (
              <HStack
                mt={3}
                spacing={2}
                data-testid="pivot-result-actions"
                aria-label={t('analytics.export.csv')}
              >
                <Menu>
                  <MenuButton
                    as={Button}
                    variant="outline"
                    colorScheme="orange"
                    data-testid="member-pivot-export-csv"
                  >
                    {t('analytics.export.csv')}
                  </MenuButton>
                  <MenuList bg="gray.800" borderColor="gray.600">
                    <MenuItem
                      bg="gray.800"
                      _hover={{ bg: 'gray.700' }}
                      onClick={handleExportCsv}
                      data-testid="member-pivot-export-csv-download"
                    >
                      {t('analytics.export.csvDownload')}
                    </MenuItem>
                    <MenuItem
                      bg="gray.800"
                      _hover={{ bg: 'gray.700' }}
                      onClick={handleOpenCsvMail}
                      data-testid="member-pivot-export-csv-email"
                    >
                      {t('analytics.export.csvEmail')}
                    </MenuItem>
                  </MenuList>
                </Menu>
                {/* Mail (R1 / pivot-output-actions task 1.3) — OFFERED only when the
                    tenant is mail-enabled (the R0 `config#mail` gate surfaced as
                    `fieldConfig.mail_enabled`). When enabled, the compose action /
                    send path is offered; when NOT enabled the action is HIDDEN and
                    the shared degradation reason explains why
                    (`analytics.degradation.mailNotEnabled`), mirroring how the labels
                    action degrades on an absent address mapping. A tenant ONBOARDING
                    gate, not a capability gate: CSV + labels stay available regardless. */}
                {mailEnabled ? (
                  <Button
                    variant="outline"
                    colorScheme="orange"
                    onClick={() => setIsMailOpen(true)}
                    data-testid="member-pivot-mail"
                  >
                    {t('analytics.export.mail')}
                  </Button>
                ) : (
                  <AnalyticsStateNotice
                    kind="degradation"
                    message={t('analytics.degradation.mailNotEnabled')}
                    testId="member-pivot-mail-unavailable"
                  />
                )}
                {/* Generate address labels (labels sub-spec R-L2 / Property 3) —
                    a first-class result action beside CSV / Mail. Opens the
                    labels options UI in a modal.

                    Availability gate (labels sub-spec R-L2 / Property 3): the
                    slot already requires `members:export`, so the one remaining
                    condition is that at least one LABEL template exists — together
                    `canGenerateLabels`. The gate depends ONLY on
                    `canExport` + `hasLabelTemplate` and deliberately NOT on the
                    address mapping / any `analytics.*` config (R6). When it holds,
                    the action is OFFERED; when there is NO label template (or no
                    export) the action is HIDDEN with the bilingual labels-namespace
                    degradation reason (`analytics.labels.noTemplate`). A
                    config/capability gate — NOT a tenant gate: CSV + Mail stay
                    available regardless. */}
                {canGenerateLabels ? (
                  <Button
                    variant="outline"
                    colorScheme="orange"
                    onClick={() => setIsLabelsOpen(true)}
                    data-testid="member-pivot-labels"
                  >
                    {t('analytics.labels.action')}
                  </Button>
                ) : (
                  <AnalyticsStateNotice
                    kind="degradation"
                    message={t('analytics.labels.noTemplate')}
                    testId="member-pivot-labels-unavailable"
                  />
                )}
              </HStack>
            )}
          </Box>
        )}
      </VStack>

      {/* "All sets" library modal — the single management surface for the pivot
          library (keeps the main pane clean). Two lists:
            1. MY PREFERRED LIST: the user's per-user ordered shortlist (also what
               the main dropdown offers). Each item Runs immediately, reorders
               (up/down), and removes. Name filter preserves the saved order.
            2. FULL LIBRARY: every preset + saved set, ALPHABETICALLY sorted, name
               filter, Run + "Add to my list" (disabled / "already added").
          Add/remove/reorder + add are gated on members:export|write; a read-only
          caller sees both lists read-only (Run only). */}
      <Modal
        isOpen={isLibraryOpen}
        onClose={() => setIsLibraryOpen(false)}
        size="2xl"
        isCentered
        scrollBehavior="inside"
      >
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white" data-testid="member-pivot-library-modal">
          <ModalHeader>{t('analytics.pivotViews.library.open')}</ModalHeader>
          <ModalCloseButton />
          <ModalBody pb={6}>
            {/* A SINGLE "All sets" list (the separate preferred list was removed —
                it duplicated the dropdown, which already IS the preferred list).
                Each row shows the FULL set name on its own line (never truncated),
                then an actions line: Run; Add (not yet preferred) / Remove + ↑↓
                reorder (already preferred). */}
            <Box data-testid="member-pivot-library">
              <Box color="gray.500" fontSize="xs" mb={2}>
                {t('analytics.pivotViews.library.description')}
              </Box>

              <Input
                size="sm"
                mb={3}
                value={libraryFilter}
                onChange={(e) => setLibraryFilter(e.target.value)}
                placeholder={t('analytics.pivotViews.library.filterPlaceholder')}
                aria-label={t('analytics.pivotViews.library.filterPlaceholder')}
                bg="gray.700"
                color="white"
                _placeholder={{ color: 'gray.400' }}
                data-testid="member-pivot-library-filter"
              />

              {filteredLibraryItems.length === 0 ? (
                <Box
                  color="gray.500"
                  fontSize="sm"
                  data-testid="member-pivot-library-empty"
                >
                  {t('analytics.pivotViews.library.empty')}
                </Box>
              ) : (
                <VStack
                  align="stretch"
                  spacing={2}
                  data-testid="member-pivot-library-list"
                >
                  {filteredLibraryItems.map((item) => {
                    const addLabel = t('analytics.pivotViews.library.add');
                    const removeLabel = t('analytics.pivotViews.library.remove');
                    const deleteLabel = t('analytics.pivotViews.library.delete');
                    return (
                      <HStack
                        key={item.optionValue}
                        bg="gray.700"
                        px={3}
                        py={2}
                        borderRadius="md"
                        align="center"
                        justify="space-between"
                        spacing={3}
                        data-testid="member-pivot-library-item"
                      >
                        {/* Full name on the left — grows to fill, wraps on word
                            boundaries (never truncated, never per-character). The
                            compact icon actions keep a fixed width on the right. */}
                        <Box
                          color="white"
                          fontSize="sm"
                          flex="1"
                          whiteSpace="normal"
                          wordBreak="break-word"
                          data-testid="member-pivot-library-name"
                        >
                          {item.label}
                        </Box>
                        {/* Manage-only icon actions (no Run — running is from the
                            main-pane dropdown + Execute): transfer in/out of my
                            list + permanently delete a CUSTOM saved set. */}
                        {canManageSets && (
                          <HStack spacing={1} flexShrink={0}>
                            {item.alreadyPreferred ? (
                              <Tooltip label={removeLabel}>
                                <IconButton
                                  size="xs"
                                  variant="ghost"
                                  colorScheme="orange"
                                  aria-label={removeLabel}
                                  icon={<MinusIcon />}
                                  onClick={() =>
                                    item.ref !== null && handleRemovePreferred(item.ref)
                                  }
                                  isDisabled={isSavingPreferred}
                                  data-testid="member-pivot-library-remove"
                                />
                              </Tooltip>
                            ) : (
                              <Tooltip label={addLabel}>
                                <IconButton
                                  size="xs"
                                  variant="ghost"
                                  colorScheme="orange"
                                  aria-label={addLabel}
                                  icon={<AddIcon />}
                                  onClick={() => handleAddRef(item.ref)}
                                  isDisabled={isSavingPreferred}
                                  data-testid="member-pivot-library-add"
                                />
                              </Tooltip>
                            )}
                            {/* Permanent delete — only for a CUSTOM saved set
                                (prefab presets live in code and cannot be
                                deleted). Gated additionally by canDeleteSets
                                (members:write|admin). Opens the confirm dialog. */}
                            {item.savedSetId !== null && canDeleteSets && (
                              <Tooltip label={deleteLabel}>
                                <IconButton
                                  size="xs"
                                  variant="ghost"
                                  colorScheme="red"
                                  aria-label={deleteLabel}
                                  icon={<DeleteIcon />}
                                  onClick={() =>
                                    setPendingDelete({
                                      id: item.savedSetId as string,
                                      name: item.label,
                                      kind: 'count',
                                    })
                                  }
                                  isDisabled={isSavingPreferred}
                                  data-testid="member-pivot-library-delete"
                                />
                              </Tooltip>
                            )}
                          </HStack>
                        )}
                      </HStack>
                    );
                  })}
                </VStack>
              )}
            </Box>
          </ModalBody>
        </ModalContent>
      </Modal>

      {/* Mail status / history modal (mail-spec task 3.3 / R9). Hosts the
          MemberMailStatus screen: a role-scoped list of send-runs + per-run
          FAILURE drill-down (R9.2), with honest "sent = SES accepted, not
          delivered" labelling (R9.4). Mounted only when its members:export entry
          point is offered; the screen loads the run list on open. */}
      {capabilities.canExport && (
        <Modal
          isOpen={isMailStatusOpen}
          onClose={() => setIsMailStatusOpen(false)}
          size="2xl"
          isCentered
          scrollBehavior="inside"
        >
          <ModalOverlay />
          <ModalContent
            bg="gray.800"
            color="white"
            data-testid="member-pivot-mail-status-modal"
          >
            <ModalHeader>{t('analytics.mailRuns.title')}</ModalHeader>
            <ModalCloseButton />
            <ModalBody pb={6}>
              <MemberMailStatus language={language} />
            </ModalBody>
          </ModalContent>
        </Modal>
      )}

      {/* The compose/edit modal (task 7.4 / 7.5). Mounted here so New set /
          Save-as / Update all route through the SAME picker; `existingModel`
          switches it between create and in-place update. On a successful
          save/update it refreshes the dropdown + reselects the set. The picker is
          never passed `processedData`, so the page's live filter can never be
          baked into a saved set (R4.4a). */}
      <MemberFieldPicker
        isOpen={isPickerOpen}
        onClose={() => setIsPickerOpen(false)}
        fieldConfig={fieldConfig}
        language={language}
        seedPreset={pickerSeed}
        existingModel={pickerModel}
        onSaved={handlePickerSaved}
      />

      {/* SES mail compose modal (task 9.2, C6). Opened from the Mail button in
          the capability-gated result-actions slot; mails the CURRENT result rows
          (recipient email resolved from fieldConfig / analytics.field_roles,
          R4.12), optionally attaching the result CSV / PDF labels. BCC-by-default
          + recipient-count confirmation are enforced in the modal + backend
          (R8.4). Mounted only when there is a result so `recipients` is defined. */}
      {/* Mounted only when there is a result AND the tenant is mail-enabled (R1,
          task 1.3): the Mail action is hidden when not enabled, so the modal can
          never open — mirroring how the labels modal mounts only when its gate
          (`canGenerateLabels`) holds. `enableTemplates` is likewise tied to the
          gate: the stored-template picker + send offer are offered only to a
          mail-enabled tenant (R0 — the compose's `enableTemplates` prop documents
          "hidden when the tenant is not mail-enabled per R0"). */}
      {result && mailEnabled && (
        <MemberMailCompose
          isOpen={isMailOpen}
          onClose={() => setIsMailOpen(false)}
          fieldConfig={fieldConfig}
          recipients={exportRows as MemberRow[]}
          language={language}
          buildCsvBase64={buildCsvBase64}
          buildPdfBase64={hasAddressMapping ? buildPdfBase64 : undefined}
          enableTemplates={mailEnabled}
        />
      )}

      {/* Delivery editor modal (task 3.4 / R3). Opened from the "Delivery"
          lifecycle action on a selected saved set; edits the set's optional
          stored delivery block and persists via the dedicated PUT/DELETE delivery
          route (never the create/update set body). Mounted only once a set has
          been resolved (`deliverySet` set by handleDelivery). */}
      {deliverySet && (
        <MemberDeliveryEditor
          isOpen={isDeliveryOpen}
          onClose={() => setIsDeliveryOpen(false)}
          setId={deliverySet.id}
          setName={deliverySet.name}
          initialDelivery={deliverySet.delivery}
          language={language}
          onSave={handleDeliverySave}
          onClear={handleDeliveryClear}
        />
      )}

      {/* Schedule editor modal (task 5.4 / R5). Opened from the "Schedule"
          lifecycle action on a selected saved set that HAS a delivery block;
          creates/updates/deletes the set's recurring run via the dedicated
          schedule route (POST/PUT/DELETE /members/schedules). Mounted only once a
          set has been resolved (`scheduleSet` set by handleSchedule). */}
      {scheduleSet && (
        <MemberScheduleEditor
          isOpen={isScheduleOpen}
          onClose={() => setIsScheduleOpen(false)}
          setName={scheduleSet.name}
          hasDelivery={scheduleSet.hasDelivery}
          initialSchedule={scheduleSet.schedule}
          onCreate={handleScheduleCreate}
          onUpdate={handleScheduleUpdate}
          onDelete={handleScheduleDelete}
        />
      )}

      {/* Address-label generate modal (labels sub-spec task 3.2 / R-L2/R-L3/R-L4).
          Hosts the TEMPLATE-DRIVEN MemberLabelsPanel: the user picks a stored
          `kind:"label"` template + an Avery format, tunes the ONE shared
          LabelStyleOptions (R-L5 — font, alignment, border, start position,
          shrink-to-fit), and Generates. The panel composes the CURRENT result
          rows (`exportRows`, the table's post-filter visible rows — R2/R3)
          through the template via `generateLabelTemplatePdf`, which uses
          `composeLabelLines` (NOT `composeAddresses`/`resolveAddressMapping`) and
          reads NO `analytics.*` (R6 / Property 4), then downloads/prints the PDF
          (R-L4). The `labelTemplates` list (loaded for the gate) is passed in so
          no extra fetch is needed — the list DTO already carries each template's
          `lines`.

          The availability GATE (members:export + ≥1 label template =
          `canGenerateLabels`) decides whether the action is reachable: the modal
          mounts only when the gate holds, so a caller without export (or a tenant
          with no label template) can never open it. */}
      {result && canGenerateLabels && (
        <Modal
          isOpen={isLabelsOpen}
          onClose={() => setIsLabelsOpen(false)}
          size="2xl"
          isCentered
          scrollBehavior="inside"
        >
          <ModalOverlay />
          <ModalContent bg="gray.800" color="white" data-testid="member-pivot-labels-modal">
            <ModalHeader>{t('analytics.labels.modalTitle')}</ModalHeader>
            <ModalCloseButton />
            <ModalBody pb={6}>
              <MemberLabelsPanel
                rows={exportRows as MemberRow[]}
                fieldConfig={fieldConfig ?? undefined}
                templates={labelTemplates}
                language={language}
                resultFields={(result?.columns ?? []).map((col) => ({
                  key: col.name,
                  label: columnLabels[col.name] ?? col.name,
                }))}
                onTemplatesChanged={reloadLabelTemplates}
              />
            </ModalBody>
          </ModalContent>
        </Modal>
      )}

      {/* Delete confirmation (task 7.5 / R4.4b) — deleting a saved set is an
          explicit, confirmed action, never implicit. Bilingual, keyboard-
          accessible (AlertDialog traps focus; the Cancel button is the initial
          focus). */}
      <AlertDialog
        isOpen={pendingDelete !== null}
        leastDestructiveRef={cancelDeleteRef}
        onClose={() => setPendingDelete(null)}
        isCentered
      >
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800" color="white" data-testid="member-pivot-delete-dialog">
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              {t('analytics.pivotViews.lifecycle.confirmDeleteTitle')}
            </AlertDialogHeader>
            <AlertDialogBody>
              {t('analytics.pivotViews.lifecycle.confirmDelete', {
                name: pendingDelete?.name ?? '',
              })}
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button
                ref={cancelDeleteRef}
                variant="ghost"
                onClick={() => setPendingDelete(null)}
                data-testid="member-pivot-delete-cancel"
              >
                {t('analytics.pivotViews.lifecycle.confirmDeleteCancel')}
              </Button>
              <Button
                colorScheme="red"
                ml={3}
                onClick={handleConfirmDelete}
                isLoading={isDeleting}
                data-testid="member-pivot-delete-confirm"
              >
                {t('analytics.pivotViews.lifecycle.confirmDeleteConfirm')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>

      {/* Send CSV by email (Export-CSV menu, C5): collect fixed address(es) + confirm, then
          mail the current result as a CSV attachment via the SAM to_fixed path. */}
      <AlertDialog
        isOpen={isCsvMailOpen}
        leastDestructiveRef={csvMailCancelRef}
        onClose={() => !csvMailSending && setIsCsvMailOpen(false)}
        isCentered
      >
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800" color="white" data-testid="member-pivot-csv-mail-dialog">
            <AlertDialogHeader>{t('analytics.export.csvMail.title')}</AlertDialogHeader>
            <AlertDialogBody>
              <Text fontSize="sm" color="gray.300" mb={3}>
                {t('analytics.export.csvMail.summary', { count: exportRows.length })}
              </Text>
              <FormControl isInvalid={csvMailTo.trim() !== '' && !csvMailValid}>
                <FormLabel htmlFor="member-pivot-csv-mail-to">
                  {t('analytics.export.csvMail.toLabel')}
                </FormLabel>
                <Input
                  id="member-pivot-csv-mail-to"
                  data-testid="member-pivot-csv-mail-to"
                  value={csvMailTo}
                  onChange={(e) => setCsvMailTo(e.target.value)}
                  placeholder={t('analytics.export.csvMail.toPlaceholder')}
                  bg="gray.900"
                  color="white"
                />
              </FormControl>
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button
                ref={csvMailCancelRef}
                variant="ghost"
                onClick={() => setIsCsvMailOpen(false)}
                isDisabled={csvMailSending}
                data-testid="member-pivot-csv-mail-cancel"
              >
                {t('analytics.pivotViews.lifecycle.confirmDeleteCancel')}
              </Button>
              <Button
                colorScheme="orange"
                ml={3}
                onClick={handleSendCsvMail}
                isDisabled={!csvMailValid}
                isLoading={csvMailSending}
                data-testid="member-pivot-csv-mail-send"
              >
                {t('analytics.export.csvMail.send')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>

      {/* Deliver now — CONFIRM before an irreversible send (redesign Q3 safety).
          Deliver now mails the on-screen result to the set's stored fixed
          recipients; the confirm turns "fired blind" into a seen, deliberate
          action. On confirm it runs the same handleDeliverNow (which reads the
          stored recipients + sends the current result via the ad-hoc path). */}
      <AlertDialog
        isOpen={isDeliverNowConfirmOpen}
        leastDestructiveRef={deliverNowCancelRef}
        onClose={() => !isDeliveringNow && setIsDeliverNowConfirmOpen(false)}
        isCentered
      >
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800" color="white" data-testid="member-pivot-deliver-now-dialog">
            <AlertDialogHeader>{t('analytics.delivery.deliverNowConfirmTitle')}</AlertDialogHeader>
            <AlertDialogBody>
              <Text fontSize="sm" color="gray.300">
                {t('analytics.delivery.deliverNowConfirmBody', {
                  name: selectedModelSummary?.name ?? '',
                  count: exportRows.length,
                })}
              </Text>
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button
                ref={deliverNowCancelRef}
                variant="ghost"
                onClick={() => setIsDeliverNowConfirmOpen(false)}
                isDisabled={isDeliveringNow}
                data-testid="member-pivot-deliver-now-cancel"
              >
                {t('analytics.pivotViews.lifecycle.confirmDeleteCancel')}
              </Button>
              <Button
                colorScheme="orange"
                ml={3}
                onClick={() => {
                  setIsDeliverNowConfirmOpen(false);
                  void handleDeliverNow();
                }}
                isLoading={isDeliveringNow}
                data-testid="member-pivot-deliver-now-confirm"
              >
                {t('analytics.delivery.deliverNowConfirmSend')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
};

export default MemberPivotViews;

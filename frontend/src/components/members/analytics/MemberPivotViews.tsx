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
 * `PivotResultTable` (REUSE — no bespoke result table, R4.7). A "set" is a
 * **saved member set** (R4.6 / R5.2) — a tenant-saved analytics set from the
 * Members API `listAnalyticsSets()`. The Members Lambda returns ONLY this
 * tenant's member sets, so no client-side data-source filter is needed (another
 * module's sets can never leak into the member surface). There are no predefined
 * presets: every view is one the user built generically (group/filter on field
 * names directly) and saved.
 *
 * Selecting a set does NOT run anything — running is an EXPLICIT action (R1.6):
 * the user picks a set, then clicks Execute, and only then is
 * `executeMemberPivot(processedData, config, fieldConfig)` (task 7.1, the client
 * adapter) called and its `PivotResult` rendered. Nothing is pivoted/listed on
 * open, and nothing auto-runs on selection (R1.6 — no auto-run).
 *
 * Resolving the chosen set's `PivotConfig`: a saved set carries only summary
 * metadata in the list, so its full definition is fetched on Execute via
 * `getAnalyticsSet(id)` (which converts the module's snake_case definition into a
 * camelCase `PivotConfig`). The saved set's own definition filters travel with it
 * (R4.4); the page's live filter is NOT baked in (R4.4a) — the adapter runs over
 * `processedData` as-is.
 *
 * Exports mount into the capability-gated, test-visible `pivot-result-actions`
 * slot (gated by `capabilities.canExport` = members:export). Within the slot the
 * Mail action carries an ADDITIONAL tenant gate (pivot-output-actions R0/R1 task
 * 1.3): the compose/send path is OFFERED only when the tenant is mail-enabled —
 * the R0 `config#mail` flag surfaced on the field config as `mail_enabled`;
 * otherwise the action is HIDDEN with the shared degradation reason (mirroring how
 * the labels action degrades when the tenant has no label template). Task 8.1 wires CSV
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
  Box,
  Button,
  FormControl,
  FormLabel,
  HStack,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  Select,
  Tooltip,
  VStack,
  useToast,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import type { PivotConfig, PivotResult } from '../../../types/pivot';
import type {
  MemberAnalyticsSetSummary,
  MemberDelivery,
  MemberSchedule,
  MemberScheduleCadence,
} from '../../../types/members';
import {
  getAnalyticsSet,
  deleteAnalyticsSet,
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
import { executeMemberPivot } from './memberPivotAdapter';
import { useTenant } from '../../../context/TenantContext';
import { recordAnalyticsOutput } from '../../../services/memberAnalyticsAuditService';
import {
  type ExistingPivotModel,
  type PivotSeed,
} from './MemberFieldPicker';
import {
  listMemberTemplates as realListMemberTemplates,
  type MemberTemplateDto,
} from '../../../services/memberTemplateService';
import AnalyticsStateNotice from './areas/AnalyticsStateNotice';
import { applyDefinitionFilters } from './analyticsConfig';
import MemberPivotResultActions from './MemberPivotResultActions';
import MemberPivotModals from './MemberPivotModals';
import { useMemberPivotExport } from './useMemberPivotExport';
import { useMemberSetLibrary } from './useMemberSetLibrary';
import {
  type SelectableSet,
  MODEL_PREFIX,
  resolveConfig,
} from './memberPivotViewsHelpers';

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
  // The active tenant's name feeds the shared export filename rule
  // (`{Tenant}-{Pivot}.csv`), same source as the Members Overview page.
  const { currentTenant } = useTenant();

  // The saved-set + preferred-list LIBRARY bundle (saved member sets, the
  // per-user preferred ref list, and the dropdown / library derivations +
  // mutations) lives in a cohesive hook (code-quality split task 5) — same
  // inputs, zero behaviour change. `savedModels` + `refreshSavedModels` feed the
  // selection/lifecycle logic that stays here.
  const {
    savedModels,
    refreshSavedModels,
    sets,
    dropdownSets,
    libraryFilter,
    setLibraryFilter,
    filteredLibraryItems,
    isSavingPreferred,
    handleAddRef,
    handleRemovePreferred,
  } = useMemberSetLibrary(t);

  // The tenant's LABEL templates (`kind:"label"`), loaded once on mount (labels
  // sub-spec R-L2, task 3.1). Their mere EXISTENCE (≥1) gates the "Generate
  // address labels" action — see `hasLabelTemplate` / `canGenerateLabels` below.
  // FAIL-CLOSED: a non-ok result or a throw leaves this empty, so the action is
  // simply hidden with the bilingual degradation reason — never a crash.
  const [labelTemplates, setLabelTemplates] = useState<MemberTemplateDto[]>([]);

  // The currently SELECTED option value — selection alone runs nothing (R1.6).
  const [selectedValue, setSelectedValue] = useState<string>('');

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
  const [pickerSeed, setPickerSeed] = useState<PivotSeed | undefined>(undefined);

  // Delete confirmation (explicit, never implicit — R4.4b). Holds the summary of
  // the set pending deletion, or null when no confirmation is open.
  const [pendingDelete, setPendingDelete] = useState<MemberAnalyticsSetSummary | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const cancelDeleteRef = useRef<HTMLButtonElement>(null);

  // --- Mail compose state (task 9.2). ----------------------------------------
  // The SES mail compose modal is opened from the Mail button in the
  // capability-gated `pivot-result-actions` slot (beside the CSV button). It
  // mails the CURRENT result rows.
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

  const selectedSet = useMemo(
    () => sets.find((s) => s.optionValue === selectedValue),
    [sets, selectedValue],
  );

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
  // A preferred/library Run and the Execute button both run the set's own saved
  // config (incl. its saved generic definition filters, issue 3).
  const executeSet = useCallback(
    async (set: SelectableSet) => {
      setIsExecuting(true);
      try {
        const config = await resolveConfig(set);
        if (!config) {
          return;
        }

        // The client adapter aggregates/lists its input rows as-is and does not
        // itself apply `config.filters`, so every saved equality definition
        // filter (e.g. {clubblad:'Papier'}, issue 3) is applied HERE via
        // applyDefinitionFilters, narrowing the page's own filtered dataset
        // (R4.4a — the page's live filter is NOT re-baked; we run over
        // processedData as-is). A jubilee / new-member list is reached by the
        // user filtering the calculated years-member / joined_date field in the
        // generic set definition — no dedicated selector machinery.
        const rows = applyDefinitionFilters(
          processedData,
          config.filters,
          fieldConfig ?? undefined,
        );

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
  // It runs the currently-SELECTED set.
  const handleExecute = useCallback(() => {
    if (!selectedSet) {
      return;
    }
    void executeSet(selectedSet);
  }, [selectedSet, executeSet]);

  // The currently-selected saved set's summary (undefined for a preset or when
  // nothing is selected) — gates the Update / Delete actions, which apply only to
  // a tenant-saved member set.
  const selectedModelSummary = useMemo<MemberAnalyticsSetSummary | undefined>(() => {
    if (selectedSet?.source !== 'model' || typeof selectedSet.modelId !== 'string') {
      return undefined;
    }
    return savedModels.find((m) => m.id === selectedSet.modelId);
  }, [selectedSet, savedModels]);

  // The produced-result EXPORT bundle (column-header label map, export rows, CSV
  // download + "send CSV by email" dialog, the base64 CSV builder, and the
  // labels/mail content gates) lives in a cohesive hook (code-quality split task
  // 5) — same inputs, zero behaviour change. `visibleRows` (reported by the
  // result table) feeds `exportRows` so every export honors the in-table filters.
  const {
    columnLabels,
    exportRows,
    mailEnabled,
    canGenerateLabels,
    buildCsvBase64,
    handleExportCsv,
    isCsvMailOpen,
    setIsCsvMailOpen,
    csvMailTo,
    setCsvMailTo,
    csvMailSending,
    csvMailValid,
    csvMailCancelRef,
    handleOpenCsvMail,
    handleSendCsvMail,
  } = useMemberPivotExport({
    result,
    resultConfig,
    selectedSet,
    fieldConfig,
    language,
    capabilities,
    labelTemplates,
    currentTenant,
    visibleRows,
    t,
  });

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
    if (!selectedSet || typeof selectedSet.modelId !== 'string') {
      return;
    }
    const saved = await getAnalyticsSet(selectedSet.modelId);
    setPickerModel(undefined);
    setPickerSeed({ config: saved.definition, name: saved.name });
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

  return (
    <Box data-testid="member-pivot-views">
      <VStack align="stretch" spacing={4}>
        <HStack align="flex-end" spacing={3}>
          <FormControl maxW="sm">
            <FormLabel htmlFor="member-pivot-set-select" color="gray.300" fontSize="sm" mb={1}>
              {t('analytics.pivotViews.selectSet')}
            </FormLabel>
            {/* The dropdown lists ONLY the user's preferred saved sets (in saved
                order). There are no predefined presets — every view is one the
                user built generically and saved. The full library is behind the
                "All sets" button beside it. */}
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

        {/* Empty Pivot Views entry point (bugfix §3). With the preset subsystem
            removed, a tenant with NO saved sets would otherwise see an empty
            dropdown and no obvious next step. Instead of a dead control, reuse
            the shared AnalyticsStateNotice in its EMPTY variant to explain that
            the user builds a view by picking fields to group/filter, with the
            existing MemberFieldPicker "New set" button as the single CTA (gated
            on the same create permission the Manage-set menu uses). Composed from
            existing building blocks only — no new component (steering 32/37). */}
        {sets.length === 0 && (
          <Box data-testid="member-pivot-empty-hint">
            <AnalyticsStateNotice
              kind="empty"
              message={t('analytics.pivotViews.emptyHint.message')}
              testId="member-pivot-empty-hint-notice"
            />
            {canManageSets && (
              <Button
                mt={3}
                colorScheme="orange"
                onClick={handleNewSet}
                data-testid="member-pivot-empty-hint-new-set"
              >
                {t('analytics.pivotViews.newSet')}
              </Button>
            )}
          </Box>
        )}

        {/* The produced result (REUSE PivotResultTable, R4.7) + the
            capability-gated export-actions slot. Rendered only AFTER an explicit
            Execute — null until then (R1.6). Extracted into a sibling
            presentational component (code-quality split task 4); all state +
            handlers stay here, so behaviour is unchanged. */}
        {result && resultConfig && (
          <MemberPivotResultActions
            result={result}
            resultConfig={resultConfig}
            isExecuting={isExecuting}
            onVisibleRowsChange={setVisibleRows}
            columnLabels={columnLabels}
            capabilities={capabilities}
            mailEnabled={mailEnabled}
            canGenerateLabels={canGenerateLabels}
            onExportCsv={handleExportCsv}
            onOpenCsvMail={handleOpenCsvMail}
            onOpenMail={() => setIsMailOpen(true)}
            onOpenLabels={() => setIsLabelsOpen(true)}
            t={t}
          />
        )}
      </VStack>

      {/* The Pivot Views modal / dialog cluster — library browser, mail-status,
          field picker, mail compose, delivery / schedule editors, address-labels,
          and the delete / csv-mail / deliver-now confirmations. Extracted into a
          sibling presentational component (code-quality split task 5); all state
          + handlers stay here, so every mount gate, testid, and i18n key is
          unchanged. */}
      <MemberPivotModals
        fieldConfig={fieldConfig}
        language={language}
        capabilities={capabilities}
        t={t}
        result={result}
        columnLabels={columnLabels}
        exportRows={exportRows}
        mailEnabled={mailEnabled}
        canGenerateLabels={canGenerateLabels}
        labelTemplates={labelTemplates}
        buildCsvBase64={buildCsvBase64}
        onReloadLabelTemplates={reloadLabelTemplates}
        isLibraryOpen={isLibraryOpen}
        onLibraryClose={() => setIsLibraryOpen(false)}
        libraryFilter={libraryFilter}
        onLibraryFilterChange={setLibraryFilter}
        filteredLibraryItems={filteredLibraryItems}
        canManageSets={canManageSets}
        canDeleteSets={canDeleteSets}
        isSavingPreferred={isSavingPreferred}
        onAddRef={handleAddRef}
        onRemovePreferred={handleRemovePreferred}
        onRequestDelete={({ id, name }) =>
          setPendingDelete({ id, name, kind: 'count' })
        }
        isMailStatusOpen={isMailStatusOpen}
        onMailStatusClose={() => setIsMailStatusOpen(false)}
        isPickerOpen={isPickerOpen}
        onPickerClose={() => setIsPickerOpen(false)}
        pickerSeed={pickerSeed}
        pickerModel={pickerModel}
        onPickerSaved={handlePickerSaved}
        isMailOpen={isMailOpen}
        onMailClose={() => setIsMailOpen(false)}
        isLabelsOpen={isLabelsOpen}
        onLabelsClose={() => setIsLabelsOpen(false)}
        deliverySet={deliverySet}
        isDeliveryOpen={isDeliveryOpen}
        onDeliveryClose={() => setIsDeliveryOpen(false)}
        onDeliverySave={handleDeliverySave}
        onDeliveryClear={handleDeliveryClear}
        scheduleSet={scheduleSet}
        isScheduleOpen={isScheduleOpen}
        onScheduleClose={() => setIsScheduleOpen(false)}
        onScheduleCreate={handleScheduleCreate}
        onScheduleUpdate={handleScheduleUpdate}
        onScheduleDelete={handleScheduleDelete}
        pendingDelete={pendingDelete}
        isDeleting={isDeleting}
        cancelDeleteRef={cancelDeleteRef}
        onDeleteCancel={() => setPendingDelete(null)}
        onConfirmDelete={handleConfirmDelete}
        isCsvMailOpen={isCsvMailOpen}
        onCsvMailClose={() => {
          if (!csvMailSending) {
            setIsCsvMailOpen(false);
          }
        }}
        csvMailTo={csvMailTo}
        onCsvMailToChange={setCsvMailTo}
        csvMailValid={csvMailValid}
        csvMailSending={csvMailSending}
        csvMailCancelRef={csvMailCancelRef}
        onSendCsvMail={handleSendCsvMail}
        selectedModelSummary={selectedModelSummary}
        isDeliverNowConfirmOpen={isDeliverNowConfirmOpen}
        onDeliverNowConfirmClose={() => {
          if (!isDeliveringNow) {
            setIsDeliverNowConfirmOpen(false);
          }
        }}
        isDeliveringNow={isDeliveringNow}
        deliverNowCancelRef={deliverNowCancelRef}
        onDeliverNowConfirm={() => {
          setIsDeliverNowConfirmOpen(false);
          void handleDeliverNow();
        }}
      />

    </Box>
  );
};

export default MemberPivotViews;

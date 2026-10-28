/**
 * MemberPivotModals — the trailing modal / dialog cluster of the Pivot Views
 * panel (library browser, mail-status, field picker, mail compose, delivery
 * editor, schedule editor, address-labels, and the delete / csv-mail /
 * deliver-now confirmation dialogs).
 *
 * Extracted verbatim from `MemberPivotViews.tsx` (code-quality split 2026-10-28,
 * task 5) with ZERO behaviour change: this is a pure presentational component
 * driven entirely by props — every mount gate, every testid, and every i18n key
 * is identical to the inline block it replaces. All state and handlers stay in
 * the parent; this component only renders them. Each child modal is imported via
 * the SAME relative specifier the parent used so the component test's module
 * mocks still intercept them unchanged.
 *
 * @module components/members/analytics/MemberPivotModals
 */

import React from 'react';
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Button,
  FormControl,
  FormLabel,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalHeader,
  ModalOverlay,
  Text,
} from '@chakra-ui/react';
import type { PivotConfig, PivotResult } from '../../../types/pivot';
import type {
  FieldConfig,
  MemberRow,
  MemberAnalyticsSetSummary,
  MemberDelivery,
  MemberSchedule,
  MemberScheduleCadence,
} from '../../../types/members';
import type { MemberAnalyticsCapabilities } from './areas/types';
import MemberFieldPicker, {
  type ExistingPivotModel,
  type PivotSeed,
} from './MemberFieldPicker';
import MemberMailCompose from './MemberMailCompose';
import MemberMailStatus from './MemberMailStatus';
import MemberDeliveryEditor from './MemberDeliveryEditor';
import MemberScheduleEditor from './MemberScheduleEditor';
import MemberLabelsPanel from './MemberLabelsPanel';
import MemberPivotLibraryModal from './MemberPivotLibraryModal';
import type { MemberTemplateDto } from '../../../services/memberTemplateService';

/**
 * The members-namespace translator, typed to its usage here: a key plus an
 * optional interpolation bag, returning a string. Matches the shape the parent's
 * `useTypedTranslation('members')` `t` provides without pulling in a brittle
 * i18next generic.
 */
type TFunction = (key: string, options?: Record<string, unknown>) => string;

/** A resolved library row (as the parent builds it for the library modal). */
interface LibraryItem {
  optionValue: string;
  label: string;
  ref: string | null;
  alreadyPreferred: boolean;
  savedSetId: string | null;
}

export interface MemberPivotModalsProps {
  // --- Shared context ------------------------------------------------------
  fieldConfig: FieldConfig | null;
  language: string;
  capabilities: MemberAnalyticsCapabilities;
  t: TFunction;

  // The produced result + its config (drives the labels / compose / csv dialogs).
  result: PivotResult | null;
  columnLabels: Record<string, string>;
  exportRows: Record<string, unknown>[];
  mailEnabled: boolean;
  canGenerateLabels: boolean;
  labelTemplates: MemberTemplateDto[];
  buildCsvBase64: () => string | null;
  onReloadLabelTemplates: () => void;

  // --- Library modal -------------------------------------------------------
  isLibraryOpen: boolean;
  onLibraryClose: () => void;
  libraryFilter: string;
  onLibraryFilterChange: (value: string) => void;
  filteredLibraryItems: LibraryItem[];
  canManageSets: boolean;
  canDeleteSets: boolean;
  isSavingPreferred: boolean;
  onAddRef: (ref: string | null) => void;
  onRemovePreferred: (ref: string) => void;
  onRequestDelete: (args: { id: string; name: string }) => void;

  // --- Mail status modal ---------------------------------------------------
  isMailStatusOpen: boolean;
  onMailStatusClose: () => void;

  // --- Field picker (new / save-as / update) -------------------------------
  isPickerOpen: boolean;
  onPickerClose: () => void;
  pickerSeed: PivotSeed | undefined;
  pickerModel: ExistingPivotModel | undefined;
  onPickerSaved: (config: PivotConfig, name: string, modelId?: string) => void;

  // --- SES mail compose ----------------------------------------------------
  isMailOpen: boolean;
  onMailClose: () => void;

  // --- Labels modal --------------------------------------------------------
  isLabelsOpen: boolean;
  onLabelsClose: () => void;

  // --- Delivery editor -----------------------------------------------------
  deliverySet: { id: string; name: string; delivery?: MemberDelivery } | null;
  isDeliveryOpen: boolean;
  onDeliveryClose: () => void;
  onDeliverySave: (delivery: MemberDelivery) => Promise<void>;
  onDeliveryClear: () => Promise<void>;

  // --- Schedule editor -----------------------------------------------------
  scheduleSet: {
    id: string;
    name: string;
    hasDelivery: boolean;
    schedule?: MemberSchedule;
  } | null;
  isScheduleOpen: boolean;
  onScheduleClose: () => void;
  onScheduleCreate: (cadence: MemberScheduleCadence, enabled: boolean) => Promise<void>;
  onScheduleUpdate: (cadence: MemberScheduleCadence, enabled: boolean) => Promise<void>;
  onScheduleDelete: () => Promise<void>;

  // --- Delete confirmation -------------------------------------------------
  pendingDelete: MemberAnalyticsSetSummary | null;
  isDeleting: boolean;
  cancelDeleteRef: React.RefObject<HTMLButtonElement | null>;
  onDeleteCancel: () => void;
  onConfirmDelete: () => void;

  // --- Send CSV by email dialog --------------------------------------------
  isCsvMailOpen: boolean;
  onCsvMailClose: () => void;
  csvMailTo: string;
  onCsvMailToChange: (value: string) => void;
  csvMailValid: boolean;
  csvMailSending: boolean;
  csvMailCancelRef: React.RefObject<HTMLButtonElement | null>;
  onSendCsvMail: () => void;

  // --- Deliver now confirmation --------------------------------------------
  selectedModelSummary: MemberAnalyticsSetSummary | undefined;
  isDeliverNowConfirmOpen: boolean;
  onDeliverNowConfirmClose: () => void;
  isDeliveringNow: boolean;
  deliverNowCancelRef: React.RefObject<HTMLButtonElement | null>;
  onDeliverNowConfirm: () => void;
}

/**
 * The Pivot Views modal / dialog cluster. Rendered as a sibling of the main
 * panel body; mounting of each individual modal is gated exactly as it was
 * inline (so behaviour, testids, and i18n keys are unchanged).
 */
const MemberPivotModals: React.FC<MemberPivotModalsProps> = ({
  fieldConfig,
  language,
  capabilities,
  t,
  result,
  columnLabels,
  exportRows,
  mailEnabled,
  canGenerateLabels,
  labelTemplates,
  buildCsvBase64,
  onReloadLabelTemplates,
  isLibraryOpen,
  onLibraryClose,
  libraryFilter,
  onLibraryFilterChange,
  filteredLibraryItems,
  canManageSets,
  canDeleteSets,
  isSavingPreferred,
  onAddRef,
  onRemovePreferred,
  onRequestDelete,
  isMailStatusOpen,
  onMailStatusClose,
  isPickerOpen,
  onPickerClose,
  pickerSeed,
  pickerModel,
  onPickerSaved,
  isMailOpen,
  onMailClose,
  isLabelsOpen,
  onLabelsClose,
  deliverySet,
  isDeliveryOpen,
  onDeliveryClose,
  onDeliverySave,
  onDeliveryClear,
  scheduleSet,
  isScheduleOpen,
  onScheduleClose,
  onScheduleCreate,
  onScheduleUpdate,
  onScheduleDelete,
  pendingDelete,
  isDeleting,
  cancelDeleteRef,
  onDeleteCancel,
  onConfirmDelete,
  isCsvMailOpen,
  onCsvMailClose,
  csvMailTo,
  onCsvMailToChange,
  csvMailValid,
  csvMailSending,
  csvMailCancelRef,
  onSendCsvMail,
  selectedModelSummary,
  isDeliverNowConfirmOpen,
  onDeliverNowConfirmClose,
  isDeliveringNow,
  deliverNowCancelRef,
  onDeliverNowConfirm,
}) => {
  return (
    <>
      {/* "All sets" library modal — the single management surface for the pivot
          library (keeps the main pane clean). Two lists:
            1. MY PREFERRED LIST: the user's per-user ordered shortlist (also what
               the main dropdown offers). Each item Runs immediately, reorders
               (up/down), and removes. Name filter preserves the saved order.
            2. FULL LIBRARY: every preset + saved set, ALPHABETICALLY sorted, name
               filter, Run + "Add to my list" (disabled / "already added").
          Add/remove/reorder + add are gated on members:export|write; a read-only
          caller sees both lists read-only (Run only). */}
      <MemberPivotLibraryModal
        isOpen={isLibraryOpen}
        onClose={onLibraryClose}
        libraryFilter={libraryFilter}
        onLibraryFilterChange={onLibraryFilterChange}
        filteredLibraryItems={filteredLibraryItems}
        canManageSets={canManageSets}
        canDeleteSets={canDeleteSets}
        isSavingPreferred={isSavingPreferred}
        onAddRef={onAddRef}
        onRemovePreferred={onRemovePreferred}
        onRequestDelete={onRequestDelete}
        t={t}
      />

      {/* Mail status / history modal (mail-spec task 3.3 / R9). Hosts the
          MemberMailStatus screen: a role-scoped list of send-runs + per-run
          FAILURE drill-down (R9.2), with honest "sent = SES accepted, not
          delivered" labelling (R9.4). Mounted only when its members:export entry
          point is offered; the screen loads the run list on open. */}
      {capabilities.canExport && (
        <Modal
          isOpen={isMailStatusOpen}
          onClose={onMailStatusClose}
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
        onClose={onPickerClose}
        fieldConfig={fieldConfig}
        language={language}
        seedPreset={pickerSeed}
        existingModel={pickerModel}
        onSaved={onPickerSaved}
      />

      {/* SES mail compose modal (task 9.2, C6). Opened from the Mail button in
          the capability-gated result-actions slot; mails the CURRENT result rows
          (recipient email resolved from the field config, R4.12), optionally
          attaching the result CSV. BCC-by-default
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
          onClose={onMailClose}
          fieldConfig={fieldConfig}
          recipients={exportRows as MemberRow[]}
          language={language}
          buildCsvBase64={buildCsvBase64}
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
          onClose={onDeliveryClose}
          setId={deliverySet.id}
          setName={deliverySet.name}
          initialDelivery={deliverySet.delivery}
          language={language}
          onSave={onDeliverySave}
          onClear={onDeliveryClear}
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
          onClose={onScheduleClose}
          setName={scheduleSet.name}
          hasDelivery={scheduleSet.hasDelivery}
          initialSchedule={scheduleSet.schedule}
          onCreate={onScheduleCreate}
          onUpdate={onScheduleUpdate}
          onDelete={onScheduleDelete}
        />
      )}

      {/* Address-label generate modal (labels sub-spec task 3.2 / R-L2/R-L3/R-L4).
          Hosts the TEMPLATE-DRIVEN MemberLabelsPanel: the user picks a stored
          `kind:"label"` template + an Avery format, tunes the ONE shared
          LabelStyleOptions (R-L5 — font, alignment, border, start position,
          shrink-to-fit), and Generates. The panel composes the CURRENT result
          rows (`exportRows`, the table's post-filter visible rows — R2/R3)
          through the template via `generateLabelTemplatePdf`, which uses
          `composeLabelLines` and reads NO `analytics.*` (R6 / Property 4), then downloads/prints the PDF
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
          onClose={onLabelsClose}
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
                onTemplatesChanged={onReloadLabelTemplates}
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
        onClose={onDeleteCancel}
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
                onClick={onDeleteCancel}
                data-testid="member-pivot-delete-cancel"
              >
                {t('analytics.pivotViews.lifecycle.confirmDeleteCancel')}
              </Button>
              <Button
                colorScheme="red"
                ml={3}
                onClick={onConfirmDelete}
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
        onClose={onCsvMailClose}
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
                  onChange={(e) => onCsvMailToChange(e.target.value)}
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
                onClick={onCsvMailClose}
                isDisabled={csvMailSending}
                data-testid="member-pivot-csv-mail-cancel"
              >
                {t('analytics.pivotViews.lifecycle.confirmDeleteCancel')}
              </Button>
              <Button
                colorScheme="orange"
                ml={3}
                onClick={onSendCsvMail}
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
        onClose={onDeliverNowConfirmClose}
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
                onClick={onDeliverNowConfirmClose}
                isDisabled={isDeliveringNow}
                data-testid="member-pivot-deliver-now-cancel"
              >
                {t('analytics.pivotViews.lifecycle.confirmDeleteCancel')}
              </Button>
              <Button
                colorScheme="orange"
                ml={3}
                onClick={onDeliverNowConfirm}
                isLoading={isDeliveringNow}
                data-testid="member-pivot-deliver-now-confirm"
              >
                {t('analytics.delivery.deliverNowConfirmSend')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </>
  );
};

export default MemberPivotModals;

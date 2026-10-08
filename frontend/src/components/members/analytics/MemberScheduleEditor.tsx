/**
 * MemberScheduleEditor — attach/manage a recurring schedule on a saved set that
 * HAS a delivery block (pivot-output-actions R5, design §2.3 / §3 / §5, task 5.4).
 *
 * A keyboard-accessible Chakra modal, opened from the "Schedule" lifecycle action
 * beside Delivery on a SELECTED saved set in {@link MemberPivotViews}. It creates,
 * edits, enables/disables, and deletes the ONE schedule that reruns the set's
 * stored delivery on a cadence (R5). It does NOT run anything itself — the
 * EventBridge Scheduler fires each schedule and reuses the R4 execute-and-deliver
 * path (tasks 5.2/5.3, built concurrently).
 *
 * A schedule can ONLY be attached to a set that already has a `delivery` block
 * (R5): the parent gates the Schedule ACTION on the set's delivery (and hides it
 * when scheduling is not allowed for the caller), so this editor is only ever
 * mounted for a schedulable set. It still shows a clear reason if opened without
 * a delivery (defence in depth).
 *
 * What it edits (design §5):
 *   - **cadence** — a FRIENDLY picker (monthly / weekly); never a raw cron. The
 *     cadence maps to the backend cron via `membersApiService.cadenceToCron` on
 *     save, and an existing schedule's cron maps back via `cronToCadence` to seed
 *     the picker.
 *   - **enabled** — an enable/disable toggle; a disabled schedule is kept but does
 *     not fire.
 *
 * Persistence (design §3, route `GET/POST/PUT/DELETE /members/schedules[/{id}]`):
 * Save → `createSchedule` (POST) for a new schedule, or `updateSchedule` (PUT)
 * for an existing one; Delete → `deleteSchedule` (DELETE). These are injected via
 * props so the parent binds them to the set/schedule id (and tests stub them).
 *
 * The R5 ACCESS gate (`members:admin` OR `members:write` + all-regions) is the
 * backend's authority; the parent additionally hides/disables the Schedule action
 * client-side so a region-narrowed write user is never offered a dead action.
 *
 * No hardcoded English: every label resolves from the `members` namespace
 * (`analytics.schedule.*`), bilingual via the active language. Native
 * `<select>`/`<input>` controls are keyboard-navigable.
 *
 * @module components/members/analytics/MemberScheduleEditor
 * @see .kiro/specs/Members/pivot-output-actions (requirements R5; design §2.3, §3, §5)
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  Button,
  FormControl,
  FormLabel,
  HStack,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Select,
  Switch,
  Text,
  VStack,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import type { MemberSchedule, MemberScheduleCadence } from '../../../types/members';
import {
  SCHEDULE_CADENCES,
  cronToCadence,
} from '../../../services/membersApiService';

/** `members`-namespace i18n key prefix for every label this modal renders. */
const T = 'analytics.schedule';

export interface MemberScheduleEditorProps {
  /** Whether the modal is open. */
  isOpen: boolean;
  /** Close handler (overlay / Escape / Cancel). */
  onClose: () => void;
  /** The saved set's name (shown in the header for context). */
  setName: string;
  /**
   * Whether the set has a stored `delivery` block. A schedule can ONLY be
   * attached to a set that has one (R5); the parent gates the action on this, but
   * the editor also refuses to save (and shows a reason) if it is `false`.
   */
  hasDelivery: boolean;
  /**
   * The set's EXISTING schedule, or `undefined` when the set has none yet. When
   * present the editor seeds its cadence/enabled from it and Save PUTs; when
   * absent Save POSTs a new schedule.
   */
  initialSchedule?: MemberSchedule;
  /**
   * Create a new schedule (POST). Resolves on success; rejects on failure (the
   * modal surfaces an error and stays open). Injected by the parent bound to the
   * set id; stubbed in tests.
   */
  onCreate: (cadence: MemberScheduleCadence, enabled: boolean) => Promise<void>;
  /**
   * Update the existing schedule (PUT). Resolves on success; rejects on failure.
   * Injected by the parent bound to the schedule id.
   */
  onUpdate: (cadence: MemberScheduleCadence, enabled: boolean) => Promise<void>;
  /**
   * Delete the existing schedule (DELETE). Resolves on success; rejects on
   * failure. Injected by the parent bound to the schedule id.
   */
  onDelete: () => Promise<void>;
}

const MemberScheduleEditor: React.FC<MemberScheduleEditorProps> = ({
  isOpen,
  onClose,
  setName,
  hasDelivery,
  initialSchedule,
  onCreate,
  onUpdate,
  onDelete,
}) => {
  const { t } = useTypedTranslation('members');

  // --- Form state (seeded from the existing schedule, if any). ---------------
  const [cadence, setCadence] = useState<MemberScheduleCadence>('monthly');
  const [enabled, setEnabled] = useState<boolean>(true);

  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // (Re)seed the form from the existing schedule whenever the modal opens, so
  // re-opening never shows a stale draft. A new schedule defaults to monthly +
  // enabled; an existing one recovers its cadence from the stored cron (design
  // §5) and its enabled flag.
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    setError(null);
    if (initialSchedule) {
      setCadence(cronToCadence(initialSchedule.cron));
      setEnabled(initialSchedule.enabled);
    } else {
      setCadence('monthly');
      setEnabled(true);
    }
  }, [isOpen, initialSchedule]);

  const isExisting = initialSchedule !== undefined;

  const handleSave = useCallback(async () => {
    // A schedule can only be attached to a set with a delivery block (R5).
    if (!hasDelivery) {
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      if (isExisting) {
        await onUpdate(cadence, enabled);
      } else {
        await onCreate(cadence, enabled);
      }
      onClose();
    } catch {
      setError(t(`${T}.saveError`));
    } finally {
      setIsSaving(false);
    }
  }, [hasDelivery, isExisting, onUpdate, onCreate, cadence, enabled, onClose, t]);

  const handleDelete = useCallback(async () => {
    setIsDeleting(true);
    setError(null);
    try {
      await onDelete();
      onClose();
    } catch {
      setError(t(`${T}.deleteError`));
    } finally {
      setIsDeleting(false);
    }
  }, [onDelete, onClose, t]);

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="lg" isCentered scrollBehavior="inside">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white" data-testid="member-schedule-editor">
        <ModalHeader>{t(`${T}.title`, { name: setName })}</ModalHeader>
        <ModalCloseButton />
        <ModalBody pb={4}>
          <VStack align="stretch" spacing={4}>
            <Text color="gray.400" fontSize="sm" data-testid="member-schedule-intro">
              {t(`${T}.intro`)}
            </Text>

            {/* A schedule REQUIRES a delivery block (R5). If the set has none, the
                editor refuses to save and explains why (the parent normally gates
                the action, so this is defence in depth). */}
            {!hasDelivery && (
              <Text color="red.300" fontSize="sm" data-testid="member-schedule-no-delivery">
                {t(`${T}.noDelivery`)}
              </Text>
            )}

            {/* Cadence picker (friendly; maps to a cron on save — never a raw cron). */}
            <FormControl>
              <FormLabel htmlFor="schedule-cadence" color="gray.300" fontSize="sm" mb={1}>
                {t(`${T}.cadence`)}
              </FormLabel>
              <Select
                id="schedule-cadence"
                value={cadence}
                onChange={(e) => setCadence(e.target.value as MemberScheduleCadence)}
                bg="gray.700"
                color="white"
                isDisabled={!hasDelivery}
                data-testid="schedule-cadence-select"
              >
                {SCHEDULE_CADENCES.map((c) => (
                  <option key={c} value={c}>
                    {t(`${T}.cadences.${c}`)}
                  </option>
                ))}
              </Select>
              <Text color="gray.500" fontSize="xs" mt={1}>
                {t(`${T}.cadenceHint.${cadence}`)}
              </Text>
            </FormControl>

            {/* Enable/disable toggle — a disabled schedule is kept but does not fire. */}
            <FormControl display="flex" alignItems="center">
              <Switch
                id="schedule-enabled"
                isChecked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                isDisabled={!hasDelivery}
                colorScheme="orange"
                mr={3}
                data-testid="schedule-enabled-switch"
              />
              <FormLabel htmlFor="schedule-enabled" color="gray.300" fontSize="sm" mb={0}>
                {t(`${T}.enabled`)}
              </FormLabel>
            </FormControl>

            {error && (
              <Text color="red.300" fontSize="sm" data-testid="member-schedule-error">
                {error}
              </Text>
            )}
          </VStack>
        </ModalBody>
        <ModalFooter>
          {/* Delete removes the schedule (DELETE); only offered when the set
              already has one (nothing to delete otherwise). */}
          {isExisting && (
            <Button
              variant="ghost"
              colorScheme="red"
              mr="auto"
              onClick={handleDelete}
              isLoading={isDeleting}
              data-testid="member-schedule-delete"
            >
              {t(`${T}.delete`)}
            </Button>
          )}
          <HStack spacing={3}>
            <Button
              variant="ghost"
              onClick={onClose}
              data-testid="member-schedule-cancel"
            >
              {t(`${T}.cancel`)}
            </Button>
            <Button
              colorScheme="orange"
              onClick={handleSave}
              isDisabled={!hasDelivery}
              isLoading={isSaving}
              data-testid="member-schedule-save"
            >
              {t(`${T}.save`)}
            </Button>
          </HStack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default MemberScheduleEditor;

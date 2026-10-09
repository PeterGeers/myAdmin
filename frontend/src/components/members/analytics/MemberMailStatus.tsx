/**
 * MemberMailStatus — the mail SEND-STATUS / HISTORY screen (mail-spec task 3.3, R9).
 *
 * The pull-model status surface the async send model needs (R9.2/R9.6): a user
 * (or a tenant admin) opens this to see what happened to each background send —
 * queued, sent, failed — so the queue is not a black box. It is a READ-ONLY view
 * over the send-run records the enqueue + worker write (R9.1); it triggers no
 * send and mutates nothing.
 *
 * What it shows (R9.2):
 *   - a LIST of runs, newest first, each a one-line outcome: the mode + the
 *     recipient count + the tally "198 sent, 2 failed" + the lifecycle status
 *     (queued / sending / completed);
 *   - per-run DRILL-DOWN: expanding a run loads its FAILURE sub-records
 *     (`GET /members/mail-runs/{runId}`) and lists each failed recipient with its
 *     outcome + reason. Only FAILURES exist as sub-records — a successful
 *     recipient is counted in the tally, never listed (the design's failure-only
 *     model) — so a run with no failures shows a clear "no failures" note.
 *
 * HONESTY OF STATUS (R9.4): "sent" means "SES ACCEPTED the message" (a MessageId
 * was returned), which is NOT "delivered to the inbox". This screen NEVER labels
 * the sent count "delivered" — it carries an explicit note
 * (`mailRuns.sentMeaning`) that "sent = accepted by SES, not confirmed
 * delivered". True delivered/bounced status is the separate, layered SES-feedback
 * concern (R9.5), surfaced here only as late `bounced` / `complaint` FAILURE
 * sub-records if that layer is present.
 *
 * ROLE-SCOPING (R9.3) is applied SERVER-SIDE: a plain user receives only the runs
 * they triggered; a Tenant_Admin receives all the tenant's runs. The frontend
 * never filters by owner — it renders exactly what the edge returns (the API
 * client's `listMailRuns` / `getMailRun` wrappers hit the role-scoped routes).
 *
 * No hardcoded English: every label resolves from the `members` namespace
 * (`analytics.mailRuns.*`), bilingual via the active language. Keyboard-
 * accessible: each run is a native `<button>` row that toggles its drill-down.
 *
 * @module components/members/analytics/MemberMailStatus
 * @see .kiro/specs/Members/pivot-output-actions/mail (R9; design "status records + read route + screen")
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Badge,
  Box,
  Button,
  HStack,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
  useToast,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import {
  listMailRuns,
  getMailRun,
  deleteMailRun,
} from '../../../services/membersApiService';
import { applyApiError } from '../../../shared/api/applyApiError';
import type {
  MailRunDetail,
  MailRunStatus,
  MailFailureStatus,
  MailRunSummary,
} from '../../../types/members';

/** `members`-namespace i18n key prefix for every label this screen renders. */
const T = 'analytics.mailRuns';

/** The Chakra color scheme for each run lifecycle status (visual, non-authoritative). */
const STATUS_COLOR: Record<MailRunStatus, string> = {
  queued: 'gray',
  sending: 'blue',
  completed: 'green',
};

/** The Chakra color scheme for each per-recipient FAILURE status. */
const FAILURE_COLOR: Record<MailFailureStatus, string> = {
  failed: 'red',
  bounced: 'orange',
  complaint: 'purple',
};

export interface MemberMailStatusProps {
  /** Active language — reserved for parity with sibling components; labels resolve via i18n. */
  language?: string;
  /**
   * List the tenant's send-run tallies. Injectable for tests; defaults to the
   * authenticated {@link listMailRuns} service (role-scoped server-side, R9.3).
   */
  loadRuns?: typeof listMailRuns;
  /**
   * Fetch one run's tally + FAILURE drill-down. Injectable for tests; defaults to
   * the authenticated {@link getMailRun} service.
   */
  loadRun?: typeof getMailRun;
  /**
   * Manually delete one send-run (R9.6 retention). Injectable for tests; defaults
   * to the authenticated {@link deleteMailRun} service. Guarded by an explicit
   * confirm (steering 32 — a destructive action is never implicit).
   */
  removeRun?: typeof deleteMailRun;
}

/** Per-run drill-down state: the fetched detail, a load flag, and any load error. */
interface DrillState {
  detail?: MailRunDetail;
  loading: boolean;
  error: boolean;
}

/**
 * The mail status/history screen (R9.2). Loads the run list on mount; each run
 * row expands to lazily load + show its FAILURE drill-down.
 */
export const MemberMailStatus: React.FC<MemberMailStatusProps> = ({
  loadRuns = listMailRuns,
  loadRun = getMailRun,
  removeRun = deleteMailRun,
}) => {
  const { t } = useTypedTranslation('members');
  const toast = useToast();

  const [runs, setRuns] = useState<MailRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  // The currently-expanded run id (one open at a time), and the per-run drill
  // state keyed by run id so a re-collapse/expand reuses the already-loaded view.
  const [expanded, setExpanded] = useState<string | null>(null);
  const [drill, setDrill] = useState<Record<string, DrillState>>({});
  // The run pending a manual delete (R9.6) — non-null while the confirm dialog is
  // open; the delete only fires once the user confirms (steering 32). `deleting`
  // guards the confirm button while the DELETE is in flight.
  const [pendingDelete, setPendingDelete] = useState<MailRunSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  // The AlertDialog's least-destructive (initial) focus target — the Cancel button.
  const cancelDeleteRef = useRef<HTMLButtonElement>(null);

  // (Re)load the run list. A load failure degrades to a clear error state (not a
  // crash); the list is role-scoped + newest-first server-side, so no client sort.
  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const list = await loadRuns();
      setRuns(list);
    } catch {
      setLoadError(true);
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, [loadRuns]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Toggle a run's drill-down. Collapsing just clears the expanded id (the loaded
  // detail is kept so re-expanding is instant). Expanding lazily loads the run's
  // tally + FAILURE list the first time; a load failure sets a per-run error.
  const toggleRun = useCallback(
    async (runId: string) => {
      if (expanded === runId) {
        setExpanded(null);
        return;
      }
      setExpanded(runId);
      if (drill[runId]?.detail || drill[runId]?.loading) {
        return; // already loaded or in flight
      }
      setDrill((prev) => ({ ...prev, [runId]: { loading: true, error: false } }));
      try {
        const detail = await loadRun(runId);
        setDrill((prev) => ({
          ...prev,
          [runId]: { detail, loading: false, error: false },
        }));
      } catch {
        setDrill((prev) => ({
          ...prev,
          [runId]: { loading: false, error: true },
        }));
      }
    },
    [expanded, drill, loadRun],
  );

  // Manual delete (R9.6 retention): the confirmed, destructive purge of one run.
  // Opened by the per-row Delete button (which sets `pendingDelete`); this fires
  // only on explicit confirm (steering 32 — never implicit). On success it toasts
  // + refreshes the list (the deleted run drops out, its drill state cleared); a
  // failure (e.g. a 404 for another user's run, or a network error) is surfaced via
  // the shared `applyApiError` toast pattern and the list is left as-is.
  const handleConfirmDelete = useCallback(async () => {
    if (!pendingDelete) {
      return;
    }
    const runId = pendingDelete.runId;
    setDeleting(true);
    try {
      await removeRun(runId);
      toast({ title: t(`${T}.delete.deleted`), status: 'success' });
      // Drop any cached drill-down + collapse if the deleted run was expanded.
      setDrill((prev) => {
        const next = { ...prev };
        delete next[runId];
        return next;
      });
      setExpanded((cur) => (cur === runId ? null : cur));
      setPendingDelete(null);
      await refresh();
    } catch (err) {
      applyApiError(err, { toast, t });
    } finally {
      setDeleting(false);
    }
  }, [pendingDelete, removeRun, refresh, toast, t]);

  return (
    <Box data-testid="member-mail-status">
      <VStack align="stretch" spacing={3}>
        <HStack justify="space-between" align="flex-start">
          <Box>
            <Text fontSize="lg" fontWeight="bold" color="white">
              {t(`${T}.title`)}
            </Text>
            <Text fontSize="sm" color="gray.400">
              {t(`${T}.intro`)}
            </Text>
          </Box>
          <Button
            variant="outline"
            colorScheme="orange"
            size="sm"
            onClick={() => void refresh()}
            isLoading={loading}
            data-testid="member-mail-status-refresh"
          >
            {t(`${T}.refresh`)}
          </Button>
        </HStack>

        {/* HONESTY OF STATUS (R9.4): an always-visible note that "sent" means
            "accepted by SES", NOT "delivered to the inbox". The sent count below
            is never labelled "delivered". */}
        <Text
          fontSize="xs"
          color="yellow.300"
          data-testid="member-mail-status-sent-meaning"
        >
          {t(`${T}.sentMeaning`)}
        </Text>

        {loading ? (
          <HStack color="gray.400" data-testid="member-mail-status-loading">
            <Spinner size="sm" />
            <Text fontSize="sm">{t(`${T}.loading`)}</Text>
          </HStack>
        ) : loadError ? (
          <Text fontSize="sm" color="red.300" data-testid="member-mail-status-error">
            {t(`${T}.loadError`)}
          </Text>
        ) : runs.length === 0 ? (
          <Text fontSize="sm" color="gray.500" data-testid="member-mail-status-empty">
            {t(`${T}.empty`)}
          </Text>
        ) : (
          <VStack align="stretch" spacing={2} data-testid="member-mail-status-list">
            {runs.map((run) => {
              const isOpen = expanded === run.runId;
              const state = drill[run.runId];
              return (
                <Box
                  key={run.runId}
                  bg="gray.700"
                  borderRadius="md"
                  data-testid="member-mail-status-run"
                >
                  {/* The run row: the toggle button (keyboard-accessible, expands
                      the drill-down, R9.2) + a SIBLING manual-delete control
                      (R9.6) — kept OUTSIDE the toggle button so it is its own
                      focusable control and a delete click never also toggles. */}
                  <HStack align="stretch" spacing={0}>
                    <Box
                      as="button"
                      type="button"
                      flex="1"
                      textAlign="left"
                      px={3}
                      py={2}
                      onClick={() => void toggleRun(run.runId)}
                      aria-expanded={isOpen}
                      data-testid="member-mail-status-run-toggle"
                    >
                      <HStack justify="space-between" align="center" spacing={3}>
                        <VStack align="start" spacing={0}>
                          <Text color="white" fontSize="sm" fontWeight="medium">
                            {t(`${T}.mode.${run.mode}`)}
                            {' · '}
                            {t(`${T}.recipientCount`, { count: run.recipientCount })}
                          </Text>
                          {/* The tally — "198 sent, 2 failed" (R9.2). `sent` is the
                              SES-ACCEPTED count, never "delivered" (R9.4). */}
                          <Text
                            color="gray.300"
                            fontSize="xs"
                            data-testid="member-mail-status-tally"
                          >
                            {t(`${T}.tally`, { sent: run.sent, failed: run.failed })}
                          </Text>
                        </VStack>
                        <HStack spacing={2} flexShrink={0}>
                          <Badge
                            colorScheme={STATUS_COLOR[run.status]}
                            data-testid="member-mail-status-badge"
                          >
                            {t(`${T}.status.${run.status}`)}
                          </Badge>
                          <Text fontSize="xs" color="orange.300">
                            {isOpen
                              ? t(`${T}.hideFailures`)
                              : t(`${T}.viewFailures`)}
                          </Text>
                        </HStack>
                      </HStack>
                    </Box>
                    {/* The manual-delete control (R9.6). Clicking opens the confirm
                        dialog (steering 32 — a destructive action needs an explicit
                        confirm); the actual DELETE fires only on confirm. */}
                    <Button
                      variant="ghost"
                      colorScheme="red"
                      size="sm"
                      alignSelf="center"
                      mr={2}
                      onClick={() => setPendingDelete(run)}
                      aria-label={t(`${T}.delete.action`)}
                      data-testid="member-mail-status-delete"
                    >
                      {t(`${T}.delete.action`)}
                    </Button>
                  </HStack>

                  {/* The per-run FAILURE drill-down (R9.2) — loaded lazily on
                      first expand. A run with no FAILURE sub-records shows a clear
                      "no failures" note (a success is counted in the tally, never
                      listed — the failure-only sub-record model). */}
                  {isOpen && (
                    <Box
                      px={3}
                      pb={3}
                      data-testid="member-mail-status-drill"
                    >
                      {state?.loading ? (
                        <HStack color="gray.400">
                          <Spinner size="xs" />
                          <Text fontSize="xs">{t(`${T}.loading`)}</Text>
                        </HStack>
                      ) : state?.error ? (
                        <Text
                          fontSize="xs"
                          color="red.300"
                          data-testid="member-mail-status-drill-error"
                        >
                          {t(`${T}.loadRunError`)}
                        </Text>
                      ) : state?.detail && state.detail.failures.length > 0 ? (
                        <>
                          <Text fontSize="xs" color="gray.400" mb={1}>
                            {t(`${T}.failuresTitle`)}
                          </Text>
                          <Table
                            size="sm"
                            variant="simple"
                            data-testid="member-mail-status-failures"
                          >
                            <Thead>
                              <Tr>
                                <Th color="gray.400">{t(`${T}.failure.address`)}</Th>
                                <Th color="gray.400">{t(`${T}.failure.status`)}</Th>
                                <Th color="gray.400">{t(`${T}.failure.reason`)}</Th>
                              </Tr>
                            </Thead>
                            <Tbody>
                              {state.detail.failures.map((failure, idx) => (
                                <Tr
                                  key={`${failure.address}-${idx}`}
                                  data-testid="member-mail-status-failure"
                                >
                                  <Td color="white">{failure.address}</Td>
                                  <Td>
                                    <Badge
                                      colorScheme={FAILURE_COLOR[failure.status]}
                                    >
                                      {t(`${T}.failureStatus.${failure.status}`)}
                                    </Badge>
                                  </Td>
                                  <Td color="gray.300">
                                    {failure.reason ?? t(`${T}.failure.noReason`)}
                                  </Td>
                                </Tr>
                              ))}
                            </Tbody>
                          </Table>
                        </>
                      ) : (
                        <Text
                          fontSize="xs"
                          color="gray.500"
                          data-testid="member-mail-status-no-failures"
                        >
                          {t(`${T}.noFailures`)}
                        </Text>
                      )}
                    </Box>
                  )}
                </Box>
              );
            })}
          </VStack>
        )}
      </VStack>

      {/* Manual-delete confirmation (R9.6; steering 32) — deleting a send-run is
          an explicit, confirmed, destructive action, never implicit. Bilingual,
          keyboard-accessible (AlertDialog traps focus; Cancel is the initial
          focus / least-destructive target). The actual DELETE fires only from the
          Confirm button. */}
      <AlertDialog
        isOpen={pendingDelete !== null}
        leastDestructiveRef={cancelDeleteRef}
        onClose={() => setPendingDelete(null)}
        isCentered
      >
        <AlertDialogOverlay>
          <AlertDialogContent
            bg="gray.800"
            color="white"
            data-testid="member-mail-status-delete-dialog"
          >
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              {t(`${T}.delete.confirmTitle`)}
            </AlertDialogHeader>
            <AlertDialogBody>{t(`${T}.delete.confirmBody`)}</AlertDialogBody>
            <AlertDialogFooter>
              <Button
                ref={cancelDeleteRef}
                onClick={() => setPendingDelete(null)}
                data-testid="member-mail-status-delete-cancel"
              >
                {t(`${T}.delete.confirmCancel`)}
              </Button>
              <Button
                colorScheme="red"
                ml={3}
                onClick={() => void handleConfirmDelete()}
                isLoading={deleting}
                data-testid="member-mail-status-delete-confirm"
              >
                {t(`${T}.delete.confirmConfirm`)}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
};

export default MemberMailStatus;

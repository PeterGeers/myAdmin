/**
 * Members BULK lifecycle-transition modal (task 20.4, R8.6) — REUSES the shared
 * modal pattern (R7.9): a Chakra `Modal`, a Cancel(ghost)/Save(orange) footer, and
 * `closeOnOverlayClick={false}`, following `MembersEditModal.tsx` /
 * `frontend/src/pages/ZZPInvoices.tsx` + `.kiro/steering/32-frontend-ui.md`.
 *
 * Operates over the user-SELECTED rows (`memberIds`). The target-state options
 * come FROM THE MODULE (design C2, R8.6) via `allTargetStates` — the union of the
 * lifecycle's declared target states carried on the resolved field config
 * (`GET /members/field-config` → `lifecycle`), never a hardcoded status list.
 * Because a selection may span members in different current states, the module
 * re-validates each member's transition individually (a target unreachable for a
 * given member is simply denied for that member).
 *
 * On confirm → `bulkTransition({ member_ids: [...selected], to_state, context? })`
 * matching the handler contract (`bulk_transition_memberships` requires a
 * non-empty `member_ids` list + `to_state`; `context` threads guard facts such as
 * h-dcn's `context.approved`). On success: toast (reporting how many), clear the
 * selection + refresh (`onDone`). On error: toast the server message; never crash.
 *
 * _Requirements: R8.6, R7.9_
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, FormControl, FormLabel,
  Select, Checkbox, VStack, Text, useToast,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { bulkTransition } from '../../services/membersApiService';
import type { FieldConfig } from '../../types/members';
import { allTargetStates, targetRequiresApproval } from './transitionTargets';

interface MembersBulkTransitionModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** The selected member ids the bulk transition acts over. */
  memberIds: string[];
  /** Resolved field config carrying the module-provided `lifecycle`. */
  fieldConfig: FieldConfig | null;
  /** Called after a successful bulk transition (page clears selection + refreshes). */
  onDone: () => void;
}

export const MembersBulkTransitionModal: React.FC<MembersBulkTransitionModalProps> = ({
  isOpen, onClose, memberIds, fieldConfig, onDone,
}) => {
  const { t } = useTypedTranslation('members');
  const toast = useToast();

  // The candidate targets FROM THE MODULE (union across states; never hardcoded).
  const targets = useMemo(
    () => allTargetStates(fieldConfig?.lifecycle),
    [fieldConfig],
  );

  const [toState, setToState] = useState('');
  const [approved, setApproved] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setToState('');
      setApproved(false);
      setSubmitting(false);
    }
  }, [isOpen]);

  const needsApproval = targetRequiresApproval(fieldConfig?.lifecycle, toState);

  const handleConfirm = async () => {
    if (memberIds.length === 0 || !toState) return;
    const body: {
      member_ids: string[];
      to_state: string;
      context?: Record<string, unknown>;
    } = {
      member_ids: memberIds,
      to_state: toState,
    };
    if (needsApproval) {
      body.context = { approved };
    }
    try {
      setSubmitting(true);
      await bulkTransition(body);
      toast({
        title: t('bulkTransition.toast.success', { count: memberIds.length }),
        status: 'success',
      });
      onDone();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('bulkTransition.toast.error');
      toast({ title: message, status: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      isCentered
      closeOnOverlayClick={false}
    >
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader>{t('bulkTransition.title')}</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack spacing={3} align="stretch">
            <Text fontSize="sm" color="gray.400">
              {t('bulkTransition.selectedCount', { count: memberIds.length })}
            </Text>

            <FormControl>
              <FormLabel color="gray.300" fontSize="sm">
                {t('bulkTransition.toStateLabel')}
              </FormLabel>
              <Select
                name="to_state"
                size="sm"
                bg="gray.700"
                color="white"
                borderColor="gray.600"
                placeholder={t('bulkTransition.toStatePlaceholder')}
                value={toState}
                onChange={(e) => setToState(e.target.value)}
                isDisabled={targets.length === 0}
              >
                {targets.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </Select>
            </FormControl>

            {targets.length === 0 && (
              <Text fontSize="sm" color="gray.500">
                {t('bulkTransition.noTargets')}
              </Text>
            )}

            {needsApproval && (
              <FormControl>
                <Checkbox
                  name="approved"
                  isChecked={approved}
                  onChange={(e) => setApproved(e.target.checked)}
                  colorScheme="orange"
                >
                  {t('bulkTransition.approvedLabel')}
                </Checkbox>
              </FormControl>
            )}
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose}>
            {t('bulkTransition.cancel')}
          </Button>
          <Button
            colorScheme="orange"
            onClick={handleConfirm}
            isLoading={submitting}
            isDisabled={!toState || memberIds.length === 0}
          >
            {t('bulkTransition.confirm')}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default MembersBulkTransitionModal;

/**
 * Members single lifecycle-transition modal (task 20.3, R8.5) — REUSES the shared
 * modal pattern (R7.9): a Chakra `Modal`, a Cancel(ghost)/Save(orange) footer, and
 * `closeOnOverlayClick={false}`, following `MembersEditModal.tsx` /
 * `frontend/src/pages/ZZPInvoices.tsx` + `.kiro/steering/32-frontend-ui.md`.
 *
 * ALLOWED TARGETS COME FROM THE MODULE (design C2, R8.5), never hardcoded here:
 * the target-state options are derived (`allowedTargetsFor`) from the member's
 * CURRENT state and the module-provided lifecycle carried on the resolved field
 * config (`GET /members/field-config` → `lifecycle`). A tenant with no configured
 * lifecycle yields no options (deny-by-default at the UI). The module stays
 * authoritative — it re-validates and answers 409 with reasons on a denial.
 *
 * On confirm → `transitionMembership(memberId, membershipId, { to_state, context? })`
 * matching the handler contract (`_parse_to_state` reads `to_state`; the optional
 * `context` object threads guard facts such as h-dcn's `context.approved`). On
 * success: toast, close, refresh (`onDone`). On error (e.g. a 409 transition
 * denied carrying reasons): toast the server message without crashing.
 *
 * _Requirements: R8.5, R7.9_
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, FormControl, FormLabel,
  Select, Checkbox, VStack, Text, Box, useToast,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { transitionMembership } from '../../services/membersApiService';
import type { Member, FieldConfig } from '../../types/members';
import { allowedTargetsFor, targetRequiresApproval } from './transitionTargets';

interface MembersTransitionModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** The member whose primary membership is being transitioned. */
  member: Member | null;
  /** Resolved field config carrying the module-provided `lifecycle`. */
  fieldConfig: FieldConfig | null;
  /** Called after a successful transition so the page can refresh its list. */
  onDone: () => void;
}

export const MembersTransitionModal: React.FC<MembersTransitionModalProps> = ({
  isOpen, onClose, member, fieldConfig, onDone,
}) => {
  const { t } = useTypedTranslation('members');
  const toast = useToast();

  const currentState = (member?.status as string) || '';

  // The candidate targets FROM THE MODULE (never a hardcoded list).
  const targets = useMemo(
    () => allowedTargetsFor(fieldConfig?.lifecycle, currentState),
    [fieldConfig, currentState],
  );

  const [toState, setToState] = useState('');
  const [approved, setApproved] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Reset the form each time the modal opens (or the member/targets change).
  useEffect(() => {
    if (isOpen) {
      setToState('');
      setApproved(false);
      setSubmitting(false);
    }
  }, [isOpen, member]);

  const needsApproval = targetRequiresApproval(
    fieldConfig?.lifecycle, toState, currentState,
  );

  // The membership id the transition targets (the member's primary membership).
  const membershipId = (member?.membership_id as string) || '';

  const handleConfirm = async () => {
    if (!member || !toState) return;
    const body: { to_state: string; context?: Record<string, unknown> } = {
      to_state: toState,
    };
    if (needsApproval) {
      body.context = { approved };
    }
    try {
      setSubmitting(true);
      await transitionMembership(member.member_id, membershipId, body);
      toast({ title: t('transition.toast.success'), status: 'success' });
      onDone();
      onClose();
    } catch (err) {
      // A denied transition (409 with reasons) surfaces its message; never crash.
      const message = err instanceof Error ? err.message : t('transition.toast.error');
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
        <ModalHeader>{t('transition.title')}</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack spacing={3} align="stretch">
            <Text fontSize="sm" color="gray.400">
              {t('transition.currentState')}:{' '}
              <Box as="span" color="white">{currentState || '-'}</Box>
            </Text>

            <FormControl>
              <FormLabel color="gray.300" fontSize="sm">
                {t('transition.toStateLabel')}
              </FormLabel>
              <Select
                name="to_state"
                size="sm"
                bg="gray.700"
                color="white"
                borderColor="gray.600"
                placeholder={t('transition.toStatePlaceholder')}
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
                {t('transition.noTargets')}
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
                  {t('transition.approvedLabel')}
                </Checkbox>
              </FormControl>
            )}
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose}>
            {t('transition.cancel')}
          </Button>
          <Button
            colorScheme="orange"
            onClick={handleConfirm}
            isLoading={submitting}
            isDisabled={!toState}
          >
            {t('transition.confirm')}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default MembersTransitionModal;

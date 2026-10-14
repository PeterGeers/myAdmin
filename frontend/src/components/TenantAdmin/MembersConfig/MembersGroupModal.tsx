/**
 * Group modal for the Members config drill-down (Phase 3, task 4.4; R4.1/R4.2/R4.4).
 *
 * Opened by a row-click on the functional-groups table (`MembersGroupsTable`), or by its "add group"
 * action in `create` mode. Edits a functional group's OWN attributes — `key`, bilingual label,
 * `order` — and offers:
 *   - **Delete**, enabled ONLY when the group holds no fields (R4.2 — a non-empty group is not
 *     deletable; the button is disabled with a reason, and an `AlertDialog` confirms the delete);
 *   - a **Fields** affordance that drills into the group's fields (the fields table, task 4.5).
 *
 * The modal is CONTROLLED and does NOT save: every change is applied to the working `field_overlay`
 * via the pure `overlayModel` helpers and bubbled up through `onChange`. The editor (task 4.8)
 * commits the whole object once through `saveMembersParameter` (one save → one re-projection,
 * Property 8). Follows the Chakra `Modal` + `AlertDialog` pattern established by `AccountModal`.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Box,
  Button,
  FormControl,
  FormErrorMessage,
  FormLabel,
  HStack,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Text,
  useDisclosure,
  VStack,
} from '@chakra-ui/react';
import type { MembersConfigValue } from '../../../types/membersConfig';
import {
  createGroup,
  deleteGroup,
  editGroup,
  groupExists,
  groupFieldCount,
  listGroups,
  type OverlayGroup,
} from './overlayModel';

export type GroupModalMode = 'create' | 'edit';

export interface MembersGroupModalProps {
  isOpen: boolean;
  onClose: () => void;
  mode: GroupModalMode;
  /** The group key being edited (edit mode). Ignored in create mode. */
  groupKey?: string;
  /** The working field_overlay the modal reads the group from and writes back to. */
  overlay: MembersConfigValue | undefined;
  /** Apply a mutated overlay (the modal never saves — the editor commits once). */
  onChange: (next: MembersConfigValue) => void;
  /** Drill into this group's fields (opens the fields table, task 4.5). */
  onOpenFields?: (groupKey: string) => void;
  /**
   * The count of RESOLVED fields in this group (remediation R1.3) — the authoritative input to the
   * delete-when-empty guard, so a group holding only base/calculated fields is correctly non-empty.
   * `undefined` (resolved config unavailable) falls back to the working-overlay field count (R1.4).
   */
  resolvedFieldCount?: number;
  lang: 'nl' | 'en';
}

interface GroupForm {
  key: string;
  label_en: string;
  label_nl: string;
  order: string; // kept as string for the number input; parsed on save
}

const EMPTY_FORM: GroupForm = { key: '', label_en: '', label_nl: '', order: '' };

/** Read a group's current attributes into the editable form shape. */
function formFromGroup(group: OverlayGroup | undefined): GroupForm {
  if (!group) return { ...EMPTY_FORM };
  return {
    key: group.key ?? '',
    label_en: typeof group.label_en === 'string' ? group.label_en : '',
    label_nl: typeof group.label_nl === 'string' ? group.label_nl : '',
    order: typeof group.order === 'number' ? String(group.order) : '',
  };
}

export const MembersGroupModal: React.FC<MembersGroupModalProps> = ({
  isOpen,
  onClose,
  mode,
  groupKey,
  overlay,
  onChange,
  onOpenFields,
  resolvedFieldCount,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  const existingGroup = useMemo(
    () => (mode === 'edit' && groupKey ? listGroups(overlay).find((g) => g.key === groupKey) : undefined),
    [mode, groupKey, overlay],
  );

  const [form, setForm] = useState<GroupForm>(() => formFromGroup(existingGroup));
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Re-seed the form whenever the modal (re)opens for a group / in create mode.
  useEffect(() => {
    if (isOpen) {
      setForm(mode === 'edit' ? formFromGroup(existingGroup) : { ...EMPTY_FORM });
      setErrors({});
    }
  }, [isOpen, mode, existingGroup]);

  // The delete-when-empty guard counts the RESOLVED fields in the group (R1.3) — a group holding
  // only base/calculated fields is non-empty even if the working overlay authored none. When the
  // resolved count is unavailable (older module build / fetch failure) fall back to the working
  // overlay's field count so the guard still errs on the safe side (R1.4).
  const fieldCount = useMemo(
    () =>
      resolvedFieldCount !== undefined
        ? resolvedFieldCount
        : groupKey
          ? groupFieldCount(overlay, groupKey)
          : 0,
    [resolvedFieldCount, overlay, groupKey],
  );
  const canDelete = mode === 'edit' && fieldCount === 0;

  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);

  const setField = (k: keyof GroupForm, v: string) => {
    setForm((prev) => ({ ...prev, [k]: v }));
    if (errors[k]) setErrors((prev) => ({ ...prev, [k]: '' }));
  };

  /** Validate the form against the working overlay (key required + unique within the overlay). */
  const validate = (): boolean => {
    const next: Record<string, string> = {};
    const key = form.key.trim();
    if (!key) {
      next.key = t('Groepssleutel is verplicht', 'Group key is required');
    } else if (mode === 'create' && groupExists(overlay, key)) {
      next.key = t('Deze groepssleutel bestaat al', 'This group key already exists');
    } else if (
      mode === 'edit' &&
      key !== groupKey &&
      listGroups(overlay).some((g) => g.key === key)
    ) {
      next.key = t('Deze groepssleutel bestaat al', 'This group key already exists');
    }
    if (form.order.trim() && Number.isNaN(Number(form.order))) {
      next.order = t('Volgorde moet een getal zijn', 'Order must be a number');
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSave = () => {
    if (!validate()) return;
    const patch: Partial<OverlayGroup> = {
      key: form.key.trim(),
      label_en: form.label_en.trim() || undefined,
      label_nl: form.label_nl.trim() || undefined,
      order: form.order.trim() ? Number(form.order) : undefined,
    };
    const next =
      mode === 'create'
        ? createGroup(overlay, patch as OverlayGroup)
        : editGroup(overlay, groupKey as string, patch);
    onChange(next);
    onClose();
  };

  const handleDelete = () => {
    if (!canDelete || !groupKey) return;
    onChange(deleteGroup(overlay, groupKey));
    onDeleteClose();
    onClose();
  };

  return (
    <>
      <Modal isOpen={isOpen} onClose={onClose} size="lg">
        <ModalOverlay />
        <ModalContent bg="gray.800" data-testid="members-group-modal">
          <ModalHeader color="orange.400">
            {mode === 'create' ? t('Groep toevoegen', 'Add group') : t('Groep bewerken', 'Edit group')}
          </ModalHeader>
          <ModalCloseButton color="white" />

          <ModalBody>
            <VStack spacing={4} pb={2} align="stretch">
              <FormControl isInvalid={!!errors.key} isRequired>
                <FormLabel color="gray.300">{t('Groepssleutel', 'Group key')}</FormLabel>
                <Input
                  value={form.key}
                  onChange={(e) => setField('key', e.target.value)}
                  placeholder="e.g., personal, address"
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                  aria-label={t('Groepssleutel', 'Group key')}
                />
                {errors.key && <FormErrorMessage>{errors.key}</FormErrorMessage>}
              </FormControl>

              <FormControl>
                <FormLabel color="gray.300">{t('Label (Engels)', 'Label (English)')}</FormLabel>
                <Input
                  value={form.label_en}
                  onChange={(e) => setField('label_en', e.target.value)}
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                  aria-label={t('Label (Engels)', 'Label (English)')}
                />
              </FormControl>

              <FormControl>
                <FormLabel color="gray.300">{t('Label (Nederlands)', 'Label (Dutch)')}</FormLabel>
                <Input
                  value={form.label_nl}
                  onChange={(e) => setField('label_nl', e.target.value)}
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                  aria-label={t('Label (Nederlands)', 'Label (Dutch)')}
                />
              </FormControl>

              <FormControl isInvalid={!!errors.order}>
                <FormLabel color="gray.300">{t('Volgorde', 'Order')}</FormLabel>
                <Input
                  type="number"
                  value={form.order}
                  onChange={(e) => setField('order', e.target.value)}
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                  aria-label={t('Volgorde', 'Order')}
                />
                {errors.order && <FormErrorMessage>{errors.order}</FormErrorMessage>}
              </FormControl>

              {mode === 'edit' && groupKey && onOpenFields && (
                <Box>
                  <Button
                    variant="outline"
                    colorScheme="orange"
                    onClick={() => onOpenFields(groupKey)}
                    data-testid="members-group-modal-fields-btn"
                  >
                    {t(`Velden (${fieldCount})`, `Fields (${fieldCount})`)}
                  </Button>
                </Box>
              )}
            </VStack>
          </ModalBody>

          <ModalFooter>
            <HStack justify="space-between" width="100%">
              {mode === 'edit' && (
                <Box>
                  <Button
                    colorScheme="red"
                    variant="outline"
                    onClick={onDeleteOpen}
                    isDisabled={!canDelete}
                    data-testid="members-group-modal-delete-btn"
                  >
                    {t('Verwijderen', 'Delete')}
                  </Button>
                  {!canDelete && (
                    <Text fontSize="xs" color="gray.500" mt={1} data-testid="members-group-modal-delete-reason">
                      {t(
                        `Kan een groep met ${fieldCount} veld(en) niet verwijderen`,
                        `Cannot delete a group with ${fieldCount} field(s)`,
                      )}
                    </Text>
                  )}
                </Box>
              )}
              <Box flex={1} />
              <HStack spacing={3}>
                <Button variant="ghost" onClick={onClose} color="white">
                  {t('Annuleren', 'Cancel')}
                </Button>
                <Button colorScheme="orange" onClick={handleSave} data-testid="members-group-modal-save-btn">
                  {mode === 'create' ? t('Aanmaken', 'Create') : t('Opslaan', 'Save')}
                </Button>
              </HStack>
            </HStack>
          </ModalFooter>
        </ModalContent>
      </Modal>

      <AlertDialog isOpen={isDeleteOpen} leastDestructiveRef={cancelRef} onClose={onDeleteClose}>
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800">
            <AlertDialogHeader fontSize="lg" fontWeight="bold" color="orange.400">
              {t('Groep verwijderen', 'Delete group')}
            </AlertDialogHeader>
            <AlertDialogBody color="white">
              {t(
                `Weet je zeker dat je de groep "${groupKey}" wilt verwijderen?`,
                `Are you sure you want to delete the group "${groupKey}"?`,
              )}
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onDeleteClose} color="white">
                {t('Annuleren', 'Cancel')}
              </Button>
              <Button
                colorScheme="red"
                onClick={handleDelete}
                ml={3}
                data-testid="members-group-modal-delete-confirm"
              >
                {t('Verwijderen', 'Delete')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </>
  );
};

export default MembersGroupModal;

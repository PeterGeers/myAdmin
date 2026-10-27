/**
 * Provenance-driven field actions + move-to-group (Members config drill-down — Phase 3, task 4.7;
 * R1.2/R1.3/R4.3).
 *
 * Rendered into the field modal's `actionsSlot` (task 4.6). The actions a field offers are GOVERNED
 * by its DERIVED provenance (step 8) — provenance is NEVER shown as a badge, it only SELECTS which
 * actions are available (R1.3):
 *
 *   - `tenant_added`    → destructive **Delete** (AlertDialog confirm) — the tenant authored this
 *     field, so removing it is a real delete;
 *   - `base`            → **Reset to default** (drop any tenant override, reverting to the platform
 *     field) + **Hide** (set `visible: false`) — a platform base field is NEVER destructively
 *     deleted (R1.5 immovable);
 *   - `base_overridden` → **Reset to default** (drop the override) — reverts to the base field.
 *
 * Every provenance also offers **Move to another group** (R4.3): a `LazySelect` of catalog-resolvable
 * groups reassigns the field's `functional_group`.
 *
 * CONTROLLED + save-free: each action is a pure `overlayModel` transform bubbled up through
 * `onChange`; the editor (task 4.8) commits the one object once (Property 8). `onClose` is invoked
 * after a delete so the modal (whose field is gone) does not linger on a stale key.
 */
import React, { useRef } from 'react';
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Box,
  Button,
  HStack,
  Text,
  useDisclosure,
  VStack,
} from '@chakra-ui/react';
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldProvenance, FunctionalGroup } from '../../../types/members';
import { deleteField, editField, moveFieldToGroup } from './overlayModel';
import { LazySelect } from '../../common/LazySelect';
import type { LazyOption } from '../../common/lazySelect.types';
import { resolveFieldConfigLabel } from '../../../services/membersConfigService';

export interface MembersFieldActionsProps {
  /** The field the actions operate on. */
  fieldKey: string;
  /** The field's group (the move-to-group picker excludes it as the current group). */
  currentGroupKey: string;
  /**
   * The RESOLVED functional-group catalog (Flat_View `fieldConfig.functional_groups`) — the SOURCE
   * of move-to-group targets. Base catalog groups live in code and are absent from the sparse
   * tenant overlay, so the picker MUST read the resolved catalog (not the overlay) or it would
   * wrongly report "no other group available" (spec 03 resolved-view rule).
   */
  functionalGroups: FunctionalGroup[];
  /**
   * The field's DERIVED provenance (from the resolved field-config). Governs which actions are
   * offered. Absent → treated as `base` (the most conservative — no destructive delete).
   */
  provenance: FieldProvenance | undefined;
  /** The working field_overlay the actions mutate. */
  overlay: MembersConfigValue | undefined;
  /** Apply a mutated overlay (actions never save — the editor commits once). */
  onChange: (next: MembersConfigValue) => void;
  /** Close the field modal (called after a delete, since the field is gone). */
  onClose: () => void;
  lang: 'nl' | 'en';
}

export const MembersFieldActions: React.FC<MembersFieldActionsProps> = ({
  fieldKey,
  currentGroupKey,
  functionalGroups,
  provenance,
  overlay,
  onChange,
  onClose,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);
  const prov: FieldProvenance = provenance ?? 'base';

  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);

  // Move-to-group picker options: every RESOLVED catalog group except the field's current one.
  // Sourced from the Flat_View `functionalGroups` (NOT the sparse overlay) — base groups live in
  // code and are absent from the overlay, so reading the overlay here wrongly yielded an empty list.
  const groupOptions: LazyOption[] = functionalGroups
    .filter((g) => g.key !== currentGroupKey)
    .map((g) => ({
      value: g.key,
      label: resolveFieldConfigLabel(g.label, lang, g.key),
    }));

  const handleDelete = () => {
    onChange(deleteField(overlay, fieldKey));
    onDeleteClose();
    onClose();
  };

  const handleReset = () => {
    // Reset to default = drop the tenant's authored entry/override, reverting to the base field.
    onChange(deleteField(overlay, fieldKey));
    onClose();
  };

  const handleHide = () => {
    onChange(editField(overlay, fieldKey, { visible: false }));
    onClose();
  };

  const handleMove = (targetGroupKey: string) => {
    if (!targetGroupKey) return;
    onChange(moveFieldToGroup(overlay, fieldKey, targetGroupKey));
    // keep the modal open; the field now shows the new group — the editor refreshes on save
  };

  return (
    <VStack align="stretch" spacing={2} data-testid="members-field-actions">
      <HStack spacing={2}>
        {prov === 'tenant_added' && (
          <Button
            colorScheme="red"
            variant="outline"
            size="sm"
            onClick={onDeleteOpen}
            data-testid="members-field-action-delete"
          >
            {t('Verwijderen', 'Delete')}
          </Button>
        )}
        {(prov === 'base' || prov === 'base_overridden') && (
          <Button
            colorScheme="orange"
            variant="outline"
            size="sm"
            onClick={handleReset}
            data-testid="members-field-action-reset"
          >
            {t('Terugzetten naar standaard', 'Reset to default')}
          </Button>
        )}
        {prov === 'base' && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleHide}
            data-testid="members-field-action-hide"
          >
            {t('Verbergen', 'Hide')}
          </Button>
        )}
      </HStack>

      {/* Move to another group (every provenance) */}
      <Box data-testid="members-field-action-move">
        <Text fontSize="xs" color="gray.400" mb={1}>
          {t('Verplaatsen naar groep', 'Move to group')}
        </Text>
        {groupOptions.length === 0 ? (
          <Text fontSize="xs" color="gray.500">
            {t('Geen andere groep beschikbaar', 'No other group available')}
          </Text>
        ) : (
          <LazySelect
            value={''}
            onChange={handleMove}
            options={groupOptions}
            label={t('Verplaatsen naar groep', 'Move to group')}
            placeholder={t('Kies een groep…', 'Choose a group…')}
            size="sm"
            name="members-field-move-group"
          />
        )}
      </Box>

      <AlertDialog isOpen={isDeleteOpen} leastDestructiveRef={cancelRef} onClose={onDeleteClose}>
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800">
            <AlertDialogHeader fontSize="lg" fontWeight="bold" color="orange.400">
              {t('Veld verwijderen', 'Delete field')}
            </AlertDialogHeader>
            <AlertDialogBody color="white">
              {t(
                `Weet je zeker dat je het veld "${fieldKey}" wilt verwijderen?`,
                `Are you sure you want to delete the field "${fieldKey}"?`,
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
                data-testid="members-field-action-delete-confirm"
              >
                {t('Verwijderen', 'Delete')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </VStack>
  );
};

export default MembersFieldActions;

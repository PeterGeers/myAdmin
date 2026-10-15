/**
 * MemberPivotLibraryModal — the "All sets" library modal of the Pivot Views
 * panel: the single management surface where every saved set can be added to /
 * removed from the user's preferred list, reordered, or (for a custom set)
 * permanently deleted.
 *
 * Extracted verbatim from `MemberPivotViews.tsx` (code-quality split 2026-10-15,
 * task 4) with ZERO behaviour change: a pure presentational component driven by
 * props. Every gate (`canManageSets`, `canDeleteSets`), every testid, and every
 * i18n key is identical to the inline modal it replaces. All state and the
 * add/remove/delete handlers stay in the parent.
 *
 * @module components/members/analytics/MemberPivotLibraryModal
 */

import React from 'react';
import {
  Box,
  IconButton,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalHeader,
  ModalOverlay,
  HStack,
  Tooltip,
  VStack,
} from '@chakra-ui/react';
import { AddIcon, DeleteIcon, MinusIcon } from '@chakra-ui/icons';

/**
 * One already-filtered, already-sorted library row — exactly the shape the
 * parent's `filteredLibraryItems` memo produces.
 */
export interface MemberPivotLibraryItem {
  optionValue: string;
  label: string;
  ref: string | null;
  alreadyPreferred: boolean;
  /** The backend set_id for a CUSTOM saved set (deletable), else null. */
  savedSetId: string | null;
}

type TFunction = (key: string, options?: Record<string, unknown>) => string;

export interface MemberPivotLibraryModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Current name-filter value for the library list. */
  libraryFilter: string;
  onLibraryFilterChange: (value: string) => void;
  /** The library items, already filtered + alphabetically sorted by the parent. */
  filteredLibraryItems: MemberPivotLibraryItem[];
  /** Whether the caller may mutate the preferred list (members:export|write). */
  canManageSets: boolean;
  /** Whether the caller may permanently delete a saved set (members:admin). */
  canDeleteSets: boolean;
  /** True while a preferred-list save is in flight (disables the row actions). */
  isSavingPreferred: boolean;
  /** Add a tagged ref to the preferred list. */
  onAddRef: (ref: string | null) => void;
  /** Remove a tagged ref from the preferred list. */
  onRemovePreferred: (ref: string) => void;
  /** Open the delete-confirm dialog for a custom saved set. */
  onRequestDelete: (item: { id: string; name: string }) => void;
  t: TFunction;
}

const MemberPivotLibraryModal: React.FC<MemberPivotLibraryModalProps> = ({
  isOpen,
  onClose,
  libraryFilter,
  onLibraryFilterChange,
  filteredLibraryItems,
  canManageSets,
  canDeleteSets,
  isSavingPreferred,
  onAddRef,
  onRemovePreferred,
  onRequestDelete,
  t,
}) => {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
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
              onChange={(e) => onLibraryFilterChange(e.target.value)}
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
                                  item.ref !== null && onRemovePreferred(item.ref)
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
                                onClick={() => onAddRef(item.ref)}
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
                                  onRequestDelete({
                                    id: item.savedSetId as string,
                                    name: item.label,
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
  );
};

export default MemberPivotLibraryModal;

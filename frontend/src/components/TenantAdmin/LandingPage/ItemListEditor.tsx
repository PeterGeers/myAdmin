/**
 * ItemListEditor — Reusable wrapper for add/remove/reorder item list pattern.
 *
 * Extracts the common logic shared by FaqItemEditor, TestimonialsItemEditor,
 * PricingItemEditor, and GalleryItemEditor:
 * - Move up/down buttons
 * - Remove with confirmation dialog
 * - Add button
 * - Optional expand/collapse per item
 *
 * Each consumer provides a `renderItem` callback for custom form fields,
 * and a `getItemLabel` callback for the collapsed header preview.
 */

import React, { useState, ReactNode } from 'react';
import {
  Box, VStack, HStack, Text, Button, IconButton, Collapse,
  AlertDialog, AlertDialogOverlay, AlertDialogContent, AlertDialogHeader,
  AlertDialogBody, AlertDialogFooter, useDisclosure,
} from '@chakra-ui/react';
import {
  AddIcon, DeleteIcon, ChevronUpIcon, ChevronDownIcon,
  TriangleUpIcon, TriangleDownIcon,
} from '@chakra-ui/icons';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';

export interface ItemListEditorProps<T> {
  /** The items array to manage */
  items: T[];
  /** Called when items change (reorder, add, remove) */
  onItemsChange: (items: T[]) => void;
  /** Render the form fields for an expanded item */
  renderItem: (item: T, index: number) => ReactNode;
  /** Return preview label for collapsed header */
  getItemLabel: (item: T, index: number) => string;
  /** Factory function returning a new empty item */
  createItem: () => T;
  /** Whether items expand/collapse on click (default: true) */
  expandable?: boolean;
  /** Render custom content for non-expandable items (e.g. gallery thumbnails) */
  renderFlatItem?: (item: T, index: number) => ReactNode;
  /** Label for the add button */
  addLabel: string;
  /** Label for remove confirmation title */
  removeTitle: string;
  /** Label for remove confirmation body */
  removeConfirm: string;
  /** Text shown when list is empty */
  emptyText: string;
  /** Hide the built-in add button (e.g. when using a custom uploader) */
  hideAddButton?: boolean;
}

export default function ItemListEditor<T>({
  items,
  onItemsChange,
  renderItem,
  getItemLabel,
  createItem,
  expandable = true,
  renderFlatItem,
  addLabel,
  removeTitle,
  removeConfirm,
  emptyText,
  hideAddButton = false,
}: ItemListEditorProps<T>) {
  const { t } = useTypedTranslation('admin');
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [removeIndex, setRemoveIndex] = useState<number | null>(null);
  const { isOpen: isRemoveOpen, onOpen: onRemoveOpen, onClose: onRemoveClose } = useDisclosure();
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  const handleAdd = () => {
    const newItems = [...items, createItem()];
    onItemsChange(newItems);
    if (expandable) setExpandedIndex(newItems.length - 1);
  };

  const handleRemove = (index: number) => {
    setRemoveIndex(index);
    onRemoveOpen();
  };

  const confirmRemove = () => {
    if (removeIndex !== null) {
      const updated = items.filter((_, i) => i !== removeIndex);
      onItemsChange(updated);
      if (expandedIndex === removeIndex) setExpandedIndex(null);
      else if (expandedIndex !== null && expandedIndex > removeIndex) {
        setExpandedIndex(expandedIndex - 1);
      }
    }
    setRemoveIndex(null);
    onRemoveClose();
  };

  const handleMoveUp = (index: number) => {
    if (index === 0) return;
    const updated = [...items];
    [updated[index - 1], updated[index]] = [updated[index], updated[index - 1]];
    onItemsChange(updated);
    if (expandable) setExpandedIndex(index - 1);
  };

  const handleMoveDown = (index: number) => {
    if (index >= items.length - 1) return;
    const updated = [...items];
    [updated[index], updated[index + 1]] = [updated[index + 1], updated[index]];
    onItemsChange(updated);
    if (expandable) setExpandedIndex(index + 1);
  };

  const toggleExpand = (index: number) => {
    setExpandedIndex(expandedIndex === index ? null : index);
  };

  /** Shared action buttons row (move up/down + remove) */
  const renderActions = (index: number, stopPropagation = false) => (
    <HStack spacing={1} justify="flex-end">
      <IconButton
        aria-label={t('landingPage.editor.moveUp')}
        icon={<TriangleUpIcon />}
        size="xs"
        variant="ghost"
        color="gray.400"
        isDisabled={index === 0}
        onClick={(e) => { if (stopPropagation) e.stopPropagation(); handleMoveUp(index); }}
        _hover={{ color: 'white' }}
      />
      <IconButton
        aria-label={t('landingPage.editor.moveDown')}
        icon={<TriangleDownIcon />}
        size="xs"
        variant="ghost"
        color="gray.400"
        isDisabled={index === items.length - 1}
        onClick={(e) => { if (stopPropagation) e.stopPropagation(); handleMoveDown(index); }}
        _hover={{ color: 'white' }}
      />
      <IconButton
        aria-label={t('landingPage.editor.remove')}
        icon={<DeleteIcon />}
        size="xs"
        variant="ghost"
        color="red.400"
        onClick={(e) => { if (stopPropagation) e.stopPropagation(); handleRemove(index); }}
        _hover={{ color: 'red.300' }}
      />
    </HStack>
  );

  return (
    <VStack spacing={2} align="stretch">
      {/* Items list */}
      {items.length === 0 ? (
        <Text color="gray.500" fontSize="xs" fontStyle="italic">
          {emptyText}
        </Text>
      ) : expandable ? (
        <VStack spacing={2} align="stretch">
          {items.map((item, index) => (
            <Box
              key={index}
              bg="gray.700"
              borderRadius="md"
              border="1px solid"
              borderColor={expandedIndex === index ? 'orange.400' : 'gray.600'}
              overflow="hidden"
            >
              {/* Item header — click to expand */}
              <HStack
                px={3}
                py={2}
                cursor="pointer"
                onClick={() => toggleExpand(index)}
                _hover={{ bg: 'gray.650' }}
                spacing={2}
              >
                {expandedIndex === index ? (
                  <ChevronUpIcon color="gray.400" boxSize={4} />
                ) : (
                  <ChevronDownIcon color="gray.400" boxSize={4} />
                )}
                <Text
                  color="white"
                  fontSize="xs"
                  flex={1}
                  noOfLines={1}
                  fontWeight={expandedIndex === index ? 'semibold' : 'normal'}
                >
                  {getItemLabel(item, index)}
                </Text>
                <Text color="gray.500" fontSize="xs">
                  #{index + 1}
                </Text>
              </HStack>

              {/* Expanded edit form */}
              <Collapse in={expandedIndex === index} animateOpacity>
                <VStack spacing={2} px={3} pb={3} align="stretch">
                  {renderItem(item, index)}
                  {renderActions(index, true)}
                </VStack>
              </Collapse>
            </Box>
          ))}
        </VStack>
      ) : (
        /* Flat mode (gallery-style): no expand/collapse */
        <VStack spacing={2} align="stretch">
          {items.map((item, index) => (
            <Box
              key={index}
              bg="gray.700"
              borderRadius="md"
              border="1px solid"
              borderColor="gray.600"
              p={2}
            >
              <HStack spacing={2} align="flex-start">
                {renderFlatItem ? renderFlatItem(item, index) : renderItem(item, index)}
                <VStack spacing={1} align="stretch">
                  {renderActions(index)}
                </VStack>
              </HStack>
            </Box>
          ))}
        </VStack>
      )}

      {/* Add item button */}
      {!hideAddButton && (
        <Button
          size="sm"
          variant="outline"
          colorScheme="orange"
          leftIcon={<AddIcon />}
          onClick={handleAdd}
        >
          {addLabel}
        </Button>
      )}

      {/* Remove confirmation dialog */}
      <AlertDialog
        isOpen={isRemoveOpen}
        leastDestructiveRef={cancelRef}
        onClose={onRemoveClose}
        isCentered
      >
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800" borderColor="gray.600">
            <AlertDialogHeader fontSize="md" color="white">
              {removeTitle}
            </AlertDialogHeader>
            <AlertDialogBody color="gray.300" fontSize="sm">
              {removeConfirm}
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} size="sm" onClick={onRemoveClose}>
                {t('landingPage.editor.cancel')}
              </Button>
              <Button size="sm" colorScheme="red" onClick={confirmRemove} ml={3}>
                {t('landingPage.editor.remove')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </VStack>
  );
}

/**
 * BlockListItem — A single block in the editor's block list.
 *
 * Displays block type, layout, drag handle, and action buttons.
 * Supports HTML5 drag-and-drop for reordering.
 */

import React, { useRef, useState } from 'react';
import {
  Box, HStack, Text, IconButton, Tooltip, Badge,
} from '@chakra-ui/react';
import { DragHandleIcon, EditIcon, DeleteIcon, ChevronUpIcon, ChevronDownIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { Section } from '../../../services/landingPageApi';
import RemoveBlockDialog from './RemoveBlockDialog';

interface BlockListItemProps {
  section: Section;
  index: number;
  totalCount: number;
  isEditing: boolean;
  onEdit: () => void;
  onRemove: () => void;
  onReorder: (fromIndex: number, toIndex: number) => void;
}

/** Icon/emoji per block type */
const BLOCK_ICONS: Record<string, string> = {
  hero: '🖼️',
  about: '📝',
  gallery: '🎨',
  testimonials: '💬',
  faq: '❓',
  pricing: '💰',
  cta: '📢',
  embed: '🔗',
  contact: '✉️',
  properties: '🏠',
  services: '🛠️',
};

export default function BlockListItem({
  section, index, totalCount, isEditing, onEdit, onRemove, onReorder,
}: BlockListItemProps) {
  const { t } = useTypedTranslation('admin');
  const [isDragOver, setIsDragOver] = useState(false);
  const [showRemoveDialog, setShowRemoveDialog] = useState(false);
  const dragRef = useRef<HTMLDivElement>(null);

  // --- Drag and drop ---
  const handleDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData('text/plain', String(index));
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setIsDragOver(true);
  };

  const handleDragLeave = () => setIsDragOver(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const fromIndex = parseInt(e.dataTransfer.getData('text/plain'), 10);
    if (!isNaN(fromIndex) && fromIndex !== index) {
      onReorder(fromIndex, index);
    }
  };

  // Block summary text
  const title = (section.properties?.title as string) || '';
  const summary = title || t(`landingPage.blockTypes.${section.type}`) || section.type;

  return (
    <>
      <Box
        ref={dragRef}
        bg={isEditing ? 'gray.600' : 'gray.700'}
        borderRadius="md"
        p={3}
        border="2px solid"
        borderColor={isDragOver ? 'orange.400' : isEditing ? 'orange.500' : 'transparent'}
        transition="all 0.15s"
        _hover={{ borderColor: isEditing ? 'orange.500' : 'gray.500' }}
        draggable
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        cursor="grab"
        _active={{ cursor: 'grabbing' }}
      >
        <HStack spacing={3}>
          {/* Drag handle */}
          <Box color="gray.400" _hover={{ color: 'gray.200' }}>
            <DragHandleIcon />
          </Box>

          {/* Block icon + info */}
          <Text fontSize="lg" flexShrink={0}>
            {BLOCK_ICONS[section.type] || '📦'}
          </Text>
          <Box flex="1" minW="0">
            <HStack spacing={2}>
              <Text color="white" fontSize="sm" fontWeight="medium" noOfLines={1}>
                {summary}
              </Text>
              <Badge colorScheme="purple" fontSize="2xs" textTransform="lowercase">
                {section.layout}
              </Badge>
            </HStack>
            <Text color="gray.400" fontSize="xs" textTransform="capitalize">
              {section.type}
            </Text>
          </Box>

          {/* Actions */}
          <HStack spacing={1}>
            <Tooltip label={t('landingPage.editor.moveUp')}>
              <IconButton
                aria-label="Move up"
                icon={<ChevronUpIcon />}
                size="xs"
                variant="ghost"
                colorScheme="gray"
                isDisabled={index === 0}
                onClick={(e) => { e.stopPropagation(); onReorder(index, index - 1); }}
              />
            </Tooltip>
            <Tooltip label={t('landingPage.editor.moveDown')}>
              <IconButton
                aria-label="Move down"
                icon={<ChevronDownIcon />}
                size="xs"
                variant="ghost"
                colorScheme="gray"
                isDisabled={index === totalCount - 1}
                onClick={(e) => { e.stopPropagation(); onReorder(index, index + 1); }}
              />
            </Tooltip>
            <Tooltip label={t('landingPage.editor.editBlock')}>
              <IconButton
                aria-label="Edit block"
                icon={<EditIcon />}
                size="xs"
                variant="ghost"
                colorScheme="orange"
                onClick={(e) => { e.stopPropagation(); onEdit(); }}
              />
            </Tooltip>
            <Tooltip label={t('landingPage.editor.removeBlock')}>
              <IconButton
                aria-label="Remove block"
                icon={<DeleteIcon />}
                size="xs"
                variant="ghost"
                colorScheme="red"
                onClick={(e) => { e.stopPropagation(); setShowRemoveDialog(true); }}
              />
            </Tooltip>
          </HStack>
        </HStack>
      </Box>

      {/* Remove confirmation dialog */}
      <RemoveBlockDialog
        isOpen={showRemoveDialog}
        blockType={section.type}
        onConfirm={() => { setShowRemoveDialog(false); onRemove(); }}
        onCancel={() => setShowRemoveDialog(false)}
      />
    </>
  );
}

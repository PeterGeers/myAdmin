/**
 * TestimonialsItemEditor — Inline editor for Testimonials block items.
 *
 * Allows add/edit/remove/reorder of testimonial cards.
 * Each item has: quote, author, and optional role/company.
 * Changes flow through onUpdate to trigger auto-save.
 */

import React, { useState } from 'react';
import {
  Box, VStack, HStack, Text, Button, IconButton, Input, Textarea,
  Collapse, Divider, FormControl, FormLabel,
  AlertDialog, AlertDialogOverlay, AlertDialogContent, AlertDialogHeader,
  AlertDialogBody, AlertDialogFooter, useDisclosure,
} from '@chakra-ui/react';
import { AddIcon, DeleteIcon, ChevronUpIcon, ChevronDownIcon, TriangleUpIcon, TriangleDownIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';

interface TestimonialItem {
  quote: string;
  author: string;
  role?: string;
}

interface TestimonialsItemEditorProps {
  items: TestimonialItem[];
  title: string;
  onUpdate: (updates: { items?: TestimonialItem[]; title?: string }) => void;
}

export default function TestimonialsItemEditor({ items, title, onUpdate }: TestimonialsItemEditorProps) {
  const { t } = useTypedTranslation('admin');
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [removeIndex, setRemoveIndex] = useState<number | null>(null);
  const { isOpen: isRemoveOpen, onOpen: onRemoveOpen, onClose: onRemoveClose } = useDisclosure();
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  const handleAddItem = () => {
    const newItems = [...items, { quote: '', author: '', role: '' }];
    onUpdate({ items: newItems });
    setExpandedIndex(newItems.length - 1);
  };

  const handleUpdateItem = (index: number, field: keyof TestimonialItem, value: string) => {
    const updated = items.map((item, i) =>
      i === index ? { ...item, [field]: value } : item
    );
    onUpdate({ items: updated });
  };

  const handleRemoveItem = (index: number) => {
    setRemoveIndex(index);
    onRemoveOpen();
  };

  const confirmRemove = () => {
    if (removeIndex !== null) {
      const updated = items.filter((_, i) => i !== removeIndex);
      onUpdate({ items: updated });
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
    onUpdate({ items: updated });
    setExpandedIndex(index - 1);
  };

  const handleMoveDown = (index: number) => {
    if (index >= items.length - 1) return;
    const updated = [...items];
    [updated[index], updated[index + 1]] = [updated[index + 1], updated[index]];
    onUpdate({ items: updated });
    setExpandedIndex(index + 1);
  };

  const toggleExpand = (index: number) => {
    setExpandedIndex(expandedIndex === index ? null : index);
  };

  return (
    <VStack spacing={3} align="stretch">
      {/* Section title field */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.fields.title')}
        </FormLabel>
        <Input
          size="sm"
          bg="gray.700"
          color="white"
          borderColor="gray.600"
          value={title || ''}
          onChange={(e) => onUpdate({ title: e.target.value })}
          placeholder={t('landingPage.testimonialsEditor.titlePlaceholder')}
          _placeholder={{ color: 'gray.500' }}
        />
      </FormControl>

      <Divider borderColor="gray.600" />

      {/* Items list */}
      {items.length === 0 ? (
        <Text color="gray.500" fontSize="xs" fontStyle="italic">
          {t('landingPage.testimonialsEditor.noItems')}
        </Text>
      ) : (
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
                  {item.author || t('landingPage.testimonialsEditor.untitledItem')}
                </Text>
                <Text color="gray.500" fontSize="xs">
                  #{index + 1}
                </Text>
              </HStack>

              {/* Expanded edit form */}
              <Collapse in={expandedIndex === index} animateOpacity>
                <VStack spacing={2} px={3} pb={3} align="stretch">
                  <FormControl>
                    <FormLabel color="gray.300" fontSize="xs" mb={1}>
                      {t('landingPage.testimonialsEditor.quote')}
                    </FormLabel>
                    <Textarea
                      size="sm"
                      bg="gray.800"
                      color="white"
                      borderColor="gray.600"
                      value={item.quote}
                      onChange={(e) => handleUpdateItem(index, 'quote', e.target.value)}
                      placeholder={t('landingPage.testimonialsEditor.quotePlaceholder')}
                      _placeholder={{ color: 'gray.500' }}
                      rows={3}
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel color="gray.300" fontSize="xs" mb={1}>
                      {t('landingPage.testimonialsEditor.author')}
                    </FormLabel>
                    <Input
                      size="sm"
                      bg="gray.800"
                      color="white"
                      borderColor="gray.600"
                      value={item.author}
                      onChange={(e) => handleUpdateItem(index, 'author', e.target.value)}
                      placeholder={t('landingPage.testimonialsEditor.authorPlaceholder')}
                      _placeholder={{ color: 'gray.500' }}
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel color="gray.300" fontSize="xs" mb={1}>
                      {t('landingPage.testimonialsEditor.role')}
                    </FormLabel>
                    <Input
                      size="sm"
                      bg="gray.800"
                      color="white"
                      borderColor="gray.600"
                      value={item.role || ''}
                      onChange={(e) => handleUpdateItem(index, 'role', e.target.value)}
                      placeholder={t('landingPage.testimonialsEditor.rolePlaceholder')}
                      _placeholder={{ color: 'gray.500' }}
                    />
                  </FormControl>

                  {/* Action buttons */}
                  <HStack spacing={1} justify="flex-end">
                    <IconButton
                      aria-label={t('landingPage.editor.moveUp')}
                      icon={<TriangleUpIcon />}
                      size="xs"
                      variant="ghost"
                      color="gray.400"
                      isDisabled={index === 0}
                      onClick={(e) => { e.stopPropagation(); handleMoveUp(index); }}
                      _hover={{ color: 'white' }}
                    />
                    <IconButton
                      aria-label={t('landingPage.editor.moveDown')}
                      icon={<TriangleDownIcon />}
                      size="xs"
                      variant="ghost"
                      color="gray.400"
                      isDisabled={index === items.length - 1}
                      onClick={(e) => { e.stopPropagation(); handleMoveDown(index); }}
                      _hover={{ color: 'white' }}
                    />
                    <IconButton
                      aria-label={t('landingPage.testimonialsEditor.removeItem')}
                      icon={<DeleteIcon />}
                      size="xs"
                      variant="ghost"
                      color="red.400"
                      onClick={(e) => { e.stopPropagation(); handleRemoveItem(index); }}
                      _hover={{ color: 'red.300' }}
                    />
                  </HStack>
                </VStack>
              </Collapse>
            </Box>
          ))}
        </VStack>
      )}

      {/* Add item button */}
      <Button
        size="sm"
        variant="outline"
        colorScheme="orange"
        leftIcon={<AddIcon />}
        onClick={handleAddItem}
      >
        {t('landingPage.testimonialsEditor.addItem')}
      </Button>

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
              {t('landingPage.testimonialsEditor.removeTitle')}
            </AlertDialogHeader>
            <AlertDialogBody color="gray.300" fontSize="sm">
              {t('landingPage.testimonialsEditor.removeConfirm')}
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

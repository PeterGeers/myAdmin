/**
 * GalleryItemEditor — Inline editor for Gallery block items.
 *
 * Allows add/remove/reorder of gallery images.
 * Uses ImageUploader for adding new images.
 * Each image has an optional alt text for accessibility.
 * Changes flow through onUpdate to trigger auto-save.
 */

import React, { useState } from 'react';
import {
  Box, VStack, HStack, Text, Button, IconButton, Input, Image,
  FormControl, FormLabel, Divider,
  AlertDialog, AlertDialogOverlay, AlertDialogContent, AlertDialogHeader,
  AlertDialogBody, AlertDialogFooter, useDisclosure,
} from '@chakra-ui/react';
import { DeleteIcon, TriangleUpIcon, TriangleDownIcon } from '@chakra-ui/icons';
import { FiImage } from 'react-icons/fi';
import { Icon } from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import ImageUploader from './ImageUploader';

interface GalleryImage {
  image_key: string;
  alt?: string;
}

interface GalleryItemEditorProps {
  images: GalleryImage[];
  title: string;
  onUpdate: (updates: { images?: GalleryImage[]; title?: string }) => void;
}

export default function GalleryItemEditor({ images, title, onUpdate }: GalleryItemEditorProps) {
  const { t } = useTypedTranslation('admin');
  const [removeIndex, setRemoveIndex] = useState<number | null>(null);
  const { isOpen: isRemoveOpen, onOpen: onRemoveOpen, onClose: onRemoveClose } = useDisclosure();
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  const cloudfrontDomain = import.meta.env.VITE_CLOUDFRONT_DOMAIN || '';

  const handleImageUploaded = (imageKey: string) => {
    if (!imageKey) return;
    const newImages = [...images, { image_key: imageKey, alt: '' }];
    onUpdate({ images: newImages });
  };

  const handleReplaceImage = (index: number, imageKey: string) => {
    if (!imageKey) return;
    const updated = images.map((img, i) =>
      i === index ? { ...img, image_key: imageKey } : img
    );
    onUpdate({ images: updated });
  };

  const handleAltChange = (index: number, alt: string) => {
    const updated = images.map((img, i) =>
      i === index ? { ...img, alt } : img
    );
    onUpdate({ images: updated });
  };

  const handleRemoveImage = (index: number) => {
    setRemoveIndex(index);
    onRemoveOpen();
  };

  const confirmRemove = () => {
    if (removeIndex !== null) {
      const updated = images.filter((_, i) => i !== removeIndex);
      onUpdate({ images: updated });
    }
    setRemoveIndex(null);
    onRemoveClose();
  };

  const handleMoveUp = (index: number) => {
    if (index === 0) return;
    const updated = [...images];
    [updated[index - 1], updated[index]] = [updated[index], updated[index - 1]];
    onUpdate({ images: updated });
  };

  const handleMoveDown = (index: number) => {
    if (index >= images.length - 1) return;
    const updated = [...images];
    [updated[index], updated[index + 1]] = [updated[index + 1], updated[index]];
    onUpdate({ images: updated });
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
          placeholder={t('landingPage.galleryEditor.titlePlaceholder')}
          _placeholder={{ color: 'gray.500' }}
        />
      </FormControl>

      <Divider borderColor="gray.600" />

      {/* Image count */}
      {images.length > 0 && (
        <Text color="gray.400" fontSize="xs">
          {t('landingPage.galleryEditor.imageCount', { count: images.length })}
        </Text>
      )}

      {/* Images list */}
      {images.length === 0 ? (
        <Text color="gray.500" fontSize="xs" fontStyle="italic">
          {t('landingPage.galleryEditor.noItems')}
        </Text>
      ) : (
        <VStack spacing={2} align="stretch">
          {images.map((img, index) => (
            <Box
              key={index}
              bg="gray.700"
              borderRadius="md"
              border="1px solid"
              borderColor="gray.600"
              p={2}
            >
              <HStack spacing={2} align="flex-start">
                {/* Thumbnail */}
                <Box flexShrink={0} w="56px" h="56px" borderRadius="sm" overflow="hidden" bg="gray.800">
                  {img.image_key ? (
                    <Image
                      src={`https://${cloudfrontDomain}/${img.image_key}`}
                      alt={img.alt || ''}
                      w="56px"
                      h="56px"
                      objectFit="cover"
                      fallback={
                        <Box w="56px" h="56px" display="flex" alignItems="center" justifyContent="center">
                          <Icon as={FiImage} color="gray.500" boxSize={4} />
                        </Box>
                      }
                    />
                  ) : (
                    <Box w="56px" h="56px" display="flex" alignItems="center" justifyContent="center">
                      <Icon as={FiImage} color="gray.500" boxSize={4} />
                    </Box>
                  )}
                </Box>

                {/* Alt text + actions */}
                <VStack flex={1} spacing={1} align="stretch">
                  <Input
                    size="xs"
                    bg="gray.800"
                    color="white"
                    borderColor="gray.600"
                    value={img.alt || ''}
                    onChange={(e) => handleAltChange(index, e.target.value)}
                    placeholder={t('landingPage.galleryEditor.altPlaceholder')}
                    _placeholder={{ color: 'gray.500' }}
                  />
                  <HStack spacing={1} justify="flex-end">
                    <IconButton
                      aria-label={t('landingPage.editor.moveUp')}
                      icon={<TriangleUpIcon />}
                      size="xs"
                      variant="ghost"
                      color="gray.400"
                      isDisabled={index === 0}
                      onClick={() => handleMoveUp(index)}
                      _hover={{ color: 'white' }}
                    />
                    <IconButton
                      aria-label={t('landingPage.editor.moveDown')}
                      icon={<TriangleDownIcon />}
                      size="xs"
                      variant="ghost"
                      color="gray.400"
                      isDisabled={index === images.length - 1}
                      onClick={() => handleMoveDown(index)}
                      _hover={{ color: 'white' }}
                    />
                    <IconButton
                      aria-label={t('landingPage.galleryEditor.removeImage')}
                      icon={<DeleteIcon />}
                      size="xs"
                      variant="ghost"
                      color="red.400"
                      onClick={() => handleRemoveImage(index)}
                      _hover={{ color: 'red.300' }}
                    />
                  </HStack>
                </VStack>
              </HStack>
            </Box>
          ))}
        </VStack>
      )}

      <Divider borderColor="gray.600" />

      {/* Add new image via ImageUploader */}
      <ImageUploader
        label={t('landingPage.galleryEditor.addImage')}
        currentImageKey=""
        onUpload={handleImageUploaded}
      />

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
              {t('landingPage.galleryEditor.removeTitle')}
            </AlertDialogHeader>
            <AlertDialogBody color="gray.300" fontSize="sm">
              {t('landingPage.galleryEditor.removeConfirm')}
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

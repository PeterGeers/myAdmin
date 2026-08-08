/**
 * GalleryItemEditor — Inline editor for Gallery block items.
 *
 * Uses ItemListEditor in flat (non-expandable) mode for gallery images.
 * Each image shows a thumbnail, alt text field, and reorder/remove actions.
 * Uses ImageUploader for adding new images.
 */

import React from 'react';
import {
  Box, VStack, HStack, Text, Input, Image, Divider, FormControl, FormLabel,
} from '@chakra-ui/react';
import { FiImage } from 'react-icons/fi';
import { Icon } from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import ImageUploader from './ImageUploader';
import ItemListEditor from './ItemListEditor';

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
  const cloudfrontDomain = import.meta.env.VITE_CLOUDFRONT_DOMAIN || '';

  const handleImageUploaded = (imageKey: string) => {
    if (!imageKey) return;
    const newImages = [...images, { image_key: imageKey, alt: '' }];
    onUpdate({ images: newImages });
  };

  const handleAltChange = (index: number, alt: string) => {
    const updated = images.map((img, i) =>
      i === index ? { ...img, alt } : img
    );
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

      <ItemListEditor<GalleryImage>
        items={images}
        onItemsChange={(newImages) => onUpdate({ images: newImages })}
        createItem={() => ({ image_key: '', alt: '' })}
        getItemLabel={(img) => img.alt || img.image_key || ''}
        expandable={false}
        hideAddButton
        addLabel={t('landingPage.galleryEditor.addImage')}
        emptyText={t('landingPage.galleryEditor.noItems')}
        removeTitle={t('landingPage.galleryEditor.removeTitle')}
        removeConfirm={t('landingPage.galleryEditor.removeConfirm')}
        renderFlatItem={(img, index) => (
          <HStack spacing={2} align="flex-start" flex={1}>
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

            {/* Alt text */}
            <Input
              size="xs"
              bg="gray.800"
              color="white"
              borderColor="gray.600"
              flex={1}
              value={img.alt || ''}
              onChange={(e) => handleAltChange(index, e.target.value)}
              placeholder={t('landingPage.galleryEditor.altPlaceholder')}
              _placeholder={{ color: 'gray.500' }}
            />
          </HStack>
        )}
        renderItem={(img, index) => (
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
        )}
      />

      <Divider borderColor="gray.600" />

      {/* Add new image via ImageUploader */}
      <ImageUploader
        label={t('landingPage.galleryEditor.addImage')}
        currentImageKey=""
        onUpload={handleImageUploaded}
      />
    </VStack>
  );
}

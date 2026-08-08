/**
 * TestimonialsItemEditor — Inline editor for Testimonials block items.
 *
 * Uses ItemListEditor for the shared add/remove/reorder pattern.
 * Provides testimonial-specific form fields (quote, author, role).
 */

import React from 'react';
import {
  VStack, Input, Textarea, Divider, FormControl, FormLabel,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import ItemListEditor from './ItemListEditor';

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

  const handleUpdateItem = (index: number, field: keyof TestimonialItem, value: string) => {
    const updated = items.map((item, i) =>
      i === index ? { ...item, [field]: value } : item
    );
    onUpdate({ items: updated });
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

      <ItemListEditor<TestimonialItem>
        items={items}
        onItemsChange={(newItems) => onUpdate({ items: newItems })}
        createItem={() => ({ quote: '', author: '', role: '' })}
        getItemLabel={(item) => item.author || t('landingPage.testimonialsEditor.untitledItem')}
        addLabel={t('landingPage.testimonialsEditor.addItem')}
        emptyText={t('landingPage.testimonialsEditor.noItems')}
        removeTitle={t('landingPage.testimonialsEditor.removeTitle')}
        removeConfirm={t('landingPage.testimonialsEditor.removeConfirm')}
        renderItem={(item, index) => (
          <>
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
          </>
        )}
      />
    </VStack>
  );
}

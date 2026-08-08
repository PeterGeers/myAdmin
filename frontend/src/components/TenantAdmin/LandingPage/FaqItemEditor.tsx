/**
 * FaqItemEditor — Inline editor for FAQ block items.
 *
 * Uses ItemListEditor for the shared add/remove/reorder pattern.
 * Provides FAQ-specific form fields (question + answer).
 */

import React from 'react';
import {
  VStack, Input, Textarea, Divider, FormControl, FormLabel,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import ItemListEditor from './ItemListEditor';

interface FaqItem {
  question: string;
  answer: string;
}

interface FaqItemEditorProps {
  items: FaqItem[];
  title: string;
  onUpdate: (updates: { items?: FaqItem[]; title?: string }) => void;
}

export default function FaqItemEditor({ items, title, onUpdate }: FaqItemEditorProps) {
  const { t } = useTypedTranslation('admin');

  const handleUpdateItem = (index: number, field: keyof FaqItem, value: string) => {
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
          placeholder={t('landingPage.faqEditor.titlePlaceholder')}
          _placeholder={{ color: 'gray.500' }}
        />
      </FormControl>

      <Divider borderColor="gray.600" />

      <ItemListEditor<FaqItem>
        items={items}
        onItemsChange={(newItems) => onUpdate({ items: newItems })}
        createItem={() => ({ question: '', answer: '' })}
        getItemLabel={(item) => item.question || t('landingPage.faqEditor.untitledQuestion')}
        addLabel={t('landingPage.faqEditor.addItem')}
        emptyText={t('landingPage.faqEditor.noItems')}
        removeTitle={t('landingPage.faqEditor.removeTitle')}
        removeConfirm={t('landingPage.faqEditor.removeConfirm')}
        renderItem={(item, index) => (
          <>
            <FormControl>
              <FormLabel color="gray.300" fontSize="xs" mb={1}>
                {t('landingPage.faqEditor.question')}
              </FormLabel>
              <Input
                size="sm"
                bg="gray.800"
                color="white"
                borderColor="gray.600"
                value={item.question}
                onChange={(e) => handleUpdateItem(index, 'question', e.target.value)}
                placeholder={t('landingPage.faqEditor.questionPlaceholder')}
                _placeholder={{ color: 'gray.500' }}
              />
            </FormControl>

            <FormControl>
              <FormLabel color="gray.300" fontSize="xs" mb={1}>
                {t('landingPage.faqEditor.answer')}
              </FormLabel>
              <Textarea
                size="sm"
                bg="gray.800"
                color="white"
                borderColor="gray.600"
                value={item.answer}
                onChange={(e) => handleUpdateItem(index, 'answer', e.target.value)}
                placeholder={t('landingPage.faqEditor.answerPlaceholder')}
                _placeholder={{ color: 'gray.500' }}
                rows={3}
              />
            </FormControl>
          </>
        )}
      />
    </VStack>
  );
}

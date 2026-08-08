/**
 * PricingItemEditor — Inline editor for Pricing block items.
 *
 * Uses ItemListEditor for the shared add/remove/reorder pattern.
 * Provides pricing-specific form fields (name, price, description, features).
 */

import React from 'react';
import {
  VStack, Text, Input, Textarea, Divider, FormControl, FormLabel,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import ItemListEditor from './ItemListEditor';

interface PricingItem {
  name: string;
  price: string;
  description: string;
  features?: string[];
}

interface PricingItemEditorProps {
  items: PricingItem[];
  title: string;
  onUpdate: (updates: { items?: PricingItem[]; title?: string }) => void;
}

export default function PricingItemEditor({ items, title, onUpdate }: PricingItemEditorProps) {
  const { t } = useTypedTranslation('admin');

  const handleUpdateItem = (index: number, field: keyof PricingItem, value: string | string[]) => {
    const updated = items.map((item, i) =>
      i === index ? { ...item, [field]: value } : item
    );
    onUpdate({ items: updated });
  };

  const handleFeaturesChange = (index: number, value: string) => {
    const features = value.split('\n');
    handleUpdateItem(index, 'features', features);
  };

  const getFeaturesText = (features?: string[]): string => {
    return (features || []).join('\n');
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
          placeholder={t('landingPage.pricingEditor.titlePlaceholder')}
          _placeholder={{ color: 'gray.500' }}
        />
      </FormControl>

      <Divider borderColor="gray.600" />

      <ItemListEditor<PricingItem>
        items={items}
        onItemsChange={(newItems) => onUpdate({ items: newItems })}
        createItem={() => ({ name: '', price: '', description: '', features: [] })}
        getItemLabel={(item) => item.name || t('landingPage.pricingEditor.untitledItem')}
        addLabel={t('landingPage.pricingEditor.addItem')}
        emptyText={t('landingPage.pricingEditor.noItems')}
        removeTitle={t('landingPage.pricingEditor.removeTitle')}
        removeConfirm={t('landingPage.pricingEditor.removeConfirm')}
        renderItem={(item, index) => (
          <>
            <FormControl>
              <FormLabel color="gray.300" fontSize="xs" mb={1}>
                {t('landingPage.pricingEditor.name')}
              </FormLabel>
              <Input
                size="sm"
                bg="gray.800"
                color="white"
                borderColor="gray.600"
                value={item.name}
                onChange={(e) => handleUpdateItem(index, 'name', e.target.value)}
                placeholder={t('landingPage.pricingEditor.namePlaceholder')}
                _placeholder={{ color: 'gray.500' }}
              />
            </FormControl>

            <FormControl>
              <FormLabel color="gray.300" fontSize="xs" mb={1}>
                {t('landingPage.pricingEditor.price')}
              </FormLabel>
              <Input
                size="sm"
                bg="gray.800"
                color="white"
                borderColor="gray.600"
                value={item.price}
                onChange={(e) => handleUpdateItem(index, 'price', e.target.value)}
                placeholder={t('landingPage.pricingEditor.pricePlaceholder')}
                _placeholder={{ color: 'gray.500' }}
              />
            </FormControl>

            <FormControl>
              <FormLabel color="gray.300" fontSize="xs" mb={1}>
                {t('landingPage.pricingEditor.description')}
              </FormLabel>
              <Textarea
                size="sm"
                bg="gray.800"
                color="white"
                borderColor="gray.600"
                value={item.description}
                onChange={(e) => handleUpdateItem(index, 'description', e.target.value)}
                placeholder={t('landingPage.pricingEditor.descriptionPlaceholder')}
                _placeholder={{ color: 'gray.500' }}
                rows={2}
              />
            </FormControl>

            <FormControl>
              <FormLabel color="gray.300" fontSize="xs" mb={1}>
                {t('landingPage.pricingEditor.features')}
              </FormLabel>
              <Textarea
                size="sm"
                bg="gray.800"
                color="white"
                borderColor="gray.600"
                value={getFeaturesText(item.features)}
                onChange={(e) => handleFeaturesChange(index, e.target.value)}
                placeholder={t('landingPage.pricingEditor.featuresPlaceholder')}
                _placeholder={{ color: 'gray.500' }}
                rows={3}
              />
              <Text color="gray.500" fontSize="xs" mt={1}>
                {t('landingPage.pricingEditor.featuresHelp')}
              </Text>
            </FormControl>
          </>
        )}
      />
    </VStack>
  );
}

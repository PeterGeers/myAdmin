/**
 * BudgetLineToolbar — Page header with version selector and action buttons.
 */

import React from 'react';
import { Flex, Text, HStack, Select, Button } from '@chakra-ui/react';
import { AddIcon, CopyIcon, StarIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { BudgetLineToolbarProps } from './types';

const BudgetLineToolbar: React.FC<BudgetLineToolbarProps> = ({
  versions,
  selectedVersionId,
  onVersionChange,
  isDraftVersion,
  onAddLine,
  onGenerateDraft,
  onCopyBudget,
  onAISuggestions,
}) => {
  const { t } = useTypedTranslation('budget');

  return (
    <Flex justify="space-between" align="center" mb={4} wrap="wrap" gap={2}>
      <Text fontSize="xl" fontWeight="bold" color="white">{t('titles.lines')}</Text>
      <HStack spacing={2} wrap="wrap">
        <Select
          size="sm"
          w="220px"
          bg="whiteAlpha.100"
          color="white"
          value={selectedVersionId || ''}
          onChange={(e) => onVersionChange(Number(e.target.value))}
        >
          {versions.map((v) => (
            <option key={v.id} value={v.id} style={{ color: 'black' }}>
              {v.name} ({v.fiscal_year})
            </option>
          ))}
        </Select>
        <Button leftIcon={<AddIcon />} size="sm" colorScheme="orange" onClick={onAddLine}>
          {t('buttons.addLine')}
        </Button>
        <Button size="sm" colorScheme="orange" onClick={onGenerateDraft}>
          {t('buttons.generateDraft')}
        </Button>
        <Button leftIcon={<CopyIcon />} size="sm" colorScheme="orange" onClick={onCopyBudget}>
          {t('buttons.copyBudget')}
        </Button>
        {isDraftVersion && (
          <Button leftIcon={<StarIcon />} size="sm" colorScheme="blue" onClick={onAISuggestions}>
            {t('buttons.aiSuggestions')}
          </Button>
        )}
      </HStack>
    </Flex>
  );
};

export default BudgetLineToolbar;

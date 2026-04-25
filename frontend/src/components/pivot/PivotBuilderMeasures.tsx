/**
 * PivotBuilderMeasures Component
 *
 * Aggregate measure picker for the PivotBuilder. Allows users to add, remove,
 * and configure aggregate measures (function + column pairs).
 *
 * Requirements: 1.4, 1.5, 1.8
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §4 PivotBuilder
 */

import React from 'react';
import {
  Box,
  Button,
  Flex,
  FormControl,
  FormLabel,
  HStack,
  IconButton,
  Select,
  Text,
} from '@chakra-ui/react';
import { AddIcon, CloseIcon } from '@chakra-ui/icons';
import type {
  AggregateMeasure,
  AggregateFunction,
  ColumnDef,
} from '../../types/pivot';
import { MAX_AGGREGATE_MEASURES } from './usePivotConfig';

export interface PivotBuilderMeasuresProps {
  measures: AggregateMeasure[];
  aggregatableColumns: ColumnDef[];
  aggregateFunctions: AggregateFunction[];
  onAdd: () => void;
  onRemove: (index: number) => void;
  onUpdate: (index: number, measure: AggregateMeasure) => void;
  t: (key: string, options?: Record<string, any>) => string;
  disabled?: boolean;
}

export function PivotBuilderMeasures({
  measures,
  aggregatableColumns,
  aggregateFunctions,
  onAdd,
  onRemove,
  onUpdate,
  t,
  disabled = false,
}: PivotBuilderMeasuresProps): React.ReactElement {
  return (
    <Box>
      <FormControl>
        <FormLabel color="white" fontSize="sm">
          {t('pivot.builder.aggregateMeasures')}
        </FormLabel>
        {measures.map((measure, index) => (
          <HStack key={index} spacing={2} mb={2}>
            <Select
              size="sm"
              bg="gray.600"
              color="white"
              value={measure.function}
              onChange={(e) =>
                onUpdate(index, {
                  ...measure,
                  function: e.target.value as AggregateFunction,
                })
              }
              disabled={disabled}
              minW="120px"
              maxW="140px"
              aria-label={t('pivot.builder.aggregateFunction')}
              sx={{ '& option': { bg: 'white', color: 'black' } }}
            >
              {aggregateFunctions.map((fn) => (
                <option key={fn} value={fn}>
                  {t(`pivot.functions.${fn}`)}
                </option>
              ))}
            </Select>
            <Select
              size="sm"
              bg="gray.600"
              color="white"
              value={measure.column}
              onChange={(e) =>
                onUpdate(index, { ...measure, column: e.target.value })
              }
              placeholder={t('pivot.builder.aggregateColumn')}
              disabled={disabled}
              flex={1}
              aria-label={t('pivot.builder.aggregateColumn')}
              sx={{
                '& option': { bg: 'white', color: 'black' },
                '&:not(:placeholder-shown)': { bg: 'orange.500', color: 'white' },
              }}
            >
              {/* COUNT can use * */}
              {measure.function === 'COUNT' && (
                <option value="*">* (all rows)</option>
              )}
              {aggregatableColumns.map((col) => (
                <option key={col.name} value={col.name}>
                  {col.label}
                </option>
              ))}
            </Select>
            <IconButton
              aria-label={t('pivot.builder.removeMeasure')}
              icon={<CloseIcon />}
              size="sm"
              variant="ghost"
              colorScheme="red"
              onClick={() => onRemove(index)}
              disabled={disabled}
            />
          </HStack>
        ))}
        <Flex justify="space-between" align="center" mt={1}>
          <Button
            size="sm"
            variant="ghost"
            colorScheme="orange"
            leftIcon={<AddIcon />}
            onClick={onAdd}
            disabled={disabled || measures.length >= MAX_AGGREGATE_MEASURES}
          >
            {t('pivot.builder.addMeasure')}
          </Button>
          {measures.length > 0 && (
            <Text fontSize="xs" color="gray.400">
              {measures.length}/{MAX_AGGREGATE_MEASURES}
            </Text>
          )}
        </Flex>
      </FormControl>
    </Box>
  );
}

export default PivotBuilderMeasures;

/**
 * PivotBuilder Component
 *
 * Main configuration UI for Dynamic Pivot Views. Composes data source selector,
 * column pickers, filter panel, aggregate measure picker, and saved model
 * management into a cohesive builder interface.
 *
 * Requirements: 1.1–1.8, 2.1–2.5, 4.1, 5.1–5.6, 9.1, 9.3, 9.5, 9.8, 9.10, 9.11
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §4 PivotBuilder
 */

import React, { useCallback, useMemo } from 'react';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  ButtonGroup,
  Flex,
  FormControl,
  FormLabel,
  HStack,
  IconButton,
  Select,
  Spinner,
  Tag,
  TagLabel,
  Text,
  VStack,
  Wrap,
  WrapItem,
} from '@chakra-ui/react';
import { ArrowUpIcon, ArrowDownIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import type {
  DataSourceModule,
  PivotConfig,
  PivotResult,
} from '../../types/pivot';
import { usePivotConfig } from './usePivotConfig';
import { GenericFilter } from '../filters/GenericFilter';
import { PivotBuilderMeasures } from './PivotBuilderMeasures';
import { PivotBuilderFilters } from './PivotBuilderFilters';
import { PivotBuilderModels } from './PivotBuilderModels';
import { executePivot } from '../../services/pivotService';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PivotBuilderProps {
  /** Optional module filter to restrict data sources (e.g., 'FIN' for financial tab) */
  moduleFilter?: DataSourceModule | null;
  /** Callback when pivot results are available */
  onResults?: (result: PivotResult) => void;
  /** Callback when config changes (for parent state sync) */
  onConfigChange?: (config: PivotConfig) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PivotBuilder({
  moduleFilter,
  onResults,
  onConfigChange,
}: PivotBuilderProps): React.ReactElement {
  const { t } = useTypedTranslation('reports');

  // Translate a database column name to a human-readable label
  const getColumnLabel = useCallback(
    (name: string) => {
      const translated = t(`pivot.columnLabels.${name}`, { defaultValue: '' });
      return translated || name;
    },
    [t],
  );

  const {
    dataSources,
    dataSourcesLoading,
    columns,
    columnsLoading,
    columnsError,
    config,
    setConfig,
    setDataSource,
    setGroupColumns,
    addAggregateMeasure,
    removeAggregateMeasure,
    updateAggregateMeasure,
    setColumnPivot,
    setColumnNestLevels,
    setDisplayMode,
    updateFilter,
    validation,
    isValid,
    aggregateFunctions,
    availableForGrouping,
    availableForPivot,
    availableForNesting,
  } = usePivotConfig({ moduleFilter });

  const [executing, setExecuting] = React.useState(false);
  const [executeError, setExecuteError] = React.useState<string | null>(null);

  // Notify parent of config changes
  React.useEffect(() => {
    onConfigChange?.(config);
  }, [config, onConfigChange]);

  // -----------------------------------------------------------------------
  // Execute pivot query
  // -----------------------------------------------------------------------
  const handleExecute = useCallback(async () => {
    if (!isValid) return;
    setExecuting(true);
    setExecuteError(null);
    try {
      const result = await executePivot(config);
      onResults?.(result);
    } catch (err) {
      setExecuteError(
        err instanceof Error ? err.message : t('pivot.errors.executeFailed'),
      );
    } finally {
      setExecuting(false);
    }
  }, [isValid, config, onResults, t]);

  // -----------------------------------------------------------------------
  // Load model callback — sets full config from saved model
  // -----------------------------------------------------------------------
  const handleLoadModel = useCallback(
    (modelConfig: PivotConfig) => {
      setConfig(modelConfig);
    },
    [setConfig],
  );

  // -----------------------------------------------------------------------
  // Validation messages
  // -----------------------------------------------------------------------
  const validationMessages = useMemo(() => {
    const msgs: string[] = [];
    if (validation.groupColumns) {
      msgs.push(t(`pivot.validation.${validation.groupColumns}`));
    }
    if (validation.aggregateMeasures) {
      msgs.push(t(`pivot.validation.${validation.aggregateMeasures}`));
    }
    if (validation.columnRoleOverlap) {
      msgs.push(
        t('pivot.validation.columnRoleOverlap', {
          column: validation.columnRoleOverlap,
        }),
      );
    }
    return msgs;
  }, [validation, t]);

  // Show display mode toggle only when 2+ group columns
  const showDisplayModeToggle = config.groupColumns.length >= 2;

  return (
    <Box>
      {/* Header row with title and action buttons */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="lg" fontWeight="bold" color="white">
          {t('pivot.builder.title')}
        </Text>
        <Flex gap={2} align="center" wrap="wrap">
          <PivotBuilderModels
            config={config}
            isValid={isValid}
            onLoadModel={handleLoadModel}
            t={t}
          />
          <Button
            colorScheme="orange"
            size="sm"
            onClick={handleExecute}
            isLoading={executing}
            disabled={!isValid || executing}
          >
            {t('pivot.actions.execute')}
          </Button>
        </Flex>
      </Flex>

      {/* Error display */}
      {executeError && (
        <Alert status="error" mb={3} borderRadius="md" bg="red.900" borderColor="red.600" borderWidth="1px">
          <AlertIcon color="red.300" />
          <Text fontSize="sm" color="red.200">{executeError}</Text>
        </Alert>
      )}

      {/* Validation messages */}
      {validationMessages.length > 0 && config.dataSource && (
        <Alert status="warning" mb={3} borderRadius="md" bg="orange.900" borderColor="orange.600" borderWidth="1px">
          <AlertIcon color="orange.300" />
          <VStack align="start" spacing={0}>
            {validationMessages.map((msg, i) => (
              <Text key={i} fontSize="sm" color="orange.200">
                {msg}
              </Text>
            ))}
          </VStack>
        </Alert>
      )}

      <VStack spacing={4} align="stretch">
        {/* Row 1: Data source selector */}
        <Flex wrap="wrap" gap={4} align="end">
          <FormControl maxW="280px">
            <FormLabel color="white" fontSize="sm">
              {t('pivot.builder.dataSource')}
            </FormLabel>
            {dataSourcesLoading ? (
              <Spinner size="sm" color="orange.400" />
            ) : (
              <Select
                size="sm"
                bg="gray.600"
                color="white"
                value={config.dataSource}
                onChange={(e) => setDataSource(e.target.value)}
                placeholder={t('pivot.builder.selectDataSource')}
                aria-label={t('pivot.builder.dataSource')}
                sx={{
                  '& option': { bg: 'white', color: 'black' },
                  '&:not(:placeholder-shown)': {
                    bg: 'orange.500',
                    color: 'white',
                  },
                }}
              >
                {dataSources.map((ds) => (
                  <option key={ds.name} value={ds.name}>
                    {ds.label || ds.name}
                  </option>
                ))}
              </Select>
            )}
          </FormControl>

          {/* Display mode toggle — only when 2+ group columns */}
          {showDisplayModeToggle && (
            <FormControl maxW="220px">
              <FormLabel color="white" fontSize="sm">
                {t('pivot.builder.displayMode')}
              </FormLabel>
              <ButtonGroup size="sm" isAttached variant="outline">
                <Button
                  colorScheme={config.displayMode === 'flat' ? 'orange' : 'gray'}
                  variant={config.displayMode === 'flat' ? 'solid' : 'outline'}
                  onClick={() => setDisplayMode('flat')}
                  color="white"
                >
                  {t('pivot.builder.flat')}
                </Button>
                <Button
                  colorScheme={
                    config.displayMode === 'hierarchical' ? 'orange' : 'gray'
                  }
                  variant={
                    config.displayMode === 'hierarchical' ? 'solid' : 'outline'
                  }
                  onClick={() => setDisplayMode('hierarchical')}
                  color="white"
                >
                  {t('pivot.builder.hierarchical')}
                </Button>
              </ButtonGroup>
            </FormControl>
          )}
        </Flex>

        {/* Row 2: Filters — one per groupable column, fully dynamic */}
        {config.dataSource && !columnsLoading && (
          <PivotBuilderFilters
            groupableColumns={columns.groupable}
            filters={config.filters}
            onFilterChange={updateFilter}
            t={t}
          />
        )}

        {/* Row 3: Column pickers — only when columns are loaded */}
        {config.dataSource && (
          <Flex wrap="wrap" gap={4} align="start">
            {columnsLoading ? (
              <Spinner size="sm" color="orange.400" />
            ) : columnsError ? (
              <Alert status="error" borderRadius="md" maxW="400px" bg="red.900" borderColor="red.600" borderWidth="1px">
                <AlertIcon color="red.300" />
                <Text fontSize="sm" color="red.200">{columnsError}</Text>
              </Alert>
            ) : (
              <>
                {/* Group columns — multi-select with reorder */}
                <Box minW="200px" flex={1} maxW="300px">
                  <GenericFilter<string>
                    label={t('pivot.builder.groupColumns')}
                    values={config.groupColumns}
                    onChange={(vals) => setGroupColumns(vals as string[])}
                    availableOptions={availableForGrouping.map((c) => c.name)}
                    multiSelect
                    placeholder={t('pivot.builder.selectGroupColumns')}
                    size="sm"
                    getOptionLabel={(name) => getColumnLabel(name)}
                    getOptionValue={(name) => name}
                    labelColor="white"
                    bg="gray.600"
                    color="white"
                  />
                  {config.groupColumns.length > 1 && (
                    <Wrap spacing={1} mt={2}>
                      {config.groupColumns.map((name, idx) => {
                        const label = getColumnLabel(name);
                        return (
                          <WrapItem key={name}>
                            <Tag size="sm" colorScheme="orange" variant="subtle">
                              <HStack spacing={0}>
                                <IconButton
                                  aria-label="Move up"
                                  icon={<ArrowUpIcon />}
                                  size="xs"
                                  variant="ghost"
                                  colorScheme="orange"
                                  isDisabled={idx === 0}
                                  onClick={() => {
                                    const arr = [...config.groupColumns];
                                    [arr[idx - 1], arr[idx]] = [arr[idx], arr[idx - 1]];
                                    setGroupColumns(arr);
                                  }}
                                  minW="18px"
                                  h="18px"
                                />
                                <TagLabel fontSize="xs">{label}</TagLabel>
                                <IconButton
                                  aria-label="Move down"
                                  icon={<ArrowDownIcon />}
                                  size="xs"
                                  variant="ghost"
                                  colorScheme="orange"
                                  isDisabled={idx === config.groupColumns.length - 1}
                                  onClick={() => {
                                    const arr = [...config.groupColumns];
                                    [arr[idx], arr[idx + 1]] = [arr[idx + 1], arr[idx]];
                                    setGroupColumns(arr);
                                  }}
                                  minW="18px"
                                  h="18px"
                                />
                              </HStack>
                            </Tag>
                          </WrapItem>
                        );
                      })}
                    </Wrap>
                  )}
                  {config.groupColumns.length > 0 && (
                    <Text fontSize="xs" color="gray.400" mt={1}>
                      {config.groupColumns.length}/5
                    </Text>
                  )}
                </Box>

                {/* Aggregate measures */}
                <Box minW="280px" flex={1} maxW="420px">
                  <PivotBuilderMeasures
                    measures={config.aggregateMeasures}
                    aggregatableColumns={columns.aggregatable}
                    aggregateFunctions={aggregateFunctions}
                    onAdd={addAggregateMeasure}
                    onRemove={removeAggregateMeasure}
                    onUpdate={updateAggregateMeasure}
                    t={t}
                  />
                </Box>

                {/* Column pivot — optional single select */}
                <Box minW="200px" flex={1} maxW="260px">
                  <GenericFilter<string>
                    label={t('pivot.builder.columnPivot')}
                    values={config.columnPivot ? [config.columnPivot] : []}
                    onChange={(vals) =>
                      setColumnPivot(
                        (vals as string[]).length > 0
                          ? (vals as string[])[0]
                          : null,
                      )
                    }
                    availableOptions={availableForPivot.map((c) => c.name)}
                    placeholder={t('pivot.builder.selectColumnPivot')}
                    size="sm"
                    getOptionLabel={(name) => getColumnLabel(name)}
                    getOptionValue={(name) => name}
                    labelColor="white"
                    bg="gray.600"
                    color="white"
                  />
                </Box>

                {/* Column nest levels — multi-select, only when pivot is set */}
                {config.columnPivot && (
                  <Box minW="200px" flex={1} maxW="300px">
                    <GenericFilter<string>
                      label={t('pivot.builder.columnNestLevels')}
                      values={config.columnNestLevels}
                      onChange={(vals) =>
                        setColumnNestLevels(vals as string[])
                      }
                      availableOptions={availableForNesting.map((c) => c.name)}
                      multiSelect
                      placeholder={t('pivot.builder.selectNestLevels')}
                      size="sm"
                      getOptionLabel={(name) => getColumnLabel(name)}
                      getOptionValue={(name) => name}
                      labelColor="white"
                      bg="gray.600"
                      color="white"
                    />
                    {config.columnNestLevels.length > 0 && (
                      <Text fontSize="xs" color="gray.400" mt={1}>
                        {config.columnNestLevels.length}/5
                      </Text>
                    )}
                  </Box>
                )}
              </>
            )}
          </Flex>
        )}
      </VStack>
    </Box>
  );
}

export default PivotBuilder;

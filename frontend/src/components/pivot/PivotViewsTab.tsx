/**
 * PivotViewsTab Component
 *
 * A consumer-facing pivot view for report tabs (FIN, STR). Users pick a
 * saved pivot model from a dropdown, optionally adjust filter values on
 * the model's group columns, then execute to see results.
 *
 * The model structure (group columns, aggregates, data source) is locked —
 * only filter values are editable. This keeps things simple for end users
 * while giving them flexibility to slice the data differently.
 *
 * Parameterized by `moduleFilter` so any report group (FIN, STR, ZZP, ADMIN)
 * can reuse the same component.
 *
 * Requirements: 3.4, 5.1, 5.2
 * Reference: .kiro/specs/dynamic-pivot-views/tasks.md §11.3, §11.4
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Divider,
  Flex,
  Select,
  Spinner,
  Text,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import {
  listPivotModels,
  loadPivotModel,
  executePivot,
  getRegisteredSources,
  getAvailableColumns,
  filterSourcesByModule,
} from '../../services/pivotService';
import { PivotBuilderFilters } from './PivotBuilderFilters';
import { PivotResultTable } from './PivotResultTable';
import type {
  DataSourceModule,
  PivotConfig,
  PivotModel,
  PivotModelSummary,
  PivotResult,
  ColumnDef,
} from '../../types/pivot';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PivotViewsTabProps {
  /** Module filter to restrict which saved models are shown (e.g. 'FIN', 'STR') */
  moduleFilter: DataSourceModule;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PivotViewsTab({ moduleFilter }: PivotViewsTabProps): React.ReactElement {
  const { t } = useTypedTranslation('reports');

  // Model list state
  const [filteredModels, setFilteredModels] = useState<PivotModelSummary[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelsError, setModelsError] = useState<string | null>(null);

  // Selected model state
  const [selectedModelId, setSelectedModelId] = useState<number | null>(null);
  const [loadedModel, setLoadedModel] = useState<PivotModel | null>(null);
  const [modelLoading, setModelLoading] = useState(false);

  // Filter state — user can adjust filters on the loaded model's columns
  const [filters, setFilters] = useState<Record<string, any>>({});
  const [groupableColumns, setGroupableColumns] = useState<ColumnDef[]>([]);

  // Execution state
  const [result, setResult] = useState<PivotResult | null>(null);
  const [executing, setExecuting] = useState(false);
  const [executeError, setExecuteError] = useState<string | null>(null);

  // -----------------------------------------------------------------------
  // Load registered sources + saved models on mount
  // -----------------------------------------------------------------------

  useEffect(() => {
    let cancelled = false;

    (async () => {
      setModelsLoading(true);
      setModelsError(null);
      try {
        // Fetch registered sources and filter by module
        const allSources = await getRegisteredSources();
        const filtered = filterSourcesByModule(allSources, moduleFilter);
        const sourceNames = filtered.map((s) => s.name);

        // Fetch all saved models for this tenant
        const allModels = await listPivotModels();

        if (!cancelled) {
          // Filter models whose data_source matches this module's sources
          const matching = allModels.filter((m) => sourceNames.includes(m.data_source));
          setFilteredModels(matching);
        }
      } catch (err: any) {
        if (!cancelled) {
          setModelsError(err.message || t('pivot.errors.loadFailed'));
        }
      } finally {
        if (!cancelled) {
          setModelsLoading(false);
        }
      }
    })();

    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleFilter]);

  // -----------------------------------------------------------------------
  // Load selected model + available columns for its data source
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (selectedModelId == null) {
      setLoadedModel(null);
      setFilters({});
      setGroupableColumns([]);
      setResult(null);
      setExecuteError(null);
      return;
    }

    let cancelled = false;

    (async () => {
      setModelLoading(true);
      setExecuteError(null);
      try {
        const model = await loadPivotModel(selectedModelId);
        if (cancelled) return;

        setLoadedModel(model);
        // Seed filters from the model's saved filter values
        setFilters(model.definition.filters ?? {});

        // Fetch column definitions for the model's data source so we can
        // render filter labels properly
        const cols = await getAvailableColumns(model.definition.dataSource);
        if (cancelled) return;

        setGroupableColumns(cols.groupable);
      } catch (err: any) {
        if (!cancelled) {
          setModelsError(err.message || t('pivot.errors.loadFailed'));
        }
      } finally {
        if (!cancelled) {
          setModelLoading(false);
        }
      }
    })();

    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModelId]);

  // -----------------------------------------------------------------------
  // Filter change handler
  // -----------------------------------------------------------------------

  const handleFilterChange = useCallback((columnName: string, value: any) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (value == null || value === '') {
        delete next[columnName];
      } else {
        next[columnName] = value;
      }
      return next;
    });
  }, []);

  // -----------------------------------------------------------------------
  // Execute pivot with the loaded model config + user filter overrides
  // -----------------------------------------------------------------------

  const handleExecute = useCallback(async () => {
    if (!loadedModel) return;

    setExecuting(true);
    setExecuteError(null);
    try {
      const config: PivotConfig = {
        ...loadedModel.definition,
        filters,
      };
      const res = await executePivot(config);
      setResult(res);
    } catch (err: any) {
      setExecuteError(err.message || t('pivot.errors.executeFailed'));
    } finally {
      setExecuting(false);
    }
  }, [loadedModel, filters, t]);

  // -----------------------------------------------------------------------
  // Build the effective config for PivotResultTable (model config + user filters)
  // -----------------------------------------------------------------------

  const effectiveConfig = useMemo<PivotConfig | null>(() => {
    if (!loadedModel) return null;
    return { ...loadedModel.definition, filters };
  }, [loadedModel, filters]);

  // -----------------------------------------------------------------------
  // Render — single root element to avoid React removeChild errors when
  // the component transitions between loading / error / empty / data states.
  // -----------------------------------------------------------------------

  return (
    <Box>
      {/* Loading state for initial model list */}
      {modelsLoading && (
        <Flex justify="center" align="center" py={8}>
          <Spinner size="lg" color="orange.300" />
        </Flex>
      )}

      {/* Error loading models */}
      {!modelsLoading && modelsError && (
        <Alert status="error" borderRadius="md">
          <AlertIcon />
          {modelsError}
        </Alert>
      )}

      {/* No saved models for this module */}
      {!modelsLoading && !modelsError && filteredModels.length === 0 && (
        <Alert status="info" borderRadius="md">
          <AlertIcon />
          {t('pivot.models.noModels')}
        </Alert>
      )}

      {/* Main content — model selector, filters, results */}
      {!modelsLoading && !modelsError && filteredModels.length > 0 && (
        <>
          {/* Model selector + Execute button */}
          <Flex gap={3} align="flex-end" mb={4} wrap="wrap">
            <Box flex="1" minW="250px" maxW="400px">
              <Text fontSize="sm" color="gray.400" mb={1}>
                {t('pivot.models.selectModel')}
              </Text>
              <Select
                placeholder={t('pivot.models.selectModel')}
                value={selectedModelId ?? ''}
                onChange={(e) => {
                  const val = e.target.value;
                  setSelectedModelId(val ? Number(val) : null);
                }}
                bg="gray.700"
                color="white"
                borderColor="gray.600"
                size="sm"
              >
                {filteredModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </Select>
            </Box>

            <Button
              colorScheme="orange"
              size="sm"
              onClick={handleExecute}
              isLoading={executing}
              isDisabled={!loadedModel || executing}
            >
              {t('pivot.actions.execute')}
            </Button>
          </Flex>

          {/* Loading indicator while fetching model details */}
          {modelLoading && (
            <Flex justify="center" py={4}>
              <Spinner size="md" color="orange.300" />
            </Flex>
          )}

          {/* Filter controls for the loaded model's group columns */}
          {loadedModel && !modelLoading && groupableColumns.length > 0 && (
            <Box mb={4}>
              <PivotBuilderFilters
                groupableColumns={groupableColumns}
                filters={filters}
                onFilterChange={handleFilterChange}
                t={t}
              />
            </Box>
          )}

          {/* Execution error */}
          {executeError && (
            <Alert status="error" borderRadius="md" mb={4}>
              <AlertIcon />
              {executeError}
            </Alert>
          )}

          {/* Results */}
          {result && effectiveConfig && (
            <>
              <Divider my={4} borderColor="gray.600" />
              <PivotResultTable
                data={result.data || []}
                columns={result.columns || []}
                config={effectiveConfig}
                isLoading={executing}
              />
            </>
          )}
        </>
      )}
    </Box>
  );
}

export default PivotViewsTab;

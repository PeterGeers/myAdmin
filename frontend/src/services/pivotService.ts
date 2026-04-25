/**
 * Pivot API Service
 *
 * Client-side functions for the Dynamic Pivot Views API.
 * Uses authenticatedGet/Post/Put/Delete from apiService.ts.
 *
 * Requirements: 3.1, 4.1, 5.1, 5.2, 5.3, 11.6, 11.7
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §6
 */

import {
  authenticatedGet,
  authenticatedPost,
  authenticatedPut,
  authenticatedDelete,
  buildEndpoint,
} from './apiService';
import type {
  PivotConfig,
  PivotResult,
  AvailableColumns,
  PivotModelSummary,
  PivotModel,
  PivotDataSource,
  DataSourceModule,
  SaveModelResponse,
  ExportResponse,
} from '../types/pivot';

const BASE = '/api/pivot';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Parse a JSON response body, throwing a descriptive error on failure.
 */
async function parseJsonResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed with status ${res.status}`);
  }
  return res.json();
}

/**
 * Convert a frontend PivotConfig (camelCase) to the backend request body
 * (snake_case) expected by POST /api/pivot/execute and /api/pivot/export.
 */
function toBackendConfig(config: PivotConfig): Record<string, any> {
  return {
    data_source: config.dataSource,
    group_columns: config.groupColumns,
    aggregate_measures: config.aggregateMeasures,
    filters: config.filters,
    column_pivot: config.columnPivot,
    column_nest_levels: config.columnNestLevels,
    include_rollup: config.includeRollup ?? false,
  };
}

// ---------------------------------------------------------------------------
// Data source discovery
// ---------------------------------------------------------------------------

/**
 * Fetch the list of registered pivot data sources from the backend.
 * Each source includes its name, label, and module tag.
 */
export async function getRegisteredSources(): Promise<PivotDataSource[]> {
  const res = await authenticatedGet(buildEndpoint(`${BASE}/sources`));
  const json = await parseJsonResponse<{ success: boolean; data: PivotDataSource[] }>(res);
  return json.data;
}

/**
 * Filter data sources by module context.
 *
 * When moduleFilter is provided (e.g. 'FIN'), returns only sources
 * tagged with that module. When moduleFilter is undefined/null (e.g.
 * TenantAdmin dashboard), returns ALL registered sources.
 *
 * Requirements: 11.6, 11.7
 */
export function filterSourcesByModule(
  sources: PivotDataSource[],
  moduleFilter?: DataSourceModule | null,
): PivotDataSource[] {
  if (!moduleFilter) {
    return sources;
  }
  return sources.filter((s) => s.module === moduleFilter);
}

// ---------------------------------------------------------------------------
// Column discovery
// ---------------------------------------------------------------------------

/**
 * Fetch available columns (groupable + aggregatable) for a data source.
 * Columns are resolved per the AllowedColumnsRegistry for the current tenant.
 */
export async function getAvailableColumns(dataSource: string): Promise<AvailableColumns> {
  const res = await authenticatedGet(buildEndpoint(`${BASE}/columns/${dataSource}`));
  const json = await parseJsonResponse<{ success: boolean; groupable: AvailableColumns['groupable']; aggregatable: AvailableColumns['aggregatable'] }>(res);
  return {
    groupable: json.groupable,
    aggregatable: json.aggregatable,
  };
}

// ---------------------------------------------------------------------------
// Query execution
// ---------------------------------------------------------------------------

/**
 * Execute a pivot query and return aggregated results.
 */
export async function executePivot(config: PivotConfig): Promise<PivotResult> {
  const res = await authenticatedPost(
    buildEndpoint(`${BASE}/execute`),
    toBackendConfig(config),
  );
  return parseJsonResponse<PivotResult>(res);
}

/**
 * Export the underlying (non-aggregated) dataset for a pivot configuration.
 * Returns raw rows matching the current filters without GROUP BY.
 */
export async function exportUnderlying(config: PivotConfig): Promise<ExportResponse> {
  const res = await authenticatedPost(
    buildEndpoint(`${BASE}/export`),
    toBackendConfig(config),
  );
  return parseJsonResponse<ExportResponse>(res);
}

// ---------------------------------------------------------------------------
// Pivot model CRUD
// ---------------------------------------------------------------------------

/**
 * List all saved pivot models for the current tenant.
 */
export async function listPivotModels(): Promise<PivotModelSummary[]> {
  const res = await authenticatedGet(buildEndpoint(`${BASE}/models`));
  const json = await parseJsonResponse<{ success: boolean; data: PivotModelSummary[] }>(res);
  return json.data;
}

/**
 * Load a specific saved pivot model by ID.
 */
export async function loadPivotModel(id: number): Promise<PivotModel> {
  const res = await authenticatedGet(buildEndpoint(`${BASE}/models/${id}`));
  return parseJsonResponse<PivotModel>(res);
}

/**
 * Save a new pivot model with the given name and configuration.
 */
export async function savePivotModel(
  name: string,
  definition: PivotConfig,
): Promise<SaveModelResponse> {
  const res = await authenticatedPost(buildEndpoint(`${BASE}/models`), {
    name,
    definition: toBackendConfig(definition),
  });
  return parseJsonResponse<SaveModelResponse>(res);
}

/**
 * Update an existing pivot model's definition.
 */
export async function updatePivotModel(
  id: number,
  definition: PivotConfig,
): Promise<void> {
  const res = await authenticatedPut(buildEndpoint(`${BASE}/models/${id}`), {
    definition: toBackendConfig(definition),
  });
  await parseJsonResponse<{ success: boolean }>(res);
}

/**
 * Delete a saved pivot model.
 */
export async function deletePivotModel(id: number): Promise<void> {
  const res = await authenticatedDelete(buildEndpoint(`${BASE}/models/${id}`));
  await parseJsonResponse<{ success: boolean }>(res);
}

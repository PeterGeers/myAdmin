/**
 * Budget Management API Service
 *
 * Service layer for interacting with the Budget Management backend API.
 * Covers versions, templates, lines, draft generation, copy, dashboard, and AI features.
 */

import {
  BudgetVersion,
  BudgetTemplate,
  BudgetTemplateWithLines,
  BudgetLine,
  DashboardData,
  DashboardLevel,
  DashboardPeriod,
  CreateVersionRequest,
  StatusTransitionRequest,
  CreateTemplateRequest,
  CreateBudgetLineRequest,
  GenerateDraftRequest,
  GenerateDraftData,
  CopyBudgetRequest,
  CopyBudgetData,
  AINarrativeRequest,
  AINarrativeData,
  AIQueryRequest,
  AIQueryData,
  AIDraftSuggestionsRequest,
  AIDraftSuggestionsData,
  AITemplateRecommendRequest,
  AITemplateRecommendData,
  ApiResponse,
} from '../types/budget';
import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete } from './apiService';

// ─── Budget Versions ─────────────────────────────────────────────────────────

/**
 * List budget versions, optionally filtered by fiscal year
 */
export const listVersions = async (year?: number): Promise<ApiResponse<BudgetVersion[]>> => {
  const endpoint = year
    ? `/api/budget/versions?year=${year}`
    : '/api/budget/versions';

  const response = await authenticatedGet(endpoint);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to list budget versions');
  }

  return response.json();
};

/**
 * Create a new budget version
 */
export const createVersion = async (data: CreateVersionRequest): Promise<ApiResponse<BudgetVersion>> => {
  const response = await authenticatedPost('/api/budget/versions', data);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to create budget version');
  }

  return response.json();
};

/**
 * Transition a budget version status (approve or revise)
 */
export const transitionVersionStatus = async (
  versionId: number,
  data: StatusTransitionRequest
): Promise<ApiResponse<BudgetVersion>> => {
  const response = await authenticatedPut(`/api/budget/versions/${versionId}/status`, data);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to transition version status');
  }

  return response.json();
};

/**
 * Toggle a budget version's active state
 */
export const activateVersion = async (versionId: number, active: boolean = true): Promise<ApiResponse<BudgetVersion>> => {
  const response = await authenticatedPut(`/api/budget/versions/${versionId}/activate`, { active });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to update budget version active state');
  }

  return response.json();
};

/**
 * Delete a draft budget version
 */
export const deleteVersion = async (versionId: number): Promise<void> => {
  const response = await authenticatedDelete(`/api/budget/versions/${versionId}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to delete budget version');
  }
};

// ─── Budget Templates ────────────────────────────────────────────────────────

/**
 * List all budget templates
 */
export const listTemplates = async (): Promise<ApiResponse<BudgetTemplate[]>> => {
  const response = await authenticatedGet('/api/budget/templates');

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to list budget templates');
  }

  return response.json();
};

/**
 * Get a single budget template with its line configurations
 */
export const getTemplate = async (templateId: number): Promise<ApiResponse<BudgetTemplateWithLines>> => {
  const response = await authenticatedGet(`/api/budget/templates/${templateId}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to get budget template');
  }

  return response.json();
};

/**
 * Create a new budget template with line configurations
 */
export const createTemplate = async (data: CreateTemplateRequest): Promise<ApiResponse<BudgetTemplate>> => {
  const response = await authenticatedPost('/api/budget/templates', data);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to create budget template');
  }

  return response.json();
};

/**
 * Update an existing budget template
 */
export const updateTemplate = async (
  templateId: number,
  data: CreateTemplateRequest
): Promise<ApiResponse<BudgetTemplate>> => {
  const response = await authenticatedPut(`/api/budget/templates/${templateId}`, data);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to update budget template');
  }

  return response.json();
};

/**
 * Delete a budget template
 */
export const deleteTemplate = async (templateId: number): Promise<void> => {
  const response = await authenticatedDelete(`/api/budget/templates/${templateId}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to delete budget template');
  }
};

// ─── Budget Lines ────────────────────────────────────────────────────────────

/**
 * List all budget lines for a specific version
 */
export const listLines = async (versionId: number): Promise<ApiResponse<BudgetLine[]>> => {
  const response = await authenticatedGet(`/api/budget/versions/${versionId}/lines`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to list budget lines');
  }

  return response.json();
};

/**
 * Create a budget line for a specific version
 */
export const createLine = async (
  versionId: number,
  data: CreateBudgetLineRequest
): Promise<ApiResponse<BudgetLine>> => {
  const response = await authenticatedPost(`/api/budget/versions/${versionId}/lines`, data);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to create budget line');
  }

  return response.json();
};

/**
 * Update a budget line's amounts
 */
export const updateLine = async (
  lineId: number,
  data: Partial<CreateBudgetLineRequest>
): Promise<ApiResponse<BudgetLine>> => {
  const response = await authenticatedPut(`/api/budget/lines/${lineId}`, data);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to update budget line');
  }

  return response.json();
};

/**
 * Delete a budget line
 */
export const deleteLine = async (lineId: number): Promise<void> => {
  const response = await authenticatedDelete(`/api/budget/lines/${lineId}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to delete budget line');
  }
};

// ─── Draft Generation & Copy ─────────────────────────────────────────────────

/**
 * Generate a draft budget from prior-year actuals using a template
 */
export const generateDraft = async (data: GenerateDraftRequest): Promise<ApiResponse<GenerateDraftData>> => {
  const response = await authenticatedPost('/api/budget/generate-draft', data);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to generate draft budget');
  }

  return response.json();
};

/**
 * Copy a budget version to a new fiscal year
 */
export const copyBudget = async (data: CopyBudgetRequest): Promise<ApiResponse<CopyBudgetData>> => {
  const response = await authenticatedPost('/api/budget/copy', data);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to copy budget');
  }

  return response.json();
};

// ─── Dashboard ───────────────────────────────────────────────────────────────

/** Parameters for the budget dashboard query */
export interface DashboardParams {
  version_id?: number;
  year?: number;
  level?: DashboardLevel;
  period?: DashboardPeriod;
  parent_code?: string;
  subparent_code?: string;
  reference_number?: string;
}

/**
 * Fetch budget vs actuals dashboard data
 */
export const getDashboard = async (params: DashboardParams): Promise<ApiResponse<DashboardData>> => {
  const queryParams = new URLSearchParams();
  if (params.version_id) queryParams.append('version_id', params.version_id.toString());
  if (params.year) queryParams.append('year', params.year.toString());

  if (params.level) queryParams.append('level', params.level);
  if (params.period) queryParams.append('period', params.period);
  if (params.parent_code) queryParams.append('parent_code', params.parent_code);
  if (params.subparent_code) queryParams.append('subparent_code', params.subparent_code);
  if (params.reference_number) queryParams.append('reference_number', params.reference_number);

  const response = await authenticatedGet(`/api/budget/dashboard?${queryParams.toString()}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to fetch dashboard data');
  }

  return response.json();
};

// ─── AI Features ─────────────────────────────────────────────────────────────

/**
 * Generate an executive narrative summary from dashboard data
 */
export const generateNarrative = async (data: AINarrativeRequest): Promise<ApiResponse<AINarrativeData>> => {
  const response = await authenticatedPost('/api/budget/ai/narrative', data);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to generate narrative');
  }

  return response.json();
};

/**
 * Translate a natural language question into dashboard parameters and results
 */
export const queryBudget = async (data: AIQueryRequest): Promise<ApiResponse<AIQueryData>> => {
  const response = await authenticatedPost('/api/budget/ai/query', data);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to process budget query');
  }

  return response.json();
};

/**
 * Get AI-powered draft adjustment suggestions based on context notes
 */
export const getDraftSuggestions = async (
  data: AIDraftSuggestionsRequest
): Promise<ApiResponse<AIDraftSuggestionsData>> => {
  const response = await authenticatedPost('/api/budget/ai/draft-suggestions', data);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to get draft suggestions');
  }

  return response.json();
};

/**
 * Get AI-powered template recommendations based on chart of accounts and prior actuals
 */
export const getTemplateRecommendations = async (
  data: AITemplateRecommendRequest
): Promise<ApiResponse<AITemplateRecommendData>> => {
  const response = await authenticatedPost('/api/budget/ai/template-recommend', data);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to get template recommendations');
  }

  return response.json();
};

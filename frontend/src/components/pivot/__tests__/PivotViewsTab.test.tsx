/**
 * PivotViewsTab — Unit Tests
 *
 * Tests for the PivotViewsTab component covering model selector rendering,
 * model loading with filter controls, filter changes applied on execute,
 * locked model structure, and empty state.
 *
 * Requirements: 1.1, 2.1, 5.1, 5.2
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom';
import { PivotViewsTab } from '../PivotViewsTab';
import type {
  PivotDataSource,
  PivotModelSummary,
  PivotModel,
  PivotResult,
  AvailableColumns,
} from '../../../types/pivot';

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const finSources: PivotDataSource[] = [
  { name: 'vw_mutaties', label: 'Financial Transactions', module: 'FIN' },
];

const strSources: PivotDataSource[] = [
  { name: 'vw_bnb_total', label: 'STR Revenue', module: 'STR' },
];

const allSources: PivotDataSource[] = [...finSources, ...strSources];

const finModels: PivotModelSummary[] = [
  { id: 1, name: 'BTW per year', data_source: 'vw_mutaties', created_by: 'user@test.com', created_at: '2025-01-01' },
  { id: 2, name: 'IB overview', data_source: 'vw_mutaties', created_by: 'user@test.com', created_at: '2025-01-02' },
];

const strModels: PivotModelSummary[] = [
  { id: 3, name: 'Revenue by channel', data_source: 'vw_bnb_total', created_by: 'user@test.com', created_at: '2025-01-03' },
];

const allModels: PivotModelSummary[] = [...finModels, ...strModels];

const mockFinColumns: AvailableColumns = {
  groupable: [
    { name: 'Aangifte', type: 'varchar', label: 'Tax Category' },
    { name: 'jaar', type: 'int', label: 'Year' },
    { name: 'kwartaal', type: 'int', label: 'Quarter' },
  ],
  aggregatable: [
    { name: 'Amount', type: 'decimal', label: 'Amount' },
  ],
};

const mockLoadedFinModel: PivotModel = {
  id: 1,
  name: 'BTW per year',
  data_source: 'vw_mutaties',
  definition: {
    dataSource: 'vw_mutaties',
    groupColumns: ['Aangifte', 'jaar'],
    aggregateMeasures: [{ function: 'SUM', column: 'Amount' }],
    filters: { jaar: '2024' },
    columnPivot: null,
    columnNestLevels: [],
    displayMode: 'hierarchical',
  },
  created_by: 'user@test.com',
  created_at: '2025-01-01',
  updated_at: '2025-01-01',
};

const mockPivotResult: PivotResult = {
  success: true,
  data: [
    { Aangifte: 'BTW', jaar: 2024, SUM_Amount: 12345.67 },
    { Aangifte: 'IB', jaar: 2024, SUM_Amount: 8000.00 },
  ],
  columns: [
    { name: 'Aangifte', type: 'group', dataType: 'varchar' },
    { name: 'jaar', type: 'group', dataType: 'int' },
    { name: 'SUM_Amount', type: 'aggregate', dataType: 'decimal', function: 'SUM', sourceColumn: 'Amount' },
  ],
  row_count: 2,
};

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetRegisteredSources = jest.fn();
const mockFilterSourcesByModule = jest.fn();
const mockListPivotModels = jest.fn();
const mockLoadPivotModel = jest.fn();
const mockExecutePivot = jest.fn();
const mockGetAvailableColumns = jest.fn();

jest.mock('../../../services/pivotService', () => ({
  getRegisteredSources: (...args: any[]) => mockGetRegisteredSources(...args),
  filterSourcesByModule: (...args: any[]) => mockFilterSourcesByModule(...args),
  listPivotModels: (...args: any[]) => mockListPivotModels(...args),
  loadPivotModel: (...args: any[]) => mockLoadPivotModel(...args),
  executePivot: (...args: any[]) => mockExecutePivot(...args),
  getAvailableColumns: (...args: any[]) => mockGetAvailableColumns(...args),
}));

// Stable t function reference to avoid infinite re-render loops in useEffect deps
const stableT = (key: string, opts?: any) => {
  const map: Record<string, string> = {
    'pivot.models.selectModel': 'Select model...',
    'pivot.models.noModels': 'No saved models for this module. Create one in the Tenant Admin dashboard.',
    'pivot.actions.execute': 'Execute',
    'pivot.builder.filters': 'Filters',
    'pivot.builder.filtersHint': 'use commas for multiple values',
    'pivot.errors.executeFailed': 'Failed to execute pivot query',
    'pivot.errors.loadFailed': 'Failed to load',
  };
  if (key.startsWith('pivot.columnLabels.')) {
    return opts?.defaultValue ?? key.replace('pivot.columnLabels.', '');
  }
  return map[key] ?? key;
};
const stableI18n = { language: 'en' };

jest.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: stableT,
    i18n: stableI18n,
  }),
}));

// Mock FilterPanel to render simplified filter inputs
jest.mock('../../filters/FilterPanel', () => ({
  FilterPanel: ({ filters }: any) => (
    <div data-testid="filter-panel">
      {(filters || []).map((f: any, i: number) => (
        <div key={i} data-testid={`filter-input-${f.label}`}>
          <label>{f.label}</label>
          <input
            data-testid={`filter-value-${f.label}`}
            value={f.value}
            onChange={(e) => f.onChange(e.target.value)}
            placeholder={f.placeholder}
          />
        </div>
      ))}
    </div>
  ),
}));

// Mock PivotResultTable to capture props
jest.mock('../PivotResultTable', () => ({
  PivotResultTable: ({ data, columns, config, isLoading }: any) => (
    <div data-testid="pivot-result-table">
      <span data-testid="result-row-count">{data?.length ?? 0}</span>
      <span data-testid="result-config">{JSON.stringify(config)}</span>
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupDefaultMocks() {
  mockGetRegisteredSources.mockResolvedValue(allSources);
  mockFilterSourcesByModule.mockImplementation(
    (sources: PivotDataSource[], filter?: string | null) => {
      if (!filter) return sources;
      return sources.filter((s) => s.module === filter);
    },
  );
  mockListPivotModels.mockResolvedValue(allModels);
  mockLoadPivotModel.mockResolvedValue(mockLoadedFinModel);
  mockExecutePivot.mockResolvedValue(mockPivotResult);
  mockGetAvailableColumns.mockResolvedValue(mockFinColumns);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PivotViewsTab', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setupDefaultMocks();
  });

  afterEach(() => {
    cleanup();
    jest.restoreAllMocks();
  });

  // -----------------------------------------------------------------------
  // Model selector with module filtering (Requirement 5.1)
  // -----------------------------------------------------------------------

  describe('model selector', () => {
    it('renders model selector dropdown with saved models filtered by module', async () => {
      render(<PivotViewsTab moduleFilter="FIN" />);

      // Wait for loading to complete
      await waitFor(() => {
        expect(mockGetRegisteredSources).toHaveBeenCalled();
        expect(mockListPivotModels).toHaveBeenCalled();
      });

      // Should show FIN models only (vw_mutaties data source)
      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
        expect(screen.getByText('IB overview')).toBeInTheDocument();
      });

      // STR model should NOT be shown
      expect(screen.queryByText('Revenue by channel')).not.toBeInTheDocument();
    });

    it('filters models by STR module correctly', async () => {
      render(<PivotViewsTab moduleFilter="STR" />);

      await waitFor(() => {
        expect(screen.getByText('Revenue by channel')).toBeInTheDocument();
      });

      // FIN models should NOT be shown
      expect(screen.queryByText('BTW per year')).not.toBeInTheDocument();
      expect(screen.queryByText('IB overview')).not.toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Loading a model populates filter controls (Requirement 5.2)
  // -----------------------------------------------------------------------

  describe('loading a model', () => {
    it('populates filter controls for the model group columns when model is selected', async () => {
      render(<PivotViewsTab moduleFilter="FIN" />);

      // Wait for models to load
      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      // Select a model
      const modelSelect = screen.getByRole('combobox');
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      // Should load the model and fetch columns
      await waitFor(() => {
        expect(mockLoadPivotModel).toHaveBeenCalledWith(1);
        expect(mockGetAvailableColumns).toHaveBeenCalledWith('vw_mutaties');
      });

      // Filter controls should appear for the model's data source columns
      await waitFor(() => {
        expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
        expect(screen.getByTestId('filter-input-Tax Category')).toBeInTheDocument();
        expect(screen.getByTestId('filter-input-Year')).toBeInTheDocument();
        expect(screen.getByTestId('filter-input-Quarter')).toBeInTheDocument();
      });
    });

    it('seeds filter values from the loaded model definition', async () => {
      render(<PivotViewsTab moduleFilter="FIN" />);

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      const modelSelect = screen.getByRole('combobox');
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      // The loaded model has filters: { jaar: '2024' }
      // The Year filter should be pre-populated with '2024'
      await waitFor(() => {
        const yearFilter = screen.getByTestId('filter-value-Year');
        expect(yearFilter).toHaveValue('2024');
      });
    });
  });

  // -----------------------------------------------------------------------
  // Filter changes applied when executing (Requirement 2.1)
  // -----------------------------------------------------------------------

  describe('filter changes applied on execute', () => {
    it('applies user filter changes when executing the pivot', async () => {
      render(<PivotViewsTab moduleFilter="FIN" />);

      // Wait for models to load and select one
      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      const modelSelect = screen.getByRole('combobox');
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      // Wait for model and columns to load
      await waitFor(() => {
        expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
      });

      // Change the Year filter value
      const yearFilter = screen.getByTestId('filter-value-Year');
      await act(async () => {
        fireEvent.change(yearFilter, { target: { value: '2025' } });
      });

      // Click execute
      const executeBtn = screen.getByText('Execute');
      await act(async () => {
        fireEvent.click(executeBtn);
      });

      // executePivot should be called with the updated filter
      await waitFor(() => {
        expect(mockExecutePivot).toHaveBeenCalled();
        const callArg = mockExecutePivot.mock.calls[0][0];
        expect(callArg.filters.jaar).toBe('2025');
      });
    });

    it('clears filter when value is emptied', async () => {
      render(<PivotViewsTab moduleFilter="FIN" />);

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      const modelSelect = screen.getByRole('combobox');
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      await waitFor(() => {
        expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
      });

      // Clear the Year filter
      const yearFilter = screen.getByTestId('filter-value-Year');
      await act(async () => {
        fireEvent.change(yearFilter, { target: { value: '' } });
      });

      // Execute
      const executeBtn = screen.getByText('Execute');
      await act(async () => {
        fireEvent.click(executeBtn);
      });

      // The cleared filter should not be in the config
      await waitFor(() => {
        expect(mockExecutePivot).toHaveBeenCalled();
        const callArg = mockExecutePivot.mock.calls[0][0];
        expect(callArg.filters).not.toHaveProperty('jaar');
      });
    });
  });

  // -----------------------------------------------------------------------
  // Model structure is not editable — only filters
  // -----------------------------------------------------------------------

  describe('locked model structure', () => {
    it('does not render group column or aggregate measure editors', async () => {
      render(<PivotViewsTab moduleFilter="FIN" />);

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      const modelSelect = screen.getByRole('combobox');
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      await waitFor(() => {
        expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
      });

      // PivotViewsTab should NOT render PivotBuilder-style editors
      // No group column selector, no aggregate measure picker, no data source selector
      expect(screen.queryByText('Group Columns')).not.toBeInTheDocument();
      expect(screen.queryByText('Aggregate Measures')).not.toBeInTheDocument();
      expect(screen.queryByText('Data Source')).not.toBeInTheDocument();
      expect(screen.queryByText('Column Pivot')).not.toBeInTheDocument();
    });

    it('preserves model group columns and aggregates in execute call', async () => {
      render(<PivotViewsTab moduleFilter="FIN" />);

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      const modelSelect = screen.getByRole('combobox');
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      await waitFor(() => {
        expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
      });

      // Execute without changing anything
      const executeBtn = screen.getByText('Execute');
      await act(async () => {
        fireEvent.click(executeBtn);
      });

      await waitFor(() => {
        expect(mockExecutePivot).toHaveBeenCalled();
        const callArg = mockExecutePivot.mock.calls[0][0];
        // Model structure should be preserved from the loaded model
        expect(callArg.dataSource).toBe('vw_mutaties');
        expect(callArg.groupColumns).toEqual(['Aangifte', 'jaar']);
        expect(callArg.aggregateMeasures).toEqual([{ function: 'SUM', column: 'Amount' }]);
        expect(callArg.displayMode).toBe('hierarchical');
      });
    });
  });

  // -----------------------------------------------------------------------
  // Empty state (Requirement 5.1)
  // -----------------------------------------------------------------------

  describe('empty state', () => {
    it('shows empty state when no saved models exist for the module', async () => {
      // Return no models
      mockListPivotModels.mockResolvedValue([]);

      render(<PivotViewsTab moduleFilter="FIN" />);

      await waitFor(() => {
        expect(screen.getByText('No saved models for this module. Create one in the Tenant Admin dashboard.')).toBeInTheDocument();
      });

      // No model selector or execute button should be shown
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
      expect(screen.queryByText('Execute')).not.toBeInTheDocument();
    });

    it('shows empty state when models exist but none match the module', async () => {
      // Return only STR models, but render FIN tab
      mockListPivotModels.mockResolvedValue(strModels);

      render(<PivotViewsTab moduleFilter="FIN" />);

      await waitFor(() => {
        expect(screen.getByText('No saved models for this module. Create one in the Tenant Admin dashboard.')).toBeInTheDocument();
      });
    });
  });

  // -----------------------------------------------------------------------
  // Execute button state
  // -----------------------------------------------------------------------

  describe('execute button', () => {
    it('disables execute button when no model is loaded', async () => {
      render(<PivotViewsTab moduleFilter="FIN" />);

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      // Execute button should be disabled when no model is selected
      const executeBtn = screen.getByText('Execute');
      expect(executeBtn).toBeDisabled();
    });

    it('enables execute button when a model is loaded', async () => {
      render(<PivotViewsTab moduleFilter="FIN" />);

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      const modelSelect = screen.getByRole('combobox');
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      await waitFor(() => {
        expect(mockLoadPivotModel).toHaveBeenCalledWith(1);
      });

      // Wait for model loading to complete
      await waitFor(() => {
        const executeBtn = screen.getByText('Execute');
        expect(executeBtn).not.toBeDisabled();
      });
    });
  });

  // -----------------------------------------------------------------------
  // Results rendering
  // -----------------------------------------------------------------------

  describe('results rendering', () => {
    it('renders PivotResultTable after successful execution', async () => {
      render(<PivotViewsTab moduleFilter="FIN" />);

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      // Select and load model
      const modelSelect = screen.getByRole('combobox');
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      await waitFor(() => {
        expect(mockLoadPivotModel).toHaveBeenCalledWith(1);
      });

      // Execute
      await waitFor(() => {
        expect(screen.getByText('Execute')).not.toBeDisabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByText('Execute'));
      });

      await waitFor(() => {
        expect(screen.getByTestId('pivot-result-table')).toBeInTheDocument();
        expect(screen.getByTestId('result-row-count')).toHaveTextContent('2');
      });
    });

    it('displays error message when execution fails', async () => {
      mockExecutePivot.mockRejectedValue(new Error('Database connection failed'));

      render(<PivotViewsTab moduleFilter="FIN" />);

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      const modelSelect = screen.getByRole('combobox');
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      await waitFor(() => {
        expect(screen.getByText('Execute')).not.toBeDisabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByText('Execute'));
      });

      await waitFor(() => {
        expect(screen.getByText('Database connection failed')).toBeInTheDocument();
      });
    });
  });

  // -----------------------------------------------------------------------
  // Error handling
  // -----------------------------------------------------------------------

  describe('error handling', () => {
    it('shows error when model list fails to load', async () => {
      mockGetRegisteredSources.mockRejectedValue(new Error('Network error'));

      render(<PivotViewsTab moduleFilter="FIN" />);

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument();
      });
    });

    it('shows error when loading a specific model fails', async () => {
      mockLoadPivotModel.mockRejectedValue(new Error('Model not found'));

      render(<PivotViewsTab moduleFilter="FIN" />);

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      const modelSelect = screen.getByRole('combobox');
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      await waitFor(() => {
        expect(screen.getByText('Model not found')).toBeInTheDocument();
      });
    });
  });
});

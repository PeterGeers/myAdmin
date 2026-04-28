/**
 * PivotBuilder — Unit Tests
 *
 * Tests for the PivotBuilder component covering data source selection,
 * column fetching, validation, save/load model flows, and filter controls.
 *
 * Requirements: 1.1, 1.2, 1.6, 2.1, 4.1, 5.1, 5.2
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor, act, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom';
import type {
  PivotDataSource,
  AvailableColumns,
  PivotModelSummary,
  PivotModel,
  PivotResult,
} from '../../../types/pivot';

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const mockDataSources: PivotDataSource[] = [
  { name: 'vw_mutaties', label: 'Financial Transactions', module: 'FIN' },
  { name: 'vw_bnb_total', label: 'STR Revenue', module: 'STR' },
];

const mockColumns: AvailableColumns = {
  groupable: [
    { name: 'Aangifte', type: 'varchar', label: 'Tax Category' },
    { name: 'jaar', type: 'int', label: 'Year' },
    { name: 'kwartaal', type: 'int', label: 'Quarter' },
  ],
  aggregatable: [
    { name: 'Amount', type: 'decimal', label: 'Amount' },
  ],
};

const mockStrColumns: AvailableColumns = {
  groupable: [
    { name: 'channel', type: 'varchar', label: 'Channel' },
    { name: 'listing', type: 'varchar', label: 'Listing' },
    { name: 'year', type: 'int', label: 'Year' },
  ],
  aggregatable: [
    { name: 'amountGross', type: 'decimal', label: 'Gross Amount' },
    { name: 'amountNett', type: 'decimal', label: 'Net Amount' },
  ],
};

const mockModels: PivotModelSummary[] = [
  { id: 1, name: 'BTW per year', data_source: 'vw_mutaties', created_by: 'user@test.com', created_at: '2025-01-01' },
  { id: 2, name: 'Revenue by channel', data_source: 'vw_bnb_total', created_by: 'user@test.com', created_at: '2025-01-02' },
];

const mockLoadedModel: PivotModel = {
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
  data: [{ Aangifte: 'BTW', jaar: 2024, SUM_Amount: 12345.67 }],
  columns: [
    { name: 'Aangifte', type: 'group', dataType: 'varchar' },
    { name: 'jaar', type: 'group', dataType: 'int' },
    { name: 'SUM_Amount', type: 'aggregate', dataType: 'decimal', function: 'SUM', sourceColumn: 'Amount' },
  ],
  row_count: 1,
};

// ---------------------------------------------------------------------------
// Mocks — Chakra UI (simple HTML equivalents)
// ---------------------------------------------------------------------------

/** Filter out non-DOM props to avoid React warnings. */
function mockFilterDomProps(props: Record<string, any>): Record<string, any> {
  const {
    bg, color, colorScheme, fontSize, fontWeight, spacing, align, justify,
    wrap, gap, maxW, minW, flex, mb, mt, borderRadius, borderColor,
    borderWidth, variant, size, labelColor, sx, isAttached, ...rest
  } = props;
  return rest;
}

vi.mock('@chakra-ui/react', () => ({
  Box: ({ children, ...p }: any) => <div {...mockFilterDomProps(p)}>{children}</div>,
  Flex: ({ children, ...p }: any) => <div {...mockFilterDomProps(p)}>{children}</div>,
  VStack: ({ children, ...p }: any) => <div {...mockFilterDomProps(p)}>{children}</div>,
  HStack: ({ children, ...p }: any) => <div {...mockFilterDomProps(p)}>{children}</div>,
  Wrap: ({ children }: any) => <div>{children}</div>,
  WrapItem: ({ children }: any) => <div>{children}</div>,
  Text: ({ children, as: _as, ...p }: any) => <span {...mockFilterDomProps(p)}>{children}</span>,
  FormControl: ({ children }: any) => <div>{children}</div>,
  FormLabel: ({ children }: any) => <label>{children}</label>,
  Select: ({ children, placeholder, 'aria-label': ariaLabel, value, onChange, disabled, ...p }: any) => (
    <select aria-label={ariaLabel || placeholder} value={value} onChange={onChange} disabled={disabled}>
      {placeholder && <option value="">{placeholder}</option>}
      {children}
    </select>
  ),
  Button: ({ children, onClick, isLoading, disabled, isDisabled, ...p }: any) => (
    <button onClick={onClick} disabled={disabled || isDisabled || isLoading}>
      {isLoading ? 'Loading...' : children}
    </button>
  ),
  ButtonGroup: ({ children }: any) => <div>{children}</div>,
  IconButton: ({ 'aria-label': ariaLabel, onClick, isDisabled, disabled }: any) => (
    <button aria-label={ariaLabel} onClick={onClick} disabled={isDisabled || disabled} />
  ),
  Tag: ({ children }: any) => <span>{children}</span>,
  TagLabel: ({ children }: any) => <span>{children}</span>,
  Spinner: () => <span data-testid="spinner">Loading...</span>,
  Alert: ({ children, status }: any) => <div role="alert" data-status={status}>{children}</div>,
  AlertIcon: () => <span />,
  Input: ({ value, onChange, placeholder, ...p }: any) => (
    <input value={value} onChange={onChange} placeholder={placeholder} />
  ),
  Modal: ({ children, isOpen }: any) => isOpen ? <div data-testid="modal">{children}</div> : null,
  ModalOverlay: () => null,
  ModalContent: ({ children }: any) => <div>{children}</div>,
  ModalHeader: ({ children }: any) => <div>{children}</div>,
  ModalBody: ({ children }: any) => <div>{children}</div>,
  ModalFooter: ({ children }: any) => <div>{children}</div>,
  ModalCloseButton: () => null,
  useDisclosure: () => ({ isOpen: false, onOpen: vi.fn(), onClose: vi.fn() }),
}));

vi.mock('@chakra-ui/icons', () => ({
  ArrowUpIcon: () => <span>↑</span>,
  ArrowDownIcon: () => <span>↓</span>,
  AddIcon: () => <span>+</span>,
  CloseIcon: () => <span>×</span>,
  DeleteIcon: () => <span>🗑</span>,
}));

// ---------------------------------------------------------------------------
// Mocks — Services
// ---------------------------------------------------------------------------

const mockGetRegisteredSources = vi.fn();
const mockFilterSourcesByModule = vi.fn();
const mockGetAvailableColumns = vi.fn();
const mockExecutePivot = vi.fn();
const mockListPivotModels = vi.fn();
const mockLoadPivotModel = vi.fn();
const mockSavePivotModel = vi.fn();
const mockUpdatePivotModel = vi.fn();
const mockDeletePivotModel = vi.fn();

vi.mock('../../../services/pivotService', () => ({
  getRegisteredSources: (...args: any[]) => mockGetRegisteredSources(...args),
  filterSourcesByModule: (...args: any[]) => mockFilterSourcesByModule(...args),
  getAvailableColumns: (...args: any[]) => mockGetAvailableColumns(...args),
  executePivot: (...args: any[]) => mockExecutePivot(...args),
  listPivotModels: (...args: any[]) => mockListPivotModels(...args),
  loadPivotModel: (...args: any[]) => mockLoadPivotModel(...args),
  savePivotModel: (...args: any[]) => mockSavePivotModel(...args),
  updatePivotModel: (...args: any[]) => mockUpdatePivotModel(...args),
  deletePivotModel: (...args: any[]) => mockDeletePivotModel(...args),
}));

// ---------------------------------------------------------------------------
// Mocks — Translation
// ---------------------------------------------------------------------------

const stableT = (key: string, opts?: any) => {
  const map: Record<string, string> = {
    'pivot.builder.title': 'Pivot Builder',
    'pivot.builder.dataSource': 'Data Source',
    'pivot.builder.selectDataSource': 'Select data source...',
    'pivot.builder.groupColumns': 'Group Columns',
    'pivot.builder.selectGroupColumns': 'Select group columns...',
    'pivot.builder.aggregateMeasures': 'Aggregate Measures',
    'pivot.builder.aggregateFunction': 'Function',
    'pivot.builder.aggregateColumn': 'Column',
    'pivot.builder.addMeasure': 'Add Measure',
    'pivot.builder.removeMeasure': 'Remove',
    'pivot.builder.columnPivot': 'Column Pivot',
    'pivot.builder.selectColumnPivot': 'Select column pivot...',
    'pivot.builder.columnNestLevels': 'Nest Levels',
    'pivot.builder.selectNestLevels': 'Select nest levels...',
    'pivot.builder.displayMode': 'Display Mode',
    'pivot.builder.flat': 'Flat',
    'pivot.builder.hierarchical': 'Hierarchical',
    'pivot.builder.filters': 'Filters',
    'pivot.builder.filtersHint': 'use commas for multiple values',
    'pivot.builder.execute': 'Execute',
    'pivot.actions.execute': 'Execute',
    'pivot.actions.save': 'Save',
    'pivot.actions.delete': 'Delete',
    'pivot.models.selectModel': 'Select model...',
    'pivot.models.enterName': 'Enter model name',
    'pivot.models.noModels': 'No saved models',
    'pivot.models.deleteConfirm': 'Delete this model?',
    'pivot.models.duplicateName': 'Name already exists',
    'pivot.validation.minGroupColumn': 'Select at least one group column',
    'pivot.validation.minAggregateMeasure': 'Add at least one aggregate measure',
    'pivot.validation.columnRoleOverlap': `Column '${opts?.column}' is used in multiple roles`,
    'pivot.errors.executeFailed': 'Failed to execute pivot query',
    'pivot.errors.loadFailed': 'Failed to load model',
    'pivot.errors.saveFailed': 'Failed to save model',
    'pivot.functions.SUM': 'SUM',
    'pivot.functions.COUNT': 'COUNT',
    'pivot.functions.AVG': 'AVG',
    'pivot.functions.MIN': 'MIN',
    'pivot.functions.MAX': 'MAX',
  };
  if (key.startsWith('pivot.columnLabels.')) {
    return opts?.defaultValue ?? key.replace('pivot.columnLabels.', '');
  }
  return map[key] ?? key;
};
const stableI18n = { language: 'en' };

vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: stableT, i18n: stableI18n }),
}));

// ---------------------------------------------------------------------------
// Mocks — Sub-components
// ---------------------------------------------------------------------------

// Mock GenericFilter to render a simplified multi-select
vi.mock('../../filters/GenericFilter', () => ({
  GenericFilter: ({ label, values, onChange, availableOptions, multiSelect, getOptionLabel }: any) => (
    <div data-testid={`generic-filter-${label}`}>
      <label>{label}</label>
      <select
        data-testid={`select-${label}`}
        multiple={multiSelect}
        value={values || []}
        onChange={(e) => {
          if (multiSelect) {
            const selected = Array.from(e.target.selectedOptions, (opt: any) => opt.value);
            onChange([...values, ...selected.filter((s: string) => !values.includes(s))]);
          } else {
            onChange([e.target.value]);
          }
        }}
      >
        {(availableOptions || []).map((opt: string) => (
          <option key={opt} value={opt}>
            {getOptionLabel ? getOptionLabel(opt) : opt}
          </option>
        ))}
      </select>
    </div>
  ),
}));

// Mock FilterPanel to render simplified filter inputs
vi.mock('../../filters/FilterPanel', () => ({
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

// Mock PivotResultTable
vi.mock('../PivotResultTable', () => ({
  PivotResultTable: () => <div data-testid="pivot-result-table" />,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupDefaultMocks() {
  mockGetRegisteredSources.mockResolvedValue(mockDataSources);
  mockFilterSourcesByModule.mockImplementation(
    (sources: PivotDataSource[], filter?: string | null) => {
      if (!filter) return sources;
      return sources.filter((s) => s.module === filter);
    },
  );
  mockGetAvailableColumns.mockImplementation((ds: string) => {
    if (ds === 'vw_mutaties') return Promise.resolve(mockColumns);
    if (ds === 'vw_bnb_total') return Promise.resolve(mockStrColumns);
    return Promise.resolve({ groupable: [], aggregatable: [] });
  });
  mockExecutePivot.mockResolvedValue(mockPivotResult);
  mockListPivotModels.mockResolvedValue(mockModels);
  mockLoadPivotModel.mockResolvedValue(mockLoadedModel);
  mockSavePivotModel.mockResolvedValue({ success: true, id: 3 });
  mockUpdatePivotModel.mockResolvedValue({ success: true });
  mockDeletePivotModel.mockResolvedValue({ success: true });
}

// Now import the component AFTER all mocks are set up
import { PivotBuilder } from '../PivotBuilder';

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PivotBuilder', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  // -----------------------------------------------------------------------
  // Data source selector (Requirement 1.1)
  // -----------------------------------------------------------------------

  describe('data source selector', () => {
    it('renders data source selector with options from registered sources', async () => {
      render(<PivotBuilder />);

      await waitFor(() => {
        expect(mockGetRegisteredSources).toHaveBeenCalled();
      });

      // Wait for data sources to load and the select to appear
      await waitFor(() => {
        expect(screen.getByText('Financial Transactions')).toBeInTheDocument();
        expect(screen.getByText('STR Revenue')).toBeInTheDocument();
      });

      const dsSelect = screen.getByRole('combobox', { name: 'Data Source' });
      expect(dsSelect).toBeInTheDocument();
    });

    it('filters data sources by moduleFilter prop', async () => {
      render(<PivotBuilder moduleFilter="FIN" />);

      await waitFor(() => {
        expect(mockFilterSourcesByModule).toHaveBeenCalledWith(
          mockDataSources,
          'FIN',
        );
      });
    });

    it('shows all data sources when no moduleFilter is provided', async () => {
      render(<PivotBuilder />);

      await waitFor(() => {
        expect(mockFilterSourcesByModule).toHaveBeenCalledWith(
          mockDataSources,
          undefined,
        );
      });
    });
  });

  // -----------------------------------------------------------------------
  // Column fetching on data source change (Requirement 1.2)
  // -----------------------------------------------------------------------

  describe('column fetching', () => {
    it('fetches and displays columns when data source is selected', async () => {
      render(<PivotBuilder />);

      await waitFor(() => {
        expect(screen.getByText('Financial Transactions')).toBeInTheDocument();
      });

      const dsSelect = screen.getByRole('combobox', { name: 'Data Source' });
      await act(async () => {
        fireEvent.change(dsSelect, { target: { value: 'vw_mutaties' } });
      });

      await waitFor(() => {
        expect(mockGetAvailableColumns).toHaveBeenCalledWith('vw_mutaties');
      });

      await waitFor(() => {
        expect(screen.getByText('Group Columns')).toBeInTheDocument();
      });
    });

    it('fetches new columns when data source changes', async () => {
      render(<PivotBuilder />);

      await waitFor(() => {
        expect(screen.getByText('Financial Transactions')).toBeInTheDocument();
      });

      const dsSelect = screen.getByRole('combobox', { name: 'Data Source' });

      await act(async () => {
        fireEvent.change(dsSelect, { target: { value: 'vw_mutaties' } });
      });

      await waitFor(() => {
        expect(mockGetAvailableColumns).toHaveBeenCalledWith('vw_mutaties');
      });

      await act(async () => {
        fireEvent.change(dsSelect, { target: { value: 'vw_bnb_total' } });
      });

      await waitFor(() => {
        expect(mockGetAvailableColumns).toHaveBeenCalledWith('vw_bnb_total');
      });
    });

    it('does not fetch columns when no data source is selected', async () => {
      render(<PivotBuilder />);

      await waitFor(() => {
        expect(screen.getByText('Financial Transactions')).toBeInTheDocument();
      });

      expect(mockGetAvailableColumns).not.toHaveBeenCalled();
      expect(screen.queryByText('Group Columns')).not.toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Validation (Requirement 1.6)
  // -----------------------------------------------------------------------

  describe('validation', () => {
    it('disables execute button when no group column or aggregate measure is selected', async () => {
      render(<PivotBuilder />);

      await waitFor(() => {
        expect(screen.getByText('Financial Transactions')).toBeInTheDocument();
      });

      const dsSelect = screen.getByRole('combobox', { name: 'Data Source' });
      await act(async () => {
        fireEvent.change(dsSelect, { target: { value: 'vw_mutaties' } });
      });

      const executeBtn = screen.getByText('Execute');
      expect(executeBtn).toBeDisabled();
    });

    it('shows validation messages when data source is selected but config is incomplete', async () => {
      render(<PivotBuilder />);

      await waitFor(() => {
        expect(screen.getByText('Financial Transactions')).toBeInTheDocument();
      });

      const dsSelect = screen.getByRole('combobox', { name: 'Data Source' });
      await act(async () => {
        fireEvent.change(dsSelect, { target: { value: 'vw_mutaties' } });
      });

      await waitFor(() => {
        expect(screen.getByText('Select at least one group column')).toBeInTheDocument();
        expect(screen.getByText('Add at least one aggregate measure')).toBeInTheDocument();
      });
    });
  });

  // -----------------------------------------------------------------------
  // Save flow (Requirement 4.1)
  // -----------------------------------------------------------------------

  describe('save model flow', () => {
    it('renders save button', async () => {
      render(<PivotBuilder />);

      await waitFor(() => {
        expect(screen.getByText('Save')).toBeInTheDocument();
      });
    });

    it('save button is disabled when config is not valid', async () => {
      render(<PivotBuilder />);

      await waitFor(() => {
        const saveBtn = screen.getByText('Save');
        expect(saveBtn).toBeDisabled();
      });
    });
  });

  // -----------------------------------------------------------------------
  // Load model (Requirements 5.1, 5.2)
  // -----------------------------------------------------------------------

  describe('load model', () => {
    it('renders model selector dropdown with saved models', async () => {
      render(<PivotBuilder />);

      await waitFor(() => {
        expect(mockListPivotModels).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
        expect(screen.getByText('Revenue by channel')).toBeInTheDocument();
      });
    });

    it('loads model and populates config when model is selected', async () => {
      const onConfigChange = vi.fn();
      render(<PivotBuilder onConfigChange={onConfigChange} />);

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      const modelSelect = screen.getByRole('combobox', { name: 'Select model...' });
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      await waitFor(() => {
        expect(mockLoadPivotModel).toHaveBeenCalledWith(1);
      });

      await waitFor(() => {
        expect(onConfigChange).toHaveBeenCalled();
        const lastCall = onConfigChange.mock.calls[onConfigChange.mock.calls.length - 1][0];
        expect(lastCall.dataSource).toBe('vw_mutaties');
        expect(lastCall.groupColumns).toEqual(['Aangifte', 'jaar']);
        expect(lastCall.aggregateMeasures).toEqual([{ function: 'SUM', column: 'Amount' }]);
      });
    });
  });

  // -----------------------------------------------------------------------
  // Filter controls match data source (Requirement 2.1)
  // -----------------------------------------------------------------------

  describe('filter controls', () => {
    it('renders filter controls matching the selected data source columns', async () => {
      render(<PivotBuilder />);

      await waitFor(() => {
        expect(screen.getByText('Financial Transactions')).toBeInTheDocument();
      });

      const dsSelect = screen.getByRole('combobox', { name: 'Data Source' });
      await act(async () => {
        fireEvent.change(dsSelect, { target: { value: 'vw_mutaties' } });
      });

      await waitFor(() => {
        expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
      });

      expect(screen.getByTestId('filter-input-Tax Category')).toBeInTheDocument();
      expect(screen.getByTestId('filter-input-Year')).toBeInTheDocument();
      expect(screen.getByTestId('filter-input-Quarter')).toBeInTheDocument();
    });

    it('updates filter controls when data source changes', async () => {
      render(<PivotBuilder />);

      await waitFor(() => {
        expect(screen.getByText('Financial Transactions')).toBeInTheDocument();
      });

      const dsSelect = screen.getByRole('combobox', { name: 'Data Source' });

      await act(async () => {
        fireEvent.change(dsSelect, { target: { value: 'vw_mutaties' } });
      });

      await waitFor(() => {
        expect(screen.getByTestId('filter-input-Tax Category')).toBeInTheDocument();
      });

      await act(async () => {
        fireEvent.change(dsSelect, { target: { value: 'vw_bnb_total' } });
      });

      await waitFor(() => {
        expect(screen.getByTestId('filter-input-Channel')).toBeInTheDocument();
        expect(screen.getByTestId('filter-input-Listing')).toBeInTheDocument();
      });

      expect(screen.queryByTestId('filter-input-Tax Category')).not.toBeInTheDocument();
      expect(screen.queryByTestId('filter-input-Quarter')).not.toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Execute flow
  // -----------------------------------------------------------------------

  describe('execute', () => {
    it('calls executePivot and passes results to onResults callback', async () => {
      const onResults = vi.fn();
      render(<PivotBuilder onResults={onResults} />);

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      // Load a model to get a valid config
      const modelSelect = screen.getByRole('combobox', { name: 'Select model...' });
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      await waitFor(() => {
        expect(mockLoadPivotModel).toHaveBeenCalledWith(1);
      });

      await waitFor(() => {
        expect(mockGetAvailableColumns).toHaveBeenCalledWith('vw_mutaties');
      });

      // Wait for execute button to become enabled
      await waitFor(() => {
        expect(screen.getByText('Execute')).not.toBeDisabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByText('Execute'));
      });

      await waitFor(() => {
        expect(mockExecutePivot).toHaveBeenCalled();
        expect(onResults).toHaveBeenCalledWith(mockPivotResult);
      });
    });

    it('displays error message when execute fails', async () => {
      mockExecutePivot.mockRejectedValue(new Error('Query timeout'));
      render(<PivotBuilder />);

      await waitFor(() => {
        expect(screen.getByText('BTW per year')).toBeInTheDocument();
      });

      const modelSelect = screen.getByRole('combobox', { name: 'Select model...' });
      await act(async () => {
        fireEvent.change(modelSelect, { target: { value: '1' } });
      });

      await waitFor(() => {
        expect(mockGetAvailableColumns).toHaveBeenCalledWith('vw_mutaties');
      });

      await waitFor(() => {
        expect(screen.getByText('Execute')).not.toBeDisabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByText('Execute'));
      });

      await waitFor(() => {
        expect(screen.getByText('Query timeout')).toBeInTheDocument();
      });
    });
  });

  // -----------------------------------------------------------------------
  // Config change callback
  // -----------------------------------------------------------------------

  describe('config change callback', () => {
    it('calls onConfigChange when config changes', async () => {
      const onConfigChange = vi.fn();
      render(<PivotBuilder onConfigChange={onConfigChange} />);

      await waitFor(() => {
        expect(onConfigChange).toHaveBeenCalled();
      });
    });
  });
});

/**
 * ParameterManagement Component - Unit Tests
 *
 * Tests the parameter management UI including:
 * - Rendering parameters in a table
 * - FilterableHeader inline column filters (v2 framework)
 * - Row-click modal for tenant-scoped parameters
 * - Add/edit/delete parameter workflows
 */
import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '../../../test-utils';
import ParameterManagement from '../ParameterManagement';

// Mock the parameter service (used for data loading + CRUD)
jest.mock('../../../services/parameterService', () => ({
  getParameters: jest.fn(),
  createParameter: jest.fn(),
  updateParameter: jest.fn(),
  deleteParameter: jest.fn(),
}));

jest.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: jest.fn() }
  })
}));

// Mock useTableConfig to return defaults without hitting the parameter API
jest.mock('../../../hooks/useTableConfig', () => ({
  useTableConfig: () => ({
    columns: ['namespace', 'key', 'value', 'value_type', 'scope_origin'],
    filterableColumns: ['namespace', 'key', 'value', 'value_type', 'scope_origin'],
    defaultSort: { field: 'namespace', direction: 'asc' },
    pageSize: 100,
    loading: false,
    error: null,
  }),
}));

const { getParameters, createParameter, updateParameter, deleteParameter } =
  require('../../../services/parameterService');

const mockParams = {
  success: true, tenant: 'T1',
  parameters: {
    storage: [
      { id: 1, namespace: 'storage', key: 'provider', value: 'google_drive', value_type: 'string', scope_origin: 'tenant', is_secret: false },
      { id: null, namespace: 'storage', key: 'bucket', value: 'default', value_type: 'string', scope_origin: 'system', is_secret: false },
    ],
    fin: [
      { id: 2, namespace: 'fin', key: 'currency', value: 'EUR', value_type: 'string', scope_origin: 'tenant', is_secret: false },
    ],
  },
};

describe('ParameterManagement', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    getParameters.mockResolvedValue(mockParams);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  /** Helper: render and wait for data to load, then flush timers */
  async function renderAndWait() {
    render(<ParameterManagement tenant="T1" />);
    // Flush the pending getParameters promise
    await act(async () => {
      jest.advanceTimersByTime(0);
    });
    await waitFor(() => expect(screen.getByText('provider')).toBeInTheDocument());
  }

  /** Helper: change a filter input and advance past the debounce timer */
  function changeFilter(input: HTMLElement, value: string) {
    fireEvent.change(input, { target: { value } });
    act(() => { jest.advanceTimersByTime(200); });
  }

  describe('Rendering', () => {
    test('shows loading spinner initially', () => {
      getParameters.mockReturnValue(new Promise(() => {}));
      render(<ParameterManagement tenant="T1" />);
      expect(document.querySelector('.chakra-spinner')).toBeInTheDocument();
    });

    test('renders parameter table after loading', async () => {
      await renderAndWait();
      expect(screen.getByText('provider')).toBeInTheDocument();
      expect(screen.getByText('google_drive')).toBeInTheDocument();
    });

    test('renders all parameters from all namespaces', async () => {
      await renderAndWait();
      expect(screen.getByText('provider')).toBeInTheDocument();
      expect(screen.getByText('bucket')).toBeInTheDocument();
      expect(screen.getByText('currency')).toBeInTheDocument();
    });

    test('shows scope badges', async () => {
      await renderAndWait();
      expect(screen.getAllByText('tenant').length).toBeGreaterThan(0);
      expect(screen.getAllByText('system').length).toBeGreaterThan(0);
    });

    test('shows secret values as masked', async () => {
      getParameters.mockResolvedValue({
        success: true, tenant: 'T1',
        parameters: { ns: [{ id: 3, namespace: 'ns', key: 'api_key', value: '********', value_type: 'string', scope_origin: 'tenant', is_secret: true }] },
      });
      render(<ParameterManagement tenant="T1" />);
      await act(async () => { jest.advanceTimersByTime(0); });
      await waitFor(() => expect(screen.getByText('********')).toBeInTheDocument());
    });

    test('shows empty state when no parameters', async () => {
      getParameters.mockResolvedValue({ success: true, tenant: 'T1', parameters: {} });
      render(<ParameterManagement tenant="T1" />);
      await act(async () => { jest.advanceTimersByTime(0); });
      await waitFor(() => expect(screen.getByText('tenantAdmin.parameters.noParameters')).toBeInTheDocument());
    });
  });

  describe('Row Click', () => {
    test('clicking tenant row opens edit modal', async () => {
      await renderAndWait();
      fireEvent.click(screen.getByText('provider'));
      await waitFor(() => expect(screen.getByText(/tenantAdmin.parameters.editParameter/)).toBeInTheDocument());
    });

    test('clicking system row does not open modal', async () => {
      await renderAndWait();
      fireEvent.click(screen.getByText('bucket'));
      expect(screen.queryByText(/tenantAdmin.parameters.editParameter/)).not.toBeInTheDocument();
    });
  });

  describe('Add Parameter', () => {
    test('add button is visible', async () => {
      await renderAndWait();
      expect(screen.getByText('tenantAdmin.parameters.addParameter')).toBeInTheDocument();
    });
  });

  describe('FilterableHeader Integration', () => {
    test('renders 5 filter inputs in column headers', async () => {
      await renderAndWait();
      const filterInputs = screen.getAllByPlaceholderText('Filter...');
      expect(filterInputs).toHaveLength(5);
    });

    test('renders column header labels', async () => {
      await renderAndWait();
      expect(screen.getByText('tenantAdmin.parameters.namespace')).toBeInTheDocument();
      expect(screen.getByText('tenantAdmin.parameters.key')).toBeInTheDocument();
      expect(screen.getByText('tenantAdmin.parameters.value')).toBeInTheDocument();
      expect(screen.getByText('tenantAdmin.parameters.valueType')).toBeInTheDocument();
      expect(screen.getByText('tenantAdmin.parameters.scope')).toBeInTheDocument();
    });

    test('filter inputs have accessible aria-labels', async () => {
      await renderAndWait();
      expect(screen.getByLabelText('Filter by tenantAdmin.parameters.namespace')).toBeInTheDocument();
      expect(screen.getByLabelText('Filter by tenantAdmin.parameters.key')).toBeInTheDocument();
      expect(screen.getByLabelText('Filter by tenantAdmin.parameters.value')).toBeInTheDocument();
      expect(screen.getByLabelText('Filter by tenantAdmin.parameters.valueType')).toBeInTheDocument();
      expect(screen.getByLabelText('Filter by tenantAdmin.parameters.scope')).toBeInTheDocument();
    });

    test('filters by namespace using case-insensitive substring match', async () => {
      await renderAndWait();

      // All 3 params visible initially
      expect(screen.getByText('currency')).toBeInTheDocument();
      expect(screen.getByText('bucket')).toBeInTheDocument();

      // Type "stor" in the namespace filter and advance past debounce
      const nsFilter = screen.getByLabelText('Filter by tenantAdmin.parameters.namespace');
      changeFilter(nsFilter, 'stor');

      // Only storage namespace params should remain
      expect(screen.getByText('provider')).toBeInTheDocument();
      expect(screen.getByText('bucket')).toBeInTheDocument();
      expect(screen.queryByText('currency')).not.toBeInTheDocument();
    });

    test('filters by key using case-insensitive substring match', async () => {
      await renderAndWait();

      const keyFilter = screen.getByLabelText('Filter by tenantAdmin.parameters.key');
      changeFilter(keyFilter, 'CUR');

      // Only "currency" key should match
      expect(screen.getByText('currency')).toBeInTheDocument();
      expect(screen.queryByText('provider')).not.toBeInTheDocument();
      expect(screen.queryByText('bucket')).not.toBeInTheDocument();
    });

    test('applies AND logic across multiple filters simultaneously', async () => {
      await renderAndWait();

      const nsFilter = screen.getByLabelText('Filter by tenantAdmin.parameters.namespace');
      const keyFilter = screen.getByLabelText('Filter by tenantAdmin.parameters.key');

      // Filter namespace = "storage" AND key = "prov"
      changeFilter(nsFilter, 'storage');
      changeFilter(keyFilter, 'prov');

      // Only provider should match (storage namespace + key contains "prov")
      expect(screen.getByText('provider')).toBeInTheDocument();
      expect(screen.queryByText('bucket')).not.toBeInTheDocument();
      expect(screen.queryByText('currency')).not.toBeInTheDocument();
    });

    test('shows empty state when filters match no parameters', async () => {
      await renderAndWait();

      const nsFilter = screen.getByLabelText('Filter by tenantAdmin.parameters.namespace');
      changeFilter(nsFilter, 'nonexistent');

      expect(screen.getByText('tenantAdmin.parameters.noParameters')).toBeInTheDocument();
    });

    test('loads all parameters without namespace filter parameter', async () => {
      await renderAndWait();

      // getParameters should be called without any namespace argument (loads all params)
      expect(getParameters).toHaveBeenCalledWith();
    });
  });
});

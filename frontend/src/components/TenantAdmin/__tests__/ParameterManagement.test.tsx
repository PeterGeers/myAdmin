/**
 * ParameterManagement Component - Unit Tests
 *
 * Tests the parameter management UI including:
 * - Rendering parameters in a table
 * - FilterableHeader inline column filters (v2 framework)
 * - Row-click modal for all parameters (no inline action buttons)
 * - Edit/delete parameter workflows
 * - Verification that Actions column, Add button, and inline buttons are removed
 * - Modal read-only vs edit mode behavior (Task 9)
 * - Reset to Default and Delete button logic (Task 9)
 * - JSON validation and Format button (Task 9)
 * - Customize flow for system-scope parameters (Task 9)
 *
 * Chakra UI Modal/AlertDialog + React 19 + jsdom causes infinite re-render
 * loops when portals open. We replace all portal-based Chakra components with
 * simple inline wrappers so the modal content renders in the same DOM tree.
 * useDisclosure and useToast are also replaced with stable implementations.
 */
import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '../../../test-utils';

/* ------------------------------------------------------------------ */
/*  Chakra UI mock — render modals inline, stable hooks                */
/* ------------------------------------------------------------------ */
const mockToast = vi.fn();

vi.mock('@chakra-ui/react', async () => {
  const mocks = await vi.importActual<typeof import('@/__mocks__/chakra-ui-react')>('@/__mocks__/chakra-ui-react');
  const React = await import('react');

  // Stable useDisclosure that doesn't trigger cascading re-renders
  function useDisclosure() {
    const [isOpen, setIsOpen] = React.useState(false);
    const onOpen = React.useCallback(() => setIsOpen(true), []);
    const onClose = React.useCallback(() => setIsOpen(false), []);
    return { isOpen, onOpen, onClose };
  }

  return {
    ...mocks,
    useDisclosure,
    useToast: () => mockToast,
    // Tr override: forward cursor as inline style so toHaveStyle assertions work
    Tr: ({ children, cursor, ...props }: any) => (
      <tr style={cursor ? { cursor } : undefined} {...props}>{children}</tr>
    ),
    // Portal-free modal components with data-testid for test queries
    Modal: ({ isOpen, children }: any) =>
      isOpen ? <div data-testid="modal">{children}</div> : null,
    ModalOverlay: ({ children }: any) => <>{children}</>,
    ModalContent: ({ children, bg, ...rest }: any) => <div>{children}</div>,
    ModalHeader: ({ children, ...rest }: any) => <div>{children}</div>,
    ModalBody: ({ children }: any) => <div>{children}</div>,
    ModalFooter: ({ children }: any) => <div>{children}</div>,
    ModalCloseButton: () => <button aria-label="Close" />,
    // Portal-free alert dialog components
    AlertDialog: ({ isOpen, children }: any) =>
      isOpen ? <div data-testid="alert-dialog">{children}</div> : null,
    AlertDialogOverlay: ({ children }: any) => <>{children}</>,
    AlertDialogContent: ({ children, bg, ...rest }: any) => <div>{children}</div>,
    AlertDialogHeader: ({ children, ...rest }: any) => <div>{children}</div>,
    AlertDialogBody: ({ children, ...rest }: any) => <div>{children}</div>,
    AlertDialogFooter: ({ children }: any) => <div>{children}</div>,
  };
});

import ParameterManagement from '../ParameterManagement';

// Mock the parameter service
vi.mock('../../../services/parameterService', () => ({
  getParameters: vi.fn(),
  createParameter: vi.fn(),
  updateParameter: vi.fn(),
  deleteParameter: vi.fn(),
  getParameterDefault: vi.fn(),
}));

// Stable translation function reference to prevent useCallback/useEffect loops
// (must be prefixed with 'mock' to be accessible inside vi.mock())
const mockT = (key: string) => key;
const mockI18n = { language: 'en', changeLanguage: vi.fn() };

vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: mockT,
    i18n: mockI18n,
  }),
}));

vi.mock('../../../hooks/useTableConfig', () => ({
  useTableConfig: () => ({
    columns: ['namespace', 'key', 'value', 'value_type', 'scope_origin'],
    filterableColumns: ['namespace', 'key', 'value', 'value_type', 'scope_origin'],
    defaultSort: { field: 'namespace', direction: 'asc' },
    pageSize: 100,
    loading: false,
    error: null,
  }),
}));

// Mock useColumnFilters to bypass debounce
vi.mock('../../../hooks/useColumnFilters', () => {
  const { useState, useMemo, useCallback } = require('react');

  function applyFilters(data: any[], filters: Record<string, string>) {
    const active = Object.entries(filters).filter(([, v]) => v !== '');
    if (active.length === 0) return data;
    return data.filter((row: any) =>
      active.every(([key, filterValue]) => {
        if (!(key in row)) return true;
        return String(row[key] ?? '').toLowerCase().includes(filterValue.toLowerCase());
      }),
    );
  }

  return {
    useColumnFilters: (data: any[], initialFilters: Record<string, string>) => {
      const [filters, setFiltersState] = (useState as any)(
        () => Object.fromEntries(Object.keys(initialFilters).map((k) => [k, ''])),
      );
      const setFilter = useCallback((key: string, value: string) => {
        setFiltersState((prev: Record<string, string>) => ({ ...prev, [key]: value }));
      }, []);
      const resetFilters = useCallback(() => {
        setFiltersState(Object.fromEntries(Object.keys(filters).map((k: string) => [k, ''])));
      }, [filters]);
      const filteredData = useMemo(() => applyFilters(data, filters), [data, filters]);
      const hasActiveFilters = useMemo(
        () => Object.values(filters).some((v) => v !== ''),
        [filters],
      );
      return { filters, setFilter, resetFilters, filteredData, hasActiveFilters };
    },
  };
});

import { getParameters, createParameter, deleteParameter, getParameterDefault } from '../../../services/parameterService';

/* ------------------------------------------------------------------ */
/*  Test data                                                          */
/* ------------------------------------------------------------------ */

const mockParams = {
  success: true,
  tenant: 'T1',
  parameters: {
    storage: [
      { id: 1, namespace: 'storage', key: 'provider', value: 'google_drive', value_type: 'string' as const, scope_origin: 'tenant' as const, is_secret: false },
      { id: null, namespace: 'storage', key: 'bucket', value: 'default', value_type: 'string' as const, scope_origin: 'system' as const, is_secret: false },
    ],
    fin: [
      { id: 2, namespace: 'fin', key: 'currency', value: 'EUR', value_type: 'string' as const, scope_origin: 'tenant' as const, is_secret: false },
    ],
  },
};

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

describe('ParameterManagement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockToast.mockClear();
    vi.mocked(getParameters).mockResolvedValue(mockParams);
  });

  /** Helper: render and wait for data to load */
  async function renderAndWait() {
    render(<ParameterManagement tenant="T1" />);
    await waitFor(() => {
      expect(screen.queryByText('Loading parameters...')).not.toBeInTheDocument();
      expect(screen.getByText('provider')).toBeInTheDocument();
    });
  }

  // ========================================================================
  // Rendering
  // ========================================================================

  describe('Rendering', () => {
    test('shows loading spinner initially', () => {
      vi.mocked(getParameters).mockReturnValue(new Promise(() => {}));
      render(<ParameterManagement tenant="T1" />);
      expect(screen.getByText('Loading parameters...')).toBeInTheDocument();
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
      expect(screen.getAllByText('tenant override').length).toBeGreaterThan(0);
      expect(screen.getAllByText('system default').length).toBeGreaterThan(0);
    });

    test('shows secret values as masked', async () => {
      vi.mocked(getParameters).mockResolvedValue({
        success: true, tenant: 'T1',
        parameters: { ns: [{ id: 3, namespace: 'ns', key: 'api_key', value: '********', value_type: 'string' as const, scope_origin: 'tenant' as const, is_secret: true }] },
      });
      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('********')).toBeInTheDocument());
    });

    test('shows empty state when no parameters', async () => {
      vi.mocked(getParameters).mockResolvedValue({ success: true, tenant: 'T1', parameters: {} });
      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('tenantAdmin.parameters.noParameters')).toBeInTheDocument());
    });
  });

  // ========================================================================
  // Row Click
  // ========================================================================

  describe('Row Click', () => {
    test('clicking tenant row has pointer cursor', async () => {
      await renderAndWait();
      const row = screen.getByText('provider').closest('tr');
      expect(row).toHaveStyle('cursor: pointer');
    });

    test('clicking system row has pointer cursor (all rows clickable)', async () => {
      await renderAndWait();
      const row = screen.getByText('bucket').closest('tr');
      expect(row).toHaveStyle('cursor: pointer');
    });
  });

  // ========================================================================
  // Removed UI Elements (Req 4.1, 4.2)
  // ========================================================================

  describe('Removed UI Elements', () => {
    test('actions column header is not rendered', async () => {
      await renderAndWait();
      expect(screen.queryByText('Actions')).not.toBeInTheDocument();
    });

    test('add button is not rendered', async () => {
      await renderAndWait();
      expect(screen.queryByText('tenantAdmin.parameters.addParameter')).not.toBeInTheDocument();
    });

    test('no inline customize or reset buttons in rows', async () => {
      await renderAndWait();
      expect(screen.queryByLabelText('Customize')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Reset to default')).not.toBeInTheDocument();
    });
  });

  // ========================================================================
  // FilterableHeader Integration
  // ========================================================================

  describe('FilterableHeader Integration', () => {
    test('renders 5 filter inputs in column headers', async () => {
      await renderAndWait();
      expect(screen.getAllByPlaceholderText('Filter...')).toHaveLength(5);
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
      const nsFilter = screen.getByLabelText('Filter by tenantAdmin.parameters.namespace');
      fireEvent.change(nsFilter, { target: { value: 'stor' } });
      await waitFor(() => {
        expect(screen.getByText('provider')).toBeInTheDocument();
        expect(screen.getByText('bucket')).toBeInTheDocument();
        expect(screen.queryByText('currency')).not.toBeInTheDocument();
      });
    });

    test('filters by key using case-insensitive substring match', async () => {
      await renderAndWait();
      const keyFilter = screen.getByLabelText('Filter by tenantAdmin.parameters.key');
      fireEvent.change(keyFilter, { target: { value: 'CUR' } });
      await waitFor(() => {
        expect(screen.getByText('currency')).toBeInTheDocument();
        expect(screen.queryByText('provider')).not.toBeInTheDocument();
        expect(screen.queryByText('bucket')).not.toBeInTheDocument();
      });
    });

    test('applies AND logic across multiple filters simultaneously', async () => {
      await renderAndWait();
      const nsFilter = screen.getByLabelText('Filter by tenantAdmin.parameters.namespace');
      fireEvent.change(nsFilter, { target: { value: 'storage' } });
      await waitFor(() => expect(screen.queryByText('currency')).not.toBeInTheDocument());

      const keyFilter = screen.getByLabelText('Filter by tenantAdmin.parameters.key');
      fireEvent.change(keyFilter, { target: { value: 'prov' } });
      await waitFor(() => {
        expect(screen.getByText('provider')).toBeInTheDocument();
        expect(screen.queryByText('bucket')).not.toBeInTheDocument();
      });
    });

    test('shows empty state when filters match no parameters', async () => {
      await renderAndWait();
      const nsFilter = screen.getByLabelText('Filter by tenantAdmin.parameters.namespace');
      fireEvent.change(nsFilter, { target: { value: 'nonexistent' } });
      await waitFor(() => {
        expect(screen.getByText('tenantAdmin.parameters.noParameters')).toBeInTheDocument();
      });
    });

    test('loads all parameters without namespace filter parameter', async () => {
      await renderAndWait();
      expect(getParameters).toHaveBeenCalledWith();
    });
  });

  // ========================================================================
  // Modal — System Parameter Read-Only (Req 4.3, 4.4, 4.5)
  // ========================================================================

  describe('Modal — System Parameter (Read-Only)', () => {
    test('system-scope row opens read-only modal with Customize button', async () => {
      await renderAndWait();

      fireEvent.click(screen.getByText('bucket'));

      await waitFor(() => {
        expect(screen.getByText(/tenantAdmin\.parameters\.viewParameter/)).toBeInTheDocument();
      });

      // Value field should be disabled (read-only)
      const valueInput = screen.getByDisplayValue('default');
      expect(valueInput).toBeDisabled();

      // Customize button present, Save absent
      expect(screen.getByText('tenantAdmin.parameters.customize')).toBeInTheDocument();
      expect(screen.queryByText('Save')).not.toBeInTheDocument();
    });

    test('Customize creates tenant copy via createParameter', async () => {
      vi.mocked(createParameter).mockResolvedValue({ success: true });

      await renderAndWait();
      fireEvent.click(screen.getByText('bucket'));

      await waitFor(() => {
        expect(screen.getByText('tenantAdmin.parameters.customize')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('tenantAdmin.parameters.customize'));

      await waitFor(() => {
        expect(createParameter).toHaveBeenCalledWith(
          expect.objectContaining({
            scope: 'tenant',
            namespace: 'storage',
            key: 'bucket',
          }),
        );
      });
    });
  });

  // ========================================================================
  // Modal — Tenant Parameter Edit Mode (Req 2.1, 2.2, 4.3, 4.4)
  // ========================================================================

  describe('Modal — Tenant Parameter (Edit Mode)', () => {
    test('tenant-scope row opens edit modal with Save button', async () => {
      await renderAndWait();

      fireEvent.click(screen.getByText('provider'));

      await waitFor(() => {
        expect(screen.getByText(/tenantAdmin\.parameters\.editParameter/)).toBeInTheDocument();
      });

      // Value field should be enabled
      const valueInput = screen.getByDisplayValue('google_drive');
      expect(valueInput).not.toBeDisabled();

      // Save button present
      expect(screen.getByText('Save')).toBeInTheDocument();
    });

    test('Reset to Default button shown when has_code_default is true', async () => {
      vi.mocked(getParameters).mockResolvedValue({
        success: true, tenant: 'T1',
        parameters: {
          storage: [
            { id: 10, namespace: 'storage', key: 'provider', value: 'custom', value_type: 'string' as const, scope_origin: 'tenant' as const, is_secret: false, has_code_default: true },
          ],
        },
      });

      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('provider')).toBeInTheDocument());

      fireEvent.click(screen.getByText('provider'));

      await waitFor(() => {
        expect(screen.getByText('tenantAdmin.parameters.resetToDefaultBtn')).toBeInTheDocument();
      });
      expect(screen.queryByText('Delete')).not.toBeInTheDocument();
    });

    test('Delete button shown when has_code_default is false', async () => {
      vi.mocked(getParameters).mockResolvedValue({
        success: true, tenant: 'T1',
        parameters: {
          custom: [
            { id: 20, namespace: 'custom', key: 'my_setting', value: 'abc', value_type: 'string' as const, scope_origin: 'tenant' as const, is_secret: false, has_code_default: false },
          ],
        },
      });

      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('my_setting')).toBeInTheDocument());

      fireEvent.click(screen.getByText('my_setting'));

      await waitFor(() => {
        expect(screen.getByText('Delete')).toBeInTheDocument();
      });
      expect(screen.queryByText('tenantAdmin.parameters.resetToDefaultBtn')).not.toBeInTheDocument();
    });
  });

  // ========================================================================
  // Reset to Default Flow (Req 2.3, 3.6, 3.7, 7.1, 7.2)
  // ========================================================================

  describe('Reset to Default Flow', () => {
    const paramsWithCodeDefault = {
      success: true, tenant: 'T1',
      parameters: {
        storage: [
          { id: 10, namespace: 'storage', key: 'provider', value: 'custom_val', value_type: 'string' as const, scope_origin: 'tenant' as const, is_secret: false, has_code_default: true },
        ],
      },
    };

    /** Open the edit modal and click Reset to Default to open the confirmation dialog */
    async function openResetDialog() {
      vi.mocked(getParameters).mockResolvedValue(paramsWithCodeDefault);
      vi.mocked(getParameterDefault).mockResolvedValue({
        success: true, has_default: true,
        value: 'google_drive', value_type: 'string', source: 'code_default',
      });

      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('provider')).toBeInTheDocument());

      // Open edit modal
      fireEvent.click(screen.getByText('provider'));
      await waitFor(() => {
        expect(screen.getByText('tenantAdmin.parameters.resetToDefaultBtn')).toBeInTheDocument();
      });

      // Click Reset to Default → fetches default, opens confirmation dialog
      fireEvent.click(screen.getByText('tenantAdmin.parameters.resetToDefaultBtn'));
      await waitFor(() => {
        expect(screen.getByText(/Reset: storage\.provider/)).toBeInTheDocument();
      });
    }

    test('confirm reset calls deleteParameter and refreshes list', async () => {
      vi.mocked(deleteParameter).mockResolvedValue({ success: true });

      await openResetDialog();

      // Confirmation dialog shows current and default value labels
      expect(screen.getByText('tenantAdmin.parameters.currentValue')).toBeInTheDocument();

      // Click confirm — the dialog has a second resetToDefaultBtn
      const confirmButtons = screen.getAllByText('tenantAdmin.parameters.resetToDefaultBtn');
      fireEvent.click(confirmButtons[confirmButtons.length - 1]);

      await waitFor(() => {
        expect(deleteParameter).toHaveBeenCalledWith(10);
      });

      // List refreshed after reset
      const callCount = vi.mocked(getParameters).mock.calls.length;
      expect(callCount).toBeGreaterThanOrEqual(2);
    });

    test('cancel reset closes dialog without API call', async () => {
      await openResetDialog();

      // Click Cancel in the confirmation dialog
      const cancelButtons = screen.getAllByText('Cancel');
      fireEvent.click(cancelButtons[cancelButtons.length - 1]);

      await waitFor(() => {
        expect(screen.queryByText(/Reset: storage\.provider/)).not.toBeInTheDocument();
      });

      expect(deleteParameter).not.toHaveBeenCalled();
    });

    test('success toast on reset', async () => {
      vi.mocked(deleteParameter).mockResolvedValue({ success: true });

      await openResetDialog();

      const confirmButtons = screen.getAllByText('tenantAdmin.parameters.resetToDefaultBtn');
      fireEvent.click(confirmButtons[confirmButtons.length - 1]);

      await waitFor(() => {
        expect(deleteParameter).toHaveBeenCalledWith(10);
      });

      // Toast was called with success status
      await waitFor(() => {
        expect(mockToast).toHaveBeenCalledWith(
          expect.objectContaining({ status: 'success' }),
        );
      });
    });

    test('error toast on reset failure', async () => {
      vi.mocked(deleteParameter).mockRejectedValue(new Error('Network error'));

      await openResetDialog();

      const confirmButtons = screen.getAllByText('tenantAdmin.parameters.resetToDefaultBtn');
      fireEvent.click(confirmButtons[confirmButtons.length - 1]);

      await waitFor(() => {
        expect(deleteParameter).toHaveBeenCalledWith(10);
      });

      await waitFor(() => {
        expect(mockToast).toHaveBeenCalledWith(
          expect.objectContaining({ status: 'error' }),
        );
      });
    });
  });

  // ========================================================================
  // JSON Validation and Format (Req 5.1, 5.2, 5.5)
  // ========================================================================

  describe('JSON Validation and Format', () => {
    const jsonParams = {
      success: true, tenant: 'T1',
      parameters: {
        table: [
          { id: 30, namespace: 'table', key: 'sort_config', value: { field: 'name', direction: 'asc' }, value_type: 'json' as const, scope_origin: 'tenant' as const, is_secret: false, has_code_default: true },
        ],
      },
    };

    test('invalid JSON disables Save and shows error', async () => {
      vi.mocked(getParameters).mockResolvedValue(jsonParams);

      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => {
        expect(screen.queryByText('Loading parameters...')).not.toBeInTheDocument();
        expect(screen.getByText('sort_config')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('sort_config'));
      await waitFor(() => expect(screen.getByText('Save')).toBeInTheDocument());

      // Target the textarea specifically (not the filter inputs)
      const textarea = document.querySelector('textarea') as HTMLTextAreaElement;
      expect(textarea).toBeTruthy();

      fireEvent.change(textarea, { target: { value: '{ invalid json' } });

      await waitFor(() => {
        expect(screen.getByText('Save')).toBeDisabled();
      });
      expect(screen.getByText(/Invalid JSON/)).toBeInTheDocument();
    });

    test('Format button re-indents valid JSON', async () => {
      vi.mocked(getParameters).mockResolvedValue(jsonParams);

      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => {
        expect(screen.queryByText('Loading parameters...')).not.toBeInTheDocument();
        expect(screen.getByText('sort_config')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('sort_config'));
      await waitFor(() => expect(screen.getByText('Format')).toBeInTheDocument());

      // Target the textarea specifically
      const textarea = document.querySelector('textarea') as HTMLTextAreaElement;
      expect(textarea).toBeTruthy();

      fireEvent.change(textarea, { target: { value: '{"field":"name","direction":"asc"}' } });

      fireEvent.click(screen.getByText('Format'));

      const expected = JSON.stringify({ field: 'name', direction: 'asc' }, null, 2);
      await waitFor(() => {
        expect(textarea.value).toBe(expected);
      });
    });
  });
});

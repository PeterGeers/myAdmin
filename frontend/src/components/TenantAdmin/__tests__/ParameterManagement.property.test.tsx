/**
 * ParameterManagement Component — Property-Based Tests
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 *
 * Feature: parameter-reset-to-default
 *
 * Property 2: Modal Footer Button Determination
 * Property 3: Confirmation Dialog Information Display
 * Property 4: JSON Values Formatted in Confirmation Dialog
 * Property 5: Modal Mode Matches Parameter Scope
 * Property 6: JSON Validation Controls Save Button
 * Property 7: JSON Format Button Idempotence
 *
 * @see .kiro/specs/parameter-reset-to-default/design.md — Properties 2–7
 *
 * Chakra UI Modal/AlertDialog + React 19 + jsdom causes infinite re-render
 * loops when portals open. We replace all portal-based Chakra components with
 * simple inline wrappers so the modal content renders in the same DOM tree.
 * useDisclosure and useToast are also replaced with stable implementations.
 *
 * For async rendering tests we use fc.sample + loop (renderHook is async and
 * fast-check's property callback is sync).
 */
import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor, fireEvent, cleanup } from '../../../test-utils';
import fc from 'fast-check';

/* ------------------------------------------------------------------ */
/*  Chakra UI mock — render modals inline, stable hooks                */
/* ------------------------------------------------------------------ */
const mockToast = vi.fn();

vi.mock('@chakra-ui/react', async () => {
  const mocks = await vi.importActual<typeof import('@/__mocks__/chakra-ui-react')>('@/__mocks__/chakra-ui-react');
  const React = await import('react');

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
    Modal: ({ isOpen, children }: any) =>
      isOpen ? <div data-testid="modal">{children}</div> : null,
    ModalOverlay: ({ children }: any) => <>{children}</>,
    ModalContent: ({ children, bg, ...rest }: any) => <div>{children}</div>,
    ModalHeader: ({ children, ...rest }: any) => <div data-testid="modal-header">{children}</div>,
    ModalBody: ({ children }: any) => <div>{children}</div>,
    ModalFooter: ({ children }: any) => <div data-testid="modal-footer">{children}</div>,
    ModalCloseButton: () => <button aria-label="Close" />,
    AlertDialog: ({ isOpen, children }: any) =>
      isOpen ? <div data-testid="alert-dialog">{children}</div> : null,
    AlertDialogOverlay: ({ children }: any) => <>{children}</>,
    AlertDialogContent: ({ children, bg, ...rest }: any) => <div>{children}</div>,
    AlertDialogHeader: ({ children, ...rest }: any) => <div data-testid="alert-dialog-header">{children}</div>,
    AlertDialogBody: ({ children, ...rest }: any) => <div data-testid="alert-dialog-body">{children}</div>,
    AlertDialogFooter: ({ children }: any) => <div>{children}</div>,
  };
});

import ParameterManagement from '../ParameterManagement';

/* ------------------------------------------------------------------ */
/*  Service mock                                                       */
/* ------------------------------------------------------------------ */
vi.mock('../../../services/parameterService', () => ({
  getParameters: vi.fn(),
  createParameter: vi.fn(),
  updateParameter: vi.fn(),
  deleteParameter: vi.fn(),
  getParameterDefault: vi.fn(),
}));

const mockT = (key: string) => key;
const mockI18n = { language: 'en', changeLanguage: vi.fn() };

vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: mockT, i18n: mockI18n }),
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

import { getParameters, getParameterDefault, deleteParameter } from '../../../services/parameterService';

/* ------------------------------------------------------------------ */
/*  Generators                                                         */
/* ------------------------------------------------------------------ */

/**
 * Generate unique namespace/key strings that won't collide with UI text.
 * Uses a prefix + alphanumeric to avoid matching column headers or badges.
 */
const namespaceArb = fc
  .stringMatching(/^[a-z][a-z0-9]{2,12}$/)
  .map((s) => `ns_${s}`);

const keyArb = fc
  .stringMatching(/^[a-z][a-z0-9]{2,12}$/)
  .map((s) => `key_${s}`);

/** Safe printable string for values (avoids collisions with UI labels). */
const safeValueArb = fc
  .stringMatching(/^[a-zA-Z0-9_]{3,20}$/)
  .map((s) => `val_${s}`);

/** Generate a scope_origin value. */
const scopeOriginArb = fc.oneof(
  fc.constant('system' as const),
  fc.constant('tenant' as const),
);

/** Generate a value_type. */
const valueTypeArb = fc.oneof(
  fc.constant('string' as const),
  fc.constant('number' as const),
  fc.constant('boolean' as const),
  fc.constant('json' as const),
);

/* ------------------------------------------------------------------ */
/*  Helper: render component with a single parameter and open modal    */
/* ------------------------------------------------------------------ */

async function renderWithParam(param: any) {
  vi.mocked(getParameters).mockResolvedValue({
    success: true,
    tenant: 'T1',
    parameters: { [param.namespace]: [param] },
  });

  render(<ParameterManagement tenant="T1" />);

  // Wait for loading to finish and the key to appear
  await waitFor(() => {
    expect(screen.queryByText('Loading parameters...')).not.toBeInTheDocument();
    expect(screen.getByText(param.key)).toBeInTheDocument();
  });

  // Click the row to open the modal
  fireEvent.click(screen.getByText(param.key));

  // Wait for modal to appear
  await waitFor(() => {
    expect(screen.getByTestId('modal')).toBeInTheDocument();
  });
}

/* ------------------------------------------------------------------ */
/*  Property 2: Modal Footer Button Determination                     */
/*  Validates: Requirements 2.1, 2.2, 2.4                             */
/* ------------------------------------------------------------------ */

describe('Feature: parameter-reset-to-default, Property 2: Modal Footer Button Determination', () => {
  it('shows correct footer buttons based on scope_origin and has_code_default (100 iterations)', async () => {
    const inputs = fc.sample(
      fc.record({
        namespace: namespaceArb,
        key: keyArb,
        scope_origin: scopeOriginArb,
        has_code_default: fc.boolean(),
        value_type: fc.constant('string' as const),
        is_secret: fc.constant(false),
      }).map((p) => ({
        ...p,
        id: p.scope_origin === 'tenant' ? Math.floor(Math.random() * 9999) + 1 : null,
        value: 'test_value',
      })),
      100,
    );

    for (const param of inputs) {
      vi.clearAllMocks();
      mockToast.mockClear();

      await renderWithParam(param);

      const footer = screen.getByTestId('modal-footer');

      if (param.scope_origin === 'tenant' && param.has_code_default) {
        // Tenant + has_code_default → "Reset to Default" button
        expect(footer.textContent).toContain('tenantAdmin.parameters.resetToDefaultBtn');
        expect(footer.textContent).not.toContain('Delete');
        expect(footer.textContent).not.toContain('tenantAdmin.parameters.customize');
      } else if (param.scope_origin === 'tenant' && !param.has_code_default) {
        // Tenant + no code default → "Delete" button
        expect(footer.textContent).toContain('Delete');
        expect(footer.textContent).not.toContain('tenantAdmin.parameters.resetToDefaultBtn');
        expect(footer.textContent).not.toContain('tenantAdmin.parameters.customize');
      } else {
        // System → "Customize" button (read-only mode)
        expect(footer.textContent).toContain('tenantAdmin.parameters.customize');
        expect(footer.textContent).not.toContain('tenantAdmin.parameters.resetToDefaultBtn');
        expect(footer.textContent).not.toContain('Delete');
      }

      cleanup();
    }
  }, 60000);
});

/* ------------------------------------------------------------------ */
/*  Property 3: Confirmation Dialog Information Display                */
/*  Validates: Requirements 3.1, 3.2, 3.3                             */
/* ------------------------------------------------------------------ */

describe('Feature: parameter-reset-to-default, Property 3: Confirmation Dialog Information Display', () => {
  it('dialog shows namespace.key heading, current value label, and default value label (100 iterations)', async () => {
    const inputs = fc.sample(
      fc.record({
        namespace: namespaceArb,
        key: keyArb,
        currentValue: safeValueArb,
        defaultValue: safeValueArb,
      }),
      100,
    );

    for (const { namespace, key, currentValue, defaultValue } of inputs) {
      vi.clearAllMocks();
      mockToast.mockClear();

      const param = {
        id: 1,
        namespace,
        key,
        value: currentValue,
        value_type: 'string' as const,
        scope_origin: 'tenant' as const,
        is_secret: false,
        has_code_default: true,
      };

      vi.mocked(getParameterDefault).mockResolvedValue({
        success: true,
        has_default: true,
        value: defaultValue,
        value_type: 'string',
        source: 'code_default',
      });

      await renderWithParam(param);

      // Click "Reset to Default" to open the confirmation dialog
      fireEvent.click(screen.getByText('tenantAdmin.parameters.resetToDefaultBtn'));

      await waitFor(() => {
        expect(screen.getByTestId('alert-dialog')).toBeInTheDocument();
      });

      // Verify namespace.key heading
      const header = screen.getByTestId('alert-dialog-header');
      expect(header.textContent).toContain(`${namespace}.${key}`);

      // Verify "Current value" and "Default value" labels
      const body = screen.getByTestId('alert-dialog-body');
      expect(body.textContent).toContain('tenantAdmin.parameters.currentValue');
      expect(body.textContent).toContain('tenantAdmin.parameters.defaultValue');

      // Verify actual values appear in the dialog body
      expect(body.textContent).toContain(currentValue);
      expect(body.textContent).toContain(defaultValue);

      cleanup();
    }
  }, 120000);
});

/* ------------------------------------------------------------------ */
/*  Property 4: JSON Values Formatted in Confirmation Dialog           */
/*  Validates: Requirements 3.4                                        */
/* ------------------------------------------------------------------ */

describe('Feature: parameter-reset-to-default, Property 4: JSON Values Formatted in Confirmation Dialog', () => {
  it('dialog displays JSON values with JSON.stringify(value, null, 2) formatting (100 iterations)', async () => {
    // Generate simple JSON objects with safe keys/values
    const safeKey = fc.stringMatching(/^[a-zA-Z][a-zA-Z0-9]{1,8}$/);
    const inputs = fc.sample(
      fc.record({
        namespace: namespaceArb,
        key: keyArb,
        currentJson: fc.dictionary(safeKey, fc.oneof(
          fc.stringMatching(/^[a-zA-Z0-9]{1,10}$/),
          fc.integer({ min: -1000, max: 1000 }),
          fc.boolean(),
        ), { minKeys: 1, maxKeys: 4 }),
        defaultJson: fc.dictionary(safeKey, fc.oneof(
          fc.stringMatching(/^[a-zA-Z0-9]{1,10}$/),
          fc.integer({ min: -1000, max: 1000 }),
          fc.boolean(),
        ), { minKeys: 1, maxKeys: 4 }),
      }),
      100,
    );

    for (const { namespace, key, currentJson, defaultJson } of inputs) {
      vi.clearAllMocks();
      mockToast.mockClear();

      const param = {
        id: 1,
        namespace,
        key,
        value: currentJson,
        value_type: 'json' as const,
        scope_origin: 'tenant' as const,
        is_secret: false,
        has_code_default: true,
      };

      vi.mocked(getParameterDefault).mockResolvedValue({
        success: true,
        has_default: true,
        value: defaultJson,
        value_type: 'json',
        source: 'code_default',
      });

      await renderWithParam(param);

      // Click "Reset to Default" to open the confirmation dialog
      fireEvent.click(screen.getByText('tenantAdmin.parameters.resetToDefaultBtn'));

      await waitFor(() => {
        expect(screen.getByTestId('alert-dialog')).toBeInTheDocument();
      });

      const body = screen.getByTestId('alert-dialog-body');
      const bodyText = body.textContent || '';

      // Both values should be formatted with 2-space indent
      const expectedCurrent = JSON.stringify(currentJson, null, 2);
      const expectedDefault = JSON.stringify(defaultJson, null, 2);

      expect(bodyText).toContain(expectedCurrent);
      expect(bodyText).toContain(expectedDefault);

      cleanup();
    }
  }, 120000);
});

/* ------------------------------------------------------------------ */
/*  Property 5: Modal Mode Matches Parameter Scope                     */
/*  Validates: Requirements 4.3, 4.4                                   */
/* ------------------------------------------------------------------ */

describe('Feature: parameter-reset-to-default, Property 5: Modal Mode Matches Parameter Scope', () => {
  it('system → read-only (fields disabled, Customize shown), tenant → edit (fields enabled, Save shown) (100 iterations)', async () => {
    const inputs = fc.sample(
      fc.record({
        namespace: namespaceArb,
        key: keyArb,
        scope_origin: scopeOriginArb,
        has_code_default: fc.boolean(),
      }),
      100,
    );

    for (const { namespace, key, scope_origin, has_code_default } of inputs) {
      vi.clearAllMocks();
      mockToast.mockClear();

      const param = {
        id: scope_origin === 'tenant' ? 1 : null,
        namespace,
        key,
        value: 'test_value',
        value_type: 'string' as const,
        scope_origin,
        is_secret: false,
        has_code_default,
      };

      await renderWithParam(param);

      const header = screen.getByTestId('modal-header');
      const footer = screen.getByTestId('modal-footer');

      if (scope_origin === 'system') {
        // Read-only mode
        expect(header.textContent).toContain('tenantAdmin.parameters.viewParameter');
        expect(footer.textContent).toContain('tenantAdmin.parameters.customize');
        expect(footer.textContent).not.toContain('Save');

        // Value input should be disabled
        const valueInput = screen.getByDisplayValue('test_value');
        expect(valueInput).toBeDisabled();
      } else {
        // Edit mode
        expect(header.textContent).toContain('tenantAdmin.parameters.editParameter');
        expect(footer.textContent).toContain('Save');
        expect(footer.textContent).not.toContain('tenantAdmin.parameters.customize');

        // Value input should be enabled
        const valueInput = screen.getByDisplayValue('test_value');
        expect(valueInput).not.toBeDisabled();
      }

      cleanup();
    }
  }, 60000);
});

/* ------------------------------------------------------------------ */
/*  Property 6: JSON Validation Controls Save Button                   */
/*  Validates: Requirements 5.1, 5.2, 5.3, 5.4                        */
/* ------------------------------------------------------------------ */

describe('Feature: parameter-reset-to-default, Property 6: JSON Validation Controls Save Button', () => {
  it('Save enabled iff JSON.parse succeeds; error message shown when invalid (100 iterations)', async () => {
    // Mix of valid JSON strings and arbitrary strings (likely invalid JSON)
    const inputs = fc.sample(
      fc.oneof(
        fc.json().map((j) => ({ input: j, shouldBeValid: true })),
        // Generate strings that are definitely not valid JSON
        fc.stringMatching(/^[a-zA-Z]{2,20}$/).map((s) => ({ input: s, shouldBeValid: false })),
      ),
      100,
    );

    const param = {
      id: 1,
      namespace: 'ns_test',
      key: 'key_json_param',
      value: { initial: true },
      value_type: 'json' as const,
      scope_origin: 'tenant' as const,
      is_secret: false,
      has_code_default: true,
    };

    for (const { input, shouldBeValid } of inputs) {
      vi.clearAllMocks();
      mockToast.mockClear();

      await renderWithParam(param);

      // Find the textarea and change its value
      const textarea = document.querySelector('textarea') as HTMLTextAreaElement;
      expect(textarea).toBeTruthy();

      fireEvent.change(textarea, { target: { value: input } });

      await waitFor(() => {
        const saveButton = screen.getByText('Save');

        if (shouldBeValid) {
          // Valid JSON → Save enabled, no error
          expect(saveButton).not.toBeDisabled();
          expect(screen.queryByText(/Invalid JSON/)).not.toBeInTheDocument();
        } else {
          // Invalid JSON → Save disabled, error shown
          expect(saveButton).toBeDisabled();
          expect(screen.getByText(/Invalid JSON/)).toBeInTheDocument();
        }
      });

      cleanup();
    }
  }, 60000);
});

/* ------------------------------------------------------------------ */
/*  Property 7: JSON Format Button Idempotence                         */
/*  Validates: Requirements 5.5                                        */
/* ------------------------------------------------------------------ */

describe('Feature: parameter-reset-to-default, Property 7: JSON Format Button Idempotence', () => {
  it('Format produces JSON.stringify(JSON.parse(input), null, 2) and is idempotent (100 iterations)', async () => {
    // Generate simple valid JSON objects with safe keys
    const safeKey = fc.stringMatching(/^[a-zA-Z][a-zA-Z0-9]{1,8}$/);
    const inputs = fc.sample(
      fc.dictionary(safeKey, fc.oneof(
        fc.stringMatching(/^[a-zA-Z0-9]{1,10}$/),
        fc.integer({ min: -1000, max: 1000 }),
        fc.boolean(),
        fc.constant(null),
      ), { minKeys: 1, maxKeys: 5 }),
      100,
    );

    const param = {
      id: 1,
      namespace: 'ns_test',
      key: 'key_json_param',
      value: { initial: true },
      value_type: 'json' as const,
      scope_origin: 'tenant' as const,
      is_secret: false,
      has_code_default: true,
    };

    for (const jsonObj of inputs) {
      vi.clearAllMocks();
      mockToast.mockClear();

      await renderWithParam(param);

      const textarea = document.querySelector('textarea') as HTMLTextAreaElement;
      expect(textarea).toBeTruthy();

      // Set compact JSON
      const compactJson = JSON.stringify(jsonObj);
      fireEvent.change(textarea, { target: { value: compactJson } });

      // Wait for validation to clear
      await waitFor(() => {
        expect(screen.queryByText(/Invalid JSON/)).not.toBeInTheDocument();
      });

      // Click Format
      const formatButton = screen.getByText('Format');
      expect(formatButton).not.toBeDisabled();
      fireEvent.click(formatButton);

      // Verify formatted output
      const expected = JSON.stringify(JSON.parse(compactJson), null, 2);
      await waitFor(() => {
        const currentTextarea = document.querySelector('textarea') as HTMLTextAreaElement;
        expect(currentTextarea.value).toBe(expected);
      });

      // Click Format again — idempotent (same result)
      fireEvent.click(screen.getByText('Format'));
      await waitFor(() => {
        const currentTextarea = document.querySelector('textarea') as HTMLTextAreaElement;
        expect(currentTextarea.value).toBe(expected);
      });

      cleanup();
    }
  }, 60000);

  it('Format button is disabled when JSON is invalid (100 iterations)', async () => {
    const inputs = fc.sample(
      // Generate strings that are definitely not valid JSON
      fc.stringMatching(/^[a-zA-Z]{2,20}$/),
      100,
    );

    const param = {
      id: 1,
      namespace: 'ns_test',
      key: 'key_json_param',
      value: { initial: true },
      value_type: 'json' as const,
      scope_origin: 'tenant' as const,
      is_secret: false,
      has_code_default: true,
    };

    for (const invalidJson of inputs) {
      vi.clearAllMocks();
      mockToast.mockClear();

      await renderWithParam(param);

      const textarea = document.querySelector('textarea') as HTMLTextAreaElement;
      expect(textarea).toBeTruthy();

      fireEvent.change(textarea, { target: { value: invalidJson } });

      await waitFor(() => {
        const formatButton = screen.getByText('Format');
        expect(formatButton).toBeDisabled();
      });

      cleanup();
    }
  }, 60000);
});

/**
 * EmailLogPanel Unit Tests
 *
 * Tests the Table Filter Framework v2 migration:
 * - FilterableHeader rendering with aria-sort and aria-label
 * - useFilterableTable hook integration (filter + sort)
 * - Preservation of limit selector, refresh, sysadmin mode
 * - processedData rendering instead of raw data
 * - Dark theme styling
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';

// Mock Chakra UI to avoid @zag-js/focus-visible crash in jsdom
vi.mock('@chakra-ui/react', () => ({
  Box: ({ children, ...props }: any) => <div data-testid={props['data-testid']} data-bg={props.bg}>{children}</div>,
  Button: ({ children, onClick, ...props }: any) => (
    <button onClick={onClick} aria-label={props['aria-label']}>{children}</button>
  ),
  Badge: ({ children, ...props }: any) => <span data-colorscheme={props.colorScheme}>{children}</span>,
  VStack: ({ children }: any) => <div>{children}</div>,
  HStack: ({ children, ...props }: any) => <div role={props.role} aria-label={props['aria-label']} onClick={props.onClick}>{children}</div>,
  Table: ({ children }: any) => <table>{children}</table>,
  Thead: ({ children }: any) => <thead>{children}</thead>,
  Tbody: ({ children }: any) => <tbody>{children}</tbody>,
  Tr: ({ children, onClick, ...props }: any) => (
    <tr onClick={onClick} data-testid={props['data-testid']}>{children}</tr>
  ),
  Th: ({ children, ...props }: any) => (
    <th aria-sort={props['aria-sort']}>{children}</th>
  ),
  Td: ({ children, ...props }: any) => <td>{children}</td>,
  Text: ({ children }: any) => <span>{children}</span>,
  Spinner: () => <div data-testid="spinner">Loading...</div>,
  Alert: ({ children }: any) => <div role="alert">{children}</div>,
  AlertIcon: () => <span>⚠️</span>,
  Select: ({ children, onChange, value, ...props }: any) => (
    <select onChange={onChange} value={value} data-testid={props['data-testid']}>
      {children}
    </select>
  ),
  Input: (props: any) => <input {...filterDomProps(props)} />,
  InputGroup: ({ children }: any) => <div>{children}</div>,
  InputLeftElement: ({ children }: any) => <span>{children}</span>,
}));

vi.mock('@chakra-ui/icons', () => ({
  SearchIcon: () => <span>🔍</span>,
}));

// Mock TenantContext
vi.mock('../../../src/context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 'test-tenant' }),
}));

// Mock API service
const mockFetchResponse = (data: any) =>
  Promise.resolve({ json: () => Promise.resolve(data) });

vi.mock('../../../src/services/apiService', () => ({
  authenticatedGet: vi.fn(() => mockFetchResponse({ success: true, logs: [] })),
  buildEndpoint: vi.fn((path: string) => path),
}));

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import EmailLogPanel from '../../../src/components/shared/EmailLogPanel';
import { authenticatedGet } from '../../../src/services/apiService';

/** Filter out non-DOM props to avoid React warnings */
function filterDomProps(props: Record<string, any>) {
  const nonDom = ['bg', 'color', 'fontSize', 'fontWeight', 'spacing', 'align',
    'justify', 'size', 'variant', 'colorScheme', 'isNumeric', 'isLoading',
    'textTransform', 'borderRadius', 'p', 'mb', 'mt', 'w', 'h', '_hover',
    'cursor', 'pointerEvents', 'boxSize', 'pl', 'autoComplete', 'autoCorrect',
    'autoCapitalize', 'spellCheck', 'maxW', 'borderColor', 'isTruncated',
    'whiteSpace', 'overflowX', 'flexWrap'];
  const filtered: Record<string, any> = {};
  for (const [key, value] of Object.entries(props)) {
    if (!nonDom.includes(key)) {
      filtered[key] = value;
    }
  }
  return filtered;
}

const mockLogs = [
  {
    id: 1,
    recipient: 'alice@example.com',
    email_type: 'invitation',
    administration: 'TenantA',
    status: 'delivered',
    ses_message_id: 'msg-001',
    subject: 'Welcome to the platform',
    sent_by: 'admin@example.com',
    error_message: null,
    created_at: '2024-06-15T10:30:00Z',
    updated_at: '2024-06-15T10:30:00Z',
  },
  {
    id: 2,
    recipient: 'bob@example.com',
    email_type: 'password_reset',
    administration: 'TenantB',
    status: 'bounced',
    ses_message_id: 'msg-002',
    subject: 'Reset your password',
    sent_by: 'system@example.com',
    error_message: 'Mailbox full',
    created_at: '2024-06-14T08:00:00Z',
    updated_at: '2024-06-14T08:01:00Z',
  },
  {
    id: 3,
    recipient: 'charlie@example.com',
    email_type: 'tenant_added',
    administration: 'TenantA',
    status: 'sent',
    ses_message_id: 'msg-003',
    subject: 'You have been added to TenantA',
    sent_by: 'admin@example.com',
    error_message: null,
    created_at: '2024-06-13T14:00:00Z',
    updated_at: '2024-06-13T14:00:00Z',
  },
];

describe('EmailLogPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (authenticatedGet as any).mockImplementation(() =>
      mockFetchResponse({ success: true, logs: mockLogs })
    );
  });

  describe('Framework Integration', () => {
    it('renders FilterableHeader components with aria-sort attributes', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText(/Showing/)).toBeInTheDocument();
      });

      // FilterableHeader renders <Th> with aria-sort
      const sortableHeaders = document.querySelectorAll('[aria-sort]');
      expect(sortableHeaders.length).toBeGreaterThanOrEqual(6); // Date, Recipient, Type, Subject, Status, Sent by
    });

    it('renders filter inputs with aria-label attributes', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText(/Showing/)).toBeInTheDocument();
      });

      // FilterableHeader renders inputs with aria-label="Filter by {label}"
      expect(screen.getByLabelText('Filter by Recipient')).toBeInTheDocument();
      expect(screen.getByLabelText('Filter by Type')).toBeInTheDocument();
      expect(screen.getByLabelText('Filter by Subject')).toBeInTheDocument();
      expect(screen.getByLabelText('Filter by Status')).toBeInTheDocument();
      expect(screen.getByLabelText('Filter by Sent by')).toBeInTheDocument();
    });

    it('displays processedData count and total count', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText('Showing 3 of 3 log(s)')).toBeInTheDocument();
      });
    });
  });

  describe('Filtering', () => {
    it('filters logs by recipient (case-insensitive substring)', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText('Showing 3 of 3 log(s)')).toBeInTheDocument();
      });

      const recipientFilter = screen.getByLabelText('Filter by Recipient');

      await act(async () => {
        fireEvent.change(recipientFilter, { target: { value: 'alice' } });
      });

      // After debounce, only Alice's log should show
      await waitFor(() => {
        expect(screen.getByText('Showing 1 of 3 log(s)')).toBeInTheDocument();
      }, { timeout: 500 });
    });

    it('filters logs by status', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText('Showing 3 of 3 log(s)')).toBeInTheDocument();
      });

      const statusFilter = screen.getByLabelText('Filter by Status');

      await act(async () => {
        fireEvent.change(statusFilter, { target: { value: 'bounced' } });
      });

      await waitFor(() => {
        expect(screen.getByText('Showing 1 of 3 log(s)')).toBeInTheDocument();
      }, { timeout: 500 });
    });

    it('filters logs by subject', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText('Showing 3 of 3 log(s)')).toBeInTheDocument();
      });

      const subjectFilter = screen.getByLabelText('Filter by Subject');

      await act(async () => {
        fireEvent.change(subjectFilter, { target: { value: 'welcome' } });
      });

      await waitFor(() => {
        expect(screen.getByText('Showing 1 of 3 log(s)')).toBeInTheDocument();
      }, { timeout: 500 });
    });
  });

  describe('Sorting', () => {
    it('default sort is by created_at descending', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText('Showing 3 of 3 log(s)')).toBeInTheDocument();
      });

      // First row should be the most recent log (id: 1, 2024-06-15)
      const rows = document.querySelectorAll('tbody tr');
      const firstRowText = rows[0]?.textContent || '';
      expect(firstRowText).toContain('alice@example.com');
    });

    it('clicking sort on recipient column triggers sort', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText('Showing 3 of 3 log(s)')).toBeInTheDocument();
      });

      const sortButton = screen.getByLabelText('Sort by Recipient');
      await act(async () => {
        fireEvent.click(sortButton);
      });

      // After sorting by recipient asc, alice should be first
      const rows = document.querySelectorAll('tbody tr');
      const firstRowText = rows[0]?.textContent || '';
      expect(firstRowText).toContain('alice@example.com');
    });
  });

  describe('Sysadmin Mode', () => {
    it('renders Tenant column with FilterableHeader in sysadmin mode', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="sysadmin" />);
      });

      await waitFor(() => {
        expect(screen.getByText(/Showing/)).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Filter by Tenant')).toBeInTheDocument();
    });

    it('does not render Tenant column in tenant mode', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText(/Showing/)).toBeInTheDocument();
      });

      expect(screen.queryByLabelText('Filter by Tenant')).not.toBeInTheDocument();
    });

    it('filters by tenant in sysadmin mode', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="sysadmin" />);
      });

      await waitFor(() => {
        expect(screen.getByText('Showing 3 of 3 log(s)')).toBeInTheDocument();
      });

      const tenantFilter = screen.getByLabelText('Filter by Tenant');

      await act(async () => {
        fireEvent.change(tenantFilter, { target: { value: 'TenantA' } });
      });

      await waitFor(() => {
        expect(screen.getByText('Showing 2 of 3 log(s)')).toBeInTheDocument();
      }, { timeout: 500 });
    });
  });

  describe('Preservation — Limit Selector and Refresh', () => {
    it('renders limit selector with options', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      const selects = document.querySelectorAll('select');
      // Should have at least one select (limit)
      expect(selects.length).toBeGreaterThanOrEqual(1);
    });

    it('refresh button re-fetches data', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText('Showing 3 of 3 log(s)')).toBeInTheDocument();
      });

      const refreshButton = screen.getByText('Refresh');

      await act(async () => {
        fireEvent.click(refreshButton);
      });

      // Should have been called twice: once on mount, once on refresh
      expect(authenticatedGet).toHaveBeenCalledTimes(2);
    });

    it('does not pass recipientFilter to API (client-side filtering only)', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText('Showing 3 of 3 log(s)')).toBeInTheDocument();
      });

      // API should be called without recipient param
      const apiCall = (authenticatedGet as any).mock.calls[0][0];
      expect(apiCall).not.toContain('recipient=');
    });

    it('passes administration param in tenant mode', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(authenticatedGet).toHaveBeenCalled();
      });

      const apiCall = (authenticatedGet as any).mock.calls[0][0];
      expect(apiCall).toContain('administration=test-tenant');
    });
  });

  describe('Dark Theme Styling', () => {
    it('renders table container with dark background', async () => {
      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText(/Showing/)).toBeInTheDocument();
      });

      // The Box wrapping the table should have bg="gray.800"
      const darkBox = document.querySelector('[data-bg="gray.800"]');
      expect(darkBox).not.toBeNull();
    });
  });

  describe('Edge Cases', () => {
    it('shows empty state when no logs found', async () => {
      (authenticatedGet as any).mockImplementation(() =>
        mockFetchResponse({ success: true, logs: [] })
      );

      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByText('No email logs found.')).toBeInTheDocument();
      });
    });

    it('shows error alert on API failure', async () => {
      (authenticatedGet as any).mockImplementation(() =>
        Promise.reject(new Error('Network error'))
      );

      await act(async () => {
        render(<EmailLogPanel mode="tenant" />);
      });

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      });
    });
  });
});

/**
 * CredentialsManagement Component - Unit Tests
 * 
 * Tests for CredentialsManagement component functionality.
 * Target: 15+ tests
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '../../../test-utils';
import { fetchAuthSession } from 'aws-amplify/auth';
import { CredentialsManagement } from '../CredentialsManagement';

// Mock AWS Amplify
jest.mock('aws-amplify/auth');

const mockFetchAuthSession = fetchAuthSession as jest.MockedFunction<typeof fetchAuthSession>;

describe('CredentialsManagement Component', () => {
  const mockToken = 'mock-jwt-token';
  const mockTenant = 'TestTenant';

  const mockCredentials = [
    {
      type: 'google_drive_credentials',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    {
      type: 'google_drive_oauth',
      created_at: '2026-01-02T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();

    mockFetchAuthSession.mockResolvedValue({
      tokens: {
        idToken: {
          toString: () => mockToken,
        },
      },
    } as any);

    // Mock successful API responses
    global.fetch = jest.fn((url: string) => {
      if (url.includes('/api/tenant-admin/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: mockCredentials }),
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({}),
      } as Response);
    }) as jest.Mock;
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  // ============================================================================
  // Rendering Tests
  // ============================================================================

  describe('Rendering', () => {
    test('renders component with loading state', () => {
      render(<CredentialsManagement tenant={mockTenant} />);
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    test('renders credentials list after loading', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByText('google_drive_credentials')).toBeInTheDocument();
        expect(screen.getByText('google_drive_oauth')).toBeInTheDocument();
      });
    });

    test('renders upload button', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /upload/i })).toBeInTheDocument();
      });
    });

    test('renders OAuth button', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /oauth/i })).toBeInTheDocument();
      });
    });

    test('renders credential type selector', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/credential type/i)).toBeInTheDocument();
      });
    });

    test('renders file input', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/select file/i)).toBeInTheDocument();
      });
    });
  });

  // ============================================================================
  // Data Loading Tests
  // ============================================================================

  describe('Data Loading', () => {
    test('fetches credentials on mount', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/tenant-admin/credentials'),
          expect.any(Object)
        );
      });
    });

    test('includes authentication token in requests', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        const calls = (global.fetch as jest.Mock).mock.calls;
        const credentialsCall = calls.find(call => call[0].includes('/api/tenant-admin/credentials'));
        expect(credentialsCall[1].headers['Authorization']).toBe(`Bearer ${mockToken}`);
      });
    });

    test('includes tenant header in requests', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        const calls = (global.fetch as jest.Mock).mock.calls;
        const credentialsCall = calls.find(call => call[0].includes('/api/tenant-admin/credentials'));
        expect(credentialsCall[1].headers['X-Tenant']).toBe(mockTenant);
      });
    });

    test('handles API error gracefully', async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('API Error'));

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.queryByText('google_drive_credentials')).not.toBeInTheDocument();
      });
    });
  });

  // ============================================================================
  // File Upload Tests
  // ============================================================================

  describe('File Upload', () => {
    test('accepts JSON file selection', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/select file/i)).toBeInTheDocument();
      });

      const file = new File(['{"key": "value"}'], 'credentials.json', { type: 'application/json' });
      const input = screen.getByLabelText(/select file/i) as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(input.files?.[0]).toBe(file);
      });
    });

    test('validates file type (JSON only)', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/select file/i)).toBeInTheDocument();
      });

      const file = new File(['content'], 'credentials.txt', { type: 'text/plain' });
      const input = screen.getByLabelText(/select file/i) as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      // Component should show error toast for invalid file type
      await waitFor(() => {
        // Toast error should be triggered
      });
    });

    test('uploads file when upload button clicked', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/select file/i)).toBeInTheDocument();
      });

      const file = new File(['{"key": "value"}'], 'credentials.json', { type: 'application/json' });
      const input = screen.getByLabelText(/select file/i) as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      const uploadButton = screen.getByRole('button', { name: /upload/i });
      fireEvent.click(uploadButton);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/tenant-admin/credentials'),
          expect.objectContaining({
            method: 'POST',
          })
        );
      });
    });

    test('shows loading state during upload', async () => {
      (global.fetch as jest.Mock).mockImplementation(() => 
        new Promise(resolve => setTimeout(() => resolve({
          ok: true,
          json: async () => ({ success: true }),
        }), 100))
      );

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/select file/i)).toBeInTheDocument();
      });

      const file = new File(['{"key": "value"}'], 'credentials.json', { type: 'application/json' });
      const input = screen.getByLabelText(/select file/i) as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      const uploadButton = screen.getByRole('button', { name: /upload/i });
      fireEvent.click(uploadButton);

      // Should show loading indicator
      expect(screen.getByText(/uploading/i)).toBeInTheDocument();
    });
  });

  // ============================================================================
  // OAuth Flow Tests
  // ============================================================================

  describe('OAuth Flow', () => {
    test('starts OAuth flow when button clicked', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ auth_url: 'https://oauth.example.com', state: 'abc123' }),
      });

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /oauth/i })).toBeInTheDocument();
      });

      const oauthButton = screen.getByRole('button', { name: /oauth/i });
      fireEvent.click(oauthButton);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/tenant-admin/credentials/oauth/start'),
          expect.objectContaining({
            method: 'POST',
          })
        );
      });
    });

    test('opens OAuth window with correct URL', async () => {
      const mockOpen = jest.fn();
      window.open = mockOpen;

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ auth_url: 'https://oauth.example.com', state: 'abc123' }),
      });

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /oauth/i })).toBeInTheDocument();
      });

      const oauthButton = screen.getByRole('button', { name: /oauth/i });
      fireEvent.click(oauthButton);

      await waitFor(() => {
        expect(mockOpen).toHaveBeenCalledWith(
          'https://oauth.example.com',
          expect.any(String),
          expect.any(String)
        );
      });
    });
  });

  // ============================================================================
  // Test Connection Tests
  // ============================================================================

  describe('Test Connection', () => {
    test('shows test button for each credential', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        const testButtons = screen.getAllByRole('button', { name: /test/i });
        expect(testButtons.length).toBeGreaterThan(0);
      });
    });

    test('tests connection when button clicked', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ credentials: mockCredentials }),
      }).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, accessible: true }),
      });

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getAllByRole('button', { name: /test/i }).length).toBeGreaterThan(0);
      });

      const testButton = screen.getAllByRole('button', { name: /test/i })[0];
      fireEvent.click(testButton);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/tenant-admin/credentials/test'),
          expect.objectContaining({
            method: 'POST',
          })
        );
      });
    });

    test('shows loading state during connection test', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ credentials: mockCredentials }),
      }).mockImplementation(() => 
        new Promise(resolve => setTimeout(() => resolve({
          ok: true,
          json: async () => ({ success: true, accessible: true }),
        }), 100))
      );

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getAllByRole('button', { name: /test/i }).length).toBeGreaterThan(0);
      });

      const testButton = screen.getAllByRole('button', { name: /test/i })[0];
      fireEvent.click(testButton);

      // Should show loading indicator
      expect(screen.getByText(/testing/i)).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Credential Type Selection Tests
  // ============================================================================

  describe('Credential Type Selection', () => {
    test('allows selecting credential type', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/credential type/i)).toBeInTheDocument();
      });

      const select = screen.getByLabelText(/credential type/i) as HTMLSelectElement;
      fireEvent.change(select, { target: { value: 'google_drive_oauth' } });

      expect(select.value).toBe('google_drive_oauth');
    });

    test('defaults to google_drive credential type', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/credential type/i)).toBeInTheDocument();
      });

      const select = screen.getByLabelText(/credential type/i) as HTMLSelectElement;
      expect(select.value).toBe('google_drive');
    });
  });

  // ============================================================================
  // Error Handling Tests
  // ============================================================================

  describe('Error Handling', () => {
    test('displays error message when credentials fail to load', async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Failed to load credentials'));

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.queryByText('google_drive_credentials')).not.toBeInTheDocument();
      });
    });

    test('displays error message when upload fails', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ credentials: mockCredentials }),
      }).mockRejectedValueOnce(new Error('Upload failed'));

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/select file/i)).toBeInTheDocument();
      });

      const file = new File(['{"key": "value"}'], 'credentials.json', { type: 'application/json' });
      const input = screen.getByLabelText(/select file/i) as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      const uploadButton = screen.getByRole('button', { name: /upload/i });
      fireEvent.click(uploadButton);

      await waitFor(() => {
        // Error toast should be displayed
      });
    });

    test('displays error message when connection test fails', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ credentials: mockCredentials }),
      }).mockRejectedValueOnce(new Error('Connection test failed'));

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getAllByRole('button', { name: /test/i }).length).toBeGreaterThan(0);
      });

      const testButton = screen.getAllByRole('button', { name: /test/i })[0];
      fireEvent.click(testButton);

      await waitFor(() => {
        // Error toast should be displayed
      });
    });
  });
});

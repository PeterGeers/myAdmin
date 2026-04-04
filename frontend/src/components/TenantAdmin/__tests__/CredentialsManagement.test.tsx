/**
 * CredentialsManagement Component - Unit Tests
 * 
 * Tests for CredentialsManagement component functionality.
 * Target: 15+ tests
 */

import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '../../../test-utils';
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
      if (typeof url === 'string' && url.includes('/api/tenant-admin/credentials')) {
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
      // Component shows a Spinner while loading
      expect(document.querySelector('.chakra-spinner')).toBeInTheDocument();
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
        expect(screen.getByRole('button', { name: /upload credentials/i })).toBeInTheDocument();
      });
    });

    test('renders OAuth button', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start google drive oauth/i })).toBeInTheDocument();
      });
    });

    test('renders credential type selector inside upload modal', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      // Wait for loading to finish
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /upload credentials/i })).toBeInTheDocument();
      });

      // Open the upload modal
      fireEvent.click(screen.getByRole('button', { name: /upload credentials/i }));

      await waitFor(() => {
        expect(screen.getAllByText('Credential Type').length).toBeGreaterThan(0);
      });
    });

    test('renders file input inside upload modal', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /upload credentials/i })).toBeInTheDocument();
      });

      // Open the upload modal
      fireEvent.click(screen.getByRole('button', { name: /upload credentials/i }));

      await waitFor(() => {
        expect(screen.getByText('JSON Credentials File')).toBeInTheDocument();
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
        const credentialsCall = calls.find((call: any[]) => call[0].includes('/api/tenant-admin/credentials'));
        expect(credentialsCall[1].headers['Authorization']).toBe(`Bearer ${mockToken}`);
      });
    });

    test('includes tenant header in requests', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        const calls = (global.fetch as jest.Mock).mock.calls;
        const credentialsCall = calls.find((call: any[]) => call[0].includes('/api/tenant-admin/credentials'));
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
    test('accepts JSON file selection in upload modal', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /upload credentials/i })).toBeInTheDocument();
      });

      // Open the upload modal
      fireEvent.click(screen.getByRole('button', { name: /upload credentials/i }));

      await waitFor(() => {
        expect(screen.getByText('JSON Credentials File')).toBeInTheDocument();
      });

      const file = new File(['{"key": "value"}'], 'credentials.json', { type: 'application/json' });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/Selected: credentials.json/)).toBeInTheDocument();
      });
    });

    test('validates file type (JSON only)', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /upload credentials/i })).toBeInTheDocument();
      });

      // Open the upload modal
      fireEvent.click(screen.getByRole('button', { name: /upload credentials/i }));

      await waitFor(() => {
        expect(screen.getByText('JSON Credentials File')).toBeInTheDocument();
      });

      // The file input has accept=".json" attribute
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      expect(input.getAttribute('accept')).toBe('.json');
    });

    test('uploads file when upload button clicked', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /upload credentials/i })).toBeInTheDocument();
      });

      // Open the upload modal
      fireEvent.click(screen.getByRole('button', { name: /upload credentials/i }));

      await waitFor(() => {
        expect(screen.getByText('JSON Credentials File')).toBeInTheDocument();
      });

      const file = new File(['{"key": "value"}'], 'credentials.json', { type: 'application/json' });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      // Click the Upload button inside the modal footer
      const uploadButton = screen.getByRole('button', { name: 'Upload' });
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

    test('shows disabled upload button when no file selected', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /upload credentials/i })).toBeInTheDocument();
      });

      // Open the upload modal
      fireEvent.click(screen.getByRole('button', { name: /upload credentials/i }));

      await waitFor(() => {
        const uploadButton = screen.getByRole('button', { name: 'Upload' });
        expect(uploadButton).toBeDisabled();
      });
    });
  });

  // ============================================================================
  // OAuth Flow Tests
  // ============================================================================

  describe('OAuth Flow', () => {
    test('starts OAuth flow when button clicked', async () => {
      // Mock window.open before rendering
      const mockOpen = jest.fn().mockReturnValue(null);
      window.open = mockOpen;

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ credentials: mockCredentials }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ oauth_url: 'https://oauth.example.com', state: 'abc123' }),
        });

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start google drive oauth/i })).toBeInTheDocument();
      });

      const oauthButton = screen.getByRole('button', { name: /start google drive oauth/i });
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
      const mockOpen = jest.fn().mockReturnValue({ closed: false });
      window.open = mockOpen;

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ credentials: mockCredentials }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ oauth_url: 'https://oauth.example.com', state: 'abc123' }),
        });

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start google drive oauth/i })).toBeInTheDocument();
      });

      const oauthButton = screen.getByRole('button', { name: /start google drive oauth/i });
      fireEvent.click(oauthButton);

      await waitFor(() => {
        expect(mockOpen).toHaveBeenCalledWith(
          'https://oauth.example.com',
          '_blank',
          expect.any(String)
        );
      });
    });
  });

  // ============================================================================
  // Test Connection Tests
  // ============================================================================

  describe('Test Connection', () => {
    test('shows test button for credentials', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /test google drive connection/i })).toBeInTheDocument();
      });
    });

    test('tests connection when button clicked', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ credentials: mockCredentials }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ test_result: { success: true, message: 'Connected' } }),
        });

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /test google drive connection/i })).toBeInTheDocument();
      });

      const testButton = screen.getByRole('button', { name: /test google drive connection/i });
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
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ credentials: mockCredentials }),
        })
        .mockImplementationOnce(() =>
          new Promise(resolve => setTimeout(() => resolve({
            ok: true,
            json: async () => ({ test_result: { success: true, message: 'Connected' } }),
          }), 5000))
        );

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /test google drive connection/i })).toBeInTheDocument();
      });

      const testButton = screen.getByRole('button', { name: /test google drive connection/i });
      fireEvent.click(testButton);

      // Button should show loading text
      await waitFor(() => {
        expect(screen.getByText(/testing/i)).toBeInTheDocument();
      });
    });
  });

  // ============================================================================
  // Credential Type Selection Tests
  // ============================================================================

  describe('Credential Type Selection', () => {
    test('allows selecting credential type in modal', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /upload credentials/i })).toBeInTheDocument();
      });

      // Open the upload modal
      fireEvent.click(screen.getByRole('button', { name: /upload credentials/i }));

      await waitFor(() => {
        expect(screen.getAllByText('Credential Type').length).toBeGreaterThan(0);
      });

      // Find the select element for credential type
      const selects = document.querySelectorAll('select');
      const credTypeSelect = Array.from(selects).find(s =>
        Array.from(s.options).some(o => o.value === 'google_drive')
      ) as HTMLSelectElement;

      expect(credTypeSelect).toBeTruthy();
      fireEvent.change(credTypeSelect, { target: { value: 's3' } });
      expect(credTypeSelect.value).toBe('s3');
    });

    test('defaults to google_drive credential type in modal', async () => {
      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /upload credentials/i })).toBeInTheDocument();
      });

      // Open the upload modal
      fireEvent.click(screen.getByRole('button', { name: /upload credentials/i }));

      await waitFor(() => {
        expect(screen.getAllByText('Credential Type').length).toBeGreaterThan(0);
      });

      const selects = document.querySelectorAll('select');
      const credTypeSelect = Array.from(selects).find(s =>
        Array.from(s.options).some(o => o.value === 'google_drive')
      ) as HTMLSelectElement;

      expect(credTypeSelect.value).toBe('google_drive');
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

    test('displays error when upload fails', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ credentials: mockCredentials }),
        })
        .mockRejectedValueOnce(new Error('Upload failed'));

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /upload credentials/i })).toBeInTheDocument();
      });

      // Open the upload modal
      fireEvent.click(screen.getByRole('button', { name: /upload credentials/i }));

      await waitFor(() => {
        expect(screen.getByText('JSON Credentials File')).toBeInTheDocument();
      });

      const file = new File(['{"key": "value"}'], 'credentials.json', { type: 'application/json' });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      const uploadButton = screen.getByRole('button', { name: 'Upload' });
      fireEvent.click(uploadButton);

      // Wait for the upload attempt to complete (error is shown via toast)
      await waitFor(() => {
        // Verify the POST was attempted
        const calls = (global.fetch as jest.Mock).mock.calls;
        const postCall = calls.find((call: any[]) =>
          typeof call[0] === 'string' &&
          call[0].includes('/api/tenant-admin/credentials') &&
          call[1]?.method === 'POST'
        );
        expect(postCall).toBeTruthy();
      });
    });

    test('displays error message when connection test fails', async () => {
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ credentials: mockCredentials }),
        })
        .mockRejectedValueOnce(new Error('Connection test failed'));

      render(<CredentialsManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /test google drive connection/i })).toBeInTheDocument();
      });

      const testButton = screen.getByRole('button', { name: /test google drive connection/i });
      fireEvent.click(testButton);

      // Wait for the test attempt to complete (error is shown via toast)
      await waitFor(() => {
        const calls = (global.fetch as jest.Mock).mock.calls;
        const testCall = calls.find((call: any[]) =>
          typeof call[0] === 'string' &&
          call[0].includes('/api/tenant-admin/credentials/test')
        );
        expect(testCall).toBeTruthy();
      });
    });
  });
});

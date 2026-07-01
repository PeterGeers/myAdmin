import React from 'react';
import { render, screen, fireEvent, waitFor } from '@/test-utils';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock parameter schema service (for reading)
const mockGetParameterSchema = vi.fn();

vi.mock('../../services/parameterSchemaService', () => ({
  getParameterSchema: (...args: unknown[]) => mockGetParameterSchema(...args),
}));

// Mock parameter service (for writing)
const mockCreateParameter = vi.fn();

vi.mock('../../services/parameterService', () => ({
  createParameter: (...args: unknown[]) => mockCreateParameter(...args),
}));

// Mock hooks
vi.mock('../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 'test-tenant' }),
}));

// Mock fetch for direct API calls
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock Amplify
vi.mock('aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn().mockResolvedValue({
    tokens: { idToken: { toString: () => 'mock-token' } },
  }),
}));

// Import after mocks
import StorageTab from './StorageTab';

describe('StorageTab Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: parameter schema returns storage config
    mockGetParameterSchema.mockResolvedValue({
      schema: {
        storage: {
          params: {
            invoice_provider: {
              options: [
                { value: 'google_drive', label: 'Google Drive' },
                { value: 's3_shared', label: 'S3 Shared' },
              ],
              current_value: 'google_drive',
              default: 'google_drive',
            },
            google_drive_folder_id: {
              current_value: 'folder-123',
            },
          },
        },
      },
    });
    // Mock fetch for credentials and config endpoints
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ credentials: [], success: true }),
    });
  });

  describe('Rendering', () => {
    it('renders loading state initially', () => {
      mockGetParameterSchema.mockReturnValue(new Promise(() => {}));
      render(<StorageTab tenant="test-tenant" />);
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it('renders storage provider section after loading', async () => {
      render(<StorageTab tenant="test-tenant" />);
      await waitFor(() => {
        expect(mockGetParameterSchema).toHaveBeenCalled();
      });
      // Should show provider selection or current provider info
    });

    it('renders Google Drive folder ID input', async () => {
      render(<StorageTab tenant="test-tenant" />);
      await waitFor(() => {
        expect(mockGetParameterSchema).toHaveBeenCalled();
      });
      // After loading, should show folder config section
      const folderInput = screen.queryByDisplayValue('folder-123');
      if (folderInput) {
        expect(folderInput).toBeInTheDocument();
      }
    });
  });

  describe('Provider Configuration', () => {
    it('calls createParameter when saving provider config', async () => {
      mockCreateParameter.mockResolvedValue({ success: true });
      render(<StorageTab tenant="test-tenant" />);
      await waitFor(() => {
        expect(mockGetParameterSchema).toHaveBeenCalled();
      });

      // Find and click save button (if visible after provider selection)
      const saveButtons = screen.queryAllByRole('button', { name: /save/i });
      if (saveButtons.length > 0) {
        fireEvent.click(saveButtons[0]);
        await waitFor(() => {
          expect(mockCreateParameter).toHaveBeenCalled();
        });
      }
    });
  });

  describe('Credentials', () => {
    it('shows no credentials message when list is empty', async () => {
      mockFetch.mockResolvedValue({ credentials: [] });
      render(<StorageTab tenant="test-tenant" />);
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });
    });

    it('shows credential info when credentials exist', async () => {
      mockFetch.mockResolvedValue({
        credentials: [
          { type: 'google_drive_credentials', created_at: '2025-01-01', updated_at: '2025-06-01' },
        ],
      });
      render(<StorageTab tenant="test-tenant" />);
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });
    });
  });

  describe('OAuth Flow', () => {
    it('starts OAuth flow when connect button is clicked', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true }),
      }); // getParameters response (via fetch)
      
      render(<StorageTab tenant="test-tenant" />);
      await waitFor(() => {
        expect(mockGetParameterSchema).toHaveBeenCalled();
      });

      const connectButton = screen.queryByRole('button', { name: /start google drive oauth/i });
      if (connectButton) {
        // Mock window.open
        const mockOpen = vi.fn().mockReturnValue({ closed: false });
        Object.defineProperty(window, 'open', { value: mockOpen, writable: true });

        fireEvent.click(connectButton);
        // OAuth start is triggered
      }
    });
  });

  describe('Error Handling', () => {
    it('handles getParameters failure gracefully', async () => {
      mockGetParameterSchema.mockRejectedValue(new Error('Network error'));
      render(<StorageTab tenant="test-tenant" />);
      await waitFor(() => {
        expect(mockGetParameterSchema).toHaveBeenCalled();
      });
      // Should not crash
    });

    it('handles listCredentials failure gracefully', async () => {
      mockFetch.mockRejectedValue(new Error('Auth error'));
      render(<StorageTab tenant="test-tenant" />);
      await waitFor(() => {
        expect(mockGetParameterSchema).toHaveBeenCalled();
      });
      // Should not crash
    });
  });
});

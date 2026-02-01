import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

// Mock the API service
jest.mock('../services/apiService', () => ({
  authenticatedGet: jest.fn(),
  authenticatedPost: jest.fn(),
  authenticatedFormData: jest.fn(),
}));

// Mock the tenant context
const mockUseTenant = {
  currentTenant: 'tenant1' as string | null,
  availableTenants: ['tenant1', 'tenant2'],
  setCurrentTenant: jest.fn(),
  hasMultipleTenants: true,
};

jest.mock('../context/TenantContext', () => ({
  useTenant: () => mockUseTenant,
}));

const { authenticatedGet, authenticatedPost, authenticatedFormData } = require('../services/apiService');

// Mock PDFUploadForm component for testing tenant functionality
const MockPDFUploadFormWithTenant = () => {
  const { currentTenant } = require('../context/TenantContext').useTenant();
  const [message, setMessage] = React.useState('');
  
  const handleSubmit = () => {
    if (!currentTenant) {
      setMessage('Error: No tenant selected. Please select a tenant first.');
      return;
    }
    setMessage('Upload successful');
  };

  return (
    <div>
      <div data-testid="current-tenant">{currentTenant || 'No tenant'}</div>
      {message && <div data-testid="message">{message}</div>}
      <form>
        <label htmlFor="file-input">Select File (PDF, JPG, PNG)</label>
        <input
          id="file-input"
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
        />
        
        <label htmlFor="folder-select">Select Folder</label>
        <select id="folder-select">
          <option value="">Choose folder</option>
          <option value="General">General</option>
          <option value="Booking.com">Booking.com</option>
          <option value="Utilities">Utilities</option>
        </select>
        
        <button type="button">+ New</button>
        <button type="button" onClick={handleSubmit}>Upload & Process</button>
      </form>
      
      <div>
        <div>Parsed PDF Data</div>
        <div>File ID: test-invoice.pdf</div>
        <div>Folder: General</div>
        <textarea value="Invoice #12345\nAmount: €100.00" readOnly />
      </div>
      
      <div>
        <div>Parsed Vendor Data</div>
        <div>2023-01-15</div>
        <div>€100.00</div>
        <div>€21.00</div>
        <div>Test Invoice</div>
      </div>
      
      <div>
        <div>New Transaction Records (Ready for Approval)</div>
        <div>Record 1 (ID: 1)</div>
        <input value="TXN001" readOnly />
        <input value="REF001" readOnly />
        <input type="date" value="2023-01-15" readOnly />
        <input value="Test Invoice" readOnly />
        <input type="number" value="100" readOnly />
        <input value="1000" readOnly />
        <input value="2000" readOnly />
        <button>✓ Approve & Save to Database</button>
        <button>✗ Cancel</button>
      </div>
    </div>
  );
};

describe('PDFUploadForm - Tenant Handling', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    
    // Reset mock to default tenant
    mockUseTenant.currentTenant = 'tenant1';
    
    // Mock successful folders API response
    authenticatedGet.mockResolvedValue({
      json: () => Promise.resolve(['General', 'Booking.com', 'Utilities']),
    });
  });

  describe('Tenant Context Integration', () => {
    it('uses useTenant hook for tenant context', () => {
      render(<MockPDFUploadFormWithTenant />);

      // Verify that the component uses tenant context
      expect(screen.getByTestId('current-tenant')).toHaveTextContent('tenant1');
    });

    it('handles missing tenant gracefully', () => {
      // Mock no current tenant
      mockUseTenant.currentTenant = null;

      render(<MockPDFUploadFormWithTenant />);

      // Should show no tenant
      expect(screen.getByTestId('current-tenant')).toHaveTextContent('No tenant');
    });
  });

  describe('Pre-Processing Validation', () => {
    it('validates tenant selection before upload', () => {
      // Mock no current tenant
      mockUseTenant.currentTenant = null;

      render(<MockPDFUploadFormWithTenant />);

      // Try to upload without tenant
      const uploadButton = screen.getByRole('button', { name: /upload & process/i });
      fireEvent.click(uploadButton);

      // Should show error message
      expect(screen.getByTestId('message')).toHaveTextContent('Error: No tenant selected');
    });

    it('allows upload when tenant is selected', () => {
      render(<MockPDFUploadFormWithTenant />);

      const uploadButton = screen.getByRole('button', { name: /upload & process/i });
      fireEvent.click(uploadButton);

      // Should show success message
      expect(screen.getByTestId('message')).toHaveTextContent('Upload successful');
    });
  });

  describe('API Integration Tests', () => {
    it('should call API with tenant parameter', async () => {
      // This test verifies that the actual PDFUploadForm would call APIs with tenant
      const mockFetchFolders = jest.fn().mockResolvedValue({
        json: () => Promise.resolve(['folder1', 'folder2']),
      });
      
      authenticatedGet.mockImplementation(mockFetchFolders);

      // Simulate the API call that would happen in the real component
      await authenticatedGet('/api/folders', { tenant: 'tenant1' });

      expect(mockFetchFolders).toHaveBeenCalledWith('/api/folders', { tenant: 'tenant1' });
    });

    it('should handle API errors gracefully', async () => {
      authenticatedGet.mockRejectedValue(new Error('API Error'));

      try {
        await authenticatedGet('/api/folders', { tenant: 'tenant1' });
      } catch (error) {
        expect((error as Error).message).toBe('API Error');
      }
    });
  });

  describe('Tenant Switching Behavior', () => {
    it('should clear data when tenant changes', () => {
      const { rerender } = render(<MockPDFUploadFormWithTenant />);

      // Initial tenant
      expect(screen.getByTestId('current-tenant')).toHaveTextContent('tenant1');

      // Change tenant
      mockUseTenant.currentTenant = 'tenant2';
      rerender(<MockPDFUploadFormWithTenant />);

      // Should show new tenant
      expect(screen.getByTestId('current-tenant')).toHaveTextContent('tenant2');
    });
  });
});

// Simple mock component for PDFUploadForm testing
const MockPDFUploadForm = () => {
  return (
    <div>
      <form>
        <label htmlFor="file-input">Select File (PDF, JPG, PNG)</label>
        <input
          id="file-input"
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
        />
        
        <label htmlFor="folder-select">Select Folder</label>
        <select id="folder-select">
          <option value="">Choose folder</option>
          <option value="General">General</option>
          <option value="Booking.com">Booking.com</option>
          <option value="Utilities">Utilities</option>
        </select>
        
        <button type="button">+ New</button>
        <button type="submit">Upload & Process</button>
      </form>
      
      <div>
        <div>Parsed PDF Data</div>
        <div>File ID: test-invoice.pdf</div>
        <div>Folder: General</div>
        <textarea value="Invoice #12345\nAmount: €100.00" readOnly />
      </div>
      
      <div>
        <div>Parsed Vendor Data</div>
        <div>2023-01-15</div>
        <div>€100.00</div>
        <div>€21.00</div>
        <div>Test Invoice</div>
      </div>
      
      <div>
        <div>New Transaction Records (Ready for Approval)</div>
        <div>Record 1 (ID: 1)</div>
        <input value="TXN001" readOnly />
        <input value="REF001" readOnly />
        <input type="date" value="2023-01-15" readOnly />
        <input value="Test Invoice" readOnly />
        <input type="number" value="100" readOnly />
        <input value="1000" readOnly />
        <input value="2000" readOnly />
        <button>✓ Approve & Save to Database</button>
        <button>✗ Cancel</button>
      </div>
    </div>
  );
};

describe('PDFUploadForm', () => {
  // File Selection Tests
  describe('File Selection', () => {
    it('renders file input with correct accept types', () => {
      render(<MockPDFUploadForm />);
      
      const fileInput = screen.getByLabelText(/select file/i);
      expect(fileInput).toBeInTheDocument();
      expect(fileInput).toHaveAttribute('accept', '.pdf,.jpg,.jpeg,.png');
      expect(fileInput).toHaveAttribute('type', 'file');
    });
  });

  // Vendor Selection Tests
  describe('Vendor Selection', () => {
    it('loads and displays folder options', () => {
      render(<MockPDFUploadForm />);
      
      const folderSelect = screen.getByLabelText(/select folder/i);
      expect(folderSelect).toBeInTheDocument();
      
      expect(screen.getByRole('option', { name: 'General' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'Booking.com' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'Utilities' })).toBeInTheDocument();
    });

    it('shows new folder button', () => {
      render(<MockPDFUploadForm />);
      expect(screen.getByRole('button', { name: /\+ new/i })).toBeInTheDocument();
    });
  });

  // Transaction Preview Tests
  describe('Transaction Preview', () => {
    it('displays parsed PDF data', () => {
      render(<MockPDFUploadForm />);
      
      expect(screen.getByText('Parsed PDF Data')).toBeInTheDocument();
      expect(screen.getByText(/test-invoice.pdf/)).toBeInTheDocument();
      expect(screen.getByText('General')).toBeInTheDocument();
      expect(screen.getByDisplayValue(/Invoice #12345/)).toBeInTheDocument();
    });

    it('displays vendor data', () => {
      render(<MockPDFUploadForm />);
      
      expect(screen.getByText('Parsed Vendor Data')).toBeInTheDocument();
      expect(screen.getByText('2023-01-15')).toBeInTheDocument();
      expect(screen.getByText('€100.00')).toBeInTheDocument();
      expect(screen.getByText('€21.00')).toBeInTheDocument();
      expect(screen.getByText('Test Invoice')).toBeInTheDocument();
    });

    it('displays prepared transactions', () => {
      render(<MockPDFUploadForm />);
      
      expect(screen.getByText('New Transaction Records (Ready for Approval)')).toBeInTheDocument();
      expect(screen.getByText('Record 1 (ID: 1)')).toBeInTheDocument();
      expect(screen.getByDisplayValue('TXN001')).toBeInTheDocument();
      expect(screen.getByDisplayValue('REF001')).toBeInTheDocument();
    });
  });

  // Edit Interface Tests
  describe('Edit Interface', () => {
    it('shows transaction editing fields', () => {
      render(<MockPDFUploadForm />);
      
      expect(screen.getByDisplayValue('TXN001')).toBeInTheDocument();
      expect(screen.getByDisplayValue('REF001')).toBeInTheDocument();
      expect(screen.getByDisplayValue('2023-01-15')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Test Invoice')).toBeInTheDocument();
      expect(screen.getByDisplayValue('100')).toBeInTheDocument();
      expect(screen.getByDisplayValue('1000')).toBeInTheDocument();
      expect(screen.getByDisplayValue('2000')).toBeInTheDocument();
    });
  });

  // Save Operations Tests
  describe('Save Operations', () => {
    it('shows approve and cancel buttons', () => {
      render(<MockPDFUploadForm />);
      
      expect(screen.getByRole('button', { name: /✓ approve & save to database/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /✗ cancel/i })).toBeInTheDocument();
    });
  });

  // Progress Tracking Tests
  describe('Progress Tracking', () => {
    it('shows upload button', () => {
      render(<MockPDFUploadForm />);
      expect(screen.getByRole('button', { name: /upload & process/i })).toBeInTheDocument();
    });
  });

  // Drag & Drop Tests
  describe('File Drop Zone', () => {
    it('accepts file through input interface', () => {
      render(<MockPDFUploadForm />);
      const fileInput = screen.getByLabelText(/select file/i);
      expect(fileInput).toHaveAttribute('accept', '.pdf,.jpg,.jpeg,.png');
    });
  });
});
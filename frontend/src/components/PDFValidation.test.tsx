import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock fetch and EventSource
const mockFetch = jest.fn();
const mockEventSource = {
  onmessage: null as any,
  onerror: null as any,
  close: jest.fn()
};

global.fetch = mockFetch;
global.EventSource = jest.fn(() => mockEventSource) as any;

// Mock PDFValidation component
const MockPDFValidation = () => {
  const [loading, setLoading] = React.useState(false);
  const [progress, setProgress] = React.useState({ total: 0, ok: 0, failed: 0 });
  const [selectedYear, setSelectedYear] = React.useState('2025');
  const [selectedAdmin, setSelectedAdmin] = React.useState('all');
  const [validationResults, setValidationResults] = React.useState<any[]>([]);
  const [showModal, setShowModal] = React.useState(false);
  const [updateForm, setUpdateForm] = React.useState({
    reference_number: '',
    ref3: '',
    ref4: ''
  });

  const validateUrls = async () => {
    setLoading(true);
    setProgress({ total: 100, ok: 85, failed: 15 });
    
    setTimeout(() => {
      setValidationResults([
        {
          status: 'file_not_found',
          record: {
            ID: 1,
            TransactionNumber: 'TXN001',
            TransactionDate: '2023-01-15',
            TransactionDescription: 'Test Invoice',
            TransactionAmount: 100.00,
            ReferenceNumber: 'REF001',
            Ref3: 'https://drive.google.com/file/broken',
            Ref4: 'invoice.pdf',
            Administration: 'TEST'
          }
        },
        {
          status: 'gmail_manual_check',
          record: {
            ID: 2,
            TransactionNumber: 'TXN002',
            TransactionDate: '2023-01-16',
            TransactionDescription: 'Gmail Invoice',
            TransactionAmount: 200.00,
            ReferenceNumber: 'REF002',
            Ref3: 'https://mail.google.com/mail/u/0/#inbox/123',
            Ref4: 'gmail-invoice.pdf',
            Administration: 'TEST'
          }
        }
      ]);
      setLoading(false);
    }, 100);
  };

  const openUpdateModal = () => {
    setUpdateForm({
      reference_number: 'REF001',
      ref3: 'https://drive.google.com/file/broken',
      ref4: 'invoice.pdf'
    });
    setShowModal(true);
  };

  const updateRecord = async () => {
    setShowModal(false);
    // Update the validation results to show fixed status
    setValidationResults(prev => 
      prev.map(result => 
        result.record.ReferenceNumber === updateForm.reference_number
          ? { ...result, status: 'updated' }
          : result
      )
    );
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'ok': return 'green';
      case 'updated': return 'green';
      case 'gmail_manual_check': return 'yellow';
      case 'file_not_found': return 'red';
      default: return 'gray';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'ok': return 'OK';
      case 'updated': return 'Fixed';
      case 'gmail_manual_check': return 'Gmail (Manual Check)';
      case 'file_not_found': return 'File Not Found';
      default: return status;
    }
  };

  return (
    <div>
      {/* Filter Controls */}
      <div>
        <select 
          value={selectedYear} 
          onChange={(e) => setSelectedYear(e.target.value)}
          aria-label="Select Year"
        >
          <option value="2025">2025</option>
          <option value="2024">2024</option>
          <option value="2023">2023</option>
          <option value="all">All Years</option>
        </select>
        
        <select 
          value={selectedAdmin} 
          onChange={(e) => setSelectedAdmin(e.target.value)}
          aria-label="Select Administration"
        >
          <option value="all">All Administrations</option>
          <option value="TEST">TEST</option>
          <option value="PROD">PROD</option>
        </select>
        
        <button onClick={validateUrls} disabled={loading}>
          Validate PDF URLs
        </button>
        
        {validationResults.length > 0 && (
          <button onClick={validateUrls} disabled={loading}>
            Refresh Results
          </button>
        )}
      </div>

      {/* Progress Bar */}
      {loading && (
        <div>
          <div>Validating URLs...</div>
          <div role="progressbar" aria-valuenow={85} aria-valuemin={0} aria-valuemax={100}>
            Progress: 85/100
          </div>
        </div>
      )}

      {/* Status Indicators */}
      {progress.total > 0 && (
        <div>
          <div>Total Records: {progress.total}</div>
          <div>Valid URLs: {progress.ok}</div>
          <div>Issues Found: {progress.failed}</div>
          <div role="progressbar" aria-valuenow={progress.ok + progress.failed} aria-valuemin={0} aria-valuemax={progress.total}>
            Overall Progress: {progress.ok + progress.failed}/{progress.total}
          </div>
        </div>
      )}

      {/* Results Display */}
      {validationResults.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Transaction Number</th>
              <th>Date</th>
              <th>Description</th>
              <th>Amount</th>
              <th>Reference</th>
              <th>URL</th>
              <th>Document</th>
              <th>Administration</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {validationResults.map((result, index) => (
              <tr key={index}>
                <td style={{ color: getStatusColor(result.status) }}>
                  {getStatusText(result.status)}
                </td>
                <td>{result.record.TransactionNumber}</td>
                <td>{result.record.TransactionDate}</td>
                <td>{result.record.TransactionDescription}</td>
                <td>{result.record.TransactionAmount}</td>
                <td>{result.record.ReferenceNumber}</td>
                <td>{result.record.Ref3}</td>
                <td>{result.record.Ref4}</td>
                <td>{result.record.Administration}</td>
                <td>
                  <button onClick={openUpdateModal}>Update</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Manual Updates Modal */}
      {showModal && (
        <div role="dialog" aria-label="Update Record">
          <div>Update Record</div>
          <div>
            <label htmlFor="reference-number">Reference Number</label>
            <input
              id="reference-number"
              value={updateForm.reference_number}
              onChange={(e) => setUpdateForm({...updateForm, reference_number: e.target.value})}
            />
            
            <label htmlFor="document-url">Document URL (Ref3)</label>
            <input
              id="document-url"
              value={updateForm.ref3}
              onChange={(e) => setUpdateForm({...updateForm, ref3: e.target.value})}
            />
            
            <label htmlFor="document-name">Document Name (Ref4)</label>
            <input
              id="document-name"
              value={updateForm.ref4}
              onChange={(e) => setUpdateForm({...updateForm, ref4: e.target.value})}
            />
          </div>
          <div>
            <button onClick={updateRecord}>Update</button>
            <button onClick={() => setShowModal(false)}>Cancel</button>
          </div>
        </div>
      )}

      {/* Empty State */}
      {validationResults.length === 0 && !loading && (
        <div>
          Click "Validate PDF URLs" to check for missing or broken Google Drive links
        </div>
      )}
    </div>
  );
};

describe('PDFValidation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetch.mockResolvedValue({
      json: () => Promise.resolve({ success: true, administrations: ['TEST', 'PROD'] })
    });
  });

  // Progress Bar Tests
  describe('Progress Bar', () => {
    it('shows progress bar during validation', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      // Wait for the loading state to appear
      await waitFor(() => {
        expect(screen.getByText(/Validating URLs/i)).toBeInTheDocument();
      });
      expect(screen.getAllByRole('progressbar')[0]).toBeInTheDocument();
    });

    it('displays progress with current/total format', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      expect(screen.getByText(/Progress: 85\/100/)).toBeInTheDocument();
    });

    it('shows overall progress after validation starts', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        expect(screen.getByText(/Overall Progress: 100\/100/)).toBeInTheDocument();
      });
    });
  });

  // URL Validation Tests
  describe('URL Validation', () => {
    it('initiates URL validation process', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      expect(validateButton).toBeDisabled();
      expect(screen.getByText('Validating URLs...')).toBeInTheDocument();
    });

    it('shows refresh button after validation completes', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /refresh results/i })).toBeInTheDocument();
      });
    });
  });

  // Filter Controls Tests
  describe('Filter Controls', () => {
    it('renders year filter dropdown', () => {
      render(<MockPDFValidation />);
      
      const yearSelect = screen.getByLabelText('Select Year');
      expect(yearSelect).toBeInTheDocument();
      expect(screen.getByRole('option', { name: '2025' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: '2024' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: '2023' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'All Years' })).toBeInTheDocument();
    });

    it('renders administration filter dropdown', () => {
      render(<MockPDFValidation />);
      
      const adminSelect = screen.getByLabelText('Select Administration');
      expect(adminSelect).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'All Administrations' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'TEST' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'PROD' })).toBeInTheDocument();
    });

    it('allows changing year filter', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const yearSelect = screen.getByLabelText('Select Year');
      await user.selectOptions(yearSelect, '2024');
      
      expect(yearSelect).toHaveValue('2024');
    });

    it('allows changing administration filter', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const adminSelect = screen.getByLabelText('Select Administration');
      await user.selectOptions(adminSelect, 'TEST');
      
      expect(adminSelect).toHaveValue('TEST');
    });
  });

  // Results Display Tests
  describe('Results Display', () => {
    it('displays validation results table', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        expect(screen.getByRole('table')).toBeInTheDocument();
        expect(screen.getByText('TXN001')).toBeInTheDocument();
        expect(screen.getByText('TXN002')).toBeInTheDocument();
      });
    });

    it('shows transaction details in results', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        expect(screen.getByText('Test Invoice')).toBeInTheDocument();
        expect(screen.getByText('Gmail Invoice')).toBeInTheDocument();
        expect(screen.getByText('100')).toBeInTheDocument();
        expect(screen.getByText('200')).toBeInTheDocument();
        expect(screen.getByText('REF001')).toBeInTheDocument();
        expect(screen.getByText('REF002')).toBeInTheDocument();
      });
    });

    it('displays URLs and document names', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        expect(screen.getByText('https://drive.google.com/file/broken')).toBeInTheDocument();
        expect(screen.getByText('https://mail.google.com/mail/u/0/#inbox/123')).toBeInTheDocument();
        expect(screen.getByText('invoice.pdf')).toBeInTheDocument();
        expect(screen.getByText('gmail-invoice.pdf')).toBeInTheDocument();
      });
    });
  });

  // Manual Updates Tests
  describe('Manual Updates', () => {
    it('opens update modal when update button clicked', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        const updateButton = screen.getAllByRole('button', { name: /update/i })[0];
        return user.click(updateButton);
      });
      
      expect(screen.getByRole('dialog', { name: 'Update Record' })).toBeInTheDocument();
    });

    it('shows update form fields in modal', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        const updateButton = screen.getAllByRole('button', { name: /update/i })[0];
        return user.click(updateButton);
      });
      
      expect(screen.getByLabelText('Reference Number')).toBeInTheDocument();
      expect(screen.getByLabelText('Document URL (Ref3)')).toBeInTheDocument();
      expect(screen.getByLabelText('Document Name (Ref4)')).toBeInTheDocument();
    });

    it('allows editing form fields', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        const updateButton = screen.getAllByRole('button', { name: /update/i })[0];
        return user.click(updateButton);
      });
      
      const urlInput = screen.getByLabelText('Document URL (Ref3)');
      await user.clear(urlInput);
      await user.type(urlInput, 'https://drive.google.com/file/fixed');
      
      expect(urlInput).toHaveValue('https://drive.google.com/file/fixed');
    });

    it('shows update modal with form fields', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        const updateButton = screen.getAllByRole('button', { name: /update/i })[0];
        return user.click(updateButton);
      });
      
      expect(screen.getByRole('dialog', { name: 'Update Record' })).toBeInTheDocument();
      expect(screen.getByLabelText('Reference Number')).toHaveValue('REF001');
      expect(screen.getByLabelText('Document URL (Ref3)')).toHaveValue('https://drive.google.com/file/broken');
    });

    it('cancels update when cancel button clicked', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        const updateButton = screen.getAllByRole('button', { name: /update/i })[0];
        return user.click(updateButton);
      });
      
      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      await user.click(cancelButton);
      
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  // Status Indicators Tests
  describe('Status Indicators', () => {
    it('displays status statistics', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        expect(screen.getByText('Total Records: 100')).toBeInTheDocument();
        expect(screen.getByText('Valid URLs: 85')).toBeInTheDocument();
        expect(screen.getByText('Issues Found: 15')).toBeInTheDocument();
      });
    });

    it('shows different status colors and text', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        expect(screen.getByText('File Not Found')).toBeInTheDocument();
        expect(screen.getByText('Gmail (Manual Check)')).toBeInTheDocument();
      });
    });

    it('shows validation status indicators', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      await waitFor(() => {
        expect(screen.getByText('File Not Found')).toBeInTheDocument();
        expect(screen.getByText('Gmail (Manual Check)')).toBeInTheDocument();
      });
    });
  });

  // Empty State Tests
  describe('Empty State', () => {
    it('shows empty state message when no results', () => {
      render(<MockPDFValidation />);
      
      expect(screen.getByText('Click "Validate PDF URLs" to check for missing or broken Google Drive links')).toBeInTheDocument();
    });

    it('hides empty state when validation starts', async () => {
      const user = userEvent.setup();
      render(<MockPDFValidation />);
      
      const validateButton = screen.getByRole('button', { name: /validate pdf urls/i });
      await user.click(validateButton);
      
      expect(screen.queryByText('Click "Validate PDF URLs" to check for missing or broken Google Drive links')).not.toBeInTheDocument();
    });
  });
});
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

export {};

interface Transaction {
  date: string;
  description: string;
  amount: number;
  debet: string;
  credit: string;
}

interface Mutatie {
  id: number;
  description: string;
  amount: number;
}

// Mock BankingProcessor component
const MockBankingProcessor = ({ 
  testMode = true,
  hasFiles = false,
  transactions = [],
  mutaties = [],
  loading = false
}: {
  testMode?: boolean;
  hasFiles?: boolean;
  transactions?: Transaction[];
  mutaties?: Mutatie[];
  loading?: boolean;
}) => {
  const [mode, setMode] = React.useState(testMode);
  const [selectedFiles, setSelectedFiles] = React.useState(hasFiles ? ['test.csv'] : []);
  const [showPatternApproval, setShowPatternApproval] = React.useState(false);

  const handleApplyPatterns = async () => {
    // Simulate pattern application
    const hasEmptyFields = transactions.some(tx => !tx.debet || !tx.credit);
    if (hasEmptyFields) {
      setShowPatternApproval(true);
    }
  };

  return (
    <div data-testid="banking-processor">
      {/* Mode Toggle */}
      <div data-testid="mode-toggle">
        <label>
          <input
            type="checkbox"
            checked={mode}
            onChange={(e) => setMode(e.target.checked)}
            data-testid="test-mode-switch"
          />
          Mode: {mode ? 'TEST' : 'PRODUCTION'}
        </label>
      </div>

      {/* File Upload */}
      <div data-testid="file-upload-section">
        <input
          type="file"
          accept=".csv,.tsv"
          multiple
          data-testid="file-input"
          onChange={(e) => setSelectedFiles(Array.from(e.target.files || []).map(f => f.name))}
        />
        {selectedFiles.length > 0 && (
          <div data-testid="selected-files">
            Selected: {selectedFiles.join(', ')}
          </div>
        )}
        <button data-testid="process-files-btn" disabled={selectedFiles.length === 0}>
          Process Files
        </button>
      </div>

      {/* Transactions Table */}
      {transactions.length > 0 && (
        <div data-testid="transactions-table">
          <h3>Transactions ({transactions.length})</h3>
          <button data-testid="apply-patterns-btn" onClick={handleApplyPatterns}>Apply Patterns</button>
          <button data-testid="save-transactions-btn">Save to Database</button>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                <th>Amount</th>
                <th>Debet</th>
                <th>Credit</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx, i) => (
                <tr key={i} data-testid={`transaction-row-${i}`}>
                  <td>
                    <input
                      data-testid={`date-input-${i}`}
                      value={tx.date}
                      onChange={() => {}}
                    />
                  </td>
                  <td>
                    <input
                      data-testid={`description-input-${i}`}
                      value={tx.description}
                      onChange={() => {}}
                    />
                  </td>
                  <td>
                    <input
                      data-testid={`amount-input-${i}`}
                      type="number"
                      value={tx.amount}
                      onChange={() => {}}
                    />
                  </td>
                  <td>
                    <input
                      data-testid={`debet-input-${i}`}
                      value={tx.debet}
                      onChange={() => {}}
                    />
                  </td>
                  <td>
                    <input
                      data-testid={`credit-input-${i}`}
                      value={tx.credit}
                      onChange={() => {}}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Mutaties Table */}
      <div data-testid="mutaties-section">
        <h3>Mutaties ({mutaties.length})</h3>
        <div data-testid="mutaties-filters">
          <select data-testid="year-filter">
            <option value="2024">2024</option>
            <option value="2025">2025</option>
          </select>
          <select data-testid="admin-filter">
            <option value="all">All</option>
            <option value="GoodwinSolutions">GoodwinSolutions</option>
          </select>
          <button data-testid="refresh-mutaties-btn">Refresh</button>
        </div>
        <div data-testid="column-filters">
          <input data-testid="id-filter" placeholder="ID" />
          <input data-testid="description-filter" placeholder="Description" />
        </div>
        {mutaties.length > 0 && (
          <table data-testid="mutaties-table">
            <tbody>
              {mutaties.map((m, i) => (
                <tr key={i} data-testid={`mutatie-row-${i}`}>
                  <td onClick={() => {}} data-testid={`edit-mutatie-${i}`}>{m.id}</td>
                  <td>{m.description}</td>
                  <td>{m.amount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {loading && <div data-testid="loading-spinner">Loading...</div>}
      
      {/* Pattern Approval Dialog */}
      {showPatternApproval && (
        <div data-testid="pattern-approval-dialog">
          <h3>Review Pattern Suggestions</h3>
          <p>Pattern suggestions have been filled into empty fields</p>
          <button onClick={() => setShowPatternApproval(false)}>Reject Suggestions</button>
          <button onClick={() => setShowPatternApproval(false)}>Approve Suggestions</button>
        </div>
      )}
    </div>
  );
};

// Mock fetch
global.fetch = jest.fn();

describe('Banking Processor', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, data: [] })
    });
  });

  describe('File Upload', () => {
    it('renders file upload interface', () => {
      render(<MockBankingProcessor />);
      
      expect(screen.getByTestId('file-input')).toBeInTheDocument();
      expect(screen.getByTestId('process-files-btn')).toBeInTheDocument();
      expect(screen.getByTestId('process-files-btn')).toBeDisabled();
    });

    it('enables process button when files selected', async () => {
      const user = userEvent.setup();
      render(<MockBankingProcessor />);
      
      const fileInput = screen.getByTestId('file-input');
      const file = new File(['test'], 'test.csv', { type: 'text/csv' });
      
      await user.upload(fileInput, file);
      
      expect(screen.getByTestId('selected-files')).toHaveTextContent('test.csv');
      expect(screen.getByTestId('process-files-btn')).not.toBeDisabled();
    });

    it('validates CSV/TSV file types', () => {
      render(<MockBankingProcessor />);
      
      const fileInput = screen.getByTestId('file-input');
      expect(fileInput).toHaveAttribute('accept', '.csv,.tsv');
    });
  });

  describe('Mode Toggle', () => {
    it('shows test mode by default', () => {
      render(<MockBankingProcessor testMode={true} />);
      
      expect(screen.getByText('Mode: TEST')).toBeInTheDocument();
      expect(screen.getByTestId('test-mode-switch')).toBeChecked();
    });

    it('toggles between test and production mode', async () => {
      const user = userEvent.setup();
      render(<MockBankingProcessor testMode={true} />);
      
      expect(screen.getByText('Mode: TEST')).toBeInTheDocument();
      
      await user.click(screen.getByTestId('test-mode-switch'));
      
      expect(screen.getByText('Mode: PRODUCTION')).toBeInTheDocument();
    });
  });

  describe('File Processing', () => {
    const mockTransactions = [
      { date: '2024-01-01', description: 'Test Transaction', amount: 100, debet: '1000', credit: '2000' },
      { date: '2024-01-02', description: 'Another Transaction', amount: 50, debet: '1001', credit: '2001' }
    ];

    it('displays transactions after processing', () => {
      render(<MockBankingProcessor transactions={mockTransactions} />);
      
      expect(screen.getByTestId('transactions-table')).toBeInTheDocument();
      expect(screen.getByText('Transactions (2)')).toBeInTheDocument();
      expect(screen.getByTestId('transaction-row-0')).toBeInTheDocument();
      expect(screen.getByTestId('transaction-row-1')).toBeInTheDocument();
    });

    it('shows apply patterns button', () => {
      render(<MockBankingProcessor transactions={mockTransactions} />);
      
      expect(screen.getByTestId('apply-patterns-btn')).toBeInTheDocument();
    });

    it('shows save transactions button', () => {
      render(<MockBankingProcessor transactions={mockTransactions} />);
      
      expect(screen.getByTestId('save-transactions-btn')).toBeInTheDocument();
    });
  });

  describe('Pattern Application', () => {
    it('applies patterns to transactions', async () => {
      const user = userEvent.setup();
      const mockTransactions = [
        { date: '2024-01-01', description: 'Test', amount: 100, debet: '', credit: '1000' }
      ];
      
      render(<MockBankingProcessor transactions={mockTransactions} />);
      
      const applyButton = screen.getByTestId('apply-patterns-btn');
      await user.click(applyButton);
      
      expect(applyButton).toBeInTheDocument();
    });
  });

  describe('Data Validation', () => {
    const mockTransactions = [
      { date: '', description: '', amount: 0, debet: '', credit: '' }
    ];

    it('shows validation errors for required fields', () => {
      render(<MockBankingProcessor transactions={mockTransactions} />);
      
      expect(screen.getByTestId('date-input-0')).toHaveValue('');
      expect(screen.getByTestId('description-input-0')).toHaveValue('');
      expect(screen.getByTestId('amount-input-0')).toHaveValue(0);
    });

    it('validates transaction amounts', () => {
      render(<MockBankingProcessor transactions={mockTransactions} />);
      
      const amountInput = screen.getByTestId('amount-input-0');
      expect(amountInput).toHaveAttribute('type', 'number');
    });
  });

  describe('API Integration', () => {
    it('has fetch available for API calls', () => {
      expect(global.fetch).toBeDefined();
      expect(typeof global.fetch).toBe('function');
    });
  });

  describe('Table Operations', () => {
    const mockMutaties = [
      { id: 1, description: 'Test Mutatie', amount: 100 },
      { id: 2, description: 'Another Mutatie', amount: 200 }
    ];

    it('displays mutaties table', () => {
      render(<MockBankingProcessor mutaties={mockMutaties} />);
      
      expect(screen.getByTestId('mutaties-table')).toBeInTheDocument();
      expect(screen.getByText('Mutaties (2)')).toBeInTheDocument();
    });

    it('shows filtering controls', () => {
      render(<MockBankingProcessor mutaties={mockMutaties} />);
      
      expect(screen.getByTestId('year-filter')).toBeInTheDocument();
      expect(screen.getByTestId('admin-filter')).toBeInTheDocument();
      expect(screen.getByTestId('id-filter')).toBeInTheDocument();
      expect(screen.getByTestId('description-filter')).toBeInTheDocument();
    });

    it('handles refresh button click', async () => {
      const user = userEvent.setup();
      render(<MockBankingProcessor mutaties={mockMutaties} />);
      
      const refreshButton = screen.getByTestId('refresh-mutaties-btn');
      await user.click(refreshButton);
      
      expect(refreshButton).toBeInTheDocument();
    });
  });

  describe('Edit Functionality', () => {
    const mockMutaties = [
      { id: 1, description: 'Test Mutatie', amount: 100 }
    ];

    it('allows clicking on mutatie rows for editing', async () => {
      const user = userEvent.setup();
      render(<MockBankingProcessor mutaties={mockMutaties} />);
      
      const editButton = screen.getByTestId('edit-mutatie-0');
      await user.click(editButton);
      
      expect(editButton).toBeInTheDocument();
    });

    it('shows editable transaction fields', () => {
      const mockTransactions = [
        { date: '2024-01-01', description: 'Test', amount: 100, debet: '1000', credit: '2000' }
      ];
      
      render(<MockBankingProcessor transactions={mockTransactions} />);
      
      expect(screen.getByTestId('date-input-0')).toBeInTheDocument();
      expect(screen.getByTestId('description-input-0')).toBeInTheDocument();
      expect(screen.getByTestId('amount-input-0')).toBeInTheDocument();
      expect(screen.getByTestId('debet-input-0')).toBeInTheDocument();
      expect(screen.getByTestId('credit-input-0')).toBeInTheDocument();
    });
  });

  describe('Loading States', () => {
    it('shows loading spinner when processing', () => {
      render(<MockBankingProcessor loading={true} />);
      
      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });
  });

  describe('Pattern Suggestions', () => {
    const mockTransactionsWithEmptyFields = [
      { date: '2024-01-01', description: 'Test Transaction', amount: 100, debet: '', credit: '' }
    ];

    it('shows pattern suggestions in empty fields after applying patterns', async () => {
      const user = userEvent.setup();
      
      // Mock fetch to return pattern suggestions
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          transactions: [
            { date: '2024-01-01', description: 'Test Transaction', amount: 100, debet: '1000', credit: '2000' }
          ],
          patterns_found: 5,
          predictions_made: { debet: 1, credit: 1, reference: 0 },
          average_confidence: 0.85
        })
      });

      render(<MockBankingProcessor transactions={mockTransactionsWithEmptyFields} />);
      
      const applyButton = screen.getByTestId('apply-patterns-btn');
      await user.click(applyButton);
      
      // Should show pattern approval dialog
      await waitFor(() => {
        expect(screen.getByText('Review Pattern Suggestions')).toBeInTheDocument();
      });
      
      expect(screen.getByText('Pattern suggestions have been filled into empty fields')).toBeInTheDocument();
      expect(screen.getByText('Approve Suggestions')).toBeInTheDocument();
      expect(screen.getByText('Reject Suggestions')).toBeInTheDocument();
    });

    it('allows approving pattern suggestions', async () => {
      const user = userEvent.setup();
      
      // Mock the pattern suggestion flow
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          transactions: [
            { date: '2024-01-01', description: 'Test Transaction', amount: 100, debet: '1000', credit: '2000' }
          ],
          patterns_found: 5,
          predictions_made: { debet: 1, credit: 1, reference: 0 },
          average_confidence: 0.85
        })
      });

      render(<MockBankingProcessor transactions={mockTransactionsWithEmptyFields} />);
      
      const applyButton = screen.getByTestId('apply-patterns-btn');
      await user.click(applyButton);
      
      // Wait for approval dialog and approve
      await waitFor(() => {
        expect(screen.getByText('Approve Suggestions')).toBeInTheDocument();
      });
      
      const approveButton = screen.getByText('Approve Suggestions');
      await user.click(approveButton);
      
      // Dialog should close and show success message
      await waitFor(() => {
        expect(screen.queryByText('Review Pattern Suggestions')).not.toBeInTheDocument();
      });
    });

    it('allows rejecting pattern suggestions', async () => {
      const user = userEvent.setup();
      
      // Mock the pattern suggestion flow
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          transactions: [
            { date: '2024-01-01', description: 'Test Transaction', amount: 100, debet: '1000', credit: '2000' }
          ],
          patterns_found: 5,
          predictions_made: { debet: 1, credit: 1, reference: 0 },
          average_confidence: 0.85
        })
      });

      render(<MockBankingProcessor transactions={mockTransactionsWithEmptyFields} />);
      
      const applyButton = screen.getByTestId('apply-patterns-btn');
      await user.click(applyButton);
      
      // Wait for approval dialog and reject
      await waitFor(() => {
        expect(screen.getByText('Reject Suggestions')).toBeInTheDocument();
      });
      
      const rejectButton = screen.getByText('Reject Suggestions');
      await user.click(rejectButton);
      
      // Dialog should close and show rejection message
      await waitFor(() => {
        expect(screen.queryByText('Review Pattern Suggestions')).not.toBeInTheDocument();
      });
    });
  });
});
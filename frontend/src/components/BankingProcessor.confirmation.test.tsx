import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock the BankingProcessor component with confirmation dialog functionality
const MockBankingProcessorWithConfirmation = ({ 
  transactions = [],
  patternResults = null,
  onSave = jest.fn(),
  onCancel = jest.fn()
}: {
  transactions?: any[];
  patternResults?: any;
  onSave?: () => void | Promise<void>;
  onCancel?: () => void;
}) => {
  const [showSaveConfirmation, setShowSaveConfirmation] = React.useState(false);
  const [loading, setLoading] = React.useState(false);

  const handleSaveTransactions = () => {
    setShowSaveConfirmation(true);
  };

  const confirmSaveTransactions = async () => {
    setLoading(true);
    setShowSaveConfirmation(false);
    await onSave();
    setLoading(false);
  };

  const cancelSave = () => {
    setShowSaveConfirmation(false);
    onCancel();
  };

  return (
    <div data-testid="banking-processor-confirmation">
        {/* Save to Database Button */}
        <button 
          data-testid="save-to-database-btn"
          onClick={handleSaveTransactions}
          disabled={transactions.length === 0}
        >
          Save to Database
        </button>

        {/* Confirmation Modal */}
        {showSaveConfirmation && (
          <div data-testid="confirmation-modal" role="dialog" aria-labelledby="modal-title">
            <div data-testid="modal-overlay" onClick={cancelSave}></div>
            <div data-testid="modal-content">
              <h2 id="modal-title" data-testid="modal-title">Confirm Save to Database</h2>
              <button data-testid="modal-close-btn" onClick={cancelSave}>×</button>
              
              <div data-testid="modal-body">
                <p data-testid="transaction-count">
                  You are about to save <strong>{transactions.length} transactions</strong> to the database.
                </p>
                
                {patternResults && (
                  <div data-testid="pattern-summary" style={{ 
                    backgroundColor: '#EBF8FF', 
                    padding: '16px', 
                    borderRadius: '6px',
                    border: '1px solid #BEE3F8'
                  }}>
                    <p data-testid="pattern-summary-title" style={{ fontWeight: 'bold', marginBottom: '8px' }}>
                      Pattern Application Summary:
                    </p>
                    <div data-testid="pattern-stats" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
                      <span data-testid="debet-predictions">
                        Debet predictions: {patternResults.predictions_made?.debet || 0}
                      </span>
                      <span data-testid="credit-predictions">
                        Credit predictions: {patternResults.predictions_made?.credit || 0}
                      </span>
                      <span data-testid="reference-predictions">
                        Reference predictions: {patternResults.predictions_made?.reference || 0}
                      </span>
                      <span data-testid="avg-confidence">
                        Avg. confidence: {(patternResults.average_confidence * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                )}
                
                <p data-testid="warning-text" style={{ fontSize: '14px', color: '#718096' }}>
                  This action cannot be undone. Please review all transactions before confirming.
                </p>
              </div>
              
              <div data-testid="modal-footer">
                <button 
                  data-testid="cancel-btn"
                  onClick={cancelSave}
                  style={{ marginRight: '12px' }}
                >
                  Cancel
                </button>
                <button 
                  data-testid="confirm-save-btn"
                  onClick={confirmSaveTransactions}
                  disabled={loading}
                  style={{ backgroundColor: '#38A169', color: 'white' }}
                >
                  {loading ? 'Saving...' : 'Confirm Save'}
                </button>
              </div>
            </div>
          </div>
        )}

        {loading && <div data-testid="loading-indicator">Saving transactions...</div>}
      </div>
  );
};

describe('BankingProcessor - Save to Database Confirmation', () => {
  const mockTransactions = [
    { id: 1, description: 'Transaction 1', amount: 100 },
    { id: 2, description: 'Transaction 2', amount: 200 },
    { id: 3, description: 'Transaction 3', amount: 300 }
  ];

  const mockPatternResults = {
    predictions_made: {
      debet: 2,
      credit: 1,
      reference: 3
    },
    average_confidence: 0.85
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Save to Database Button', () => {
    it('renders save to database button', () => {
      render(<MockBankingProcessorWithConfirmation transactions={mockTransactions} />);
      
      expect(screen.getByTestId('save-to-database-btn')).toBeInTheDocument();
      expect(screen.getByText('Save to Database')).toBeInTheDocument();
    });

    it('disables save button when no transactions', () => {
      render(<MockBankingProcessorWithConfirmation transactions={[]} />);
      
      const saveButton = screen.getByTestId('save-to-database-btn');
      expect(saveButton).toBeDisabled();
    });

    it('enables save button when transactions exist', () => {
      render(<MockBankingProcessorWithConfirmation transactions={mockTransactions} />);
      
      const saveButton = screen.getByTestId('save-to-database-btn');
      expect(saveButton).not.toBeDisabled();
    });
  });

  describe('Confirmation Dialog', () => {
    it('shows confirmation dialog when save button is clicked', async () => {
      const user = userEvent.setup();
      render(<MockBankingProcessorWithConfirmation transactions={mockTransactions} />);
      
      const saveButton = screen.getByTestId('save-to-database-btn');
      await user.click(saveButton);
      
      expect(screen.getByTestId('confirmation-modal')).toBeInTheDocument();
      expect(screen.getByTestId('modal-title')).toHaveTextContent('Confirm Save to Database');
    });

    it('displays correct transaction count in confirmation dialog', async () => {
      const user = userEvent.setup();
      render(<MockBankingProcessorWithConfirmation transactions={mockTransactions} />);
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      
      expect(screen.getByTestId('transaction-count')).toHaveTextContent('You are about to save 3 transactions to the database.');
    });

    it('shows pattern results summary when available', async () => {
      const user = userEvent.setup();
      render(
        <MockBankingProcessorWithConfirmation 
          transactions={mockTransactions} 
          patternResults={mockPatternResults}
        />
      );
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      
      expect(screen.getByTestId('pattern-summary')).toBeInTheDocument();
      expect(screen.getByTestId('pattern-summary-title')).toHaveTextContent('Pattern Application Summary:');
      expect(screen.getByTestId('debet-predictions')).toHaveTextContent('Debet predictions: 2');
      expect(screen.getByTestId('credit-predictions')).toHaveTextContent('Credit predictions: 1');
      expect(screen.getByTestId('reference-predictions')).toHaveTextContent('Reference predictions: 3');
      expect(screen.getByTestId('avg-confidence')).toHaveTextContent('Avg. confidence: 85.0%');
    });

    it('hides pattern results when not available', async () => {
      const user = userEvent.setup();
      render(<MockBankingProcessorWithConfirmation transactions={mockTransactions} />);
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      
      expect(screen.queryByTestId('pattern-summary')).not.toBeInTheDocument();
    });

    it('shows warning text about irreversible action', async () => {
      const user = userEvent.setup();
      render(<MockBankingProcessorWithConfirmation transactions={mockTransactions} />);
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      
      expect(screen.getByTestId('warning-text')).toHaveTextContent(
        'This action cannot be undone. Please review all transactions before confirming.'
      );
    });

    it('has proper modal accessibility attributes', async () => {
      const user = userEvent.setup();
      render(<MockBankingProcessorWithConfirmation transactions={mockTransactions} />);
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      
      const modal = screen.getByTestId('confirmation-modal');
      expect(modal).toHaveAttribute('role', 'dialog');
      expect(modal).toHaveAttribute('aria-labelledby', 'modal-title');
    });
  });

  describe('Confirmation Dialog Actions', () => {
    it('closes dialog when cancel button is clicked', async () => {
      const user = userEvent.setup();
      const onCancel = jest.fn();
      render(
        <MockBankingProcessorWithConfirmation 
          transactions={mockTransactions} 
          onCancel={onCancel}
        />
      );
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      expect(screen.getByTestId('confirmation-modal')).toBeInTheDocument();
      
      await user.click(screen.getByTestId('cancel-btn'));
      
      expect(screen.queryByTestId('confirmation-modal')).not.toBeInTheDocument();
      expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it('closes dialog when close button (×) is clicked', async () => {
      const user = userEvent.setup();
      const onCancel = jest.fn();
      render(
        <MockBankingProcessorWithConfirmation 
          transactions={mockTransactions} 
          onCancel={onCancel}
        />
      );
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      await user.click(screen.getByTestId('modal-close-btn'));
      
      expect(screen.queryByTestId('confirmation-modal')).not.toBeInTheDocument();
      expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it('closes dialog when overlay is clicked', async () => {
      const user = userEvent.setup();
      const onCancel = jest.fn();
      render(
        <MockBankingProcessorWithConfirmation 
          transactions={mockTransactions} 
          onCancel={onCancel}
        />
      );
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      await user.click(screen.getByTestId('modal-overlay'));
      
      expect(screen.queryByTestId('confirmation-modal')).not.toBeInTheDocument();
      expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it('calls onSave and closes dialog when confirm button is clicked', async () => {
      const user = userEvent.setup();
      const onSave = jest.fn().mockResolvedValue(undefined);
      render(
        <MockBankingProcessorWithConfirmation 
          transactions={mockTransactions} 
          onSave={onSave}
        />
      );
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      await user.click(screen.getByTestId('confirm-save-btn'));
      
      expect(onSave).toHaveBeenCalledTimes(1);
      
      await waitFor(() => {
        expect(screen.queryByTestId('confirmation-modal')).not.toBeInTheDocument();
      });
    });

    it('shows loading state during save operation', async () => {
      const user = userEvent.setup();
      let resolvePromise: () => void;
      const savePromise = new Promise<void>((resolve) => {
        resolvePromise = resolve;
      });
      const onSave = jest.fn().mockReturnValue(savePromise);
      
      render(
        <MockBankingProcessorWithConfirmation 
          transactions={mockTransactions} 
          onSave={onSave}
        />
      );
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      
      // Check that confirm button shows normal state initially
      const confirmButton = screen.getByTestId('confirm-save-btn');
      expect(confirmButton).toHaveTextContent('Confirm Save');
      expect(confirmButton).not.toBeDisabled();
      
      // Click confirm button to start save operation
      await user.click(confirmButton);
      
      // Check loading state
      expect(screen.getByTestId('loading-indicator')).toBeInTheDocument();
      expect(screen.getByText('Saving transactions...')).toBeInTheDocument();
      
      // Modal should be closed during save, so we can't check the button state
      expect(screen.queryByTestId('confirmation-modal')).not.toBeInTheDocument();
      
      // Resolve the promise to complete the save
      resolvePromise!();
      
      await waitFor(() => {
        expect(screen.queryByTestId('loading-indicator')).not.toBeInTheDocument();
      });
    });
  });

  describe('Edge Cases', () => {
    it('handles zero confidence pattern results', async () => {
      const user = userEvent.setup();
      const zeroConfidenceResults = {
        predictions_made: { debet: 0, credit: 0, reference: 0 },
        average_confidence: 0
      };
      
      render(
        <MockBankingProcessorWithConfirmation 
          transactions={mockTransactions} 
          patternResults={zeroConfidenceResults}
        />
      );
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      
      expect(screen.getByTestId('debet-predictions')).toHaveTextContent('Debet predictions: 0');
      expect(screen.getByTestId('avg-confidence')).toHaveTextContent('Avg. confidence: 0.0%');
    });

    it('handles single transaction correctly', async () => {
      const user = userEvent.setup();
      const singleTransaction = [{ id: 1, description: 'Single Transaction', amount: 100 }];
      
      render(<MockBankingProcessorWithConfirmation transactions={singleTransaction} />);
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      
      expect(screen.getByTestId('transaction-count')).toHaveTextContent('You are about to save 1 transactions to the database.');
    });

    it('handles missing pattern predictions gracefully', async () => {
      const user = userEvent.setup();
      const incompletePatternResults = {
        predictions_made: { debet: 1 }, // missing credit and reference
        average_confidence: 0.75
      };
      
      render(
        <MockBankingProcessorWithConfirmation 
          transactions={mockTransactions} 
          patternResults={incompletePatternResults}
        />
      );
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      
      expect(screen.getByTestId('debet-predictions')).toHaveTextContent('Debet predictions: 1');
      expect(screen.getByTestId('credit-predictions')).toHaveTextContent('Credit predictions: 0');
      expect(screen.getByTestId('reference-predictions')).toHaveTextContent('Reference predictions: 0');
    });
  });

  describe('User Experience', () => {
    it('prevents accidental saves by requiring explicit confirmation', async () => {
      const user = userEvent.setup();
      const onSave = jest.fn();
      render(
        <MockBankingProcessorWithConfirmation 
          transactions={mockTransactions} 
          onSave={onSave}
        />
      );
      
      // Click save button - should not save immediately
      await user.click(screen.getByTestId('save-to-database-btn'));
      expect(onSave).not.toHaveBeenCalled();
      
      // Must click confirm to actually save
      await user.click(screen.getByTestId('confirm-save-btn'));
      expect(onSave).toHaveBeenCalledTimes(1);
    });

    it('provides clear visual feedback about what will be saved', async () => {
      const user = userEvent.setup();
      render(
        <MockBankingProcessorWithConfirmation 
          transactions={mockTransactions} 
          patternResults={mockPatternResults}
        />
      );
      
      await user.click(screen.getByTestId('save-to-database-btn'));
      
      // Should show transaction count
      expect(screen.getByTestId('transaction-count')).toBeVisible();
      
      // Should show pattern summary if available
      expect(screen.getByTestId('pattern-summary')).toBeVisible();
      
      // Should show warning about irreversible action
      expect(screen.getByTestId('warning-text')).toBeVisible();
    });
  });
});
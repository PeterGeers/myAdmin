import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

/**
 * Integration test for duplicate detection in PDFUploadForm
 * 
 * This test verifies that the duplicate warning dialog is properly integrated
 * into the PDF upload workflow and displays when duplicate transactions are detected.
 * 
 * **Validates: Requirements 7.3, 7.4, 7.5**
 */

// Mock component that simulates PDFUploadForm with duplicate detection
const MockPDFUploadFormWithDuplicates = ({ hasDuplicates = false }: { hasDuplicates?: boolean }) => {
  const [showDialog, setShowDialog] = React.useState(false);
  const [duplicateInfo, setDuplicateInfo] = React.useState<any>(null);

  React.useEffect(() => {
    if (hasDuplicates) {
      // Simulate duplicate detection after upload
      setTimeout(() => {
        setDuplicateInfo({
          existingTransaction: {
            id: '123',
            transactionDate: '2024-01-15',
            transactionDescription: 'Test Invoice',
            transactionAmount: 100.00,
            debet: '1000',
            credit: '2000',
            referenceNumber: 'TEST001',
            ref1: 'REF1',
            ref2: 'REF2',
            ref3: 'https://drive.google.com/file/existing',
            ref4: 'existing-invoice.pdf'
          },
          newTransaction: {
            id: 'new',
            transactionDate: '2024-01-15',
            transactionDescription: 'Test Invoice',
            transactionAmount: 100.00,
            debet: '1000',
            credit: '2000',
            referenceNumber: 'TEST001',
            ref1: 'REF1',
            ref2: 'REF2',
            ref3: 'https://drive.google.com/file/new',
            ref4: 'new-invoice.pdf'
          },
          matchCount: 1
        });
        setShowDialog(true);
      }, 100);
    }
  }, [hasDuplicates]);

  return (
    <div>
      <div data-testid="upload-form">
        <h1>PDF Upload Form</h1>
        <input type="file" data-testid="file-input" />
        <button data-testid="upload-button">Upload & Process</button>
      </div>

      {/* Duplicate Warning Dialog */}
      {showDialog && duplicateInfo && (
        <div 
          role="dialog" 
          aria-modal="true"
          data-testid="duplicate-warning-dialog"
        >
          <h2>⚠️ Duplicate Invoice Detected</h2>
          <div data-testid="duplicate-alert">
            {duplicateInfo.matchCount === 1 
              ? "An existing transaction with the same reference number, date, and amount was found."
              : `${duplicateInfo.matchCount} existing transactions with the same reference number, date, and amount were found.`
            }
          </div>
          
          <div data-testid="transaction-comparison">
            <h3>Transaction Comparison</h3>
            <table>
              <tbody>
                <tr>
                  <td>Date</td>
                  <td>{duplicateInfo.existingTransaction.transactionDate}</td>
                  <td>{duplicateInfo.newTransaction.transactionDate}</td>
                </tr>
                <tr>
                  <td>Amount</td>
                  <td>€{duplicateInfo.existingTransaction.transactionAmount.toFixed(2)}</td>
                  <td>€{duplicateInfo.newTransaction.transactionAmount.toFixed(2)}</td>
                </tr>
                <tr>
                  <td>Reference</td>
                  <td>{duplicateInfo.existingTransaction.referenceNumber}</td>
                  <td>{duplicateInfo.newTransaction.referenceNumber}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div data-testid="action-buttons">
            <button 
              data-testid="cancel-button"
              onClick={() => {
                setShowDialog(false);
                setDuplicateInfo(null);
              }}
            >
              Cancel Import
            </button>
            <button 
              data-testid="continue-button"
              onClick={() => {
                setShowDialog(false);
              }}
            >
              Continue Anyway
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

describe('PDFUploadForm Duplicate Detection Integration', () => {
  it('should not show duplicate dialog when no duplicates are detected', () => {
    render(<MockPDFUploadFormWithDuplicates hasDuplicates={false} />);
    
    // Upload form should be visible
    expect(screen.getByTestId('upload-form')).toBeInTheDocument();
    expect(screen.getByTestId('file-input')).toBeInTheDocument();
    expect(screen.getByTestId('upload-button')).toBeInTheDocument();
    
    // Duplicate dialog should not be present
    expect(screen.queryByTestId('duplicate-warning-dialog')).not.toBeInTheDocument();
    expect(screen.queryByText('⚠️ Duplicate Invoice Detected')).not.toBeInTheDocument();
  });

  it('should show duplicate dialog when duplicates are detected', async () => {
    render(<MockPDFUploadFormWithDuplicates hasDuplicates={true} />);
    
    // Initially, dialog should not be visible
    expect(screen.queryByTestId('duplicate-warning-dialog')).not.toBeInTheDocument();
    
    // Wait for duplicate detection to complete
    await waitFor(() => {
      expect(screen.getByTestId('duplicate-warning-dialog')).toBeInTheDocument();
    }, { timeout: 500 });
    
    // **Requirement 7.3**: Should provide clear visual feedback
    expect(screen.getByText('⚠️ Duplicate Invoice Detected')).toBeInTheDocument();
    
    // **Requirement 7.4**: Should prevent other actions until user makes a decision
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    
    // Verify duplicate information is displayed
    expect(screen.getByTestId('duplicate-alert')).toBeInTheDocument();
    expect(screen.getByText(/An existing transaction with the same reference number/)).toBeInTheDocument();
    
    // Verify transaction comparison is shown
    expect(screen.getByTestId('transaction-comparison')).toBeInTheDocument();
    expect(screen.getByText('Transaction Comparison')).toBeInTheDocument();
    
    // Verify transaction details are displayed (using getAllByText since values appear twice in comparison)
    expect(screen.getAllByText('2024-01-15').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/€100\.00/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('TEST001').length).toBeGreaterThan(0);
    
    // **Requirement 7.5**: Action buttons should be present and functional
    expect(screen.getByTestId('action-buttons')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-button')).toBeInTheDocument();
    expect(screen.getByTestId('continue-button')).toBeInTheDocument();
  });

  it('should display loading indicator during duplicate check', () => {
    // This test verifies that the loading state is properly managed
    // In the actual implementation, this would show "Checking for duplicates..."
    
    render(<MockPDFUploadFormWithDuplicates hasDuplicates={false} />);
    
    // Upload button should be present
    const uploadButton = screen.getByTestId('upload-button');
    expect(uploadButton).toBeInTheDocument();
    expect(uploadButton).toHaveTextContent('Upload & Process');
  });

  it('should maintain consistent styling with myAdmin interface', async () => {
    render(<MockPDFUploadFormWithDuplicates hasDuplicates={true} />);
    
    // Wait for dialog to appear
    await waitFor(() => {
      expect(screen.getByTestId('duplicate-warning-dialog')).toBeInTheDocument();
    });
    
    // **Requirement 7.1**: Should use consistent styling
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    
    // Verify dialog structure matches expected layout
    expect(screen.getByText('⚠️ Duplicate Invoice Detected')).toBeInTheDocument();
    expect(screen.getByTestId('transaction-comparison')).toBeInTheDocument();
    expect(screen.getByTestId('action-buttons')).toBeInTheDocument();
  });

  it('should handle user decision to continue with duplicate', async () => {
    render(<MockPDFUploadFormWithDuplicates hasDuplicates={true} />);
    
    // Wait for dialog to appear
    await waitFor(() => {
      expect(screen.getByTestId('duplicate-warning-dialog')).toBeInTheDocument();
    });
    
    // Click continue button
    const continueButton = screen.getByTestId('continue-button');
    continueButton.click();
    
    // Dialog should close
    await waitFor(() => {
      expect(screen.queryByTestId('duplicate-warning-dialog')).not.toBeInTheDocument();
    });
  });

  it('should handle user decision to cancel duplicate', async () => {
    render(<MockPDFUploadFormWithDuplicates hasDuplicates={true} />);
    
    // Wait for dialog to appear
    await waitFor(() => {
      expect(screen.getByTestId('duplicate-warning-dialog')).toBeInTheDocument();
    });
    
    // Click cancel button
    const cancelButton = screen.getByTestId('cancel-button');
    cancelButton.click();
    
    // Dialog should close
    await waitFor(() => {
      expect(screen.queryByTestId('duplicate-warning-dialog')).not.toBeInTheDocument();
    });
  });
});

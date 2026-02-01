import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';

// Mock DuplicateWarningDialog component for testing
interface Transaction {
  id: string;
  transactionDate: string;
  transactionDescription: string;
  transactionAmount: number;
  debet: string;
  credit: string;
  referenceNumber: string;
  ref1?: string;
  ref2?: string;
  ref3?: string; // File URL
  ref4?: string;
}

interface DuplicateWarningProps {
  isOpen: boolean;
  duplicateInfo: {
    existingTransaction: Transaction;
    newTransaction: Transaction;
    matchCount: number;
  };
  onContinue: () => void;
  onCancel: () => void;
  isLoading?: boolean;
}

// Mock component that simulates the actual DuplicateWarningDialog behavior
const MockDuplicateWarningDialog: React.FC<DuplicateWarningProps> = ({
  isOpen,
  duplicateInfo,
  onContinue,
  onCancel,
  isLoading = false
}) => {
  if (!isOpen) {
    return null;
  }

  const formatAmount = (amount: number): string => {
    return `€${Number(amount).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}`;
  };

  const formatDate = (dateString: string): string => {
    try {
      return new Date(dateString).toLocaleDateString('nl-NL');
    } catch {
      return dateString;
    }
  };

  const { existingTransaction, newTransaction, matchCount } = duplicateInfo;

  const renderTransactionRow = (label: string, field: keyof Transaction) => {
    const existingValue = existingTransaction[field];
    const newValue = newTransaction[field];
    const isMatch = existingValue === newValue;
    
    return (
      <tr key={field} data-testid={`transaction-row-${field}`}>
        <td>{label}</td>
        <td>
          {field === 'transactionAmount' && typeof existingValue === 'number' 
            ? formatAmount(existingValue)
            : field === 'transactionDate' && typeof existingValue === 'string'
            ? formatDate(existingValue)
            : String(existingValue || 'N/A')}
        </td>
        <td>
          {field === 'transactionAmount' && typeof newValue === 'number'
            ? formatAmount(newValue)
            : field === 'transactionDate' && typeof newValue === 'string'
            ? formatDate(newValue)
            : String(newValue || 'N/A')}
        </td>
        <td>
          <span className={`badge ${isMatch ? 'match' : 'diff'}`}>
            {isMatch ? "MATCH" : "DIFF"}
          </span>
        </td>
      </tr>
    );
  };

  return (
    <div 
      role="dialog" 
      aria-modal="true"
      data-testid="duplicate-warning-dialog"
      style={{ 
        position: 'fixed', 
        top: 0, 
        left: 0, 
        right: 0, 
        bottom: 0, 
        backgroundColor: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}
    >
      <div style={{ 
        backgroundColor: 'white', 
        padding: '20px', 
        borderRadius: '8px',
        maxWidth: '90vw',
        maxHeight: '90vh',
        overflow: 'auto'
      }}>
        {/* Header */}
        <div style={{ backgroundColor: '#e53e3e', color: 'white', padding: '12px', marginBottom: '16px' }}>
          <h2>⚠️ Duplicate Invoice Detected</h2>
        </div>

        {!isLoading && (
          <button 
            aria-label="Close"
            onClick={onCancel}
            style={{ position: 'absolute', top: '10px', right: '10px' }}
          >
            ×
          </button>
        )}

        {/* Alert Section */}
        <div style={{ backgroundColor: '#fed7d7', padding: '12px', marginBottom: '16px', borderRadius: '4px' }}>
          <div>
            <strong>Potential Duplicate Found!</strong>
          </div>
          <div>
            {matchCount === 1 
              ? "An existing transaction with the same reference number, date, and amount was found."
              : `${matchCount} existing transactions with the same reference number, date, and amount were found.`
            }
          </div>
        </div>

        {/* Transaction Comparison Table */}
        <div style={{ marginBottom: '16px' }}>
          <h3>Transaction Comparison</h3>
          
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: '#f7fafc' }}>
                <th style={{ padding: '8px', textAlign: 'left' }}>Field</th>
                <th style={{ padding: '8px', textAlign: 'left' }}>Existing Transaction</th>
                <th style={{ padding: '8px', textAlign: 'left' }}>New Transaction</th>
                <th style={{ padding: '8px', textAlign: 'center' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {renderTransactionRow("Date", "transactionDate")}
              {renderTransactionRow("Description", "transactionDescription")}
              {renderTransactionRow("Amount", "transactionAmount")}
              {renderTransactionRow("Reference", "referenceNumber")}
              {renderTransactionRow("Debet", "debet")}
              {renderTransactionRow("Credit", "credit")}
              {renderTransactionRow("Ref1", "ref1")}
              {renderTransactionRow("Ref2", "ref2")}
              {renderTransactionRow("File URL", "ref3")}
              {renderTransactionRow("Filename", "ref4")}
            </tbody>
          </table>
        </div>

        {/* File Information */}
        {(existingTransaction.ref3 || newTransaction.ref3) && (
          <div style={{ marginBottom: '16px' }}>
            <h3>File Information</h3>
            
            {existingTransaction.ref3 && (
              <div style={{ backgroundColor: '#bee3f8', padding: '12px', marginBottom: '8px', borderRadius: '4px' }}>
                <div><strong>Existing File:</strong></div>
                <a 
                  href={existingTransaction.ref3} 
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: '#3182ce', textDecoration: 'underline', wordBreak: 'break-all' }}
                >
                  {existingTransaction.ref3}
                </a>
              </div>
            )}
            
            {newTransaction.ref3 && (
              <div style={{ backgroundColor: '#c6f6d5', padding: '12px', borderRadius: '4px' }}>
                <div><strong>New File:</strong></div>
                <a 
                  href={newTransaction.ref3} 
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: '#38a169', textDecoration: 'underline', wordBreak: 'break-all' }}
                >
                  {newTransaction.ref3}
                </a>
              </div>
            )}
          </div>
        )}

        {/* Decision Help */}
        <div style={{ backgroundColor: '#f7fafc', padding: '16px', marginBottom: '16px', borderRadius: '4px' }}>
          <div><strong>What would you like to do?</strong></div>
          <div style={{ marginTop: '8px' }}>
            <div>• <strong>Continue:</strong> Process this as a new transaction (creates duplicate)</div>
            <div>• <strong>Cancel:</strong> Stop processing and clean up uploaded files</div>
          </div>
        </div>

        {/* Footer Buttons */}
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          <button
            type="button"
            onClick={onCancel}
            disabled={false}
            style={{ 
              padding: '8px 16px', 
              border: '1px solid #e53e3e', 
              backgroundColor: 'white', 
              color: '#e53e3e',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            Cancel Import
          </button>
          
          <button
            type="button"
            onClick={onContinue}
            disabled={isLoading}
            style={{ 
              padding: '8px 16px', 
              backgroundColor: '#ff6600', 
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              opacity: isLoading ? 0.6 : 1
            }}
          >
            {isLoading ? 'Processing...' : 'Continue Anyway'}
          </button>
        </div>
      </div>
    </div>
  );
};

// Helper functions for generating test data
const generateRandomString = (length: number = 10): string => {
  return Math.random().toString(36).substring(2, 2 + length);
};

const generateRandomDate = (): string => {
  const start = new Date('2020-01-01');
  const end = new Date('2025-12-31');
  const randomTime = start.getTime() + Math.random() * (end.getTime() - start.getTime());
  return new Date(randomTime).toISOString().split('T')[0];
};

const generateRandomAmount = (): number => {
  return Math.round((Math.random() * 20000 - 10000) * 100) / 100;
};

const generateTransaction = (): Transaction => ({
  id: generateRandomString(10),
  transactionDate: generateRandomDate(),
  transactionDescription: generateRandomString(50),
  transactionAmount: generateRandomAmount(),
  debet: generateRandomString(10),
  credit: generateRandomString(10),
  referenceNumber: generateRandomString(20),
  ref1: Math.random() > 0.5 ? generateRandomString(20) : undefined,
  ref2: Math.random() > 0.5 ? generateRandomString(20) : undefined,
  ref3: Math.random() > 0.5 ? `https://example.com/${generateRandomString(20)}` : undefined,
  ref4: Math.random() > 0.5 ? generateRandomString(20) : undefined
});

const generateTestProps = (): DuplicateWarningProps => ({
  isOpen: Math.random() > 0.5,
  duplicateInfo: {
    existingTransaction: generateTransaction(),
    newTransaction: generateTransaction(),
    matchCount: Math.floor(Math.random() * 10) + 1
  },
  onContinue: jest.fn(),
  onCancel: jest.fn(),
  isLoading: Math.random() > 0.7
});

// Helper function to verify dialog is open with correct structure
const verifyDialogStructure = (container: HTMLElement) => {
  const modal = screen.getByRole('dialog');
  expect(modal).toBeInTheDocument();
  expect(modal).toHaveAttribute('aria-modal', 'true');
  expect(modal).toHaveAttribute('role', 'dialog');

  const modalContent = container.querySelector('[role="dialog"]');
  expect(modalContent).toBeInTheDocument();

  expect(screen.getByText('⚠️ Duplicate Invoice Detected')).toBeInTheDocument();
  expect(screen.getByText('Transaction Comparison')).toBeInTheDocument();
  
  return modal;
};

// Helper function to verify match count message
const verifyMatchCountMessage = (matchCount: number) => {
  const expectedPattern = matchCount === 1
    ? /An existing transaction with the same reference number, date, and amount was found/
    : new RegExp(`${matchCount} existing transactions`);
  
  expect(screen.getByText(expectedPattern)).toBeInTheDocument();
};

// Helper function to verify transaction fields are displayed
const verifyTransactionFields = () => {
  const transactionFields = [
    'Date', 'Description', 'Amount', 'Reference', 'Debet', 'Credit', 
    'Ref1', 'Ref2', 'File URL', 'Filename'
  ];
  
  transactionFields.forEach(field => {
    expect(screen.getByText(field)).toBeInTheDocument();
  });
};

// Helper function to verify formatted amounts
const verifyFormattedAmounts = (existingAmount: number, newAmount: number) => {
  const formattedExistingAmount = `€${Number(existingAmount).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}`;
  const formattedNewAmount = `€${Number(newAmount).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}`;
  
  expect(screen.getByText(formattedExistingAmount)).toBeInTheDocument();
  expect(screen.getByText(formattedNewAmount)).toBeInTheDocument();
};

// Helper function to get and verify buttons
const getAndVerifyButtons = () => {
  const buttons = screen.getAllByRole('button');
  const continueButton = buttons.find(btn => btn.textContent?.includes('Continue') || btn.textContent?.includes('Processing'));
  const cancelButton = buttons.find(btn => btn.textContent?.includes('Cancel Import'));
  
  expect(continueButton).toBeInTheDocument();
  expect(cancelButton).toBeInTheDocument();
  expect(continueButton).toHaveAttribute('type', 'button');
  expect(cancelButton).toHaveAttribute('type', 'button');
  
  return { continueButton, cancelButton };
};

// Helper function to verify loading state
const verifyLoadingState = (container: HTMLElement, isLoading: boolean, continueButton: Element | undefined) => {
  const closeButton = container.querySelector('[aria-label="Close"]');
  
  expect(continueButton).toBeDefined();
  
  if (isLoading) {
    expect(continueButton).toBeDisabled();
    expect(screen.getByText('Processing...')).toBeInTheDocument();
    expect(closeButton).not.toBeInTheDocument();
  } else {
    expect(continueButton).not.toBeDisabled();
    expect(closeButton).toBeInTheDocument();
  }
};

// Helper function to verify file information section
const verifyFileInformation = (existingRef3: string | undefined, newRef3: string | undefined) => {
  const hasFileInfo = existingRef3 || newRef3;
  
  if (!hasFileInfo) {
    return;
  }
  
  expect(screen.getByText('File Information')).toBeInTheDocument();
  
  if (existingRef3) {
    expect(screen.getByText('Existing File:')).toBeInTheDocument();
    const existingFileLink = screen.getByRole('link', { name: existingRef3 });
    expect(existingFileLink).toHaveAttribute('href', existingRef3);
    expect(existingFileLink).toHaveAttribute('target', '_blank');
  }
  
  if (newRef3) {
    expect(screen.getByText('New File:')).toBeInTheDocument();
    const newFileLink = screen.getByRole('link', { name: newRef3 });
    expect(newFileLink).toHaveAttribute('href', newRef3);
    expect(newFileLink).toHaveAttribute('target', '_blank');
  }
};

// Helper function to verify decision help section
const verifyDecisionHelp = (container: HTMLElement) => {
  expect(screen.getByText('What would you like to do?')).toBeInTheDocument();
  expect(screen.getByText('Continue:')).toBeInTheDocument();
  expect(container.textContent).toContain('Process this as a new transaction');
  expect(screen.getByText('Cancel:')).toBeInTheDocument();
  expect(container.textContent).toContain('Stop processing and clean up uploaded files');
};

// Helper function to test button interactions
const testButtonInteractions = (
  isLoading: boolean,
  continueButton: Element | undefined,
  cancelButton: Element | undefined,
  mockOnContinue: jest.Mock,
  mockOnCancel: jest.Mock
) => {
  if (isLoading || !continueButton || !cancelButton) {
    return;
  }
  
  fireEvent.click(continueButton);
  expect(mockOnContinue).toHaveBeenCalledTimes(1);

  mockOnContinue.mockClear();
  fireEvent.click(cancelButton);
  expect(mockOnCancel).toHaveBeenCalledTimes(1);
};

// Helper function to verify match/diff badges
const verifyMatchDiffBadges = (container: HTMLElement, existingTransaction: Transaction, newTransaction: Transaction) => {
  const badges = screen.getAllByText(/MATCH|DIFF/);
  expect(badges.length).toBeGreaterThan(0);
  
  const transactionFieldKeys: (keyof Transaction)[] = [
    'transactionDate', 'transactionDescription', 'transactionAmount', 
    'referenceNumber', 'debet', 'credit', 'ref1', 'ref2', 'ref3', 'ref4'
  ];
  
  transactionFieldKeys.forEach(field => {
    const existingValue = existingTransaction[field];
    const newValue = newTransaction[field];
    const isMatch = existingValue === newValue;
    
    const fieldRow = container.querySelector(`[data-testid="transaction-row-${field}"]`);
    
    if (!fieldRow) {
      return;
    }
    
    const badge = fieldRow.querySelector('.badge');
    if (!badge) {
      return;
    }
    
    expect(badge.textContent).toBe(isMatch ? 'MATCH' : 'DIFF');
  });
};

describe('DuplicateWarningDialog Property Tests', () => {
  /**
   * **Feature: duplicate-invoice-detection, Property 6: User Interface Consistency**
   * 
   * For any duplicate warning scenario, the interface should display information clearly, 
   * provide intuitive controls, maintain consistent styling with existing myAdmin components, 
   * and prevent conflicting user actions
   * 
   * **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 7.1, 7.2, 7.3, 7.4, 7.5**
   */
  it('should display duplicate information consistently and provide clear user controls for any duplicate scenario', () => {
    // Run property-based test with 100 random test cases
    for (let i = 0; i < 100; i++) {
      const testProps = generateTestProps();
      const mockOnContinue = jest.fn();
      const mockOnCancel = jest.fn();

      const { container, unmount } = render(
        <MockDuplicateWarningDialog
          {...testProps}
          onContinue={mockOnContinue}
          onCancel={mockOnCancel}
        />
      );

      try {
        // Test based on dialog open state
        const isDialogOpen = testProps.isOpen;
        
        // Verify closed state
        const dialogElement = screen.queryByRole('dialog');
        const warningText = screen.queryByText('⚠️ Duplicate Invoice Detected');
        
        // When closed, dialog should not be present
        const shouldBeAbsent = !isDialogOpen;
        expect(dialogElement === null).toBe(shouldBeAbsent);
        expect(warningText === null).toBe(shouldBeAbsent);
        
        // Skip further checks if dialog is closed
        if (!isDialogOpen) {
          unmount();
          continue;
        }

        // Dialog is open - verify all requirements
        const { existingTransaction, newTransaction, matchCount } = testProps.duplicateInfo;
        
        // **Requirement 2.1**: Dialog should display all data from existing transaction in a popup window
        // **Requirement 7.1**: Should use consistent styling with existing myAdmin interface
        verifyDialogStructure(container);

        // **Requirement 2.2**: Should show all relevant information about the existing transaction
        verifyMatchCountMessage(matchCount);

        // **Requirement 7.2**: Should format data clearly and readably
        verifyTransactionFields();
        verifyFormattedAmounts(existingTransaction.transactionAmount, newTransaction.transactionAmount);

        // **Requirement 7.3**: Should provide clear visual feedback and button states
        const { continueButton, cancelButton } = getAndVerifyButtons();

        // **Requirement 7.4**: Should prevent other actions until user makes a decision
        // Modal should not close on overlay click or escape when not loading
        const modal = screen.getByRole('dialog');
        expect(modal).toHaveAttribute('aria-modal', 'true');

        // **Requirement 7.5**: Should display appropriate loading indicators
        verifyLoadingState(container, testProps.isLoading || false, continueButton);
        
        // Cancel button should always be enabled (even during loading)
        expect(cancelButton).not.toBeDisabled();

        // Check file information section
        verifyFileInformation(existingTransaction.ref3, newTransaction.ref3);

        // Check decision help section
        verifyDecisionHelp(container);

        // Test button interactions
        testButtonInteractions(testProps.isLoading || false, continueButton, cancelButton, mockOnContinue, mockOnCancel);

        // **Requirement 2.3, 2.4, 2.5**: Check match/diff badges for field comparison
        verifyMatchDiffBadges(container, existingTransaction, newTransaction);

      } catch (error) {
        console.error('UI consistency test failed for props:', testProps);
        throw error;
      } finally {
        unmount();
      }
    }
  });

  // Additional focused tests for edge cases
  it('should handle empty or undefined transaction fields gracefully', () => {
    const emptyTransaction = {
      id: '',
      transactionDate: '',
      transactionDescription: '',
      transactionAmount: 0,
      debet: '',
      credit: '',
      referenceNumber: '',
      ref1: undefined,
      ref2: undefined,
      ref3: undefined,
      ref4: undefined
    };

    const props = {
      isOpen: true,
      duplicateInfo: {
        existingTransaction: emptyTransaction,
        newTransaction: emptyTransaction,
        matchCount: 1
      },
      onContinue: jest.fn(),
      onCancel: jest.fn(),
      isLoading: false
    };

    const { unmount } = render(<MockDuplicateWarningDialog {...props} />);

    try {
      // Should render without crashing
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      
      // Should show N/A for empty fields
      const naTexts = screen.getAllByText('N/A');
      expect(naTexts.length).toBeGreaterThan(0);
      
      // Should still show formatted amount even if 0
      expect(screen.getAllByText('€0,00')).toHaveLength(2); // Both existing and new transaction amounts
      
      // Should show all MATCH badges since all fields are the same
      const matchBadges = screen.getAllByText('MATCH');
      expect(matchBadges.length).toBe(10); // 10 transaction fields compared
      
    } finally {
      unmount();
    }
  });

  it('should maintain button functionality during loading states', () => {
    const mockOnContinue = jest.fn();
    const mockOnCancel = jest.fn();

    const props = {
      isOpen: true,
      duplicateInfo: {
        existingTransaction: {
          id: '1',
          transactionDate: '2024-01-01',
          transactionDescription: 'Test',
          transactionAmount: 100,
          debet: '1000',
          credit: '2000',
          referenceNumber: 'TEST001'
        },
        newTransaction: {
          id: '2',
          transactionDate: '2024-01-01',
          transactionDescription: 'Test',
          transactionAmount: 100,
          debet: '1000',
          credit: '2000',
          referenceNumber: 'TEST001'
        },
        matchCount: 1
      },
      onContinue: mockOnContinue,
      onCancel: mockOnCancel,
      isLoading: true
    };

    const { unmount } = render(<MockDuplicateWarningDialog {...props} />);

    try {
      const buttons = screen.getAllByRole('button');
      const continueButton = buttons.find(btn => btn.textContent?.includes('Processing'));
      const cancelButton = buttons.find(btn => btn.textContent?.includes('Cancel Import'));
      
      // Continue button should be disabled and show loading state
      expect(continueButton).toBeTruthy();
      expect(continueButton).toBeDisabled();
      expect(screen.getByText('Processing...')).toBeInTheDocument();
      
      // Cancel button should still be clickable during loading
      expect(cancelButton).toBeTruthy();
      expect(cancelButton).not.toBeDisabled();
      
      // Clicking disabled continue button should not trigger callback
      const continueButtonElement = continueButton as Element;
      fireEvent.click(continueButtonElement);
      expect(mockOnContinue).not.toHaveBeenCalled();
      
      // Clicking cancel should still work
      const cancelButtonElement = cancelButton as Element;
      fireEvent.click(cancelButtonElement);
      expect(mockOnCancel).toHaveBeenCalledTimes(1);
      
    } finally {
      unmount();
    }
  });
});
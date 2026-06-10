import React from 'react';
import { render, screen, fireEvent, waitFor } from '@/test-utils';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import YearEndClosureSection from './YearEndClosureSection';

// Mock the yearEndClosureService
vi.mock('../services/yearEndClosureService', () => ({
  getYearStatus: vi.fn(),
  validateYear: vi.fn(),
  closeYear: vi.fn(),
  reopenYear: vi.fn(),
}));

// Mock useTypedTranslation to return keys as-is
vi.mock('../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, params?: any) => {
      if (params?.year !== undefined) return `${key} (${params.year})`;
      if (params?.nextYear !== undefined) return `${key} (${params.year}, ${params.nextYear})`;
      return key;
    },
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}));

import { getYearStatus, validateYear, closeYear, reopenYear } from '../services/yearEndClosureService';

const mockGetYearStatus = getYearStatus as ReturnType<typeof vi.fn>;
const mockValidateYear = validateYear as ReturnType<typeof vi.fn>;
const mockCloseYear = closeYear as ReturnType<typeof vi.fn>;
const mockReopenYear = reopenYear as ReturnType<typeof vi.fn>;

// Sample test data
const openYearStatus = {
  year: 2024,
  closed: false,
  can_close: true,
  errors: [],
  warnings: [],
  info: {
    net_result: 15000,
    net_result_formatted: '€15,000.00',
    balance_sheet_accounts: 12,
    previous_year_closed: true,
  },
};

const closedYearStatus = {
  year: 2024,
  closed: true,
  closed_date: '2025-01-15T10:30:00Z',
  closed_by: 'admin@test.com',
  closure_transaction_number: 'YE-2024-001',
  opening_balance_transaction_number: 'OB-2025-001',
  notes: 'Year closed after audit',
};

const validationSuccess = {
  can_close: true,
  errors: [],
  warnings: ['Some minor warning'],
  info: {
    net_result: 15000,
    net_result_formatted: '€15,000.00',
    balance_sheet_accounts: 12,
  },
};

const validationWithErrors = {
  can_close: false,
  errors: ['Unreconciled transactions exist', 'Missing bank statements'],
  warnings: [],
  info: {
    net_result: 15000,
    net_result_formatted: '€15,000.00',
    balance_sheet_accounts: 12,
  },
};

describe('YearEndClosureSection Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: open year status
    mockGetYearStatus.mockResolvedValue(openYearStatus);
    mockValidateYear.mockResolvedValue(validationSuccess);
  });

  describe('Loading State', () => {
    it('shows loading spinner before status is fetched', () => {
      // Make the status never resolve immediately
      mockGetYearStatus.mockImplementation(() => new Promise(() => {}));
      render(<YearEndClosureSection year={2024} />);
      expect(screen.getByText('messages.loading')).toBeInTheDocument();
    });
  });

  describe('Open Year Rendering', () => {
    it('renders the year-end title heading', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.title')).toBeInTheDocument();
      });
    });

    it('displays open status badge', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.status.open')).toBeInTheDocument();
      });
    });

    it('displays status year information', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText(/yearEnd.status.title.*2024/)).toBeInTheDocument();
      });
    });

    it('shows net result info for open year', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText(/€15,000.00/)).toBeInTheDocument();
      });
    });

    it('shows balance sheet accounts count', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText(/12/)).toBeInTheDocument();
      });
    });

    it('shows previous year closed status when validation includes it', async () => {
      mockValidateYear.mockResolvedValue({
        ...validationSuccess,
        info: {
          ...validationSuccess.info,
          previous_year_closed: true,
        },
      });
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText(/2023/)).toBeInTheDocument();
      });
    });

    it('renders close year button for open year', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });
    });

    it('does not render reopen button for open year', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.title')).toBeInTheDocument();
      });
      expect(screen.queryByText(/yearEnd.actions.reopenYear/)).not.toBeInTheDocument();
    });
  });

  describe('Closed Year Rendering', () => {
    beforeEach(() => {
      mockGetYearStatus.mockImplementation((year: number) => {
        if (year === 2024) return Promise.resolve(closedYearStatus);
        // Next year (2025) is open
        return Promise.resolve({ year: 2025, closed: false });
      });
    });

    it('displays closed status badge', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.status.closed')).toBeInTheDocument();
      });
    });

    it('shows closed date', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText(/yearEnd.closedDate/)).toBeInTheDocument();
      });
    });

    it('shows closed by user', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText(/admin@test.com/)).toBeInTheDocument();
      });
    });

    it('shows closure notes', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText(/Year closed after audit/)).toBeInTheDocument();
      });
    });

    it('renders reopen button for closed year', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.reopenYear (2024)')).toBeInTheDocument();
      });
    });

    it('does not render close button for closed year', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.title')).toBeInTheDocument();
      });
      expect(screen.queryByText(/yearEnd.actions.closeYear/)).not.toBeInTheDocument();
    });
  });

  describe('Reopen Blocked When Next Year Closed', () => {
    beforeEach(() => {
      mockGetYearStatus.mockImplementation((year: number) => {
        if (year === 2024) return Promise.resolve(closedYearStatus);
        // Next year (2025) is also closed
        return Promise.resolve({ year: 2025, closed: true, closed_date: '2026-01-10T00:00:00Z' });
      });
    });

    it('disables reopen button when next year is closed', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        const reopenBtn = screen.getByText('yearEnd.actions.reopenYear (2024)');
        expect(reopenBtn.closest('button')).toBeDisabled();
      });
    });

    it('shows warning alert about blocked reopen', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText(/yearEnd.reopen.blockedByNextYear/)).toBeInTheDocument();
      });
    });
  });

  describe('Close Year Dialog', () => {
    it('opens close dialog on button click', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.closeYear (2024)'));

      await waitFor(() => {
        expect(screen.getByText('yearEnd.wizard.confirmTitle (2024)')).toBeInTheDocument();
      });
    });

    it('shows validation warnings in close dialog', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.closeYear (2024)'));

      await waitFor(() => {
        expect(screen.getByText('• Some minor warning')).toBeInTheDocument();
      });
    });

    it('shows ready to close message when validation passes', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.closeYear (2024)'));

      await waitFor(() => {
        expect(screen.getByText('yearEnd.wizard.readyToClose')).toBeInTheDocument();
      });
    });

    it('shows errors and hides confirm button when validation fails', async () => {
      mockValidateYear.mockResolvedValue(validationWithErrors);

      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.closeYear (2024)'));

      await waitFor(() => {
        expect(screen.getByText('yearEnd.wizard.cannotClose')).toBeInTheDocument();
        expect(screen.getByText('• Unreconciled transactions exist')).toBeInTheDocument();
        expect(screen.getByText('• Missing bank statements')).toBeInTheDocument();
      });
      // Confirm close button should not be shown
      expect(screen.queryByText('yearEnd.actions.confirmClose')).not.toBeInTheDocument();
    });

    it('shows notes textarea when validation passes', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.closeYear (2024)'));

      await waitFor(() => {
        expect(screen.getByPlaceholderText('yearEnd.wizard.notesPlaceholder')).toBeInTheDocument();
      });
    });

    it('shows cancel button in close dialog', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.closeYear (2024)'));

      await waitFor(() => {
        expect(screen.getByText('actions.cancel')).toBeInTheDocument();
      });
    });

    it('closes dialog when cancel is clicked', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.closeYear (2024)'));

      await waitFor(() => {
        expect(screen.getByText('yearEnd.wizard.confirmTitle (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('actions.cancel'));

      await waitFor(() => {
        expect(screen.queryByText('yearEnd.wizard.confirmTitle (2024)')).not.toBeInTheDocument();
      });
    });
  });

  describe('Close Year Action', () => {
    it('calls closeYear service when confirmed', async () => {
      mockCloseYear.mockResolvedValue({
        success: true,
        year: 2024,
        message: 'Year 2024 closed successfully',
      });

      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.closeYear (2024)'));

      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.confirmClose')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.confirmClose'));

      await waitFor(() => {
        expect(mockCloseYear).toHaveBeenCalledWith(2024, '');
      });
    });

    it('passes notes to closeYear when provided', async () => {
      mockCloseYear.mockResolvedValue({
        success: true,
        year: 2024,
        message: 'Year 2024 closed successfully',
      });

      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.closeYear (2024)'));

      await waitFor(() => {
        expect(screen.getByPlaceholderText('yearEnd.wizard.notesPlaceholder')).toBeInTheDocument();
      });

      fireEvent.change(screen.getByPlaceholderText('yearEnd.wizard.notesPlaceholder'), {
        target: { value: 'Audit completed' },
      });

      fireEvent.click(screen.getByText('yearEnd.actions.confirmClose'));

      await waitFor(() => {
        expect(mockCloseYear).toHaveBeenCalledWith(2024, 'Audit completed');
      });
    });

    it('calls onYearClosed callback after successful closure', async () => {
      const onYearClosed = vi.fn();
      mockCloseYear.mockResolvedValue({
        success: true,
        year: 2024,
        message: 'Year 2024 closed successfully',
      });

      render(<YearEndClosureSection year={2024} onYearClosed={onYearClosed} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.closeYear (2024)'));
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.confirmClose')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.confirmClose'));

      await waitFor(() => {
        expect(onYearClosed).toHaveBeenCalled();
      });
    });
  });

  describe('Reopen Year Dialog', () => {
    beforeEach(() => {
      mockGetYearStatus.mockImplementation((year: number) => {
        if (year === 2024) return Promise.resolve(closedYearStatus);
        return Promise.resolve({ year: 2025, closed: false });
      });
    });

    it('opens reopen dialog on button click', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.reopenYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.reopenYear (2024)'));

      await waitFor(() => {
        expect(screen.getByText('yearEnd.reopen.confirmTitle (2024)')).toBeInTheDocument();
      });
    });

    it('shows warning in reopen dialog', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.reopenYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.reopenYear (2024)'));

      await waitFor(() => {
        expect(screen.getByText('yearEnd.reopen.warning')).toBeInTheDocument();
      });
    });

    it('calls reopenYear service when confirmed', async () => {
      mockReopenYear.mockResolvedValue({
        success: true,
        year: 2024,
        message: 'Year 2024 reopened',
      });

      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.reopenYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.reopenYear (2024)'));

      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.confirmReopen')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.confirmReopen'));

      await waitFor(() => {
        expect(mockReopenYear).toHaveBeenCalledWith(2024);
      });
    });

    it('calls onYearReopened callback after successful reopen', async () => {
      const onYearReopened = vi.fn();
      mockReopenYear.mockResolvedValue({
        success: true,
        year: 2024,
        message: 'Year 2024 reopened',
      });

      render(<YearEndClosureSection year={2024} onYearReopened={onYearReopened} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.reopenYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.reopenYear (2024)'));
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.confirmReopen')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.confirmReopen'));

      await waitFor(() => {
        expect(onYearReopened).toHaveBeenCalled();
      });
    });

    it('closes reopen dialog when cancel is clicked', async () => {
      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.reopenYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.reopenYear (2024)'));
      await waitFor(() => {
        expect(screen.getByText('yearEnd.reopen.confirmTitle (2024)')).toBeInTheDocument();
      });

      // There may be multiple cancel buttons (one from close dialog area if rendered), get the visible one
      const cancelButtons = screen.getAllByText('actions.cancel');
      fireEvent.click(cancelButtons[cancelButtons.length - 1]);

      await waitFor(() => {
        expect(screen.queryByText('yearEnd.reopen.confirmTitle (2024)')).not.toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('handles getYearStatus failure gracefully', async () => {
      mockGetYearStatus.mockRejectedValue(new Error('Network error'));
      render(<YearEndClosureSection year={2024} />);
      // Should show loading state since status never resolves successfully
      // The component stays in loading state as yearStatus remains null
      await waitFor(() => {
        expect(screen.getByText('messages.loading')).toBeInTheDocument();
      });
    });

    it('handles validateYear failure in close dialog with toast', async () => {
      mockValidateYear.mockRejectedValue(new Error('Validation service unavailable'));

      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.closeYear (2024)'));

      // Dialog should not open since validation failed
      await waitFor(() => {
        expect(screen.queryByText('yearEnd.wizard.confirmTitle (2024)')).not.toBeInTheDocument();
      });
    });

    it('handles closeYear failure gracefully', async () => {
      mockCloseYear.mockRejectedValue(new Error('Close operation failed'));

      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.closeYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.closeYear (2024)'));
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.confirmClose')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.confirmClose'));

      // Should not crash, dialog should still be visible
      await waitFor(() => {
        expect(screen.getByText('yearEnd.wizard.confirmTitle (2024)')).toBeInTheDocument();
      });
    });

    it('handles reopenYear failure gracefully', async () => {
      mockGetYearStatus.mockImplementation((year: number) => {
        if (year === 2024) return Promise.resolve(closedYearStatus);
        return Promise.resolve({ year: 2025, closed: false });
      });
      mockReopenYear.mockRejectedValue(new Error('Reopen failed'));

      render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.reopenYear (2024)')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.reopenYear (2024)'));
      await waitFor(() => {
        expect(screen.getByText('yearEnd.actions.confirmReopen')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('yearEnd.actions.confirmReopen'));

      // Should not crash, dialog should still be visible
      await waitFor(() => {
        expect(screen.getByText('yearEnd.reopen.confirmTitle (2024)')).toBeInTheDocument();
      });
    });
  });

  describe('Year Change', () => {
    it('fetches new status when year prop changes', async () => {
      const { rerender } = render(<YearEndClosureSection year={2024} />);
      await waitFor(() => {
        expect(mockGetYearStatus).toHaveBeenCalledWith(2024);
      });

      rerender(<YearEndClosureSection year={2023} />);
      await waitFor(() => {
        expect(mockGetYearStatus).toHaveBeenCalledWith(2023);
      });
    });
  });
});

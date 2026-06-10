import React from 'react';
import { render, screen, fireEvent, waitFor } from '@/test-utils';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import STRInvoice from './STRInvoice';

// Mock the API service
vi.mock('../services/apiService', () => ({
  authenticatedGet: vi.fn(),
  authenticatedPost: vi.fn(),
}));

// Mock useTypedTranslation to return keys as-is
vi.mock('../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) => {
      if (params?.count !== undefined) return `${key} (${params.count})`;
      if (params?.filtered !== undefined && params?.total !== undefined)
        return `${key} (${params.filtered}/${params.total})`;
      if (params?.code !== undefined) return `${key} (${params.code})`;
      if (params?.name !== undefined) return `${key} (${params.name})`;
      return key;
    },
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}));

import { authenticatedGet, authenticatedPost } from '../services/apiService';

const mockAuthGet = authenticatedGet as ReturnType<typeof vi.fn>;
const mockAuthPost = authenticatedPost as ReturnType<typeof vi.fn>;

// Helper to create mock response
function mockFetchResponse(data: unknown) {
  return { json: () => Promise.resolve(data) };
}

// Sample test data
const mockBookings = [
  {
    reservationCode: 'RES001',
    guestName: 'John Doe',
    channel: 'Airbnb',
    listing: 'Green Studio',
    checkinDate: '2025-03-15',
    checkoutDate: '2025-03-18',
    nights: 3,
    guests: 2,
    amountGross: 450.00,
  },
  {
    reservationCode: 'RES002',
    guestName: 'Jane Smith',
    channel: 'Booking.com',
    listing: 'Red Studio',
    checkinDate: '2025-04-01',
    checkoutDate: '2025-04-05',
    nights: 4,
    guests: 1,
    amountGross: 600.50,
  },
];

describe('STRInvoice Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: bookings API returns mock data
    mockAuthGet.mockImplementation(() => {
      return Promise.resolve(mockFetchResponse({ success: true, bookings: mockBookings }));
    });
  });

  describe('Initial Rendering', () => {
    it('renders the invoice title', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('invoice.title')).toBeInTheDocument();
      });
    });

    it('renders the filter section heading', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('invoice.filterBookings')).toBeInTheDocument();
      });
    });

    it('renders language selector with Dutch and English options', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'invoice.languages.nl' })).toBeInTheDocument();
        expect(screen.getByRole('option', { name: 'invoice.languages.en' })).toBeInTheDocument();
      });
    });

    it('renders the reload button', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('invoice.reload')).toBeInTheDocument();
      });
    });

    it('renders start and end date inputs', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('invoice.startDate')).toBeInTheDocument();
        expect(screen.getByText('invoice.endDate')).toBeInTheDocument();
      });
    });
  });

  describe('Data Loading', () => {
    it('calls bookings API on mount with date range', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(mockAuthGet).toHaveBeenCalledWith(
          expect.stringContaining('/api/str-invoice/search-booking')
        );
      });
    });

    it('includes query, limit, startDate, and endDate params in API call', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        const call = mockAuthGet.mock.calls[0][0] as string;
        expect(call).toContain('query=');
        expect(call).toContain('limit=all');
        expect(call).toContain('startDate=');
        expect(call).toContain('endDate=');
      });
    });

    it('displays booking data in table after loading', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('RES001')).toBeInTheDocument();
        expect(screen.getByText('John Doe')).toBeInTheDocument();
        expect(screen.getByText('Airbnb')).toBeInTheDocument();
      });
    });

    it('displays multiple bookings in table', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('RES001')).toBeInTheDocument();
        expect(screen.getByText('RES002')).toBeInTheDocument();
      });
    });

    it('displays formatted amount with euro sign', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        // Euro sign and amount are in separate text nodes inside a <td>
        const cells = screen.getAllByRole('cell');
        const amount450 = cells.find(cell => cell.textContent?.includes('€') && cell.textContent?.includes('450.00'));
        const amount600 = cells.find(cell => cell.textContent?.includes('€') && cell.textContent?.includes('600.50'));
        expect(amount450).toBeDefined();
        expect(amount600).toBeDefined();
      });
    });

    it('shows info alert with bookings loaded count', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('invoice.bookingsLoaded (2)')).toBeInTheDocument();
      });
    });

    it('shows no data message when bookings are empty', async () => {
      mockAuthGet.mockImplementation(() => {
        return Promise.resolve(mockFetchResponse({ success: true, bookings: [] }));
      });

      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('invoice.messages.noBookingsInDatabase')).toBeInTheDocument();
      });
    });
  });

  describe('Date Range Controls', () => {
    it('reloads bookings when reload button is clicked', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('invoice.reload')).toBeInTheDocument();
      });

      mockAuthGet.mockClear();
      fireEvent.click(screen.getByText('invoice.reload'));

      await waitFor(() => {
        expect(mockAuthGet).toHaveBeenCalled();
      });
    });
  });

  describe('Language Selection', () => {
    it('defaults to Dutch language', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        const selects = screen.getAllByRole('combobox');
        const langSelect = selects.find(s => {
          const options = s.querySelectorAll('option');
          return Array.from(options).some(opt => opt.textContent === 'invoice.languages.nl');
        });
        expect(langSelect).toHaveValue('nl');
      });
    });

    it('allows changing language to English', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        const selects = screen.getAllByRole('combobox');
        const langSelect = selects.find(s => {
          const options = s.querySelectorAll('option');
          return Array.from(options).some(opt => opt.textContent === 'invoice.languages.nl');
        });
        expect(langSelect).toBeDefined();
        fireEvent.change(langSelect!, { target: { value: 'en' } });
        expect(langSelect).toHaveValue('en');
      });
    });
  });

  describe('Invoice Generation', () => {
    it('opens billing form when generate invoice button is clicked', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('RES002')).toBeInTheDocument();
      });

      // Table sorted desc by checkinDate — RES002 first
      const generateButtons = screen.getAllByText('invoice.table.generateInvoice');
      fireEvent.click(generateButtons[0]);

      await waitFor(() => {
        expect(screen.getByText('invoice.billingAddress.title (RES002)')).toBeInTheDocument();
      });
    });

    it('shows billing form fields for custom billing info', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('RES001')).toBeInTheDocument();
      });

      const generateButtons = screen.getAllByText('invoice.table.generateInvoice');
      fireEvent.click(generateButtons[0]);

      await waitFor(() => {
        // Billing modal has 3 input fields (name, address, city)
        const inputs = screen.getAllByRole('textbox');
        // The billing form adds 3 new inputs
        expect(inputs.length).toBeGreaterThanOrEqual(3);
      });
    });

    it('calls generate-invoice API when billing form is submitted', async () => {
      mockAuthPost.mockResolvedValue(
        mockFetchResponse({ success: true, html: '<div>Invoice HTML</div>' })
      );

      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('RES002')).toBeInTheDocument();
      });

      // Table is sorted by checkinDate desc, so RES002 (Apr) appears first
      const generateButtons = screen.getAllByText('invoice.table.generateInvoice');
      fireEvent.click(generateButtons[0]);

      await waitFor(() => {
        expect(screen.getByText('invoice.billingAddress.generate')).toBeInTheDocument();
      });

      // Click the Generate button in the billing form
      fireEvent.click(screen.getByText('invoice.billingAddress.generate'));

      await waitFor(() => {
        expect(mockAuthPost).toHaveBeenCalledWith('/api/str-invoice/generate-invoice', {
          reservationCode: 'RES002',
          language: 'nl',
          customBilling: {},
        });
      });
    });

    it('opens invoice preview modal after successful generation', async () => {
      mockAuthPost.mockResolvedValue(
        mockFetchResponse({ success: true, html: '<div>Invoice Content</div>' })
      );

      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('RES002')).toBeInTheDocument();
      });

      const generateButtons = screen.getAllByText('invoice.table.generateInvoice');
      fireEvent.click(generateButtons[0]);

      await waitFor(() => {
        expect(screen.getByText('invoice.billingAddress.generate')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('invoice.billingAddress.generate'));

      await waitFor(() => {
        expect(screen.getByText('invoice.invoicePreview.title (RES002)')).toBeInTheDocument();
      });
    });

    it('shows print button in the invoice preview', async () => {
      mockAuthPost.mockResolvedValue(
        mockFetchResponse({ success: true, html: '<div>Invoice Content</div>' })
      );

      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('RES002')).toBeInTheDocument();
      });

      const generateButtons = screen.getAllByText('invoice.table.generateInvoice');
      fireEvent.click(generateButtons[0]);

      await waitFor(() => {
        expect(screen.getByText('invoice.billingAddress.generate')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('invoice.billingAddress.generate'));

      await waitFor(() => {
        expect(screen.getByText('invoice.invoicePreview.print')).toBeInTheDocument();
      });
    });

    it('sends custom billing data when provided', async () => {
      mockAuthPost.mockResolvedValue(
        mockFetchResponse({ success: true, html: '<div>Invoice</div>' })
      );

      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('RES002')).toBeInTheDocument();
      });

      // Table sorted by checkinDate desc, RES002 first
      const generateButtons = screen.getAllByText('invoice.table.generateInvoice');
      fireEvent.click(generateButtons[0]);

      // Wait for billing modal to be visible
      await waitFor(() => {
        expect(screen.getByText('invoice.billingAddress.generate')).toBeInTheDocument();
      });

      // Fill in custom billing fields
      const billingInputs = screen.getAllByRole('textbox').filter(input =>
        input.getAttribute('placeholder')?.includes('invoice.billingAddress.')
      );

      expect(billingInputs).toHaveLength(3);
      fireEvent.change(billingInputs[0], { target: { value: 'Custom Corp' } });
      fireEvent.change(billingInputs[1], { target: { value: '123 Main St' } });
      fireEvent.change(billingInputs[2], { target: { value: 'Amsterdam' } });

      // Wait for state to settle after changes
      await waitFor(() => {
        expect(billingInputs[0]).toHaveValue('Custom Corp');
      });

      const generateBtn = screen.getByText('invoice.billingAddress.generate');
      fireEvent.click(generateBtn);

      await waitFor(() => {
        expect(mockAuthPost).toHaveBeenCalled();
      });

      // Verify the call includes custom billing data
      const postCall = mockAuthPost.mock.calls[0];
      expect(postCall[0]).toBe('/api/str-invoice/generate-invoice');
      expect(postCall[1].customBilling).toEqual({ name: 'Custom Corp', address: '123 Main St', city: 'Amsterdam' });
    });

    it('closes billing form when cancel button is clicked', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('RES001')).toBeInTheDocument();
      });

      const generateButtons = screen.getAllByText('invoice.table.generateInvoice');
      fireEvent.click(generateButtons[0]);

      await waitFor(() => {
        expect(screen.getByText('invoice.billingAddress.cancel')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('invoice.billingAddress.cancel'));

      await waitFor(() => {
        expect(screen.queryByText('invoice.billingAddress.generate')).not.toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('handles bookings API failure gracefully', async () => {
      mockAuthGet.mockRejectedValue(new Error('Network error'));

      render(<STRInvoice />);
      // Should render without crashing and show empty state
      await waitFor(() => {
        expect(screen.getByText('invoice.title')).toBeInTheDocument();
      });
    });

    it('handles API returning success:false', async () => {
      mockAuthGet.mockImplementation(() => {
        return Promise.resolve(mockFetchResponse({ success: false, error: 'Server error' }));
      });

      render(<STRInvoice />);
      // Should render without crashing
      await waitFor(() => {
        expect(screen.getByText('invoice.title')).toBeInTheDocument();
      });
    });

    it('handles invoice generation API failure gracefully', async () => {
      mockAuthPost.mockRejectedValue(new Error('Generation failed'));

      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('RES002')).toBeInTheDocument();
      });

      const generateButtons = screen.getAllByText('invoice.table.generateInvoice');
      fireEvent.click(generateButtons[0]);

      await waitFor(() => {
        expect(screen.getByText('invoice.billingAddress.generate')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('invoice.billingAddress.generate'));

      // Should not crash — component should still be visible
      await waitFor(() => {
        expect(screen.getByText('invoice.title')).toBeInTheDocument();
      });
    });
  });

  describe('Table Display', () => {
    it('shows generate invoice button for each booking row', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        const generateButtons = screen.getAllByText('invoice.table.generateInvoice');
        expect(generateButtons).toHaveLength(2);
      });
    });

    it('displays booking nights count', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        expect(screen.getByText('3')).toBeInTheDocument();
        expect(screen.getByText('4')).toBeInTheDocument();
      });
    });

    it('displays filtered results count', async () => {
      render(<STRInvoice />);
      await waitFor(() => {
        // Shows filtered/total count when data is loaded — text is "invoice.filteredResults (2/2)"
        expect(screen.getByText('invoice.filteredResults (2/2)')).toBeInTheDocument();
      });
    });
  });
});

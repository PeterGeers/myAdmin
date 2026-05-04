/**
 * BnbReturningGuestsReport Unit Tests
 *
 * Tests the Table Filter Framework v2 migration:
 * - FilterableHeader rendering with aria-sort and aria-label
 * - useFilterableTable hook integration (filter + sort)
 * - Preservation of row-click expand/collapse behavior
 * - processedData rendering instead of raw data
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';

// Mock translation hook
vi.mock('../../../src/hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'bnb.returningGuests': 'Returning Guests',
        'bnb.guestsFound': `${params?.count ?? 0} guests found`,
        'bnb.count': 'Count',
        'tables.guestName': 'Guest Name',
        'actions.refreshData': 'Refresh Data',
        'bnb.bookingsFor': `Bookings for ${params?.name ?? ''}`,
        'bnb.totalBookings': `${params?.count ?? 0} bookings`,
        'tables.checkIn': 'Check-in',
        'tables.checkOut': 'Check-out',
        'filters.channel': 'Channel',
        'filters.listing': 'Listing',
        'tables.nights': 'Nights',
        'tables.gross': 'Gross',
        'tables.net': 'Net',
        'tables.reservation': 'Reservation',
        'titles.bnbReturningGuests': 'BNB Returning Guests',
        'common:labels.instructions': 'Instructions',
        'common:messages.clickRefreshToLoad': 'Click refresh to load',
        'bnb.tableShowsReturningGuests': 'Table shows returning guests',
        'bnb.clickGuestToExpand': 'Click guest to expand',
        'bnb.expandedViewShowsDetails': 'Expanded view shows details',
        'bnb.helpsIdentifyLoyalCustomers': 'Helps identify loyal customers',
      };
      return translations[key] || key;
    },
  }),
}));

// Mock API service
const mockFetchResponse = (data: any) =>
  Promise.resolve({ json: () => Promise.resolve(data) });

vi.mock('../../../src/services/apiService', () => ({
  authenticatedGet: vi.fn(() => mockFetchResponse({ success: true, data: [] })),
  buildEndpoint: vi.fn((path: string, params?: URLSearchParams) =>
    params ? `${path}?${params.toString()}` : path
  ),
}));

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@/test-utils';
import BnbReturningGuestsReport from '../../../src/components/reports/BnbReturningGuestsReport';
import { authenticatedGet } from '../../../src/services/apiService';

const mockGuests = [
  { guestName: 'Alice Johnson', aantal: 5 },
  { guestName: 'Bob Smith', aantal: 3 },
  { guestName: 'Charlie Brown', aantal: 8 },
  { guestName: 'Diana Prince', aantal: 2 },
];

const mockBookings = [
  {
    checkinDate: '2024-03-15',
    checkoutDate: '2024-03-18',
    channel: 'Airbnb',
    listing: 'Beach House',
    nights: 3,
    amountGross: 450.00,
    amountNett: 405.00,
    reservationCode: 'ABC123',
  },
  {
    checkinDate: '2024-06-01',
    checkoutDate: '2024-06-05',
    channel: 'Booking.com',
    listing: 'City Apartment',
    nights: 4,
    amountGross: 600.00,
    amountNett: 540.00,
    reservationCode: 'DEF456',
  },
];

describe('BnbReturningGuestsReport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (authenticatedGet as any).mockImplementation((url: string) => {
      if (url.includes('bnb-returning-guests')) {
        return mockFetchResponse({ success: true, data: mockGuests });
      }
      if (url.includes('bnb-guest-bookings')) {
        return mockFetchResponse({ success: true, data: mockBookings });
      }
      return mockFetchResponse({ success: true, data: [] });
    });
  });

  describe('Framework Integration', () => {
    it('renders FilterableHeader components with aria-sort attributes', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText(/guests found/)).toBeInTheDocument();
      });

      // FilterableHeader renders <Th> with aria-sort
      const sortableHeaders = document.querySelectorAll('[aria-sort]');
      expect(sortableHeaders.length).toBeGreaterThanOrEqual(2);
    });

    it('renders filter inputs with aria-label attributes', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      await waitFor(() => {
        expect(screen.getByText(/guests found/)).toBeInTheDocument();
      });

      // FilterableHeader renders inputs with aria-label="Filter by {label}"
      const guestNameFilter = screen.getByLabelText('Filter by Guest Name');
      const countFilter = screen.getByLabelText('Filter by Count');

      expect(guestNameFilter).toBeInTheDocument();
      expect(countFilter).toBeInTheDocument();
    });

    it('displays processedData count (not raw data count) in header', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      await waitFor(() => {
        expect(screen.getByText('4 guests found')).toBeInTheDocument();
      });
    });
  });

  describe('Filtering', () => {
    it('filters guests by name (case-insensitive substring)', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      await waitFor(() => {
        expect(screen.getByText('4 guests found')).toBeInTheDocument();
      });

      const guestNameFilter = screen.getByLabelText('Filter by Guest Name');

      await act(async () => {
        fireEvent.change(guestNameFilter, { target: { value: 'alice' } });
      });

      // After debounce, only Alice should show
      await waitFor(() => {
        expect(screen.getByText('1 guests found')).toBeInTheDocument();
      }, { timeout: 500 });
    });

    it('filters guests by count', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      await waitFor(() => {
        expect(screen.getByText('4 guests found')).toBeInTheDocument();
      });

      const countFilter = screen.getByLabelText('Filter by Count');

      await act(async () => {
        fireEvent.change(countFilter, { target: { value: '5' } });
      });

      // After debounce, only Alice (5) should show
      await waitFor(() => {
        expect(screen.getByText('1 guests found')).toBeInTheDocument();
      }, { timeout: 500 });
    });

    it('shows all guests when filter is cleared', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      await waitFor(() => {
        expect(screen.getByText('4 guests found')).toBeInTheDocument();
      });

      const guestNameFilter = screen.getByLabelText('Filter by Guest Name');

      // Apply filter
      await act(async () => {
        fireEvent.change(guestNameFilter, { target: { value: 'alice' } });
      });

      await waitFor(() => {
        expect(screen.getByText('1 guests found')).toBeInTheDocument();
      }, { timeout: 500 });

      // Clear filter
      await act(async () => {
        fireEvent.change(guestNameFilter, { target: { value: '' } });
      });

      await waitFor(() => {
        expect(screen.getByText('4 guests found')).toBeInTheDocument();
      }, { timeout: 500 });
    });
  });

  describe('Sorting', () => {
    it('default sort is by aantal descending', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      await waitFor(() => {
        expect(screen.getByText('4 guests found')).toBeInTheDocument();
      });

      // First data row should be Charlie (8) since default sort is aantal desc
      const rows = document.querySelectorAll('tbody tr');
      // The first row in the main table should contain "Charlie Brown" (highest count)
      const firstRowText = rows[0]?.textContent || '';
      expect(firstRowText).toContain('Charlie Brown');
      expect(firstRowText).toContain('8');
    });

    it('clicking sort on guest name column triggers sort', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      await waitFor(() => {
        expect(screen.getByText('4 guests found')).toBeInTheDocument();
      });

      // Click the "Sort by Guest Name" button
      const sortButton = screen.getByLabelText('Sort by Guest Name');
      await act(async () => {
        fireEvent.click(sortButton);
      });

      // After sorting by guestName asc, Alice should be first
      const rows = document.querySelectorAll('tbody tr');
      const firstRowText = rows[0]?.textContent || '';
      expect(firstRowText).toContain('Alice Johnson');
    });
  });

  describe('Preservation — Row-Click Expand/Collapse', () => {
    it('clicking a guest row fetches and displays bookings', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      await waitFor(() => {
        expect(screen.getByText('4 guests found')).toBeInTheDocument();
      });

      // Click on Alice's row (first row after sort by aantal desc is Charlie)
      // Find the row containing "Alice Johnson" and click it
      const aliceRow = screen.getByText('Alice Johnson').closest('tr');
      expect(aliceRow).not.toBeNull();

      await act(async () => {
        fireEvent.click(aliceRow!);
      });

      // Should fetch guest bookings
      await waitFor(() => {
        expect(authenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('bnb-guest-bookings')
        );
      });

      // Should display booking details
      await waitFor(() => {
        expect(screen.getByText(/Bookings for Alice Johnson/)).toBeInTheDocument();
      });
    });

    it('clicking the same guest row collapses bookings', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      await waitFor(() => {
        expect(screen.getByText('4 guests found')).toBeInTheDocument();
      });

      const aliceRow = screen.getByText('Alice Johnson').closest('tr');

      // Expand
      await act(async () => {
        fireEvent.click(aliceRow!);
      });

      await waitFor(() => {
        expect(screen.getByText(/Bookings for Alice Johnson/)).toBeInTheDocument();
      });

      // Collapse
      await act(async () => {
        fireEvent.click(aliceRow!);
      });

      await waitFor(() => {
        expect(screen.queryByText(/Bookings for Alice Johnson/)).not.toBeInTheDocument();
      });
    });

    it('displays booking summary totals when expanded', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      await waitFor(() => {
        expect(screen.getByText('4 guests found')).toBeInTheDocument();
      });

      const aliceRow = screen.getByText('Alice Johnson').closest('tr');

      await act(async () => {
        fireEvent.click(aliceRow!);
      });

      // Should show summary: 2 bookings | 7 nights | €1.050,00
      await waitFor(() => {
        expect(screen.getByText(/2 bookings/)).toBeInTheDocument();
      });
    });
  });

  describe('Preservation — API Fetch on Mount', () => {
    it('fetches returning guests data on mount', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      expect(authenticatedGet).toHaveBeenCalledWith(
        expect.stringContaining('bnb-returning-guests')
      );
    });

    it('refresh button re-fetches data', async () => {
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      await waitFor(() => {
        expect(screen.getByText('4 guests found')).toBeInTheDocument();
      });

      const refreshButton = screen.getByText('Refresh Data');

      await act(async () => {
        fireEvent.click(refreshButton);
      });

      // Should have been called twice: once on mount, once on refresh
      expect(authenticatedGet).toHaveBeenCalledTimes(2);
    });
  });

  describe('Edge Cases', () => {
    it('shows instructions when no guests loaded', async () => {
      (authenticatedGet as any).mockImplementation(() =>
        mockFetchResponse({ success: true, data: [] })
      );

      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      await waitFor(() => {
        expect(screen.getByText(/Instructions/)).toBeInTheDocument();
      });
    });

    it('handles API error gracefully', async () => {
      (authenticatedGet as any).mockImplementation(() =>
        Promise.reject(new Error('Network error'))
      );

      // Should not throw
      await act(async () => {
        render(<BnbReturningGuestsReport />);
      });

      // Should show 0 guests (empty state)
      await waitFor(() => {
        expect(screen.getByText('0 guests found')).toBeInTheDocument();
      });
    });
  });
});

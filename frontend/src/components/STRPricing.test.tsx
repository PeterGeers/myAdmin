import React from 'react';
import { render, screen, fireEvent, waitFor } from '@/test-utils';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import STRPricing from './STRPricing';

// Mock the API service
vi.mock('../services/apiService', () => ({
  authenticatedGet: vi.fn(),
  authenticatedPost: vi.fn(),
}));

// Mock useTypedTranslation to return keys as-is
vi.mock('../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, params?: any) => {
      if (params?.count !== undefined) return `${key} (${params.count})`;
      return key;
    },
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}));

// Mock Recharts components
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
  LineChart: ({ children }: any) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
}));

import { authenticatedGet, authenticatedPost } from '../services/apiService';

const mockAuthGet = authenticatedGet as ReturnType<typeof vi.fn>;
const mockAuthPost = authenticatedPost as ReturnType<typeof vi.fn>;

// Helper to create mock response
function mockFetchResponse(data: any) {
  return { json: () => Promise.resolve(data) };
}

// Sample test data
const mockListings = ['Green Studio', 'Red Studio', 'Child Friendly'];

const mockRecommendations = [
  {
    listing_name: 'Green Studio',
    price_date: '2025-03-15',
    recommended_price: 125.50,
    ai_recommended_adr: 130.00,
    ai_historical_adr: 110.00,
    ai_variance: 14.1,
    ai_reasoning: 'Higher demand expected',
    is_weekend: true,
    event_uplift: 10,
    event_name: 'Kings Day',
    last_year_adr: 105.00,
    base_rate: 100,
    historical_mult: 1.1,
    occupancy_mult: 1.05,
    pace_mult: 1.02,
    event_mult: 1.1,
    ai_correction: 0.98,
    btw_adjustment: 1.09,
  },
  {
    listing_name: 'Red Studio',
    price_date: '2025-03-15',
    recommended_price: 95.00,
    ai_recommended_adr: 100.00,
    ai_historical_adr: 90.00,
    ai_variance: -5.3,
    ai_reasoning: 'Low season',
    is_weekend: false,
    event_uplift: 0,
    event_name: '',
    last_year_adr: 85.00,
    base_rate: 80,
    historical_mult: 1.05,
    occupancy_mult: 0.98,
    pace_mult: 1.0,
    event_mult: 1.0,
    ai_correction: 1.01,
    btw_adjustment: 1.09,
  },
];

const mockMultipliers = [
  {
    listing_name: 'Green Studio',
    avg_base_rate: 100,
    avg_historical_mult: 1.1,
    avg_occupancy_mult: 1.05,
    avg_pace_mult: 1.02,
    avg_event_mult: 1.1,
    avg_ai_correction: 0.98,
    record_count: 420,
  },
  {
    listing_name: 'Red Studio',
    avg_base_rate: 80,
    avg_historical_mult: 1.05,
    avg_occupancy_mult: 0.98,
    avg_pace_mult: 1.0,
    avg_event_mult: 1.0,
    avg_ai_correction: 1.01,
    record_count: 380,
  },
];

describe('STRPricing Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: all API calls return empty/success
    mockAuthGet.mockImplementation((url: string) => {
      if (url.includes('/listings')) {
        return Promise.resolve(mockFetchResponse({ success: true, listings: mockListings }));
      }
      if (url.includes('/recommendations')) {
        return Promise.resolve(mockFetchResponse({ success: true, recommendations: mockRecommendations }));
      }
      if (url.includes('/multipliers')) {
        return Promise.resolve(mockFetchResponse({ success: true, multipliers: mockMultipliers }));
      }
      return Promise.resolve(mockFetchResponse({ success: true }));
    });
  });

  describe('Initial Rendering', () => {
    it('renders the pricing title', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.title')).toBeInTheDocument();
      });
    });

    it('renders the listing selector', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.allListings')).toBeInTheDocument();
      });
    });

    it('renders the generate pricing button', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.generatePricing')).toBeInTheDocument();
      });
    });

    it('renders multipliers summary section heading', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.multipliersSummary.title')).toBeInTheDocument();
      });
    });

    it('renders trend chart section heading', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.trendChart.title')).toBeInTheDocument();
      });
    });

    it('renders monthly multipliers section heading', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.monthlyMultipliers.title')).toBeInTheDocument();
      });
    });

    it('renders quarterly summary section heading', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.quarterlySummary.title')).toBeInTheDocument();
      });
    });

    it('renders recommendations section heading', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.recommendations.title')).toBeInTheDocument();
      });
    });
  });

  describe('Data Loading', () => {
    it('calls listings API on mount', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(mockAuthGet).toHaveBeenCalledWith('/api/pricing/listings');
      });
    });

    it('calls recommendations API on mount', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(mockAuthGet).toHaveBeenCalledWith('/api/pricing/recommendations');
      });
    });

    it('calls multipliers API on mount', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(mockAuthGet).toHaveBeenCalledWith('/api/pricing/multipliers');
      });
    });

    it('displays listings in the selector after loading', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'Green Studio' })).toBeInTheDocument();
        expect(screen.getByRole('option', { name: 'Red Studio' })).toBeInTheDocument();
        expect(screen.getByRole('option', { name: 'Child Friendly' })).toBeInTheDocument();
      });
    });

    it('displays multiplier data in the summary table', async () => {
      render(<STRPricing />);
      // Component auto-selects first listing (Green Studio), 
      // so only Green Studio multiplier row shows
      await waitFor(() => {
        // Green Studio is shown both in the multiplier summary and other places
        const cells = screen.getAllByRole('cell');
        const greenStudioCell = cells.find(cell => cell.textContent === 'Green Studio');
        expect(greenStudioCell).toBeDefined();
      });
    });

    it('shows no data message when multipliers are empty', async () => {
      mockAuthGet.mockImplementation((url: string) => {
        if (url.includes('/listings')) {
          return Promise.resolve(mockFetchResponse({ success: true, listings: [] }));
        }
        if (url.includes('/recommendations')) {
          return Promise.resolve(mockFetchResponse({ success: true, recommendations: [] }));
        }
        if (url.includes('/multipliers')) {
          return Promise.resolve(mockFetchResponse({ success: true, multipliers: [] }));
        }
        return Promise.resolve(mockFetchResponse({ success: true }));
      });

      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.multipliersSummary.noData')).toBeInTheDocument();
      });
    });
  });

  describe('Listing Selection', () => {
    it('changes selected listing when dropdown value changes', async () => {
      render(<STRPricing />);

      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'Red Studio' })).toBeInTheDocument();
      });

      const select = screen.getAllByRole('combobox')[0];
      fireEvent.change(select, { target: { value: 'Red Studio' } });

      // After selecting Red Studio, the recommendations title should reflect it
      await waitFor(() => {
        expect(select).toHaveValue('Red Studio');
      });
    });
  });

  describe('Generate Pricing', () => {
    it('calls generate API when button is clicked', async () => {
      mockAuthPost.mockResolvedValue(
        mockFetchResponse({
          success: true,
          result: { daily_prices_count: 420 },
        })
      );

      render(<STRPricing />);

      await waitFor(() => {
        expect(screen.getByText('pricing.generatePricing')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('pricing.generatePricing'));

      await waitFor(() => {
        expect(mockAuthPost).toHaveBeenCalledWith('/api/pricing/generate', {
          months: 14,
          listing: expect.any(String),
        });
      });
    });

    it('reloads data after successful generation', async () => {
      mockAuthPost.mockResolvedValue(
        mockFetchResponse({
          success: true,
          result: { daily_prices_count: 420 },
        })
      );

      render(<STRPricing />);

      await waitFor(() => {
        expect(screen.getByText('pricing.generatePricing')).toBeInTheDocument();
      });

      // Initial calls
      const initialCallCount = mockAuthGet.mock.calls.length;

      fireEvent.click(screen.getByText('pricing.generatePricing'));

      await waitFor(() => {
        // After generate, recommendations and multipliers should be re-fetched
        const newCalls = mockAuthGet.mock.calls.slice(initialCallCount);
        const recommendationCalls = newCalls.filter((c: string[]) => c[0].includes('/recommendations'));
        const multiplierCalls = newCalls.filter((c: string[]) => c[0].includes('/multipliers'));
        expect(recommendationCalls.length).toBeGreaterThan(0);
        expect(multiplierCalls.length).toBeGreaterThan(0);
      });
    });

    it('shows loading text while generating', async () => {
      // Make the post hang so we can see the loading state
      mockAuthPost.mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockFetchResponse({
          success: true,
          result: { daily_prices_count: 100 },
        })), 500))
      );

      render(<STRPricing />);

      await waitFor(() => {
        expect(screen.getByText('pricing.generatePricing')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('pricing.generatePricing'));

      // Button should show loading text
      await waitFor(() => {
        expect(screen.getByText('pricing.generating')).toBeInTheDocument();
      });
    });
  });

  describe('Recommendations Table', () => {
    it('displays pricing recommendations with correct values', async () => {
      render(<STRPricing />);
      // Component auto-selects first listing (Green Studio), so only that recommendation shows
      // €125.50 is split across text nodes as "€" + "125.50" inside a <p>
      await waitFor(() => {
        const cells = screen.getAllByRole('cell');
        const priceCell = cells.find(cell => cell.textContent?.includes('125.50'));
        expect(priceCell).toBeDefined();
      });
    });

    it('shows weekend badge for weekend dates', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        // Weekend badge and weekday badge - one in header, one as badge value
        const weekendBadges = screen.getAllByText('pricing.recommendations.weekend');
        expect(weekendBadges.length).toBeGreaterThan(1);
      });
    });

    it('shows event name badge when event exists', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('Kings Day')).toBeInTheDocument();
      });
    });

    it('shows positive variance formatting', async () => {
      render(<STRPricing />);
      // Green Studio has +14.1% variance
      await waitFor(() => {
        const cells = screen.getAllByRole('cell');
        const varianceCell = cells.find(cell => cell.textContent?.includes('+') && cell.textContent?.includes('14.1'));
        expect(varianceCell).toBeDefined();
      });
    });

    it('filters recommendations by selected listing', async () => {
      render(<STRPricing />);
      // Component auto-selects Green Studio, so only Green Studio recommendation shows
      await waitFor(() => {
        expect(screen.getByText('Higher demand expected')).toBeInTheDocument();
      });
      // "Low season" (Red Studio) should not be visible when Green Studio is selected
      expect(screen.queryByText('Low season')).not.toBeInTheDocument();
    });

    it('displays AI reasoning text', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('Higher demand expected')).toBeInTheDocument();
      });
    });

    it('shows loading spinner while loading recommendations', async () => {
      // Make recommendations hang
      mockAuthGet.mockImplementation((url: string) => {
        if (url.includes('/listings')) {
          return Promise.resolve(mockFetchResponse({ success: true, listings: mockListings }));
        }
        if (url.includes('/recommendations')) {
          return new Promise(() => {}); // never resolves
        }
        if (url.includes('/multipliers')) {
          return Promise.resolve(mockFetchResponse({ success: true, multipliers: mockMultipliers }));
        }
        return Promise.resolve(mockFetchResponse({ success: true }));
      });

      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.recommendations.loading')).toBeInTheDocument();
      });
    });

    it('shows info alert when no recommendations are available', async () => {
      mockAuthGet.mockImplementation((url: string) => {
        if (url.includes('/listings')) {
          return Promise.resolve(mockFetchResponse({ success: true, listings: mockListings }));
        }
        if (url.includes('/recommendations')) {
          return Promise.resolve(mockFetchResponse({ success: true, recommendations: [] }));
        }
        if (url.includes('/multipliers')) {
          return Promise.resolve(mockFetchResponse({ success: true, multipliers: mockMultipliers }));
        }
        return Promise.resolve(mockFetchResponse({ success: true }));
      });

      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.recommendations.noData')).toBeInTheDocument();
      });
    });
  });

  describe('Trend Chart', () => {
    it('renders the chart when data is available', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByTestId('line-chart')).toBeInTheDocument();
      });
    });

    it('shows no data message when chart data is empty', async () => {
      mockAuthGet.mockImplementation((url: string) => {
        if (url.includes('/listings')) {
          return Promise.resolve(mockFetchResponse({ success: true, listings: mockListings }));
        }
        if (url.includes('/recommendations')) {
          return Promise.resolve(mockFetchResponse({ success: true, recommendations: [] }));
        }
        if (url.includes('/multipliers')) {
          return Promise.resolve(mockFetchResponse({ success: true, multipliers: [] }));
        }
        return Promise.resolve(mockFetchResponse({ success: true }));
      });

      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.trendChart.noData')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('handles listings API failure gracefully', async () => {
      mockAuthGet.mockImplementation((url: string) => {
        if (url.includes('/listings')) {
          return Promise.reject(new Error('Network error'));
        }
        if (url.includes('/recommendations')) {
          return Promise.resolve(mockFetchResponse({ success: true, recommendations: [] }));
        }
        if (url.includes('/multipliers')) {
          return Promise.resolve(mockFetchResponse({ success: true, multipliers: [] }));
        }
        return Promise.resolve(mockFetchResponse({ success: true }));
      });

      // Should render without crashing
      render(<STRPricing />);
      await waitFor(() => {
        expect(screen.getByText('pricing.title')).toBeInTheDocument();
      });
    });

    it('handles generate API failure gracefully', async () => {
      mockAuthPost.mockRejectedValue(new Error('Server error'));

      render(<STRPricing />);

      await waitFor(() => {
        expect(screen.getByText('pricing.generatePricing')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('pricing.generatePricing'));

      // Should not crash - button should be re-enabled after error
      await waitFor(() => {
        expect(screen.getByText('pricing.generatePricing')).toBeInTheDocument();
      });
    });
  });

  describe('Multipliers Table', () => {
    it('displays multiplier values correctly formatted', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        // Check that record counts appear (these are plain numbers in their own td)
        expect(screen.getByText('420')).toBeInTheDocument();
      });
    });

    it('displays listing names in multiplier summary', async () => {
      render(<STRPricing />);
      await waitFor(() => {
        // Both listings appear in the multiplier summary table (not filtered by selection)
        const greenStudioCells = screen.getAllByText('Green Studio');
        expect(greenStudioCells.length).toBeGreaterThan(0);
      });
    });
  });
});

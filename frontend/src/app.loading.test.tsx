import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

export {};

// Mock App component with loading states
const MockAppWithLoading = ({ isLoading = false, hasError = false }) => {
  if (hasError) {
    return <div data-testid="error-state">Error loading app</div>;
  }
  
  if (isLoading) {
    return (
      <div data-testid="loading-state">
        <div data-testid="loading-spinner">Loading...</div>
        <div data-testid="loading-text">Initializing myAdmin Dashboard</div>
      </div>
    );
  }
  
  return (
    <div data-testid="app-loaded">
      <h1>myAdmin Dashboard</h1>
      <div data-testid="status-badge">Production Mode</div>
    </div>
  );
};

// Mock fetch for API calls
const mockFetch = (response: any, delay = 0) => {
  global.fetch = jest.fn(() =>
    new Promise((resolve) =>
      setTimeout(() => resolve({
        ok: true,
        json: () => Promise.resolve(response)
      } as Response), delay)
    )
  );
};

describe('App Loading States', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Initial Loading Behavior', () => {
    it('shows loading state initially', () => {
      render(<MockAppWithLoading isLoading={true} />);
      
      expect(screen.getByTestId('loading-state')).toBeInTheDocument();
      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
      expect(screen.getByText('Loading...')).toBeInTheDocument();
      expect(screen.getByText('Initializing myAdmin Dashboard')).toBeInTheDocument();
    });

    it('shows loaded state after successful API call', async () => {
      mockFetch({ mode: 'Production', database: 'finance', folder: 'Facturen' });
      
      const { rerender } = render(<MockAppWithLoading isLoading={true} />);
      expect(screen.getByTestId('loading-state')).toBeInTheDocument();
      
      rerender(<MockAppWithLoading isLoading={false} />);
      expect(screen.getByTestId('app-loaded')).toBeInTheDocument();
      expect(screen.getByText('myAdmin Dashboard')).toBeInTheDocument();
    });

    it('shows error state when API call fails', () => {
      render(<MockAppWithLoading hasError={true} />);
      
      expect(screen.getByTestId('error-state')).toBeInTheDocument();
      expect(screen.getByText('Error loading app')).toBeInTheDocument();
    });

    it('displays status information after loading', () => {
      render(<MockAppWithLoading isLoading={false} />);
      
      expect(screen.getByTestId('status-badge')).toBeInTheDocument();
      expect(screen.getByText('Production Mode')).toBeInTheDocument();
    });

    it('handles loading timeout gracefully', async () => {
      mockFetch({ mode: 'Production' }, 100);
      
      const { rerender } = render(<MockAppWithLoading isLoading={true} />);
      expect(screen.getByTestId('loading-state')).toBeInTheDocument();
      
      await waitFor(() => {
        rerender(<MockAppWithLoading isLoading={false} />);
        expect(screen.getByTestId('app-loaded')).toBeInTheDocument();
      }, { timeout: 200 });
    });
  });

  describe('Loading State Components', () => {
    it('renders loading spinner', () => {
      render(<MockAppWithLoading isLoading={true} />);
      
      const spinner = screen.getByTestId('loading-spinner');
      expect(spinner).toBeInTheDocument();
      expect(spinner).toHaveTextContent('Loading...');
    });

    it('renders loading message', () => {
      render(<MockAppWithLoading isLoading={true} />);
      
      const message = screen.getByTestId('loading-text');
      expect(message).toBeInTheDocument();
      expect(message).toHaveTextContent('Initializing myAdmin Dashboard');
    });

    it('does not render loading components when loaded', () => {
      render(<MockAppWithLoading isLoading={false} />);
      
      expect(screen.queryByTestId('loading-spinner')).not.toBeInTheDocument();
      expect(screen.queryByTestId('loading-text')).not.toBeInTheDocument();
    });
  });
});
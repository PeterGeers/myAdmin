import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

export {};

// Mock ErrorBoundary component
class MockErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error?: Error }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div data-testid="error-boundary">
          <h1>⚠️ Something went wrong</h1>
          <p>An unexpected error occurred</p>
          <button 
            onClick={() => this.setState({ hasError: false, error: undefined })}
          >
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

const ThrowError = ({ shouldThrow }: { shouldThrow: boolean }) => {
  if (shouldThrow) {
    throw new Error('Test error');
  }
  return <div data-testid="working-component">Working component</div>;
};

describe('App Error Boundaries', () => {
  beforeEach(() => {
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('ErrorBoundary Component', () => {
    it('renders children when no error occurs', () => {
      render(
        <MockErrorBoundary>
          <ThrowError shouldThrow={false} />
        </MockErrorBoundary>
      );

      expect(screen.getByTestId('working-component')).toBeInTheDocument();
      expect(screen.queryByTestId('error-boundary')).not.toBeInTheDocument();
    });

    it('catches and displays error when child component throws', () => {
      render(
        <MockErrorBoundary>
          <ThrowError shouldThrow={true} />
        </MockErrorBoundary>
      );

      expect(screen.getByTestId('error-boundary')).toBeInTheDocument();
      expect(screen.getByText('⚠️ Something went wrong')).toBeInTheDocument();
      expect(screen.getByText('An unexpected error occurred')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Try Again' })).toBeInTheDocument();
    });

    it('displays Try Again button in error state', () => {
      render(
        <MockErrorBoundary>
          <ThrowError shouldThrow={true} />
        </MockErrorBoundary>
      );

      const tryAgainButton = screen.getByRole('button', { name: 'Try Again' });
      expect(tryAgainButton).toBeInTheDocument();
    });

    it('logs error to console when error is caught', () => {
      const consoleSpy = jest.spyOn(console, 'error');

      render(
        <MockErrorBoundary>
          <ThrowError shouldThrow={true} />
        </MockErrorBoundary>
      );

      expect(consoleSpy).toHaveBeenCalledWith(
        'Error caught by boundary:',
        expect.any(Error),
        expect.any(Object)
      );
    });

    it('handles multiple error scenarios', () => {
      const { rerender } = render(
        <MockErrorBoundary>
          <ThrowError shouldThrow={false} />
        </MockErrorBoundary>
      );

      expect(screen.getByTestId('working-component')).toBeInTheDocument();

      rerender(
        <MockErrorBoundary>
          <ThrowError shouldThrow={true} />
        </MockErrorBoundary>
      );

      expect(screen.getByTestId('error-boundary')).toBeInTheDocument();
    });
  });
});
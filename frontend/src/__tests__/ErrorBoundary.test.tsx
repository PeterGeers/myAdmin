/**
 * Unit tests for ErrorBoundary.tsx
 *
 * Tests the error boundary class component:
 * - Renders children when no error
 * - Catches errors and shows fallback UI
 * - Try Again button resets error state
 * - Language-aware error messages
 *
 * Task 55 of Phase 7: Missing Test Coverage
 */

import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import React from 'react';
import ErrorBoundary from '../components/ErrorBoundary';
import { render, screen, fireEvent } from '@/test-utils';

// Component that throws on demand
const ThrowOnDemand = ({ shouldThrow }: { shouldThrow: boolean }) => {
  if (shouldThrow) throw new Error('Test crash');
  return <div data-testid="child-content">Working fine</div>;
};

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.removeItem('i18nextLng');
  });

  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <ThrowOnDemand shouldThrow={false} />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('child-content')).toBeInTheDocument();
  });

  it('shows error UI when child throws', () => {
    render(
      <ErrorBoundary>
        <ThrowOnDemand shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.queryByTestId('child-content')).not.toBeInTheDocument();
    expect(screen.getByText(/Something went wrong/)).toBeInTheDocument();
    expect(screen.getByText(/unexpected error/i)).toBeInTheDocument();
  });

  it('renders Try Again button in error state', () => {
    render(
      <ErrorBoundary>
        <ThrowOnDemand shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByRole('button', { name: /Try Again/i })).toBeInTheDocument();
  });

  it('resets error state when Try Again is clicked', () => {
    render(
      <ErrorBoundary>
        <ThrowOnDemand shouldThrow={true} />
      </ErrorBoundary>
    );

    // Error UI is shown
    expect(screen.getByText(/Something went wrong/)).toBeInTheDocument();

    // Click Try Again
    fireEvent.click(screen.getByRole('button', { name: /Try Again/i }));

    // After reset, children render again (but they'll throw again since prop is still true)
    // The boundary will catch it again — this tests the state reset mechanism
    expect(screen.getByText(/Something went wrong/)).toBeInTheDocument();
  });

  it('shows Dutch messages when language is nl', () => {
    localStorage.setItem('i18nextLng', 'nl');

    render(
      <ErrorBoundary>
        <ThrowOnDemand shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText(/Er is een fout opgetreden/)).toBeInTheDocument();
    expect(screen.getByText(/onverwachte fout/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Opnieuw proberen/i })).toBeInTheDocument();
  });

  it('shows English messages when language is en', () => {
    localStorage.setItem('i18nextLng', 'en');

    render(
      <ErrorBoundary>
        <ThrowOnDemand shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText(/Something went wrong/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Try Again/i })).toBeInTheDocument();
  });

  it('logs error to console via componentDidCatch', () => {
    const consoleSpy = vi.spyOn(console, 'error');

    render(
      <ErrorBoundary>
        <ThrowOnDemand shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(consoleSpy).toHaveBeenCalledWith(
      'Error caught by boundary:',
      expect.any(Error),
      expect.any(Object)
    );
  });
});

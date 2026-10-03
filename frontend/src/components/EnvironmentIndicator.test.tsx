/**
 * Unit tests for EnvironmentIndicator (Req 5.1-5.5).
 *
 * The component reads APP_ENV / RESOLVED, which are evaluated at MODULE LOAD in
 * src/config/appEnv.ts (fail-fast resolver). So — exactly like appEnv.test.ts — each
 * case stubs VITE_APP_ENV, vi.resetModules(), then dynamically imports a fresh copy of
 * the component. This also proves the indicator derives from the resolver (the injected
 * APP_ENV), never from the hostname or any incidental signal (Req 5.3).
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, within } from '@/test-utils';
import {
  TEST_FRONTEND_CONFIG,
  PROD_FRONTEND_CONFIG,
} from '../config/environmentDefinition';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

/** Load a fresh copy of the component built under a specific VITE_APP_ENV value. */
async function loadIndicatorWith(raw: string): Promise<React.FC<{ variant?: 'compact' | 'detailed' }>> {
  vi.resetModules();
  vi.stubEnv('VITE_APP_ENV', raw);
  const mod = await import('./EnvironmentIndicator');
  return mod.EnvironmentIndicator;
}

describe('EnvironmentIndicator — environment label (Req 5.1)', () => {
  it("shows a 'TEST' badge when APP_ENV='test'", async () => {
    const Indicator = await loadIndicatorWith('test');
    render(<Indicator />);
    const badge = screen.getByTestId('environment-indicator-badge');
    expect(badge).toHaveTextContent('TEST');
  });

  it("shows a 'PROD' badge when APP_ENV='production'", async () => {
    const Indicator = await loadIndicatorWith('production');
    render(<Indicator />);
    const badge = screen.getByTestId('environment-indicator-badge');
    expect(badge).toHaveTextContent('PROD');
  });
});

describe('EnvironmentIndicator — derives from the resolver, not the hostname (Req 5.3)', () => {
  it('reflects the injected APP_ENV even though the test host is "localhost"', async () => {
    // window.location.hostname is 'localhost' under jsdom; a hostname-based indicator
    // would wrongly show TEST here. The resolver-driven one must honour APP_ENV.
    expect(window.location.hostname).toBe('localhost');
    const Indicator = await loadIndicatorWith('production');
    render(<Indicator />);
    expect(screen.getByTestId('environment-indicator-badge')).toHaveTextContent('PROD');
  });
});

describe('EnvironmentIndicator — accessible, not color-only (Req 5.5)', () => {
  it('exposes the environment via an accessible role + aria-label (TEST)', async () => {
    const Indicator = await loadIndicatorWith('test');
    render(<Indicator />);
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-label', expect.stringContaining('TEST'));
    // The text "TEST" itself conveys the environment — distinction is not color-only.
    expect(within(status).getByText('TEST')).toBeInTheDocument();
  });

  it('renders TEST and PROD with visually distinct badge styling (Req 5.5)', async () => {
    // TEST stands out: solid orange. PROD is subtle/neutral. The distinction is encoded
    // in stable data-* hooks (color-independent) so the two environments can never share
    // an identical badge appearance.
    const TestIndicator = await loadIndicatorWith('test');
    const { unmount } = render(<TestIndicator />);
    const testBadge = screen.getByTestId('environment-indicator-badge');
    expect(testBadge).toHaveAttribute('data-variant', 'solid');
    const testVariant = testBadge.getAttribute('data-variant');
    unmount();

    const ProdIndicator = await loadIndicatorWith('production');
    render(<ProdIndicator />);
    const prodBadge = screen.getByTestId('environment-indicator-badge');
    expect(prodBadge).toHaveAttribute('data-variant', 'subtle');
    // The two environments must not render an identical badge appearance.
    expect(prodBadge.getAttribute('data-variant')).not.toBe(testVariant);
  });
});

describe('EnvironmentIndicator — detailed variant (Req 5.2, 5.4)', () => {
  it('shows the active pool/identity label while authenticated (TEST)', async () => {
    const Indicator = await loadIndicatorWith('test');
    render(<Indicator variant="detailed" />);
    expect(screen.getByTestId('environment-indicator-pool')).toHaveTextContent(
      TEST_FRONTEND_CONFIG.cognito.poolLabel,
    );
  });

  it('shows the active pool/identity label while authenticated (PROD)', async () => {
    const Indicator = await loadIndicatorWith('production');
    render(<Indicator variant="detailed" />);
    expect(screen.getByTestId('environment-indicator-pool')).toHaveTextContent(
      PROD_FRONTEND_CONFIG.cognito.poolLabel,
    );
  });

  it('falls back to the SAM stack label when the API URL is a placeholder (Req 5.4)', async () => {
    // Both configs currently carry PLACEHOLDER SAM API URLs, so the indicator shows the
    // observable stack-environment label instead of a fake endpoint.
    const Indicator = await loadIndicatorWith('test');
    render(<Indicator variant="detailed" />);
    expect(screen.getByTestId('environment-indicator-sam')).toHaveTextContent(
      TEST_FRONTEND_CONFIG.sam.stackName,
    );
  });

  it('compact variant omits the pool/SAM detail (login-screen use, Req 5.1)', async () => {
    const Indicator = await loadIndicatorWith('test');
    render(<Indicator variant="compact" />);
    expect(screen.getByTestId('environment-indicator-badge')).toHaveTextContent('TEST');
    expect(screen.queryByTestId('environment-indicator-pool')).not.toBeInTheDocument();
    expect(screen.queryByTestId('environment-indicator-sam')).not.toBeInTheDocument();
  });
});

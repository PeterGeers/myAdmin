/**
 * Component tests for the Member Analytics non-happy-state presentation (task 3.4, R1.4).
 *
 * Covers the two notice kinds the shared `AnalyticsStateNotice` renders — the
 * NEUTRAL empty state and the WARNING degradation state — asserting they render
 * DISTINCTLY (R1.4) and accessibly (R6.6, colour is not the sole signal: each
 * kind pairs a distinct icon + ARIA role + test id with its bilingual text), and
 * covers `PivotViewsArea` surfacing the "no analytics config" degradation reason
 * when the tenant has authored no analytics config.
 */
import { vi, describe, it, expect } from 'vitest';
import React from 'react';

// Echo i18n keys so assertions are locale-independent.
vi.mock('../../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (key: string) => key }),
}));

import { render, screen } from '@/test-utils';
import AnalyticsStateNotice from './AnalyticsStateNotice';
import PivotViewsArea from './PivotViewsArea';
import type { Member, MemberRow, FieldConfig } from '../../../../types/members';

describe('AnalyticsStateNotice (task 3.4, R1.4)', () => {
  it('renders the NEUTRAL empty state distinctly (status role, info icon, empty testid)', () => {
    render(<AnalyticsStateNotice kind="empty" message="analytics.states.empty" />);

    const notice = screen.getByTestId('analytics-empty');
    expect(notice).toBeInTheDocument();
    // Neutral empty is a polite status, NOT an alert — distinct from degradation.
    expect(notice).toHaveAttribute('role', 'status');
    expect(notice).toHaveAttribute('data-notice-kind', 'empty');
    expect(screen.getByText('analytics.states.empty')).toBeInTheDocument();
    // The non-colour signal: an info icon accompanies the text (R6.6).
    expect(screen.getByTestId('InfoOutlineIcon')).toBeInTheDocument();
  });

  it('renders the WARNING degradation state distinctly (alert role, warning icon, degradation testid)', () => {
    render(
      <AnalyticsStateNotice kind="degradation" message="analytics.degradation.noConfig" />,
    );

    const notice = screen.getByTestId('analytics-degradation');
    expect(notice).toBeInTheDocument();
    // Degradation is an assertive alert — distinct role from the empty status.
    expect(notice).toHaveAttribute('role', 'alert');
    expect(notice).toHaveAttribute('data-notice-kind', 'degradation');
    expect(screen.getByText('analytics.degradation.noConfig')).toBeInTheDocument();
    // The non-colour signal: a warning icon accompanies the text (R6.6).
    expect(screen.getByTestId('WarningTwoIcon')).toBeInTheDocument();
  });

  it('the two kinds are mutually distinct (different icon + role + testid)', () => {
    const { unmount } = render(
      <AnalyticsStateNotice kind="empty" message="analytics.states.empty" />,
    );
    expect(screen.getByTestId('analytics-empty')).toHaveAttribute('role', 'status');
    expect(screen.queryByTestId('analytics-degradation')).not.toBeInTheDocument();
    unmount();

    render(<AnalyticsStateNotice kind="degradation" message="analytics.degradation.noConfig" />);
    expect(screen.getByTestId('analytics-degradation')).toHaveAttribute('role', 'alert');
    expect(screen.queryByTestId('analytics-empty')).not.toBeInTheDocument();
  });
});

describe('PivotViewsArea — no-analytics-config degradation (task 3.4, R1.4)', () => {
  const baseProps = {
    processedData: [{ member_id: 'a' }] as unknown as MemberRow[],
    members: [{ member_id: 'a' }] as unknown as Member[],
    fieldConfig: { fields: [] } as unknown as FieldConfig,
    language: 'en',
    capabilities: { canExport: true },
  };

  it('shows the degradation reason when the tenant has NO analytics config', () => {
    render(<PivotViewsArea {...baseProps} hasAnalyticsConfig={false} />);

    // The config-dependent sets degrade with a bilingual reason (R1.4 / R9.5) —
    // a WARNING, not an error, and not an empty state.
    const notice = screen.getByTestId('analytics-degradation');
    expect(notice).toBeInTheDocument();
    expect(notice).toHaveAttribute('role', 'alert');
    expect(screen.getByText('analytics.degradation.noConfig')).toBeInTheDocument();
    // The area itself still renders (it does not error/crash).
    expect(screen.getByTestId('analytics-area-pivotViews')).toBeInTheDocument();
  });

  it('does NOT show the degradation reason when analytics config is present', () => {
    render(<PivotViewsArea {...baseProps} hasAnalyticsConfig={true} />);

    expect(screen.queryByTestId('analytics-degradation')).not.toBeInTheDocument();
    expect(screen.getByTestId('analytics-area-pivotViews')).toBeInTheDocument();
  });
});

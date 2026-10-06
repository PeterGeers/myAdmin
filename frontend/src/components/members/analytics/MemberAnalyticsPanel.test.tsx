/**
 * Component tests for MemberAnalyticsPanel (the Member Analytics view switch).
 *
 * Verifies task 3.3 (R1.3, R1.6, R6.6):
 *   - the switch is a keyboard-navigable ARIA tablist with three tabs
 *     (Overview / Distributions / Pivot Views);
 *   - Overview is the DEFAULT landing area;
 *   - ONE area is visible at a time, and only the ACTIVE area is mounted — an
 *     area that has never been selected is never mounted (lazy mounting, R1.6);
 *   - selecting a tab (click OR keyboard arrow/Home/End) mounts that area then;
 *   - the prop bundle (processedData, members, fieldConfig, language,
 *     capabilities) is plumbed through to the active area;
 *   - the panel is exported from the analytics barrel.
 *
 * The three lazy areas are mocked with lightweight synchronous components that
 * record each mount, so we can assert on mount order / lazy behavior without the
 * real area chunks (mirrors the project's existing lazy-component mock pattern).
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';

// Record every area mount so we can prove lazy mounting (only the active area
// ever mounts). Each mock also echoes the props it received for prop-plumbing
// assertions.
const mounts: string[] = [];

function makeAreaMock(name: string) {
  return {
    default: function MockArea(props: any) {
      React.useEffect(() => {
        mounts.push(name);
      }, []);
      return (
        <div
          data-testid={`mock-area-${name}`}
          data-row-count={props.processedData?.length ?? 'none'}
          data-member-count={props.members?.length ?? 'none'}
          data-language={props.language ?? 'none'}
          data-can-export={String(props.capabilities?.canExport)}
          data-has-field-config={String(props.fieldConfig != null)}
          data-has-analytics-config={String(props.hasAnalyticsConfig)}
        >
          {name}
        </div>
      );
    },
  };
}

vi.mock('./areas/OverviewArea', () => makeAreaMock('overview'));
vi.mock('./areas/DistributionsArea', () => makeAreaMock('distributions'));
vi.mock('./areas/PivotViewsArea', () => makeAreaMock('pivotViews'));

// Echo i18n keys so assertions are locale-independent.
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (key: string) => key }),
}));

import { render, screen, fireEvent, waitFor } from '@/test-utils';
import MemberAnalyticsPanel from './MemberAnalyticsPanel';
import { MemberAnalyticsPanel as PanelFromBarrel } from './index';
import type { Member, MemberRow, FieldConfig } from '../../../types/members';

const members = [
  { member_id: 'a' },
  { member_id: 'b' },
  { member_id: 'c' },
] as unknown as Member[];

const processedData = [{ member_id: 'a' }, { member_id: 'b' }] as unknown as MemberRow[];

const fieldConfig = { fields: [] } as unknown as FieldConfig;

function renderPanel(overrides: Partial<React.ComponentProps<typeof MemberAnalyticsPanel>> = {}) {
  return render(
    <MemberAnalyticsPanel
      processedData={processedData}
      members={members}
      fieldConfig={fieldConfig}
      hasAnalyticsConfig={true}
      language="en"
      capabilities={{ canExport: true }}
      {...overrides}
    />
  );
}

beforeEach(() => {
  mounts.length = 0;
});

describe('MemberAnalyticsPanel (view switch)', () => {
  it('is exported from the analytics barrel', () => {
    expect(PanelFromBarrel).toBe(MemberAnalyticsPanel);
  });

  it('renders a tablist with the three analytics area tabs', async () => {
    renderPanel();
    const tablist = screen.getByRole('tablist');
    expect(tablist).toBeInTheDocument();
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map(tab => tab.textContent)).toEqual([
      'analytics.areas.overview',
      'analytics.areas.distributions',
      'analytics.areas.pivotViews',
    ]);
  });

  it('lands on Overview by default and does NOT mount the other areas (lazy)', async () => {
    renderPanel();

    await waitFor(() => {
      expect(screen.getByTestId('mock-area-overview')).toBeInTheDocument();
    });

    // Overview tab is selected and the sole tab-stop (roving tabindex).
    const overviewTab = screen.getByTestId('analytics-tab-overview');
    expect(overviewTab).toHaveAttribute('aria-selected', 'true');
    expect(overviewTab).toHaveAttribute('tabindex', '0');

    // The other two areas are NOT in the DOM and were never mounted (R1.6).
    expect(screen.queryByTestId('mock-area-distributions')).not.toBeInTheDocument();
    expect(screen.queryByTestId('mock-area-pivotViews')).not.toBeInTheDocument();
    expect(mounts).toEqual(['overview']);
  });

  it('plumbs the prop bundle through to the active area', async () => {
    renderPanel();
    const area = await screen.findByTestId('mock-area-overview');
    expect(area).toHaveAttribute('data-row-count', '2'); // processedData.length
    expect(area).toHaveAttribute('data-member-count', '3'); // members.length
    expect(area).toHaveAttribute('data-language', 'en');
    expect(area).toHaveAttribute('data-can-export', 'true');
    expect(area).toHaveAttribute('data-has-field-config', 'true');
    expect(area).toHaveAttribute('data-has-analytics-config', 'true');
  });

  it('plumbs the no-analytics-config degradation signal through to the area (R1.4)', async () => {
    renderPanel({ hasAnalyticsConfig: false });
    const area = await screen.findByTestId('mock-area-overview');
    // The "no analytics config" signal reaches the area unchanged, so the
    // config-dependent sets can degrade with a reason while the
    // fixed/calculated areas keep working (R1.4 / R9.5).
    expect(area).toHaveAttribute('data-has-analytics-config', 'false');
  });

  it('mounts a different area ONLY when it is selected (click)', async () => {
    renderPanel();
    await screen.findByTestId('mock-area-overview');
    expect(mounts).toEqual(['overview']);

    fireEvent.click(screen.getByTestId('analytics-tab-distributions'));

    await waitFor(() => {
      expect(screen.getByTestId('mock-area-distributions')).toBeInTheDocument();
    });
    // Overview is unmounted (one area visible at a time); Distributions now mounted.
    expect(screen.queryByTestId('mock-area-overview')).not.toBeInTheDocument();
    expect(mounts).toEqual(['overview', 'distributions']);
    // Pivot Views still never mounted.
    expect(screen.queryByTestId('mock-area-pivotViews')).not.toBeInTheDocument();
  });

  it('navigates the switch with the keyboard (ArrowRight / Home / End)', async () => {
    renderPanel();
    await screen.findByTestId('mock-area-overview');

    const overviewTab = screen.getByTestId('analytics-tab-overview');

    // ArrowRight: overview -> distributions.
    fireEvent.keyDown(overviewTab, { key: 'ArrowRight' });
    await waitFor(() => {
      expect(screen.getByTestId('analytics-tab-distributions')).toHaveAttribute(
        'aria-selected',
        'true'
      );
    });
    expect(screen.getByTestId('mock-area-distributions')).toBeInTheDocument();

    // End: jump to the last tab (pivotViews). Wait for its lazy area to actually
    // mount (the chunk resolves via Suspense) before moving on.
    fireEvent.keyDown(screen.getByTestId('analytics-tab-distributions'), { key: 'End' });
    await waitFor(() => {
      expect(screen.getByTestId('analytics-tab-pivotViews')).toHaveAttribute(
        'aria-selected',
        'true'
      );
    });
    expect(await screen.findByTestId('mock-area-pivotViews')).toBeInTheDocument();

    // Home: jump back to the first tab (overview).
    fireEvent.keyDown(screen.getByTestId('analytics-tab-pivotViews'), { key: 'Home' });
    await waitFor(() => {
      expect(screen.getByTestId('analytics-tab-overview')).toHaveAttribute(
        'aria-selected',
        'true'
      );
    });
    expect(await screen.findByTestId('mock-area-overview')).toBeInTheDocument();

    // All three areas have now been visited, each mounted exactly when selected.
    expect(mounts).toEqual(['overview', 'distributions', 'pivotViews', 'overview']);
  });

  it('ArrowLeft wraps from the first tab to the last', async () => {
    renderPanel();
    await screen.findByTestId('mock-area-overview');

    fireEvent.keyDown(screen.getByTestId('analytics-tab-overview'), { key: 'ArrowLeft' });
    await waitFor(() => {
      expect(screen.getByTestId('analytics-tab-pivotViews')).toHaveAttribute(
        'aria-selected',
        'true'
      );
    });
  });
});

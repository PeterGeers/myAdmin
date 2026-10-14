/**
 * Component tests for the Member Analytics non-happy-state presentation (task 3.4, R1.4).
 *
 * Covers the two notice kinds the shared `AnalyticsStateNotice` renders — the
 * NEUTRAL empty state and the WARNING degradation state — asserting they render
 * DISTINCTLY (R1.4) and accessibly (R6.6, colour is not the sole signal: each
 * kind pairs a distinct icon + ARIA role + test id with its bilingual text), and
 * covers `PivotViewsArea` mounting the pivot sub-panel with NO degradation notice
 * (the "no analytics config" state was removed with the role machinery — a tenant
 * with no saved sets now sees the empty-state hint built into the sub-panel).
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';

// Echo i18n keys so assertions are locale-independent.
vi.mock('../../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (key: string) => key }),
}));

// Mock the Members API so PivotViewsArea's real MemberPivotViews sub-panel does
// not hit the network: no saved sets, empty preferred list, no label templates.
const listAnalyticsSets = vi.fn();
const getPreferredList = vi.fn();
vi.mock('../../../../services/membersApiService', () => ({
  listAnalyticsSets: (...args: unknown[]) => listAnalyticsSets(...args),
  getPreferredList: (...args: unknown[]) => getPreferredList(...args),
  getAnalyticsSet: vi.fn(),
  deleteAnalyticsSet: vi.fn(),
  savePreferredList: vi.fn(),
  putAnalyticsSetDelivery: vi.fn(),
  deleteAnalyticsSetDelivery: vi.fn(),
  listSchedulesForSet: vi.fn(),
  createSchedule: vi.fn(),
  updateSchedule: vi.fn(),
  deleteSchedule: vi.fn(),
  sendAdHocMail: vi.fn(),
}));
const listMemberTemplates = vi.fn();
vi.mock('../../../../services/memberTemplateService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../../services/memberTemplateService')>();
  return { ...actual, listMemberTemplates: (...args: unknown[]) => listMemberTemplates(...args) };
});

import { render, screen, waitFor } from '@/test-utils';
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
      <AnalyticsStateNotice kind="degradation" message="analytics.degradation.mailNotEnabled" />,
    );

    const notice = screen.getByTestId('analytics-degradation');
    expect(notice).toBeInTheDocument();
    // Degradation is an assertive alert — distinct role from the empty status.
    expect(notice).toHaveAttribute('role', 'alert');
    expect(notice).toHaveAttribute('data-notice-kind', 'degradation');
    expect(screen.getByText('analytics.degradation.mailNotEnabled')).toBeInTheDocument();
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

    render(
      <AnalyticsStateNotice kind="degradation" message="analytics.degradation.mailNotEnabled" />,
    );
    expect(screen.getByTestId('analytics-degradation')).toHaveAttribute('role', 'alert');
    expect(screen.queryByTestId('analytics-empty')).not.toBeInTheDocument();
  });
});

describe('PivotViewsArea — no degradation notice (role machinery removed)', () => {
  const baseProps = {
    processedData: [{ member_id: 'a' }] as unknown as MemberRow[],
    members: [{ member_id: 'a' }] as unknown as Member[],
    fieldConfig: { fields: [] } as unknown as FieldConfig,
    language: 'en',
    capabilities: { canExport: true },
  };

  beforeEach(() => {
    listAnalyticsSets.mockReset();
    getPreferredList.mockReset();
    listMemberTemplates.mockReset();
    listAnalyticsSets.mockResolvedValue([]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    listMemberTemplates.mockResolvedValue({ ok: true, data: [] });
  });

  it('mounts the pivot sub-panel with NO analytics-config degradation notice', async () => {
    render(<PivotViewsArea {...baseProps} />);

    // The area renders the real sub-panel (it does not error/crash).
    expect(screen.getByTestId('analytics-area-pivotViews')).toBeInTheDocument();
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    // The former "no analytics config" degradation notice is GONE.
    expect(screen.queryByTestId('analytics-degradation')).not.toBeInTheDocument();
  });

  it('shows the empty-state hint (not a degradation) when there are no saved sets', async () => {
    render(<PivotViewsArea {...baseProps} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    // A tenant with no saved sets sees the neutral empty-state hint + New set CTA.
    const hint = await screen.findByTestId('member-pivot-empty-hint');
    expect(hint).toBeInTheDocument();
    expect(screen.getByTestId('member-pivot-empty-hint-new-set')).toBeInTheDocument();
    expect(screen.queryByTestId('analytics-degradation')).not.toBeInTheDocument();
  });
});

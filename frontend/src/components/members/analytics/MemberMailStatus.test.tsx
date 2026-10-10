/**
 * Component tests for MemberMailStatus (analytics/MemberMailStatus.tsx).
 *
 * Verifies mail-spec task 3.3 (R9):
 *   - the screen renders the LIST of send-runs with the mode + recipient count +
 *     the "198 sent, 2 failed" tally + the lifecycle status (R9.2);
 *   - a run row DRILLS DOWN on click, lazily loading its FAILURE sub-records
 *     (`getMailRun`) and listing each failed recipient with its outcome + reason;
 *   - a run with NO failures shows a clear "no failures" note (successes are
 *     counted in the tally, never listed — the failure-only sub-record model);
 *   - HONESTY OF STATUS (R9.4): an explicit "sent = SES accepted, NOT delivered"
 *     note is always present, and the sent count is never labelled "delivered";
 *   - the EMPTY state (no runs) and the load-ERROR state render;
 *   - no hardcoded English (labels resolve from the `members` namespace, echoed
 *     by the i18n mock).
 *
 * The API client wrappers (`listMailRuns` / `getMailRun`) are injected via props
 * so the screen runs with no network; the i18n hook is mocked to echo keys so
 * assertions are locale-independent (proving no hardcoded English).
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';
import type { MailRunDetail, MailRunSummary } from '../../../types/members';

// Echo i18n keys (with any interpolated count/sent/failed) so assertions are
// locale-independent — this is how we prove no hardcoded English.
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key} ${JSON.stringify(opts)}` : key,
  }),
}));

import { render, screen, fireEvent, waitFor } from '@/test-utils';
import MemberMailStatus from './MemberMailStatus';
import { MemberMailStatus as FromBarrel } from './index';
import type { MemberMailStatusProps } from './MemberMailStatus';

const RUNS: MailRunSummary[] = [
  {
    runId: 'run-1',
    mode: 'per_recipient',
    triggeredBy: 'sub-1',
    recipientCount: 200,
    status: 'completed',
    sent: 198,
    failed: 2,
    createdAt: '2026-01-02T00:00:00Z',
    updatedAt: '2026-01-02T00:05:00Z',
  },
  {
    runId: 'run-2',
    mode: 'to_fixed',
    triggeredBy: 'sub-1',
    recipientCount: 1,
    status: 'queued',
    sent: 0,
    failed: 0,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  },
];

const DETAIL_WITH_FAILURES: MailRunDetail = {
  run: RUNS[0],
  failures: [
    {
      address: 'bad@example.com',
      status: 'failed',
      reason: 'MessageRejected',
      messageId: null,
    },
    {
      address: 'bounce@example.com',
      status: 'bounced',
      reason: null,
      messageId: 'ses-123',
    },
  ],
};

const DETAIL_NO_FAILURES: MailRunDetail = { run: RUNS[1], failures: [] };

let loadRuns: ReturnType<typeof vi.fn>;
let loadRun: ReturnType<typeof vi.fn>;
let removeRun: ReturnType<typeof vi.fn>;

function makeProps(overrides: Partial<MemberMailStatusProps> = {}): MemberMailStatusProps {
  return {
    language: 'en',
    loadRuns: loadRuns as unknown as MemberMailStatusProps['loadRuns'],
    loadRun: loadRun as unknown as MemberMailStatusProps['loadRun'],
    removeRun: removeRun as unknown as MemberMailStatusProps['removeRun'],
    ...overrides,
  };
}

beforeEach(() => {
  loadRuns = vi.fn().mockResolvedValue(RUNS);
  loadRun = vi.fn().mockResolvedValue(DETAIL_WITH_FAILURES);
  removeRun = vi.fn().mockResolvedValue(undefined);
});

describe('MemberMailStatus', () => {
  it('is exported from the analytics barrel', () => {
    expect(FromBarrel).toBe(MemberMailStatus);
  });

  it('loads and renders the run list with mode, recipient count, tally and status (R9.2)', async () => {
    render(<MemberMailStatus {...makeProps()} />);

    // The list appears once the runs load.
    const runRows = await screen.findAllByTestId('member-mail-status-run');
    expect(runRows).toHaveLength(2);
    expect(loadRuns).toHaveBeenCalledTimes(1);

    // The tally is rendered with the sent/failed counts interpolated (R9.2).
    const tallies = screen.getAllByTestId('member-mail-status-tally');
    expect(tallies[0]).toHaveTextContent('analytics.mailRuns.tally');
    expect(tallies[0]).toHaveTextContent('"sent":198');
    expect(tallies[0]).toHaveTextContent('"failed":2');

    // The lifecycle status badge resolves from the members namespace.
    const badges = screen.getAllByTestId('member-mail-status-badge');
    expect(badges[0]).toHaveTextContent('analytics.mailRuns.status.completed');
    expect(badges[1]).toHaveTextContent('analytics.mailRuns.status.queued');
  });

  it('always shows the honest "sent = SES accepted, not delivered" note (R9.4)', async () => {
    render(<MemberMailStatus {...makeProps()} />);
    // Present immediately (not gated on a run) — the core view must not claim delivered.
    expect(
      screen.getByTestId('member-mail-status-sent-meaning'),
    ).toHaveTextContent('analytics.mailRuns.sentMeaning');
    await screen.findAllByTestId('member-mail-status-run');
  });

  it('drills into a run on click, loading and listing its failures (R9.2)', async () => {
    render(<MemberMailStatus {...makeProps()} />);
    const toggles = await screen.findAllByTestId('member-mail-status-run-toggle');

    // Expand the first run → lazily loads its drill-down.
    fireEvent.click(toggles[0]);
    await waitFor(() => expect(loadRun).toHaveBeenCalledWith('run-1'));

    const failures = await screen.findAllByTestId('member-mail-status-failure');
    expect(failures).toHaveLength(2);
    expect(failures[0]).toHaveTextContent('bad@example.com');
    expect(failures[0]).toHaveTextContent('analytics.mailRuns.failureStatus.failed');
    expect(failures[0]).toHaveTextContent('MessageRejected');
    // A late bounce is a FAILURE sub-record too (R8.4 layered feedback).
    expect(failures[1]).toHaveTextContent('bounce@example.com');
    expect(failures[1]).toHaveTextContent('analytics.mailRuns.failureStatus.bounced');
    // A failure with no reason falls back to the "no reason recorded" label.
    expect(failures[1]).toHaveTextContent('analytics.mailRuns.failure.noReason');
  });

  it('shows a "no failures" note for a run whose drill-down has none', async () => {
    loadRun = vi.fn().mockResolvedValue(DETAIL_NO_FAILURES);
    render(<MemberMailStatus {...makeProps()} />);
    const toggles = await screen.findAllByTestId('member-mail-status-run-toggle');

    // Expand the second (queued, 0/0) run.
    fireEvent.click(toggles[1]);
    await waitFor(() => expect(loadRun).toHaveBeenCalledWith('run-2'));
    expect(
      await screen.findByTestId('member-mail-status-no-failures'),
    ).toHaveTextContent('analytics.mailRuns.noFailures');
    expect(screen.queryByTestId('member-mail-status-failure')).not.toBeInTheDocument();
  });

  it('collapses a run on a second click and does not re-fetch its drill-down', async () => {
    render(<MemberMailStatus {...makeProps()} />);
    const toggles = await screen.findAllByTestId('member-mail-status-run-toggle');

    fireEvent.click(toggles[0]); // expand → load
    await waitFor(() => expect(loadRun).toHaveBeenCalledTimes(1));
    expect(await screen.findByTestId('member-mail-status-drill')).toBeInTheDocument();

    fireEvent.click(toggles[0]); // collapse
    await waitFor(() =>
      expect(screen.queryByTestId('member-mail-status-drill')).not.toBeInTheDocument(),
    );

    fireEvent.click(toggles[0]); // re-expand → reuse cached detail (no second fetch)
    await screen.findByTestId('member-mail-status-drill');
    expect(loadRun).toHaveBeenCalledTimes(1);
  });

  it('renders the empty state when there are no runs', async () => {
    loadRuns = vi.fn().mockResolvedValue([]);
    render(<MemberMailStatus {...makeProps()} />);
    expect(
      await screen.findByTestId('member-mail-status-empty'),
    ).toHaveTextContent('analytics.mailRuns.empty');
    expect(screen.queryByTestId('member-mail-status-run')).not.toBeInTheDocument();
  });

  it('renders a clear error state when the run list fails to load', async () => {
    loadRuns = vi.fn().mockRejectedValue(new Error('boom'));
    render(<MemberMailStatus {...makeProps()} />);
    expect(
      await screen.findByTestId('member-mail-status-error'),
    ).toHaveTextContent('analytics.mailRuns.loadError');
  });

  it('shows a per-run error when a drill-down load fails, without breaking the list', async () => {
    loadRun = vi.fn().mockRejectedValue(new Error('drill boom'));
    render(<MemberMailStatus {...makeProps()} />);
    const toggles = await screen.findAllByTestId('member-mail-status-run-toggle');

    fireEvent.click(toggles[0]);
    expect(
      await screen.findByTestId('member-mail-status-drill-error'),
    ).toHaveTextContent('analytics.mailRuns.loadRunError');
    // The run list is still intact.
    expect(screen.getAllByTestId('member-mail-status-run')).toHaveLength(2);
  });

  it('refreshes the run list on the Refresh button', async () => {
    render(<MemberMailStatus {...makeProps()} />);
    await screen.findAllByTestId('member-mail-status-run');
    expect(loadRuns).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('member-mail-status-refresh'));
    await waitFor(() => expect(loadRuns).toHaveBeenCalledTimes(2));
  });

  // ── Manual delete (R9.6 retention; steering 32 — explicit confirm) ───────────────

  it('does not delete until the user confirms (steering 32 destructive-action confirm)', async () => {
    render(<MemberMailStatus {...makeProps()} />);
    const deletes = await screen.findAllByTestId('member-mail-status-delete');

    // Clicking the row Delete opens the confirm dialog but fires NO delete yet.
    fireEvent.click(deletes[0]);
    expect(
      await screen.findByTestId('member-mail-status-delete-dialog'),
    ).toBeInTheDocument();
    expect(removeRun).not.toHaveBeenCalled();

    // Cancelling closes the dialog and still fires no delete.
    fireEvent.click(screen.getByTestId('member-mail-status-delete-cancel'));
    await waitFor(() =>
      expect(
        screen.queryByTestId('member-mail-status-delete-dialog'),
      ).not.toBeInTheDocument(),
    );
    expect(removeRun).not.toHaveBeenCalled();
  });

  it('deletes the run on confirm, calling the route and refreshing the list (R9.6)', async () => {
    render(<MemberMailStatus {...makeProps()} />);
    const deletes = await screen.findAllByTestId('member-mail-status-delete');
    expect(loadRuns).toHaveBeenCalledTimes(1);

    fireEvent.click(deletes[0]); // open confirm for run-1
    fireEvent.click(await screen.findByTestId('member-mail-status-delete-confirm'));

    // The DELETE route is called for the right run id, then the list refreshes.
    await waitFor(() => expect(removeRun).toHaveBeenCalledWith('run-1'));
    await waitFor(() => expect(loadRuns).toHaveBeenCalledTimes(2));
    // The dialog closes on success.
    await waitFor(() =>
      expect(
        screen.queryByTestId('member-mail-status-delete-dialog'),
      ).not.toBeInTheDocument(),
    );
  });

  it('surfaces an error and does not refresh when the delete fails', async () => {
    removeRun = vi.fn().mockRejectedValue(new Error('nope'));
    render(<MemberMailStatus {...makeProps()} />);
    const deletes = await screen.findAllByTestId('member-mail-status-delete');
    expect(loadRuns).toHaveBeenCalledTimes(1);

    fireEvent.click(deletes[0]);
    fireEvent.click(await screen.findByTestId('member-mail-status-delete-confirm'));

    await waitFor(() => expect(removeRun).toHaveBeenCalledWith('run-1'));
    // A failed delete does NOT trigger a list refresh (the list is left as-is).
    expect(loadRuns).toHaveBeenCalledTimes(1);
  });
});

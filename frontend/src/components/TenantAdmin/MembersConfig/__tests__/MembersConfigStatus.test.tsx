/**
 * Tests for the Members config delivered/loaded status banner (Phase 0 step 3, risk #6).
 *
 * The banner is presentation-only: it renders the module's projected `config_status` map
 * (`{config_id: version | null}`) as a per-config delivered / not-yet-delivered indicator, and
 * claims NOTHING when the status is unavailable (empty map → older module build / fetch glitch).
 */
import { vi } from 'vitest';
import React from 'react';
import { render, screen, within } from '../../../../test-utils';
import { MembersConfigStatus } from '../MembersConfigStatus';

describe('MembersConfigStatus', () => {
  it('renders nothing when the status is unavailable (empty map)', () => {
    const { container } = render(<MembersConfigStatus status={{}} lang="en" />);
    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('members-config-status')).not.toBeInTheDocument();
  });

  it('renders nothing when status is undefined', () => {
    const { container } = render(<MembersConfigStatus lang="en" />);
    expect(container.firstChild).toBeNull();
  });

  it('shows Delivered with the loaded version for a non-null version', () => {
    render(
      <MembersConfigStatus
        status={{ fields: '2026-10-12T09:00:00', scope: 3, views: null, mail: null }}
        lang="en"
      />,
    );
    const fields = screen.getByTestId('members-config-status-fields');
    expect(within(fields).getByText('Delivered')).toBeInTheDocument();
    // The loaded version is surfaced so staleness can be judged against the source.
    expect(within(fields).getByText(/loaded version: 2026-10-12T09:00:00/)).toBeInTheDocument();

    const scope = screen.getByTestId('members-config-status-scope');
    expect(within(scope).getByText('Delivered')).toBeInTheDocument();
    expect(within(scope).getByText(/loaded version: 3/)).toBeInTheDocument();
  });

  it('shows Not yet delivered for a null version', () => {
    render(<MembersConfigStatus status={{ views: null }} lang="en" />);
    const views = screen.getByTestId('members-config-status-views');
    expect(within(views).getByText('Not yet delivered')).toBeInTheDocument();
  });

  it('skips a config id the module did not report at all', () => {
    render(<MembersConfigStatus status={{ fields: 1 }} lang="en" />);
    expect(screen.getByTestId('members-config-status-fields')).toBeInTheDocument();
    // scope/views/mail were not in the map → not rendered.
    expect(screen.queryByTestId('members-config-status-scope')).not.toBeInTheDocument();
    expect(screen.queryByTestId('members-config-status-mail')).not.toBeInTheDocument();
  });

  it('renders Dutch labels when lang is nl', () => {
    render(<MembersConfigStatus status={{ fields: null }} lang="nl" />);
    const fields = screen.getByTestId('members-config-status-fields');
    expect(within(fields).getByText('Nog niet geleverd')).toBeInTheDocument();
    expect(screen.getByText('Projectiestatus')).toBeInTheDocument();
  });
});

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
        status={{ fields: '2026-10-12T09:00:00', scope: 3, mail: null }}
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
    render(<MembersConfigStatus status={{ mail: null }} lang="en" />);
    const mail = screen.getByTestId('members-config-status-mail');
    expect(within(mail).getByText('Not yet delivered')).toBeInTheDocument();
  });

  it('skips a config id the module did not report at all', () => {
    render(<MembersConfigStatus status={{ fields: 1 }} lang="en" />);
    expect(screen.getByTestId('members-config-status-fields')).toBeInTheDocument();
    // scope/mail were not in the map → not rendered.
    expect(screen.queryByTestId('members-config-status-scope')).not.toBeInTheDocument();
    expect(screen.queryByTestId('members-config-status-mail')).not.toBeInTheDocument();
  });

  it('labels a timestamp version as UTC to prevent local-time misreading (regression)', () => {
    // The projected version is a UTC ISO-8601 string stored without a `Z`. Rendered raw it
    // was misread as local time (a fresh projection looked hours old to a CEST viewer). The
    // banner must label it `UTC` explicitly. We assert on the per-config version node's text.
    render(<MembersConfigStatus status={{ fields: '2026-10-14T21:51:03' }} lang="en" />);
    const versionNode = screen.getByTestId('members-config-status-fields-version');
    // The authoritative UTC value is shown AND explicitly labelled UTC.
    expect(versionNode).toHaveTextContent('2026-10-14T21:51:03 UTC');
  });

  it('does NOT attach a timezone label to a non-timestamp (integer) version', () => {
    // An integer counter version is not a wall-clock time, so no `UTC` claim is made.
    render(<MembersConfigStatus status={{ fields: 7 }} lang="en" />);
    const versionNode = screen.getByTestId('members-config-status-fields-version');
    expect(versionNode).toHaveTextContent('loaded version: 7');
    expect(versionNode).not.toHaveTextContent('UTC');
  });

  it('renders Dutch labels when lang is nl', () => {
    render(<MembersConfigStatus status={{ fields: null }} lang="nl" />);
    const fields = screen.getByTestId('members-config-status-fields');
    expect(within(fields).getByText('Nog niet geleverd')).toBeInTheDocument();
    expect(screen.getByText('Projectiestatus')).toBeInTheDocument();
  });
});

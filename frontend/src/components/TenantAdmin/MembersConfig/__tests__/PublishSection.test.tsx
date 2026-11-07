/**
 * Tests for PublishSection — the deliberate go-live control (grouped per-group-save redesign).
 *
 * Extracted out of ApplicationFormShellPanel. Publish is DISTINCT from Save: it is readiness-gated
 * (slug + certified sender + ≥1 on-form field) and, when not ready, explains WHICH precondition is
 * missing (show, don't silently block). When ready + the draft has saved-but-unpublished changes,
 * it surfaces the save ≠ publish hint.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '../../../../test-utils';
import { PublishSection } from '../PublishSection';
import type { ReadinessState } from '../applicationReadiness';

const READY: ReadinessState = {
  certifiedSender: true,
  slugPresent: true,
  hasFieldOnForm: true,
  isSendReady: true,
};

describe('PublishSection', () => {
  it('fires the publish handler when ready and the button is clicked', () => {
    const onPublish = vi.fn();
    render(<PublishSection readiness={READY} onPublish={onPublish} lang="en" />);
    const btn = screen.getByTestId('application-form-publish-button');
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    expect(onPublish).toHaveBeenCalledTimes(1);
  });

  it('disables Publish and explains every missing precondition when not ready (R5.4)', () => {
    const onPublish = vi.fn();
    render(
      <PublishSection
        readiness={{
          certifiedSender: false,
          slugPresent: false,
          hasFieldOnForm: false,
          isSendReady: false,
        }}
        onPublish={onPublish}
        lang="en"
      />,
    );
    const btn = screen.getByTestId('application-form-publish-button');
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onPublish).not.toHaveBeenCalled();
    expect(screen.getByTestId('application-form-publish-blocked')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-publish-need-slug')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-publish-need-sender')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-publish-need-field')).toBeInTheDocument();
  });

  it('explains ONLY the missing precondition', () => {
    render(
      <PublishSection
        readiness={{
          certifiedSender: true,
          slugPresent: true,
          hasFieldOnForm: false,
          isSendReady: true,
        }}
        onPublish={vi.fn()}
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-form-publish-button')).toBeDisabled();
    expect(screen.getByTestId('application-form-publish-need-field')).toBeInTheDocument();
    expect(screen.queryByTestId('application-form-publish-need-slug')).not.toBeInTheDocument();
    expect(screen.queryByTestId('application-form-publish-need-sender')).not.toBeInTheDocument();
  });

  it('surfaces the "unpublished changes" hint when ready + pending edits (save ≠ publish)', () => {
    render(
      <PublishSection readiness={READY} onPublish={vi.fn()} hasUnpublishedChanges lang="en" />,
    );
    expect(
      screen.getByTestId('application-form-publish-unpublished-changes'),
    ).toBeInTheDocument();
  });

  it('labels the button Publish first time and Republish once published', () => {
    const { rerender } = render(
      <PublishSection readiness={READY} onPublish={vi.fn()} everPublished={false} lang="en" />,
    );
    expect(screen.getByTestId('application-form-publish-button')).toHaveTextContent('Publish');
    rerender(<PublishSection readiness={READY} onPublish={vi.fn()} everPublished lang="en" />);
    expect(screen.getByTestId('application-form-publish-button')).toHaveTextContent('Republish');
  });
});

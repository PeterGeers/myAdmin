/**
 * Tests for the Application live preview (spec 11, task 4.2; R7.1–R7.4, design §4/§6/§9 S1·S2/§10).
 *
 * The change-with-tests pairing for the new `ApplicationFormPreview` (the full dedicated suite is
 * task 4.3). It asserts the R7 contract this task owns:
 *  - the preview renders an `<iframe>` to the CloudFront-hosted public form URL derived from the
 *    slug (R7.1 — the preview IS the real hosted form, zero drift);
 *  - no slug → a neutral "no preview available yet" placeholder pointing at the Landing Page
 *    editor, NOT an iframe (R5.1 / E4);
 *  - the reload token (bumped by the builder after a save) changes the iframe `key`/`src` so the
 *    preview re-fetches the hosted form — the "save to update preview" affordance (R7.4);
 *  - the manual "Update preview" button also reloads the iframe without a save.
 *
 * The component takes `lang` directly (no i18n), so a plain Chakra render suffices.
 */
import { describe, it, expect } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '../../../../test-utils';
import { ApplicationFormPreview } from '../ApplicationFormPreview';

describe('ApplicationFormPreview — iframe to the hosted public form (R7.1)', () => {
  it('renders an iframe pointed at the derived public form URL', () => {
    render(<ApplicationFormPreview slug="h-dcn" lang="en" />);
    const iframe = screen.getByTestId('application-form-preview-iframe');
    expect(iframe).toBeInTheDocument();
    // The preview IS the real CloudFront-hosted form at <slug>.jabaki.nl (zero drift).
    expect(iframe.getAttribute('src') ?? '').toContain('https://h-dcn.jabaki.nl');
  });
});

describe('ApplicationFormPreview — no slug → neutral placeholder (R5.1 / E4)', () => {
  it('shows the "no preview available yet" placeholder + a Landing Page editor link, no iframe', () => {
    render(<ApplicationFormPreview slug={null} lang="en" />);
    expect(screen.getByTestId('application-form-preview-no-url')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-preview-landing-link')).toBeInTheDocument();
    expect(screen.queryByTestId('application-form-preview-iframe')).not.toBeInTheDocument();
  });
});

describe('ApplicationFormPreview — save-to-update-preview reload (R7.4)', () => {
  it('a changed reload token changes the iframe src (remount re-fetches the hosted form)', () => {
    const { rerender } = render(<ApplicationFormPreview slug="h-dcn" reloadToken={0} lang="en" />);
    const before = screen.getByTestId('application-form-preview-iframe').getAttribute('src');

    // The builder bumps the token after a successful save → the preview re-fetches the live form.
    rerender(<ApplicationFormPreview slug="h-dcn" reloadToken={1} lang="en" />);
    const after = screen.getByTestId('application-form-preview-iframe').getAttribute('src');

    expect(after).not.toBe(before);
    expect(after ?? '').toContain('https://h-dcn.jabaki.nl');
  });

  it('the manual "Update preview" button reloads the iframe without a save', () => {
    render(<ApplicationFormPreview slug="h-dcn" lang="en" />);
    const before = screen.getByTestId('application-form-preview-iframe').getAttribute('src');

    fireEvent.click(screen.getByTestId('application-form-preview-reload'));
    const after = screen.getByTestId('application-form-preview-iframe').getAttribute('src');

    expect(after).not.toBe(before);
  });
});

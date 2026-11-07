/**
 * Tests for ApplicationAddressFields — the Public-address group's deferred prefix + slug inputs
 * (grouped per-group-save redesign, Task 5).
 *
 * The component is a pure controlled value-lifter: it renders the prefix + slug inputs bound to the
 * builder-owned drafts and lifts edits via onPrefixChange/onSlugChange. It owns NO Save button and
 * fires NO network call — the group's single Save (GroupSaveBar → handleSaveAddress) commits both.
 * (Ordering + the actual commit are asserted in the builder suite.)
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '../../../../test-utils';
import { ApplicationAddressFields } from '../ApplicationAddressFields';

describe('ApplicationAddressFields', () => {
  it('renders prefix + slug inputs seeded from the drafts, with programmatic labels', () => {
    render(
      <ApplicationAddressFields
        prefixDraft="h-dcn"
        slugDraft="h-dcn-apply"
        onPrefixChange={vi.fn()}
        onSlugChange={vi.fn()}
        publicUrl="https://h-dcn-apply.jabaki.nl/apply"
        lang="en"
      />,
    );
    expect((screen.getByTestId('application-form-address-prefix-input') as HTMLInputElement).value).toBe(
      'h-dcn',
    );
    expect((screen.getByTestId('application-form-address-slug-input') as HTMLInputElement).value).toBe(
      'h-dcn-apply',
    );
    // Accessibility: both inputs have programmatic labels.
    expect(screen.getByLabelText(/public prefix/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/form slug/i)).toBeInTheDocument();
  });

  it('lifts a prefix edit up via onPrefixChange (no write)', () => {
    const onPrefixChange = vi.fn();
    render(
      <ApplicationAddressFields
        prefixDraft="h-dcn"
        slugDraft=""
        onPrefixChange={onPrefixChange}
        onSlugChange={vi.fn()}
        publicUrl={null}
        lang="en"
      />,
    );
    fireEvent.change(screen.getByTestId('application-form-address-prefix-input'), {
      target: { value: 'h-dcn-new' },
    });
    expect(onPrefixChange).toHaveBeenCalledWith('h-dcn-new');
  });

  it('lifts a slug edit up via onSlugChange (no write)', () => {
    const onSlugChange = vi.fn();
    render(
      <ApplicationAddressFields
        prefixDraft="h-dcn"
        slugDraft="h-dcn-apply"
        onPrefixChange={vi.fn()}
        onSlugChange={onSlugChange}
        publicUrl={null}
        lang="en"
      />,
    );
    fireEvent.change(screen.getByTestId('application-form-address-slug-input'), {
      target: { value: 'h-dcn-join' },
    });
    expect(onSlugChange).toHaveBeenCalledWith('h-dcn-join');
  });

  it('shows the derived public URL + open-live link when a URL is present', () => {
    render(
      <ApplicationAddressFields
        prefixDraft="h-dcn"
        slugDraft="h-dcn-apply"
        onPrefixChange={vi.fn()}
        onSlugChange={vi.fn()}
        publicUrl="https://h-dcn-apply.jabaki.nl/apply"
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-form-address-public-url')).toHaveTextContent(
      'https://h-dcn-apply.jabaki.nl/apply',
    );
    const link = screen.getByTestId('application-form-address-open-live');
    expect(link).toHaveAttribute('href', 'https://h-dcn-apply.jabaki.nl/apply');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel') ?? '').toContain('noopener');
  });

  it('shows a "no public address yet" note when no URL is present', () => {
    render(
      <ApplicationAddressFields
        prefixDraft=""
        slugDraft=""
        onPrefixChange={vi.fn()}
        onSlugChange={vi.fn()}
        publicUrl={null}
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-form-address-no-url')).toBeInTheDocument();
    expect(screen.queryByTestId('application-form-address-open-live')).not.toBeInTheDocument();
  });
});

/**
 * Tests for the application-form landing-page block (spec Members/11 task 3.2a, E4a/R5.2a).
 *
 * The block renders the tenant's PUBLIC member-application form as a NATIVE, same-origin section
 * of the landing page (no iframe). It composes the SAME public pieces the standalone /apply route
 * uses: PublicApplicationPage (fetch-by-slug + loading/404/409 states) + ApplicationFormPage
 * (config-driven form). Both are mocked here so the test pins the BLOCK's wiring, not the
 * (separately-tested) form internals: slug + layout pass-through, optional title, no-slug no-op.
 *
 * Validates: Requirements R5.2a (E4a native block)
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen } from '../../../../test-utils';
import { ApplicationFormBlock } from '../ApplicationFormBlock';

vi.mock('../../../../components/public/application/PublicApplicationPage', () => ({
  PublicApplicationPage: ({
    tenantSlug,
    renderForm,
  }: {
    tenantSlug: string;
    renderForm: (c: unknown) => React.ReactNode;
  }) => (
    <div data-testid="stub-public-application-page" data-slug={tenantSlug}>
      {renderForm({ fields: [] })}
    </div>
  ),
}));

vi.mock('../../../../components/public/application/ApplicationFormPage', () => ({
  ApplicationFormPage: ({
    tenantSlug,
    initialLocale,
  }: {
    tenantSlug: string;
    initialLocale?: string;
  }) => (
    <div
      data-testid="stub-application-form-page"
      data-slug={tenantSlug}
      data-locale={initialLocale ?? ''}
    />
  ),
}));

describe('ApplicationFormBlock — native same-origin landing-page block (task 3.2a)', () => {
  it('renders the public application page for the tenant slug (same-origin, no iframe)', () => {
    render(
      <ApplicationFormBlock properties={{}} layout="contained" tenantSlug="hdcn-application-form" />,
    );
    const page = screen.getByTestId('stub-public-application-page');
    expect(page).toBeInTheDocument();
    expect(page).toHaveAttribute('data-slug', 'hdcn-application-form');
    expect(document.querySelector('iframe')).toBeNull();
  });

  it('feeds the slug + initial locale into the form via the renderForm slot', () => {
    render(
      <ApplicationFormBlock
        properties={{ locale: 'en' }}
        layout="contained"
        tenantSlug="hdcn-application-form"
      />,
    );
    const form = screen.getByTestId('stub-application-form-page');
    expect(form).toHaveAttribute('data-slug', 'hdcn-application-form');
    expect(form).toHaveAttribute('data-locale', 'en');
  });

  it('renders an optional block title above the form', () => {
    render(
      <ApplicationFormBlock
        properties={{ title: 'Join us' }}
        layout="full-width"
        tenantSlug="hdcn-application-form"
      />,
    );
    expect(screen.getByText('Join us')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-block')).toBeInTheDocument();
  });

  it('renders nothing when there is no tenant slug', () => {
    const { container } = render(
      <ApplicationFormBlock properties={{}} layout="contained" tenantSlug="" />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

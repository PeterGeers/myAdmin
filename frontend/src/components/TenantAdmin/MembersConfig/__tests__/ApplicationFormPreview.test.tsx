/**
 * Tests for the Application live preview (spec 11, task 4.2; R7.1/R7.2/R7.4, design §4/§6/§9 S1·S2/§10).
 *
 * The change-with-tests pairing for the rewritten `ApplicationFormPreview` (the full dedicated
 * suite is task 4.3). It asserts the R7 contract this task owns — the preview is an IN-APP render
 * of the public form via the shared spec-10 `ApplicationFormRenderer`, fed by the server-side
 * `POST /members/application-preview` over the builder's WORKING overlay (zero client mirror, zero
 * drift):
 *  - it POSTs the working overlay to the preview service and renders the returned schema through
 *    `ApplicationFormRenderer` (R7.1/R7.2 — single filter authority + single render path);
 *  - a change to the working overlay re-POSTs and re-renders, so the preview reflects UNSAVED edits
 *    live (R7.1 / §9 S2);
 *  - rapid overlay changes are DEBOUNCED into fewer requests and the latest overlay wins;
 *  - the preview is READ-ONLY — no submit control (R7.4);
 *  - a malformed-overlay error surfaces a neutral inline message instead of a blank/crashed form.
 *
 * The preview service is mocked so the test asserts the component's wiring (debounce → POST →
 * render) without a network; `debounceMs={0}` makes the POST deterministic/immediate.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '../../../../test-utils';
import { ApplicationFormPreview } from '../ApplicationFormPreview';
import type { PublicFieldConfig } from '../../../public/application/applicationFieldConfig';
import { previewMembersApplicationConfig } from '../../../../services/membersConfigService';

vi.mock('../../../../services/membersConfigService', () => ({
  previewMembersApplicationConfig: vi.fn(),
}));

const mockPreview = vi.mocked(previewMembersApplicationConfig);

/** A minimal applicant-facing schema the server preview would return for a working overlay. */
function schemaWith(fieldKeys: string[]): PublicFieldConfig {
  return {
    fields: fieldKeys.map((key, i) => ({
      key,
      type: 'string',
      label: { nl: `NL ${key}`, en: `Label ${key}` },
      functional_group: 'personal',
      order: i,
      required: false,
    })),
    locales: ['nl', 'en'],
    notice: null,
  };
}

beforeEach(() => {
  mockPreview.mockReset();
});

describe('ApplicationFormPreview — in-app render via the server preview endpoint (R7.1/R7.2)', () => {
  it('POSTs the working overlay and renders the returned schema through ApplicationFormRenderer', async () => {
    mockPreview.mockResolvedValue(schemaWith(['personal.email']));
    const overlay = { fields: { 'personal.email': { application_visible: true } } };

    render(<ApplicationFormPreview overlay={overlay} lang="en" debounceMs={0} />);

    // The preview POSTs the WORKING overlay to the single server filter (not a client mirror).
    await waitFor(() => expect(mockPreview).toHaveBeenCalledWith(overlay));
    // The returned schema is rendered through the shared renderer (one render path).
    await screen.findByTestId('application-form-preview-render');
    expect(screen.getByTestId('application-form')).toBeInTheDocument();
    expect(screen.getByText('Label personal.email')).toBeInTheDocument();
  });

  it('reflects UNSAVED edits: a changed working overlay re-POSTs and re-renders the new schema', async () => {
    mockPreview.mockResolvedValueOnce(schemaWith(['personal.email']));
    const { rerender } = render(
      <ApplicationFormPreview
        overlay={{ fields: { 'personal.email': { application_visible: true } } }}
        lang="en"
        debounceMs={0}
      />,
    );
    await screen.findByText('Label personal.email');

    // The admin toggles another field ON (an UNSAVED edit) → the preview re-POSTs the new overlay
    // and renders the new field, with NO save / round-trip to the hosted form (R7.1 / §9 S2).
    mockPreview.mockResolvedValueOnce(schemaWith(['personal.email', 'personal.phone']));
    rerender(
      <ApplicationFormPreview
        overlay={{
          fields: {
            'personal.email': { application_visible: true },
            'personal.phone': { application_visible: true },
          },
        }}
        lang="en"
        debounceMs={0}
      />,
    );

    await screen.findByText('Label personal.phone');
    expect(screen.getByText('Label personal.email')).toBeInTheDocument();
    expect(mockPreview).toHaveBeenCalledTimes(2);
  });

  it('debounces rapid overlay changes into ONE request, and the latest overlay wins', async () => {
    mockPreview.mockResolvedValue(schemaWith(['personal.email']));
    vi.useFakeTimers();
    try {
      const { rerender } = render(
        <ApplicationFormPreview overlay={{ fields: { a: { application_visible: true } } }} lang="en" />,
      );
      // Two quick successive edits within the debounce window.
      rerender(
        <ApplicationFormPreview overlay={{ fields: { b: { application_visible: true } } }} lang="en" />,
      );
      const latest = { fields: { c: { application_visible: true } } };
      rerender(<ApplicationFormPreview overlay={latest} lang="en" />);

      // Nothing fired yet — the timer is still pending.
      expect(mockPreview).not.toHaveBeenCalled();

      vi.advanceTimersByTime(500);
      // Exactly one POST, carrying the LATEST overlay (the earlier edits were debounced away).
      expect(mockPreview).toHaveBeenCalledTimes(1);
      expect(mockPreview).toHaveBeenCalledWith(latest);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('ApplicationFormPreview — read-only (R7.4)', () => {
  it('renders no submit control (the preview cannot be submitted)', async () => {
    mockPreview.mockResolvedValue(schemaWith(['personal.email']));
    render(<ApplicationFormPreview overlay={{}} lang="en" debounceMs={0} />);

    await screen.findByTestId('application-form-preview-render');
    expect(screen.queryByRole('button', { name: /submit|versturen/i })).not.toBeInTheDocument();
  });
});

describe('ApplicationFormPreview — error surfacing', () => {
  it('shows a neutral inline message when the overlay is rejected (no blank/crashed form)', async () => {
    mockPreview.mockRejectedValue(new Error('application-preview field_overlay is invalid'));
    render(<ApplicationFormPreview overlay={{}} lang="en" debounceMs={0} />);

    await screen.findByTestId('application-form-preview-error');
    expect(screen.queryByTestId('application-form-preview-render')).not.toBeInTheDocument();
  });
});

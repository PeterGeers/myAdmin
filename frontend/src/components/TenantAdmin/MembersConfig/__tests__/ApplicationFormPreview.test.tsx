/**
 * Tests for the Application live preview (spec 12 — Application Form Serving Redesign, task 5.1;
 * R3.1/R3.2, design §C2 / D4).
 *
 * The change-with-tests pairing for the rewritten `ApplicationFormPreview`. Spec 12 retires the
 * server round-trip (`POST /members/application-preview`, deleted in task 5.2): the preview is now
 * an IN-BROWSER render of the public form via the shared spec-10 `ApplicationFormRenderer`, fed by
 * the PURE `buildPreviewConfig` filter over the builder's WORKING draft (resolved `FieldConfig` ⊕
 * the one `field_overlay`). This suite asserts the R3 contract:
 *  - the preview renders the applicant-facing selection WITHOUT any network call — the preview API
 *    is gone, so there is nothing to mock (R3.1/R3.2);
 *  - a change to the WORKING overlay re-derives + re-renders in memory, so the preview reflects
 *    UNSAVED edits live with no save and no round-trip (R3.1);
 *  - only ON-form fields (`application_visible`, overlay ⊕ served) appear;
 *  - the preview is READ-ONLY — no submit control (R7.4);
 *  - an empty form (no on-form fields) shows the neutral empty state, not a blank/crashed form.
 *
 * Fixtures use the bare `key` + `group` server shape (R2.3) — the resolved `FieldConfig` the builder
 * loads from `GET /members/field-config`.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen } from '../../../../test-utils';
import { ApplicationFormPreview } from '../ApplicationFormPreview';
import type { FieldConfig, FieldConfigField } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';

/**
 * Guard that NO preview API exists to be called: the retired `previewMembersApplicationConfig`
 * (and its underlying `previewApplicationFieldConfig`) must be gone from the service surface, so
 * the in-browser preview can never silently fall back to a network round-trip.
 */
import * as membersConfigService from '../../../../services/membersConfigService';
import * as membersApiService from '../../../../services/membersApiService';

/** A resolved field in the BARE `key` + `group` server shape (R2.3). */
function field(key: string, group: string, extra: Partial<FieldConfigField> = {}): FieldConfigField {
  return {
    key,
    group,
    type: 'string',
    label: { nl: `NL ${key}`, en: `Label ${key}` },
    functional_group: group,
    origin: 'fixed',
    provenance: 'base',
    ...extra,
  };
}

/** A resolved `FieldConfig` carrying the given fields. */
function configWith(fields: FieldConfigField[]): FieldConfig {
  return { fields } as FieldConfig;
}

describe('ApplicationFormPreview — in-browser render over the working draft (R3.1)', () => {
  it('renders the applicant-facing selection with NO network call (the preview API is gone)', () => {
    // The field is turned ON via the WORKING overlay (origin-aware override key for a base field).
    const fieldConfig = configWith([field('email', 'personal')]);
    const overlay: MembersConfigValue = {
      fixed_overrides: { 'personal.email': { application_visible: true } },
    };

    render(<ApplicationFormPreview fieldConfig={fieldConfig} overlay={overlay} lang="en" />);

    // Rendered through the shared renderer (one render path) — synchronously, no await needed.
    expect(screen.getByTestId('application-form-preview-render')).toBeInTheDocument();
    expect(screen.getByTestId('application-form')).toBeInTheDocument();
    expect(screen.getByText('Label email')).toBeInTheDocument();

    // No preview API is reachable at all — the service surface must not export it anymore.
    expect(
      (membersConfigService as Record<string, unknown>).previewMembersApplicationConfig,
    ).toBeUndefined();
    expect(
      (membersApiService as Record<string, unknown>).previewApplicationFieldConfig,
    ).toBeUndefined();
  });

  it('reflects UNSAVED edits live: a changed working overlay re-renders the new field in memory', () => {
    const fieldConfig = configWith([field('email', 'personal'), field('phone', 'personal')]);

    const { rerender } = render(
      <ApplicationFormPreview
        fieldConfig={fieldConfig}
        overlay={{ fixed_overrides: { 'personal.email': { application_visible: true } } }}
        lang="en"
      />,
    );
    expect(screen.getByText('Label email')).toBeInTheDocument();
    // `phone` is not on the form yet.
    expect(screen.queryByText('Label phone')).not.toBeInTheDocument();

    // The admin toggles `phone` ON (an UNSAVED in-memory edit) → the preview re-derives + re-renders
    // the new field with NO save and NO server round-trip (R3.1).
    rerender(
      <ApplicationFormPreview
        fieldConfig={fieldConfig}
        overlay={{
          fixed_overrides: {
            'personal.email': { application_visible: true },
            'personal.phone': { application_visible: true },
          },
        }}
        lang="en"
      />,
    );
    expect(screen.getByText('Label phone')).toBeInTheDocument();
    expect(screen.getByText('Label email')).toBeInTheDocument();
  });

  it('shows only ON-form fields — an unselected field is omitted (applicant-facing selection)', () => {
    const fieldConfig = configWith([
      field('email', 'personal', { application_visible: true }), // served ON
      field('secret_note', 'personal'), // not on the form
    ]);

    render(<ApplicationFormPreview fieldConfig={fieldConfig} overlay={{}} lang="en" />);

    expect(screen.getByText('Label email')).toBeInTheDocument();
    expect(screen.queryByText('Label secret_note')).not.toBeInTheDocument();
  });
});

describe('ApplicationFormPreview — read-only (R7.4)', () => {
  it('renders no submit control (the preview cannot be submitted)', () => {
    const fieldConfig = configWith([field('email', 'personal', { application_visible: true })]);
    render(<ApplicationFormPreview fieldConfig={fieldConfig} overlay={{}} lang="en" />);

    expect(screen.getByTestId('application-form-preview-render')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit|versturen/i })).not.toBeInTheDocument();
  });
});

describe('ApplicationFormPreview — empty state', () => {
  it('shows the neutral empty message when no field is on the form (no blank/crashed form)', () => {
    const fieldConfig = configWith([field('email', 'personal')]); // nothing turned on
    render(<ApplicationFormPreview fieldConfig={fieldConfig} overlay={{}} lang="en" />);

    expect(screen.getByTestId('application-form-preview-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('application-form-preview-render')).not.toBeInTheDocument();
  });
});

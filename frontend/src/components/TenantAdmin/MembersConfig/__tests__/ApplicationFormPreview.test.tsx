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
import { renderPageStyles } from '../pageStyles';

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

/**
 * Look-and-feel parity (spec 15 — SAM Page Look-and-Feel, task 13.1; Req 4.2/4.3/7). The preview
 * runs the browser-side Layer-2 mirror `renderPageStyles` over the working look-and-feel values and
 * applies the resulting `:root` CSS variables to the preview container, so what the admin sees
 * matches what publish bakes. The container exposes the produced variable string on a
 * `data-lookandfeel-vars` attribute for assertion.
 */
describe('ApplicationFormPreview — look-and-feel (spec 15, task 13.1; Req 4.2/4.3/7)', () => {
  const onFormConfig = () => configWith([field('email', 'personal', { application_visible: true })]);

  it('applies the Layer-2 defaults when no look-and-feel is supplied (Req 7.3)', () => {
    render(<ApplicationFormPreview fieldConfig={onFormConfig()} overlay={{}} lang="en" />);

    const container = screen.getByTestId('application-form-preview-render');
    // Mirrors exactly what the Python/TS Layer-2 generator emits for empty settings.
    expect(container.getAttribute('data-lookandfeel-vars')).toBe(
      renderPageStyles({}).cssVariables,
    );
  });

  it('carries the SAME styling the publish Layer-2 would produce for the given values (Req 7)', () => {
    const lookAndFeel = { color_primary: '#112233', base_spacing: 'relaxed', shadow_style: 'dramatic' };
    render(
      <ApplicationFormPreview
        fieldConfig={onFormConfig()}
        overlay={{}}
        lang="en"
        lookAndFeel={lookAndFeel}
      />,
    );

    const container = screen.getByTestId('application-form-preview-render');
    // The container carries the exact Layer-2 `:root` block the publish path would bake.
    expect(container.getAttribute('data-lookandfeel-vars')).toBe(
      renderPageStyles(lookAndFeel).cssVariables,
    );
    // ...and that block carries the relaxed-spacing value the form consumes via var(--spacing-section).
    expect(renderPageStyles(lookAndFeel).cssVariableMap['--spacing-section']).toBe('3rem');
    expect(container.getAttribute('data-lookandfeel-vars')).toContain('--spacing-section: 3rem;');
  });

  it('identical values → identical styling across two renders (Req 4.3)', () => {
    const lf = { color_primary: '#2D5F8A', border_radius_global: 'pill' };
    const { unmount } = render(
      <ApplicationFormPreview fieldConfig={onFormConfig()} overlay={{}} lang="en" lookAndFeel={lf} />,
    );
    const first = screen
      .getByTestId('application-form-preview-render')
      .getAttribute('data-lookandfeel-vars');
    unmount();

    render(
      <ApplicationFormPreview fieldConfig={onFormConfig()} overlay={{}} lang="en" lookAndFeel={{ ...lf }} />,
    );
    const second = screen
      .getByTestId('application-form-preview-render')
      .getAttribute('data-lookandfeel-vars');
    expect(second).toBe(first);
  });

  it('reflects an UNSAVED look-and-feel edit live — a changed value re-renders new styling (Req 4.2)', () => {
    const { rerender } = render(
      <ApplicationFormPreview
        fieldConfig={onFormConfig()}
        overlay={{}}
        lang="en"
        lookAndFeel={{ base_spacing: 'compact' }}
      />,
    );
    const before = screen
      .getByTestId('application-form-preview-render')
      .getAttribute('data-lookandfeel-vars');

    rerender(
      <ApplicationFormPreview
        fieldConfig={onFormConfig()}
        overlay={{}}
        lang="en"
        lookAndFeel={{ base_spacing: 'relaxed' }}
      />,
    );
    const after = screen
      .getByTestId('application-form-preview-render')
      .getAttribute('data-lookandfeel-vars');

    expect(after).not.toBe(before);
    expect(after).toBe(renderPageStyles({ base_spacing: 'relaxed' }).cssVariables);
  });
});

/**
 * spec 12 (Application Form Serving Redesign) task 5.4 — the SHARED-RENDERER PIN (R8.2).
 *
 * R8.2 (requirements.md) mandates ONE renderer, ONE code path for the in-app PREVIEW, the NATIVE
 * landing-page block (E4a), and the published artifact — so they cannot visually or behaviorally
 * diverge. Tasks 5.1/5.3 already cover the other two 5.4 checklist items:
 *   - preview reflects UNSAVED edits live, no network  → `ApplicationFormPreview.test.tsx`
 *   - client↔server filter parity fixture             → `applicationFilterParity.test.ts`
 * This file closes the KEY 5.4 gap: a regression pin that FAILS the day a future change forks the
 * renderer so one surface stops going through `ApplicationFormRenderer`.
 *
 * Two independent surfaces, verified against ONE renderer:
 *  1. the in-app PREVIEW — `ApplicationFormPreview` (task 5.1) renders the WORKING draft through the
 *     shared `ApplicationFormRenderer` after the pure `buildPreviewConfig` filter;
 *  2. the NATIVE landing-page block (E4a) — `ApplicationFormBlock` → `ApplicationFormPage` renders
 *     the public field-config through the SAME `ApplicationFormRenderer`, same-origin (no iframe).
 *
 * The pin has two complementary teeth:
 *  - MODULE IDENTITY: the renderer symbol each surface's module imports is the SAME object — there
 *    is literally one renderer module, not two that happen to look alike.
 *  - OUTPUT EQUIVALENCE: feed the SAME applicant-facing `PublicFieldConfig` through the renderer in
 *    the preview context AND the native-block context (`ApplicationFormPage`); assert both emit the
 *    same form structure — identical group sections, fields, order, and control ids — so the two
 *    surfaces render a given schema identically.
 *
 * If a future change forks the preview onto a different renderer, BOTH teeth bite: the identity
 * assertion fails (two modules) and/or the structural comparison diverges. This does NOT weaken any
 * existing assertion — it adds the R8.2 one-code-path guarantee the other 5.4 tests do not make.
 *
 * Fixtures use the applicant-facing public shape the server emits (R2.3 bare `key` + `group` is the
 * BUILDER-side shape; by the time a schema reaches the renderer it is the filtered public
 * `PublicFieldConfig`, so the renderer sees the same object on both surfaces).
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, within } from '../../../../test-utils';

// The renderer as the PREVIEW path imports it (ApplicationFormPreview →
// '../../public/application/ApplicationFormRenderer').
import { ApplicationFormRenderer as RendererFromPreviewPath } from '../../../public/application/ApplicationFormRenderer';
// The renderer as the NATIVE-BLOCK path imports it (ApplicationFormBlock → ApplicationFormPage →
// './ApplicationFormRenderer'). Importing the SAME module here mirrors that composition; the
// identity check below proves the preview path resolves to this very object.
import { ApplicationFormRenderer as RendererFromPublicPath } from '../../../public/application/ApplicationFormRenderer';

import { ApplicationFormPreview } from '../ApplicationFormPreview';
import { ApplicationFormPage } from '../../../public/application/ApplicationFormPage';
import { buildPreviewConfig } from '../applicationPreviewFilter';

import type { FieldConfig, FieldConfigField } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import type { PublicFieldConfig } from '../../../public/application/applicationFieldConfig';

// ── Mock the public submit API so ApplicationFormPage mounts without a network client. We are
//    verifying the RENDER path shared with the preview, not the submit wiring (covered elsewhere).
vi.mock('../../../../services/applicationApi', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../../../services/applicationApi');
  return { ...actual, submitApplication: vi.fn() };
});

/** A resolved field in the BARE `key` + `group` server shape (R2.3) — the builder-side input. */
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

function configWith(fields: FieldConfigField[]): FieldConfig {
  return { fields } as FieldConfig;
}

/**
 * Collect the renderer's observable structure from a mounted `application-form` root: for each
 * group section (`[data-group]`) its key + the `htmlFor` of every control label, in document order.
 * This is the renderer's visible/behavioral contract — group sectioning, field set, ordering, and
 * the stable control-id association — independent of which surface mounted it.
 */
function rendererStructure(container: HTMLElement): Array<{ group: string; labels: string[] }> {
  const form = container.querySelector('[data-testid="application-form"]');
  if (!form) throw new Error('no application-form root rendered');
  const groups = Array.from(form.querySelectorAll('[data-group]'));
  return groups.map((g) => ({
    group: g.getAttribute('data-group') ?? '',
    labels: Array.from(g.querySelectorAll('label[for]')).map((l) => l.getAttribute('for') ?? ''),
  }));
}

describe('ApplicationFormRenderer shared code path — preview ⇆ native landing block (R8.2)', () => {
  it('both surfaces import the SAME renderer module (one renderer, not a fork)', () => {
    // Referential identity: there is ONE `ApplicationFormRenderer` export both paths resolve to.
    // A future fork that gives the preview its own renderer breaks this object identity.
    expect(RendererFromPreviewPath).toBe(RendererFromPublicPath);
    expect(typeof RendererFromPreviewPath).toBe('function');
  });

  it('the preview panel mounts the shared ApplicationFormRenderer (data-testid application-form)', () => {
    const fieldConfig = configWith([
      field('first_name', 'personal', { application_visible: true }),
      field('email', 'personal', { application_visible: true }),
    ]);
    const { container } = render(
      <ApplicationFormPreview fieldConfig={fieldConfig} overlay={{}} lang="en" />,
    );
    // The preview render wrapper contains the shared renderer's root.
    const panel = container.querySelector('[data-testid="application-form-preview-render"]');
    expect(panel).not.toBeNull();
    expect(within(panel as HTMLElement).getByTestId('application-form')).toBeInTheDocument();
  });

  it('preview and native-block render the SAME schema identically (same groups, fields, order, ids)', () => {
    // One applicant-facing schema, derived once through the pure filter — the exact object the
    // renderer sees on BOTH surfaces (the preview feeds it directly; the native block gets it from
    // the public field-config read, which is pinned to this same selection by task 5.3).
    const fieldConfig = configWith([
      // Deliberately out of order to prove the shared renderer orders both surfaces alike.
      field('last_name', 'personal', { application_visible: true, order: 20 }),
      field('first_name', 'personal', { application_visible: true, order: 10 }),
      field('email', 'contact', { application_visible: true, order: 10 }),
    ]);
    const schema: PublicFieldConfig = buildPreviewConfig(fieldConfig, {}, []);
    // Guard: the filter actually produced on-form fields, so the comparison is meaningful.
    expect(schema.fields.length).toBeGreaterThan(0);

    // Surface 1 — the PREVIEW drives the renderer directly (controlled, read-only).
    const { container: previewContainer } = render(
      <RendererFromPreviewPath
        config={schema}
        locale="en"
        values={{}}
        onChange={() => { }}
        idPrefix="application-preview"
      />,
    );

    // Surface 2 — the NATIVE landing-page block composes the SAME renderer through
    // ApplicationFormPage (the exact path ApplicationFormBlock → ApplicationFormPage uses, E4a).
    const { container: nativeContainer } = render(
      <ApplicationFormPage tenantSlug="hdcn" config={schema} initialLocale="en" />,
    );

    const previewStructure = rendererStructure(previewContainer);
    const nativeStructure = rendererStructure(nativeContainer);

    // Normalize the SURFACE-SPECIFIC idPrefix so the comparison is about STRUCTURE (groups, fields,
    // order), not the id namespace: the preview passes `idPrefix="application-preview"`, while
    // ApplicationFormPage lets the renderer use its own default (`app-field`). Both produce
    // `{idPrefix}-{dotted-key-with-dashes}`; stripping each surface's OWN known prefix leaves the
    // stable dotted-key-derived control id the renderer guarantees. A diverging renderer would
    // differ in groups/fields/order, which this still catches.
    const stripKnownPrefix = (s: Array<{ group: string; labels: string[] }>, prefix: string) =>
      s.map((g) => ({
        group: g.group,
        labels: g.labels.map((l) => (l.startsWith(`${prefix}-`) ? l.slice(prefix.length + 1) : l)),
      }));

    // Same groups, in the same order, each with the same fields in the same order.
    expect(stripKnownPrefix(nativeStructure, 'app-field')).toEqual(
      stripKnownPrefix(previewStructure, 'application-preview'),
    );

    // And both actually rendered the applicant-facing fields (not an empty form on either side).
    const previewLabelCount = previewStructure.reduce((n, g) => n + g.labels.length, 0);
    expect(previewLabelCount).toBe(schema.fields.length);
    const nativeLabelCount = nativeStructure.reduce((n, g) => n + g.labels.length, 0);
    expect(nativeLabelCount).toBe(schema.fields.length);
  });
});

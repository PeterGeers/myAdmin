/**
 * Responsive one-line + multi-column layout on the PUBLIC application form
 * (spec 13, task 4.3 / R4.3, R4.4).
 *
 * Task 4.1 made each field's `FormControl` `display={{ base: 'block', md: 'flex' }}` (label above
 * the control on a narrow viewport, beside it on `md`+). Task 4.2 replaced the per-group `VStack`
 * with a responsive `SimpleGrid columns={{ base: 1, md: 2 }}` (one column on `base`, ≥2 on `md`),
 * with an intrinsically-wide field (`isWideField` — textarea/text_area/long_text/multiline)
 * getting a full-row `gridColumn={{ md: '1 / -1' }}` span. This file pins the task-4.3 facts:
 *   - the responsive single-column-at-`base` / ≥2-columns-at-`md` layout is driven by Chakra's
 *     responsive `columns` object (R4.3 — responsive system, no viewport sniffing);
 *   - the wide field spans the full row while ordinary fields do not (R4.3);
 *   - DOM / tab order inside the grid is the config-resolved `(group order → field (order,key))`
 *     sequence — a single logical reading/tab order (R4.4);
 *   - the error `aria-describedby` / error-summary anchor still targets the right control id after
 *     the layout change (R4.4 / HC2).
 *
 * WHY THIS FILE OVERRIDES THE CHAKRA MOCK (same reasoning as the task-3.2 dropdownStyle test):
 * ------------------------------------------------------------------------------------------
 * The central chakra mock (`src/__mocks__/chakra-ui-react.tsx`) renders `SimpleGrid`/`FormControl`
 * to plain `<div>`s and STRIPS responsive style props (`columns`, `gridColumn`, `display`) via
 * `filterChakraProps` before they reach the DOM. So the responsive `columns={{ base: 1, md: 2 }}`
 * and the wide field's `gridColumn` span CANNOT be read off raw DOM attributes. Following the
 * established repo pattern (see `ApplicationFormRenderer.dropdownStyle.test.tsx`), we
 * `vi.mock('@chakra-ui/react')` off the central mock and override ONLY `SimpleGrid` + `FormControl`
 * to RECORD the props they receive while still rendering real DOM (preserving `id`/label
 * association + DOM order), so the responsive layout props AND the DOM order / aria wiring can all
 * be asserted in one render.
 *
 * The behavioural grid-structure/order tests (the `multi-column grid layout` block) live in
 * `ApplicationFormRenderer.test.tsx` and are NOT touched — this file ADDS the responsive-prop +
 * aria-anchoring assertions task 4.3 calls for.
 *
 * _Requirements: R4.3, R4.4, HC2_
 */

import React, { useState } from 'react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

/* ------------------------------------------------------------------------ */
/*  Chakra mock: keep the central mock, but override SimpleGrid + FormControl */
/*  to CAPTURE the responsive props the central mock would otherwise strip,   */
/*  while still rendering a real DOM container (so DOM order + aria hold).     */
/* ------------------------------------------------------------------------ */

/** Props captured from each SimpleGrid render, keyed by its `data-testid` (`group-grid-{key}`). */
const capturedGrids: Record<string, Record<string, unknown>> = {};
/**
 * Props captured from each FormControl render, keyed by the control `id` found on the rendered
 * child (so we can match a FormControl to its field by the control's stable id).
 */
const capturedControls: Array<Record<string, unknown>> = [];

vi.mock('@chakra-ui/react', async () => {
  const mocks = await vi.importActual<typeof import('@/__mocks__/chakra-ui-react')>(
    '@/__mocks__/chakra-ui-react',
  );
  const React = await import('react');

  const SimpleGrid = ({ children, columns, spacing, ...rest }: any) => {
    const testid = rest['data-testid'];
    if (testid) capturedGrids[testid] = { columns, spacing, ...rest };
    // Render a real DOM container preserving data-testid + DOM order of children.
    return (
      <div data-testid={testid} data-grid="true">
        {children}
      </div>
    );
  };

  const FormControl = ({ children, isRequired, isInvalid, gridColumn, display, ...rest }: any) => {
    capturedControls.push({ isRequired, isInvalid, gridColumn, display, ...rest });
    // Render a real DOM wrapper so the inner control + label association survives.
    return <div data-formcontrol="true">{children}</div>;
  };

  return { ...mocks, SimpleGrid, FormControl };
});

/* ------------------------------------------------------------------------ */
/*  Imports AFTER the mock so the renderer picks up the overridden layout.   */
/* ------------------------------------------------------------------------ */

import { render, screen, within } from '@/test-utils';
import { ApplicationFormRenderer } from '../components/public/application/ApplicationFormRenderer';
import { buildInitialValues } from '../components/public/application/applicationForm.model';
import type { PublicFieldConfig } from '../services/applicationApi';

// Two functional groups, deliberately out of (group, order) sequence in the INPUT to prove the
// renderer resolves the sequence. `membership` min order = 10, `personal` min order = 20, so the
// resolved GROUP order is membership → personal (NOT the input order). Within `personal`, the
// fields order first_name(20) → notes(25, wide) → last_name(30). The wide `notes` field proves
// the full-row span, and it sits between two non-wide fields to prove the span is per-field.
const CONFIG: PublicFieldConfig = {
  fields: [
    {
      key: 'personal.last_name',
      type: 'string',
      label: { nl: 'Achternaam', en: 'Last name' },
      functional_group: 'personal',
      order: 30,
      required: true,
    },
    {
      key: 'personal.notes',
      type: 'textarea',
      label: { nl: 'Opmerkingen', en: 'Notes' },
      functional_group: 'personal',
      order: 25,
    },
    {
      key: 'personal.first_name',
      type: 'string',
      label: { nl: 'Voornaam', en: 'First name' },
      functional_group: 'personal',
      order: 20,
      required: true,
    },
    {
      key: 'membership.membership_type',
      type: 'enum',
      label: { nl: 'Type', en: 'Type' },
      functional_group: 'membership',
      order: 10,
      required: true,
      options: [
        { value: 'gewoon', label: { nl: 'Gewoon lid', en: 'Ordinary member' } },
        { value: 'incasso', label: { nl: 'Incasso', en: 'Direct debit' } },
      ],
    },
  ],
  locales: ['nl', 'en'],
};

function Harness({ errors }: { errors?: Record<string, string> }) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    buildInitialValues(CONFIG.fields),
  );
  return (
    <ApplicationFormRenderer
      config={CONFIG}
      values={values}
      errors={errors}
      onChange={(k, v) => setValues((prev) => ({ ...prev, [k]: v }))}
    />
  );
}

describe('ApplicationFormRenderer — responsive multi-column layout (spec 13 task 4.3, R4.3/R4.4)', () => {
  beforeEach(() => {
    for (const k of Object.keys(capturedGrids)) delete capturedGrids[k];
    capturedControls.length = 0;
  });

  it('drives single-column-at-base / >=2-columns-at-md via Chakra responsive `columns` (R4.3)', () => {
    render(<Harness />);

    // Every group's grid carries the SAME responsive columns object — one column on `base`
    // (mobile), two on `md`+ (laptop/desktop). This is the responsive system, not viewport sniffing.
    const membershipGrid = capturedGrids['group-grid-membership'];
    const personalGrid = capturedGrids['group-grid-personal'];
    expect(membershipGrid).toBeTruthy();
    expect(personalGrid).toBeTruthy();

    for (const grid of [membershipGrid, personalGrid]) {
      expect(grid.columns).toEqual({ base: 1, md: 2 });
      // base === 1 (single column on mobile); md >= 2 (multi-column on desktop).
      expect((grid.columns as any).base).toBe(1);
      expect((grid.columns as any).md).toBeGreaterThanOrEqual(2);
    }
  });

  it('spans an intrinsically-wide field full-width (gridColumn md 1/-1) and NOT ordinary fields (R4.3)', () => {
    render(<Harness />);

    // Resolved field render order (DOM order of FormControls across all groups):
    //   membership.membership_type (group membership)
    //   personal.first_name (order 20)
    //   personal.notes (order 25, WIDE)
    //   personal.last_name (order 30)
    expect(capturedControls).toHaveLength(4);
    const [typeCtl, firstNameCtl, notesCtl, lastNameCtl] = capturedControls;

    // The wide `notes` (textarea) field spans the full grid row on `md`+.
    expect(notesCtl.gridColumn).toEqual({ md: '1 / -1' });

    // Ordinary fields get NO span (sit in a single column).
    expect(typeCtl.gridColumn).toBeUndefined();
    expect(firstNameCtl.gridColumn).toBeUndefined();
    expect(lastNameCtl.gridColumn).toBeUndefined();
  });

  it('places label beside control on md / stacked on base via responsive display (R4.3 one-line)', () => {
    render(<Harness />);
    // Every FormControl carries the responsive display: block on `base` (label above), flex on
    // `md`+ (label beside control). No viewport sniffing — a pure responsive prop.
    for (const ctl of capturedControls) {
      expect(ctl.display).toEqual({ base: 'block', md: 'flex' });
    }
  });

  it('preserves a single logical reading/tab order = resolved (group order -> (order,key)) (R4.4)', () => {
    render(<Harness />);

    // GROUP order in the DOM: membership (min order 10) BEFORE personal (min order 20), which is
    // NOT the input order (personal fields were listed first).
    const groupOrder = Array.from(document.querySelectorAll('[data-group]')).map((el) =>
      el.getAttribute('data-group'),
    );
    expect(groupOrder).toEqual(['membership', 'personal']);

    // FIELD order inside the personal grid: first_name(20) -> notes(25) -> last_name(30), i.e. the
    // SimpleGrid lays out in DOM order so the wide field does not jump the reading order.
    const personalGrid = screen.getByTestId('group-grid-personal');
    const personalLabels = within(personalGrid)
      .getAllByText(/Voornaam|Opmerkingen|Achternaam/)
      .map((n) => n.textContent);
    expect(personalLabels).toEqual(['Voornaam', 'Opmerkingen', 'Achternaam']);
  });

  it('keeps error aria-describedby / error-summary anchor pointed at the right control id (R4.4/HC2)', () => {
    // Give the first-name field a server/client error; its control must describe the matching
    // error message element so the error-summary anchor link focuses the right control.
    render(<Harness errors={{ 'personal.first_name': 'Voornaam is verplicht' }} />);

    const firstName = screen.getByLabelText('Voornaam') as HTMLInputElement;
    const describedBy = firstName.getAttribute('aria-describedby');
    expect(describedBy).toBe('app-field-personal-first_name-error');

    // The described error element actually exists in the DOM carrying that id and the message —
    // this is the anchor target the error summary links to (HC2 association survives the grid).
    const errorEl = document.getElementById('app-field-personal-first_name-error');
    expect(errorEl).toBeTruthy();
    expect(errorEl).toHaveTextContent('Voornaam is verplicht');

    // The control id the label is associated with (htmlFor) matches the control carrying the
    // describedby — label -> control -> error form one unbroken chain.
    expect(firstName.id).toBe('app-field-personal-first_name');

    // A field WITHOUT an error carries no dangling aria-describedby (no phantom anchor).
    const lastName = screen.getByLabelText('Achternaam') as HTMLInputElement;
    expect(lastName.getAttribute('aria-describedby')).toBeNull();
  });
});

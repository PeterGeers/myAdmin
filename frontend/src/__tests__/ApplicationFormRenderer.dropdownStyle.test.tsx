/**
 * De-emphasized dropdown styling on the PUBLIC application form (spec 13, task 3.2 / R3).
 *
 * Task 3.1 added a shared `PUBLIC_FORM_CONTROL_STYLE` constant in `ApplicationFormRenderer.tsx`
 * (an `outline` variant, neutral `borderColor` gray.300, `focusBorderColor` blue.500) and spread
 * it UNIFORMLY onto BOTH the text `<Input>` and the enum `<Select>`, so the two controls read at
 * the SAME visual weight with the accent reserved for focus (R3.1/R3.2/R3.3).
 *
 * WHY THIS IS A SEPARATE FILE (and why it overrides the chakra mock):
 * -------------------------------------------------------------------
 * The central chakra mock (`src/__mocks__/chakra-ui-react.tsx`) renders `Input`/`Select` to plain
 * DOM elements and STRIPS style props (`variant`, `borderColor`, `focusBorderColor`) via
 * `filterChakraProps` so they never reach the DOM. Asserting on raw DOM attributes is therefore
 * impossible for exactly the props R3 cares about. The established repo pattern (see
 * `members/MembersModalBody.responsive.test.tsx`) is to `vi.mock('@chakra-ui/react')` off the
 * central mock and override only the component(s) under test. Here we override `Input` and
 * `Select` to RECORD the props they receive (while still rendering a real DOM element, preserving
 * `id`/label association) so we can assert the shared styling reached BOTH controls equally and
 * the focus affordance is present — the facts R3 asserts.
 *
 * The existing behavioural tests (grouping, ordering, locale, show_when, headings, round-trip,
 * MSW) live in `ApplicationFormRenderer.test.tsx` and are NOT touched — this file only ADDS the
 * R3 styling assertions.
 *
 * _Requirements: R3.1, R3.2, R3.3_
 */

import React, { useState } from 'react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

/* ------------------------------------------------------------------------ */
/*  Chakra mock: keep the central mock, but override Input + Select to       */
/*  CAPTURE the props they receive (the style props the central mock would   */
/*  otherwise strip), while still rendering a real DOM control.              */
/* ------------------------------------------------------------------------ */

/** Props captured from the LAST render of each control kind, keyed by field `name`. */
const captured: {
  input: Record<string, Record<string, unknown>>;
  select: Record<string, Record<string, unknown>>;
} = { input: {}, select: {} };

vi.mock('@chakra-ui/react', async () => {
  const mocks = await vi.importActual<typeof import('@/__mocks__/chakra-ui-react')>(
    '@/__mocks__/chakra-ui-react',
  );
  const React = await import('react');

  const Input = ({ value, onChange, type, name, ...rest }: any) => {
    // Record EVERY prop (incl. the style props the central mock strips) keyed by field name.
    captured.input[name] = { value, onChange, type, name, ...rest };
    return (
      <input
        id={rest.id}
        name={name}
        type={type}
        value={value}
        onChange={onChange}
        aria-required={rest['aria-required']}
        aria-invalid={rest['aria-invalid']}
      />
    );
  };

  const Select = ({ children, value, onChange, name, ...rest }: any) => {
    captured.select[name] = { value, onChange, name, ...rest };
    return (
      <select
        id={rest.id}
        name={name}
        value={value}
        onChange={onChange}
        aria-required={rest['aria-required']}
        aria-invalid={rest['aria-invalid']}
      >
        {children}
      </select>
    );
  };

  return { ...mocks, Input, Select };
});

/* ------------------------------------------------------------------------ */
/*  Imports AFTER the mock so the renderer picks up the overridden controls. */
/* ------------------------------------------------------------------------ */

import { render } from '@/test-utils';
import { ApplicationFormRenderer } from '../components/public/application/ApplicationFormRenderer';
import { buildInitialValues } from '../components/public/application/applicationForm.model';
import type { PublicFieldConfig } from '../services/applicationApi';

// A config with BOTH a text input (string) and a dropdown (enum) in one group, so one render
// exercises both control kinds and we can compare the styling they each received.
const CONFIG: PublicFieldConfig = {
  fields: [
    {
      key: 'personal.first_name',
      type: 'string',
      label: { nl: 'Voornaam', en: 'First name' },
      functional_group: 'personal',
      order: 10,
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

function Harness() {
  const [values, setValues] = useState<Record<string, string>>(() =>
    buildInitialValues(CONFIG.fields),
  );
  return (
    <ApplicationFormRenderer
      config={CONFIG}
      values={values}
      onChange={(k, v) => setValues((prev) => ({ ...prev, [k]: v }))}
    />
  );
}

/** The style keys R3 cares about — the shared control styling both controls must carry. */
const STYLE_KEYS = ['variant', 'borderColor', 'focusBorderColor'] as const;

function styleSlice(props: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(STYLE_KEYS.map((k) => [k, props[k]]));
}

describe('ApplicationFormRenderer — de-emphasized dropdown styling (spec 13 task 3.2, R3)', () => {
  beforeEach(() => {
    captured.input = {};
    captured.select = {};
  });

  it('applies the SAME shared control styling to the text input and the dropdown (R3.1/R3.2)', () => {
    render(<Harness />);

    const inputProps = captured.input['personal.first_name'];
    const selectProps = captured.select['membership.membership_type'];
    expect(inputProps).toBeTruthy();
    expect(selectProps).toBeTruthy();

    // Both controls received the style props at all (not stripped before reaching them)...
    for (const key of STYLE_KEYS) {
      expect(inputProps).toHaveProperty(key);
      expect(selectProps).toHaveProperty(key);
    }

    // ...and they are IDENTICAL — the softening is uniform, not a per-field one-off (R3.2).
    expect(styleSlice(selectProps)).toEqual(styleSlice(inputProps));
  });

  it('uses a neutral resting weight: outline variant + neutral border, not a saturated accent (R3.1)', () => {
    render(<Harness />);

    const selectProps = captured.select['membership.membership_type'];
    // An outline variant with a neutral grey resting border — the dominant orange accent is gone.
    expect(selectProps.variant).toBe('outline');
    expect(selectProps.borderColor).toBe('gray.300');
    // Same neutral resting weight on the text input.
    expect(captured.input['personal.first_name'].borderColor).toBe('gray.300');
  });

  it('reserves the accent for FOCUS: both controls carry a visible focusBorderColor (R3.3/HC2)', () => {
    render(<Harness />);

    // Spec 13 R3.2: the orange accent is RESERVED FOR FOCUS. `focusBorderColor` drives Chakra's
    // focus border + boxShadow focus ring, so the control stays clearly discoverable on focus
    // (visible focus state) while quiet/neutral at rest on the white page.
    expect(captured.input['personal.first_name'].focusBorderColor).toBe('orange.400');
    expect(captured.select['membership.membership_type'].focusBorderColor).toBe('orange.400');
  });

  it('keeps the dropdown affordance: the select does NOT override its default chevron icon (R3.1)', () => {
    render(<Harness />);
    // We never pass a custom `icon`, so the Select keeps its default chevron — it still reads as a
    // dropdown even with the softened resting styling.
    expect(captured.select['membership.membership_type']).not.toHaveProperty('icon');
  });

  it('scopes the styling to the controls only — no global theme override is applied (R3 scope)', () => {
    render(<Harness />);
    // The styling is spread onto the two controls at the renderer boundary; it is NOT a
    // colorScheme/theme swap. Neither control carries an app-wide `colorScheme` accent, confirming
    // the rest of the app theme is untouched.
    expect(captured.input['personal.first_name']).not.toHaveProperty('colorScheme');
    expect(captured.select['membership.membership_type']).not.toHaveProperty('colorScheme');
  });
});

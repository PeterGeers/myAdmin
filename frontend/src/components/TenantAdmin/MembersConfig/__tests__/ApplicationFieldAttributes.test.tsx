/**
 * Tests for the per-field application attributes panel (spec 11, task 3.1; R3.1–R3.5 / R4.1,
 * design §3/§3.1/§4/§10).
 *
 * This is the change-with-tests pairing for the new `ApplicationFieldAttributes` behavior (the full
 * dedicated suite is task 3.5). It asserts the R3/R4 contract the component owns:
 *  - the application-required toggle writes `application_required`, TIGHTENS an optional field, and
 *    is DISABLED/forced-on for a platform-required field (R3.1);
 *  - the enum subset picker is offered ONLY on a field with choices, is constrained to the field's
 *    OWN choices, writes a proper subset to `application_choices`, and stores the full set as `null`
 *    (R3.2 / R4.1);
 *  - the format dropdown offers ONLY the platform-known `field_format_tokens` and clears to `null`
 *    (R3.3);
 *  - all controls are gated on `application_visible` (R3.4);
 *  - every change is a pure overlay transform bubbled via `onChange` — no network (R3.5 / §3.1).
 *
 * The component takes `lang` directly (no i18n), so a plain Chakra render suffices.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '../../../../test-utils';
import type { FieldConfig } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import type { MembershipType } from '../../../../types/members';
import { ApplicationFieldAttributes } from '../ApplicationFieldAttributes';
import { findField } from '../overlayModel';

/* ------------------------------------------------------------------ */
/*  Fixture — an optional enum field, a platform-required field, and   */
/*  the platform-known format tokens.                                  */
/* ------------------------------------------------------------------ */
const FIELD_CONFIG: FieldConfig = {
  field_format_tokens: ['EMAIL', 'IBAN'],
  functional_groups: [{ key: 'contact', order: 1 }],
  fields: [
    // An optional enum (tenant-added) field with three own choices.
    {
      key: 'preference',
      functional_group: 'contact',
      type: 'enum',
      provenance: 'tenant_added',
      required: false,
      label: { en: 'Preference', nl: 'Voorkeur' },
      options: [
        { value: 'a', label: { en: 'A', nl: 'A' } },
        { value: 'b', label: { en: 'B', nl: 'B' } },
        { value: 'c', label: { en: 'C', nl: 'C' } },
      ],
    },
    // A platform-required base field (no choices) — required toggle forced on + disabled. Its
    // storage `group` drives the origin-aware overlay key (`{group}.{key}` → `contact.email`).
    {
      key: 'email',
      group: 'contact',
      functional_group: 'contact',
      type: 'string',
      origin: 'fixed',
      provenance: 'base',
      required: true,
      label: { en: 'Email', nl: 'E-mail' },
    },
    // The membership-type field (R4, task 3.3). It is NOT platform-required and carries static
    // served options, but when exposed it is forced required and its subset is the LIVE catalog
    // (`membershipTypeCatalog`), NOT these static options.
    {
      key: 'membership_type',
      group: 'membership',
      functional_group: 'membership',
      type: 'reference',
      origin: 'fixed',
      provenance: 'base',
      required: false,
      label: { en: 'Type', nl: 'Type' },
      options: [{ value: 'stale', label: { en: 'Stale', nl: 'Verouderd' } }],
    },
  ],
};

/** The tenant's LIVE membership-type catalog (the subset vocabulary for the membership-type field). */
const CATALOG: MembershipType[] = [
  { type_code: 'regular', label: { en: 'Regular', nl: 'Gewoon' }, active: true, order: 1 },
  { type_code: 'honorary', label: { en: 'Honorary', nl: 'Erelid' }, active: true, order: 2 },
  { type_code: 'staff', label: { en: 'Staff', nl: 'Staf' }, active: false, order: 3 },
];

function renderAttrs(
  selectedKey: string | null,
  overlay: MembersConfigValue = {},
  onChange = vi.fn(),
  catalog: MembershipType[] | null = null,
) {
  const utils = render(
    <ApplicationFieldAttributes
      fieldConfig={FIELD_CONFIG}
      selectedKey={selectedKey}
      overlay={overlay}
      onChange={onChange}
      membershipTypeCatalog={catalog}
      lang="en"
    />,
  );
  return { ...utils, onChange };
}

/** An overlay with the given field already on the form (so the controls are ungated). */
function onFormOverlay(key: string, extra: Record<string, unknown> = {}): MembersConfigValue {
  return { fields: { [key]: { application_visible: true, ...extra } } } as MembersConfigValue;
}

/** A platform-required base field on the form writes under `fixed_overrides[{group}.{key}]`. */
function overrideOnFormOverlay(overlayKey: string): MembersConfigValue {
  return { fixed_overrides: { [overlayKey]: { application_visible: true } } } as MembersConfigValue;
}

/** The membership-type (base) field on the form, authored under `fixed_overrides[membership.membership_type]`. */
function membershipOnFormOverlay(extra: Record<string, unknown> = {}): MembersConfigValue {
  return {
    fixed_overrides: {
      'membership.membership_type': { application_visible: true, ...extra },
    },
  } as MembersConfigValue;
}

/** The actual checkbox/switch INPUT under a Chakra control testid (the testid is on the wrapper). */
function inputUnder(testId: string): HTMLInputElement {
  const el = screen.getByTestId(testId);
  const input = el.querySelector('input');
  if (!input) throw new Error(`no input under ${testId}`);
  return input as HTMLInputElement;
}

describe('ApplicationFieldAttributes — gating (R3.4)', () => {
  it('shows a hint and no controls when nothing is selected', () => {
    renderAttrs(null);
    expect(screen.getByTestId('application-field-attributes-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('application-field-required-toggle')).not.toBeInTheDocument();
  });

  it('shows a "put on the form first" hint for a selected field NOT on the form', () => {
    renderAttrs('preference', {});
    expect(screen.getByTestId('application-field-attributes-not-on-form')).toBeInTheDocument();
    expect(screen.queryByTestId('application-field-required-toggle')).not.toBeInTheDocument();
  });

  it('shows the controls once the field is on the form', () => {
    renderAttrs('preference', onFormOverlay('preference'));
    expect(screen.getByTestId('application-field-required-toggle')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-format')).toBeInTheDocument();
  });
});

describe('ApplicationFieldAttributes — application-required (R3.1)', () => {
  it('tightens an optional field to required (writes application_required=true)', () => {
    const { onChange } = renderAttrs('preference', onFormOverlay('preference'));
    fireEvent.click(screen.getByTestId('application-field-required-toggle'));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'preference')?.field.application_required).toBe(true);
  });

  it('is forced ON and DISABLED for a platform-required field (no relax)', () => {
    const { onChange } = renderAttrs('email', overrideOnFormOverlay('contact.email'));
    const toggle = screen.getByTestId('application-field-required-toggle');
    // Forced ON — a platform-required field is always required on the form (R3.1).
    expect(toggle).toBeChecked();
    // The platform-required provenance is surfaced so the admin understands why it cannot relax.
    expect(screen.getByText('platform-required')).toBeInTheDocument();
    // And the no-relax guard holds: a click can NEVER write a relax to the overlay (R3.1 / R8.1c).
    fireEvent.click(toggle);
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe('ApplicationFieldAttributes — enum subset picker (R3.2 / R4.1)', () => {
  it('is offered ONLY on a field with choices (absent for a plain string field)', () => {
    const { rerender } = renderAttrs('preference', onFormOverlay('preference'));
    expect(screen.getByTestId('application-field-subset')).toBeInTheDocument();
    rerender(
      <ApplicationFieldAttributes
        fieldConfig={FIELD_CONFIG}
        selectedKey="email"
        overlay={{ fixed_overrides: { 'contact.email': { application_visible: true } } } as MembersConfigValue}
        onChange={vi.fn()}
        lang="en"
      />,
    );
    expect(screen.queryByTestId('application-field-subset')).not.toBeInTheDocument();
  });

  it('seeds all of the field\u2019s own choices as selected (full set) by default', () => {
    renderAttrs('preference', onFormOverlay('preference'));
    expect(inputUnder('application-field-subset-option-a')).toBeChecked();
    expect(inputUnder('application-field-subset-option-b')).toBeChecked();
    expect(inputUnder('application-field-subset-option-c')).toBeChecked();
  });

  it('unchecking one choice writes a proper SUBSET (the remaining field choices) to application_choices', () => {
    const { onChange } = renderAttrs('preference', onFormOverlay('preference'));
    fireEvent.click(screen.getByTestId('application-field-subset-option-b'));
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    // Only valid field choices, in the field's own order, minus the unchecked one.
    expect(findField(next, 'preference')?.field.application_choices).toEqual(['a', 'c']);
  });

  it('re-selecting all choices stores the FULL set as null (not a list)', () => {
    // Start from an authored subset of ['a'] and tick 'b' and 'c' back on.
    const seeded = onFormOverlay('preference', { application_choices: ['a'] });
    const { onChange } = renderAttrs('preference', seeded);
    // 'a' is checked, 'b'/'c' are not.
    expect(inputUnder('application-field-subset-option-a')).toBeChecked();
    expect(inputUnder('application-field-subset-option-b')).not.toBeChecked();
    fireEvent.click(inputUnder('application-field-subset-option-b'));
    // After ticking 'b', the subset is ['a','b'] — still a proper subset, so a list.
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'preference')?.field.application_choices).toEqual(['a', 'b']);
  });

  it('only offers values that are the field\u2019s own choices (no out-of-set option)', () => {
    renderAttrs('preference', onFormOverlay('preference'));
    // Exactly the three field choices are rendered — nothing else is selectable.
    expect(screen.getByTestId('application-field-subset-option-a')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-subset-option-c')).toBeInTheDocument();
    expect(screen.queryByTestId('application-field-subset-option-x')).not.toBeInTheDocument();
  });

  it('a WRITTEN subset stays \u2286 the field\u2019s own choices — a stale out-of-vocabulary authored value is pruned, never echoed back (R3.2 edge)', () => {
    // A prior session authored a subset carrying a value ('z') that is NO LONGER one of the field's
    // choices (the enum vocabulary was later narrowed on the Field-configuration tab). The picker
    // offers only the field's CURRENT choices, so 'z' is not even rendered as an option.
    const seeded = onFormOverlay('preference', { application_choices: ['a', 'z'] });
    const { onChange } = renderAttrs('preference', seeded);
    expect(screen.queryByTestId('application-field-subset-option-z')).not.toBeInTheDocument();
    // Only 'a' is ticked (the authored subset); 'b'/'c' are not. The stale 'z' is invisible.
    expect(inputUnder('application-field-subset-option-a')).toBeChecked();
    expect(inputUnder('application-field-subset-option-b')).not.toBeChecked();

    // Ticking 'b' back on writes a list rebuilt STRICTLY from the field's own choices in field
    // order — the stale 'z' is dropped, so the persisted subset stays ⊆ the field's choices.
    fireEvent.click(inputUnder('application-field-subset-option-b'));
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    const written = findField(next, 'preference')?.field.application_choices as string[];
    expect(written).toEqual(['a', 'b']);
    // The invariant made explicit: every written value is a real field choice (⊆ choices).
    const fieldChoiceValues = ['a', 'b', 'c'];
    expect(written.every((v) => fieldChoiceValues.includes(v))).toBe(true);
    expect(written).not.toContain('z');
  });
});

describe('ApplicationFieldAttributes — format dropdown (R3.3)', () => {
  it('offers ONLY the platform-known tokens plus "none"', () => {
    renderAttrs('preference', onFormOverlay('preference'));
    const select = screen.getByTestId('application-field-format-select') as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(['', 'EMAIL', 'IBAN']);
  });

  it('selecting a known token writes format={checker}', () => {
    const { onChange } = renderAttrs('preference', onFormOverlay('preference'));
    fireEvent.change(screen.getByTestId('application-field-format-select'), {
      target: { value: 'EMAIL' },
    });
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'preference')?.field.format).toEqual({ checker: 'EMAIL' });
  });

  it('selecting "none" clears format to null', () => {
    const seeded = onFormOverlay('preference', { format: { checker: 'EMAIL' } });
    const { onChange } = renderAttrs('preference', seeded);
    fireEvent.change(screen.getByTestId('application-field-format-select'), {
      target: { value: '' },
    });
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'preference')?.field.format).toBeNull();
  });
});

/* ------------------------------------------------------------------ */
/*  Membership-type coherence (R4, task 3.3): forced-required, subset  */
/*  over the LIVE catalog, empty/unknown-subset validation.            */
/* ------------------------------------------------------------------ */
describe('ApplicationFieldAttributes — membership-type coherence (R4, task 3.3)', () => {
  it('forces the exposed membership-type field application-required (forced ON + disabled, R4.2)', () => {
    const { onChange } = renderAttrs(
      'membership_type',
      membershipOnFormOverlay(),
      vi.fn(),
      CATALOG,
    );
    const toggle = screen.getByTestId('application-field-required-toggle');
    // Forced ON even though the field is NOT platform-required — an exposed membership-type field
    // is always application-required (spec 10 D21 / R4.2).
    expect(toggle).toBeChecked();
    expect(screen.getByText('membership-type')).toBeInTheDocument();
    // The no-relax guard holds: clicking the forced toggle never writes a relax to the overlay.
    fireEvent.click(toggle);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('sources the subset from the LIVE catalog, NOT the field\u2019s static served options (R4.1)', () => {
    renderAttrs('membership_type', membershipOnFormOverlay(), vi.fn(), CATALOG);
    // Live catalog codes are offered (incl. the retired `staff` — the server is the authority on
    // acceptability, R4.3); the field's stale static option is NOT.
    expect(screen.getByTestId('application-field-subset-option-regular')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-subset-option-honorary')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-subset-option-staff')).toBeInTheDocument();
    expect(screen.queryByTestId('application-field-subset-option-stale')).not.toBeInTheDocument();
  });

  it('writes a proper subset of LIVE catalog codes to application_choices (R4.1)', () => {
    const { onChange } = renderAttrs(
      'membership_type',
      membershipOnFormOverlay(),
      vi.fn(),
      CATALOG,
    );
    // Start with the full catalog selected; unchecking `staff` leaves the proper subset. A base
    // field authors under `fixed_overrides[{group}.{key}]`, so the overlay entry key is dotted.
    fireEvent.click(screen.getByTestId('application-field-subset-option-staff'));
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'membership.membership_type')?.field.application_choices).toEqual([
      'regular',
      'honorary',
    ]);
  });

  it('flags an EMPTY authored subset on the exposed-required membership-type field (R4.2)', () => {
    renderAttrs(
      'membership_type',
      membershipOnFormOverlay({ application_choices: [] }),
      vi.fn(),
      CATALOG,
    );
    expect(screen.getByTestId('application-field-subset-empty-error')).toBeInTheDocument();
  });

  it('flags a subset value NOT in the live catalog (R4.3)', () => {
    renderAttrs(
      'membership_type',
      membershipOnFormOverlay({ application_choices: ['regular', 'ghost'] }),
      vi.fn(),
      CATALOG,
    );
    const err = screen.getByTestId('application-field-subset-unknown-error');
    expect(err).toBeInTheDocument();
    expect(err).toHaveTextContent('ghost');
  });

  it('does NOT flag a null/absent subset (the coherent full-catalog default)', () => {
    renderAttrs('membership_type', membershipOnFormOverlay(), vi.fn(), CATALOG);
    expect(screen.queryByTestId('application-field-subset-empty-error')).not.toBeInTheDocument();
    expect(screen.queryByTestId('application-field-subset-unknown-error')).not.toBeInTheDocument();
  });

  it('shows "no types yet" when the live catalog is empty (R4.1)', () => {
    renderAttrs('membership_type', membershipOnFormOverlay(), vi.fn(), []);
    expect(screen.getByTestId('application-field-subset-empty-catalog')).toBeInTheDocument();
  });
});

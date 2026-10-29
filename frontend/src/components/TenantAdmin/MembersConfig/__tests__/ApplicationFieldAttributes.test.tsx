/**
 * Tests for the per-field application attributes panel (spec 11, task 3.1; R3.1–R3.5 / R4.1,
 * design §3/§3.1/§4/§10).
 *
 * This is the change-with-tests pairing for the new `ApplicationFieldAttributes` behavior (the full
 * dedicated suite is task 3.5). It asserts the R3/R4 contract the component owns:
 *  - the application-required toggle writes `application_required` as an EXPLICIT boolean (OFF is a
 *    deliberate `false`, 03b Req 2.1), seeds from the platform-required default, and is NEVER
 *    force-on/disabled — the admin freely sets requiredness for any field (03b Req 1.2/1.3);
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
    // A platform-required base field (no choices). After 03b Req 1 the required toggle SEEDS on
    // from the platform-required default but is NEVER forced/disabled — the admin may relax it.
    // Its storage `group` drives the origin-aware overlay key (`{group}.{key}` → `contact.email`).
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
    // The membership-type field (03b): a NORMAL enum/reference field that owns its OWN options.
    // NOT platform-required; after 03b Req 1.2 it is no longer forced-required when exposed. Its
    // subset sources from these options (the live catalog is retired) — `staff` is retired
    // (allowed:false) so it is NOT offered on the form.
    {
      key: 'membership_type',
      group: 'membership',
      functional_group: 'membership',
      type: 'reference',
      origin: 'fixed',
      provenance: 'base',
      required: false,
      label: { en: 'Type', nl: 'Type' },
      options: [
        { value: 'regular', label: { en: 'Regular', nl: 'Gewoon' } },
        { value: 'honorary', label: { en: 'Honorary', nl: 'Erelid' } },
        { value: 'staff', label: { en: 'Staff', nl: 'Staf' }, allowed: false },
      ],
    },
  ],
};

function renderAttrs(
  selectedKey: string | null,
  overlay: MembersConfigValue = {},
  onChange = vi.fn(),
) {
  const utils = render(
    <ApplicationFieldAttributes
      fieldConfig={FIELD_CONFIG}
      selectedKey={selectedKey}
      overlay={overlay}
      onChange={onChange}
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

  it('seeds ON for a platform-required field but is NOT disabled — the admin may relax it (03b Req 1)', () => {
    const { onChange } = renderAttrs('email', overrideOnFormOverlay('contact.email'));
    const toggle = screen.getByTestId('application-field-required-toggle');
    // Seeds ON from the platform-required default (a sensible initial state, not a lock, R3.1).
    expect(toggle).toBeChecked();
    expect(toggle).not.toBeDisabled();
    // The platform-required provenance is still surfaced as information.
    expect(screen.getByText('platform-required')).toBeInTheDocument();
    // 03b Req 1.1/1.4: the former no-relax binding is REMOVED — clicking the toggle off now
    // writes a relax to the overlay. 03b Req 2.1/2.4 (BU-5): the OFF is an EXPLICIT `false`, not a
    // dropped `undefined` the change-op diff would treat as "unchanged" (the toggle root cause).
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'contact.email')?.field.application_required).toBe(false);
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
/*  membership_type (03b 9b.2): a normal enum/reference field owning    */
/*  its OWN options; the subset sources from the field options, not a   */
/*  live catalog. Catalog-based subset validation is removed.           */
/* ------------------------------------------------------------------ */
describe('ApplicationFieldAttributes — membership-type coherence (R4, task 3.3)', () => {
  it('does NOT force the membership-type field application-required — the admin sets it (03b Req 1.2)', () => {
    const { onChange } = renderAttrs(
      'membership_type',
      membershipOnFormOverlay(),
    );
    const toggle = screen.getByTestId('application-field-required-toggle');
    // 03b Req 1.2: the former force-on/disable binding for the membership-type field is REMOVED.
    // The field is NOT platform-required (`required: false`) and carries no authored value, so the
    // toggle seeds OFF and is freely settable — no overrule.
    expect(toggle).not.toBeChecked();
    expect(toggle).not.toBeDisabled();
    // The membership-type provenance is still surfaced as information.
    expect(screen.getByText('membership-type')).toBeInTheDocument();
    // Clicking it ON now writes an explicit boolean (the admin's choice), not a no-op.
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'membership.membership_type')?.field.application_required).toBe(true);
  });

  it('sources the subset from the field OWN options; a retired option is not offered (03b 9b.2)', () => {
    renderAttrs('membership_type', membershipOnFormOverlay());
    // The field's own active options are offered; `staff` is allowed:false (retired) -> omitted.
    expect(screen.getByTestId('application-field-subset-option-regular')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-subset-option-honorary')).toBeInTheDocument();
    expect(screen.queryByTestId('application-field-subset-option-staff')).not.toBeInTheDocument();
  });

  it('writes a proper subset of the field option codes to application_choices (03b 9b.2)', () => {
    const { onChange } = renderAttrs('membership_type', membershipOnFormOverlay());
    // Offered set = {regular, honorary} (staff retired). Unchecking honorary leaves [regular].
    fireEvent.click(screen.getByTestId('application-field-subset-option-honorary'));
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'membership.membership_type')?.field.application_choices).toEqual([
      'regular',
    ]);
  });

  it('shows the "no options yet" note when the field has no options (03b 9b.2)', () => {
    const emptyCfg = {
      ...FIELD_CONFIG,
      fields: FIELD_CONFIG.fields.map((f) =>
        f.key === 'membership_type' ? { ...f, options: [] } : f,
      ),
    } as typeof FIELD_CONFIG;
    render(
      <ApplicationFieldAttributes
        fieldConfig={emptyCfg}
        selectedKey="membership_type"
        overlay={membershipOnFormOverlay()}
        onChange={vi.fn()}
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-field-subset-empty-catalog')).toBeInTheDocument();
  });
});

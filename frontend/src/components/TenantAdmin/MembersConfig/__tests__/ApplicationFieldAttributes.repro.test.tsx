/**
 * REPRO (diagnostic) — does the per-field CHOICE SELECTOR (enum subset picker) render?
 * Live symptom: "I have still not seen the choice selectors." This renders the REAL
 * ApplicationFieldAttributes for an enum field, with the field ON the form, and checks whether the
 * subset picker (`application-field-subset`) appears — distinguishing a GATING bug (field not
 * on-form) from a DATA bug (resolved field carries no `options`).
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen } from '../../../../test-utils';
import type { FieldConfig } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import { ApplicationFieldAttributes } from '../ApplicationFieldAttributes';

// A tenant-added ENUM field WITH options (the server serializes options as rich {value,label}).
const CFG: FieldConfig = {
  functional_groups: [{ key: 'personal', label: { en: 'Personal' }, order: 1 }],
  fields: [
    {
      key: 'shirt_size',
      functional_group: 'personal',
      order: 1,
      type: 'enum',
      origin: 'variable',
      provenance: 'tenant_added',
      label: { en: 'Shirt size' },
      options: [
        { value: 'S', label: { en: 'Small' } },
        { value: 'M', label: { en: 'Medium' } },
        { value: 'L', label: { en: 'Large' } },
      ],
    },
  ],
  field_format_tokens: ['EMAIL', 'IBAN'],
} as unknown as FieldConfig;

describe('REPRO — choice selector (enum subset picker) visibility', () => {
  it('CASE A: field NOT on the form → picker hidden (gating)', () => {
    render(
      <ApplicationFieldAttributes
        fieldConfig={CFG}
        selectedKey="shirt_size"
        overlay={{} as MembersConfigValue}
        onChange={vi.fn()}
        membershipTypeCatalog={null}
        lang="en"
      />,
    );
    const notOnForm = screen.queryByTestId('application-field-attributes-not-on-form');
    const picker = screen.queryByTestId('application-field-subset');
    // eslint-disable-next-line no-console
    console.log(`REPRO_A notOnForm=${!!notOnForm} pickerVisible=${!!picker}`);
    expect(notOnForm).toBeInTheDocument();
    expect(picker).not.toBeInTheDocument();
  });

  it('CASE B: field ON the form (application_visible:true) → picker SHOULD show', () => {
    // Seed the overlay so the field is on the form — tenant field → fields[key].
    const overlay = { fields: { shirt_size: { application_visible: true } } } as MembersConfigValue;
    render(
      <ApplicationFieldAttributes
        fieldConfig={CFG}
        selectedKey="shirt_size"
        overlay={overlay}
        onChange={vi.fn()}
        membershipTypeCatalog={null}
        lang="en"
      />,
    );
    const picker = screen.queryByTestId('application-field-subset');
    const optS = screen.queryByTestId('application-field-subset-option-S');
    // eslint-disable-next-line no-console
    console.log(`REPRO_B pickerVisible=${!!picker} optionS=${!!optS}`);
    expect(picker).toBeInTheDocument();
    expect(optS).toBeInTheDocument();
  });
});

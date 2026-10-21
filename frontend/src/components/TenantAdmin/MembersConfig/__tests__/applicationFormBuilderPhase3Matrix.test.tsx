/**
 * Dedicated Phase-3 R9.1 matrix suite for the Application Form Builder (spec 11, task 3.5).
 *
 * Tasks 3.1/3.2/3.3/3.4 each landed their own change-with-tests pairing
 * (`ApplicationFieldAttributes.test.tsx`, `ApplicationFormShellPanel.test.tsx`,
 * `applicationMembershipType.test.ts`, `ApplicationFormBuilder.test.tsx`). Those suites already
 * cover MOST of the R9.1 Phase-3 matrix:
 *
 *  - required toggle DISABLED + no-relax guard for a platform-required field .... ApplicationFieldAttributes
 *  - subset picker only on enum fields + out-of-set value structurally impossible  ApplicationFieldAttributes
 *  - format dropdown offers ONLY the known tokens + clears to null ("none") ....... ApplicationFieldAttributes
 *  - consent version BUMPS on text edit + KEPT when unchanged .................... ApplicationFormShellPanel
 *  - embed <iframe> snippet matches the derived public URL ....................... ApplicationFormShellPanel
 *  - EACH per-field attr lands on the right overlay entry (tenant / base) ........ ApplicationFieldAttributes
 *
 * The ONE matrix item NOT asserted end to end anywhere is the combined
 * **"all four per-field attrs (`application_visible`, `application_required`, `application_choices`,
 * `format`) land TOGETHER on the RIGHT overlay entry, origin-aware"** case — the single-object
 * invariant the whole builder exists to protect (design §3.1 / steering 38 rule 5). The
 * per-attribute tests prove each key individually routes to the right slice; this suite proves they
 * CO-EXIST on the one entry, for BOTH provenances:
 *  - a tenant-added field authors under `fields[key]`;
 *  - a platform base field authors under `fixed_overrides[{group}.{key}]`.
 *
 * It drives the real `ApplicationFieldAttributes` component (feeding each mutated overlay back in,
 * exactly as the builder root does) so the assertion is on the genuine `overlayModel.upsertField`
 * write path, not a hand-built object. No duplication of the per-attribute assertions above — only
 * the missing combined/origin-aware end-to-end case.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '../../../../test-utils';
import type { FieldConfig, MembershipType } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import { ApplicationFieldAttributes } from '../ApplicationFieldAttributes';
import { findField } from '../overlayModel';

/* ------------------------------------------------------------------ */
/*  Fixture — a tenant-added enum field AND an OPTIONAL base enum field */
/*  (so required/subset/format can all be authored on a base field     */
/*  that lands under fixed_overrides[{group}.{key}]).                  */
/* ------------------------------------------------------------------ */
const FIELD_CONFIG: FieldConfig = {
  field_format_tokens: ['EMAIL', 'IBAN'],
  functional_groups: [
    { key: 'contact', order: 1 },
    { key: 'extra', order: 2 },
  ],
  fields: [
    // Tenant-added enum field → authors under fields[preference].
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
    // OPTIONAL platform base enum field → authors under fixed_overrides[extra.hobby]. Being base +
    // NOT platform-required lets the required toggle actually TIGHTEN (so all four attrs are
    // authorable on the one base entry).
    {
      key: 'hobby',
      group: 'extra',
      functional_group: 'extra',
      type: 'enum',
      origin: 'fixed',
      provenance: 'base',
      required: false,
      label: { en: 'Hobby', nl: 'Hobby' },
      options: [
        { value: 'x', label: { en: 'X', nl: 'X' } },
        { value: 'y', label: { en: 'Y', nl: 'Y' } },
      ],
    },
  ],
};

const NO_CATALOG: MembershipType[] | null = null;

/**
 * Render the attributes panel over a MUTABLE overlay: each `onChange` is fed straight back in as the
 * new overlay (what the builder root does), so a sequence of edits accumulates on the ONE object.
 */
function renderWithLiveOverlay(selectedKey: string, initial: MembersConfigValue) {
  let overlay = initial;
  const onChange = vi.fn((next: MembersConfigValue) => {
    overlay = next;
    rerender();
  });
  const el = () => (
    <ApplicationFieldAttributes
      fieldConfig={FIELD_CONFIG}
      selectedKey={selectedKey}
      overlay={overlay}
      onChange={onChange}
      membershipTypeCatalog={NO_CATALOG}
      lang="en"
    />
  );
  const utils = render(el());
  const rerender = () => utils.rerender(el());
  return {
    ...utils,
    onChange,
    getOverlay: () => overlay,
  };
}

/** An overlay with the given field already on the form under the given slice/key. */
function onFormOverlay(slice: 'fields' | 'fixed_overrides', key: string): MembersConfigValue {
  return { [slice]: { [key]: { application_visible: true } } } as MembersConfigValue;
}

describe('Application Form Builder Phase-3 matrix (task 3.5) — all four attrs on the RIGHT overlay entry (R9.1)', () => {
  it('a TENANT-added field lands application_visible + required + choices + format together under fields[key]', () => {
    // Seed with the field already on the form (application_visible=true under fields[preference]).
    const { getOverlay } = renderWithLiveOverlay(
      'preference',
      onFormOverlay('fields', 'preference'),
    );

    // 1) application_required — tighten the optional field to required.
    fireEvent.click(screen.getByTestId('application-field-required-toggle'));
    // 2) application_choices — uncheck 'b' → a proper subset ['a','c'] of the field's OWN choices.
    fireEvent.click(screen.getByTestId('application-field-subset-option-b'));
    // 3) format — select a known token.
    fireEvent.change(screen.getByTestId('application-field-format-select'), {
      target: { value: 'EMAIL' },
    });

    const overlay = getOverlay() as { fields?: Record<string, unknown>; fixed_overrides?: Record<string, unknown> };
    // The one entry lives under fields[preference] — NOT fixed_overrides, never duplicated.
    expect(overlay.fields).toHaveProperty('preference');
    expect(overlay.fixed_overrides ?? {}).not.toHaveProperty('preference');

    // All four per-field attributes co-exist on that ONE entry.
    const entry = findField(overlay as MembersConfigValue, 'preference')?.field;
    expect(entry?.application_visible).toBe(true);
    expect(entry?.application_required).toBe(true);
    expect(entry?.application_choices).toEqual(['a', 'c']);
    expect(entry?.format).toEqual({ checker: 'EMAIL' });
  });

  it('a platform BASE field lands all four attrs together under fixed_overrides[{group}.{key}] (never fields[key])', () => {
    // Seed the base field on the form under its origin-aware key fixed_overrides[extra.hobby].
    const { getOverlay } = renderWithLiveOverlay(
      'hobby',
      onFormOverlay('fixed_overrides', 'extra.hobby'),
    );

    // Author all three remaining per-field attributes on the base field.
    fireEvent.click(screen.getByTestId('application-field-required-toggle')); // required (optional→required)
    fireEvent.click(screen.getByTestId('application-field-subset-option-y')); // subset ['x'] of own choices
    fireEvent.change(screen.getByTestId('application-field-format-select'), {
      target: { value: 'IBAN' },
    });

    const overlay = getOverlay() as { fields?: Record<string, unknown>; fixed_overrides?: Record<string, unknown> };
    // Origin-aware: a base field writes under the DOTTED fixed_overrides key, and the bare key is
    // NEVER created in fields (no cross-map duplication, overlayModel.upsertField contract).
    expect(overlay.fixed_overrides).toHaveProperty('extra.hobby');
    expect(overlay.fields ?? {}).not.toHaveProperty('hobby');
    expect(overlay.fixed_overrides ?? {}).not.toHaveProperty('hobby');

    const entry = findField(overlay as MembersConfigValue, 'extra.hobby')?.field;
    expect(entry?.application_visible).toBe(true);
    expect(entry?.application_required).toBe(true);
    expect(entry?.application_choices).toEqual(['x']);
    expect(entry?.format).toEqual({ checker: 'IBAN' });
  });

  it('clearing format back to "none" leaves the other three attrs intact on the same entry', () => {
    // Start the tenant field on the form with a format already authored, then clear it.
    const seeded = {
      fields: {
        preference: {
          application_visible: true,
          application_required: true,
          application_choices: ['a', 'c'],
          format: { checker: 'EMAIL' },
        },
      },
    } as MembersConfigValue;
    const { getOverlay } = renderWithLiveOverlay('preference', seeded);

    fireEvent.change(screen.getByTestId('application-field-format-select'), {
      target: { value: '' }, // "— none —"
    });

    const entry = findField(getOverlay(), 'preference')?.field;
    // format cleared to null; the other three attributes untouched on the one entry.
    expect(entry?.format).toBeNull();
    expect(entry?.application_visible).toBe(true);
    expect(entry?.application_required).toBe(true);
    expect(entry?.application_choices).toEqual(['a', 'c']);
  });
});

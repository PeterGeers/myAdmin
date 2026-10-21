/**
 * Tests for the Application field list (spec 11, task 2.3; R2.1–R2.5, design §3/§3.1/§10).
 *
 * This is the change-with-tests pairing for the new `ApplicationFieldList` behavior (the full
 * dedicated suite is task 2.4). It asserts the R2 contract the component owns:
 *  - the resolved fields render GROUPED by `functional_group`, ordered `(group.order, field.order,
 *    key)` (R2.1);
 *  - the per-row on-the-form toggle writes `application_visible` into the ONE working overlay via
 *    the pure `overlayModel` transform, bubbled through `onChange` — no network (R2.3 / §3.1);
 *  - a calculated / read-only field is NOT offerable — no toggle, a clear note instead (R2.5);
 *  - membership-admin storage-group fields default OFF but stay toggleable (R2.4);
 *  - one-object/one-save: a toggle mutates the SAME overlay object, never per-field.
 *
 * The component takes `lang` directly (no i18n), so a plain Chakra render suffices.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, within, fireEvent } from '../../../../test-utils';
import type { FieldConfig } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import { ApplicationFieldList } from '../ApplicationFieldList';
import { findField } from '../overlayModel';

/* ------------------------------------------------------------------ */
/*  Fixture — two catalog groups (ordered) + a calculated + a          */
/*  membership-admin storage-group field.                              */
/* ------------------------------------------------------------------ */
const FIELD_CONFIG: FieldConfig = {
  functional_groups: [
    { key: 'contact', label: { en: 'Contact', nl: 'Contact' }, order: 1 },
    { key: 'personal', label: { en: 'Personal', nl: 'Persoonlijk' }, order: 2 },
  ],
  fields: [
    // personal group (order 2) — two fields, ordered by (field.order, key)
    { key: 'last_name', functional_group: 'personal', order: 2, type: 'string', provenance: 'tenant_added', label: { en: 'Last name' } },
    { key: 'first_name', functional_group: 'personal', order: 1, type: 'string', provenance: 'tenant_added', label: { en: 'First name' } },
    // contact group (order 1) — one field
    { key: 'email', functional_group: 'contact', order: 1, type: 'string', provenance: 'tenant_added', label: { en: 'Email' } },
    // membership-admin storage-group field (defaults off, toggleable)
    { key: 'member_number', group: 'membership', functional_group: 'contact', order: 2, type: 'string', origin: 'fixed', provenance: 'base', label: { en: 'Member number' } },
    // calculated / derived field — NOT offerable
    { key: 'age', functional_group: 'personal', order: 3, type: 'number', origin: 'calculated', read_only: true, label: { en: 'Age' } },
  ],
};

/* ------------------------------------------------------------------ */
/*  Fixture — a group with THREE fields sharing one `field.order`, to  */
/*  pin the alphabetical-key tiebreak of `(group.order, field.order,   */
/*  key)` (the last tier of the catalog ordering rule, R2.1).          */
/* ------------------------------------------------------------------ */
const TIEBREAK_CONFIG: FieldConfig = {
  functional_groups: [{ key: 'contact', label: { en: 'Contact' }, order: 1 }],
  fields: [
    // All three share order 5 → the key tiebreak decides: zulu < alpha? No — alpha < mike < zulu.
    { key: 'zulu', functional_group: 'contact', order: 5, type: 'string', provenance: 'tenant_added', label: { en: 'Zulu' } },
    { key: 'alpha', functional_group: 'contact', order: 5, type: 'string', provenance: 'tenant_added', label: { en: 'Alpha' } },
    { key: 'mike', functional_group: 'contact', order: 5, type: 'string', provenance: 'tenant_added', label: { en: 'Mike' } },
  ],
};

function renderList(overlay: MembersConfigValue = {}, onChange = vi.fn()) {
  const utils = render(
    <ApplicationFieldList fieldConfig={FIELD_CONFIG} overlay={overlay} onChange={onChange} lang="en" />,
  );
  return { ...utils, onChange };
}

describe('ApplicationFieldList — grouped & ordered render (R2.1)', () => {
  it('renders groups ordered by group.order and fields by (field.order, key)', () => {
    renderList();
    // Group sections render in catalog order (contact:1 before personal:2).
    const groups = screen.getAllByTestId(/^application-field-group-/);
    expect(groups.map((g) => g.getAttribute('data-testid'))).toEqual([
      'application-field-group-contact',
      'application-field-group-personal',
    ]);

    // Within "personal", first_name (order 1) precedes last_name (order 2).
    const personal = screen.getByTestId('application-field-group-personal');
    const rows = within(personal).getAllByTestId(/^application-field-row-/);
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual([
      'application-field-row-first_name',
      'application-field-row-last_name',
      'application-field-row-age',
    ]);
  });

  it('breaks an equal (group.order, field.order) tie ALPHABETICALLY by key (R2.1, last tier)', () => {
    render(
      <ApplicationFieldList fieldConfig={TIEBREAK_CONFIG} overlay={{}} onChange={vi.fn()} lang="en" />,
    );
    const contact = screen.getByTestId('application-field-group-contact');
    const rows = within(contact).getAllByTestId(/^application-field-row-/);
    // All three share order 5 → the key tiebreak orders them alpha < mike < zulu.
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual([
      'application-field-row-alpha',
      'application-field-row-mike',
      'application-field-row-zulu',
    ]);
  });
});

describe('ApplicationFieldList — on-the-form toggle writes application_visible (R2.3 / §3.1)', () => {
  it('toggling a tenant field ON sets application_visible=true under fields[key] in the one overlay', () => {
    const { onChange } = renderList({});
    fireEvent.click(screen.getByTestId('application-field-toggle-email'));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'email')?.field.application_visible).toBe(true);
  });

  it('toggling OFF clears application_visible to the default (undefined), not false', () => {
    // Seed the field already on the form in the working overlay.
    const seeded: MembersConfigValue = {
      fields: { email: { type: 'string', application_visible: true } },
    };
    const { onChange } = renderList(seeded);
    // The seeded "on" state is reflected.
    expect(screen.getByTestId('application-field-toggle-email')).toBeChecked();
    fireEvent.click(screen.getByTestId('application-field-toggle-email'));
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'email')?.field.application_visible).toBeUndefined();
  });

  it('a base field toggles under fixed_overrides keyed {group}.{key}', () => {
    const { onChange } = renderList({});
    fireEvent.click(screen.getByTestId('application-field-toggle-member_number'));
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    // Written under fixed_overrides['membership.member_number'] (origin-aware target).
    expect(findField(next, 'membership.member_number')?.field.application_visible).toBe(true);
  });

  it('accumulates toggles into the ONE overlay object — no per-field write, never two stores (§3.1)', () => {
    // A tenant field (→ fields[key]) and a base field (→ fixed_overrides[{group}.{key}]) both
    // land in the SAME single overlay object; neither slice clobbers the other, proving the
    // one-object authoring model the single Save commits verbatim.
    let overlay: MembersConfigValue = {};
    const onChange = vi.fn((next: MembersConfigValue) => {
      overlay = next;
    });
    const { rerender } = render(
      <ApplicationFieldList fieldConfig={FIELD_CONFIG} overlay={overlay} onChange={onChange} lang="en" />,
    );
    fireEvent.click(screen.getByTestId('application-field-toggle-email'));
    rerender(
      <ApplicationFieldList fieldConfig={FIELD_CONFIG} overlay={overlay} onChange={onChange} lang="en" />,
    );
    fireEvent.click(screen.getByTestId('application-field-toggle-member_number'));

    // Both toggles survive in the ONE object: tenant slice + override slice, side by side.
    expect(findField(overlay, 'email')?.field.application_visible).toBe(true);
    expect(findField(overlay, 'email')?.origin).toBe('fields');
    expect(findField(overlay, 'membership.member_number')?.field.application_visible).toBe(true);
    expect(findField(overlay, 'membership.member_number')?.origin).toBe('fixed_overrides');
  });
});

describe('ApplicationFieldList — offerability (R2.4 / R2.5)', () => {
  it('a calculated/read-only field is NOT offerable — a note, no toggle', () => {
    renderList();
    expect(screen.queryByTestId('application-field-toggle-age')).not.toBeInTheDocument();
    expect(screen.getByTestId('application-field-not-offerable-age')).toBeInTheDocument();
  });

  it('a membership-admin field defaults OFF but is toggleable (R2.4)', () => {
    renderList();
    const toggle = screen.getByTestId('application-field-toggle-member_number');
    // Defaults off (no authored value, membership storage group).
    expect(toggle).not.toBeChecked();
    // Still present + enabled (toggleable per field, not all-or-nothing).
    expect(toggle).toBeEnabled();
  });
});


describe('ApplicationFieldList — scope + reference fields are offerable and grouped (user req)', () => {
  // Reference (membership_type) and scope (region) fields are neither calculated nor read_only, so
  // they MUST be offerable on the application form and grouped by functional_group like any field.
  const SCOPE_REF_CONFIG: FieldConfig = {
    functional_groups: [
      { key: 'membership', label: { en: 'Membership' }, order: 1 },
      { key: 'personal', label: { en: 'Personal' }, order: 2 },
    ],
    fields: [
      // REFERENCE field (membership_type) — base/fixed, required, NOT read-only → offerable.
      {
        key: 'membership_type',
        group: 'membership',
        functional_group: 'membership',
        order: 1,
        type: 'reference',
        origin: 'fixed',
        provenance: 'base',
        required: true,
        label: { en: 'Membership type' },
      },
      // SCOPE field (region) — a tenant overlay enum bound to a scope dimension → offerable.
      {
        key: 'region',
        functional_group: 'personal',
        order: 1,
        type: 'enum',
        provenance: 'tenant_added',
        scope: { enabled: true, required_for: ['Members_CRUD'] },
        options: ['Noord', 'Zuid'],
        label: { en: 'Region' },
      },
    ],
  };

  it('offers a toggle for a REFERENCE field (membership_type) and a SCOPE field (region)', () => {
    render(
      <ApplicationFieldList fieldConfig={SCOPE_REF_CONFIG} overlay={{}} onChange={vi.fn()} lang="en" />,
    );
    // Both render a toggle (offerable) — not a "not available" note.
    expect(screen.getByTestId('application-field-toggle-membership_type')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-toggle-region')).toBeInTheDocument();
    expect(screen.queryByTestId('application-field-not-offerable-membership_type')).not.toBeInTheDocument();
    expect(screen.queryByTestId('application-field-not-offerable-region')).not.toBeInTheDocument();
  });

  it('groups the reference + scope fields under their functional_group sections', () => {
    render(
      <ApplicationFieldList fieldConfig={SCOPE_REF_CONFIG} overlay={{}} onChange={vi.fn()} lang="en" />,
    );
    const membership = screen.getByTestId('application-field-group-membership');
    expect(within(membership).getByTestId('application-field-row-membership_type')).toBeInTheDocument();
    const personal = screen.getByTestId('application-field-group-personal');
    expect(within(personal).getByTestId('application-field-row-region')).toBeInTheDocument();
  });

  it('toggling a REFERENCE field on writes application_visible under its origin-aware override key', () => {
    const onChange = vi.fn();
    render(
      <ApplicationFieldList fieldConfig={SCOPE_REF_CONFIG} overlay={{}} onChange={onChange} lang="en" />,
    );
    fireEvent.click(screen.getByTestId('application-field-toggle-membership_type'));
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    // base reference field → fixed_overrides['membership.membership_type']
    expect(findField(next, 'membership.membership_type')?.field.application_visible).toBe(true);
  });
});

/**
 * Tests for the Application field list (modal-open) (spec 12 — Application Form Serving Redesign,
 * task 4.1; R1.1, design §C1 / redesign A).
 *
 * This is the change-with-tests pairing for the field surface that REPLACES spec 11's
 * `ApplicationFieldList` toggle-list. It asserts the task 4.1 contract the list owns:
 *  - the resolved fields render GROUPED by `functional_group`, ordered `(group.order, field.order,
 *    key)` (R2.1) — the SAME catalog ordering the retired list used;
 *  - a row-click (and keyboard Enter/Space) OPENS the per-field modal via `onOpenField` — there is
 *    no inline toggle on this surface anymore (R1.1 / redesign A);
 *  - the on-the-form state shows as a read-only BADGE (authored in the modal), with the SAME
 *    precedence the modal writes with;
 *  - a calculated / read-only field is NOT offerable — a note, no badge toggle (R2.5).
 *
 * Fixtures use the bare `key` + `group` server shape (R2.3) — never a pre-dotted key.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, within, fireEvent } from '../../../../test-utils';
import type { FieldConfig } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import { ApplicationFieldModalList } from '../ApplicationFieldModalList';

const FIELD_CONFIG: FieldConfig = {
  functional_groups: [
    { key: 'contact', label: { en: 'Contact', nl: 'Contact' }, order: 1 },
    { key: 'personal', label: { en: 'Personal', nl: 'Persoonlijk' }, order: 2 },
  ],
  fields: [
    { key: 'last_name', functional_group: 'personal', order: 2, type: 'string', provenance: 'tenant_added', label: { en: 'Last name' } },
    { key: 'first_name', functional_group: 'personal', order: 1, type: 'string', provenance: 'tenant_added', label: { en: 'First name' } },
    { key: 'email', functional_group: 'contact', order: 1, type: 'string', provenance: 'tenant_added', label: { en: 'Email' } },
    // base/fixed with a storage group (bare key + group, R2.3)
    { key: 'member_number', group: 'membership', functional_group: 'contact', order: 2, type: 'string', origin: 'fixed', provenance: 'base', label: { en: 'Member number' } },
    // calculated — NOT offerable
    { key: 'age', functional_group: 'personal', order: 3, type: 'number', origin: 'calculated', read_only: true, label: { en: 'Age' } },
  ],
};

function renderList(overlay: MembersConfigValue = {}, onOpenField = vi.fn()) {
  const utils = render(
    <ApplicationFieldModalList
      fieldConfig={FIELD_CONFIG}
      overlay={overlay}
      onOpenField={onOpenField}
      lang="en"
    />,
  );
  return { ...utils, onOpenField };
}

describe('ApplicationFieldModalList — grouped & ordered render (R2.1)', () => {
  it('renders groups ordered by group.order and fields by (field.order, key)', () => {
    renderList();
    const groups = screen.getAllByTestId(/^application-field-group-/);
    expect(groups.map((g) => g.getAttribute('data-testid'))).toEqual([
      'application-field-group-contact',
      'application-field-group-personal',
    ]);
    const personal = screen.getByTestId('application-field-group-personal');
    const rows = within(personal).getAllByTestId(/^application-field-row-/);
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual([
      'application-field-row-first_name',
      'application-field-row-last_name',
      'application-field-row-age',
    ]);
  });

  it('shows the empty state when there are no resolvable fields', () => {
    render(
      <ApplicationFieldModalList fieldConfig={null} overlay={{}} onOpenField={vi.fn()} lang="en" />,
    );
    expect(screen.getByTestId('application-field-list-empty')).toBeInTheDocument();
  });
});

describe('ApplicationFieldModalList — row-click opens the modal (R1.1 / redesign A)', () => {
  it('clicking a field row raises onOpenField with its key (no inline toggle on this surface)', () => {
    const { onOpenField } = renderList();
    // The retired inline toggle is gone — there is no toggle control on the surface.
    expect(screen.queryByTestId('application-field-toggle-email')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('application-field-row-email'));
    expect(onOpenField).toHaveBeenCalledWith('email');
  });

  it('activates the row on keyboard Enter and Space (WCAG 2.1.1)', () => {
    const { onOpenField } = renderList();
    const row = screen.getByTestId('application-field-row-email');
    expect(row).toHaveAttribute('role', 'button');
    expect(row).toHaveAttribute('tabindex', '0');
    fireEvent.keyDown(row, { key: 'Enter' });
    fireEvent.keyDown(row, { key: ' ' });
    expect(onOpenField).toHaveBeenCalledTimes(2);
    expect(onOpenField).toHaveBeenNthCalledWith(1, 'email');
    expect(onOpenField).toHaveBeenNthCalledWith(2, 'email');
  });

  it('a non-Enter/Space key does not open the modal', () => {
    const { onOpenField } = renderList();
    fireEvent.keyDown(screen.getByTestId('application-field-row-email'), { key: 'a' });
    expect(onOpenField).not.toHaveBeenCalled();
  });

  it('a non-offerable (calculated) row is still clickable to open the modal (no dead end)', () => {
    const { onOpenField } = renderList();
    fireEvent.click(screen.getByTestId('application-field-row-age'));
    expect(onOpenField).toHaveBeenCalledWith('age');
  });
});

describe('ApplicationFieldModalList — read-only on-the-form status badge (R2.2/R2.3)', () => {
  it('shows "off form" by default and "on form" when the overlay has the field on', () => {
    renderList();
    expect(screen.getByTestId('application-field-status-email')).toHaveTextContent('off form');

    // Seed email on-the-form in the working overlay (tenant field → fields[email]).
    render(
      <ApplicationFieldModalList
        fieldConfig={FIELD_CONFIG}
        overlay={{ fields: { email: { application_visible: true } } } as MembersConfigValue}
        onOpenField={vi.fn()}
        lang="en"
      />,
    );
    expect(screen.getAllByTestId('application-field-status-email').at(-1)).toHaveTextContent(
      'on form',
    );
  });

  it('a calculated/read-only field shows a "not available" note, no status badge', () => {
    renderList();
    expect(screen.queryByTestId('application-field-status-age')).not.toBeInTheDocument();
    expect(screen.getByTestId('application-field-not-offerable-age')).toBeInTheDocument();
  });
});

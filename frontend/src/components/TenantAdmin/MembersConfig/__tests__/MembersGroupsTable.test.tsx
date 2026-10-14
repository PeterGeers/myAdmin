/**
 * Tests for the functional-groups table + group modal (Members config drill-down remediation, R1).
 *
 * The drill-down entry point. Post-remediation the table DISPLAYS the group catalog + its resolved
 * field counts from the RESOLVED `FieldConfig` (not the raw `field_overlay`); the working overlay
 * stays the WRITE model the modal mutates (controlled — every mutation flows out through `onChange`,
 * the editor saves once, task 4.8). These assert:
 *  - groups render from the resolved config in derived `(group.order, key)` order;
 *  - the delete-only-when-empty guard counts RESOLVED fields (R1.3) — a group holding only base
 *    fields is non-empty even when the overlay authored none;
 *  - the modal mutations (create / duplicate-key / delete) still flow out through `overlayModel`.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, within, fireEvent } from '../../../../test-utils';
import i18n from '../../../../i18n';
import { MembersGroupsTable } from '../MembersGroupsTable';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import type { FieldConfig } from '../../../../types/members';

/**
 * The RESOLVED field-config the table DISPLAYS from (fixed ⊕ overlay ⊕ calculated). `personal`
 * holds a BASE field only (no overlay delta); `motor` is an empty catalog group. This is the heart
 * of R1.3: `personal` must count as non-empty from the resolved set, not the overlay.
 */
function fieldConfig(): FieldConfig {
  return {
    fields: [
      // personal: a platform BASE field (NOT in the write overlay) → the group is non-empty (R1.3)
      {
        key: 'personal.first_name',
        functional_group: 'personal',
        provenance: 'base',
        type: 'string',
        label: { en: 'First name', nl: 'Voornaam' },
      },
    ],
    functional_groups: [
      { key: 'motor', label: { en: 'Motorcycle', nl: 'Motor' }, order: 2 },
      { key: 'personal', label: { en: 'Personal', nl: 'Persoonlijk' }, order: 1 },
    ],
  };
}

/** The WRITE model — note it authors NO delta for `personal.first_name` (it is a base field). */
function overlay(): MembersConfigValue {
  return {
    functional_groups: [
      { key: 'motor', label_en: 'Motorcycle', label_nl: 'Motor', order: 2 },
      { key: 'personal', label_en: 'Personal', label_nl: 'Persoonlijk', order: 1 },
    ],
    fields: {},
    fixed_overrides: {},
  };
}

function renderTable(
  value: MembersConfigValue = overlay(),
  onChange: (next: MembersConfigValue) => void = vi.fn(),
  cfg: FieldConfig | null = fieldConfig(),
) {
  i18n.changeLanguage('en');
  return render(
    <I18nextProvider i18n={i18n}>
      <MembersGroupsTable fieldConfig={cfg} overlay={value} onChange={onChange} lang="en" />
    </I18nextProvider>,
  );
}

describe('MembersGroupsTable — entry point (displays the resolved config, R1.1)', () => {
  it('lists groups from the resolved config in derived (group.order, key) order', () => {
    renderTable();
    const rows = screen
      .getAllByTestId(/^members-groups-row-/)
      .map((n) => n.getAttribute('data-testid'));
    expect(rows).toEqual(['members-groups-row-personal', 'members-groups-row-motor']);
  });

  it('row-click opens the group modal in edit mode', () => {
    renderTable();
    fireEvent.click(screen.getByTestId('members-groups-row-personal'));
    const modal = screen.getByTestId('members-group-modal');
    expect(modal).toBeInTheDocument();
    expect(within(modal).getByRole('heading', { name: 'Edit group' })).toBeInTheDocument();
  });

  it('the add-group action opens the modal in create mode', () => {
    renderTable();
    fireEvent.click(screen.getByTestId('members-groups-add-btn'));
    const modal = screen.getByTestId('members-group-modal');
    // The modal header reads "Add group"; its save button reads "Create" in create mode.
    expect(within(modal).getByRole('heading', { name: 'Add group' })).toBeInTheDocument();
    expect(screen.getByTestId('members-group-modal-save-btn')).toHaveTextContent('Create');
  });

  it('shows an empty-state hint when there are no groups', () => {
    renderTable({ functional_groups: [], fields: {}, fixed_overrides: {} }, vi.fn(), {
      fields: [],
      functional_groups: [],
    });
    expect(screen.getByTestId('members-groups-empty')).toBeInTheDocument();
  });

  it('degrades to the working overlay groups when the resolved config is unavailable (R1.4)', () => {
    renderTable(overlay(), vi.fn(), null);
    // Still lists the overlay-authored groups — never blocks.
    const rows = screen
      .getAllByTestId(/^members-groups-row-/)
      .map((n) => n.getAttribute('data-testid'));
    expect(rows).toEqual(['members-groups-row-personal', 'members-groups-row-motor']);
  });

  // Label resolution (R4): the group heading reads STRAIGHT from the served per-language `label{}`
  // (`label[lang] ?? label.en ?? label.nl ?? key`) — no resource-key indirection; never blank.
  it('resolves the group label from the served label{} for the active language (R4)', () => {
    renderTable(overlay(), vi.fn(), fieldConfig());
    expect(within(screen.getByTestId('members-groups-row-personal')).getByText('Personal')).toBeInTheDocument();
  });

  it('the language selector picks the NL group-label variant (R4)', () => {
    i18n.changeLanguage('nl');
    render(
      <I18nextProvider i18n={i18n}>
        <MembersGroupsTable fieldConfig={fieldConfig()} overlay={overlay()} onChange={vi.fn()} lang="nl" />
      </I18nextProvider>,
    );
    expect(within(screen.getByTestId('members-groups-row-personal')).getByText('Persoonlijk')).toBeInTheDocument();
  });

  it('falls back to the stable group key when no label resolves (never blank, R4)', () => {
    const cfg: FieldConfig = {
      fields: [],
      functional_groups: [{ key: 'bare_group', order: 1 }],
    };
    renderTable({ functional_groups: [{ key: 'bare_group', order: 1 }], fields: {}, fixed_overrides: {} }, vi.fn(), cfg);
    // The label fell through to the key: the label cell (first <td>) shows the key — never blank.
    const labelCell = screen.getByTestId('members-groups-row-bare_group').querySelector('td');
    expect(labelCell).toHaveTextContent('bare_group');
  });
});

describe('MembersGroupModal — create / edit / delete-when-empty (R1.3)', () => {
  it('creates a new group and bubbles the mutated overlay out through onChange', () => {
    const onChange = vi.fn();
    renderTable(overlay(), onChange);
    fireEvent.click(screen.getByTestId('members-groups-add-btn'));
    const modal = screen.getByTestId('members-group-modal');
    fireEvent.change(within(modal).getByLabelText('Group key'), { target: { value: 'address' } });
    fireEvent.change(within(modal).getByLabelText('Label (English)'), {
      target: { value: 'Address' },
    });
    fireEvent.change(within(modal).getByLabelText('Order'), { target: { value: '3' } });
    fireEvent.click(screen.getByTestId('members-group-modal-save-btn'));

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    const added = next.functional_groups.find((g: any) => g.key === 'address');
    expect(added).toMatchObject({ key: 'address', label_en: 'Address', order: 3 });
  });

  it('refuses a duplicate group key with a validation message', () => {
    const onChange = vi.fn();
    renderTable(overlay(), onChange);
    fireEvent.click(screen.getByTestId('members-groups-add-btn'));
    fireEvent.change(screen.getByLabelText('Group key'), { target: { value: 'personal' } });
    fireEvent.click(screen.getByTestId('members-group-modal-save-btn'));
    expect(screen.getByText('This group key already exists')).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('DISABLES delete for a group holding RESOLVED (base) fields, even with no overlay delta (R1.3)', () => {
    renderTable();
    // `personal` holds only the BASE field `personal.first_name` — absent from the write overlay,
    // present in the resolved config. The guard must still treat the group as non-empty.
    fireEvent.click(screen.getByTestId('members-groups-row-personal'));
    expect(screen.getByTestId('members-group-modal-delete-btn')).toBeDisabled();
    const reason = screen.getByTestId('members-group-modal-delete-reason');
    expect(reason).toBeInTheDocument();
    expect(reason).toHaveTextContent('1 field');
  });

  it('ALLOWS delete for a group with no resolved fields and removes it on confirm', () => {
    const onChange = vi.fn();
    renderTable(overlay(), onChange);
    fireEvent.click(screen.getByTestId('members-groups-row-motor')); // motor has no resolved fields
    const deleteBtn = screen.getByTestId('members-group-modal-delete-btn');
    expect(deleteBtn).not.toBeDisabled();
    fireEvent.click(deleteBtn);
    fireEvent.click(screen.getByTestId('members-group-modal-delete-confirm'));

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    expect(next.functional_groups.some((g: any) => g.key === 'motor')).toBe(false);
    expect(next.functional_groups.some((g: any) => g.key === 'personal')).toBe(true);
  });

  it('the Fields button drills into the group (calls onOpenFields)', () => {
    const onOpenFields = vi.fn();
    i18n.changeLanguage('en');
    render(
      <I18nextProvider i18n={i18n}>
        <MembersGroupsTable
          fieldConfig={fieldConfig()}
          overlay={overlay()}
          onChange={vi.fn()}
          onOpenFields={onOpenFields}
          lang="en"
        />
      </I18nextProvider>,
    );
    fireEvent.click(screen.getByTestId('members-groups-row-personal'));
    fireEvent.click(screen.getByTestId('members-group-modal-fields-btn'));
    expect(onOpenFields).toHaveBeenCalledWith('personal');
  });
});

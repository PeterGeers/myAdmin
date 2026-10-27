/**
 * Tests for the provenance-driven field actions + move-to-group (Phase 3, task 4.7; R1.2/R1.3/R4.3).
 *
 * The contract: provenance is NEVER a rendered badge — it GOVERNS which actions a field offers.
 *   - tenant_added → destructive Delete (confirm) and NO reset;
 *   - base → Reset to default + Hide, NO destructive delete;
 *   - base_overridden → Reset to default, NO destructive delete and NO hide.
 * Every provenance offers Move-to-group. Actions are pure overlay transforms bubbled via onChange.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, fireEvent } from '../../../../test-utils';
import i18n from '../../../../i18n';
import { MembersFieldActions } from '../MembersFieldActions';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import type { FieldProvenance } from '../../../../types/members';

function overlay(): MembersConfigValue {
  return {
    functional_groups: [
      { key: 'personal', label_en: 'Personal', order: 1 },
      { key: 'motor', label_en: 'Motorcycle', order: 2 },
    ],
    fields: {
      region: { type: 'string', functional_group: 'personal', visible: true },
    },
    fixed_overrides: {
      'personal.first_name': { label_en: 'Given name', functional_group: 'personal' },
    },
  };
}

// The RESOLVED functional-group catalog (Flat_View). Note `address` + `membership` exist here
// but NOT in the sparse overlay() above — proving the picker reads the catalog, not the overlay.
function resolvedGroups() {
  return [
    { key: 'personal', label: { en: 'Personal', nl: 'Persoonlijk' }, order: 1 },
    { key: 'address', label: { en: 'Address', nl: 'Adres' }, order: 2 },
    { key: 'membership', label: { en: 'Membership', nl: 'Lidmaatschap' }, order: 3 },
    { key: 'motor', label: { en: 'Motorcycle', nl: 'Motor' }, order: 4 },
  ];
}

function renderActions(
  provenance: FieldProvenance,
  props: Partial<React.ComponentProps<typeof MembersFieldActions>> = {},
) {
  i18n.changeLanguage('en');
  const merged: React.ComponentProps<typeof MembersFieldActions> = {
    fieldKey: 'region',
    currentGroupKey: 'personal',
    functionalGroups: resolvedGroups(),
    provenance,
    overlay: overlay(),
    onChange: vi.fn(),
    onClose: vi.fn(),
    lang: 'en',
    ...props,
  };
  return {
    ...render(
      <I18nextProvider i18n={i18n}>
        <MembersFieldActions {...merged} />
      </I18nextProvider>,
    ),
    props: merged,
  };
}

describe('MembersFieldActions — provenance governs the available actions (R1.3)', () => {
  it('tenant_added → Delete, NO reset, NO hide; provenance is not rendered as a badge', () => {
    renderActions('tenant_added');
    expect(screen.getByTestId('members-field-action-delete')).toBeInTheDocument();
    expect(screen.queryByTestId('members-field-action-reset')).not.toBeInTheDocument();
    expect(screen.queryByTestId('members-field-action-hide')).not.toBeInTheDocument();
    // no provenance label/badge is rendered anywhere
    expect(screen.queryByText(/tenant.added/i)).not.toBeInTheDocument();
  });

  it('base → Reset + Hide, NO destructive Delete', () => {
    renderActions('base');
    expect(screen.getByTestId('members-field-action-reset')).toBeInTheDocument();
    expect(screen.getByTestId('members-field-action-hide')).toBeInTheDocument();
    expect(screen.queryByTestId('members-field-action-delete')).not.toBeInTheDocument();
  });

  it('base_overridden → Reset only (no delete, no hide)', () => {
    renderActions('base_overridden');
    expect(screen.getByTestId('members-field-action-reset')).toBeInTheDocument();
    expect(screen.queryByTestId('members-field-action-delete')).not.toBeInTheDocument();
    expect(screen.queryByTestId('members-field-action-hide')).not.toBeInTheDocument();
  });

  it('absent provenance is treated as base (conservative — no destructive delete)', () => {
    renderActions(undefined as unknown as FieldProvenance);
    expect(screen.getByTestId('members-field-action-reset')).toBeInTheDocument();
    expect(screen.queryByTestId('members-field-action-delete')).not.toBeInTheDocument();
  });
});

describe('MembersFieldActions — the actions mutate the overlay', () => {
  it('Delete (tenant_added) removes the field after confirm and closes the modal', () => {
    const onChange = vi.fn();
    const onClose = vi.fn();
    renderActions('tenant_added', { onChange, onClose });
    fireEvent.click(screen.getByTestId('members-field-action-delete'));
    fireEvent.click(screen.getByTestId('members-field-action-delete-confirm'));
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    expect(next.fields.region).toBeUndefined();
    expect(onClose).toHaveBeenCalled();
  });

  it('Reset to default (base_overridden) drops the override entry', () => {
    const onChange = vi.fn();
    renderActions('base_overridden', { fieldKey: 'personal.first_name', onChange });
    fireEvent.click(screen.getByTestId('members-field-action-reset'));
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    expect(next.fixed_overrides['personal.first_name']).toBeUndefined();
  });

  it('Hide (base) sets visible:false', () => {
    const onChange = vi.fn();
    renderActions('base', { onChange });
    fireEvent.click(screen.getByTestId('members-field-action-hide'));
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    expect(next.fields.region.visible).toBe(false);
  });

  it('Move-to-group reassigns functional_group to the chosen group (R4.3)', () => {
    const onChange = vi.fn();
    renderActions('tenant_added', { onChange });
    // LazySelect combobox: click to open the listbox, then mousedown the "Motorcycle" option.
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Motorcycle' }));
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    expect(next.fields.region.functional_group).toBe('motor');
  });
});


describe('MembersFieldActions — move-to-group reads the RESOLVED catalog, not the sparse overlay (bugfix)', () => {
  it('offers base catalog groups (address) absent from the overlay as move targets', () => {
    // currentGroupKey=personal; overlay only knows {personal, motor}; the RESOLVED catalog adds
    // address + membership. Before the fix the picker read the overlay and showed "no other group".
    renderActions('base', { currentGroupKey: 'personal' });
    // the empty-state must NOT be shown
    expect(
      screen.queryByText(/Geen andere groep beschikbaar|No other group available/i),
    ).not.toBeInTheDocument();
    // the move control is present and addressable
    expect(screen.getByTestId('members-field-action-move')).toBeInTheDocument();
  });

  it('still shows the empty-state only when the catalog has no OTHER group', () => {
    // a catalog that contains ONLY the current group → genuinely nothing to move to
    renderActions('base', {
      currentGroupKey: 'solo',
      functionalGroups: [{ key: 'solo', label: { en: 'Solo' }, order: 1 }],
    });
    expect(
      screen.getByText(/Geen andere groep beschikbaar|No other group available/i),
    ).toBeInTheDocument();
  });
});

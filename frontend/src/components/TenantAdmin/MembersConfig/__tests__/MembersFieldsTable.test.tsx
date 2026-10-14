/**
 * Tests for the fields table within a group (Members config drill-down remediation, R1.1/R1.2).
 *
 * The third drill-down tier. Post-remediation the table DISPLAYS the group's FULL resolved field
 * set — platform FIXED, CALCULATED, and tenant-ADDED — from the RESOLVED `FieldConfig`, in derived
 * `(field.order, key)` order (the I-3 fix: the raw `field_overlay` showed only tenant deltas, hiding
 * every fixed/calculated field). The working overlay stays the WRITE model. The ungrouped bucket
 * (R4.3) surfaces fields whose group is not catalog-resolvable. CONTROLLED — row-click/add signal
 * via callbacks; the editor saves once (task 4.8).
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, within, fireEvent } from '../../../../test-utils';
import i18n from '../../../../i18n';
import { MembersFieldsTable } from '../MembersFieldsTable';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import type { FieldConfig } from '../../../../types/members';

/**
 * The RESOLVED field-config the table DISPLAYS from. The `personal` group holds all three
 * provenances — a tenant-ADDED field, a platform FIXED (base) field, and a CALCULATED field — so a
 * single group exercises R1.2 (fixed+calculated+added all appear, in derived order). The resolved
 * `scope` on `region` drives the scope-axis flag. `legacy_pin` references a non-catalog group → the
 * ungrouped bucket (R4.3).
 */
function fieldConfig(): FieldConfig {
  return {
    fields: [
      // personal: order drives the derived list → first_name(1), region(2), age(3)
      {
        key: 'personal.first_name',
        functional_group: 'personal',
        provenance: 'base',
        type: 'string',
        label: { en: 'First name', nl: 'Voornaam' },
        order: 1,
      },
      {
        key: 'region',
        functional_group: 'personal',
        provenance: 'tenant_added',
        type: 'enum',
        label: { en: 'Region', nl: 'Regio' },
        order: 2,
        // served after the SAM read-wire (task 3.1); the table reads it off the resolved descriptor
        scope: { enabled: true },
      } as FieldConfig['fields'][number],
      {
        key: 'age',
        functional_group: 'personal',
        provenance: 'base',
        type: 'number',
        label: { en: 'Age', nl: 'Leeftijd' },
        order: 3,
        read_only: true, // a CALCULATED (derived) field is read-only
      },
      // a non-catalog-resolvable group → surfaced in the ungrouped bucket (R4.3)
      {
        key: 'legacy_pin',
        functional_group: 'ghost',
        provenance: 'tenant_added',
        type: 'string',
        label: { en: 'Legacy pin', nl: 'Legacy pin' },
      },
    ],
    functional_groups: [{ key: 'personal', label: { en: 'Personal', nl: 'Persoonlijk' }, order: 1 }],
  };
}

/** The WRITE model — intentionally sparse; it is NOT the display source (R1.1). */
function overlay(): MembersConfigValue {
  return {
    functional_groups: [{ key: 'personal', label_en: 'Personal', order: 1 }],
    fields: {
      region: { type: 'enum', functional_group: 'personal', scope: { enabled: true } },
    },
    fixed_overrides: {},
  };
}

function renderTable(props: Partial<React.ComponentProps<typeof MembersFieldsTable>> = {}) {
  i18n.changeLanguage('en');
  const merged: React.ComponentProps<typeof MembersFieldsTable> = {
    fieldConfig: fieldConfig(),
    overlay: overlay(),
    groupKey: 'personal',
    lang: 'en',
    ...props,
  };
  return render(
    <I18nextProvider i18n={i18n}>
      <MembersFieldsTable {...merged} />
    </I18nextProvider>,
  );
}

describe('MembersFieldsTable — displays the resolved field set (R1.1/R1.2)', () => {
  it('lists fixed + calculated + added fields, in derived (field.order, key) order', () => {
    renderTable();
    const rows = screen
      .getAllByTestId(/^members-fields-row-/)
      .map((n) => n.getAttribute('data-testid'));
    // first_name (base, order 1), region (added, order 2), age (calculated, order 3)
    expect(rows).toEqual([
      'members-fields-row-personal.first_name',
      'members-fields-row-region',
      'members-fields-row-age',
    ]);
    // legacy_pin is NOT in the personal group's table (its group is `ghost`)
    expect(screen.queryByTestId('members-fields-row-legacy_pin')).not.toBeInTheDocument();
  });

  it('shows the correct resolved type flag for each field', () => {
    renderTable();
    expect(
      within(screen.getByTestId('members-fields-row-region')).getByText('enum'),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('members-fields-row-age')).getByText('number'),
    ).toBeInTheDocument();
  });

  it('shows the scope-axis flag from the resolved scope attribute', () => {
    renderTable();
    const regionRow = screen.getByTestId('members-fields-row-region');
    expect(within(regionRow).getByText('scope axis')).toBeInTheDocument();
  });

  it('row-click opens the field modal (calls onEditField with the field key)', () => {
    const onEditField = vi.fn();
    renderTable({ onEditField });
    fireEvent.click(screen.getByTestId('members-fields-row-personal.first_name'));
    expect(onEditField).toHaveBeenCalledWith('personal.first_name');
  });

  it('the add action opens the field modal in create mode (calls onAddField with the group)', () => {
    const onAddField = vi.fn();
    renderTable({ onAddField });
    fireEvent.click(screen.getByTestId('members-fields-add-btn'));
    expect(onAddField).toHaveBeenCalledWith('personal');
  });

  it('surfaces the ungrouped bucket for a non-catalog-resolvable group reference (R4.3)', () => {
    renderTable({ groupKey: null });
    // legacy_pin (group `ghost`, not a defined catalog group) shows in the ungrouped bucket …
    expect(screen.getByTestId('members-fields-table-__ungrouped__')).toBeInTheDocument();
    expect(screen.getByTestId('members-fields-row-legacy_pin')).toBeInTheDocument();
    // … and the catalog-resolvable fields do NOT leak into it.
    expect(screen.queryByTestId('members-fields-row-personal.first_name')).not.toBeInTheDocument();
    // the ungrouped bucket offers no "add field" (you add into a real group)
    expect(screen.queryByTestId('members-fields-add-btn')).not.toBeInTheDocument();
  });

  it('shows an empty note for a group with no resolved fields', () => {
    renderTable({
      fieldConfig: { fields: [], functional_groups: [{ key: 'empty', order: 1 }] },
      overlay: { functional_groups: [{ key: 'empty', order: 1 }], fields: {}, fixed_overrides: {} },
      groupKey: 'empty',
    });
    expect(screen.getByTestId('members-fields-empty-empty')).toBeInTheDocument();
  });

  it('degrades to the working overlay fields when the resolved config is unavailable (R1.4)', () => {
    renderTable({ fieldConfig: null });
    // Falls back to the overlay's own `region` field — never blocks.
    expect(screen.getByTestId('members-fields-row-region')).toBeInTheDocument();
    // The base field (resolved-only, absent from the overlay) is NOT shown in the fallback.
    expect(screen.queryByTestId('members-fields-row-personal.first_name')).not.toBeInTheDocument();
  });
});

/**
 * Label resolution (R4): the drill-down reads the field label STRAIGHT from the served per-language
 * `label{}` dict (`label[lang] ?? label.en ?? label.nl ?? key`) — no resource-key indirection. The
 * viewer's active UI language selects the variant; the fallback is never blank.
 */
describe('MembersFieldsTable — label resolution from the served label{} (R4)', () => {
  it('shows the EN label for an EN viewer, straight off the served dict', () => {
    renderTable({ lang: 'en' });
    const row = screen.getByTestId('members-fields-row-region');
    expect(within(row).getByText('Region')).toBeInTheDocument();
  });

  it('the language selector picks the NL variant for a NL viewer', () => {
    renderTable({ lang: 'nl' });
    const row = screen.getByTestId('members-fields-row-region');
    expect(within(row).getByText('Regio')).toBeInTheDocument();
  });

  it('falls through en → nl when the active variant is absent (never blank)', () => {
    // `nl_only` ships only an NL label; an EN viewer falls through the tail to the NL value.
    renderTable({
      lang: 'en',
      fieldConfig: {
        fields: [
          {
            key: 'nl_only',
            functional_group: 'personal',
            provenance: 'tenant_added',
            type: 'string',
            label: { nl: 'Alleen NL' },
            order: 1,
          } as FieldConfig['fields'][number],
        ],
        functional_groups: [{ key: 'personal', label: { en: 'Personal' }, order: 1 }],
      },
    });
    const row = screen.getByTestId('members-fields-row-nl_only');
    expect(within(row).getByText('Alleen NL')).toBeInTheDocument();
  });

  it('falls back to the stable field key when no label resolves (never blank)', () => {
    renderTable({
      lang: 'en',
      fieldConfig: {
        fields: [
          {
            key: 'unlabelled',
            functional_group: 'personal',
            provenance: 'tenant_added',
            type: 'string',
            order: 1,
          },
        ],
        functional_groups: [{ key: 'personal', label: { en: 'Personal' }, order: 1 }],
      },
    });
    const row = screen.getByTestId('members-fields-row-unlabelled');
    // The label fell through to the key: both the label cell and the key cell show the key —
    // the label is never blank (R4.4). The first cell is the label column.
    const labelCell = row.querySelector('td');
    expect(labelCell).toHaveTextContent('unlabelled');
  });
});

/**
 * MembersFieldFormBody — the CURRENT value is always visible + selected in edit mode (s5j).
 *
 * Bug: a `<select {...formikField}>` only preselects an option when the bound value EXACTLY
 * matches a rendered `<option value>`. When the stored value is not in the option set — a LEGACY
 * scope value retired from `scope_dimensions.values`, or a role-gated enum option the caller
 * can't pick — the control fell back to its placeholder and the existing value looked BLANK.
 *
 * Fix (narrow stopgap; see myBacklog "reusable lazy dropdown"): `renderOptions` prepends the
 * current value as an option when it is non-empty and absent from the list, so the value is
 * always shown and selected while staying editable.
 */

import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@/test-utils';
import { Formik, Form } from 'formik';
import type { FieldConfig, FieldConfigField } from '../../types/members';
import { MembersFieldFormBody } from './MembersFieldFormBody';
import { groupFieldsBySection, formFields } from './fieldForm';

const t = (k: string) => k;

function renderBody(
  fields: FieldConfigField[],
  values: Record<string, unknown>,
  opts: { regionValues?: string[]; callerRoles?: string[] } = {},
) {
  const fieldConfig: FieldConfig = { fields };
  const resolved = formFields(fieldConfig);
  const sections = groupFieldsBySection(resolved, fieldConfig.functional_groups);
  return render(
    <Formik initialValues={values} onSubmit={() => {}}>
      <Form>
        <MembersFieldFormBody
          sections={sections}
          fieldConfig={fieldConfig}
          values={values}
          callerRoles={opts.callerRoles ?? []}
          lang="nl"
          t={t}
          dimensionKey="region"
          regionValues={opts.regionValues ?? []}
          membershipTypes={null}
        />
      </Form>
    </Formik>,
  );
}

describe('MembersFieldFormBody — current value always selectable (s5j)', () => {
  it('shows a LEGACY region value even when it is not in the current scope values', () => {
    const fields: FieldConfigField[] = [
      { key: 'region', group: 'overlay', type: 'enum', order: 10 },
    ];
    // Member has a legacy spelling; current dimension values use the corrected one.
    renderBody(
      fields,
      { region: 'Groningen/Drente' },
      { regionValues: ['Groningen/Drenthe', 'Oost', 'Utrecht'] },
    );

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    // The legacy value is present as an option AND is the selected value.
    const values = within(select).getAllByRole('option').map((o) => (o as HTMLOptionElement).value);
    expect(values).toContain('Groningen/Drente');
    expect(select.value).toBe('Groningen/Drente');
  });

  it('shows a rich-enum value even when the caller role cannot pick that option', () => {
    const fields: FieldConfigField[] = [
      {
        key: 'tier',
        group: 'overlay',
        type: 'enum',
        order: 10,
        options: [
          { value: 'standard', label: { nl: 'Standaard', en: 'Standard' } },
          { value: 'premium', label: { nl: 'Premium', en: 'Premium' }, roles: ['Members_CRUD'] },
        ],
      } as FieldConfigField,
    ];
    // Member is 'premium' but the caller has NO roles → premium is normally filtered out.
    renderBody(fields, { tier: 'premium', region: '' }, { callerRoles: [] });

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    const values = within(select).getAllByRole('option').map((o) => (o as HTMLOptionElement).value);
    expect(values).toContain('premium'); // preserved as the current value
    expect(select.value).toBe('premium');
  });

  it('does NOT duplicate the value when it already IS one of the options', () => {
    const fields: FieldConfigField[] = [
      { key: 'region', group: 'overlay', type: 'enum', order: 10 },
    ];
    renderBody(fields, { region: 'Oost' }, { regionValues: ['Oost', 'Utrecht'] });

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    const oostCount = within(select)
      .getAllByRole('option')
      .filter((o) => (o as HTMLOptionElement).value === 'Oost').length;
    expect(oostCount).toBe(1);
    expect(select.value).toBe('Oost');
  });
});

/**
 * MembersFieldFormBody — the CURRENT value is always visible in edit mode (s5j → LazySelect).
 *
 * Original bug: a `<select {...formikField}>` only preselects an option when the bound value
 * EXACTLY matches a rendered `<option value>`. When the stored value was not in the option set —
 * a LEGACY scope value retired from `scope_dimensions.values`, or a role-gated enum option the
 * caller can't pick — the control fell back to its placeholder and the existing value looked BLANK.
 *
 * The s5j stopgap (`renderOptions` prepending the current value as a synthetic, SELECTABLE
 * `<option>`) has been retired: the generic dropdown branch now renders `<LazySelect>`, which owns
 * "tolerate legacy, enforce on change". The out-of-set / role-gated current value is still shown at
 * rest ON THE TRIGGER (never blanked — LazySelect R1), but it is NOT injected into the open list as
 * a selectable option (LazySelect R5.2). That is the intended behavioral shift from the old
 * synthetic `<option>`: legacy data stays visible and preserved, but is never *offered*.
 *
 * These tests preserve the original intent — the out-of-set value is still VISIBLE and preserved,
 * and an in-set value is not duplicated — expressed against the LazySelect markup: a
 * `role="combobox"` trigger (testid `${name}-lazyselect`) at rest, and a `role="listbox"` of
 * `role="option"` children only after opening the control.
 *
 * @see .kiro/specs/Common/Frameworks/lazy-select/  (Requirements 8.1, 9.1, 9.2)
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@/test-utils';
import '../../i18n';
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
    <Formik initialValues={values} onSubmit={() => { }}>
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

describe('MembersFieldFormBody — current value always visible + preserved (LazySelect)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a LEGACY region value at rest even when it is not in the current scope values', () => {
    const fields: FieldConfigField[] = [
      { key: 'region', group: 'overlay', type: 'enum', order: 10 },
    ];
    // Member has a legacy spelling; current dimension values use the corrected one.
    renderBody(
      fields,
      { region: 'Groningen/Drente' },
      { regionValues: ['Groningen/Drenthe', 'Oost', 'Utrecht'] },
    );

    // At rest the legacy value is displayed on the combobox trigger (never blanked) — R1.1/R1.3.
    const trigger = screen.getByRole('combobox');
    expect(trigger).toHaveTextContent('Groningen/Drente');
    expect(screen.getByTestId('region-lazyselect')).toHaveTextContent('Groningen/Drente');

    // After OPENING, the out-of-set legacy value is NOT offered as a selectable option (R5.2 —
    // the behavioral shift from the old synthetic <option>: tolerated at rest, never offered).
    // The in-set corrected values ARE offered.
    fireEvent.click(trigger);
    const listbox = screen.getByRole('listbox');
    const optionLabels = within(listbox).getAllByRole('option').map((o) => o.textContent);
    expect(optionLabels).toEqual(['Groningen/Drenthe', 'Oost', 'Utrecht']);
    expect(within(listbox).queryByRole('option', { name: 'Groningen/Drente' })).not.toBeInTheDocument();
  });

  it('shows a rich-enum value at rest even when the caller role cannot pick that option', () => {
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

    // The role-gated current value is preserved + shown at rest on the trigger (R1.1) — here as its
    // in-set label 'Premium' (the value maps to a known option even though the caller can't pick it).
    const trigger = screen.getByRole('combobox');
    expect(trigger).toHaveTextContent('Premium');
    expect(screen.getByTestId('tier-lazyselect')).toHaveTextContent('Premium');

    // After OPENING, 'Premium' is NOT offered (role-gated out of the selectable list); only the
    // caller-permitted 'Standaard' is offered (R5.1/R5.2).
    fireEvent.click(trigger);
    const listbox = screen.getByRole('listbox');
    const optionLabels = within(listbox).getAllByRole('option').map((o) => o.textContent);
    expect(optionLabels).toEqual(['Standaard']);
    expect(within(listbox).queryByRole('option', { name: 'Premium' })).not.toBeInTheDocument();
  });

  it('does NOT duplicate the value when it already IS one of the options', () => {
    const fields: FieldConfigField[] = [
      { key: 'region', group: 'overlay', type: 'enum', order: 10 },
    ];
    renderBody(fields, { region: 'Oost' }, { regionValues: ['Oost', 'Utrecht'] });

    // In-set value is shown/selected at rest on the trigger.
    const trigger = screen.getByRole('combobox');
    expect(trigger).toHaveTextContent('Oost');

    // After opening, the in-set value appears exactly once as an option and is marked selected.
    fireEvent.click(trigger);
    const listbox = screen.getByRole('listbox');
    const oostOptions = within(listbox)
      .getAllByRole('option')
      .filter((o) => o.textContent === 'Oost');
    expect(oostOptions).toHaveLength(1);
    expect(oostOptions[0]).toHaveAttribute('aria-selected', 'true');
  });
});

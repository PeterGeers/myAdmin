/**
 * MembersFieldFormBody — membership_type dropdown (spec 03b: a normal enum field).
 *
 * Verifies the shared add/edit form body renders `membership_type` as a DROPDOWN whose options are
 * the field's OWN resolved `options`, each shown by its bilingual label, with NO free-text input.
 *
 * Spec 03b retired the live `membershiptype#` catalog: membership_type is now an ordinary
 * reference/enum field that owns its vocabulary, so its options are fed EAGERLY from the field
 * config's `options` through the SAME path as every other rich-enum field — there is NO async
 * `listMembershipTypes(true)` fetch and NO `membershipTypes` prop. The options are not in the DOM
 * at rest; they appear inside a `role="listbox"` only after the trigger is clicked.
 *
 * LazySelect resolves an option's bilingual label via the active i18n language (not the component's
 * `lang` prop), so each test sets `i18n.changeLanguage(...)` explicitly.
 *
 * @see .kiro/specs/Common/Frameworks/lazy-select/  (Requirements 8.1, 9.1, 9.2)
 * **Validates: Requirements 3.1, 3.3, 5.8**
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { Formik, Form } from 'formik';
import i18n from '../../i18n';
import type { FieldConfig, FieldConfigField } from '../../types/members';
import { MembersFieldFormBody } from './MembersFieldFormBody';
import { groupFieldsBySection, formFields } from './fieldForm';
import { render, screen, within, fireEvent, waitFor } from '@/test-utils';

const t = (k: string) => k;

// The membership_type field owns its vocabulary as inline rich-enum `options` (spec 03b). The two
// ACTIVE options below are fed eagerly to the dropdown; an `allowed:false`/absent option would be
// grandfathered-but-not-offered, but the offered-set assertions here use only allowed options.
const FIELDS: FieldConfigField[] = [
  { key: 'first_name', group: 'personal', type: 'string', order: 10 },
  {
    key: 'membership_type', group: 'membership', type: 'reference', required: true, order: 20,
    options: [
      { value: 'erelid', label: { nl: 'Erelid', en: 'Honorary' } },
      { value: 'donateur', label: { nl: 'Donateur', en: 'Donor' } },
    ],
  },
];

const fieldConfig: FieldConfig = { fields: FIELDS };

function renderBody(lang = 'nl') {
  const fields = formFields(fieldConfig);
  const sections = groupFieldsBySection(fields, fieldConfig.functional_groups);
  return render(
    <Formik initialValues={{ first_name: '', membership_type: '', region: '' }} onSubmit={() => { }}>
      <Form>
        <MembersFieldFormBody
          sections={sections}
          fieldConfig={fieldConfig}
          values={{ first_name: '', membership_type: '', region: '' }}
          callerRoles={[]}
          lang={lang}
          t={t}
          dimensionKey="region"
          regionValues={[]}
        />
      </Form>
    </Formik>,
  );
}

/** Open the membership_type LazySelect and return its listbox (options are eager — no async wait). */
function openMembershipType() {
  const trigger = screen.getByTestId('membership_type-lazyselect').querySelector('[role="combobox"]');
  fireEvent.click(trigger as Element);
  return screen.getByRole('listbox');
}

describe('MembersFieldFormBody — membership_type dropdown (spec 03b, eager field options)', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('nl');
  });

  it('offers exactly the field options as options (Dutch labels, no free-text)', async () => {
    await i18n.changeLanguage('nl');
    renderBody('nl');

    const listbox = openMembershipType();

    await waitFor(() => {
      expect(within(listbox).getAllByRole('option')).toHaveLength(2);
    });
    const labels = within(listbox).getAllByRole('option').map((o) => o.textContent);
    expect(labels).toEqual(['Erelid', 'Donateur']);
    expect(within(listbox).getByRole('option', { name: 'Erelid' })).toBeInTheDocument();
    expect(within(listbox).getByRole('option', { name: 'Donateur' })).toBeInTheDocument();
  });

  it('shows the English labels when the language is en', async () => {
    await i18n.changeLanguage('en');
    renderBody('en');

    const listbox = openMembershipType();

    await waitFor(() => {
      expect(within(listbox).getAllByRole('option')).toHaveLength(2);
    });
    const labels = within(listbox).getAllByRole('option').map((o) => o.textContent);
    expect(labels).toEqual(['Honorary', 'Donor']);
  });

  it('offers no options when the field carries none (no free-text fallback)', async () => {
    await i18n.changeLanguage('nl');
    const emptyConfig: FieldConfig = {
      fields: [
        { key: 'first_name', group: 'personal', type: 'string', order: 10 },
        { key: 'membership_type', group: 'membership', type: 'reference', required: true, order: 20, options: [] },
      ],
    };
    const fields = formFields(emptyConfig);
    const sections = groupFieldsBySection(fields, emptyConfig.functional_groups);
    render(
      <Formik initialValues={{ first_name: '', membership_type: '', region: '' }} onSubmit={() => { }}>
        <Form>
          <MembersFieldFormBody
            sections={sections}
            fieldConfig={emptyConfig}
            values={{ first_name: '', membership_type: '', region: '' }}
            callerRoles={[]}
            lang="nl"
            t={t}
            dimensionKey="region"
            regionValues={[]}
          />
        </Form>
      </Formik>,
    );

    const listbox = openMembershipType();
    await waitFor(() => {
      expect(within(listbox).queryAllByRole('option')).toHaveLength(0);
    });
    expect(within(listbox).getByText(i18n.t('placeholders.noOptions'))).toBeInTheDocument();
  });
});

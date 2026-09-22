/**
 * MembersFieldFormBody — membership_type catalog dropdown (s5c task 4.7, design C-SURFACE; R5.8).
 *
 * Verifies that the shared add/edit form body renders the `membership_type` field as a DROPDOWN
 * whose options are the tenant's ACTIVE **Lidmaatschap Beheer** catalog entries — the list the
 * page fetches via `listMembershipTypes(true)` (`GET /membership-types?active_only=true`) and
 * threads in as `membershipTypes` — with each option shown by its bilingual label. The domain
 * layer re-validates the chosen type authoritatively (covered by the SAM tests); this asserts the
 * presentation-only convenience: only active types appear, and no free-text input is offered.
 *
 * **Validates: Requirements 5.8**
 */

import { vi, describe, it, expect } from 'vitest';
import { render, screen, within } from '@/test-utils';
import { Formik, Form } from 'formik';
import type { FieldConfig, FieldConfigField, MembershipType } from '../../types/members';
import { MembersFieldFormBody } from './MembersFieldFormBody';
import { groupFieldsBySection, formFields } from './fieldForm';

const t = (k: string) => k;

const FIELDS: FieldConfigField[] = [
  { key: 'first_name', group: 'personal', type: 'string', order: 10 },
  { key: 'membership_type', group: 'membership', type: 'reference', required: true, order: 20 },
];

const fieldConfig: FieldConfig = { fields: FIELDS };

const ACTIVE_TYPES: MembershipType[] = [
  { key: 'erelid', label: { nl: 'Erelid', en: 'Honorary' }, active: true },
  { key: 'donateur', label: { nl: 'Donateur', en: 'Donor' }, active: true },
];

function renderBody(membershipTypes: MembershipType[] | null, lang = 'nl') {
  const fields = formFields(fieldConfig);
  const sections = groupFieldsBySection(fields, fieldConfig.functional_groups);
  return render(
    <Formik initialValues={{ first_name: '', membership_type: '', region: '' }} onSubmit={() => {}}>
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
          membershipTypes={membershipTypes}
        />
      </Form>
    </Formik>,
  );
}

describe('MembersFieldFormBody — membership_type catalog dropdown (R5.8)', () => {
  it('renders a select whose options are the ACTIVE catalog entries (bilingual label)', () => {
    renderBody(ACTIVE_TYPES);
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    const optionValues = within(select).getAllByRole('option').map((o) => (o as HTMLOptionElement).value);
    // The blank placeholder + the two active catalog codes.
    expect(optionValues).toContain('erelid');
    expect(optionValues).toContain('donateur');
    // Dutch labels are shown for lang=nl.
    expect(within(select).getByText('Erelid')).toBeInTheDocument();
    expect(within(select).getByText('Donateur')).toBeInTheDocument();
  });

  it('shows the English label when lang=en', () => {
    renderBody(ACTIVE_TYPES, 'en');
    const select = screen.getByRole('combobox');
    expect(within(select).getByText('Honorary')).toBeInTheDocument();
    expect(within(select).getByText('Donor')).toBeInTheDocument();
  });

  it('renders no catalog options when the active feed is empty (no free-text fallback)', () => {
    renderBody([]);
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    const optionValues = within(select)
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value)
      .filter((v) => v !== '');
    expect(optionValues).toEqual([]);
  });
});

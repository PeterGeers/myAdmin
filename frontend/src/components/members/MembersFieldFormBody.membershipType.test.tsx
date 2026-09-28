/**
 * MembersFieldFormBody — membership_type catalog dropdown (s5c task 4.7 → LazySelect; R5.8, R8.1).
 *
 * Verifies that the shared add/edit form body renders the `membership_type` field as a DROPDOWN
 * whose options are the tenant's ACTIVE **Lidmaatschap Beheer** catalog entries, each shown by its
 * bilingual label, with NO free-text input. The domain layer re-validates the chosen type
 * authoritatively (covered by the SAM tests); this asserts the presentation-only convenience: only
 * active types are offered, and the offered set is EXACTLY the active catalog (no free-text).
 *
 * Behavioral shift vs. the old native `<select>`: the field now renders `<LazySelect>` and loads its
 * options ASYNC on open via `listMembershipTypes(true)` (mapped by `membershipTypeOptions`). The
 * `membershipTypes` prop is no longer read for this field — the component calls the service — so the
 * test MOCKS `../../services/membersApiService` and awaits the fetch after opening the combobox. The
 * options are NOT in the DOM at rest; they appear inside a `role="listbox"` only after the trigger
 * is clicked.
 *
 * LazySelect resolves an option's bilingual label via the active i18n language (not the component's
 * `lang` prop), so each test sets `i18n.changeLanguage(...)` explicitly.
 *
 * @see .kiro/specs/Common/Frameworks/lazy-select/  (Requirements 8.1, 9.1, 9.2)
 * **Validates: Requirements 5.8**
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, within, fireEvent, waitFor } from '@/test-utils';
import i18n from '../../i18n';
import { Formik, Form } from 'formik';
import type { FieldConfig, FieldConfigField, MembershipType } from '../../types/members';
import { MembersFieldFormBody } from './MembersFieldFormBody';
import { groupFieldsBySection, formFields } from './fieldForm';

// The membership_type field loads its options ASYNC via the members API service on open. Mock the
// module the component imports (`../../services/membersApiService`) so `listMembershipTypes(true)`
// resolves the ACTIVE catalog without any network. The component maps the result through
// `membershipTypeOptions`, so the resolved shape must match `MembershipType[]`.
const listMembershipTypes = vi.fn();
vi.mock('../../services/membersApiService', () => ({
  listMembershipTypes: (...args: unknown[]) => listMembershipTypes(...args),
}));

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
          membershipTypes={null}
        />
      </Form>
    </Formik>,
  );
}

/** Open the membership_type LazySelect and wait for the async catalog fetch to settle. */
async function openMembershipTypeAndAwaitOptions() {
  const trigger = screen.getByTestId('membership_type-lazyselect').querySelector('[role="combobox"]');
  fireEvent.click(trigger as Element);
  // The options resolve asynchronously after open; wait until the fetch has run.
  await waitFor(() => expect(listMembershipTypes).toHaveBeenCalledWith(true));
  return screen.getByRole('listbox');
}

describe('MembersFieldFormBody — membership_type catalog dropdown (R5.8, LazySelect)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('offers exactly the ACTIVE catalog entries as options (Dutch labels, no free-text)', async () => {
    await i18n.changeLanguage('nl');
    listMembershipTypes.mockResolvedValue(ACTIVE_TYPES);
    renderBody('nl');

    const listbox = await openMembershipTypeAndAwaitOptions();

    await waitFor(() => {
      expect(within(listbox).getAllByRole('option')).toHaveLength(ACTIVE_TYPES.length);
    });
    // Offered set is EXACTLY the active catalog, by Dutch label (no free-text entry offered).
    const labels = within(listbox).getAllByRole('option').map((o) => o.textContent);
    expect(labels).toEqual(['Erelid', 'Donateur']);
    expect(within(listbox).getByRole('option', { name: 'Erelid' })).toBeInTheDocument();
    expect(within(listbox).getByRole('option', { name: 'Donateur' })).toBeInTheDocument();
  });

  it('shows the English labels when the language is en', async () => {
    await i18n.changeLanguage('en');
    listMembershipTypes.mockResolvedValue(ACTIVE_TYPES);
    renderBody('en');

    const listbox = await openMembershipTypeAndAwaitOptions();

    await waitFor(() => {
      expect(within(listbox).getAllByRole('option')).toHaveLength(ACTIVE_TYPES.length);
    });
    const labels = within(listbox).getAllByRole('option').map((o) => o.textContent);
    expect(labels).toEqual(['Honorary', 'Donor']);
  });

  it('offers no catalog options when the active feed is empty (no free-text fallback)', async () => {
    await i18n.changeLanguage('nl');
    listMembershipTypes.mockResolvedValue([]);
    renderBody('nl');

    const listbox = await openMembershipTypeAndAwaitOptions();

    // Empty feed → zero selectable options offered (the "no options" row instead of any free-text).
    await waitFor(() => {
      expect(within(listbox).queryAllByRole('option')).toHaveLength(0);
    });
    // The localized "no options" row is shown (nl: "Geen opties beschikbaar") — never a free-text input.
    expect(within(listbox).getByText(i18n.t('placeholders.noOptions'))).toBeInTheDocument();
  });
});

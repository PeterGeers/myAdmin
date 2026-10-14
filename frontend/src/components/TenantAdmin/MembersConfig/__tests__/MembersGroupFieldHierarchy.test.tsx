/**
 * Tests for the group → field → attribute authoring hierarchy (Members config redesign Phase 3
 * step 11 — task 4.1, R4.1/R4.2/R4.3).
 *
 * Covers the two halves task 4.1 adds:
 *  - `groupResolvedFields` — the pure derivation that buckets resolved fields under their
 *    functional group and orders them by the DERIVED `(group.order, field.order, key)` rule, with
 *    NO stored absolute position (R4.1/R4.2), surfacing a non-catalog-resolvable group reference in
 *    a trailing "ungrouped" bucket rather than dropping it (R4.3);
 *  - `MembersGroupFieldHierarchy` — the presentation of that hierarchy: group sections, nested
 *    fields, and per-field attribute chips (type / required / visibility / scope axis / provenance).
 *
 * The derivation is the catalog-first contract (`38-sam-module-field-config.md` rules 1/2): every
 * DEFINED catalog group is a section (even empty), the display order is derived not stored, and an
 * unresolvable field reference is kept visible — the picker-resolvability guard made observable.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, within, fireEvent, waitFor } from '../../../../test-utils';
import { groupResolvedFields } from '../../../../services/membersConfigService';
import { MembersGroupFieldHierarchy } from '../MembersGroupFieldHierarchy';
import type { FieldConfig } from '../../../../types/members';
import i18n from '../../../../i18n';

/** Render the hierarchy inside the real i18n instance at a given language (task 4.2 i18n). */
function renderWithI18n(ui: React.ReactElement, lng: 'nl' | 'en') {
  i18n.changeLanguage(lng);
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

/**
 * A resolved field-config deliberately NOT in display order on the wire, so the tests prove the
 * hierarchy DERIVES `(group.order, field.order, key)`:
 *   - group `membership` has order 3, group `personal` order 1 → personal section comes first.
 *   - within `personal`: first_name (order 1) before last_name (order 2); nickname (no order) last.
 *   - `orphan_field` references a group ('ghost') NOT in functional_groups → trailing bucket (R4.3).
 */
const CONFIG: FieldConfig = {
  fields: [
    {
      key: 'membership.status',
      functional_group: 'membership',
      order: 1,
      origin: 'fixed',
      provenance: 'base',
      type: 'enum',
      required: true,
      label: { en: 'Status', nl: 'Status' },
    },
    {
      key: 'personal.last_name',
      functional_group: 'personal',
      order: 2,
      origin: 'fixed',
      provenance: 'base',
      type: 'string',
      label: { en: 'Last name', nl: 'Achternaam' },
    },
    {
      key: 'personal.first_name',
      functional_group: 'personal',
      order: 1,
      origin: 'fixed',
      provenance: 'base_overridden',
      type: 'string',
      label: { en: 'First name', nl: 'Voornaam' },
    },
    {
      key: 'nickname',
      functional_group: 'personal',
      origin: 'variable',
      provenance: 'tenant_added',
      type: 'string',
      visible: false,
      label: { en: 'Nickname', nl: 'Bijnaam' },
    },
    {
      key: 'orphan_field',
      functional_group: 'ghost',
      origin: 'variable',
      provenance: 'tenant_added',
      type: 'string',
      label: { en: 'Orphan', nl: 'Wees' },
    },
  ],
  functional_groups: [
    { key: 'membership', label: { en: 'Membership', nl: 'Lidmaatschap' }, order: 3 },
    { key: 'personal', label: { en: 'Personal', nl: 'Persoonlijk' }, order: 1 },
    // An empty defined group — a tenant can author fields into it; it must still render.
    { key: 'address', label: { en: 'Address', nl: 'Adres' }, order: 2 },
  ],
};

describe('groupResolvedFields (group → field → attribute derivation, R4.1/R4.2/R4.3)', () => {
  it('emits a section for EVERY defined catalog group, ordered by (group.order, key)', () => {
    const sections = groupResolvedFields(CONFIG);
    // personal (1), address (2), membership (3) — defined groups in derived order; then the
    // trailing "ungrouped" bucket for orphan_field.
    expect(sections.map((s) => (s.resolved ? s.key : '__ungrouped__'))).toEqual([
      'personal',
      'address',
      'membership',
      '__ungrouped__',
    ]);
  });

  it('nests fields within their group ordered by (field.order, key), no stored position', () => {
    const sections = groupResolvedFields(CONFIG);
    const personal = sections.find((s) => s.key === 'personal')!;
    // first_name (order 1), last_name (order 2), nickname (no order → last, then key tiebreak).
    expect(personal.fields.map((f) => f.key)).toEqual([
      'personal.first_name',
      'personal.last_name',
      'nickname',
    ]);
  });

  it('keeps an empty defined group as a section (a tenant can author into it)', () => {
    const sections = groupResolvedFields(CONFIG);
    const address = sections.find((s) => s.key === 'address')!;
    expect(address.resolved).toBe(true);
    expect(address.fields).toHaveLength(0);
  });

  it('surfaces a non-catalog-resolvable group reference in a trailing bucket, never dropped (R4.3)', () => {
    const sections = groupResolvedFields(CONFIG);
    const ungrouped = sections.find((s) => !s.resolved)!;
    expect(ungrouped).toBeTruthy();
    expect(ungrouped.fields.map((f) => f.key)).toEqual(['orphan_field']);
  });

  it('preserves the field SET — the union of sections equals the input fields (Property-1 invariant)', () => {
    const sections = groupResolvedFields(CONFIG);
    const seen = sections.flatMap((s) => s.fields.map((f) => f.key)).sort();
    const input = CONFIG.fields.map((f) => f.key).sort();
    expect(seen).toEqual(input);
  });

  it('returns no sections for a null/absent config', () => {
    expect(groupResolvedFields(null)).toEqual([]);
    expect(groupResolvedFields(undefined)).toEqual([]);
    expect(groupResolvedFields({ fields: [] })).toEqual([]);
  });
});

describe('MembersGroupFieldHierarchy (presentation, R4.1/R4.2)', () => {
  it('renders a section per defined group plus the ungrouped bucket', () => {
    render(<MembersGroupFieldHierarchy config={CONFIG} lang="en" />);
    expect(screen.getByTestId('members-group-field-hierarchy')).toBeInTheDocument();
    expect(screen.getByTestId('members-hierarchy-group-personal')).toBeInTheDocument();
    expect(screen.getByTestId('members-hierarchy-group-address')).toBeInTheDocument();
    expect(screen.getByTestId('members-hierarchy-group-membership')).toBeInTheDocument();
    expect(screen.getByTestId('members-hierarchy-group-__ungrouped__')).toBeInTheDocument();
  });

  it('nests each field under its group in the derived order', () => {
    render(<MembersGroupFieldHierarchy config={CONFIG} lang="en" />);
    const personal = screen.getByTestId('members-hierarchy-group-personal');
    const fieldIds = within(personal)
      .getAllByTestId(/^members-hierarchy-field-/)
      .map((n) => n.getAttribute('data-testid'));
    expect(fieldIds).toEqual([
      'members-hierarchy-field-personal.first_name',
      'members-hierarchy-field-personal.last_name',
      'members-hierarchy-field-nickname',
    ]);
  });

  it('shows per-field attribute chips (type / required / hidden / scope)', () => {
    const config: FieldConfig = {
      fields: [
        {
          key: 'region',
          functional_group: 'personal',
          order: 1,
          origin: 'variable',
          provenance: 'tenant_added',
          type: 'string',
          required: true,
          // scope-axis attribute carried on the resolved descriptor. (The analytics-role
          // `alias` chip was removed — members-analytics-role-removal.)
          ...({ scope: { enabled: true, values: ['A'] } } as object),
        },
      ],
      functional_groups: [{ key: 'personal', label: { en: 'Personal' }, order: 1 }],
    };
    render(<MembersGroupFieldHierarchy config={config} lang="en" />);
    expect(screen.getByTestId('members-hierarchy-attr-type-region')).toHaveTextContent('string');
    expect(screen.getByTestId('members-hierarchy-attr-required-region')).toHaveTextContent('required');
    expect(screen.getByTestId('members-hierarchy-attr-scope-region')).toHaveTextContent('scope axis');
    expect(screen.queryByTestId('members-hierarchy-attr-alias-region')).not.toBeInTheDocument();
  });

  it('renders a provenance badge per field (shared vocabulary with the provenance list)', () => {
    render(<MembersGroupFieldHierarchy config={CONFIG} lang="en" />);
    expect(
      screen.getByTestId('members-hierarchy-provenance-personal.first_name'),
    ).toHaveTextContent('Base (overridden)');
    expect(
      screen.getByTestId('members-hierarchy-provenance-nickname'),
    ).toHaveTextContent('Tenant-added');
  });

  it('degrades to an "unavailable" note when the config is null', () => {
    render(<MembersGroupFieldHierarchy config={null} lang="en" />);
    expect(screen.getByTestId('members-group-field-hierarchy-empty')).toBeInTheDocument();
  });
});

/**
 * Task 4.2 — composition from the REGISTERED building blocks (R4.5, `37`) + the `32`
 * table/accessibility conventions. The per-group field list is rendered via the Table Filter
 * Framework v2 (`useFilterableTable` + `FilterableHeader`), not a bespoke Chakra layout.
 */
describe('MembersGroupFieldHierarchy — building-block composition + accessibility (R4.5/R4.6)', () => {
  it('renders each non-empty group as a sortable/filterable table with FilterableHeader columns', () => {
    render(<MembersGroupFieldHierarchy config={CONFIG} lang="en" />);
    const personal = screen.getByTestId('members-hierarchy-group-personal');
    // Table Filter Framework v2 is a real <table> (steering 32 table layout) with an aria-label.
    const table = within(personal).getByRole('table');
    expect(table).toHaveAttribute('aria-label', expect.stringContaining('Personal'));
    // Sortable headers expose aria-sort (FilterableHeader accessibility) — Field + Key + Provenance.
    const sortableHeaders = within(personal)
      .getAllByRole('columnheader')
      .filter((th) => th.getAttribute('aria-sort') !== null);
    expect(sortableHeaders.length).toBeGreaterThanOrEqual(3);
    sortableHeaders.forEach((th) => expect(th).toHaveAttribute('aria-sort', 'none'));
    // The sort affordance is keyboard-activatable (role="button" + an aria-label naming the column).
    expect(
      within(personal).getByRole('button', { name: /Sort by Field/i }),
    ).toBeInTheDocument();
  });

  it('filters a group table by the field-label column via the FilterableHeader input', async () => {
    render(<MembersGroupFieldHierarchy config={CONFIG} lang="en" />);
    const personal = screen.getByTestId('members-hierarchy-group-personal');
    // All three personal fields present initially.
    expect(within(personal).getAllByTestId(/^members-hierarchy-field-/)).toHaveLength(3);
    // Type a filter into the Field column header input → only matching rows survive (the Table
    // Filter Framework debounces, so await the filtered result).
    const fieldFilter = within(personal).getByLabelText('Filter by Field');
    fireEvent.change(fieldFilter, { target: { value: 'first' } });
    await waitFor(() => {
      const remaining = within(personal)
        .getAllByTestId(/^members-hierarchy-field-/)
        .map((n) => n.getAttribute('data-testid'));
      expect(remaining).toEqual(['members-hierarchy-field-personal.first_name']);
    });
  });

  it('sorts a group table when a sortable header is activated (asc flips the derived order)', () => {
    render(<MembersGroupFieldHierarchy config={CONFIG} lang="en" />);
    const personal = screen.getByTestId('members-hierarchy-group-personal');
    const keyHeader = within(personal).getByRole('button', { name: /Sort by Key/i });
    fireEvent.click(keyHeader);
    const sorted = within(personal)
      .getAllByTestId(/^members-hierarchy-field-/)
      .map((n) => n.getAttribute('data-testid'));
    // asc by key: 'nickname' < 'personal.first_name' < 'personal.last_name'.
    expect(sorted).toEqual([
      'members-hierarchy-field-nickname',
      'members-hierarchy-field-personal.first_name',
      'members-hierarchy-field-personal.last_name',
    ]);
  });
});

/**
 * Task 4.2 — i18n Option (b) (R4.4, `38` rule 6): shipped labels resolve via resource keys
 * (`admin:membersConfig.field/group/enum.*`) with an inline per-language tenant override that
 * wins; an enum option's `value` is language-neutral, only its `label` is per-language.
 */
describe('MembersGroupFieldHierarchy — i18n resource-key resolution + inline override (R4.4)', () => {
  beforeEach(() => i18n.changeLanguage('en'));

  /** A config whose shipped fields carry NO inline label → labels must come from resource keys. */
  const SHIPPED: FieldConfig = {
    fields: [
      // Shipped base field, dotted key, NO inline label → resolves from
      // admin:membersConfig.field.first_name.
      { key: 'personal.first_name', functional_group: 'personal', order: 1, provenance: 'base' },
      // Shipped enum field, NO inline label; its options carry language-neutral values whose
      // labels resolve from admin:membersConfig.enum.status.<value>.
      {
        key: 'status',
        functional_group: 'membership',
        order: 1,
        provenance: 'base',
        type: 'enum',
        options: ['active', 'lapsed'],
      },
    ],
    functional_groups: [
      // Shipped group, NO inline label → resolves from admin:membersConfig.group.personal / .membership.
      { key: 'personal', order: 1 },
      { key: 'membership', order: 2 },
    ],
  };

  it('resolves a shipped FIELD label from its resource key when no inline override is present', () => {
    renderWithI18n(<MembersGroupFieldHierarchy config={SHIPPED} lang="en" />, 'en');
    expect(
      within(screen.getByTestId('members-hierarchy-field-personal.first_name')).getByText('First name'),
    ).toBeInTheDocument();
    // NL resolves the Dutch resource value for the same key.
    screen.getByTestId('members-group-field-hierarchy'); // sanity: mounted
  });

  it('resolves a shipped GROUP heading from its resource key (NL locale)', () => {
    renderWithI18n(<MembersGroupFieldHierarchy config={SHIPPED} lang="nl" />, 'nl');
    const personal = screen.getByTestId('members-hierarchy-group-personal');
    expect(within(personal).getByText('Persoonlijk')).toBeInTheDocument();
  });

  it('lets an inline per-language tenant override WIN over the shipped resource key', () => {
    const overridden: FieldConfig = {
      fields: [
        {
          key: 'personal.first_name',
          functional_group: 'personal',
          order: 1,
          provenance: 'base_overridden',
          // Tenant relabels the shipped field in both languages.
          label: { en: 'Given name', nl: 'Roepnaam' },
        },
      ],
      functional_groups: [{ key: 'personal', order: 1 }],
    };
    renderWithI18n(<MembersGroupFieldHierarchy config={overridden} lang="en" />, 'en');
    const row = screen.getByTestId('members-hierarchy-field-personal.first_name');
    expect(within(row).getByText('Given name')).toBeInTheDocument();
    // The shipped resource label is NOT shown when the inline override is present.
    expect(within(row).queryByText('First name')).not.toBeInTheDocument();
  });

  it('renders enum options as a language-neutral value + a per-language resolved label', () => {
    renderWithI18n(<MembersGroupFieldHierarchy config={SHIPPED} lang="en" />, 'en');
    const activeOpt = screen.getByTestId('members-hierarchy-enum-status-active');
    // The VALUE segment appears verbatim (never translated) …
    expect(activeOpt).toHaveTextContent('active');
    // … and the shipped per-language LABEL resolves from the enum resource key.
    expect(activeOpt).toHaveTextContent('Active');
  });
});

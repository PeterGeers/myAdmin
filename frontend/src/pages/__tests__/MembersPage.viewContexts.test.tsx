/**
 * MembersPage view contexts (generic renderer) — task 3.3 (design C-VIEW)
 *
 * Verifies the parameter-driven view-context renderer on the Members Overzicht
 * page (R5.1, R5.1a, Property 7):
 *
 * (a) DROPDOWN GATING — the context dropdown lists ONLY the contexts the current
 *     user's roles permit: a context with `permission_roles` the caller lacks is
 *     omitted; a context with empty/absent `permission_roles` is available to all.
 * (b) PER-CONTEXT COLUMNS — selecting a context renders exactly its `columns`
 *     (resolved against `fieldConfig.fields`) via the existing filterable-table
 *     toolkit, in context order.
 * (c) SKIP UNRESOLVABLE — a `columns` entry with no matching field key is SKIPPED
 *     (never a crash), the resolvable columns still render (Property 7 / R5.1a).
 * (d) DEFAULT/EMPTY CONTEXT — a context with empty `columns` (the `__default__`
 *     sentinel) shows all visible fields (today's compact/full behavior), i.e. the
 *     compact/full switch is present and the fixed columns render.
 *
 * Mocking/render approach matches the sibling MembersPage tests: the service
 * layer is mocked with `vi.mock` + `vi.mocked(...)`; the page is rendered with the
 * shared `@/test-utils` `render` helper (ChakraProvider); `useTypedTranslation`
 * returns raw i18n keys so labels/buttons are asserted by their raw keys. `useAuth`
 * is mocked with a per-test mutable role set so we can drive the gating.
 *
 * **Property 7: Config references resolve or are safely dropped.**
 * **Validates: Requirements 5.1, 5.1a**
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@/test-utils';
import MembersPage from '../MembersPage';
import * as membersApiService from '../../services/membersApiService';
import type { Member, FieldConfig, ViewContext } from '../../types/members';

vi.mock('../../services/membersApiService');

// Per-test controllable role set backing `useAuth().hasAnyRole`. Reset in
// beforeEach; individual tests set it before rendering.
let currentRoles: string[] = [];
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    hasAnyRole: (roles: string[]) => roles.some(r => currentRoles.includes(r)),
  }),
}));

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockListMembershipTypes = vi.mocked(membersApiService.listMembershipTypes);

const mockMembers: Member[] = [
  {
    member_id: 'm-1',
    name: 'Jan',
    email: 'jan@h-dcn.example',
    status: 'active',
    membership_type: 'regulier',
    region: 'Noord',
    iban: 'NL00BANK0123456789',
    payment_method: 'incasso',
  },
  {
    member_id: 'm-2',
    name: 'Piet',
    email: 'piet@h-dcn.example',
    status: 'active',
    membership_type: 'erelid',
    region: 'Zuid',
    iban: 'NL11BANK9876543210',
    payment_method: 'factuur',
  },
];

/** Fields the tenant authored (fixed ⊕ overlay), the resolvable key set. */
const FIELDS: FieldConfig['fields'] = [
  { key: 'name', label: 'Naam', compact: true, order: 1 },
  { key: 'email', label: 'E-mail', order: 2 },
  { key: 'status', label: 'Status', order: 3 },
  { key: 'membership_type', label: 'Type', order: 4 },
  { key: 'iban', label: 'IBAN', order: 10 },
  { key: 'payment_method', label: 'Betaalwijze', order: 11 },
];

// Two authored contexts: "overview" is open to Members_Read/Members_CRUD;
// "financial" is restricted to Members_CRUD.
const OVERVIEW: ViewContext = {
  key: 'overview',
  label: { nl: 'Overzicht', en: 'Overview' },
  permission_roles: ['Members_Read', 'Members_CRUD'],
  columns: ['name', 'email', 'status', 'membership_type'],
  filterable_columns: ['name', 'status'],
  default_sort: { field: 'name', direction: 'asc' },
  page_size: 50,
};
const FINANCIAL: ViewContext = {
  key: 'financial',
  label: { nl: 'Financieel', en: 'Financial' },
  permission_roles: ['Members_CRUD'],
  columns: ['name', 'iban', 'payment_method'],
  filterable_columns: ['payment_method'],
  default_sort: { field: 'name', direction: 'asc' },
  page_size: 50,
};

const configWith = (view_contexts: ViewContext[]): FieldConfig => ({
  fields: FIELDS,
  dimensions: [
    { key: 'region', label: 'Regio', enabled: true, values: ['Noord', 'Zuid'] },
  ],
  view_contexts,
});

const waitForRows = async () => {
  await waitFor(() => {
    expect(screen.getByText('Jan')).toBeInTheDocument();
    expect(screen.getByText('Piet')).toBeInTheDocument();
  });
};

/** Locate the view-context dropdown (aria-label is the raw i18n key). */
const contextDropdown = () =>
  screen.getByLabelText('viewContext.label') as HTMLSelectElement;

describe('MembersPage — view contexts (task 3.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentRoles = [];
    mockListMembers.mockResolvedValue(mockMembers as never);
    mockGetMember.mockResolvedValue(mockMembers[0] as never);
    mockListMembershipTypes.mockResolvedValue([] as never);
  });

  describe('(a) dropdown lists only permitted contexts', () => {
    it('shows both contexts for a Members_CRUD user', async () => {
      currentRoles = ['Members_CRUD'];
      mockGetFieldConfig.mockResolvedValue(configWith([OVERVIEW, FINANCIAL]) as never);

      render(<MembersPage />);
      await waitForRows();

      const dropdown = contextDropdown();
      const options = within(dropdown).getAllByRole('option').map(o => o.textContent);
      expect(options).toEqual(['Overzicht', 'Financieel']);
    });

    it('omits the restricted context for a Members_Read-only user', async () => {
      currentRoles = ['Members_Read'];
      mockGetFieldConfig.mockResolvedValue(configWith([OVERVIEW, FINANCIAL]) as never);

      render(<MembersPage />);
      await waitForRows();

      // Only "overview" is permitted → a single permitted context, so the
      // dropdown is not rendered (nothing to pick between).
      expect(screen.queryByLabelText('viewContext.label')).not.toBeInTheDocument();

      // ...and the overview columns render (not the financial IBAN column).
      expect(screen.getByText('E-mail')).toBeInTheDocument();
      expect(screen.queryByText('IBAN')).not.toBeInTheDocument();
    });
  });

  describe('(b) selecting a context renders its columns via the toolkit', () => {
    it('switches the rendered column set when a different context is selected', async () => {
      currentRoles = ['Members_CRUD'];
      mockGetFieldConfig.mockResolvedValue(configWith([OVERVIEW, FINANCIAL]) as never);

      render(<MembersPage />);
      await waitForRows();

      // Default = first available context ("overview"): its columns are shown.
      expect(screen.getByText('E-mail')).toBeInTheDocument();
      expect(screen.getByText('Status')).toBeInTheDocument();
      expect(screen.queryByText('IBAN')).not.toBeInTheDocument();

      // Select "financial" → its columns render, overview-only ones drop out.
      fireEvent.change(contextDropdown(), { target: { value: 'financial' } });

      await waitFor(() => {
        expect(screen.getByText('IBAN')).toBeInTheDocument();
        expect(screen.getByText('Betaalwijze')).toBeInTheDocument();
        // The toolkit renders the resolved column VALUES too.
        expect(screen.getByText('NL00BANK0123456789')).toBeInTheDocument();
      });
      // `status`/`email` are not in the financial context.
      expect(screen.queryByText('E-mail')).not.toBeInTheDocument();
      expect(screen.queryByText('Status')).not.toBeInTheDocument();
    });

    it('renders a filter input only for the context filterable_columns', async () => {
      currentRoles = ['Members_CRUD'];
      mockGetFieldConfig.mockResolvedValue(configWith([FINANCIAL]) as never);

      render(<MembersPage />);
      await waitForRows();

      // financial.filterable_columns = ['payment_method'] → only that header has
      // a filter input; `name`/`iban` headers render without one.
      expect(screen.getByLabelText('Filter by Betaalwijze')).toBeInTheDocument();
      expect(screen.queryByLabelText('Filter by IBAN')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Filter by Naam')).not.toBeInTheDocument();
    });
  });

  describe('(c) unresolvable column keys are skipped (Property 7, R5.1a)', () => {
    it('omits the dangling key and still renders the resolvable columns without crashing', async () => {
      currentRoles = ['Members_CRUD'];
      const withDangling: ViewContext = {
        key: 'broken',
        label: { nl: 'Kapot', en: 'Broken' },
        columns: ['name', 'does_not_exist', 'iban'],
        filterable_columns: [],
        default_sort: null,
        page_size: null,
      };
      mockGetFieldConfig.mockResolvedValue(configWith([withDangling]) as never);

      render(<MembersPage />);
      await waitForRows();

      // Resolvable columns render; the dangling key is silently skipped.
      expect(screen.getByText('IBAN')).toBeInTheDocument();
      expect(screen.getByText('NL00BANK0123456789')).toBeInTheDocument();
      // No column header for the unresolvable key.
      expect(screen.queryByText('does_not_exist')).not.toBeInTheDocument();
    });
  });

  describe('(e) parameter-driven + calculated columns render (task 4.1, R5.1/R5.2)', () => {
    // A field set spanning fixed, parameter-driven (overlay), calculated
    // (read-only), a date-typed field, and a NOT-visible field.
    const RICH_FIELDS: FieldConfig['fields'] = [
      { key: 'display_name', label: 'Korte naam', origin: 'calculated', order: 1 },
      { key: 'years_member', label: 'Jaren lid', origin: 'calculated', order: 2 },
      { key: 'joined_date', label: 'Ingangsdatum', origin: 'fixed', type: 'date', order: 3 },
      { key: 'field_a', label: 'Veld A', origin: 'variable', order: 4 },
      { key: 'secret', label: 'Verborgen', origin: 'variable', visible: false, order: 5 },
    ];

    const RICH_MEMBERS: Member[] = [
      {
        member_id: 'm-1',
        name: 'Jan',
        display_name: 'Jan de Vries',
        years_member: 12,
        joined_date: '2013-06-01',
        field_a: 'Waarde-A',
        secret: 'zzz-hidden',
      },
      {
        member_id: 'm-2',
        name: 'Piet',
        display_name: 'Piet Bakker',
        years_member: 3,
        joined_date: '2022-02-15',
        field_a: 'Waarde-B',
        secret: 'yyy-hidden',
      },
    ];

    const richContext: ViewContext = {
      key: 'rich',
      label: { nl: 'Rijk', en: 'Rich' },
      // References all keys incl. the not-visible `secret` (which must be skipped).
      columns: ['display_name', 'years_member', 'joined_date', 'field_a', 'secret'],
      filterable_columns: [],
      default_sort: null,
      page_size: null,
    };

    beforeEach(() => {
      mockListMembers.mockResolvedValue(RICH_MEMBERS as never);
      mockGetMember.mockResolvedValue(RICH_MEMBERS[0] as never);
    });

    const waitForRichRows = async () => {
      await waitFor(() => {
        expect(screen.getByText('Jan de Vries')).toBeInTheDocument();
        expect(screen.getByText('Piet Bakker')).toBeInTheDocument();
      });
    };

    it('renders calculated (read-only) + parameter-driven columns and values in an explicit context', async () => {
      currentRoles = ['Members_CRUD'];
      mockGetFieldConfig.mockResolvedValue(
        ({ fields: RICH_FIELDS, view_contexts: [richContext] }) as never,
      );

      render(<MembersPage />);
      await waitForRichRows();

      // Calculated column headers + values render read-only, like any field.
      expect(screen.getByText('Korte naam')).toBeInTheDocument();
      expect(screen.getByText('Jaren lid')).toBeInTheDocument();
      expect(screen.getByText('12')).toBeInTheDocument();
      // Parameter-driven (overlay) column + value render.
      expect(screen.getByText('Veld A')).toBeInTheDocument();
      expect(screen.getByText('Waarde-A')).toBeInTheDocument();
    });

    it('formats a date-typed column value (not the raw ISO string)', async () => {
      currentRoles = ['Members_CRUD'];
      mockGetFieldConfig.mockResolvedValue(
        ({ fields: RICH_FIELDS, view_contexts: [richContext] }) as never,
      );

      render(<MembersPage />);
      await waitForRichRows();

      // The date column header renders; the value is localized (nl → 01-06-2013),
      // so the raw ISO string must NOT be present.
      expect(screen.getByText('Ingangsdatum')).toBeInTheDocument();
      expect(screen.queryByText('2013-06-01')).not.toBeInTheDocument();
      expect(screen.getByText('01-06-2013')).toBeInTheDocument();
    });

    it('skips a not-visible (visible:false) field even when the context names it (R5.1)', async () => {
      currentRoles = ['Members_CRUD'];
      mockGetFieldConfig.mockResolvedValue(
        ({ fields: RICH_FIELDS, view_contexts: [richContext] }) as never,
      );

      render(<MembersPage />);
      await waitForRichRows();

      // The hidden field has neither a header nor a value cell.
      expect(screen.queryByText('Verborgen')).not.toBeInTheDocument();
      expect(screen.queryByText('zzz-hidden')).not.toBeInTheDocument();
    });

    it('surfaces calculated columns in the default/full context too (R5.2)', async () => {
      currentRoles = [];
      // No authored contexts → synthesized default; full view reveals non-compact
      // fields, which includes the calculated + overlay columns.
      mockGetFieldConfig.mockResolvedValue(({ fields: RICH_FIELDS }) as never);

      render(<MembersPage />);
      // Default/compact view renders the fixed `name` column (not `display_name`).
      await waitFor(() => {
        expect(screen.getByText('Jan')).toBeInTheDocument();
        expect(screen.getByText('Piet')).toBeInTheDocument();
      });

      // Compact view hides the non-compact columns.
      expect(screen.queryByText('Korte naam')).not.toBeInTheDocument();

      fireEvent.click(screen.getByText('view.full'));
      await waitFor(() => {
        // Calculated + overlay columns appear as read-only columns; the hidden
        // field stays out even in full view.
        expect(screen.getByText('Korte naam')).toBeInTheDocument();
        expect(screen.getByText('Jaren lid')).toBeInTheDocument();
        expect(screen.getByText('Veld A')).toBeInTheDocument();
        expect(screen.queryByText('Verborgen')).not.toBeInTheDocument();
      });
    });
  });

  describe('(d) default/empty context shows all visible fields', () => {
    it('synthesizes a single default context (empty columns) → compact/full switch + fixed columns', async () => {
      currentRoles = [];
      // Module returns exactly one default context with EMPTY columns.
      mockGetFieldConfig.mockResolvedValue(
        configWith([{ key: '__default__', columns: [] }]) as never,
      );

      render(<MembersPage />);
      await waitForRows();

      // No dropdown (single default context) but the all-visible-fields behavior:
      // the compact/full switch is present and the fixed columns render.
      expect(screen.queryByLabelText('viewContext.label')).not.toBeInTheDocument();
      expect(screen.getByText('view.compact')).toBeInTheDocument();
      expect(screen.getByText('view.full')).toBeInTheDocument();

      // Fixed compact columns + region badge render (today's default behavior).
      // "Noord" now appears both as the read-only Badge <span> and as an option
      // in the scope enum-filter (task 4.2), so assert on the Badge <span>.
      expect(screen.getByText('jan@h-dcn.example')).toBeInTheDocument();
      expect(
        screen.getAllByText('Noord').some((el) => el.tagName.toLowerCase() === 'span'),
      ).toBe(true);

      // Full view reveals the overlay columns (iban/payment_method) by label.
      fireEvent.click(screen.getByText('view.full'));
      await waitFor(() => {
        expect(screen.getByText('IBAN')).toBeInTheDocument();
        expect(screen.getByText('Betaalwijze')).toBeInTheDocument();
      });
    });

    it('falls back to a default context when the field config has none at all', async () => {
      currentRoles = [];
      mockGetFieldConfig.mockResolvedValue({ fields: FIELDS } as never);

      render(<MembersPage />);
      await waitForRows();

      // No authored contexts → synthesized default; page renders normally.
      expect(screen.queryByLabelText('viewContext.label')).not.toBeInTheDocument();
      expect(screen.getByText('view.compact')).toBeInTheDocument();
      expect(screen.getByText('jan@h-dcn.example')).toBeInTheDocument();
    });
  });
});

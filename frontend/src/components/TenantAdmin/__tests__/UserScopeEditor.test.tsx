/**
 * UserScopeEditor Component - Unit Tests (s5d task 6.2)
 *
 * Covers:
 *  - the R4.6 gating helper (`holdsMembersCapabilityRole`),
 *  - the plain value filter seam (`plainFilterValues`),
 *  - per-dimension multi-selects of PLAIN values + an All toggle,
 *  - load of the current grant + reflect it in the selection,
 *  - Save issues `setUserScope` with the selected set (atomic overwrite),
 *  - the All toggle yields `["*"]`,
 *  - clearing all selections removes the grant (`{}`),
 *  - a 400 validation error is surfaced.
 *
 * The `tenantAdminApi` service module is mocked (matching the repo's
 * component-test pattern of mocking the service, not the fetch plumbing).
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor, fireEvent } from '../../../test-utils';
import {
  UserScopeEditor,
  holdsMembersCapabilityRole,
  plainFilterValues,
} from '../UserScopeEditor';
import * as tenantAdminApi from '../../../services/tenantAdminApi';
import type { ScopeDimensionOption, ScopeGrant } from '../../../types/members';

// Mock the service module — the component talks to these functions directly.
vi.mock('../../../services/tenantAdminApi');

// Keep translation keys as-is so assertions match the key strings.
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}));

const mockGetScopeDimensions = vi.mocked(tenantAdminApi.getScopeDimensions);
const mockGetUserScope = vi.mocked(tenantAdminApi.getUserScope);
const mockSetUserScope = vi.mocked(tenantAdminApi.setUserScope);

const regionDimension: ScopeDimensionOption = {
  key: 'region',
  label: { nl: 'Regio', en: 'Region' },
  values: ['Noord', 'Oost', 'Zuid', 'West'],
  field: 'region',
};

const ageDimension: ScopeDimensionOption = {
  key: 'age_group',
  label: { en: 'Age group' },
  values: ['U15', 'U17', 'Senior'],
};

function renderEditor(overrides?: Partial<{ username: string }>) {
  return render(
    <UserScopeEditor
      username={overrides?.username ?? 'user1'}
      t={(k: string) => k}
      lang="en"
    />,
  );
}

describe('holdsMembersCapabilityRole (R4.6 gating)', () => {
  test('true for a Members_* capability role', () => {
    expect(holdsMembersCapabilityRole(['Members_CRUD'])).toBe(true);
    expect(holdsMembersCapabilityRole(['Finance_Read', 'Members_Read'])).toBe(true);
    expect(holdsMembersCapabilityRole(['Members_Export'])).toBe(true);
  });

  test('false for non-Members roles, Tenant_Admin, and Regio_*', () => {
    expect(holdsMembersCapabilityRole(['Tenant_Admin'])).toBe(false);
    expect(holdsMembersCapabilityRole(['Finance_CRUD'])).toBe(false);
    expect(holdsMembersCapabilityRole(['Regio_Oost'])).toBe(false);
    expect(holdsMembersCapabilityRole([])).toBe(false);
    expect(holdsMembersCapabilityRole(undefined)).toBe(false);
  });
});

describe('plainFilterValues (picker seam for 6.3 fuzzy)', () => {
  test('empty query returns all values', () => {
    expect(plainFilterValues(['Noord', 'Oost'], '')).toEqual(['Noord', 'Oost']);
  });
  test('case-insensitive substring match', () => {
    expect(plainFilterValues(['Noord', 'Oost', 'Zuid'], 'oo')).toEqual(['Noord', 'Oost']);
  });
});

describe('UserScopeEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetScopeDimensions.mockResolvedValue([regionDimension]);
    mockGetUserScope.mockResolvedValue({});
    mockSetUserScope.mockImplementation(async (_u, _m, scopes: ScopeGrant) => scopes);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('renders per-dimension multi-select of PLAIN values + All toggle', async () => {
    renderEditor();

    await waitFor(() => {
      expect(screen.getByText('Region')).toBeInTheDocument();
    });

    // Plain values as checkboxes (never Regio_ prefixed).
    expect(screen.getByLabelText('Noord')).toBeInTheDocument();
    expect(screen.getByLabelText('Oost')).toBeInTheDocument();
    expect(screen.queryByText('Regio_Oost')).not.toBeInTheDocument();

    // Explicit All toggle (a switch).
    expect(screen.getByLabelText('userManagement.scope.all')).toBeInTheDocument();
  });

  test('renders an independent selector per dimension (R4.4)', async () => {
    mockGetScopeDimensions.mockResolvedValue([regionDimension, ageDimension]);
    renderEditor();

    await waitFor(() => {
      expect(screen.getByText('Region')).toBeInTheDocument();
      expect(screen.getByText('Age group')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('U15')).toBeInTheDocument();
    expect(screen.getByLabelText('Noord')).toBeInTheDocument();
  });

  test('reflects the loaded grant in the selection', async () => {
    mockGetUserScope.mockResolvedValue({ region: ['Oost'] });
    renderEditor();

    await waitFor(() => {
      expect(screen.getByLabelText('Oost')).toBeChecked();
    });
    expect(screen.getByLabelText('Noord')).not.toBeChecked();
  });

  test('selecting values + Save calls setUserScope with the selected set', async () => {
    renderEditor();

    await waitFor(() => expect(screen.getByLabelText('Oost')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Oost'));
    fireEvent.click(screen.getByLabelText('Zuid'));
    fireEvent.click(screen.getByRole('button', { name: 'userManagement.scope.save' }));

    await waitFor(() => {
      expect(mockSetUserScope).toHaveBeenCalledWith('user1', 'members', {
        region: ['Oost', 'Zuid'],
      });
    });
  });

  test('the All toggle yields ["*"] on save', async () => {
    renderEditor();

    await waitFor(() => expect(screen.getByLabelText('userManagement.scope.all')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('userManagement.scope.all'));
    fireEvent.click(screen.getByRole('button', { name: 'userManagement.scope.save' }));

    await waitFor(() => {
      expect(mockSetUserScope).toHaveBeenCalledWith('user1', 'members', {
        region: ['*'],
      });
    });
  });

  test('clearing all selections removes the grant (sends {})', async () => {
    mockGetUserScope.mockResolvedValue({ region: ['Oost'] });
    renderEditor();

    await waitFor(() => expect(screen.getByLabelText('Oost')).toBeChecked());

    // Deselect the only value, then save.
    fireEvent.click(screen.getByLabelText('Oost'));
    fireEvent.click(screen.getByRole('button', { name: 'userManagement.scope.save' }));

    await waitFor(() => {
      expect(mockSetUserScope).toHaveBeenCalledWith('user1', 'members', {});
    });
  });

  test('surfaces a 400 validation error from setUserScope', async () => {
    mockSetUserScope.mockRejectedValue(new Error('Unknown value "Bogus" for dimension "region"'));
    renderEditor();

    await waitFor(() => expect(screen.getByLabelText('Oost')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Oost'));
    fireEvent.click(screen.getByRole('button', { name: 'userManagement.scope.save' }));

    await waitFor(() => {
      expect(screen.getByText(/Unknown value "Bogus"/)).toBeInTheDocument();
    });
  });

  test('fuzzy typeahead: a diacritic/spacing variant filters to the canonical value, and selecting it PUTs the canonical value (R5.3/R5.4)', async () => {
    // A dimension whose canonical values carry accents + separators.
    mockGetScopeDimensions.mockResolvedValue([
      {
        key: 'province',
        label: { en: 'Province' },
        values: ['Fryslân', 'Noord-Holland', 'Zuid-Holland'],
        field: 'province',
      },
    ]);
    renderEditor();

    await waitFor(() => expect(screen.getByLabelText('Noord-Holland')).toBeInTheDocument());

    // Type a spacing/diacritic-tolerant variant of the canonical value.
    const search = screen.getByLabelText('userManagement.scope.filterValues');
    fireEvent.change(search, { target: { value: 'noord holl' } });

    // Fuzzy narrows the list to the single matching CANONICAL value.
    await waitFor(() => {
      expect(screen.getByLabelText('Noord-Holland')).toBeInTheDocument();
      expect(screen.queryByLabelText('Fryslân')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Zuid-Holland')).not.toBeInTheDocument();
    });

    // Selecting the filtered result + Save stores the CANONICAL value unchanged,
    // NOT the typed "noord holl" variant.
    fireEvent.click(screen.getByLabelText('Noord-Holland'));
    fireEvent.click(screen.getByRole('button', { name: 'userManagement.scope.save' }));

    await waitFor(() => {
      expect(mockSetUserScope).toHaveBeenCalledWith('user1', 'members', {
        province: ['Noord-Holland'],
      });
    });
  });

  test('shows a message when the tenant has no scope dimensions', async () => {
    mockGetScopeDimensions.mockResolvedValue([]);
    renderEditor();

    await waitFor(() => {
      expect(screen.getByText('userManagement.scope.noDimensions')).toBeInTheDocument();
    });
  });
});

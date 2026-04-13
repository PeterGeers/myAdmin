/**
 * TaxRateManagement Component - Unit Tests
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '../../../test-utils';
import TaxRateManagement from '../TaxRateManagement';

jest.mock('../../../services/taxRateService', () => ({
  getTaxRates: jest.fn(),
  createTaxRate: jest.fn(),
  updateTaxRate: jest.fn(),
  deleteTaxRate: jest.fn(),
}));

jest.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: jest.fn() }
  })
}));

const { getTaxRates } = require('../../../services/taxRateService');

const mockRates = {
  success: true, tenant: 'T1',
  tax_rates: [
    { id: 1, tax_type: 'btw', tax_code: 'high', rate: 21, ledger_account: '2020', effective_from: '2000-01-01', effective_to: '9999-12-31', source: 'system', description: 'BTW Hoog', calc_method: 'percentage' },
    { id: 2, tax_type: 'tourist_tax', tax_code: 'standard', rate: 6.9, ledger_account: null, effective_from: '2026-01-01', effective_to: '9999-12-31', source: 'tenant', description: 'Toeristenbelasting', calc_method: 'percentage' },
    { id: 3, tax_type: 'tourist_tax', tax_code: 'standard', rate: 6.02, ledger_account: null, effective_from: '2000-01-01', effective_to: '2025-12-31', source: 'tenant', description: 'Toeristenbelasting oud', calc_method: 'percentage' },
  ],
};

describe('TaxRateManagement', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getTaxRates.mockResolvedValue(mockRates);
  });

  describe('Rendering', () => {
    test('shows loading spinner initially', () => {
      getTaxRates.mockReturnValue(new Promise(() => {}));
      render(<TaxRateManagement tenant="T1" />);
      expect(document.querySelector('.chakra-spinner')).toBeInTheDocument();
    });

    test('renders tax rate table after loading', async () => {
      render(<TaxRateManagement tenant="T1" />);
      await waitFor(() => {
        expect(screen.getByText('BTW Hoog')).toBeInTheDocument();
        expect(screen.getByText('Toeristenbelasting')).toBeInTheDocument();
      });
    });

    test('shows source badges', async () => {
      render(<TaxRateManagement tenant="T1" />);
      await waitFor(() => {
        expect(screen.getAllByText('system').length).toBeGreaterThan(0);
        expect(screen.getAllByText('tenant').length).toBeGreaterThan(0);
      });
    });

    test('shows infinity symbol for open-ended rates', async () => {
      render(<TaxRateManagement tenant="T1" />);
      await waitFor(() => {
        expect(screen.getAllByText('∞').length).toBeGreaterThan(0);
      });
    });

    test('shows empty state when no rates', async () => {
      getTaxRates.mockResolvedValue({ success: true, tenant: 'T1', tax_rates: [] });
      render(<TaxRateManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('tenantAdmin.taxRates.noTaxRates')).toBeInTheDocument());
    });
  });

  describe('Row Click', () => {
    test('clicking tenant row opens edit modal', async () => {
      render(<TaxRateManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('Toeristenbelasting')).toBeInTheDocument());
      fireEvent.click(screen.getByText('Toeristenbelasting'));
      await waitFor(() => expect(screen.getByText(/tenantAdmin.taxRates.editTaxRate/)).toBeInTheDocument());
    });

    test('clicking system row does not open modal for non-sysadmin', async () => {
      render(<TaxRateManagement tenant="T1" isSysAdmin={false} />);
      await waitFor(() => expect(screen.getByText('BTW Hoog')).toBeInTheDocument());
      fireEvent.click(screen.getByText('BTW Hoog'));
      expect(screen.queryByText(/tenantAdmin.taxRates.editTaxRate/)).not.toBeInTheDocument();
    });

    test('clicking system row opens modal for sysadmin', async () => {
      render(<TaxRateManagement tenant="T1" isSysAdmin={true} />);
      await waitFor(() => expect(screen.getByText('BTW Hoog')).toBeInTheDocument());
      fireEvent.click(screen.getByText('BTW Hoog'));
      await waitFor(() => expect(screen.getByText(/tenantAdmin.taxRates.editTaxRate/)).toBeInTheDocument());
    });
  });

  describe('Add Tax Rate', () => {
    test('add button is visible', async () => {
      render(<TaxRateManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('tenantAdmin.taxRates.addTaxRate')).toBeInTheDocument());
    });
  });
});

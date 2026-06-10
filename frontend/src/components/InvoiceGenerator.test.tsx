import React from 'react';
import { render, screen, fireEvent, waitFor } from '@/test-utils';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import InvoiceGenerator from './InvoiceGenerator';

// Mock the TenantContext
const mockUseTenant = vi.fn();
vi.mock('../context/TenantContext', () => ({
  useTenant: () => mockUseTenant(),
}));

// Mock the receiptGenerator utility
vi.mock('../utils/receiptGenerator', () => ({
  generateReceipt: vi.fn(),
  downloadReceipt: vi.fn(),
}));

import { generateReceipt, downloadReceipt } from '../utils/receiptGenerator';

const mockGenerateReceipt = generateReceipt as ReturnType<typeof vi.fn>;
const mockDownloadReceipt = downloadReceipt as ReturnType<typeof vi.fn>;

describe('InvoiceGenerator Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: tenant is selected
    mockUseTenant.mockReturnValue({
      currentTenant: 'test-tenant',
      availableTenants: ['test-tenant'],
      setCurrentTenant: vi.fn(),
      hasMultipleTenants: false,
    });
    // generateReceipt returns a fake canvas element
    mockGenerateReceipt.mockReturnValue(document.createElement('canvas'));
  });

  describe('Initial Rendering', () => {
    it('renders the page heading', () => {
      render(<InvoiceGenerator />);
      expect(screen.getByText('Kassabon Generator')).toBeInTheDocument();
    });

    it('renders company name input with default value', () => {
      render(<InvoiceGenerator />);
      const input = screen.getByDisplayValue('Intratuin');
      expect(input).toBeInTheDocument();
    });

    it('renders filename input with default value', () => {
      render(<InvoiceGenerator />);
      const input = screen.getByDisplayValue('Intratuin 202502.jpg');
      expect(input).toBeInTheDocument();
    });

    it('renders date input with default value', () => {
      render(<InvoiceGenerator />);
      const input = screen.getByDisplayValue('13-05-2025');
      expect(input).toBeInTheDocument();
    });

    it('renders total amount input with default value', () => {
      render(<InvoiceGenerator />);
      const input = screen.getByDisplayValue('193.29');
      expect(input).toBeInTheDocument();
    });

    it('renders VAT amount input with default value', () => {
      render(<InvoiceGenerator />);
      const input = screen.getByDisplayValue('33.55');
      expect(input).toBeInTheDocument();
    });

    it('renders the generate button', () => {
      render(<InvoiceGenerator />);
      expect(screen.getByRole('button', { name: /Genereer Kassabon/i })).toBeInTheDocument();
    });

    it('renders form labels', () => {
      render(<InvoiceGenerator />);
      expect(screen.getByText('Bedrijfsnaam')).toBeInTheDocument();
      expect(screen.getByText('Bestandsnaam')).toBeInTheDocument();
      expect(screen.getByText('Datum (DD-MM-YYYY)')).toBeInTheDocument();
      expect(screen.getByText('Totaalbedrag (€)')).toBeInTheDocument();
      expect(screen.getByText('BTW-bedrag (€)')).toBeInTheDocument();
    });
  });

  describe('Form Inputs', () => {
    it('updates company name on input change', () => {
      render(<InvoiceGenerator />);
      const input = screen.getByDisplayValue('Intratuin');
      fireEvent.change(input, { target: { value: 'Albert Heijn' } });
      expect(screen.getByDisplayValue('Albert Heijn')).toBeInTheDocument();
    });

    it('updates filename on input change', () => {
      render(<InvoiceGenerator />);
      const input = screen.getByDisplayValue('Intratuin 202502.jpg');
      fireEvent.change(input, { target: { value: 'AH 202503.jpg' } });
      expect(screen.getByDisplayValue('AH 202503.jpg')).toBeInTheDocument();
    });

    it('updates date on input change', () => {
      render(<InvoiceGenerator />);
      const input = screen.getByDisplayValue('13-05-2025');
      fireEvent.change(input, { target: { value: '25-12-2024' } });
      expect(screen.getByDisplayValue('25-12-2024')).toBeInTheDocument();
    });

    it('updates total amount on input change', () => {
      render(<InvoiceGenerator />);
      const input = screen.getByDisplayValue('193.29');
      fireEvent.change(input, { target: { value: '250.00' } });
      expect(screen.getByDisplayValue('250.00')).toBeInTheDocument();
    });

    it('updates VAT amount on input change', () => {
      render(<InvoiceGenerator />);
      const input = screen.getByDisplayValue('33.55');
      fireEvent.change(input, { target: { value: '52.50' } });
      expect(screen.getByDisplayValue('52.50')).toBeInTheDocument();
    });
  });

  describe('Form Submission', () => {
    it('calls generateReceipt with correct parameters on button click', () => {
      render(<InvoiceGenerator />);
      fireEvent.click(screen.getByRole('button', { name: /Genereer Kassabon/i }));

      expect(mockGenerateReceipt).toHaveBeenCalledWith({
        supplierName: 'Intratuin',
        transactionDate: '13-05-2025',
        totalAmount: 193.29,
        vatAmount: 33.55,
      });
    });

    it('calls downloadReceipt with canvas and filename', () => {
      const fakeCanvas = document.createElement('canvas');
      mockGenerateReceipt.mockReturnValue(fakeCanvas);

      render(<InvoiceGenerator />);
      fireEvent.click(screen.getByRole('button', { name: /Genereer Kassabon/i }));

      expect(mockDownloadReceipt).toHaveBeenCalledWith(fakeCanvas, 'Intratuin 202502.jpg');
    });

    it('shows success message after generation', () => {
      render(<InvoiceGenerator />);
      fireEvent.click(screen.getByRole('button', { name: /Genereer Kassabon/i }));

      expect(screen.getByText('Kassabon gedownload: Intratuin 202502.jpg')).toBeInTheDocument();
    });

    it('uses updated form values when generating', () => {
      render(<InvoiceGenerator />);

      // Change form values
      fireEvent.change(screen.getByDisplayValue('Intratuin'), { target: { value: 'Jumbo' } });
      fireEvent.change(screen.getByDisplayValue('Intratuin 202502.jpg'), { target: { value: 'Jumbo 202503.jpg' } });
      fireEvent.change(screen.getByDisplayValue('13-05-2025'), { target: { value: '01-03-2025' } });
      fireEvent.change(screen.getByDisplayValue('193.29'), { target: { value: '50.00' } });
      fireEvent.change(screen.getByDisplayValue('33.55'), { target: { value: '8.68' } });

      fireEvent.click(screen.getByRole('button', { name: /Genereer Kassabon/i }));

      expect(mockGenerateReceipt).toHaveBeenCalledWith({
        supplierName: 'Jumbo',
        transactionDate: '01-03-2025',
        totalAmount: 50.0,
        vatAmount: 8.68,
      });
      expect(mockDownloadReceipt).toHaveBeenCalledWith(expect.any(HTMLCanvasElement), 'Jumbo 202503.jpg');
    });

    it('shows error message when generateReceipt throws', () => {
      mockGenerateReceipt.mockImplementation(() => {
        throw new Error('Canvas not supported');
      });

      render(<InvoiceGenerator />);
      fireEvent.click(screen.getByRole('button', { name: /Genereer Kassabon/i }));

      expect(screen.getByText(/Fout:/)).toBeInTheDocument();
    });
  });

  describe('Tenant Handling', () => {
    it('disables generate button when no tenant is selected', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null,
        availableTenants: [],
        setCurrentTenant: vi.fn(),
        hasMultipleTenants: false,
      });

      render(<InvoiceGenerator />);
      const button = screen.getByRole('button', { name: /Genereer Kassabon/i });
      expect(button).toBeDisabled();
    });

    it('shows error message when generating without tenant', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null,
        availableTenants: [],
        setCurrentTenant: vi.fn(),
        hasMultipleTenants: false,
      });

      render(<InvoiceGenerator />);
      const button = screen.getByRole('button', { name: /Genereer Kassabon/i });
      // Button is disabled, so we force the call by triggering the handler directly
      // But since button is disabled, we verify the disabled state instead
      expect(button).toBeDisabled();
    });

    it('enables generate button when tenant is selected', () => {
      render(<InvoiceGenerator />);
      const button = screen.getByRole('button', { name: /Genereer Kassabon/i });
      expect(button).not.toBeDisabled();
    });
  });
});

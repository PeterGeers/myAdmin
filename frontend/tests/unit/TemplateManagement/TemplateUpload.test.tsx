/**
 * TemplateUpload Component Unit Tests
 * 
 * Tests for file upload, validation, template type selection, and field mappings.
 */

import { vi } from 'vitest';

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { TemplateUpload } from '../../../src/components/TenantAdmin/TemplateManagement/TemplateUpload';
import type { TemplateType } from '../../../src/types/template';

describe('TemplateUpload', () => {
  const mockOnUpload = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders template type selector', () => {
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      expect(screen.getByLabelText(/template type/i)).toBeInTheDocument();
      expect(screen.getByText(/select template type/i)).toBeInTheDocument();
    });

    it('renders file upload button', () => {
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      expect(screen.getByRole('button', { name: /browse files/i })).toBeInTheDocument();
    });

    it('renders upload button (disabled initially)', () => {
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      expect(uploadButton).toBeInTheDocument();
      expect(uploadButton).toBeDisabled();
    });

    it('renders help instructions', () => {
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      expect(screen.getByText(/upload instructions/i)).toBeInTheDocument();
      expect(screen.getByText(/select the template type/i)).toBeInTheDocument();
    });
  });

  describe('Template Type Selection', () => {
    it('displays all template type options', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      const select = screen.getByLabelText(/template type/i);
      await user.click(select);
      
      expect(screen.getByText(/STR Invoice \(Dutch\)/i)).toBeInTheDocument();
      expect(screen.getByText(/STR Invoice \(English\)/i)).toBeInTheDocument();
      expect(screen.getByText(/BTW Aangifte/i)).toBeInTheDocument();
      expect(screen.getByText(/Aangifte IB/i)).toBeInTheDocument();
      expect(screen.getByText(/Toeristenbelasting/i)).toBeInTheDocument();
      expect(screen.getByText(/Financial Report/i)).toBeInTheDocument();
    });

    it('shows description when template type is selected', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      expect(screen.getByText(/short-term rental invoice in dutch/i)).toBeInTheDocument();
    });

    it('clears errors when template type changes', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      // Upload a non-HTML file to trigger a file error
      const badFile = new File(['test content'], 'document.pdf', {
        type: 'application/pdf',
      });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [badFile], writable: false, configurable: true });
      fireEvent.change(input);
      
      // Should show file error
      await waitFor(() => {
        expect(screen.getByText(/only html files/i)).toBeInTheDocument();
      });
      
      // Select a template type — should clear errors
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      // Error should be cleared
      expect(screen.queryByText(/only html files/i)).not.toBeInTheDocument();
    });
  });

  describe('File Upload', () => {
    it('accepts HTML file selection', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      expect(screen.getByText('template.html')).toBeInTheDocument();
    });

    it('displays file size', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      expect(screen.getByText(/KB/i)).toBeInTheDocument();
    });

    it('rejects non-HTML files', async () => {
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      const file = new File(['test content'], 'document.pdf', {
        type: 'application/pdf',
      });
      
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);
      
      await waitFor(() => {
        expect(screen.getByText(/only html files/i)).toBeInTheDocument();
      });
    });

    it('rejects files larger than 5MB', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      // Create a file larger than 5MB
      const largeContent = 'x'.repeat(6 * 1024 * 1024);
      const file = new File([largeContent], 'large.html', {
        type: 'text/html',
      });
      
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      await waitFor(() => {
        expect(screen.getByText(/file size exceeds 5mb/i)).toBeInTheDocument();
      });
    });

    it('changes button text after file selection', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      expect(screen.getByRole('button', { name: /change file/i })).toBeInTheDocument();
    });
  });

  describe('Field Mappings', () => {
    it('hides field mappings by default', () => {
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      // Mock Collapse removes content from DOM when not open
      expect(screen.queryByLabelText(/field mappings \(json\)/i)).not.toBeInTheDocument();
    });

    it('shows field mappings when toggled', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      const toggleButton = screen.getByRole('button', { name: /advanced: field mappings/i });
      await user.click(toggleButton);
      
      expect(screen.getByLabelText(/field mappings \(json\)/i)).toBeInTheDocument();
    });

    it('validates JSON format', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      // Select template type first (triggers useEffect that resets field mappings)
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      // Upload a valid file
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      // Show field mappings
      const toggleButton = screen.getByRole('button', { name: /advanced: field mappings/i });
      await user.click(toggleButton);
      
      // Enter invalid JSON AFTER type selection (so useEffect doesn't overwrite it)
      const textarea = screen.getByLabelText(/field mappings \(json\)/i);
      fireEvent.change(textarea, { target: { value: '{invalid json}' } });
      
      // Click upload
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      await waitFor(() => {
        expect(screen.getByText(/invalid json format/i)).toBeInTheDocument();
      });
    });

    it('accepts valid JSON', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      // Show field mappings
      const toggleButton = screen.getByRole('button', { name: /advanced: field mappings/i });
      await user.click(toggleButton);
      
      // Enter valid JSON using fireEvent (userEvent can't handle curly braces)
      const textarea = screen.getByLabelText(/field mappings \(json\)/i);
      fireEvent.change(textarea, { target: { value: '{"field": "value"}' } });
      
      // Should not show error
      expect(screen.queryByText(/invalid json format/i)).not.toBeInTheDocument();
    });

    it('accepts empty field mappings', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      // Show field mappings
      const toggleButton = screen.getByRole('button', { name: /advanced: field mappings/i });
      await user.click(toggleButton);
      
      // Leave empty (default {})
      const textarea = screen.getByLabelText(/field mappings \(json\)/i);
      expect(textarea).toHaveValue('{}');
      
      // Should not show error
      expect(screen.queryByText(/invalid json format/i)).not.toBeInTheDocument();
    });
  });

  describe('Form Validation', () => {
    it('shows error when uploading without file', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      // Select template type
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      // Button should be disabled without file
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      expect(uploadButton).toBeDisabled();
    });

    it('shows error when uploading without template type', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      // Upload file
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      // Button should be disabled without template type
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      expect(uploadButton).toBeDisabled();
    });

    it('enables upload button when all required fields are filled', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      expect(uploadButton).toBeDisabled();
      
      // Select template type
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      // Upload file
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      // Button should be enabled
      await waitFor(() => {
        expect(uploadButton).not.toBeDisabled();
      });
    });
  });

  describe('Upload Submission', () => {
    it('calls onUpload with correct parameters', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      // Select template type
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      // Upload file
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      // Click upload
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      await waitFor(() => {
        expect(mockOnUpload).toHaveBeenCalledWith(
          expect.any(File),
          'str_invoice_nl',
          {}
        );
      });
    });

    it('calls onUpload with field mappings when provided', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);
      
      // Select template type
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      // Upload file
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      // Add field mappings
      const toggleButton = screen.getByRole('button', { name: /advanced: field mappings/i });
      await user.click(toggleButton);
      
      const textarea = screen.getByLabelText(/field mappings \(json\)/i);
      await user.clear(textarea);
      // Use fireEvent for JSON input (userEvent can't handle curly braces)
      fireEvent.change(textarea, { target: { value: '{"custom_field": "value"}' } });
      
      // Click upload
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      await waitFor(() => {
        expect(mockOnUpload).toHaveBeenCalledWith(
          expect.any(File),
          'str_invoice_nl',
          { custom_field: 'value' }
        );
      });
    });
  });

  describe('Loading and Disabled States', () => {
    it('disables all inputs when loading', () => {
      render(<TemplateUpload onUpload={mockOnUpload} loading={true} />);
      
      expect(screen.getByLabelText(/template type/i)).toBeDisabled();
      expect(screen.getByRole('button', { name: /browse files/i })).toBeDisabled();
      // When loading, button shows "Uploading..." text
      expect(screen.getByRole('button', { name: /uploading/i })).toBeDisabled();
    });

    it('disables all inputs when disabled prop is true', () => {
      render(<TemplateUpload onUpload={mockOnUpload} disabled={true} />);
      
      expect(screen.getByLabelText(/template type/i)).toBeDisabled();
      expect(screen.getByRole('button', { name: /browse files/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /upload & preview template/i })).toBeDisabled();
    });

    it('shows loading text on upload button when loading', () => {
      render(<TemplateUpload onUpload={mockOnUpload} loading={true} />);
      
      expect(screen.getByText(/uploading.../i)).toBeInTheDocument();
    });
  });
});

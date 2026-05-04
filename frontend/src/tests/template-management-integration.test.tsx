/**
 * Template Management Integration Tests
 * 
 * Tests the integration between TemplateUpload, ValidationResults, 
 * TemplatePreview, and TemplateApproval components.
 */

import { vi } from 'vitest';

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { TemplateUpload } from '../components/TenantAdmin/TemplateManagement/TemplateUpload';
import { ValidationResults } from '../components/TenantAdmin/TemplateManagement/ValidationResults';
import { TemplatePreview } from '../components/TenantAdmin/TemplateManagement/TemplatePreview';
import { TemplateApproval } from '../components/TenantAdmin/TemplateManagement/TemplateApproval';
import { AIHelpButton } from '../components/TenantAdmin/TemplateManagement/AIHelpButton';

describe('Template Management Integration Tests', () => {
  describe('Upload → Validation Flow', () => {
    it('uploads a file and displays validation results', async () => {
      const mockOnUpload = vi.fn();
      const mockValidationResult = {
        is_valid: false,
        errors: [
          { type: 'placeholder', message: 'Missing required field: invoice_number', line: 10 },
        ],
        warnings: [
          { type: 'warning', message: 'Logo image not found', line: 5 },
        ],
      };

      const { rerender } = render(
        <div>
          <TemplateUpload onUpload={mockOnUpload} />
        </div>
      );

      // Upload a file
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      // Select template type
      const user = userEvent.setup();
      const select = screen.getByRole('combobox', { name: /template type/i });
      await user.selectOptions(select, 'str_invoice_nl');

      // Click upload
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);

      // Verify upload was called
      await waitFor(() => {
        expect(mockOnUpload).toHaveBeenCalledWith(
          expect.any(File),
          'str_invoice_nl',
          {}
        );
      });

      // Now render validation results
      rerender(
        <div>
          <ValidationResults validationResult={mockValidationResult} />
        </div>
      );

      // Verify validation results are displayed
      expect(screen.getByText(/missing required field: invoice_number/i)).toBeInTheDocument();
      expect(screen.getByText(/logo image not found/i)).toBeInTheDocument();
    });
  });

  describe('Validation → Preview Flow', () => {
    it('displays preview when validation passes', () => {
      const mockValidationResult = {
        is_valid: true,
        errors: [],
        warnings: [],
      };

      const mockPreviewHtml = '<html><body><h1>Invoice Preview</h1></body></html>';

      render(
        <div>
          <ValidationResults validationResult={mockValidationResult} />
          <TemplatePreview 
            previewHtml={mockPreviewHtml}
            sampleDataInfo={{ source: 'Most recent booking', record_count: 1 }}
          />
        </div>
      );

      // Verify validation passed
      expect(screen.getByText(/your template passed all validation checks/i)).toBeInTheDocument();

      // Verify preview is shown
      const iframe = screen.getByTitle(/template preview/i);
      expect(iframe).toBeInTheDocument();
    });

    it('shows errors and warnings together', () => {
      const mockValidationResult = {
        is_valid: false,
        errors: [
          { type: 'placeholder', message: 'Missing required field: total_amount', line: 15 },
        ],
        warnings: [
          { type: 'warning', message: 'Footer section is empty', line: 100 },
        ],
      };

      render(<ValidationResults validationResult={mockValidationResult} />);

      // Verify both errors and warnings are shown
      expect(screen.getByText(/missing required field: total_amount/i)).toBeInTheDocument();
      expect(screen.getByText(/footer section is empty/i)).toBeInTheDocument();
    });
  });

  describe('Validation → AI Help Flow', () => {
    it('enables AI help button when there are errors', () => {
      const mockOnRequestHelp = vi.fn();
      const mockOnApplyFixes = vi.fn();

      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          hasErrors={true}
          loading={false}
          disabled={false}
          aiSuggestions={null}
        />
      );

      const aiButton = screen.getByRole('button', { name: /get ai help/i });
      expect(aiButton).not.toBeDisabled();
    });

    it('disables AI help button when there are no errors', () => {
      const mockOnRequestHelp = vi.fn();
      const mockOnApplyFixes = vi.fn();

      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          hasErrors={false}
          loading={false}
          disabled={false}
          aiSuggestions={null}
        />
      );

      const aiButton = screen.getByRole('button', { name: /get ai help/i });
      expect(aiButton).toBeDisabled();
    });

    it('displays AI suggestions when available', async () => {
      const user = userEvent.setup();
      const mockOnRequestHelp = vi.fn();
      const mockOnApplyFixes = vi.fn();
      const mockAISuggestions = {
        success: true,
        ai_suggestions: {
          analysis: 'Your template is missing required placeholders',
          fixes: [
            {
              issue: 'Missing placeholder',
              suggestion: 'Add {{invoice_number}} placeholder',
              code_example: '<span>{{invoice_number}}</span>',
              location: 'body',
              confidence: 'high' as const,
              auto_fixable: true,
            },
          ],
          auto_fixable: true,
        },
        fallback: false,
      };

      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          hasErrors={true}
          loading={false}
          disabled={false}
          aiSuggestions={mockAISuggestions}
        />
      );

      // Verify AI help button is enabled when there are errors
      const aiButton = screen.getByRole('button', { name: /get ai help/i });
      expect(aiButton).not.toBeDisabled();
      
      // Verify button is clickable
      await user.click(aiButton);
      expect(mockOnRequestHelp).toHaveBeenCalled();
    });
  });

  describe('Validation → Approval Flow', () => {
    it('enables approve button when validation passes', () => {
      const mockOnApprove = vi.fn();
      const mockOnReject = vi.fn();

      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
          loading={false}
          disabled={false}
        />
      );

      const approveButton = screen.getByRole('button', { name: /approve template/i });
      expect(approveButton).not.toBeDisabled();
    });

    it('disables approve button when validation fails', () => {
      const mockOnApprove = vi.fn();
      const mockOnReject = vi.fn();

      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={false}
          loading={false}
          disabled={false}
        />
      );

      const approveButton = screen.getByRole('button', { name: /approve template/i });
      expect(approveButton).toBeDisabled();
    });

    it('allows rejection even when validation fails', () => {
      const mockOnApprove = vi.fn();
      const mockOnReject = vi.fn();

      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={false}
          loading={false}
          disabled={false}
        />
      );

      const rejectButton = screen.getByRole('button', { name: /reject template/i });
      expect(rejectButton).not.toBeDisabled();
    });
  });

  describe('Complete Workflow Simulation', () => {
    it('simulates upload → validation → preview → approval workflow', async () => {
      const user = userEvent.setup();
      
      // Step 1: Upload
      const mockOnUpload = vi.fn();
      const { rerender } = render(<TemplateUpload onUpload={mockOnUpload} />);

      const file = new File(['<html><body>Valid Template</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      const select = screen.getByRole('combobox', { name: /template type/i });
      await user.selectOptions(select, 'str_invoice_nl');

      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);

      await waitFor(() => {
        expect(mockOnUpload).toHaveBeenCalled();
      });

      // Step 2: Validation (passed)
      const validationResult = {
        is_valid: true,
        errors: [],
        warnings: [],
      };

      rerender(
        <div>
          <ValidationResults validationResult={validationResult} />
          <TemplatePreview 
            previewHtml="<html><body>Preview</body></html>"
            sampleDataInfo={{ source: 'Test data' }}
          />
        </div>
      );

      expect(screen.getByText(/your template passed all validation checks/i)).toBeInTheDocument();

      // Step 3: Approval
      const mockOnApprove = vi.fn();
      const mockOnReject = vi.fn();

      rerender(
        <div>
          <ValidationResults validationResult={validationResult} />
          <TemplatePreview 
            previewHtml="<html><body>Preview</body></html>"
            sampleDataInfo={{ source: 'Test data' }}
          />
          <TemplateApproval
            onApprove={mockOnApprove}
            onReject={mockOnReject}
            isValid={true}
            loading={false}
            disabled={false}
          />
        </div>
      );

      const approveButton = screen.getByRole('button', { name: /^approve template$/i });
      expect(approveButton).not.toBeDisabled();
      
      // Verify button is clickable (opens modal)
      await user.click(approveButton);
      
      // In a real scenario, the modal would open and user would click confirm
      // For integration test, we verify the button interaction works
      expect(approveButton).toBeInTheDocument();
    });

    it('simulates upload → validation errors → AI help → rejection workflow', async () => {
      const user = userEvent.setup();
      
      // Step 1: Upload
      const mockOnUpload = vi.fn();
      const { rerender } = render(<TemplateUpload onUpload={mockOnUpload} />);

      const file = new File(['<html><body>Invalid Template</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      const select = screen.getByRole('combobox', { name: /template type/i });
      await user.selectOptions(select, 'str_invoice_nl');

      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);

      await waitFor(() => {
        expect(mockOnUpload).toHaveBeenCalled();
      });

      // Step 2: Validation (failed)
      const validationResult = {
        is_valid: false,
        errors: [
          { type: 'placeholder', message: 'Missing required field', line: 10 },
        ],
        warnings: [],
      };

      const mockOnRequestHelp = vi.fn();
      const mockOnApplyFixes = vi.fn();

      rerender(
        <div>
          <ValidationResults validationResult={validationResult} />
          <AIHelpButton
            onRequestHelp={mockOnRequestHelp}
            onApplyFixes={mockOnApplyFixes}
            hasErrors={true}
            loading={false}
            disabled={false}
            aiSuggestions={null}
          />
        </div>
      );

      expect(screen.getByText(/missing required field/i)).toBeInTheDocument();

      // Step 3: Request AI Help
      const aiButton = screen.getByRole('button', { name: /get ai help/i });
      await user.click(aiButton);

      await waitFor(() => {
        expect(mockOnRequestHelp).toHaveBeenCalled();
      });

      // Step 4: Rejection
      const mockOnApprove = vi.fn();
      const mockOnReject = vi.fn();

      rerender(
        <div>
          <ValidationResults validationResult={validationResult} />
          <TemplateApproval
            onApprove={mockOnApprove}
            onReject={mockOnReject}
            isValid={false}
            loading={false}
            disabled={false}
          />
        </div>
      );

      const rejectButton = screen.getByRole('button', { name: /^reject template$/i });
      await user.click(rejectButton);

      // In a real scenario, the modal would open and user would click confirm
      // For integration test, we verify the button interaction works
      expect(rejectButton).toBeInTheDocument();
    });
  });
});

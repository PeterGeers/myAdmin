/**
 * TemplateManagement Component Unit Tests
 * 
 * Tests for main container component, state management, and workflow orchestration.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TemplateManagement } from '../TemplateManagement';
import * as templateApi from '../../../../services/templateApi';
import type { PreviewResponse, AIHelpResponse, ApprovalResponse, RejectionResponse } from '../../../../types/template';

// Use centralized Chakra UI mocks
jest.mock('@chakra-ui/react', () => require('../chakraMock').chakraMock);
jest.mock('@chakra-ui/icons', () => require('../chakraMock').iconsMock);

// Mock the template API
jest.mock('../../../../services/templateApi');

describe('TemplateManagement', () => {
  const mockPreviewTemplate = templateApi.previewTemplate as jest.MockedFunction<typeof templateApi.previewTemplate>;
  const mockApproveTemplate = templateApi.approveTemplate as jest.MockedFunction<typeof templateApi.approveTemplate>;
  const mockRejectTemplate = templateApi.rejectTemplate as jest.MockedFunction<typeof templateApi.rejectTemplate>;
  const mockGetAIHelp = templateApi.getAIHelp as jest.MockedFunction<typeof templateApi.getAIHelp>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Initial Rendering', () => {
    it('renders component title', () => {
      render(<TemplateManagement />);
      
      expect(screen.getByText(/template management/i)).toBeInTheDocument();
    });

    it('renders description', () => {
      render(<TemplateManagement />);
      
      expect(screen.getByText(/upload and customize report templates/i)).toBeInTheDocument();
    });

    it('shows upload step initially', () => {
      render(<TemplateManagement />);
      
      expect(screen.getByRole('button', { name: /browse files/i })).toBeInTheDocument();
      expect(screen.getByLabelText(/template type/i)).toBeInTheDocument();
    });

    it('renders step indicator', () => {
      render(<TemplateManagement />);
      
      expect(screen.getByRole('group', { name: /step 1: upload/i })).toBeInTheDocument();
      expect(screen.getByRole('group', { name: /step 2: preview and validate/i })).toBeInTheDocument();
      expect(screen.getByRole('group', { name: /step 3: approve/i })).toBeInTheDocument();
    });
  });

  describe('File Upload Flow', () => {
    const mockPreviewResponse: PreviewResponse = {
      success: true,
      preview_html: '<html><body><h1>Test Preview</h1></body></html>',
      validation: {
        is_valid: true,
        errors: [],
        warnings: [],
        checks_performed: ['html_syntax', 'placeholder_validation'],
      },
      sample_data_info: {
        source: 'database',
        record_count: 5,
      },
    };

    it('uploads file and shows preview', async () => {
      const user = userEvent.setup();
      mockPreviewTemplate.mockResolvedValue(mockPreviewResponse);
      
      render(<TemplateManagement />);
      
      // Select template type
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      // Upload file
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      // Click upload button
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      // Wait for preview to appear
      await waitFor(() => {
        expect(screen.getByText(/validation results/i)).toBeInTheDocument();
      });
      expect(screen.getByText(/template preview/i)).toBeInTheDocument();
    });

    it('shows success message for valid template', async () => {
      const user = userEvent.setup();
      mockPreviewTemplate.mockResolvedValue(mockPreviewResponse);
      
      render(<TemplateManagement />);
      
      // Upload template
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      await waitFor(() => {
        expect(screen.getByText(/template validated successfully/i)).toBeInTheDocument();
      });
    });

    it('shows error message for invalid template', async () => {
      const user = userEvent.setup();
      const invalidResponse: PreviewResponse = {
        success: true,
        preview_html: '<html><body>Test</body></html>',
        validation: {
          is_valid: false,
          errors: [
            { type: 'missing_placeholder', message: 'Missing required placeholder' },
          ],
          warnings: [],
        },
      };
      mockPreviewTemplate.mockResolvedValue(invalidResponse);
      
      render(<TemplateManagement />);
      
      // Upload template
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      await waitFor(() => {
        expect(screen.getByText(/template has 1 error\(s\)/i)).toBeInTheDocument();
      });
    });

    it('handles upload API error', async () => {
      const user = userEvent.setup();
      mockPreviewTemplate.mockRejectedValue(new Error('Network error'));
      
      render(<TemplateManagement />);
      
      // Upload template
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      await waitFor(() => {
        expect(screen.getByText(/network error/i)).toBeInTheDocument();
      });
    });

    it('validates file size before upload', async () => {
      const user = userEvent.setup();
      
      render(<TemplateManagement />);
      
      // Select template type
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      // Create large file (> 5MB)
      const largeContent = 'x'.repeat(6 * 1024 * 1024);
      const file = new File([largeContent], 'large.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      await waitFor(() => {
        expect(screen.getByText(/file size exceeds 5mb/i)).toBeInTheDocument();
      });
      
      // API should not be called
      expect(mockPreviewTemplate).not.toHaveBeenCalled();
    });
  });

  describe('Approval Flow', () => {
    const mockPreviewResponse: PreviewResponse = {
      success: true,
      preview_html: '<html><body>Test</body></html>',
      validation: {
        is_valid: true,
        errors: [],
        warnings: [],
      },
    };

    const mockApprovalResponse: ApprovalResponse = {
      success: true,
      template_id: 'template-123',
      file_id: 'file-456',
      message: 'Template approved successfully',
    };

    it('approves template successfully', async () => {
      const user = userEvent.setup();
      mockPreviewTemplate.mockResolvedValue(mockPreviewResponse);
      mockApproveTemplate.mockResolvedValue(mockApprovalResponse);
      
      render(<TemplateManagement />);
      
      // Upload template
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      // Wait for preview
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /approve template/i })).toBeInTheDocument();
      });
      
      // Approve template
      const approveButton = screen.getByRole('button', { name: /approve template/i });
      await user.click(approveButton);
      
      // Confirm approval
      const confirmButton = screen.getByRole('button', { name: /confirm approval/i });
      await user.click(confirmButton);
      
      await waitFor(() => {
        expect(screen.getByText(/template approved successfully/i)).toBeInTheDocument();
      });
    });

    it('prevents approval of invalid template', async () => {
      const user = userEvent.setup();
      const invalidResponse: PreviewResponse = {
        success: true,
        preview_html: '<html><body>Test</body></html>',
        validation: {
          is_valid: false,
          errors: [{ type: 'error', message: 'Error' }],
          warnings: [],
        },
      };
      mockPreviewTemplate.mockResolvedValue(invalidResponse);
      
      render(<TemplateManagement />);
      
      // Upload template
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      // Wait for preview
      await waitFor(() => {
        const approveButton = screen.getByRole('button', { name: /approve template/i });
        expect(approveButton).toBeDisabled();
      });
    });

    it('handles approval API error', async () => {
      const user = userEvent.setup();
      mockPreviewTemplate.mockResolvedValue(mockPreviewResponse);
      mockApproveTemplate.mockRejectedValue(new Error('Approval failed'));
      
      render(<TemplateManagement />);
      
      // Upload and approve
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /approve template/i })).toBeInTheDocument();
      });
      
      const approveButton = screen.getByRole('button', { name: /approve template/i });
      await user.click(approveButton);
      
      const confirmButton = screen.getByRole('button', { name: /confirm approval/i });
      await user.click(confirmButton);
      
      await waitFor(() => {
        expect(screen.getByText(/approval failed/i)).toBeInTheDocument();
      });
    });
  });

  describe('Rejection Flow', () => {
    const mockPreviewResponse: PreviewResponse = {
      success: true,
      preview_html: '<html><body>Test</body></html>',
      validation: {
        is_valid: true,
        errors: [],
        warnings: [],
      },
    };

    const mockRejectionResponse: RejectionResponse = {
      success: true,
      message: 'Template rejected',
    };

    it('rejects template successfully', async () => {
      const user = userEvent.setup();
      mockPreviewTemplate.mockResolvedValue(mockPreviewResponse);
      mockRejectTemplate.mockResolvedValue(mockRejectionResponse);
      
      render(<TemplateManagement />);
      
      // Upload template
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      // Wait for preview
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /reject template/i })).toBeInTheDocument();
      });
      
      // Reject template
      const rejectButton = screen.getByRole('button', { name: /reject template/i });
      await user.click(rejectButton);
      
      // Confirm rejection
      const confirmButton = screen.getByRole('button', { name: /confirm rejection/i });
      await user.click(confirmButton);
      
      await waitFor(() => {
        expect(screen.getByText(/template rejected/i)).toBeInTheDocument();
      });
    });
  });

  describe('AI Help Flow', () => {
    const mockPreviewResponse: PreviewResponse = {
      success: true,
      preview_html: '<html><body>Test</body></html>',
      validation: {
        is_valid: false,
        errors: [
          { type: 'missing_placeholder', message: 'Missing placeholder' },
        ],
        warnings: [],
      },
    };

    const mockAIResponse: AIHelpResponse = {
      success: true,
      ai_suggestions: {
        analysis: 'Your template needs fixes',
        fixes: [
          {
            issue: 'Missing placeholder',
            suggestion: 'Add placeholder',
            code_example: '{{placeholder}}',
            location: 'Line 10',
            confidence: 'high',
            auto_fixable: true,
          },
        ],
        auto_fixable: true,
      },
    };

    it('requests AI help successfully', async () => {
      const user = userEvent.setup();
      mockPreviewTemplate.mockResolvedValue(mockPreviewResponse);
      mockGetAIHelp.mockResolvedValue(mockAIResponse);
      
      render(<TemplateManagement />);
      
      // Upload template with errors
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      // Wait for preview and click AI help
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /get ai help/i })).toBeInTheDocument();
      });
      
      const aiButton = screen.getByRole('button', { name: /get ai help/i });
      await user.click(aiButton);
      
      await waitFor(() => {
        expect(mockGetAIHelp).toHaveBeenCalled();
      });
    });
  });

  describe('Start Over', () => {
    it('resets to initial state', async () => {
      const user = userEvent.setup();
      const mockPreviewResponse: PreviewResponse = {
        success: true,
        preview_html: '<html><body>Test</body></html>',
        validation: {
          is_valid: true,
          errors: [],
          warnings: [],
        },
      };
      mockPreviewTemplate.mockResolvedValue(mockPreviewResponse);
      
      render(<TemplateManagement />);
      
      // Upload template
      const select = screen.getByLabelText(/template type/i);
      await user.selectOptions(select, 'str_invoice_nl');
      
      const file = new File(['<html><body>Test</body></html>'], 'template.html', {
        type: 'text/html',
      });
      const input = screen.getByLabelText(/upload html template file/i);
      await user.upload(input, file);
      
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);
      
      // Wait for preview
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start over/i })).toBeInTheDocument();
      });
      
      // Click start over
      const startOverButton = screen.getByRole('button', { name: /start over/i });
      await user.click(startOverButton);
      
      // Should be back to upload step
      expect(screen.getByRole('button', { name: /browse files/i })).toBeInTheDocument();
    });
  });

  describe('Step Indicator', () => {
    it('highlights current step', () => {
      render(<TemplateManagement />);
      
      // Upload step should be active
      const uploadStep = screen.getByRole('group', { name: /step 1: upload/i });
      expect(uploadStep).toHaveAttribute('aria-current', 'step');
    });
  });
});







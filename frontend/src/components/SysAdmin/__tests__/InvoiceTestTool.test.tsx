/**
 * Unit Tests — Invoice Processing Test Tool (Frontend Components)
 *
 * Tests rendering, loading states, error display, comparison views,
 * and empty states for the InvoiceTestTool components.
 *
 * Requirements: 6.5, 6.6, 6.8, 3.4, 3.5
 */

import React from 'react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@/test-utils';
import { InvoiceTestTool } from '../InvoiceTestTool';
import { PipelineResultsPanel } from '../PipelineResultsPanel';
import { CustomPromptEditor } from '../CustomPromptEditor';
import { VendorHistoryPanel } from '../VendorHistoryPanel';
import type {
  ProcessResponse,
  ExtractionResult,
  RerunPromptResponse,
} from '../../../types/invoiceTestTool';

// ─── Mock API service ────────────────────────────────────────────────────────

vi.mock('../../../services/invoiceTestToolService', () => ({
  processFile: vi.fn(),
  rerunPrompt: vi.fn(),
  getVendorHistory: vi.fn(),
}));

import { processFile, rerunPrompt, getVendorHistory } from '../../../services/invoiceTestToolService';

// ─── Mock Data Factories ─────────────────────────────────────────────────────

function createMockExtractionResult(overrides?: Partial<ExtractionResult>): ExtractionResult {
  return {
    date: '2024-01-15',
    total_amount: 150.0,
    vat_amount: 31.5,
    description: 'Invoice #12345',
    vendor: 'TestVendor',
    ...overrides,
  };
}

function createMockProcessResponse(overrides?: Partial<ProcessResponse>): ProcessResponse {
  return {
    success: true,
    pipeline_result: {
      raw_text: 'Sample extracted text from invoice file.',
      raw_text_truncated: false,
      extraction_result: createMockExtractionResult(),
      formatted_transactions: [
        { date: '2024-01-15', amount: 150.0, description: 'Invoice #12345', debet: '1400', credit: '4000' },
      ],
      prepared_transactions: [
        {
          ID: '1', TransactionNumber: 'TX001', TransactionDate: '2024-01-15',
          TransactionDescription: 'Invoice #12345', TransactionAmount: 150.0,
          Debet: '1400', Credit: '4000', ReferenceNumber: 'REF001',
          Ref1: null, Ref2: null, Ref3: '', Ref4: '', Administration: 'TestAdmin',
        },
      ],
      parser_used: 'ai',
      folder_name: 'TestVendor',
    },
    performance: {
      total_duration_ms: 3450,
      ai_duration_ms: 2800,
      ai_model: 'deepseek/deepseek-chat',
      ai_tokens: { prompt_tokens: 420, completion_tokens: 85, total_tokens: 505 },
    },
    ai_usage_preview: {
      administration: 'TestAdmin',
      feature: 'invoice_extraction_TestVendor',
      tokens_used: 505,
      cost_estimate: '0.000346',
      cost_breakdown: {
        model: 'deepseek/deepseek-chat',
        rate_per_million: 0.685,
        total_tokens: 505,
        formula: '(505 / 1000000) * 0.685',
      },
    },
    execution_log: 'Starting file processing...\nAI extraction complete.',
    errors: [],
    ...overrides,
  };
}

function createMockRerunResponse(overrides?: Partial<RerunPromptResponse>): RerunPromptResponse {
  return {
    success: true,
    extraction_result: createMockExtractionResult({ description: 'Re-run result' }),
    performance: {
      ai_duration_ms: 2100,
      ai_model: 'deepseek/deepseek-chat',
      ai_tokens: { prompt_tokens: 380, completion_tokens: 90, total_tokens: 470 },
    },
    ai_usage_preview: null,
    errors: [],
    ...overrides,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// InvoiceTestTool Component Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('InvoiceTestTool', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Upload form rendering', () => {
    it('renders the upload form with all fields', () => {
      render(<InvoiceTestTool />);

      expect(screen.getByText('Invoice Processing Test Tool')).toBeInTheDocument();
      expect(screen.getByText('Choose File')).toBeInTheDocument();
      expect(screen.getByText('Process File')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('TestVendor')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Optional tenant identifier')).toBeInTheDocument();
    });

    it('submit button is disabled when no file selected', () => {
      render(<InvoiceTestTool />);

      const submitBtn = screen.getByText('Process File');
      expect(submitBtn).toBeDisabled();
    });
  });

  describe('Validation error display', () => {
    it('shows error for invalid vendor name', () => {
      render(<InvoiceTestTool />);

      const vendorInput = screen.getByPlaceholderText('TestVendor');
      fireEvent.change(vendorInput, { target: { value: 'invalid vendor!' } });

      expect(screen.getByText(/letters, numbers, hyphens, underscores only/i)).toBeInTheDocument();
    });

    it('shows error for unsupported file type', () => {
      render(<InvoiceTestTool />);

      const fileInput = screen.getByLabelText('Invoice file upload');
      const invalidFile = new File(['content'], 'test.exe', { type: 'application/octet-stream' });
      fireEvent.change(fileInput, { target: { files: [invalidFile] } });

      expect(screen.getByText(/unsupported file type/i)).toBeInTheDocument();
    });

    it('shows error for oversized file', () => {
      render(<InvoiceTestTool />);

      const fileInput = screen.getByLabelText('Invoice file upload');
      // Create a file larger than 20 MB
      const bigFile = new File(['x'], 'big.pdf', { type: 'application/pdf' });
      Object.defineProperty(bigFile, 'size', { value: 25 * 1024 * 1024 });
      fireEvent.change(fileInput, { target: { files: [bigFile] } });

      expect(screen.getByText(/exceeds the 20 MB limit/i)).toBeInTheDocument();
    });
  });

  describe('Loading state and disabled submit during processing', () => {
    it('shows loading state and disables submit during processing', async () => {
      // Mock processFile to never resolve (simulates loading)
      vi.mocked(processFile).mockReturnValue(new Promise(() => {}));

      render(<InvoiceTestTool />);

      // Select a valid file
      const fileInput = screen.getByLabelText('Invoice file upload');
      const validFile = new File(['pdf content'], 'invoice.pdf', { type: 'application/pdf' });
      fireEvent.change(fileInput, { target: { files: [validFile] } });

      // Click submit
      const submitBtn = screen.getByText('Process File');
      fireEvent.click(submitBtn);

      // Should show loading text
      await waitFor(() => {
        expect(screen.getByText('Processing...')).toBeInTheDocument();
      });

      // Button should be disabled during loading
      expect(screen.getByText('Processing...')).toBeDisabled();
    });
  });

  describe('Error display on submit failure', () => {
    it('displays API error message on submit failure', async () => {
      vi.mocked(processFile).mockRejectedValue(new Error('Server unavailable'));

      render(<InvoiceTestTool />);

      // Select a valid file
      const fileInput = screen.getByLabelText('Invoice file upload');
      const validFile = new File(['pdf content'], 'invoice.pdf', { type: 'application/pdf' });
      fireEvent.change(fileInput, { target: { files: [validFile] } });

      // Click submit
      const submitBtn = screen.getByText('Process File');
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByText('Server unavailable')).toBeInTheDocument();
      });
    });
  });

  describe('Results display after successful processing', () => {
    it('renders PipelineResultsPanel after successful processing', async () => {
      vi.mocked(processFile).mockResolvedValue(createMockProcessResponse());

      render(<InvoiceTestTool />);

      // Select a valid file
      const fileInput = screen.getByLabelText('Invoice file upload');
      const validFile = new File(['pdf content'], 'invoice.pdf', { type: 'application/pdf' });
      fireEvent.change(fileInput, { target: { files: [validFile] } });

      // Click submit
      const submitBtn = screen.getByText('Process File');
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByText('Pipeline Results')).toBeInTheDocument();
      });
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// PipelineResultsPanel Component Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('PipelineResultsPanel', () => {
  describe('Rendering with mock data', () => {
    it('renders all pipeline sections', () => {
      const response = createMockProcessResponse();
      render(<PipelineResultsPanel response={response} />);

      expect(screen.getByText('Pipeline Results')).toBeInTheDocument();
      expect(screen.getByText('Pipeline Overview')).toBeInTheDocument();
      expect(screen.getByText('Raw Extracted Text')).toBeInTheDocument();
      expect(screen.getByText('Extraction Result')).toBeInTheDocument();
      expect(screen.getByText('Formatted Transactions')).toBeInTheDocument();
      expect(screen.getByText('Prepared Transactions')).toBeInTheDocument();
      expect(screen.getByText('Performance Metrics')).toBeInTheDocument();
    });

    it('displays parser used and vendor name', () => {
      const response = createMockProcessResponse();
      render(<PipelineResultsPanel response={response} />);

      expect(screen.getByText('ai')).toBeInTheDocument();
      // Vendor name appears in both Pipeline Overview and Extraction Result sections
      const vendorElements = screen.getAllByText('TestVendor');
      expect(vendorElements.length).toBeGreaterThanOrEqual(1);
    });

    it('displays extraction result field values', () => {
      const response = createMockProcessResponse();
      render(<PipelineResultsPanel response={response} />);

      // Date, amount, description appear in multiple tables (extraction, formatted, prepared)
      // Use getAllByText to verify they exist
      const dateElements = screen.getAllByText('2024-01-15');
      expect(dateElements.length).toBeGreaterThanOrEqual(1);
      const amountElements = screen.getAllByText('150.00');
      expect(amountElements.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('31.50')).toBeInTheDocument();
    });

    it('displays performance metrics', () => {
      const response = createMockProcessResponse();
      render(<PipelineResultsPanel response={response} />);

      expect(screen.getByText('3450 ms')).toBeInTheDocument();
      expect(screen.getByText('2800 ms')).toBeInTheDocument();
      // Model name appears in both Performance Metrics and AI Usage Preview
      const modelElements = screen.getAllByText('deepseek/deepseek-chat');
      expect(modelElements.length).toBeGreaterThanOrEqual(1);
    });

    it('displays formatted transaction data', () => {
      const response = createMockProcessResponse();
      render(<PipelineResultsPanel response={response} />);

      expect(screen.getByText('1 transaction')).toBeInTheDocument();
    });

    it('displays prepared transaction data', () => {
      const response = createMockProcessResponse();
      render(<PipelineResultsPanel response={response} />);

      expect(screen.getByText('1 prepared transaction')).toBeInTheDocument();
    });
  });

  describe('Empty states (Requirements 3.4, 3.5)', () => {
    it('shows empty state for formatted transactions when list is empty', () => {
      const response = createMockProcessResponse({
        pipeline_result: {
          ...createMockProcessResponse().pipeline_result,
          formatted_transactions: [],
        },
      });
      render(<PipelineResultsPanel response={response} />);

      expect(screen.getByText('No formatted transactions produced')).toBeInTheDocument();
    });

    it('shows empty state for prepared transactions when list is empty', () => {
      const response = createMockProcessResponse({
        pipeline_result: {
          ...createMockProcessResponse().pipeline_result,
          prepared_transactions: [],
        },
      });
      render(<PipelineResultsPanel response={response} />);

      expect(screen.getByText('No prepared transactions produced')).toBeInTheDocument();
    });

    it('shows empty state for extraction result when null', () => {
      const response = createMockProcessResponse({
        pipeline_result: {
          ...createMockProcessResponse().pipeline_result,
          extraction_result: null,
        },
      });
      render(<PipelineResultsPanel response={response} />);

      expect(screen.getByText('No extraction result available')).toBeInTheDocument();
    });
  });

  describe('Error display', () => {
    it('renders pipeline errors with stage and message', () => {
      const response = createMockProcessResponse({
        errors: [
          {
            stage: 'ai_extraction',
            error_type: 'AllModelsExhausted',
            message: 'All 6 AI models failed to extract invoice data',
          },
        ],
      });
      render(<PipelineResultsPanel response={response} />);

      expect(screen.getByText('Errors')).toBeInTheDocument();
      expect(screen.getByText('ai_extraction')).toBeInTheDocument();
      expect(screen.getByText('AllModelsExhausted')).toBeInTheDocument();
      expect(screen.getByText('All 6 AI models failed to extract invoice data')).toBeInTheDocument();
    });
  });

  describe('Raw text truncation indicator', () => {
    it('shows truncation badge when text was truncated', () => {
      const response = createMockProcessResponse({
        pipeline_result: {
          ...createMockProcessResponse().pipeline_result,
          raw_text: 'x'.repeat(500),
          raw_text_truncated: true,
        },
      });
      render(<PipelineResultsPanel response={response} />);

      expect(screen.getByText(/truncated/i)).toBeInTheDocument();
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// CustomPromptEditor Component Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('CustomPromptEditor', () => {
  const defaultProps = {
    originalPrompt: 'Extract invoice data: date, amount, vat, description, vendor.',
    originalResult: createMockExtractionResult(),
    textContent: 'Sample raw text from invoice.',
    vendorHint: 'TestVendor',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders original prompt read-only and editable textarea', () => {
      render(<CustomPromptEditor {...defaultProps} />);

      expect(screen.getByText('Custom Prompt Editor')).toBeInTheDocument();
      expect(screen.getByText('Original Prompt (read-only)')).toBeInTheDocument();
      expect(screen.getByText('Custom Prompt')).toBeInTheDocument();
      expect(screen.getByText('Re-run with Custom Prompt')).toBeInTheDocument();
    });

    it('pre-populates editable textarea with original prompt', () => {
      render(<CustomPromptEditor {...defaultProps} />);

      const textareas = screen.getAllByDisplayValue(defaultProps.originalPrompt);
      expect(textareas.length).toBeGreaterThan(0);
    });
  });

  describe('Loading state (Requirement 6.5)', () => {
    it('shows loading state and disables submit during re-run', async () => {
      vi.mocked(rerunPrompt).mockReturnValue(new Promise(() => {}));

      render(<CustomPromptEditor {...defaultProps} />);

      const submitBtn = screen.getByText('Re-run with Custom Prompt');
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByText('Re-running extraction...')).toBeInTheDocument();
      });

      expect(screen.getByText('Re-running extraction...')).toBeDisabled();
    });
  });

  describe('Comparison view after re-run (Requirement 6.6)', () => {
    it('displays original and re-run results side by side after successful re-run', async () => {
      vi.mocked(rerunPrompt).mockResolvedValue(createMockRerunResponse());

      render(<CustomPromptEditor {...defaultProps} />);

      const submitBtn = screen.getByText('Re-run with Custom Prompt');
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByText('Original Result')).toBeInTheDocument();
        expect(screen.getByText('Re-run Result')).toBeInTheDocument();
      });

      // Should show comparison label
      expect(screen.getByText('Extraction Result Comparison')).toBeInTheDocument();
    });

    it('displays re-run timing and token badges', async () => {
      vi.mocked(rerunPrompt).mockResolvedValue(createMockRerunResponse());

      render(<CustomPromptEditor {...defaultProps} />);

      const submitBtn = screen.getByText('Re-run with Custom Prompt');
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByText('Duration: 2100 ms')).toBeInTheDocument();
        expect(screen.getByText('Model: deepseek/deepseek-chat')).toBeInTheDocument();
        expect(screen.getByText('Prompt: 380')).toBeInTheDocument();
        expect(screen.getByText('Completion: 90')).toBeInTheDocument();
        expect(screen.getByText('Total: 470')).toBeInTheDocument();
      });
    });
  });

  describe('Error on failure (Requirement 6.8)', () => {
    it('displays error message when re-run fails', async () => {
      vi.mocked(rerunPrompt).mockRejectedValue(new Error('AI model timeout'));

      render(<CustomPromptEditor {...defaultProps} />);

      const submitBtn = screen.getByText('Re-run with Custom Prompt');
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByText(/re-run failed: AI model timeout/i)).toBeInTheDocument();
      });
    });

    it('preserves original result on failure', async () => {
      vi.mocked(rerunPrompt).mockRejectedValue(new Error('Network error'));

      render(<CustomPromptEditor {...defaultProps} />);

      const submitBtn = screen.getByText('Re-run with Custom Prompt');
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByText(/re-run failed/i)).toBeInTheDocument();
      });

      // Original prompt should still be in the textarea
      const textareas = screen.getAllByDisplayValue(defaultProps.originalPrompt);
      expect(textareas.length).toBeGreaterThan(0);
    });
  });

  describe('Prompt validation', () => {
    it('disables submit for empty prompt', () => {
      render(<CustomPromptEditor {...defaultProps} />);

      // Clear the textarea
      const textarea = screen.getAllByDisplayValue(defaultProps.originalPrompt)[1]; // editable one
      fireEvent.change(textarea, { target: { value: '' } });

      const submitBtn = screen.getByText('Re-run with Custom Prompt');
      expect(submitBtn).toBeDisabled();
    });

    it('shows validation error for prompt exceeding 10,000 chars', () => {
      render(<CustomPromptEditor {...defaultProps} />);

      const textarea = screen.getAllByDisplayValue(defaultProps.originalPrompt)[1];
      fireEvent.change(textarea, { target: { value: 'x'.repeat(10_001) } });

      expect(screen.getByText(/exceeds maximum length/i)).toBeInTheDocument();
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// VendorHistoryPanel Component Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('VendorHistoryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders the vendor history panel with search form', () => {
      render(<VendorHistoryPanel />);

      expect(screen.getByText('Vendor Transaction History')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Enter vendor name to look up history')).toBeInTheDocument();
      expect(screen.getByText('Look Up')).toBeInTheDocument();
    });

    it('pre-fills vendor name when provided', () => {
      render(<VendorHistoryPanel vendorName="MyVendor" />);

      const input = screen.getByDisplayValue('MyVendor');
      expect(input).toBeInTheDocument();
    });
  });

  describe('Empty state', () => {
    it('displays message when no transactions found for vendor', async () => {
      vi.mocked(getVendorHistory).mockResolvedValue({
        success: true,
        vendor_name: 'SomeVendor',
        transactions: [],
        count: 0,
      });

      render(<VendorHistoryPanel vendorName="SomeVendor" />);

      const lookUpBtn = screen.getByText('Look Up');
      fireEvent.click(lookUpBtn);

      await waitFor(() => {
        expect(screen.getByText(/no transaction history found/i)).toBeInTheDocument();
      });
    });
  });

  describe('Rendering with transactions', () => {
    it('displays transaction table with date, amount, and description', async () => {
      vi.mocked(getVendorHistory).mockResolvedValue({
        success: true,
        vendor_name: 'TestVendor',
        transactions: [
          { date: '2024-01-10', amount: 125.5, description: 'Invoice #12300' },
          { date: '2024-01-05', amount: 80.0, description: 'Invoice #12250' },
        ],
        count: 2,
      });

      render(<VendorHistoryPanel vendorName="TestVendor" />);

      const lookUpBtn = screen.getByText('Look Up');
      fireEvent.click(lookUpBtn);

      await waitFor(() => {
        expect(screen.getByText('2024-01-10')).toBeInTheDocument();
      });

      expect(screen.getByText('€ 125.50')).toBeInTheDocument();
      expect(screen.getByText('Invoice #12300')).toBeInTheDocument();
      expect(screen.getByText('2024-01-05')).toBeInTheDocument();
      expect(screen.getByText('€ 80.00')).toBeInTheDocument();
      expect(screen.getByText('Invoice #12250')).toBeInTheDocument();
    });
  });

  describe('Loading state', () => {
    it('disables input and button during loading', async () => {
      vi.mocked(getVendorHistory).mockReturnValue(new Promise(() => {}));

      render(<VendorHistoryPanel vendorName="TestVendor" />);

      const lookUpBtn = screen.getByText('Look Up');
      fireEvent.click(lookUpBtn);

      await waitFor(() => {
        expect(screen.getByText('Loading...')).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText('Enter vendor name to look up history');
      expect(input).toBeDisabled();
    });
  });

  describe('Error handling', () => {
    it('displays error message on fetch failure', async () => {
      vi.mocked(getVendorHistory).mockRejectedValue(new Error('Failed to fetch'));

      render(<VendorHistoryPanel vendorName="TestVendor" />);

      const lookUpBtn = screen.getByText('Look Up');
      fireEvent.click(lookUpBtn);

      await waitFor(() => {
        expect(screen.getByText('Failed to fetch')).toBeInTheDocument();
      });
    });

    it('validates vendor name before submit', () => {
      render(<VendorHistoryPanel />);

      // Try submitting with empty vendor name - button should be disabled
      const lookUpBtn = screen.getByText('Look Up');
      expect(lookUpBtn).toBeDisabled();
    });
  });
});

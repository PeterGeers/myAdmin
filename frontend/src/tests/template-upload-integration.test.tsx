/**
 * Template Upload Integration Tests
 * 
 * Tests the integration between TemplateUpload component and validation/preview flow
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TemplateUpload } from '../components/TenantAdmin/TemplateManagement/TemplateUpload';
import * as templateApi from '../services/templateApi';

// Mock the template API
jest.mock('../services/templateApi', () => ({
  getCurrentTemplate: jest.fn(),
  TemplateType: {
    STR_INVOICE_NL: 'str_invoice_nl',
    STR_INVOICE_EN: 'str_invoice_en',
    BTW_AANGIFTE: 'btw_aangifte',
    AANGIFTE_IB: 'aangifte_ib',
    TOERISTENBELASTING: 'toeristenbelasting',
    FINANCIAL_REPORT: 'financial_report',
  },
}));

// Mock Chakra UI
jest.mock('@chakra-ui/react', () => ({
  Box: ({ children, ...props }: any) => {
    const { bg, p, borderRadius, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  VStack: ({ children, ...props }: any) => {
    const { spacing, align, color, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  HStack: ({ children, ...props }: any) => {
    const { spacing, flex, mt, borderRadius, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  Heading: ({ children }: any) => <h1>{children}</h1>,
  Text: ({ children, ...props }: any) => {
    const { fontSize, color, fontWeight, mb, ...domProps } = props;
    return <p {...domProps}>{children}</p>;
  },
  Button: ({ children, onClick, ...props }: any) => {
    const { colorScheme, isLoading, loadingText, isDisabled, variant, size, w, flex, mb, ...domProps } = props;
    return (
      <button onClick={onClick} disabled={isDisabled || isLoading} {...domProps}>
        {isLoading && loadingText ? loadingText : children}
      </button>
    );
  },
  Input: ({ ...props }: any) => {
    const { display, ...domProps } = props;
    return <input {...domProps} style={display === 'none' ? { display: 'none' } : undefined} />;
  },
  Textarea: ({ ...props }: any) => {
    const { fontFamily, fontSize, bg, isDisabled, minHeight, whiteSpace, overflowX, resize, ...domProps } = props;
    return <textarea disabled={isDisabled} {...domProps} />;
  },
  Select: ({ children, ...props }: any) => {
    const { isDisabled, placeholder, ...domProps } = props;
    return <select disabled={isDisabled} {...domProps}>{placeholder && <option value="">{placeholder}</option>}{children}</select>;
  },
  FormControl: ({ children, ...props }: any) => {
    const { isInvalid, isRequired, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  FormLabel: ({ children, ...props }: any) => {
    const { fontSize, ...domProps } = props;
    return <label {...domProps}>{children}</label>;
  },
  FormErrorMessage: ({ children }: any) => <div role="alert">{children}</div>,
  FormHelperText: ({ children, ...props }: any) => {
    const { color, fontSize, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  Alert: ({ children, ...props }: any) => {
    const { status, variant, bg, borderColor, ...domProps } = props;
    return <div role="alert" data-status={status} {...domProps}>{children}</div>;
  },
  AlertIcon: () => <span>ℹ️</span>,
  AlertTitle: ({ children, ...props }: any) => {
    const { fontSize, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  AlertDescription: ({ children, ...props }: any) => {
    const { fontSize, color, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  Spinner: ({ ...props }: any) => {
    const { size, ...domProps } = props;
    return <div role="status" {...domProps}>Loading...</div>;
  },
  Badge: ({ children, ...props }: any) => {
    const { colorScheme, ml, fontSize, ...domProps } = props;
    return <span {...domProps}>{children}</span>;
  },
  Collapse: ({ children, ...props }: any) => {
    const { animateOpacity, in: inProp, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  Icon: ({ as }: any) => <span>{as?.name || 'icon'}</span>,
  useDisclosure: () => ({
    isOpen: true,
    onOpen: jest.fn(),
    onClose: jest.fn(),
    onToggle: jest.fn(),
  }),
  useToast: () => jest.fn(),
}));

describe('Template Upload Integration Tests', () => {
  const mockOnUpload = jest.fn();
  const mockGetCurrentTemplate = templateApi.getCurrentTemplate as jest.MockedFunction<typeof templateApi.getCurrentTemplate>;

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Mock getCurrentTemplate to throw error (404) when no template found
    mockGetCurrentTemplate.mockRejectedValue(new Error('No template found'));
  });

  afterEach(() => {
    jest.clearAllTimers();
  });

  describe('Complete Upload Flow', () => {
    it('completes full upload workflow with all fields', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);

      // Step 1: Select template type
      const select = screen.getByRole('combobox', { name: /template type/i });
      await user.selectOptions(select, 'str_invoice_nl');

      // Verify description is shown
      expect(screen.getByText(/short-term rental invoice in dutch/i)).toBeInTheDocument();

      // Step 2: Upload file
      const file = new File(
        ['<html><body><h1>Invoice Template</h1></body></html>'],
        'invoice-template.html',
        { type: 'text/html' }
      );
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      // Verify file is displayed
      expect(screen.getByText('invoice-template.html')).toBeInTheDocument();
      expect(screen.getByText(/KB/i)).toBeInTheDocument();

      // Step 3: Add field mappings (optional)
      const textarea = screen.getByRole('textbox', { name: /field mappings \(json\)/i });
      fireEvent.change(textarea, {
        target: { value: '{"invoice_number": "{{invoice_id}}", "total": "{{amount}}"}' },
      });

      // Step 4: Submit
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      expect(uploadButton).not.toBeDisabled();
      
      await user.click(uploadButton);

      // Verify callback was called with correct parameters
      await waitFor(() => {
        expect(mockOnUpload).toHaveBeenCalledWith(
          expect.any(File),
          'str_invoice_nl',
          {
            invoice_number: '{{invoice_id}}',
            total: '{{amount}}',
          }
        );
      });
    });

    it('handles validation errors during upload', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);

      // Try to upload without selecting template type
      const file = new File(['<html></html>'], 'test.html', { type: 'text/html' });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      // Button should be disabled
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      expect(uploadButton).toBeDisabled();

      // Select template type
      const select = screen.getByRole('combobox', { name: /template type/i });
      await user.selectOptions(select, 'str_invoice_nl');

      // Button should now be enabled
      await waitFor(() => {
        expect(uploadButton).not.toBeDisabled();
      });
    });

    it('validates file type before upload', async () => {
      render(<TemplateUpload onUpload={mockOnUpload} />);

      // Try to upload non-HTML file
      const file = new File(['PDF content'], 'document.pdf', { type: 'application/pdf' });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      // Error should be displayed
      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent(/only html files/i);
      });

      // Upload button should be disabled
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      expect(uploadButton).toBeDisabled();

      // Callback should not have been called
      expect(mockOnUpload).not.toHaveBeenCalled();
    });

    it('validates file size before upload', async () => {
      render(<TemplateUpload onUpload={mockOnUpload} />);

      // Create file larger than 5MB
      const largeContent = 'x'.repeat(6 * 1024 * 1024);
      const file = new File([largeContent], 'large.html', { type: 'text/html' });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      // Error should be displayed
      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent(/file size exceeds 5mb/i);
      });

      // Upload button should be disabled
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      expect(uploadButton).toBeDisabled();
    });
  });

  describe('Field Mappings Integration', () => {
    it('validates JSON format in field mappings', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);

      // Select template type and upload file
      const select = screen.getByRole('combobox', { name: /template type/i });
      await user.selectOptions(select, 'str_invoice_nl');

      const file = new File(['<html></html>'], 'test.html', { type: 'text/html' });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      // Enter invalid JSON
      const textarea = screen.getByRole('textbox', { name: /field mappings \(json\)/i });
      fireEvent.change(textarea, { target: { value: '{invalid json}' } });

      // Try to upload
      const uploadButton = screen.getByRole('button', { name: /upload & preview template/i });
      await user.click(uploadButton);

      // Error should be displayed
      await waitFor(() => {
        expect(screen.getByText(/invalid json format/i)).toBeInTheDocument();
      });

      // Callback should not have been called
      expect(mockOnUpload).not.toHaveBeenCalled();
    });

    it('accepts empty field mappings', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);

      // Select template type and upload file
      const select = screen.getByRole('combobox', { name: /template type/i });
      await user.selectOptions(select, 'str_invoice_nl');

      const file = new File(['<html></html>'], 'test.html', { type: 'text/html' });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      // Leave field mappings as default ({})
      const textarea = screen.getByRole('textbox', { name: /field mappings \(json\)/i });
      expect(textarea).toHaveValue('{}');

      // Upload should work
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
  });

  describe('Loading and Disabled States', () => {
    it('disables all inputs when loading', () => {
      render(<TemplateUpload onUpload={mockOnUpload} loading={true} />);

      expect(screen.getByRole('combobox', { name: /template type/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /browse files/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /uploading/i })).toBeDisabled();
    });

    it('shows loading state during upload', () => {
      render(<TemplateUpload onUpload={mockOnUpload} loading={true} />);

      expect(screen.getByText(/uploading/i)).toBeInTheDocument();
    });
  });

  describe('User Experience Flow', () => {
    it('provides clear feedback at each step', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);

      // Initial state - instructions visible
      expect(screen.getByText(/upload instructions/i)).toBeInTheDocument();
      expect(screen.getByText(/select the template type/i)).toBeInTheDocument();

      // After selecting type - description shown
      const select = screen.getByRole('combobox', { name: /template type/i });
      await user.selectOptions(select, 'btw_aangifte');
      expect(screen.getByText(/vat declaration report/i)).toBeInTheDocument();

      // After uploading file - file info shown
      const file = new File(['<html></html>'], 'vat-template.html', { type: 'text/html' });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      expect(screen.getByText('vat-template.html')).toBeInTheDocument();
      expect(screen.getByText(/KB/i)).toBeInTheDocument();

      // Button text changes
      expect(screen.getByRole('button', { name: /change file/i })).toBeInTheDocument();
    });

    it('allows changing template type after selection', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);

      // Select first type
      const select = screen.getByRole('combobox', { name: /template type/i });
      await user.selectOptions(select, 'str_invoice_nl');
      expect(screen.getByText(/short-term rental invoice in dutch/i)).toBeInTheDocument();

      // Change to different type
      await user.selectOptions(select, 'financial_report');
      expect(screen.getByText(/general financial report/i)).toBeInTheDocument();
      expect(screen.queryByText(/short-term rental invoice in dutch/i)).not.toBeInTheDocument();
    });
  });
});

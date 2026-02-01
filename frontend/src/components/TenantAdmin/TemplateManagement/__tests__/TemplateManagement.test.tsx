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



// Mock Chakra UI to avoid dependency issues
jest.mock('@chakra-ui/react', () => (// Mock Chakra UI components to avoid dependency issues
// This removes Chakra-specific props before passing to DOM elements
{
  ChakraProvider: ({ children }: any) => <div>{children}</div>,
  Box: ({ children, ...props }: any) => {
    const { bg, p, px, py, m, mx, my, mt, mb, ml, mr, borderRadius, boxShadow, minH, maxH, minW, maxW, w, h, display, alignItems, justifyContent, flexDirection, flex, position, top, left, right, bottom, zIndex, overflow, border, borderColor, borderWidth, textAlign, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  VStack: ({ children, ...props }: any) => {
    const { spacing, align, w, h, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  HStack: ({ children, ...props }: any) => {
    const { spacing, justify, align, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  Grid: ({ children, ...props }: any) => {
    const { templateColumns, gap, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  GridItem: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  Heading: ({ children, ...props }: any) => {
    const { size, color, mb, ...domProps } = props;
    return <h1 {...domProps}>{children}</h1>;
  },
  Text: ({ children, ...props }: any) => {
    const { fontSize, fontWeight, color, as, mt, mb, ml, mr, textAlign, ...domProps } = props;
    const Component = as || 'p';
    return <Component {...domProps}>{children}</Component>;
  },
  Button: ({ children, onClick, ...props }: any) => {
    const { isDisabled, isLoading, loadingText, leftIcon, rightIcon, colorScheme, variant, size, w, flex, mb, mt, ml, mr, ...domProps } = props;
    return (
      <button onClick={onClick} disabled={isDisabled || isLoading} {...domProps}>
        {leftIcon}{isLoading && loadingText ? loadingText : children}{rightIcon}
      </button>
    );
  },
  Input: ({ ...props }: any) => {
    const { bg, isDisabled, isInvalid, isRequired, ...domProps } = props;
    return <input disabled={isDisabled} {...domProps} />;
  },
  Textarea: ({ ...props }: any) => {
    const { bg, fontFamily, fontSize, ...domProps } = props;
    return <textarea {...domProps} />;
  },
  Select: ({ children, ...props }: any) => {
    const { placeholder, ...domProps } = props;
    return (
      <select {...domProps}>
        {placeholder && <option value="">{placeholder}</option>}
        {children}
      </select>
    );
  },
  FormControl: ({ children, ...props }: any) => {
    const { isInvalid, isRequired, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  FormLabel: ({ children, ...props }: any) => {
    const { fontSize, ...domProps } = props;
    return <label {...domProps}>{children}</label>;
  },
  FormHelperText: ({ children, ...props }: any) => {
    const { color, fontSize, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  FormErrorMessage: ({ children }: any) => <div role="alert">{children}</div>,
  Alert: ({ children, ...props }: any) => {
    const { status, bg, borderRadius, size, mb, ...domProps } = props;
    return <div role="alert" {...domProps}>{children}</div>;
  },
  AlertIcon: () => <span>ℹ️</span>,
  AlertTitle: ({ children, ...props }: any) => {
    const { mb, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  AlertDescription: ({ children, ...props }: any) => {
    const { fontSize, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  CloseButton: ({ onClick }: any) => <button onClick={onClick}>×</button>,
  Progress: ({ ...props }: any) => {
    const { size, isIndeterminate, colorScheme, ...domProps } = props;
    return <div role="progressbar" {...domProps} />;
  },
  Skeleton: ({ ...props }: any) => {
    const { height, borderRadius, ...domProps } = props;
    return <div className="chakra-skeleton" {...domProps} />;
  },
  Badge: ({ children, ...props }: any) => {
    const { colorScheme, fontSize, px, py, textTransform, ...domProps } = props;
    return <span {...domProps}>{children}</span>;
  },
  Code: ({ children, ...props }: any) => {
    const { display, whiteSpace, p, bg, borderRadius, fontSize, ...domProps } = props;
    return <code {...domProps}>{children}</code>;
  },
  Divider: ({ ...props }: any) => {
    const { borderColor, ...domProps } = props;
    return <hr {...domProps} />;
  },
  Collapse: ({ children, ...props }: any) => {
    const { in: isOpen, animateOpacity, ...domProps } = props;
    return isOpen ? <div {...domProps}>{children}</div> : null;
  },
  Accordion: ({ children, ...props }: any) => {
    const { allowMultiple, defaultIndex, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  AccordionItem: ({ children, ...props }: any) => {
    const { border, borderColor, borderRadius, mb, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  AccordionButton: ({ children, onClick, ...props }: any) => {
    const { _hover, ...domProps } = props;
    return <button onClick={onClick} {...domProps}>{children}</button>;
  },
  AccordionPanel: ({ children, ...props }: any) => {
    const { pb, bg, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  AccordionIcon: () => <span>▼</span>,
  Modal: ({ children, ...props }: any) => {
    const { isOpen, onClose, size, scrollBehavior, ...domProps } = props;
    return isOpen ? <div role="dialog" {...domProps}>{children}</div> : null;
  },
  ModalOverlay: () => <div />,
  ModalContent: ({ children, ...props }: any) => {
    const { bg, maxH, borderColor, borderWidth, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  ModalHeader: ({ children }: any) => <h2>{children}</h2>,
  ModalBody: ({ children }: any) => <div>{children}</div>,
  ModalFooter: ({ children }: any) => <div>{children}</div>,
  ModalCloseButton: ({ onClick }: any) => <button onClick={onClick}>×</button>,
  Checkbox: ({ children, ...props }: any) => {
    const { isChecked, onChange, isDisabled, ...domProps } = props;
    return (
      <label>
        <input type="checkbox" checked={isChecked} onChange={onChange} disabled={isDisabled} role="checkbox" {...domProps} />
        {children}
      </label>
    );
  },
  Spinner: ({ ...props }: any) => {
    const { size, color, mb, ...domProps } = props;
    return <div role="status" {...domProps}>Loading...</div>;
  },
  Container: ({ children, ...props }: any) => {
    const { maxW, py, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  List: ({ children, ...props }: any) => {
    const { spacing, ...domProps } = props;
    return <ul {...domProps}>{children}</ul>;
  },
  ListItem: ({ children, ...props }: any) => {
    const { p, bg, borderRadius, border, borderColor, ...domProps } = props;
    return <li {...domProps}>{children}</li>;
  },
  ListIcon: ({ ...props }: any) => {
    const { as, color, mt, ...domProps } = props;
    return <span {...domProps}>✓</span>;
  },
  Icon: ({ ...props }: any) => {
    const { as, boxSize, color, mt, ...domProps } = props;
    return <span {...domProps}>{as?.name || 'icon'}</span>;
  },
  useDisclosure: () => ({
    isOpen: false,
    onOpen: jest.fn(),
    onClose: jest.fn(),
    onToggle: jest.fn(),
  }),
  useToast: () => jest.fn(),
}));

jest.mock('@chakra-ui/icons', () => ({
  CheckIcon: () => <span>✓</span>,
  CloseIcon: () => <span>✗</span>,
  WarningIcon: () => <span>⚠</span>,
  InfoIcon: () => <span>ℹ</span>,
  CheckCircleIcon: () => <span>✓</span>,
}));

jest.mock('@chakra-ui/react', () => require('../chakraMock').chakraMock);
jest.mock('@chakra-ui/icons', () => require('../chakraMock').iconsMock);
jest.mock('@chakra-ui/react', () => ({
  ChakraProvider: ({ children }: any) => <div>{children}</div>,
  Box: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  VStack: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  HStack: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  Grid: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  GridItem: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  Heading: ({ children, ...props }: any) => <h1 {...props}>{children}</h1>,
  Text: ({ children, ...props }: any) => <p {...props}>{children}</p>,
  Button: ({ children, onClick, isDisabled, isLoading, loadingText, leftIcon, ...props }: any) => (
    <button onClick={onClick} disabled={isDisabled || isLoading} {...props}>
      {leftIcon}{isLoading ? loadingText : children}
    </button>
  ),
  Input: (props: any) => <input {...props} />,
  Textarea: (props: any) => <textarea {...props} />,
  Select: ({ children, ...props }: any) => <select {...props}>{children}</select>,
  FormControl: ({ children }: any) => <div>{children}</div>,
  FormLabel: ({ children, ...props }: any) => <label {...props}>{children}</label>,
  FormHelperText: ({ children }: any) => <div>{children}</div>,
  FormErrorMessage: ({ children }: any) => <div role="alert">{children}</div>,
  Alert: ({ children, ...props }: any) => <div role="alert" {...props}>{children}</div>,
  AlertIcon: () => <span>ℹ️</span>,
  AlertTitle: ({ children }: any) => <div>{children}</div>,
  AlertDescription: ({ children }: any) => <div>{children}</div>,
  CloseButton: ({ onClick }: any) => <button onClick={onClick}>×</button>,
  Progress: () => <div role="progressbar" />,
  Skeleton: () => <div className="chakra-skeleton" />,
  Badge: ({ children }: any) => <span>{children}</span>,
  Code: ({ children, ...props }: any) => <code {...props}>{children}</code>,
  Divider: () => <hr />,
  Collapse: ({ in: isOpen, children }: any) => isOpen ? <div>{children}</div> : null,
  Accordion: ({ children }: any) => <div>{children}</div>,
  AccordionItem: ({ children }: any) => <div>{children}</div>,
  AccordionButton: ({ children, onClick }: any) => <button onClick={onClick}>{children}</button>,
  AccordionPanel: ({ children }: any) => <div>{children}</div>,
  AccordionIcon: () => <span>▼</span>,
  Modal: ({ isOpen, children }: any) => isOpen ? <div role="dialog">{children}</div> : null,
  ModalOverlay: () => <div />,
  ModalContent: ({ children }: any) => <div>{children}</div>,
  ModalHeader: ({ children }: any) => <h2>{children}</h2>,
  ModalBody: ({ children }: any) => <div>{children}</div>,
  ModalFooter: ({ children }: any) => <div>{children}</div>,
  ModalCloseButton: ({ onClick }: any) => <button onClick={onClick}>×</button>,
  Checkbox: ({ isChecked, onChange, isDisabled, onClick, children, ...props }: any) => (
    <label>
      <input type="checkbox" checked={isChecked} onChange={onChange} disabled={isDisabled} onClick={onClick} {...props} />
      {children}
    </label>
  ),
  Spinner: () => <div role="status">Loading...</div>,
  Container: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  useDisclosure: () => ({
    isOpen: false,
    onOpen: jest.fn(),
    onClose: jest.fn(),
    onToggle: jest.fn(),
  }),
  useToast: () => jest.fn(),
}));

jest.mock('@chakra-ui/icons', () => ({
  CheckIcon: () => <span>✓</span>,
  CloseIcon: () => <span>✗</span>,
  WarningIcon: () => <span>⚠</span>,
  InfoIcon: () => <span>ℹ</span>,
  CheckCircleIcon: () => <span>✓</span>,
}));


jest.mock('@chakra-ui/react', () => {
  const React = require('react');
  return {
    ChakraProvider: ({ children }: any) => React.createElement('div', null, children),
    Box: ({ children, ...props }: any) => React.createElement('div', props, children),
    VStack: ({ children, ...props }: any) => React.createElement('div', props, children),
    HStack: ({ children, ...props }: any) => React.createElement('div', props, children),
    Button: ({ children, ...props }: any) => React.createElement('button', props, children),
    Input: (props: any) => React.createElement('input', props),
    Textarea: (props: any) => React.createElement('textarea', props),
    Select: ({ children, ...props }: any) => React.createElement('select', props, children),
    FormControl: ({ children, ...props }: any) => React.createElement('div', props, children),
    FormLabel: ({ children, ...props }: any) => React.createElement('label', props, children),
    FormErrorMessage: ({ children, ...props }: any) => React.createElement('div', props, children),
    FormHelperText: ({ children, ...props }: any) => React.createElement('div', props, children),
    Text: ({ children, ...props }: any) => React.createElement('span', props, children),
    Heading: ({ children, ...props }: any) => React.createElement('h2', props, children),
    Alert: ({ children, ...props }: any) => React.createElement('div', { ...props, role: 'alert' }, children),
    AlertIcon: () => React.createElement('span', null, '⚠'),
    AlertTitle: ({ children, ...props }: any) => React.createElement('div', props, children),
    AlertDescription: ({ children, ...props }: any) => React.createElement('div', props, children),
    CloseButton: (props: any) => React.createElement('button', { ...props, 'aria-label': 'Close' }),
    Progress: (props: any) => React.createElement('div', props),
    Skeleton: (props: any) => React.createElement('div', { ...props, className: 'chakra-skeleton' }),
    Badge: ({ children, ...props }: any) => React.createElement('span', props, children),
    Divider: (props: any) => React.createElement('hr', props),
    Collapse: ({ children, in: isOpen, ...props }: any) => isOpen ? React.createElement('div', props, children) : null,
    Modal: ({ children, isOpen, ...props }: any) => isOpen ? React.createElement('div', { ...props, role: 'dialog' }, children) : null,
    ModalOverlay: ({ children, ...props }: any) => React.createElement('div', props, children),
    ModalContent: ({ children, ...props }: any) => React.createElement('div', props, children),
    ModalHeader: ({ children, ...props }: any) => React.createElement('div', props, children),
    ModalBody: ({ children, ...props }: any) => React.createElement('div', props, children),
    ModalFooter: ({ children, ...props }: any) => React.createElement('div', props, children),
    ModalCloseButton: (props: any) => React.createElement('button', { ...props, 'aria-label': 'Close' }),
    Accordion: ({ children, ...props }: any) => React.createElement('div', props, children),
    AccordionItem: ({ children, ...props }: any) => React.createElement('div', props, children),
    AccordionButton: ({ children, ...props }: any) => React.createElement('button', props, children),
    AccordionPanel: ({ children, ...props }: any) => React.createElement('div', props, children),
    AccordionIcon: () => React.createElement('span', null, '▼'),
    Checkbox: (props: any) => React.createElement('input', { ...props, type: 'checkbox' }),
    Code: ({ children, ...props }: any) => React.createElement('code', props, children),
    Container: ({ children, ...props }: any) => React.createElement('div', props, children),
    Grid: ({ children, ...props }: any) => React.createElement('div', props, children),
    GridItem: ({ children, ...props }: any) => React.createElement('div', props, children),
    Spinner: (props: any) => React.createElement('div', props, 'Loading...'),
    useDisclosure: () => ({ isOpen: false, onOpen: jest.fn(), onClose: jest.fn(), onToggle: jest.fn() }),
    useToast: () => jest.fn(),
    CheckIcon: () => React.createElement('span', null, '✓'),
    CloseIcon: () => React.createElement('span', null, '✗'),
    WarningIcon: () => React.createElement('span', null, '⚠'),
    InfoIcon: () => React.createElement('span', null, 'ℹ'),
    CheckCircleIcon: () => React.createElement('span', null, '✓'),
  };
});




// Mock the template API
jest.mock('../../../../services/templateApi');

describe('TemplateManagement', () => {
  const mockPreviewTemplate = templateApi.previewTemplate as jest.MockedFunction<typeof templateApi.previewTemplate>;
  const mockApproveTemplate = templateApi.approveTemplate as jest.MockedFunction<typeof templateApi.approveTemplate>;
  const mockRejectTemplate = templateApi.rejectTemplate as jest.MockedFunction<typeof templateApi.rejectTemplate>;
  const mockGetAIHelp = templateApi.getAIHelp as jest.MockedFunction<typeof templateApi.getAIHelp>;
  const mockApplyAIFixes = templateApi.applyAIFixes as jest.MockedFunction<typeof templateApi.applyAIFixes>;

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
      
      expect(screen.getByText(/upload/i)).toBeInTheDocument();
      expect(screen.getByText(/preview & validate/i)).toBeInTheDocument();
      expect(screen.getByText(/approve/i)).toBeInTheDocument();
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
        expect(screen.getByText(/template preview/i)).toBeInTheDocument();
      });
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
      const uploadStep = screen.getByText(/upload/i).closest('div');
      expect(uploadStep).toHaveAttribute('aria-current', 'step');
    });
  });
});







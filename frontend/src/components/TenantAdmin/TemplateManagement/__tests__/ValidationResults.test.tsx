/**
 * ValidationResults Component Unit Tests
 * 
 * Tests for displaying validation errors, warnings, and success states.
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ValidationResults } from '../ValidationResults';
import type { ValidationResult } from '../../../../types/template';



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
    const { isDisabled, isLoading, loadingText, leftIcon, rightIcon, colorScheme, variant, size, w, ...domProps } = props;
    return (
      <button onClick={onClick} disabled={isDisabled || isLoading} {...domProps}>
        {leftIcon}{isLoading && loadingText ? loadingText : children}{rightIcon}
      </button>
    );
  },
  Input: ({ ...props }: any) => {
    const { bg, ...domProps } = props;
    return <input {...domProps} />;
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




describe('ValidationResults', () => {
  describe('No Results State', () => {
    it('shows placeholder when no validation result', () => {
      render(<ValidationResults validationResult={null} />);
      
      expect(screen.getByText(/no validation results yet/i)).toBeInTheDocument();
      expect(screen.getByText(/upload a template to see validation results/i)).toBeInTheDocument();
    });
  });

  describe('Valid Template', () => {
    const validResult: ValidationResult = {
      is_valid: true,
      errors: [],
      warnings: [],
      checks_performed: ['html_syntax', 'placeholder_validation', 'security_check'],
    };

    it('shows success status', () => {
      render(<ValidationResults validationResult={validResult} />);
      
      expect(screen.getByText(/template valid/i)).toBeInTheDocument();
      expect(screen.getByText(/passed all validation checks/i)).toBeInTheDocument();
    });

    it('shows zero errors and warnings', () => {
      render(<ValidationResults validationResult={validResult} />);
      
      expect(screen.getByText(/0 error/i)).toBeInTheDocument();
      expect(screen.getByText(/0 warning/i)).toBeInTheDocument();
    });

    it('shows checks performed', () => {
      render(<ValidationResults validationResult={validResult} />);
      
      expect(screen.getByText(/checks: html_syntax, placeholder_validation, security_check/i)).toBeInTheDocument();
    });

    it('shows success message', () => {
      render(<ValidationResults validationResult={validResult} />);
      
      expect(screen.getByText(/no errors or warnings found/i)).toBeInTheDocument();
      expect(screen.getByText(/ready to approve/i)).toBeInTheDocument();
    });
  });

  describe('Invalid Template with Errors', () => {
    const invalidResult: ValidationResult = {
      is_valid: false,
      errors: [
        {
          type: 'missing_placeholder',
          message: 'Required placeholder {{invoice_number}} is missing',
          placeholder: 'invoice_number',
        },
        {
          type: 'invalid_syntax',
          message: 'Unclosed HTML tag detected',
          line: 42,
        },
      ],
      warnings: [],
    };

    it('shows failure status', () => {
      render(<ValidationResults validationResult={invalidResult} />);
      
      expect(screen.getByText(/validation failed/i)).toBeInTheDocument();
      expect(screen.getByText(/fix the errors below/i)).toBeInTheDocument();
    });

    it('shows error count', () => {
      render(<ValidationResults validationResult={invalidResult} />);
      
      expect(screen.getByText(/2 errors/i)).toBeInTheDocument();
    });

    it('displays errors section', () => {
      render(<ValidationResults validationResult={invalidResult} />);
      
      expect(screen.getByText(/errors \(2\)/i)).toBeInTheDocument();
    });

    it('shows error details', () => {
      render(<ValidationResults validationResult={invalidResult} />);
      
      expect(screen.getByText(/required placeholder {{invoice_number}} is missing/i)).toBeInTheDocument();
      expect(screen.getByText(/unclosed html tag detected/i)).toBeInTheDocument();
    });

    it('shows error type badges', () => {
      render(<ValidationResults validationResult={invalidResult} />);
      
      expect(screen.getByText(/missing placeholder/i)).toBeInTheDocument();
      expect(screen.getByText(/invalid syntax/i)).toBeInTheDocument();
    });

    it('shows line numbers when available', () => {
      render(<ValidationResults validationResult={invalidResult} />);
      
      expect(screen.getByText(/line:/i)).toBeInTheDocument();
      expect(screen.getByText(/42/)).toBeInTheDocument();
    });

    it('shows placeholder names when available', () => {
      render(<ValidationResults validationResult={invalidResult} />);
      
      expect(screen.getByText(/placeholder:/i)).toBeInTheDocument();
      expect(screen.getByText(/invoice_number/)).toBeInTheDocument();
    });
  });

  describe('Template with Warnings', () => {
    const warningResult: ValidationResult = {
      is_valid: true,
      errors: [],
      warnings: [
        {
          type: 'deprecated_placeholder',
          message: 'Placeholder {{old_field}} is deprecated',
          placeholder: 'old_field',
        },
        {
          type: 'style_recommendation',
          message: 'Consider using CSS classes instead of inline styles',
        },
      ],
    };

    it('shows warning count', () => {
      render(<ValidationResults validationResult={warningResult} />);
      
      expect(screen.getByText(/2 warnings/i)).toBeInTheDocument();
    });

    it('displays warnings section', () => {
      render(<ValidationResults validationResult={warningResult} />);
      
      expect(screen.getByText(/warnings \(2\)/i)).toBeInTheDocument();
    });

    it('shows warning details', () => {
      render(<ValidationResults validationResult={warningResult} />);
      
      expect(screen.getByText(/placeholder {{old_field}} is deprecated/i)).toBeInTheDocument();
      expect(screen.getByText(/consider using css classes/i)).toBeInTheDocument();
    });
  });

  describe('Template with Both Errors and Warnings', () => {
    const mixedResult: ValidationResult = {
      is_valid: false,
      errors: [
        {
          type: 'missing_placeholder',
          message: 'Required placeholder missing',
        },
      ],
      warnings: [
        {
          type: 'style_recommendation',
          message: 'Style recommendation',
        },
      ],
    };

    it('shows both error and warning counts', () => {
      render(<ValidationResults validationResult={mixedResult} />);
      
      expect(screen.getByText(/1 error/i)).toBeInTheDocument();
      expect(screen.getByText(/1 warning/i)).toBeInTheDocument();
    });

    it('displays both sections', () => {
      render(<ValidationResults validationResult={mixedResult} />);
      
      expect(screen.getByText(/errors \(1\)/i)).toBeInTheDocument();
      expect(screen.getByText(/warnings \(1\)/i)).toBeInTheDocument();
    });
  });

  describe('Collapsible Sections', () => {
    const result: ValidationResult = {
      is_valid: false,
      errors: [
        {
          type: 'error1',
          message: 'Error message 1',
        },
        {
          type: 'error2',
          message: 'Error message 2',
        },
      ],
      warnings: [
        {
          type: 'warning1',
          message: 'Warning message 1',
        },
      ],
    };

    it('errors section is expanded by default', () => {
      render(<ValidationResults validationResult={result} />);
      
      expect(screen.getByText(/error message 1/i)).toBeVisible();
      expect(screen.getByText(/error message 2/i)).toBeVisible();
    });

    it('warnings section is expanded by default', () => {
      render(<ValidationResults validationResult={result} />);
      
      expect(screen.getByText(/warning message 1/i)).toBeVisible();
    });

    it('can collapse errors section', async () => {
      const user = userEvent.setup();
      render(<ValidationResults validationResult={result} />);
      
      const errorsHeader = screen.getByText(/errors \(2\)/i);
      await user.click(errorsHeader);
      
      // Content should be hidden (Chakra Collapse uses display: none)
      expect(screen.queryByText(/error message 1/i)).not.toBeVisible();
    });

    it('can collapse warnings section', async () => {
      const user = userEvent.setup();
      render(<ValidationResults validationResult={result} />);
      
      const warningsHeader = screen.getByText(/warnings \(1\)/i);
      await user.click(warningsHeader);
      
      // Content should be hidden
      expect(screen.queryByText(/warning message 1/i)).not.toBeVisible();
    });
  });

  describe('Visual Styling', () => {
    it('uses green styling for valid templates', () => {
      const validResult: ValidationResult = {
        is_valid: true,
        errors: [],
        warnings: [],
      };
      
      render(<ValidationResults validationResult={validResult} />);
      
      const statusBox = screen.getByText(/template valid/i).closest('div');
      expect(statusBox).toHaveStyle({ backgroundColor: expect.stringContaining('green') });
    });

    it('uses red styling for invalid templates', () => {
      const invalidResult: ValidationResult = {
        is_valid: false,
        errors: [{ type: 'error', message: 'Error' }],
        warnings: [],
      };
      
      render(<ValidationResults validationResult={invalidResult} />);
      
      const statusBox = screen.getByText(/validation failed/i).closest('div');
      expect(statusBox).toHaveStyle({ backgroundColor: expect.stringContaining('red') });
    });
  });

  describe('Edge Cases', () => {
    it('handles empty errors array', () => {
      const result: ValidationResult = {
        is_valid: true,
        errors: [],
        warnings: [],
      };
      
      render(<ValidationResults validationResult={result} />);
      
      expect(screen.queryByText(/errors \(/i)).not.toBeInTheDocument();
    });

    it('handles empty warnings array', () => {
      const result: ValidationResult = {
        is_valid: true,
        errors: [],
        warnings: [],
      };
      
      render(<ValidationResults validationResult={result} />);
      
      expect(screen.queryByText(/warnings \(/i)).not.toBeInTheDocument();
    });

    it('handles missing checks_performed', () => {
      const result: ValidationResult = {
        is_valid: true,
        errors: [],
        warnings: [],
      };
      
      render(<ValidationResults validationResult={result} />);
      
      expect(screen.queryByText(/checks:/i)).not.toBeInTheDocument();
    });

    it('handles errors without line numbers', () => {
      const result: ValidationResult = {
        is_valid: false,
        errors: [
          {
            type: 'general_error',
            message: 'General error without line number',
          },
        ],
        warnings: [],
      };
      
      render(<ValidationResults validationResult={result} />);
      
      expect(screen.getByText(/general error without line number/i)).toBeInTheDocument();
      expect(screen.queryByText(/line:/i)).not.toBeInTheDocument();
    });

    it('handles errors without placeholders', () => {
      const result: ValidationResult = {
        is_valid: false,
        errors: [
          {
            type: 'syntax_error',
            message: 'Syntax error without placeholder',
          },
        ],
        warnings: [],
      };
      
      render(<ValidationResults validationResult={result} />);
      
      expect(screen.getByText(/syntax error without placeholder/i)).toBeInTheDocument();
      expect(screen.queryByText(/placeholder:/i)).not.toBeInTheDocument();
    });
  });
});







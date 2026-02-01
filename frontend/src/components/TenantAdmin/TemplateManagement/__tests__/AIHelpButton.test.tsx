/**
 * AIHelpButton Component Unit Tests
 * 
 * Tests for AI assistance modal, fix suggestions, and auto-fix application.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AIHelpButton } from '../AIHelpButton';
import type { AIHelpResponse, AIFixSuggestion } from '../../../../types/template';



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




describe('AIHelpButton', () => {
  const mockOnRequestHelp = jest.fn();
  const mockOnApplyFixes = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockOnRequestHelp.mockResolvedValue(undefined);
    mockOnApplyFixes.mockResolvedValue(undefined);
  });

  describe('Button Rendering', () => {
    it('renders AI help button', () => {
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={null}
          hasErrors={true}
        />
      );
      
      expect(screen.getByRole('button', { name: /get ai help/i })).toBeInTheDocument();
    });

    it('disables button when no errors', () => {
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={null}
          hasErrors={false}
        />
      );
      
      expect(screen.getByRole('button', { name: /get ai help/i })).toBeDisabled();
    });

    it('disables button when disabled prop is true', () => {
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={null}
          hasErrors={true}
          disabled={true}
        />
      );
      
      expect(screen.getByRole('button', { name: /get ai help/i })).toBeDisabled();
    });

    it('shows loading state', () => {
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={null}
          hasErrors={true}
          loading={true}
        />
      );
      
      expect(screen.getByText(/analyzing.../i)).toBeInTheDocument();
    });
  });

  describe('Modal Interaction', () => {
    it('opens modal when button is clicked', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={null}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      await waitFor(() => {
        expect(screen.getByText(/ai template assistant/i)).toBeInTheDocument();
      });
    });

    it('calls onRequestHelp when button is clicked', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={null}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      expect(mockOnRequestHelp).toHaveBeenCalledTimes(1);
    });

    it('closes modal when close button is clicked', async () => {
      const user = userEvent.setup();
      const aiSuggestions: AIHelpResponse = {
        success: true,
        ai_suggestions: {
          analysis: 'Test analysis',
          fixes: [],
          auto_fixable: false,
        },
      };
      
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      // Open modal
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      // Close modal
      const closeButton = screen.getByRole('button', { name: /close/i });
      await user.click(closeButton);
      
      await waitFor(() => {
        expect(screen.queryByText(/ai template assistant/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('AI Suggestions Display', () => {
    const aiSuggestions: AIHelpResponse = {
      success: true,
      ai_suggestions: {
        analysis: 'Your template has 2 issues that need attention.',
        fixes: [
          {
            issue: 'Missing required placeholder',
            suggestion: 'Add {{invoice_number}} placeholder',
            code_example: '<div>{{invoice_number}}</div>',
            location: 'Line 10',
            confidence: 'high',
            auto_fixable: true,
          },
          {
            issue: 'Unclosed HTML tag',
            suggestion: 'Close the <div> tag',
            code_example: '</div>',
            location: 'Line 25',
            confidence: 'medium',
            auto_fixable: false,
          },
        ],
        auto_fixable: true,
      },
      tokens_used: 150,
      cost_estimate: 0.0015,
    };

    it('displays analysis text', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      expect(screen.getByText(/your template has 2 issues/i)).toBeInTheDocument();
    });

    it('displays usage stats', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      expect(screen.getByText(/tokens: 150/i)).toBeInTheDocument();
      expect(screen.getByText(/cost: \$0\.0015/i)).toBeInTheDocument();
    });

    it('displays fix suggestions', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      expect(screen.getByText(/missing required placeholder/i)).toBeInTheDocument();
      expect(screen.getByText(/unclosed html tag/i)).toBeInTheDocument();
    });

    it('displays confidence badges', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      expect(screen.getByText(/high confidence/i)).toBeInTheDocument();
      expect(screen.getByText(/medium confidence/i)).toBeInTheDocument();
    });

    it('displays auto-fixable badges', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      expect(screen.getByText(/auto-fixable/i)).toBeInTheDocument();
    });
  });

  describe('Fix Selection', () => {
    const aiSuggestions: AIHelpResponse = {
      success: true,
      ai_suggestions: {
        analysis: 'Test analysis',
        fixes: [
          {
            issue: 'Issue 1',
            suggestion: 'Fix 1',
            code_example: 'code1',
            location: 'Line 1',
            confidence: 'high',
            auto_fixable: true,
          },
          {
            issue: 'Issue 2',
            suggestion: 'Fix 2',
            code_example: 'code2',
            location: 'Line 2',
            confidence: 'high',
            auto_fixable: true,
          },
        ],
        auto_fixable: true,
      },
    };

    it('allows selecting individual fixes', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      const checkboxes = screen.getAllByRole('checkbox');
      await user.click(checkboxes[0]);
      
      expect(checkboxes[0]).toBeChecked();
    });

    it('shows "Select All Auto-Fixable" button', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      expect(screen.getByRole('button', { name: /select all auto-fixable/i })).toBeInTheDocument();
    });

    it('selects all auto-fixable fixes when button is clicked', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      const selectAllButton = screen.getByRole('button', { name: /select all auto-fixable/i });
      await user.click(selectAllButton);
      
      const checkboxes = screen.getAllByRole('checkbox');
      expect(checkboxes[0]).toBeChecked();
      expect(checkboxes[1]).toBeChecked();
    });
  });

  describe('Apply Fixes', () => {
    const aiSuggestions: AIHelpResponse = {
      success: true,
      ai_suggestions: {
        analysis: 'Test analysis',
        fixes: [
          {
            issue: 'Issue 1',
            suggestion: 'Fix 1',
            code_example: 'code1',
            location: 'Line 1',
            confidence: 'high',
            auto_fixable: true,
          },
        ],
        auto_fixable: true,
      },
    };

    it('shows apply button when fixes are selected', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      const checkbox = screen.getByRole('checkbox');
      await user.click(checkbox);
      
      expect(screen.getByRole('button', { name: /apply 1 fix/i })).toBeInTheDocument();
    });

    it('calls onApplyFixes with selected fixes', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      const checkbox = screen.getByRole('checkbox');
      await user.click(checkbox);
      
      const applyButton = screen.getByRole('button', { name: /apply 1 fix/i });
      await user.click(applyButton);
      
      await waitFor(() => {
        expect(mockOnApplyFixes).toHaveBeenCalledWith([aiSuggestions.ai_suggestions!.fixes[0]]);
      });
    });

    it('closes modal after applying fixes', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      const checkbox = screen.getByRole('checkbox');
      await user.click(checkbox);
      
      const applyButton = screen.getByRole('button', { name: /apply 1 fix/i });
      await user.click(applyButton);
      
      await waitFor(() => {
        expect(screen.queryByText(/ai template assistant/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('Fallback Mode', () => {
    const fallbackSuggestions: AIHelpResponse = {
      success: true,
      fallback: true,
      ai_suggestions: {
        analysis: 'Generic help',
        fixes: [],
        auto_fixable: false,
      },
    };

    it('shows fallback badge', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={fallbackSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      expect(screen.getByText(/fallback mode/i)).toBeInTheDocument();
    });

    it('shows AI unavailable warning', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={fallbackSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      expect(screen.getByText(/ai service is currently unavailable/i)).toBeInTheDocument();
    });
  });

  describe('No Fixes Available', () => {
    const noFixesSuggestions: AIHelpResponse = {
      success: true,
      ai_suggestions: {
        analysis: 'No automatic fixes available',
        fixes: [],
        auto_fixable: false,
      },
    };

    it('shows no fixes message', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={noFixesSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      expect(screen.getByText(/no automatic fixes available/i)).toBeInTheDocument();
    });
  });

  describe('Accordion Interaction', () => {
    const aiSuggestions: AIHelpResponse = {
      success: true,
      ai_suggestions: {
        analysis: 'Test analysis',
        fixes: [
          {
            issue: 'Issue 1',
            suggestion: 'Suggestion 1',
            code_example: '<div>Example</div>',
            location: 'Line 10',
            confidence: 'high',
            auto_fixable: true,
          },
        ],
        auto_fixable: true,
      },
    };

    it('expands fix details when clicked', async () => {
      const user = userEvent.setup();
      render(
        <AIHelpButton
          onRequestHelp={mockOnRequestHelp}
          onApplyFixes={mockOnApplyFixes}
          aiSuggestions={aiSuggestions}
          hasErrors={true}
        />
      );
      
      const button = screen.getByRole('button', { name: /get ai help/i });
      await user.click(button);
      
      // Initially expanded (defaultIndex={[0]})
      expect(screen.getByText(/suggestion 1/i)).toBeVisible();
      expect(screen.getByText(/<div>Example<\/div>/i)).toBeVisible();
    });
  });
});







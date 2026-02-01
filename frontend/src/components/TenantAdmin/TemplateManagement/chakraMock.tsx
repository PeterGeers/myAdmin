// Mock Chakra UI components to avoid dependency issues
// This removes Chakra-specific props before passing to DOM elements
import React from 'react';

export const chakraMock = {
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
};

export const iconsMock = {
  CheckIcon: () => <span>✓</span>,
  CloseIcon: () => <span>✗</span>,
  WarningIcon: () => <span>⚠</span>,
  InfoIcon: () => <span>ℹ</span>,
  CheckCircleIcon: () => <span>✓</span>,
};

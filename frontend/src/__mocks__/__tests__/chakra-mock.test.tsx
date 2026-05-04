/**
 * Unit Tests for Chakra Mock Framework
 *
 * Verifies that all required components, hooks, and utilities are exported
 * and behave correctly for common test scenarios.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { renderHook } from '@testing-library/react';
import * as ChakraMock from '../chakra-ui-react';
import * as IconsMock from '../chakra-ui-icons';

// ---------------------------------------------------------------------------
// Requirement 1.1: Mock module exports all required components
// ---------------------------------------------------------------------------
describe('Mock module exports all required components', () => {
  const requiredComponents = [
    'Box', 'Flex', 'VStack', 'HStack', 'Grid', 'GridItem', 'Container',
    'Heading', 'Text', 'Button', 'Input', 'Textarea', 'Select', 'Checkbox',
    'Switch', 'FormControl', 'FormLabel', 'FormHelperText', 'FormErrorMessage',
    'Alert', 'AlertIcon', 'AlertTitle', 'AlertDescription',
    'Modal', 'ModalOverlay', 'ModalContent', 'ModalHeader', 'ModalBody',
    'ModalFooter', 'ModalCloseButton',
    'Drawer', 'DrawerOverlay', 'DrawerContent', 'DrawerHeader', 'DrawerBody',
    'DrawerFooter', 'DrawerCloseButton',
    'AlertDialog', 'AlertDialogOverlay', 'AlertDialogContent',
    'AlertDialogHeader', 'AlertDialogBody', 'AlertDialogFooter',
    'Popover', 'PopoverTrigger', 'PopoverContent', 'PopoverBody',
    'PopoverHeader', 'PopoverCloseButton',
    'Accordion', 'AccordionItem', 'AccordionButton', 'AccordionPanel',
    'AccordionIcon',
    'Tabs', 'TabList', 'Tab', 'TabPanels', 'TabPanel',
    'Badge', 'Code', 'Divider', 'Spinner', 'Progress', 'Skeleton',
    'Collapse', 'CloseButton', 'List', 'ListItem', 'ListIcon', 'Icon',
    'Card', 'CardBody', 'CardHeader', 'ChakraProvider', 'Tooltip',
    'Menu', 'MenuButton', 'MenuList', 'MenuItem',
    'Table', 'Thead', 'Tbody', 'Tr', 'Th', 'Td', 'TableContainer', 'Image',
  ];

  it.each(requiredComponents)('exports %s as a function', (name) => {
    const exported = (ChakraMock as any)[name];
    expect(exported).toBeDefined();
    expect(typeof exported).toBe('function');
  });
});

// ---------------------------------------------------------------------------
// Requirement 1.6: Mock module exports all required hooks
// ---------------------------------------------------------------------------
describe('Mock module exports all required hooks', () => {
  it.each(['useToast', 'useDisclosure', 'useColorMode', 'useColorModeValue'])(
    'exports %s as a function',
    (name) => {
      const exported = (ChakraMock as any)[name];
      expect(exported).toBeDefined();
      expect(typeof exported).toBe('function');
    },
  );
});

// ---------------------------------------------------------------------------
// Requirement 1.7: Mock module exports all required utilities
// ---------------------------------------------------------------------------
describe('Mock module exports all required utilities', () => {
  it.each(['extendTheme', 'forwardRef', 'keyframes', 'createStandaloneToast'])(
    'exports %s as a function',
    (name) => {
      const exported = (ChakraMock as any)[name];
      expect(exported).toBeDefined();
      expect(typeof exported).toBe('function');
    },
  );
});

// ---------------------------------------------------------------------------
// Requirement 1.9: useToast returns a callable function
// ---------------------------------------------------------------------------
describe('useToast', () => {
  it('returns a callable function', () => {
    const { result } = renderHook(() => ChakraMock.useToast());
    expect(typeof result.current).toBe('function');
    // Should not throw when called
    result.current({ title: 'Test', status: 'success' });
  });
});

// ---------------------------------------------------------------------------
// Requirement 1.11: forwardRef preserves ref forwarding
// ---------------------------------------------------------------------------
describe('forwardRef', () => {
  it('preserves ref forwarding', () => {
    const MyComponent = ChakraMock.forwardRef((props: any, ref: any) => (
      <div ref={ref} data-testid="forwarded" {...props} />
    ));

    const ref = React.createRef<HTMLDivElement>();
    render(<MyComponent ref={ref} />);

    expect(ref.current).not.toBeNull();
    expect(ref.current!.getAttribute('data-testid')).toBe('forwarded');
  });
});

// ---------------------------------------------------------------------------
// Requirement 1.12: createStandaloneToast returns { toast: fn }
// ---------------------------------------------------------------------------
describe('createStandaloneToast', () => {
  it('returns an object with a callable toast property', () => {
    const result = ChakraMock.createStandaloneToast();
    expect(result).toHaveProperty('toast');
    expect(typeof result.toast).toBe('function');
    // Should not throw when called
    result.toast({ title: 'Test' });
  });
});

// ---------------------------------------------------------------------------
// Requirement 2.1: Icons module exports all required icons
// ---------------------------------------------------------------------------
describe('Icons module exports all required icons', () => {
  const requiredIcons = [
    'CheckIcon', 'CloseIcon', 'WarningIcon', 'InfoIcon', 'CheckCircleIcon',
    'SearchIcon', 'ChevronDownIcon', 'ChevronUpIcon', 'ViewIcon', 'ViewOffIcon',
    'ArrowUpIcon', 'ArrowDownIcon', 'AddIcon', 'DeleteIcon', 'EditIcon',
    'ExternalLinkIcon', 'DownloadIcon', 'HamburgerIcon',
    // Backward-compatible icons
    'ArrowBackIcon', 'ArrowForwardIcon', 'ChevronLeftIcon', 'ChevronRightIcon',
    'CopyIcon', 'InfoOutlineIcon', 'LockIcon', 'MinusIcon', 'MoonIcon',
    'RepeatIcon', 'Search2Icon', 'SettingsIcon', 'SmallAddIcon', 'SmallCloseIcon',
    'SpinnerIcon', 'StarIcon', 'SunIcon', 'TimeIcon',
    'TriangleDownIcon', 'TriangleUpIcon', 'UnlockIcon', 'WarningTwoIcon',
  ];

  it.each(requiredIcons)('exports %s as a function', (name) => {
    const exported = (IconsMock as any)[name];
    expect(exported).toBeDefined();
    expect(typeof exported).toBe('function');
  });

  it('exports createIcon factory', () => {
    expect(typeof IconsMock.createIcon).toBe('function');
  });
});

// ---------------------------------------------------------------------------
// Requirement 6.4: Select forwards value and onChange
// ---------------------------------------------------------------------------
describe('Select', () => {
  it('forwards value and onChange to native select', () => {
    const handleChange = vi.fn();
    render(
      <ChakraMock.Select value="option1" onChange={handleChange} data-testid="sel">
        <option value="option1">Option 1</option>
        <option value="option2">Option 2</option>
      </ChakraMock.Select>,
    );

    const select = screen.getByTestId('sel') as HTMLSelectElement;
    expect(select.tagName).toBe('SELECT');
    expect(select.value).toBe('option1');

    fireEvent.change(select, { target: { value: 'option2' } });
    expect(handleChange).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Requirement 6.5: Checkbox forwards isChecked/onChange
// ---------------------------------------------------------------------------
describe('Checkbox', () => {
  it('forwards isChecked and onChange to native input[type=checkbox]', () => {
    const handleChange = vi.fn();
    const { container } = render(
      <ChakraMock.Checkbox isChecked={true} onChange={handleChange}>
        Accept
      </ChakraMock.Checkbox>,
    );

    const checkbox = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(checkbox).not.toBeNull();
    expect(checkbox.checked).toBe(true);

    fireEvent.click(checkbox);
    expect(handleChange).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Requirement 6.8: Tabs renders children queryable via RTL
// ---------------------------------------------------------------------------
describe('Tabs', () => {
  it('renders Tab and TabPanel children queryable via RTL', () => {
    render(
      <ChakraMock.Tabs>
        <ChakraMock.TabList>
          <ChakraMock.Tab>Tab 1</ChakraMock.Tab>
          <ChakraMock.Tab>Tab 2</ChakraMock.Tab>
        </ChakraMock.TabList>
        <ChakraMock.TabPanels>
          <ChakraMock.TabPanel>Panel 1 content</ChakraMock.TabPanel>
          <ChakraMock.TabPanel>Panel 2 content</ChakraMock.TabPanel>
        </ChakraMock.TabPanels>
      </ChakraMock.Tabs>,
    );

    expect(screen.getByText('Tab 1')).toBeDefined();
    expect(screen.getByText('Tab 2')).toBeDefined();
    expect(screen.getByText('Panel 1 content')).toBeDefined();
    expect(screen.getByText('Panel 2 content')).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// Requirement 6.10: Popover renders children queryable via RTL
// ---------------------------------------------------------------------------
describe('Popover', () => {
  it('renders PopoverTrigger and PopoverContent children queryable via RTL', () => {
    render(
      <ChakraMock.Popover>
        <ChakraMock.PopoverTrigger>
          <button>Open Popover</button>
        </ChakraMock.PopoverTrigger>
        <ChakraMock.PopoverContent>
          <ChakraMock.PopoverHeader>Header</ChakraMock.PopoverHeader>
          <ChakraMock.PopoverBody>Body content</ChakraMock.PopoverBody>
        </ChakraMock.PopoverContent>
      </ChakraMock.Popover>,
    );

    expect(screen.getByText('Open Popover')).toBeDefined();
    expect(screen.getByText('Header')).toBeDefined();
    expect(screen.getByText('Body content')).toBeDefined();
  });
});

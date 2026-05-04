/**
 * Centralized Chakra UI Mock Module
 *
 * Provides lightweight mock implementations for all @chakra-ui/react exports.
 * Loaded via resolve.alias in vite.config.ts test block so that ALL imports
 * (direct and transitive) of @chakra-ui/react resolve here instead of the
 * real package. This prevents the @zag-js/focus-visible jsdom crash and
 * eliminates per-file vi.mock() boilerplate.
 *
 * CRITICAL: This file must contain ZERO imports from @chakra-ui/react,
 * @zag-js/focus-visible, or any Chakra internal package.
 */
import React from 'react';
import { vi } from 'vitest';
import { filterChakraProps } from './chakra-prop-filter';

// ---------------------------------------------------------------------------
// Pattern A: Simple container → div
// ---------------------------------------------------------------------------
export const Box = ({ children, as: As, ...props }: any) => {
  const filtered = filterChakraProps(props);
  if (As) return <As {...filtered}>{children}</As>;
  return <div {...filtered}>{children}</div>;
};
export const Flex = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const VStack = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const HStack = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const Stack = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const Grid = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const GridItem = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const Container = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const Card = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const CardBody = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const CardHeader = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const FormControl = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const ModalBody = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const ModalFooter = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const DrawerBody = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const DrawerFooter = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const PopoverBody = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const AccordionPanel = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const TabPanels = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const TabPanel = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const AlertDescription = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const FormHelperText = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const TableContainer = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const SimpleGrid = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const Wrap = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const WrapItem = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const ButtonGroup = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);

// ---------------------------------------------------------------------------
// Pattern B: Semantic HTML elements
// ---------------------------------------------------------------------------
export const Heading = ({ children, ...props }: any) => (
  <h2 {...filterChakraProps(props)}>{children}</h2>
);
export const Text = ({ children, ...props }: any) => (
  <p {...filterChakraProps(props)}>{children}</p>
);

export const Button = ({
  children, onClick, isDisabled, isLoading, loadingText, ...props
}: any) => (
  <button
    onClick={onClick}
    disabled={isDisabled || isLoading}
    {...filterChakraProps(props)}
  >
    {isLoading && loadingText ? loadingText : children}
  </button>
);

export const Input = ({
  value,
  onChange,
  placeholder,
  type,
  isDisabled,
  ...props
}: any) => (
  <input
    value={value}
    onChange={onChange}
    placeholder={placeholder}
    type={type}
    disabled={isDisabled}
    {...filterChakraProps(props)}
  />
);

export const Textarea = ({
  value,
  onChange,
  placeholder,
  isDisabled,
  ...props
}: any) => (
  <textarea
    value={value}
    onChange={onChange}
    placeholder={placeholder}
    disabled={isDisabled}
    {...filterChakraProps(props)}
  />
);

export const Select = ({
  children,
  value,
  onChange,
  placeholder,
  isDisabled,
  ...props
}: any) => (
  <select
    value={value}
    onChange={onChange}
    disabled={isDisabled}
    {...filterChakraProps(props)}
  >
    {placeholder && <option value="">{placeholder}</option>}
    {children}
  </select>
);

export const Checkbox = ({ children, isChecked, onChange, ...props }: any) => (
  <label {...filterChakraProps(props)}>
    <input type="checkbox" checked={isChecked} onChange={onChange} />
    {children}
  </label>
);

export const Code = ({ children, ...props }: any) => (
  <code {...filterChakraProps(props)}>{children}</code>
);

export const Divider = (props: any) => <hr {...filterChakraProps(props)} />;

export const Image = (props: any) => <img {...filterChakraProps(props)} />;

export const Link = ({ children, ...props }: any) => (
  <a {...filterChakraProps(props)}>{children}</a>
);

// Table elements
export const Table = ({ children, ...props }: any) => (
  <table {...filterChakraProps(props)}>{children}</table>
);
export const Thead = ({ children, ...props }: any) => (
  <thead {...filterChakraProps(props)}>{children}</thead>
);
export const Tbody = ({ children, ...props }: any) => (
  <tbody {...filterChakraProps(props)}>{children}</tbody>
);
export const Tr = ({ children, ...props }: any) => (
  <tr {...filterChakraProps(props)}>{children}</tr>
);
export const Th = ({ children, ...props }: any) => (
  <th {...filterChakraProps(props)}>{children}</th>
);
export const Td = ({ children, ...props }: any) => (
  <td {...filterChakraProps(props)}>{children}</td>
);

// List elements
export const List = ({ children, ...props }: any) => (
  <ul {...filterChakraProps(props)}>{children}</ul>
);
export const ListItem = ({ children, ...props }: any) => (
  <li {...filterChakraProps(props)}>{children}</li>
);

// ---------------------------------------------------------------------------
// Pattern C: Conditional render
// ---------------------------------------------------------------------------
export const Modal = ({ children, isOpen, ...props }: any) =>
  isOpen ? (
    <div role="dialog" {...filterChakraProps(props)}>{children}</div>
  ) : null;

export const AlertDialog = ({ children, isOpen, ...props }: any) =>
  isOpen ? (
    <div role="alertdialog" {...filterChakraProps(props)}>{children}</div>
  ) : null;

export const Drawer = ({ children, isOpen, ...props }: any) =>
  isOpen ? (
    <div role="dialog" {...filterChakraProps(props)}>{children}</div>
  ) : null;

export const Collapse = ({ children, in: isVisible, ...props }: any) =>
  isVisible ? (
    <div {...filterChakraProps(props)}>{children}</div>
  ) : null;

// ---------------------------------------------------------------------------
// Pattern D: Passthrough / no-op
// ---------------------------------------------------------------------------
export const ModalOverlay = ({ children }: any) =>
  children ? <div>{children}</div> : <div />;
export const DrawerOverlay = ({ children }: any) =>
  children ? <div>{children}</div> : <div />;
export const AlertDialogOverlay = ({ children }: any) =>
  children ? <div>{children}</div> : <div />;

export const Tooltip = ({ children }: any) => <>{children}</>;
export const PopoverTrigger = ({ children }: any) => <>{children}</>;

export const AccordionIcon = (props: any) => (
  <span data-testid="accordion-icon" {...filterChakraProps(props)} />
);
export const AlertIcon = (props: any) => (
  <span data-testid="alert-icon" {...filterChakraProps(props)} />
);
export const ListIcon = (props: any) => (
  <span data-testid="list-icon" {...filterChakraProps(props)} />
);

export const Skeleton = ({ children, ...props }: any) =>
  children ? <>{children}</> : <div {...filterChakraProps(props)} />;

export const ModalCloseButton = (props: any) => (
  <button aria-label="Close" {...filterChakraProps(props)} />
);
export const DrawerCloseButton = (props: any) => (
  <button aria-label="Close" {...filterChakraProps(props)} />
);
export const PopoverCloseButton = (props: any) => (
  <button aria-label="Close" {...filterChakraProps(props)} />
);

// ---------------------------------------------------------------------------
// Remaining component mocks
// ---------------------------------------------------------------------------
export const Alert = ({ children, ...props }: any) => (
  <div role="alert" {...filterChakraProps(props)}>{children}</div>
);
export const AlertTitle = ({ children, ...props }: any) => (
  <div data-testid="alert-title" {...filterChakraProps(props)}>{children}</div>
);

export const ModalHeader = ({ children, ...props }: any) => (
  <h2 {...filterChakraProps(props)}>{children}</h2>
);
export const ModalContent = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);

export const DrawerHeader = ({ children, ...props }: any) => (
  <h2 {...filterChakraProps(props)}>{children}</h2>
);
export const DrawerContent = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);

export const AlertDialogContent = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const AlertDialogHeader = ({ children, ...props }: any) => (
  <h2 {...filterChakraProps(props)}>{children}</h2>
);
export const AlertDialogBody = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const AlertDialogFooter = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);

export const Popover = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const PopoverContent = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const PopoverHeader = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);

export const Accordion = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const AccordionItem = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const AccordionButton = ({ children, ...props }: any) => (
  <button {...filterChakraProps(props)}>{children}</button>
);

export const Tabs = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const TabList = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const Tab = ({ children, ...props }: any) => (
  <button {...filterChakraProps(props)}>{children}</button>
);

export const Badge = ({ children, ...props }: any) => (
  <span {...filterChakraProps(props)}>{children}</span>
);
export const Spinner = (props: any) => (
  <span role="status" {...filterChakraProps(props)} />
);
export const Progress = (props: any) => (
  <div role="progressbar" {...filterChakraProps(props)} />
);
export const CloseButton = (props: any) => (
  <button aria-label="Close" {...filterChakraProps(props)} />
);
export const Icon = (props: any) => (
  <span {...filterChakraProps(props)} />
);
export const Switch = ({ isChecked, onChange, ...props }: any) => (
  <input type="checkbox" checked={isChecked} onChange={onChange} {...filterChakraProps(props)} />
);
export const FormLabel = ({ children, ...props }: any) => (
  <label {...filterChakraProps(props)}>{children}</label>
);
export const FormErrorMessage = ({ children, ...props }: any) => (
  <div role="alert" {...filterChakraProps(props)}>{children}</div>
);

export const Menu = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const MenuButton = ({ children, ...props }: any) => (
  <button {...filterChakraProps(props)}>{children}</button>
);
export const MenuList = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const MenuItem = ({ children, ...props }: any) => (
  <button {...filterChakraProps(props)}>{children}</button>
);
export const IconButton = ({ 'aria-label': ariaLabel, onClick, isDisabled, disabled, ...props }: any) => (
  <button aria-label={ariaLabel} onClick={onClick} disabled={isDisabled || disabled} {...filterChakraProps(props)} />
);
export const Tag = ({ children, ...props }: any) => (
  <span {...filterChakraProps(props)}>{children}</span>
);
export const TagLabel = ({ children, ...props }: any) => (
  <span {...filterChakraProps(props)}>{children}</span>
);

export const ChakraProvider = ({ children }: any) => <>{children}</>;

export const InputGroup = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
export const InputLeftElement = ({ children, ...props }: any) => (
  <span {...filterChakraProps(props)}>{children}</span>
);
export const InputRightElement = ({ children, ...props }: any) => (
  <span {...filterChakraProps(props)}>{children}</span>
);

// ---------------------------------------------------------------------------
// Hook mocks
// ---------------------------------------------------------------------------
export const useDisclosure = (options?: { defaultIsOpen?: boolean }) => {
  const [isOpen, setIsOpen] = React.useState(options?.defaultIsOpen ?? false);
  return {
    isOpen,
    onOpen: vi.fn(() => setIsOpen(true)),
    onClose: vi.fn(() => setIsOpen(false)),
    onToggle: vi.fn(() => setIsOpen((prev: boolean) => !prev)),
  };
};

export const useToast = () => vi.fn();

export const useColorMode = () => ({
  colorMode: 'light' as const,
  toggleColorMode: vi.fn(),
  setColorMode: vi.fn(),
});

export const useColorModeValue = (light: any, _dark: any) => light;

// ---------------------------------------------------------------------------
// Utility mocks
// ---------------------------------------------------------------------------
export const extendTheme = (config: any) => config ?? {};

export const forwardRef = (renderFn: any) => React.forwardRef(renderFn);

export const keyframes = () => '';

export const createStandaloneToast = () => ({ toast: vi.fn() });

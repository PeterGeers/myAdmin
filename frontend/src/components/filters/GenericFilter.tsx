import React, { useRef, useCallback, useMemo } from 'react';
import {
  Button,
  Checkbox,
  FormControl,
  FormLabel,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  Select,
  Text,
  HStack,
  Spinner,
  Alert,
  AlertIcon,
  useDisclosure,
} from '@chakra-ui/react';
import { ChevronDownIcon } from '@chakra-ui/icons';

/**
 * Generic filter component props interface
 * @template T - The type of data being filtered
 */
export interface GenericFilterProps<T> {
  // Core filtering
  /** Current selected values */
  values: T[];
  /** Callback when selection changes */
  onChange: (values: T[]) => void;
  /** Available options to select from */
  availableOptions: T[];

  // Behavior
  /** Enable multi-select mode (default: false for single-select) */
  multiSelect?: boolean;
  /** Disable the filter */
  disabled?: boolean;

  // Display
  /** Label for the filter */
  label: string;
  /** Placeholder text when no selection */
  placeholder?: string;
  /** Size variant */
  size?: 'sm' | 'md' | 'lg';

  // Rendering
  /** Custom option renderer */
  renderOption?: (option: T) => React.ReactNode;
  /** Get display label from option */
  getOptionLabel?: (option: T) => string;
  /** Get unique value from option */
  getOptionValue?: (option: T) => string;

  // State
  /** Show loading state */
  isLoading?: boolean;
  /** Error message to display */
  error?: string | null;
}

/**
 * GenericFilter - A reusable filter component supporting both single and multi-select modes
 * 
 * @template T - The type of data being filtered (string, object, etc.)
 * 
 * Features:
 * - Single-select mode (dropdown)
 * - Multi-select mode (checkbox menu)
 * - Type-safe with TypeScript generics
 * - Accessible (ARIA labels, keyboard navigation)
 * - Loading and error states
 * - Customizable rendering
 * 
 * @example
 * // Single-select string filter
 * <GenericFilter
 *   values={[selectedYear]}
 *   onChange={(values) => setSelectedYear(values[0])}
 *   availableOptions={['2023', '2024', '2025']}
 *   label="Year"
 *   placeholder="Select year"
 * />
 * 
 * @example
 * // Multi-select object filter
 * <GenericFilter
 *   values={selectedListings}
 *   onChange={setSelectedListings}
 *   availableOptions={listings}
 *   multiSelect
 *   label="Listings"
 *   getOptionLabel={(listing) => listing.name}
 *   getOptionValue={(listing) => listing.id}
 *   renderOption={(listing) => (
 *     <Box>
 *       <Text fontWeight="bold">{listing.name}</Text>
 *       <Text fontSize="sm">{listing.address}</Text>
 *     </Box>
 *   )}
 * />
 */
export function GenericFilter<T>({
  values,
  onChange,
  availableOptions,
  multiSelect = false,
  disabled = false,
  label,
  placeholder = 'Select...',
  size = 'md',
  renderOption,
  getOptionLabel,
  getOptionValue,
  isLoading = false,
  error = null,
}: GenericFilterProps<T>): React.ReactElement {
  const { isOpen, onOpen, onClose } = useDisclosure();
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  // Default label/value extractors for primitive types
  const defaultGetLabel = useCallback((option: T): string => {
    if (typeof option === 'string' || typeof option === 'number') {
      return String(option);
    }
    if (option && typeof option === 'object' && 'label' in option) {
      return String((option as any).label);
    }
    return String(option);
  }, []);

  const defaultGetValue = useCallback((option: T): string => {
    if (typeof option === 'string' || typeof option === 'number') {
      return String(option);
    }
    if (option && typeof option === 'object' && 'value' in option) {
      return String((option as any).value);
    }
    if (option && typeof option === 'object' && 'id' in option) {
      return String((option as any).id);
    }
    return String(option);
  }, []);

  const getLabelFn = getOptionLabel || defaultGetLabel;
  const getValueFn = getOptionValue || defaultGetValue;

  // Check if an option is selected
  const isSelected = useCallback(
    (option: T): boolean => {
      const optionValue = getValueFn(option);
      return values.some((v) => getValueFn(v) === optionValue);
    },
    [values, getValueFn]
  );

  // Handle single-select change
  const handleSingleSelectChange = useCallback(
    (event: React.ChangeEvent<HTMLSelectElement>) => {
      const selectedValue = event.target.value;
      if (!selectedValue) {
        onChange([]);
        return;
      }
      const selectedOption = availableOptions.find(
        (opt) => getValueFn(opt) === selectedValue
      );
      if (selectedOption) {
        onChange([selectedOption]);
      }
    },
    [availableOptions, onChange, getValueFn]
  );

  // Handle multi-select toggle
  const handleMultiSelectToggle = useCallback(
    (option: T) => {
      const optionValue = getValueFn(option);
      const isCurrentlySelected = values.some((v) => getValueFn(v) === optionValue);

      if (isCurrentlySelected) {
        // Remove from selection
        onChange(values.filter((v) => getValueFn(v) !== optionValue));
      } else {
        // Add to selection
        onChange([...values, option]);
      }
    },
    [values, onChange, getValueFn]
  );

  // Get display text for selected values
  const getDisplayText = useMemo(() => {
    if (values.length === 0) {
      return placeholder;
    }
    if (values.length === 1) {
      return getLabelFn(values[0]);
    }
    return `${values.length} selected`;
  }, [values, placeholder, getLabelFn]);

  // Render single-select mode
  if (!multiSelect) {
    return (
      <FormControl isDisabled={disabled || isLoading} size={size}>
        <FormLabel htmlFor={`filter-${label}`}>{label}</FormLabel>
        {error && (
          <Alert status="error" mb={2} size="sm">
            <AlertIcon />
            {error}
          </Alert>
        )}
        <Select
          id={`filter-${label}`}
          value={values.length > 0 ? getValueFn(values[0]) : ''}
          onChange={handleSingleSelectChange}
          placeholder={placeholder}
          size={size}
          aria-label={label}
          icon={isLoading ? <Spinner size="sm" /> : <ChevronDownIcon />}
        >
          {availableOptions.map((option) => {
            const value = getValueFn(option);
            const displayLabel = getLabelFn(option);
            return (
              <option key={value} value={value}>
                {displayLabel}
              </option>
            );
          })}
        </Select>
      </FormControl>
    );
  }

  // Render multi-select mode
  return (
    <FormControl isDisabled={disabled || isLoading} size={size}>
      <FormLabel htmlFor={`filter-${label}`}>{label}</FormLabel>
      {error && (
        <Alert status="error" mb={2} size="sm">
          <AlertIcon />
          {error}
        </Alert>
      )}
      <Menu isOpen={isOpen} onClose={onClose} closeOnSelect={false}>
        <MenuButton
          as={Button}
          ref={menuButtonRef}
          rightIcon={isLoading ? <Spinner size="sm" /> : <ChevronDownIcon />}
          onClick={onOpen}
          disabled={disabled || isLoading}
          size={size}
          width="100%"
          textAlign="left"
          fontWeight="normal"
          aria-label={label}
          aria-haspopup="true"
          aria-expanded={isOpen}
        >
          <Text isTruncated>{getDisplayText}</Text>
        </MenuButton>
        <MenuList maxH="300px" overflowY="auto" minW="200px">
          {availableOptions.length === 0 ? (
            <MenuItem isDisabled>
              <Text color="gray.500">No options available</Text>
            </MenuItem>
          ) : (
            availableOptions.map((option) => {
              const value = getValueFn(option);
              const selected = isSelected(option);
              return (
                <MenuItem
                  key={value}
                  onClick={() => handleMultiSelectToggle(option)}
                  closeOnSelect={false}
                  aria-checked={selected}
                  role="menuitemcheckbox"
                >
                  <HStack spacing={2} width="100%">
                    <Checkbox
                      isChecked={selected}
                      pointerEvents="none"
                      aria-hidden="true"
                    />
                    {renderOption ? (
                      renderOption(option)
                    ) : (
                      <Text>{getLabelFn(option)}</Text>
                    )}
                  </HStack>
                </MenuItem>
              );
            })
          )}
        </MenuList>
      </Menu>
    </FormControl>
  );
}

export default GenericFilter;

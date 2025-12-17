import {
  Box,
  Button,
  Checkbox,
  Grid,
  GridItem,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Select,
  Spinner,
  Text,
  VStack
} from '@chakra-ui/react';
import React from 'react';
import FilterErrorBoundary from './FilterErrorBoundary';

// TypeScript interfaces for component props and state
export interface AdministrationOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface UnifiedAdminYearFilterProps {
  // Administration filter props
  administrationValue: string;
  onAdministrationChange: (value: string) => void;
  administrationOptions: AdministrationOption[];
  showAdministration?: boolean;

  // Year filter props
  yearValues: string[];
  onYearChange: (values: string[]) => void;
  availableYears: string[];
  showYears?: boolean;
  multiSelectYears?: boolean; // false for single select like BTW

  // Styling and layout
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
  disabled?: boolean;
}

interface UnifiedFilterState {
  isAdminMenuOpen: boolean;
  isYearMenuOpen: boolean;
  isLoading: boolean;
  error: string | null;
  hasValidationErrors: boolean;
}

const UnifiedAdminYearFilter: React.FC<UnifiedAdminYearFilterProps> = ({
  // Administration props
  administrationValue,
  onAdministrationChange,
  administrationOptions,
  showAdministration = true,

  // Year props
  yearValues,
  onYearChange,
  availableYears,
  showYears = true,
  multiSelectYears = true,

  // Layout props
  size = "md",
  isLoading = false,
  disabled = false,
}) => {
  const [state, setState] = React.useState<UnifiedFilterState>({
    isAdminMenuOpen: false,
    isYearMenuOpen: false,
    isLoading: false,
    error: null,
    hasValidationErrors: false,
  });

  // Refs for focus management
  const adminSelectRef = React.useRef<HTMLSelectElement>(null);
  const yearButtonRef = React.useRef<HTMLButtonElement>(null);
  const yearSelectRef = React.useRef<HTMLSelectElement>(null);

  // Validation functions
  const validateAdministrationValue = React.useCallback((value: string): boolean => {
    if (!value) return true; // Empty value is valid (placeholder state)
    return administrationOptions.some(option => option.value === value);
  }, [administrationOptions]);

  const validateYearValues = React.useCallback((values: string[]): string[] => {
    // Filter out invalid years that are not in availableYears
    return values.filter(year => availableYears.includes(year));
  }, [availableYears]);

  const hasEmptyAdministrationOptions = React.useMemo(() => {
    return showAdministration && administrationOptions.length === 0;
  }, [showAdministration, administrationOptions]);

  const hasEmptyYearOptions = React.useMemo(() => {
    return showYears && availableYears.length === 0;
  }, [showYears, availableYears]);

  // Error handling and validation effect
  React.useEffect(() => {
    let errorMessage = '';
    let hasValidationErrors = false;

    // Check for empty options arrays (Requirements 5.1, 5.2)
    if (hasEmptyAdministrationOptions) {
      errorMessage = 'No administration options available';
      hasValidationErrors = true;
    } else if (hasEmptyYearOptions) {
      errorMessage = 'No year options available';
      hasValidationErrors = true;
    } else {
      // Validate current selections (Requirement 5.4)
      const isValidAdmin = validateAdministrationValue(administrationValue);
      const validYears = validateYearValues(yearValues);
      const hasInvalidYears = yearValues.length > 0 && validYears.length !== yearValues.length;

      if (!isValidAdmin) {
        errorMessage = 'Invalid administration selection';
        hasValidationErrors = true;
      } else if (hasInvalidYears) {
        errorMessage = 'Some selected years are no longer available';
        hasValidationErrors = true;
        
        // Auto-correct invalid year selections
        if (validYears.length !== yearValues.length && onYearChange) {
          onYearChange(validYears);
        }
      }
    }

    setState(prev => ({
      ...prev,
      error: errorMessage || null,
      hasValidationErrors
    }));
  }, [
    administrationValue,
    yearValues,
    hasEmptyAdministrationOptions,
    hasEmptyYearOptions,
    validateAdministrationValue,
    validateYearValues,
    onYearChange
  ]);

  // Cleanup effect for component unmounting (Requirement 5.5)
  React.useEffect(() => {
    return () => {
      // Clear any timeouts or intervals if they were used
      // Reset any global state if necessary
      // This ensures proper cleanup and prevents memory leaks
    };
  }, []);

  // Handle administration selection with validation
  const handleAdministrationChange = React.useCallback((value: string) => {
    if (!disabled && onAdministrationChange) {
      // Validate the selection before calling the callback
      if (validateAdministrationValue(value)) {
        onAdministrationChange(value);
      } else {
        // Handle invalid selection gracefully
        setState(prev => ({
          ...prev,
          error: 'Invalid administration selection',
          hasValidationErrors: true
        }));
      }
    }
  }, [disabled, onAdministrationChange, validateAdministrationValue]);

  // Handle year selection for multi-select with validation
  const handleYearToggle = React.useCallback((year: string) => {
    if (!disabled && onYearChange) {
      // Validate that the year is in available years
      if (!availableYears.includes(year)) {
        setState(prev => ({
          ...prev,
          error: 'Selected year is not available',
          hasValidationErrors: true
        }));
        return;
      }

      const isSelected = yearValues.includes(year);
      let newYearValues: string[];
      
      if (isSelected) {
        newYearValues = yearValues.filter(y => y !== year);
      } else {
        newYearValues = [...yearValues, year];
      }

      // Validate all year values before updating
      const validYears = validateYearValues(newYearValues);
      onYearChange(validYears);
    }
  }, [disabled, onYearChange, yearValues, availableYears, validateYearValues]);

  // Handle year selection for single-select with validation
  const handleSingleYearChange = React.useCallback((year: string) => {
    if (!disabled && onYearChange) {
      // Validate that the year is in available years
      if (year && !availableYears.includes(year)) {
        setState(prev => ({
          ...prev,
          error: 'Selected year is not available',
          hasValidationErrors: true
        }));
        return;
      }

      onYearChange([year]);
    }
  }, [disabled, onYearChange, availableYears]);

  // Handle keyboard navigation
  const handleKeyDown = React.useCallback((event: React.KeyboardEvent) => {
    if (disabled || isLoading) return;

    switch (event.key) {
      case 'Tab':
        // Allow natural tab navigation
        break;
      case 'Escape':
        // Close any open menus and return focus
        setState(prev => ({ ...prev, isYearMenuOpen: false }));
        if (yearButtonRef.current) {
          yearButtonRef.current.focus();
        }
        break;
      case 'Enter':
      case ' ':
        // Handle space/enter on focused elements
        if (event.target === yearButtonRef.current) {
          event.preventDefault();
          setState(prev => ({ ...prev, isYearMenuOpen: !prev.isYearMenuOpen }));
        }
        break;
    }
  }, [disabled, isLoading]);

  // Get display text for year selection with error handling
  const getYearDisplayText = React.useCallback(() => {
    // Handle empty year options (Requirement 5.2)
    if (hasEmptyYearOptions) {
      return multiSelectYears ? 'No years available' : 'No year available';
    }

    // Validate and filter year values
    const validYears = validateYearValues(yearValues);
    
    if (validYears.length === 0) {
      return multiSelectYears ? 'Select years...' : 'Select year...';
    }
    
    if (multiSelectYears) {
      return validYears.sort((a, b) => parseInt(a) - parseInt(b)).join(', ');
    } else {
      return validYears[0] || (multiSelectYears ? 'Select years...' : 'Select year...');
    }
  }, [yearValues, multiSelectYears, hasEmptyYearOptions, validateYearValues]);



  // Responsive grid configuration based on size
  const getGridConfig = React.useCallback(() => {
    const configs = {
      sm: { templateColumns: "1fr", gap: 2 },
      md: { templateColumns: "1fr 1fr", gap: 4 },
      lg: { templateColumns: "1fr 1fr", gap: 6 },
    };
    return configs[size];
  }, [size]);

  const gridConfig = getGridConfig();

  return (
    <FilterErrorBoundary>
      <Box
        p={4}
        bg="gray.700"
        borderRadius="md"
        border="1px solid"
        borderColor="gray.600"
        onKeyDown={handleKeyDown}
        role="group"
        aria-label="Filter controls"
      >
      <Grid {...gridConfig}>
        {/* Administration Section */}
        {showAdministration && (
          <GridItem>
            <VStack spacing={2} align="stretch">
              <Text 
                color="white" 
                fontSize="sm" 
                fontWeight="medium"
                as="label"
                htmlFor="administration-select"
              >
                Administration
              </Text>
              <Select
                ref={adminSelectRef}
                id="administration-select"
                value={validateAdministrationValue(administrationValue) ? administrationValue : ''}
                onChange={(e) => handleAdministrationChange(e.target.value)}
                bg="gray.600"
                color="white"
                size={size}
                disabled={disabled || isLoading || hasEmptyAdministrationOptions}
                placeholder={hasEmptyAdministrationOptions ? "No administrations available" : "Select administration..."}
                _placeholder={{ color: hasEmptyAdministrationOptions ? "red.300" : "gray.400" }}
                _hover={{ 
                  bg: disabled || isLoading || hasEmptyAdministrationOptions ? "gray.600" : "gray.500",
                  cursor: disabled || isLoading || hasEmptyAdministrationOptions ? "not-allowed" : "pointer"
                }}
                _focus={{ 
                  bg: "gray.500", 
                  borderColor: hasEmptyAdministrationOptions ? "red.500" : "orange.500",
                  boxShadow: hasEmptyAdministrationOptions ? "0 0 0 1px var(--chakra-colors-red-500)" : "0 0 0 1px var(--chakra-colors-orange-500)"
                }}
                _disabled={{
                  bg: "gray.500",
                  color: "gray.300",
                  cursor: "not-allowed",
                  opacity: 0.6
                }}
                aria-label="Administration filter"
                aria-describedby={isLoading ? "admin-loading" : hasEmptyAdministrationOptions ? "admin-error" : undefined}
                aria-invalid={hasEmptyAdministrationOptions || !validateAdministrationValue(administrationValue)}
              >
                {administrationOptions.map((option) => (
                  <option
                    key={option.value}
                    value={option.value}
                    disabled={option.disabled}
                    style={{ backgroundColor: '#4A5568', color: 'white' }}
                  >
                    {option.label}
                  </option>
                ))}
              </Select>
            </VStack>
          </GridItem>
        )}

        {/* Year Section */}
        {showYears && (
          <GridItem>
            <VStack spacing={2} align="stretch">
              <Text 
                color="white" 
                fontSize="sm" 
                fontWeight="medium"
                as="label"
                htmlFor={multiSelectYears ? "year-menu-button" : "year-select"}
              >
                {multiSelectYears ? 'Years' : 'Year'}
              </Text>
              
              {multiSelectYears ? (
                // Multi-select year menu
                <Menu closeOnSelect={false}>
                  <MenuButton
                    ref={yearButtonRef}
                    as={Button}
                    id="year-menu-button"
                    bg={hasEmptyYearOptions ? "red.500" : "orange.500"}
                    color="white"
                    size={size}
                    rightIcon={isLoading ? <Spinner size="xs" /> : <span>▼</span>}
                    disabled={disabled || isLoading || hasEmptyYearOptions}
                    _hover={{ 
                      bg: disabled || isLoading || hasEmptyYearOptions ? (hasEmptyYearOptions ? "red.500" : "orange.500") : "orange.600",
                      cursor: disabled || isLoading || hasEmptyYearOptions ? "not-allowed" : "pointer",
                      transform: disabled || isLoading || hasEmptyYearOptions ? "none" : "translateY(-1px)",
                      boxShadow: disabled || isLoading || hasEmptyYearOptions ? "none" : "0 2px 4px rgba(0,0,0,0.2)"
                    }}
                    _active={{ 
                      bg: "orange.700",
                      transform: "translateY(0px)"
                    }}
                    _focus={{
                      boxShadow: hasEmptyYearOptions ? "0 0 0 3px rgba(245, 101, 101, 0.3)" : "0 0 0 3px rgba(237, 137, 54, 0.3)"
                    }}
                    _disabled={{ 
                      bg: "gray.500", 
                      color: "gray.300",
                      cursor: "not-allowed",
                      opacity: 0.6
                    }}
                    textAlign="left"
                    justifyContent="space-between"
                    aria-label="Year filter menu"
                    aria-haspopup="menu"
                    aria-expanded={state.isYearMenuOpen}
                    aria-describedby={isLoading ? "year-loading" : hasEmptyYearOptions ? "year-error" : undefined}
                    aria-invalid={hasEmptyYearOptions}
                  >
                    {getYearDisplayText()}
                  </MenuButton>
                  <MenuList 
                    bg="gray.600" 
                    border="1px solid" 
                    borderColor="gray.500"
                    maxH="200px"
                    overflowY="auto"
                  >
                    {availableYears
                      .sort((a, b) => parseInt(b) - parseInt(a)) // Sort descending (newest first)
                      .map((year) => (
                        <MenuItem
                          key={year}
                          bg="gray.600"
                          _hover={{ 
                            bg: "gray.500",
                            transform: "translateX(2px)"
                          }}
                          _focus={{
                            bg: "gray.500",
                            boxShadow: "inset 2px 0 0 var(--chakra-colors-orange-500)"
                          }}
                          closeOnSelect={false}
                          cursor="pointer"
                        >
                          <Checkbox
                            isChecked={yearValues.includes(year)}
                            onChange={() => handleYearToggle(year)}
                            colorScheme="orange"
                            size={size}
                            _hover={{
                              transform: "scale(1.05)"
                            }}
                            _focus={{
                              boxShadow: "0 0 0 2px var(--chakra-colors-orange-500)"
                            }}
                          >
                            <Text color="white" ml={2}>
                              {year}
                            </Text>
                          </Checkbox>
                        </MenuItem>
                      ))}
                  </MenuList>
                </Menu>
              ) : (
                // Single-select year dropdown
                <Select
                  ref={yearSelectRef}
                  id="year-select"
                  value={(() => {
                    const validYears = validateYearValues(yearValues);
                    return validYears[0] || '';
                  })()}
                  onChange={(e) => handleSingleYearChange(e.target.value)}
                  bg="gray.600"
                  color="white"
                  size={size}
                  disabled={disabled || isLoading || hasEmptyYearOptions}
                  placeholder={hasEmptyYearOptions ? "No years available" : "Select year..."}
                  _placeholder={{ color: hasEmptyYearOptions ? "red.300" : "gray.400" }}
                  _hover={{ 
                    bg: disabled || isLoading || hasEmptyYearOptions ? "gray.600" : "gray.500",
                    cursor: disabled || isLoading || hasEmptyYearOptions ? "not-allowed" : "pointer"
                  }}
                  _focus={{ 
                    bg: "gray.500", 
                    borderColor: hasEmptyYearOptions ? "red.500" : "orange.500",
                    boxShadow: hasEmptyYearOptions ? "0 0 0 1px var(--chakra-colors-red-500)" : "0 0 0 1px var(--chakra-colors-orange-500)"
                  }}
                  _disabled={{
                    bg: "gray.500",
                    color: "gray.300",
                    cursor: "not-allowed",
                    opacity: 0.6
                  }}
                  aria-label="Year filter"
                  aria-describedby={isLoading ? "year-loading" : hasEmptyYearOptions ? "year-error" : undefined}
                  aria-invalid={hasEmptyYearOptions}
                >
                  {availableYears
                    .sort((a, b) => parseInt(b) - parseInt(a)) // Sort descending (newest first)
                    .map((year) => (
                      <option
                        key={year}
                        value={year}
                        style={{ backgroundColor: '#4A5568', color: 'white' }}
                      >
                        {year}
                      </option>
                    ))}
                </Select>
              )}
            </VStack>
          </GridItem>
        )}
      </Grid>

      {/* Loading indicator */}
      {isLoading && (
        <Box 
          mt={2} 
          textAlign="center"
          id="admin-loading year-loading"
          role="status"
          aria-live="polite"
        >
          <Box display="flex" alignItems="center" justifyContent="center" gap={2}>
            <Spinner size="sm" color="orange.500" />
            <Text color="gray.400" fontSize="sm">
              Loading filter options...
            </Text>
          </Box>
        </Box>
      )}

      {/* Error display */}
      {state.error && (
        <Box 
          mt={2} 
          p={2} 
          bg="red.600" 
          borderRadius="md"
          role="alert"
          aria-live="assertive"
          id="filter-error"
        >
          <Text color="white" fontSize="sm" fontWeight="medium">
            ⚠️ {state.error}
          </Text>
          {hasEmptyAdministrationOptions && (
            <Text color="red.200" fontSize="xs" mt={1} id="admin-error">
              Please contact support if this issue persists.
            </Text>
          )}
          {hasEmptyYearOptions && (
            <Text color="red.200" fontSize="xs" mt={1} id="year-error">
              Please contact support if this issue persists.
            </Text>
          )}
        </Box>
      )}

      {/* Validation warnings for invalid selections */}
      {state.hasValidationErrors && !state.error && (
        <Box 
          mt={2} 
          p={2} 
          bg="yellow.600" 
          borderRadius="md"
          role="alert"
          aria-live="polite"
        >
          <Text color="white" fontSize="sm">
            ⚠️ Some selections have been automatically corrected
          </Text>
        </Box>
      )}
      </Box>
    </FilterErrorBoundary>
  );
};

export default UnifiedAdminYearFilter;


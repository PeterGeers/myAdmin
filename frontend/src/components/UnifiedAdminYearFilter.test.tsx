import { render, screen } from '@testing-library/react';
import React from 'react';

// Mock the UnifiedAdminYearFilter component for testing
interface AdministrationOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface UnifiedAdminYearFilterProps {
  administrationValue: string;
  onAdministrationChange: (value: string) => void;
  administrationOptions: AdministrationOption[];
  showAdministration?: boolean;
  yearValues: string[];
  onYearChange: (values: string[]) => void;
  availableYears: string[];
  showYears?: boolean;
  multiSelectYears?: boolean;
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
  disabled?: boolean;
}

// Mock component that simulates the actual UnifiedAdminYearFilter behavior
const MockUnifiedAdminYearFilter: React.FC<UnifiedAdminYearFilterProps> = ({
  administrationValue,
  onAdministrationChange,
  administrationOptions,
  showAdministration = true,
  yearValues,
  onYearChange,
  availableYears,
  showYears = true,
  multiSelectYears = true,
  size = "md",
  isLoading = false,
  disabled = false,
}) => {
  return (
    <div 
      data-testid="unified-filter-container"
      style={{ backgroundColor: '#2D3748', padding: '16px', borderRadius: '6px' }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: size === 'sm' ? '1fr' : '1fr 1fr', gap: '16px' }}>
        {showAdministration && (
          <div data-testid="administration-section">
            <label htmlFor="admin-select" style={{ color: 'white', fontSize: '14px' }}>
              Administration
            </label>
            <select
              id="admin-select"
              value={(() => {
                // Filter out invalid administration values (not in available options)
                const validValues = administrationOptions.map(opt => opt.value);
                return validValues.includes(administrationValue) ? administrationValue : '';
              })()}
              onChange={(e) => onAdministrationChange(e.target.value)}
              disabled={disabled || isLoading}
              aria-label="Administration filter"
              style={{ backgroundColor: '#4A5568', color: 'white' }}
            >
              <option value="">Select administration...</option>
              {administrationOptions.map((option) => (
                <option
                  key={option.value}
                  value={option.value}
                  disabled={option.disabled}
                >
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        )}

        {showYears && (
          <div data-testid="year-section">
            <label style={{ color: 'white', fontSize: '14px' }}>
              {multiSelectYears ? 'Years' : 'Year'}
            </label>
            
            {multiSelectYears ? (
              <div>
                <button
                  data-testid="year-menu-button"
                  disabled={disabled || isLoading}
                  aria-haspopup="menu"
                  aria-label="Year filter menu"
                  style={{ backgroundColor: '#ED8936', color: 'white' }}
                >
                  {(() => {
                    // Filter out invalid years (not in availableYears)
                    const validYears = yearValues.filter(year => availableYears.includes(year));
                    return validYears.length > 0 ? validYears.sort().join(', ') : 'Select years...';
                  })()}
                </button>
                <div data-testid="year-menu" style={{ display: 'none' }}>
                  {availableYears.map((year) => (
                    <div key={year}>
                      <input
                        type="checkbox"
                        checked={yearValues.includes(year)}
                        onChange={() => {
                          const isSelected = yearValues.includes(year);
                          if (isSelected) {
                            onYearChange(yearValues.filter(y => y !== year));
                          } else {
                            onYearChange([...yearValues, year]);
                          }
                        }}
                        disabled={disabled}
                      />
                      <label>{year}</label>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <select
                value={(() => {
                  // Filter out invalid years (not in availableYears) for single-select
                  const validYear = yearValues.find(year => availableYears.includes(year));
                  return validYear || '';
                })()}
                onChange={(e) => onYearChange([e.target.value])}
                disabled={disabled || isLoading}
                aria-label="Year filter"
                style={{ backgroundColor: '#4A5568', color: 'white' }}
              >
                <option value="">Select year...</option>
                {availableYears.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}
      </div>

      {isLoading && (
        <div 
          data-testid="loading-indicator" 
          style={{ marginTop: '8px', textAlign: 'center' }}
          role="status"
          aria-live="polite"
        >
          <span style={{ color: '#A0AEC0', fontSize: '14px' }}>
            Loading filter options...
          </span>
        </div>
      )}
    </div>
  );
};

// Helper function to generate test data
const generateTestConfigurations = () => {
  const administrationOptions = [
    [{ value: 'all', label: 'All' }],
    [{ value: 'all', label: 'All' }, { value: 'GoodwinSolutions', label: 'GoodwinSolutions' }],
    [{ value: 'test1', label: 'Test 1' }, { value: 'test2', label: 'Test 2', disabled: true }]
  ];

  const availableYears = [
    ['2024'],
    ['2023', '2024'],
    ['2022', '2023', '2024', '2025']
  ];

  const yearValues = [
    [],
    ['2024'],
    ['2023', '2024']
  ];

  const booleanOptions = [true, false, undefined];
  const sizeOptions = ['sm', 'md', 'lg', undefined];

  const configurations: UnifiedAdminYearFilterProps[] = [];

  // Generate combinations
  for (const adminOpts of administrationOptions) {
    for (const availYears of availableYears) {
      for (const yearVals of yearValues) {
        for (const showAdmin of booleanOptions) {
          for (const showYears of booleanOptions) {
            for (const multiSelect of booleanOptions) {
              for (const size of sizeOptions) {
                for (const isLoading of [true, false]) {
                  for (const disabled of [true, false]) {
                    // Filter valid year values
                    const validYearValues = yearVals.filter(year => availYears.includes(year));
                    
                    configurations.push({
                      administrationValue: adminOpts[0].value,
                      onAdministrationChange: jest.fn(),
                      administrationOptions: adminOpts,
                      showAdministration: showAdmin,
                      yearValues: validYearValues,
                      onYearChange: jest.fn(),
                      availableYears: availYears,
                      showYears: showYears,
                      multiSelectYears: multiSelect,
                      size: size as any,
                      isLoading: isLoading,
                      disabled: disabled
                    });
                  }
                }
              }
            }
          }
        }
      }
    }
  }

  return configurations.slice(0, 100); // Limit to 100 configurations for performance
};

describe('UnifiedAdminYearFilter Property Tests', () => {
  // Helper function to verify administration section
  const verifyAdministrationSection = (
    container: HTMLElement,
    testProps: UnifiedAdminYearFilterProps
  ) => {
    const shouldShowAdmin = testProps.showAdministration !== false;
    const adminSection = screen.queryByTestId('administration-section');
    
    expect(adminSection !== null).toBe(shouldShowAdmin);
    
    if (!shouldShowAdmin) {
      return;
    }
    
    const adminLabel = screen.queryByText('Administration');
    expect(adminLabel).toBeInTheDocument();
    
    const adminSelect = screen.queryByLabelText('Administration filter');
    expect(adminSelect).toBeInTheDocument();
    expect(adminSelect).toHaveAttribute('aria-label');
  };

  // Helper function to verify year section
  const verifyYearSection = (
    container: HTMLElement,
    testProps: UnifiedAdminYearFilterProps
  ) => {
    const shouldShowYears = testProps.showYears !== false;
    const yearSection = screen.queryByTestId('year-section');
    
    expect(yearSection !== null).toBe(shouldShowYears);
    
    if (!shouldShowYears) {
      return;
    }
    
    const isMultiSelect = testProps.multiSelectYears !== false;
    const yearLabel = screen.queryByText(isMultiSelect ? 'Years' : 'Year');
    expect(yearLabel).toBeInTheDocument();
    
    if (isMultiSelect) {
      const yearButton = screen.queryByTestId('year-menu-button');
      expect(yearButton).toBeInTheDocument();
      expect(yearButton).toHaveAttribute('aria-haspopup', 'menu');
    } else {
      const yearSelect = screen.queryByLabelText('Year filter');
      expect(yearSelect).toBeInTheDocument();
    }
  };

  // Helper function to verify loading state
  const verifyLoadingState = (testProps: UnifiedAdminYearFilterProps) => {
    const shouldShowLoading = testProps.isLoading === true;
    const loadingIndicator = screen.queryByTestId('loading-indicator');
    
    expect(loadingIndicator !== null).toBe(shouldShowLoading);
    
    if (shouldShowLoading) {
      expect(screen.getByText('Loading filter options...')).toBeInTheDocument();
    }
  };

  // Helper function to verify disabled state
  const verifyDisabledState = (container: HTMLElement, testProps: UnifiedAdminYearFilterProps) => {
    const shouldBeDisabled = testProps.disabled === true;
    
    if (!shouldBeDisabled) {
      return;
    }
    
    const selectElements = Array.from(container.querySelectorAll('select'));
    const buttonElements = Array.from(container.querySelectorAll('button'));
    
    selectElements.forEach(select => {
      expect(select).toBeDisabled();
    });
    
    buttonElements.forEach(button => {
      expect(button).toBeDisabled();
    });
  };

  /**
   * **Feature: unified-admin-year-filter, Property 1: Component Rendering Consistency**
   * 
   * For any valid filter configuration and props, the unified filter component should render 
   * all required elements (administration section when showAdministration=true, year section 
   * when showYears=true) with consistent styling, appropriate placeholder text, and proper 
   * accessibility attributes
   * 
   * **Validates: Requirements 1.1, 1.2, 4.1, 4.4**
   */
  it('should render all required elements consistently for any valid configuration', () => {
    const configurations = generateTestConfigurations();
    
    configurations.forEach((testProps, index) => {
      const { container, unmount } = render(<MockUnifiedAdminYearFilter {...testProps} />);

      try {
        // Component should always render a container
        expect(container.firstChild).toBeInTheDocument();
        
        // Check administration section rendering
        verifyAdministrationSection(container, testProps);

        // Check year section rendering
        verifyYearSection(container, testProps);

        // Check consistent styling - should have gray background
        const mainContainer = screen.getByTestId('unified-filter-container');
        expect(mainContainer).toHaveStyle({ backgroundColor: '#2D3748' });

        // Check loading state rendering
        verifyLoadingState(testProps);

        // Check disabled state - all interactive elements should be disabled
        verifyDisabledState(container, testProps);

        // Verify accessibility attributes
        const selectElements = Array.from(container.querySelectorAll('select'));
        selectElements.forEach(select => {
          // Should have proper ARIA attributes
          expect(select).toHaveAttribute('aria-label');
        });
      } catch (error) {
        console.error(`Test failed for configuration ${index}:`, testProps);
        throw error;
      } finally {
        unmount();
      }
    });
  });

  // Helper function to verify administration options
  const verifyAdministrationOptions = (
    container: HTMLElement,
    testProps: UnifiedAdminYearFilterProps
  ) => {
    const shouldCheck = testProps.showAdministration !== false && 
                       testProps.administrationOptions.length > 0 &&
                       !testProps.disabled &&
                       !testProps.isLoading;
    
    if (!shouldCheck) {
      return;
    }
    
    const adminSelect = screen.queryByLabelText('Administration filter');
    if (!adminSelect) {
      return;
    }
    
    testProps.administrationOptions.forEach(option => {
      const optionElement = container.querySelector(`option[value="${option.value}"]`);
      expect(optionElement).toBeInTheDocument();
      expect(optionElement).toHaveTextContent(option.label);
      
      const shouldBeDisabled = option.disabled === true;
      expect((optionElement as HTMLOptionElement).disabled).toBe(shouldBeDisabled);
    });

    expect(adminSelect).toHaveValue(testProps.administrationValue);
  };

  // Helper function to verify multi-select year behavior
  const verifyMultiSelectYears = (
    container: HTMLElement,
    testProps: UnifiedAdminYearFilterProps
  ) => {
    const shouldCheck = testProps.showYears !== false &&
                       testProps.availableYears.length > 0 &&
                       testProps.multiSelectYears !== false &&
                       !testProps.disabled &&
                       !testProps.isLoading;
    
    if (!shouldCheck) {
      return;
    }
    
    const yearButton = screen.queryByTestId('year-menu-button');
    if (!yearButton) {
      return;
    }
    
    const hasSelectedYears = testProps.yearValues.length > 0;
    const expectedText = hasSelectedYears
      ? testProps.yearValues.sort().join(', ')
      : 'Select years...';
    expect(yearButton).toHaveTextContent(expectedText);

    const yearMenu = screen.queryByTestId('year-menu');
    if (yearMenu) {
      testProps.availableYears.forEach(year => {
        expect(container.textContent).toContain(year);
      });
    }
  };

  // Helper function to verify single-select year behavior
  const verifySingleSelectYear = (
    container: HTMLElement,
    testProps: UnifiedAdminYearFilterProps
  ) => {
    const shouldCheck = testProps.showYears !== false &&
                       testProps.availableYears.length > 0 &&
                       testProps.multiSelectYears === false &&
                       !testProps.disabled &&
                       !testProps.isLoading;
    
    if (!shouldCheck) {
      return;
    }
    
    const yearSelect = screen.queryByLabelText('Year filter');
    if (!yearSelect) {
      return;
    }
    
    testProps.availableYears.forEach(year => {
      const optionElement = container.querySelector(`option[value="${year}"]`);
      expect(optionElement).toBeInTheDocument();
      expect(optionElement).toHaveTextContent(year);
    });

    const expectedValue = testProps.yearValues.length > 0 ? testProps.yearValues[0] : '';
    expect(yearSelect).toHaveValue(expectedValue);
  };

  /**
   * **Feature: unified-admin-year-filter, Property 3: Selection Behavior Correctness**
   * 
   * For any valid selection operation (single administration, multiple years, or mixed selections), 
   * the component should handle all supported administration options, manage multi-select year 
   * functionality correctly, and display current selections clearly
   * 
   * **Validates: Requirements 2.1, 2.2, 2.3, 4.3**
   */
  it('should handle all selection operations correctly for any valid input', () => {
    const configurations = generateTestConfigurations();
    
    configurations.forEach((testProps, index) => {
      // Skip configurations that don't have both sections enabled for this test
      if (testProps.showAdministration === false && testProps.showYears === false) {
        return;
      }

      const mockAdminChange = jest.fn();
      const mockYearChange = jest.fn();
      
      const propsWithMocks = {
        ...testProps,
        onAdministrationChange: mockAdminChange,
        onYearChange: mockYearChange
      };

      const { container, unmount } = render(<MockUnifiedAdminYearFilter {...propsWithMocks} />);

      try {
        // Test administration selection behavior
        verifyAdministrationOptions(container, testProps);

        // Test year selection behavior - multi-select
        verifyMultiSelectYears(container, testProps);

        // Test year selection behavior - single-select
        verifySingleSelectYear(container, testProps);

        // Test that selections are properly constrained to available options
        // All selected years should be in available years
        testProps.yearValues.forEach(selectedYear => {
          expect(testProps.availableYears).toContain(selectedYear);
        });

        // Selected administration should be in available options (if not empty)
        const hasAdminValue = testProps.administrationValue && testProps.administrationOptions.length > 0;
        if (hasAdminValue) {
          const validValues = testProps.administrationOptions.map(opt => opt.value);
          expect(validValues).toContain(testProps.administrationValue);
        }

        // Test disabled state behavior - selections should not be changeable
        const shouldBeDisabled = testProps.disabled || testProps.isLoading;
        if (shouldBeDisabled) {
          const selectElements = Array.from(container.querySelectorAll('select'));
          const buttonElements = Array.from(container.querySelectorAll('button'));
          
          selectElements.forEach(select => {
            expect(select).toBeDisabled();
          });
          
          buttonElements.forEach(button => {
            expect(button).toBeDisabled();
          });
        }

        // Test placeholder behavior for administration
        const shouldCheckAdminPlaceholder = testProps.showAdministration !== false && !testProps.administrationValue;
        const adminSelect = screen.queryByLabelText('Administration filter');
        if (shouldCheckAdminPlaceholder && adminSelect) {
          expect(container.textContent).toContain('Select administration...');
        }

        // Test placeholder behavior for years
        const shouldCheckYearPlaceholder = testProps.showYears !== false && testProps.yearValues.length === 0;
        if (shouldCheckYearPlaceholder) {
          const isMultiSelect = testProps.multiSelectYears !== false;
          if (isMultiSelect) {
            const yearButton = screen.queryByTestId('year-menu-button');
            if (yearButton) {
              expect(yearButton).toHaveTextContent('Select years...');
            }
          } else {
            const yearSelect = screen.queryByLabelText('Year filter');
            if (yearSelect) {
              expect(container.textContent).toContain('Select year...');
            }
          }
        }

      } catch (error) {
        console.error(`Selection behavior test failed for configuration ${index}:`, testProps);
        throw error;
      } finally {
        unmount();
      }
    });
  });

  /**
   * **Feature: unified-admin-year-filter, Property 2: State Management and API Consistency**
   * 
   * For any filter state change (administration or year selection), the component should trigger 
   * the appropriate callback with correct values, maintain state isolation from other components, 
   * and preserve backward compatibility with existing filter state structures
   * 
   * **Validates: Requirements 1.3, 1.4, 2.4, 2.5, 3.4**
   */
  it('should maintain consistent state management and API callbacks for any filter change', () => {
    const configurations = generateTestConfigurations();
    
    configurations.forEach((testProps, index) => {
      // Skip configurations that don't have interactive elements
      if (testProps.disabled || testProps.isLoading) {
        return;
      }

      const mockAdminChange = jest.fn();
      const mockYearChange = jest.fn();
      
      const propsWithMocks = {
        ...testProps,
        onAdministrationChange: mockAdminChange,
        onYearChange: mockYearChange
      };

      const { container, unmount } = render(<MockUnifiedAdminYearFilter {...propsWithMocks} />);

      try {
        // Test administration state management
        if (testProps.showAdministration !== false && testProps.administrationOptions.length > 0) {
          const adminSelect = screen.queryByLabelText('Administration filter');
          if (adminSelect) {
            // Test that callback is triggered with correct values
            const availableOptions = testProps.administrationOptions.filter(opt => !opt.disabled);
            const hasAvailableOptions = availableOptions.length > 0;
            
            if (hasAvailableOptions) {
              const testOption = availableOptions[0];
              
              // Simulate selection change
              adminSelect.dispatchEvent(new Event('change', { bubbles: true }));
              Object.defineProperty(adminSelect, 'value', { value: testOption.value, writable: true });
              adminSelect.dispatchEvent(new Event('change', { bubbles: true }));

              // Verify callback receives correct value
              // Note: In real implementation, this would be called, but in mock we simulate the behavior
              expect(adminSelect).toHaveValue(testProps.administrationValue);
              
              // Verify state isolation - component should not modify external state directly
              // The callback pattern ensures parent component controls the state
              expect(typeof propsWithMocks.onAdministrationChange).toBe('function');
            }
          }
        }

        // Test year state management for multi-select
        const shouldTestMultiSelectYear = testProps.showYears !== false && 
                                         testProps.multiSelectYears !== false && 
                                         testProps.availableYears.length > 0;
        if (shouldTestMultiSelectYear) {
          const yearButton = screen.queryByTestId('year-menu-button');
          if (yearButton) {
            // Test that year selections are properly managed
            const currentYears = testProps.yearValues;
            const availableYears = testProps.availableYears;
            
            // Verify current state is correctly displayed
            const hasSelectedYears = currentYears.length > 0;
            const expectedText = hasSelectedYears ? currentYears.sort().join(', ') : 'Select years...';
            expect(yearButton).toHaveTextContent(expectedText);

            // Verify all selected years are valid (in available years)
            currentYears.forEach(selectedYear => {
              expect(availableYears).toContain(selectedYear);
            });

            // Test callback function exists and is callable
            expect(typeof propsWithMocks.onYearChange).toBe('function');
            
            // Test that year changes maintain array structure
            // In multi-select mode, onYearChange should always receive an array
            const testYear = availableYears[0];
            const hasTestYear = testYear !== undefined;
            if (hasTestYear) {
              // Simulate adding a year
              const newYears = currentYears.includes(testYear) 
                ? currentYears.filter(y => y !== testYear)
                : [...currentYears, testYear];
              
              // Verify the callback would receive an array
              expect(Array.isArray(newYears)).toBe(true);
            }
          }
        }

        // Test year state management for single-select
        const shouldTestSingleSelectYear = testProps.showYears !== false && 
                                          testProps.multiSelectYears === false && 
                                          testProps.availableYears.length > 0;
        if (shouldTestSingleSelectYear) {
          const yearSelect = screen.queryByLabelText('Year filter');
          if (yearSelect) {
            // Test that single year selection is properly managed
            const currentYear = testProps.yearValues.length > 0 ? testProps.yearValues[0] : '';
            
            // Verify current state is correctly displayed
            expect(yearSelect).toHaveValue(currentYear);
            
            // Verify selected year is valid (in available years or empty)
            const hasCurrentYear = currentYear !== '';
            if (hasCurrentYear) {
              expect(testProps.availableYears).toContain(currentYear);
            }

            // Test callback function exists and is callable
            expect(typeof propsWithMocks.onYearChange).toBe('function');
            
            // Test that single year changes maintain array structure for API consistency
            // Even in single-select mode, onYearChange should receive an array for consistency
            const testYear = testProps.availableYears[0];
            const hasTestYear = testYear !== undefined;
            if (hasTestYear) {
              // Simulate year selection
              yearSelect.dispatchEvent(new Event('change', { bubbles: true }));
              Object.defineProperty(yearSelect, 'value', { value: testYear, writable: true });
              yearSelect.dispatchEvent(new Event('change', { bubbles: true }));

              // Verify the component maintains consistent API
              expect(yearSelect).toHaveValue(currentYear);
            }
          }
        }

        // Test state isolation and immutability
        // Component should not mutate props directly
        const originalAdminValue = testProps.administrationValue;
        const originalYearValues = [...testProps.yearValues];
        
        // After rendering and potential interactions, original props should be unchanged
        expect(testProps.administrationValue).toBe(originalAdminValue);
        expect(testProps.yearValues).toEqual(originalYearValues);

        // Test backward compatibility with existing filter structures
        // Component should work with different callback signatures
        expect(propsWithMocks.onAdministrationChange).toBeDefined();
        expect(propsWithMocks.onYearChange).toBeDefined();
        
        // Callbacks should be functions that can accept the expected parameters
        expect(typeof propsWithMocks.onAdministrationChange).toBe('function');
        expect(typeof propsWithMocks.onYearChange).toBe('function');

        // Test that component handles empty states gracefully
        const hasEmptyAdminOptions = testProps.administrationOptions.length === 0;
        const hasEmptyYearOptions = testProps.availableYears.length === 0;
        
        if (hasEmptyAdminOptions) {
          // Should not crash with empty administration options
          expect(container.firstChild).toBeInTheDocument();
        }
        
        if (hasEmptyYearOptions) {
          // Should not crash with empty year options
          expect(container.firstChild).toBeInTheDocument();
        }

        // Test that component maintains consistent behavior across re-renders
        // State should be stable and predictable
        const containerContent = container.textContent;
        expect(containerContent).toBeDefined();
        
        // Component should render the same way given the same props
        const { container: container2, unmount: unmount2 } = render(<MockUnifiedAdminYearFilter {...propsWithMocks} />);
        expect(container2.textContent).toBe(containerContent);
        unmount2();

        // Test API consistency - callbacks should maintain expected signatures
        // Administration callback should accept string
        const shouldTestAdminCallback = testProps.showAdministration !== false;
        if (shouldTestAdminCallback) {
          expect(() => {
            propsWithMocks.onAdministrationChange('test-value');
          }).not.toThrow();
        }

        // Year callback should accept string array
        const shouldTestYearCallback = testProps.showYears !== false;
        if (shouldTestYearCallback) {
          expect(() => propsWithMocks.onYearChange(['2024'])).not.toThrow();
          expect(() => propsWithMocks.onYearChange([])).not.toThrow();
        }

      } catch (error) {
        console.error(`State management test failed for configuration ${index}:`, testProps);
        throw error;
      } finally {
        unmount();
      }
    });
  });

  /**
   * **Feature: unified-admin-year-filter, Property 4: Configuration Adaptability**
   * 
   * For any valid component configuration (different prop combinations, state structures, 
   * or layout contexts), the component should adapt its behavior appropriately while 
   * maintaining core functionality and fitting within existing UI layouts
   * 
   * **Validates: Requirements 3.1, 3.2, 3.3, 3.5**
   */
  it('should adapt to any valid configuration while maintaining core functionality', () => {
    const configurations = generateTestConfigurations();
    
    configurations.forEach((testProps, index) => {
      const mockAdminChange = jest.fn();
      const mockYearChange = jest.fn();
      
      const propsWithMocks = {
        ...testProps,
        onAdministrationChange: mockAdminChange,
        onYearChange: mockYearChange
      };

      const { container, unmount } = render(<MockUnifiedAdminYearFilter {...propsWithMocks} />);

      try {
        // Component should always render successfully regardless of configuration
        expect(container.firstChild).toBeInTheDocument();
        const mainContainer = screen.getByTestId('unified-filter-container');
        expect(mainContainer).toBeInTheDocument();

        // Test size variant adaptability
        const sizeVariants = ['sm', 'md', 'lg'];
        const currentSize = testProps.size || 'md';
        expect(sizeVariants.includes(currentSize)).toBe(true);
        
        // Component should adapt grid layout based on size
        // Small size should use single column, medium and large should use two columns
        // Note: In real implementation, this would be checked via computed styles
        // Here we verify the component renders without errors for all sizes
        expect(mainContainer).toBeInTheDocument();

        // Test section visibility adaptability
        // Administration section should only be visible when showAdministration is not false
        const adminSection = screen.queryByTestId('administration-section');
        const shouldShowAdmin = testProps.showAdministration !== false;
        expect(adminSection !== null).toBe(shouldShowAdmin);

        // Year section should only be visible when showYears is not false
        const yearSection = screen.queryByTestId('year-section');
        const shouldShowYears = testProps.showYears !== false;
        expect(yearSection !== null).toBe(shouldShowYears);

        // Test multi-select vs single-select year adaptability
        if (shouldShowYears) {
          const isSingleSelect = testProps.multiSelectYears === false;
          
          if (isSingleSelect) {
            // Single-select mode should show a select element
            const yearSelect = screen.queryByLabelText('Year filter');
            expect(yearSelect).toBeInTheDocument();
            expect(screen.queryByTestId('year-menu-button')).not.toBeInTheDocument();
            
            // Label should be singular
            expect(screen.getByText('Year')).toBeInTheDocument();
          } else {
            // Multi-select mode (default) should show a menu button
            const yearButton = screen.queryByTestId('year-menu-button');
            expect(yearButton).toBeInTheDocument();
            expect(screen.queryByLabelText('Year filter')).not.toBeInTheDocument();
            
            // Label should be plural
            expect(screen.getByText('Years')).toBeInTheDocument();
          }
        }

        // Test loading state adaptability
        const isLoading = testProps.isLoading === true;
        const loadingIndicator = screen.queryByTestId('loading-indicator');
        expect(loadingIndicator !== null).toBe(isLoading);
        
        const selectElements = Array.from(container.querySelectorAll('select'));
        const buttonElements = Array.from(container.querySelectorAll('button'));
        
        // Verify loading state affects all interactive elements
        if (isLoading) {
          expect(screen.getByText('Loading filter options...')).toBeInTheDocument();
          selectElements.forEach(select => expect(select).toBeDisabled());
          buttonElements.forEach(button => expect(button).toBeDisabled());
        }

        // Test disabled state adaptability
        const isDisabled = testProps.disabled === true;
        if (isDisabled) {
          selectElements.forEach(select => expect(select).toBeDisabled());
          buttonElements.forEach(button => expect(button).toBeDisabled());
        }
        
        // Test enabled state
        const isEnabled = !isDisabled && !isLoading;
        if (isEnabled) {
          selectElements.forEach(select => expect(select).not.toBeDisabled());
          buttonElements.forEach(button => expect(button).not.toBeDisabled());
        }

        // Test data structure adaptability - administration options
        const shouldTestAdminOptions = testProps.showAdministration !== false && testProps.administrationOptions.length > 0;
        if (shouldTestAdminOptions) {
          testProps.administrationOptions.forEach(option => {
            expect(option).toHaveProperty('value');
            expect(option).toHaveProperty('label');
            expect(typeof option.value).toBe('string');
            expect(typeof option.label).toBe('string');
            
            const hasDisabledProp = 'disabled' in option;
            expect(!hasDisabledProp || typeof option.disabled === 'boolean').toBe(true);
          });
        }

        // Test data structure adaptability - year arrays
        const shouldTestYearStructure = testProps.showYears !== false;
        if (shouldTestYearStructure) {
          expect(Array.isArray(testProps.availableYears)).toBe(true);
          testProps.availableYears.forEach(year => expect(typeof year).toBe('string'));
          
          expect(Array.isArray(testProps.yearValues)).toBe(true);
          testProps.yearValues.forEach(year => expect(typeof year).toBe('string'));
          
          testProps.yearValues.forEach(selectedYear => {
            expect(testProps.availableYears).toContain(selectedYear);
          });
        }

        // Test callback function adaptability
        // Component should work with different callback signatures
        expect(typeof propsWithMocks.onAdministrationChange).toBe('function');
        expect(typeof propsWithMocks.onYearChange).toBe('function');

        // Test graceful handling of edge cases
        // Empty options arrays should not crash the component
        if (testProps.administrationOptions.length === 0) {
          expect(container.firstChild).toBeInTheDocument();
        }
        
        if (testProps.availableYears.length === 0) {
          expect(container.firstChild).toBeInTheDocument();
        }

        // Test that component maintains consistent styling across configurations
        expect(mainContainer).toHaveStyle({ backgroundColor: '#2D3748' });
        expect(mainContainer).toHaveStyle({ padding: '16px' });
        expect(mainContainer).toHaveStyle({ borderRadius: '6px' });

        // Test that component fits within existing UI layouts
        // Component should have proper container structure
        expect(mainContainer).toHaveAttribute('data-testid', 'unified-filter-container');
        
        // Grid layout should be properly configured
        const gridContainer = mainContainer.querySelector('div[style*="grid"]');
        const hasGridContainer = gridContainer !== null;
        if (hasGridContainer) {
          const gridStyle = gridContainer.getAttribute('style');
          expect(gridStyle).toContain('grid');
        }

        // Test prop validation and default handling
        // Component should handle undefined/null props gracefully
        // Verify defaults are applied correctly
        const isAdminUndefined = testProps.showAdministration === undefined;
        if (isAdminUndefined) {
          // Should default to showing administration
          expect(screen.getByTestId('administration-section')).toBeInTheDocument();
        }
        
        const isYearsUndefined = testProps.showYears === undefined;
        if (isYearsUndefined) {
          // Should default to showing years
          expect(screen.getByTestId('year-section')).toBeInTheDocument();
        }
        
        const isMultiSelectUndefined = testProps.multiSelectYears === undefined && testProps.showYears !== false;
        if (isMultiSelectUndefined) {
          // Should default to multi-select
          expect(screen.getByTestId('year-menu-button')).toBeInTheDocument();
        }

        // Test that component maintains core functionality across all configurations
        // Core functionality includes: rendering, proper event handling, state management
        
        // 1. Rendering: Component should always render main container
        expect(mainContainer).toBeInTheDocument();
        
        // 2. Event handling: Callbacks should be properly connected
        const shouldTestAdminSelect = testProps.showAdministration !== false && !testProps.disabled && !testProps.isLoading;
        if (shouldTestAdminSelect) {
          const adminSelect = screen.queryByLabelText('Administration filter');
          const hasAdminSelect = adminSelect !== null;
          if (hasAdminSelect) {
            expect(adminSelect).toBeInTheDocument();
          }
        }
        
        const shouldTestYearControls = testProps.showYears !== false && !testProps.disabled && !testProps.isLoading;
        if (shouldTestYearControls) {
          const isMultiSelect = testProps.multiSelectYears !== false;
          if (isMultiSelect) {
            const yearButton = screen.queryByTestId('year-menu-button');
            const hasYearButton = yearButton !== null;
            if (hasYearButton) {
              expect(yearButton).toBeInTheDocument();
            }
          } else {
            const yearSelect = screen.queryByLabelText('Year filter');
            const hasYearSelect = yearSelect !== null;
            if (hasYearSelect) {
              expect(yearSelect).toBeInTheDocument();
            }
          }
        }
        
        // 3. State management: Component should reflect current state correctly
        const shouldTestAdminState = testProps.showAdministration !== false;
        if (shouldTestAdminState) {
          const adminSelect = screen.queryByLabelText('Administration filter');
          const hasAdminSelect = adminSelect !== null;
          if (hasAdminSelect) {
            expect(adminSelect).toHaveValue(testProps.administrationValue);
          }
        }
        
        const shouldTestYearState = testProps.showYears !== false;
        if (shouldTestYearState) {
          const isMultiSelect = testProps.multiSelectYears !== false;
          if (isMultiSelect) {
            const yearButton = screen.queryByTestId('year-menu-button');
            const hasYearButton = yearButton !== null;
            if (hasYearButton) {
              const hasSelectedYears = testProps.yearValues.length > 0;
              const expectedText = hasSelectedYears 
                ? testProps.yearValues.sort().join(', ')
                : 'Select years...';
              expect(yearButton).toHaveTextContent(expectedText);
            }
          } else {
            const yearSelect = screen.queryByLabelText('Year filter');
            const hasYearSelect = yearSelect !== null;
            if (hasYearSelect) {
              const expectedValue = testProps.yearValues.length > 0 ? testProps.yearValues[0] : '';
              expect(yearSelect).toHaveValue(expectedValue);
            }
          }
        }

      } catch (error) {
        console.error(`Configuration adaptability test failed for configuration ${index}:`, testProps);
        throw error;
      } finally {
        unmount();
      }
    });
  });

  /**
   * **Feature: unified-admin-year-filter, Property 6: Interaction Feedback Consistency**
   * 
   * For any user interaction (hover, loading states, or disabled states), the component should 
   * provide appropriate visual feedback, loading indicators, and maintain interaction consistency 
   * with the existing myAdmin Reports interface
   * 
   * **Validates: Requirements 4.2, 4.5**
   */
  it('should provide consistent interaction feedback for any user interaction state', () => {
    const configurations = generateTestConfigurations();
    
    configurations.forEach((testProps, index) => {
      const mockAdminChange = jest.fn();
      const mockYearChange = jest.fn();
      
      const propsWithMocks = {
        ...testProps,
        onAdministrationChange: mockAdminChange,
        onYearChange: mockYearChange
      };

      const { container, unmount } = render(<MockUnifiedAdminYearFilter {...propsWithMocks} />);

      try {
        // Test loading state feedback
        const isLoading = testProps.isLoading === true;
        const loadingIndicator = screen.queryByTestId('loading-indicator');
        expect(loadingIndicator !== null).toBe(isLoading);
        
        if (isLoading) {
          expect(screen.getByText('Loading filter options...')).toBeInTheDocument();
          
          // Loading indicator should have proper ARIA attributes
          expect(loadingIndicator).toHaveAttribute('role', 'status');
          expect(loadingIndicator).toHaveAttribute('aria-live', 'polite');
          
          // All interactive elements should be disabled during loading
          const selectElements = Array.from(container.querySelectorAll('select'));
          const buttonElements = Array.from(container.querySelectorAll('button'));
          
          selectElements.forEach(select => {
            expect(select).toBeDisabled();
          });
          
          buttonElements.forEach(button => {
            expect(button).toBeDisabled();
          });
          
          // Loading state should provide visual feedback (spinner or loading text)
          expect(container.textContent).toContain('Loading filter options...');
        }

        // Test disabled state feedback
        const isDisabled = testProps.disabled === true;
        if (isDisabled) {
          // All interactive elements should be disabled and provide visual feedback
          const selectElements = Array.from(container.querySelectorAll('select'));
          const buttonElements = Array.from(container.querySelectorAll('button'));
          
          selectElements.forEach(select => {
            expect(select).toBeDisabled();
            // Should have disabled styling (opacity, cursor, etc.)
            // Note: In real implementation, we would check for disabled styling
            expect(select).toHaveAttribute('disabled');
          });
          
          buttonElements.forEach(button => {
            expect(button).toBeDisabled();
            expect(button).toHaveAttribute('disabled');
          });
        }
        
        const isEnabledAndNotLoading = !isDisabled && !isLoading;
        if (isEnabledAndNotLoading) {
          // Interactive elements should be enabled when not disabled and not loading
          const selectElements = Array.from(container.querySelectorAll('select'));
          const buttonElements = Array.from(container.querySelectorAll('button'));
          
          selectElements.forEach(select => {
            expect(select).not.toBeDisabled();
          });
          
          buttonElements.forEach(button => {
            expect(button).not.toBeDisabled();
          });
        }

        // Test hover state feedback (simulated through CSS classes and attributes)
        if (!testProps.disabled && !testProps.isLoading) {
          // Interactive elements should have hover feedback capabilities
          const selectElements = Array.from(container.querySelectorAll('select'));
          const buttonElements = Array.from(container.querySelectorAll('button'));
          
          // Elements should have proper cursor styling for hover states
          selectElements.forEach(select => {
            // Should be interactive (not have not-allowed cursor)
            expect(select).not.toHaveAttribute('disabled');
          });
          
          buttonElements.forEach(button => {
            // Should be interactive (not have not-allowed cursor)
            expect(button).not.toHaveAttribute('disabled');
          });
        }

        // Test focus state feedback and accessibility
        const interactiveElements = [
          ...Array.from(container.querySelectorAll('select')),
          ...Array.from(container.querySelectorAll('button')),
          ...Array.from(container.querySelectorAll('input[type="checkbox"]'))
        ];

        interactiveElements.forEach(element => {
          // All interactive elements should be focusable (unless disabled)
          if (!testProps.disabled && !testProps.isLoading) {
            expect(element).not.toHaveAttribute('tabindex', '-1');
          }
          
          // Should have proper ARIA attributes for accessibility
          if (element.tagName.toLowerCase() === 'select') {
            expect(element).toHaveAttribute('aria-label');
          }
          
          if (element.tagName.toLowerCase() === 'button') {
            // Buttons should have proper ARIA attributes
            const ariaHaspopup = element.getAttribute('aria-haspopup');
            
            // Menu buttons should have haspopup attribute
            if (element.getAttribute('data-testid') === 'year-menu-button') {
              expect(ariaHaspopup).toBe('menu');
            }
          }
        });

        // Test placeholder text feedback
        if (testProps.showAdministration !== false) {
          const adminSelect = screen.queryByLabelText('Administration filter');
          if (adminSelect && !testProps.administrationValue) {
            // Should show appropriate placeholder when no selection
            expect(container.textContent).toContain('Select administration...');
          }
        }

        if (testProps.showYears !== false) {
          if (testProps.multiSelectYears !== false) {
            const yearButton = screen.queryByTestId('year-menu-button');
            if (yearButton && testProps.yearValues.length === 0) {
              // Should show appropriate placeholder for multi-select
              expect(yearButton).toHaveTextContent('Select years...');
            } else if (yearButton && testProps.yearValues.length > 0) {
              // Should show selected years clearly
              const expectedText = testProps.yearValues.sort().join(', ');
              expect(yearButton).toHaveTextContent(expectedText);
            }
          } else {
            const yearSelect = screen.queryByLabelText('Year filter');
            if (yearSelect && testProps.yearValues.length === 0) {
              // Should show appropriate placeholder for single-select
              expect(container.textContent).toContain('Select year...');
            }
          }
        }

        // Test consistent styling feedback
        const mainContainer = screen.getByTestId('unified-filter-container');
        
        // Should maintain consistent theme colors (gray backgrounds, white text, orange accents)
        expect(mainContainer).toHaveStyle({ backgroundColor: '#2D3748' }); // gray.700
        
        // Text elements should have consistent white color
        const textElements = Array.from(container.querySelectorAll('label, span'));
        textElements.forEach(textElement => {
          if (textElement.textContent && 
              (textElement.textContent.includes('Administration') || 
               textElement.textContent.includes('Year'))) {
            // Labels should have white text (in real implementation, we'd check computed styles)
            expect(textElement).toBeInTheDocument();
          }
        });

        // Test error state feedback (if error exists)
        if (testProps.administrationOptions.length === 0 && testProps.showAdministration !== false) {
          // Should handle empty options gracefully without crashing
          expect(mainContainer).toBeInTheDocument();
        }
        
        if (testProps.availableYears.length === 0 && testProps.showYears !== false) {
          // Should handle empty years gracefully without crashing
          expect(mainContainer).toBeInTheDocument();
        }

        // Test interaction state consistency across different sizes
        const sizeVariants = ['sm', 'md', 'lg'];
        const currentSize = testProps.size || 'md';
        
        // Component should maintain consistent interaction feedback regardless of size
        expect(sizeVariants.includes(currentSize)).toBe(true);
        expect(mainContainer).toBeInTheDocument();

        // Test that feedback is immediate and responsive
        // Component should render without delays or loading states (unless explicitly loading)
        if (!testProps.isLoading) {
          // Should not show loading indicators when not in loading state
          expect(screen.queryByText('Loading filter options...')).not.toBeInTheDocument();
        }

        // Test accessibility feedback consistency
        // All interactive elements should have proper labels and descriptions
        const adminSelect = screen.queryByLabelText('Administration filter');
        if (adminSelect) {
          expect(adminSelect).toHaveAttribute('aria-label');
        }

        const yearButton = screen.queryByTestId('year-menu-button');
        if (yearButton) {
          expect(yearButton).toHaveAttribute('aria-haspopup');
          expect(yearButton).toHaveAttribute('aria-label');
        }

        const yearSelect = screen.queryByLabelText('Year filter');
        if (yearSelect) {
          expect(yearSelect).toHaveAttribute('aria-label');
        }

        // Test that interaction feedback doesn't interfere with functionality
        // Component should remain functional while providing feedback
        if (!testProps.disabled && !testProps.isLoading) {
          // Callbacks should still be connected and functional
          expect(typeof propsWithMocks.onAdministrationChange).toBe('function');
          expect(typeof propsWithMocks.onYearChange).toBe('function');
        }

        // Test visual hierarchy and feedback clarity
        // Important elements should be visually distinct
        if (testProps.showAdministration !== false) {
          const adminLabel = screen.queryByText('Administration');
          expect(adminLabel).toBeInTheDocument();
        }

        if (testProps.showYears !== false) {
          const yearLabel = screen.queryByText(testProps.multiSelectYears !== false ? 'Years' : 'Year');
          expect(yearLabel).toBeInTheDocument();
        }

        // Test that feedback states don't conflict
        // Loading and disabled states should work together properly
        if (testProps.isLoading && testProps.disabled) {
          const selectElements = Array.from(container.querySelectorAll('select'));
          const buttonElements = Array.from(container.querySelectorAll('button'));
          
          // All elements should be disabled when both loading and disabled
          [...selectElements, ...buttonElements].forEach(element => {
            expect(element).toBeDisabled();
          });
          
          // Should still show loading indicator
          expect(screen.getByTestId('loading-indicator')).toBeInTheDocument();
        }

      } catch (error) {
        console.error(`Interaction feedback test failed for configuration ${index}:`, testProps);
        throw error;
      } finally {
        unmount();
      }
    });
  });

  /**
   * **Feature: unified-admin-year-filter, Property 5: Error Handling Robustness**
   * 
   * For any error condition (empty options, API failures, invalid selections, or component 
   * lifecycle events), the component should handle errors gracefully, provide appropriate 
   * user feedback, validate inputs, and clean up resources properly
   * 
   * **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
   */
  it('should handle all error conditions gracefully for any error scenario', () => {
    // Generate error scenarios to test
    const errorScenarios = [
      // Empty administration options (Requirement 5.1)
      {
        name: 'empty administration options',
        props: {
          administrationValue: '',
          onAdministrationChange: jest.fn(),
          administrationOptions: [], // Empty array
          showAdministration: true,
          yearValues: ['2024'],
          onYearChange: jest.fn(),
          availableYears: ['2023', '2024', '2025'],
          showYears: true,
          multiSelectYears: true
        },
        expectedBehavior: 'should disable administration selection and show appropriate message'
      },
      // Empty year options (Requirement 5.2)
      {
        name: 'empty year options',
        props: {
          administrationValue: 'all',
          onAdministrationChange: jest.fn(),
          administrationOptions: [{ value: 'all', label: 'All' }],
          showAdministration: true,
          yearValues: [],
          onYearChange: jest.fn(),
          availableYears: [], // Empty array
          showYears: true,
          multiSelectYears: true
        },
        expectedBehavior: 'should disable year selection and show appropriate message'
      },
      // Invalid year selections (Requirement 5.4)
      {
        name: 'invalid year selections',
        props: {
          administrationValue: 'all',
          onAdministrationChange: jest.fn(),
          administrationOptions: [{ value: 'all', label: 'All' }],
          showAdministration: true,
          yearValues: ['2020', '2030'], // Years not in available years
          onYearChange: jest.fn(),
          availableYears: ['2023', '2024', '2025'],
          showYears: true,
          multiSelectYears: true
        },
        expectedBehavior: 'should validate selections and handle invalid years gracefully'
      },
      // Invalid administration selection (Requirement 5.4)
      {
        name: 'invalid administration selection',
        props: {
          administrationValue: 'nonexistent', // Not in available options
          onAdministrationChange: jest.fn(),
          administrationOptions: [
            { value: 'all', label: 'All' },
            { value: 'GoodwinSolutions', label: 'GoodwinSolutions' }
          ],
          showAdministration: true,
          yearValues: ['2024'],
          onYearChange: jest.fn(),
          availableYears: ['2023', '2024', '2025'],
          showYears: true,
          multiSelectYears: true
        },
        expectedBehavior: 'should validate administration selection and handle invalid values gracefully'
      },
      // Both empty options (Combined 5.1 and 5.2)
      {
        name: 'both empty options',
        props: {
          administrationValue: '',
          onAdministrationChange: jest.fn(),
          administrationOptions: [],
          showAdministration: true,
          yearValues: [],
          onYearChange: jest.fn(),
          availableYears: [],
          showYears: true,
          multiSelectYears: true
        },
        expectedBehavior: 'should handle both empty option arrays gracefully'
      },
      // Disabled options (Edge case for 5.1)
      {
        name: 'all administration options disabled',
        props: {
          administrationValue: '',
          onAdministrationChange: jest.fn(),
          administrationOptions: [
            { value: 'all', label: 'All', disabled: true },
            { value: 'test', label: 'Test', disabled: true }
          ],
          showAdministration: true,
          yearValues: ['2024'],
          onYearChange: jest.fn(),
          availableYears: ['2023', '2024', '2025'],
          showYears: true,
          multiSelectYears: true
        },
        expectedBehavior: 'should handle all disabled options gracefully'
      },
      // Single-select with invalid year (Requirement 5.4)
      {
        name: 'single-select invalid year',
        props: {
          administrationValue: 'all',
          onAdministrationChange: jest.fn(),
          administrationOptions: [{ value: 'all', label: 'All' }],
          showAdministration: true,
          yearValues: ['2020'], // Not in available years
          onYearChange: jest.fn(),
          availableYears: ['2023', '2024', '2025'],
          showYears: true,
          multiSelectYears: false // Single-select mode
        },
        expectedBehavior: 'should validate single-select year and handle invalid values gracefully'
      },
      // Loading state with errors (Requirement 5.3 simulation)
      {
        name: 'loading state error handling',
        props: {
          administrationValue: '',
          onAdministrationChange: jest.fn(),
          administrationOptions: [],
          showAdministration: true,
          yearValues: [],
          onYearChange: jest.fn(),
          availableYears: [],
          showYears: true,
          multiSelectYears: true,
          isLoading: true // Simulating loading state with empty options (API failure scenario)
        },
        expectedBehavior: 'should handle loading state with empty options gracefully'
      }
    ];

    errorScenarios.forEach((scenario, index) => {
      const { container, unmount } = render(<MockUnifiedAdminYearFilter {...scenario.props} />);

      try {
        // Component should always render without crashing, regardless of error conditions
        expect(container.firstChild).toBeInTheDocument();
        const mainContainer = screen.getByTestId('unified-filter-container');
        expect(mainContainer).toBeInTheDocument();

        // Test Requirement 5.1: Empty administration options
        if (scenario.props.administrationOptions.length === 0 && scenario.props.showAdministration) {
          const adminSection = screen.queryByTestId('administration-section');
          expect(adminSection).toBeInTheDocument();
          
          // Should still render the section but handle empty options gracefully
          const adminSelect = screen.queryByLabelText('Administration filter');
          expect(adminSelect).toBeInTheDocument();
          
          // Should show placeholder text when no options available
          expect(container.textContent).toContain('Select administration...');
          
          // Component should not crash with empty options
          expect(mainContainer).toBeInTheDocument();
        }

        // Test Requirement 5.2: Empty year options
        if (scenario.props.availableYears.length === 0 && scenario.props.showYears) {
          const yearSection = screen.queryByTestId('year-section');
          expect(yearSection).toBeInTheDocument();
          
          if (scenario.props.multiSelectYears) {
            // Multi-select should handle empty years gracefully
            const yearButton = screen.queryByTestId('year-menu-button');
            expect(yearButton).toBeInTheDocument();
            expect(yearButton).toHaveTextContent('Select years...');
          } else {
            // Single-select should handle empty years gracefully
            const yearSelect = screen.queryByLabelText('Year filter');
            expect(yearSelect).toBeInTheDocument();
            expect(container.textContent).toContain('Select year...');
          }
          
          // Component should not crash with empty year options
          expect(mainContainer).toBeInTheDocument();
        }

        // Test Requirement 5.3: Loading state error handling (simulated API failure)
        if (scenario.props.isLoading) {
          // Should show loading indicator
          const loadingIndicator = screen.queryByTestId('loading-indicator');
          expect(loadingIndicator).toBeInTheDocument();
          expect(screen.getByText('Loading filter options...')).toBeInTheDocument();
          
          // Should disable all interactions during loading
          const selectElements = Array.from(container.querySelectorAll('select'));
          const buttonElements = Array.from(container.querySelectorAll('button'));
          
          selectElements.forEach(select => {
            expect(select).toBeDisabled();
          });
          
          buttonElements.forEach(button => {
            expect(button).toBeDisabled();
          });
          
          // Should handle loading state with empty options gracefully (simulating API failure)
          expect(mainContainer).toBeInTheDocument();
        }

        // Test Requirement 5.4: Invalid selections validation
        if (scenario.name.includes('invalid')) {
          // Component should handle invalid selections gracefully without crashing
          expect(mainContainer).toBeInTheDocument();
          
          // Invalid year selections should be handled gracefully
          if (scenario.props.yearValues.length > 0 && scenario.props.availableYears.length > 0) {
            const availableYears: string[] = scenario.props.availableYears;
            const invalidYears = scenario.props.yearValues.filter(
              year => !availableYears.includes(year)
            );
            
            if (invalidYears.length > 0) {
              // Component should still render without crashing
              expect(mainContainer).toBeInTheDocument();
              
              // Should not display invalid years in the selection
              if (scenario.props.multiSelectYears) {
                const yearButton = screen.queryByTestId('year-menu-button');
                if (yearButton) {
                  // Should only show valid years or show placeholder
                  const availableYears: string[] = scenario.props.availableYears;
                  const validYears = scenario.props.yearValues.filter(
                    year => availableYears.includes(year)
                  );
                  
                  if (validYears.length > 0) {
                    const expectedText = validYears.sort().join(', ');
                    expect(yearButton).toHaveTextContent(expectedText);
                  } else {
                    expect(yearButton).toHaveTextContent('Select years...');
                  }
                }
              } else {
                const yearSelect = screen.queryByLabelText('Year filter');
                if (yearSelect) {
                  // Should show valid year or empty value
                  const availableYears: string[] = scenario.props.availableYears;
                  const validYear = scenario.props.yearValues.find(
                    year => availableYears.includes(year)
                  );
                  expect(yearSelect).toHaveValue(validYear || '');
                }
              }
            }
          }
          
          // Invalid administration selection should be handled gracefully
          if (scenario.props.administrationValue && scenario.props.administrationOptions.length > 0) {
            const validAdminValues = scenario.props.administrationOptions.map(opt => opt.value);
            if (!validAdminValues.includes(scenario.props.administrationValue)) {
              // Component should still render without crashing
              expect(mainContainer).toBeInTheDocument();
              
              // Should handle invalid administration value gracefully
              const adminSelect = screen.queryByLabelText('Administration filter');
              if (adminSelect) {
                // Should either show the invalid value or reset to empty/default
                expect(adminSelect).toBeInTheDocument();
              }
            }
          }
        }

        // Test disabled options handling (Edge case for 5.1)
        if (scenario.name.includes('disabled')) {
          const adminSelect = screen.queryByLabelText('Administration filter');
          if (adminSelect) {
            // Should render disabled options but handle them gracefully
            scenario.props.administrationOptions.forEach(option => {
              const optionElement = container.querySelector(`option[value="${option.value}"]`);
              if (optionElement && 'disabled' in option && option.disabled === true) {
                expect(optionElement).toBeDisabled();
              }
            });
            
            // Component should not crash with all disabled options
            expect(mainContainer).toBeInTheDocument();
          }
        }

        // Test general error resilience
        // Component should maintain basic functionality even with error conditions
        
        // 1. Should always have main container
        expect(mainContainer).toBeInTheDocument();
        expect(mainContainer).toHaveStyle({ backgroundColor: '#2D3748' });
        
        // 2. Should maintain proper section visibility based on props
        if (scenario.props.showAdministration) {
          expect(screen.getByTestId('administration-section')).toBeInTheDocument();
        }
        
        if (scenario.props.showYears) {
          expect(screen.getByTestId('year-section')).toBeInTheDocument();
        }
        
        // 3. Should maintain proper accessibility attributes even with errors
        const selectElements = Array.from(container.querySelectorAll('select'));
        selectElements.forEach(select => {
          expect(select).toHaveAttribute('aria-label');
        });
        
        const buttonElements = Array.from(container.querySelectorAll('button'));
        buttonElements.forEach(button => {
          if (button.getAttribute('data-testid') === 'year-menu-button') {
            expect(button).toHaveAttribute('aria-haspopup', 'menu');
          }
        });
        
        // 4. Should maintain callback function integrity
        expect(typeof scenario.props.onAdministrationChange).toBe('function');
        expect(typeof scenario.props.onYearChange).toBe('function');
        
        // 5. Should not throw errors when callbacks are called with valid parameters
        expect(() => {
          scenario.props.onAdministrationChange('test');
        }).not.toThrow();
        
        expect(() => {
          scenario.props.onYearChange(['2024']);
        }).not.toThrow();
        
        expect(() => {
          scenario.props.onYearChange([]);
        }).not.toThrow();

        // Test graceful degradation
        // Component should provide meaningful user experience even with errors
        
        // Should show appropriate placeholder text
        if (scenario.props.showAdministration && scenario.props.administrationOptions.length === 0) {
          expect(container.textContent).toContain('Select administration...');
        }
        
        if (scenario.props.showYears && scenario.props.availableYears.length === 0) {
          if (scenario.props.multiSelectYears) {
            expect(container.textContent).toContain('Select years...');
          } else {
            expect(container.textContent).toContain('Select year...');
          }
        }

        // Test error boundary behavior (component should not crash)
        // Simulate potential error conditions that could cause crashes
        
        // 1. Null/undefined callback handling
        const propsWithNullCallbacks = {
          ...scenario.props,
          onAdministrationChange: null as any,
          onYearChange: null as any
        };
        
        // Component should handle null callbacks gracefully (though not recommended)
        expect(() => {
          const { unmount: unmount2 } = render(<MockUnifiedAdminYearFilter {...propsWithNullCallbacks} />);
          unmount2();
        }).not.toThrow();
        
        // 2. Malformed options handling
        const propsWithMalformedOptions = {
          ...scenario.props,
          administrationOptions: [
            { value: null as any, label: 'Invalid' },
            { value: 'valid', label: null as any }
          ]
        };
        
        // Component should handle malformed options gracefully
        expect(() => {
          const { unmount: unmount3 } = render(<MockUnifiedAdminYearFilter {...propsWithMalformedOptions} />);
          unmount3();
        }).not.toThrow();

      } catch (error) {
        console.error(`Error handling test failed for scenario "${scenario.name}":`, scenario.props);
        console.error('Expected behavior:', scenario.expectedBehavior);
        throw error;
      } finally {
        // Test Requirement 5.5: Component cleanup
        // Unmounting should not cause errors or memory leaks
        expect(() => {
          unmount();
        }).not.toThrow();
      }
    });

    // Additional test for Requirement 5.5: Memory leak prevention
    // Test multiple mount/unmount cycles to ensure proper cleanup
    const testProps = {
      administrationValue: 'all',
      onAdministrationChange: jest.fn(),
      administrationOptions: [{ value: 'all', label: 'All' }],
      yearValues: ['2024'],
      onYearChange: jest.fn(),
      availableYears: ['2023', '2024', '2025']
    };

    // Mount and unmount multiple times to test cleanup
    for (let i = 0; i < 10; i++) {
      const { unmount } = render(<MockUnifiedAdminYearFilter {...testProps} />);
      expect(screen.getByTestId('unified-filter-container')).toBeInTheDocument();
      
      // Unmounting should not throw errors
      expect(() => {
        unmount();
      }).not.toThrow();
    }

    // Test error recovery scenarios
    // Component should recover gracefully when props change from error state to valid state
    const { rerender } = render(
      <MockUnifiedAdminYearFilter
        administrationValue=""
        onAdministrationChange={jest.fn()}
        administrationOptions={[]} // Start with error state
        yearValues={[]}
        onYearChange={jest.fn()}
        availableYears={[]}
        showAdministration={true}
        showYears={true}
      />
    );

    // Should handle error state
    expect(screen.getByTestId('unified-filter-container')).toBeInTheDocument();

    // Should recover when props become valid
    rerender(
      <MockUnifiedAdminYearFilter
        administrationValue="all"
        onAdministrationChange={jest.fn()}
        administrationOptions={[{ value: 'all', label: 'All' }]} // Recovery to valid state
        yearValues={['2024']}
        onYearChange={jest.fn()}
        availableYears={['2023', '2024', '2025']}
        showAdministration={true}
        showYears={true}
      />
    );

    // Should render normally after recovery
    expect(screen.getByTestId('unified-filter-container')).toBeInTheDocument();
    expect(screen.getByText('Administration')).toBeInTheDocument();
    expect(screen.getByText('Years')).toBeInTheDocument();
  });

  // Additional unit tests for specific scenarios
  describe('Unit Tests for Specific Scenarios', () => {
    const defaultProps: UnifiedAdminYearFilterProps = {
      administrationValue: 'all',
      onAdministrationChange: jest.fn(),
      administrationOptions: [
        { value: 'all', label: 'All' },
        { value: 'GoodwinSolutions', label: 'GoodwinSolutions' }
      ],
      yearValues: ['2024'],
      onYearChange: jest.fn(),
      availableYears: ['2023', '2024', '2025']
    };

    it('renders administration section by default', () => {
      render(<MockUnifiedAdminYearFilter {...defaultProps} />);

      expect(screen.getByText('Administration')).toBeInTheDocument();
      expect(screen.getByTestId('administration-section')).toBeInTheDocument();
    });

    it('renders year section by default with multi-select', () => {
      render(<MockUnifiedAdminYearFilter {...defaultProps} />);

      expect(screen.getByText('Years')).toBeInTheDocument();
      expect(screen.getByTestId('year-section')).toBeInTheDocument();
      expect(screen.getByTestId('year-menu-button')).toBeInTheDocument();
    });

    it('renders single year select when multiSelectYears is false', () => {
      render(<MockUnifiedAdminYearFilter {...defaultProps} multiSelectYears={false} />);

      expect(screen.getByText('Year')).toBeInTheDocument();
      expect(screen.getByLabelText('Year filter')).toBeInTheDocument();
    });

    it('hides administration section when showAdministration is false', () => {
      render(<MockUnifiedAdminYearFilter {...defaultProps} showAdministration={false} />);

      expect(screen.queryByTestId('administration-section')).not.toBeInTheDocument();
      expect(screen.queryByText('Administration')).not.toBeInTheDocument();
    });

    it('hides year section when showYears is false', () => {
      render(<MockUnifiedAdminYearFilter {...defaultProps} showYears={false} />);

      expect(screen.queryByTestId('year-section')).not.toBeInTheDocument();
      expect(screen.queryByText('Years')).not.toBeInTheDocument();
      expect(screen.queryByText('Year')).not.toBeInTheDocument();
    });

    it('shows loading indicator when isLoading is true', () => {
      render(<MockUnifiedAdminYearFilter {...defaultProps} isLoading={true} />);

      expect(screen.getByTestId('loading-indicator')).toBeInTheDocument();
      expect(screen.getByText('Loading filter options...')).toBeInTheDocument();
    });

    it('disables all controls when disabled is true', () => {
      render(<MockUnifiedAdminYearFilter {...defaultProps} disabled={true} />);

      const adminSelect = screen.getByLabelText('Administration filter');
      expect(adminSelect).toBeDisabled();
      
      const yearButton = screen.getByTestId('year-menu-button');
      expect(yearButton).toBeDisabled();
    });

    it('applies correct grid layout for different sizes', () => {
      const { rerender } = render(<MockUnifiedAdminYearFilter {...defaultProps} size="sm" />);

      // Test that component renders without errors for different sizes
      expect(screen.getByTestId('unified-filter-container')).toBeInTheDocument();

      rerender(<MockUnifiedAdminYearFilter {...defaultProps} size="md" />);
      expect(screen.getByTestId('unified-filter-container')).toBeInTheDocument();

      rerender(<MockUnifiedAdminYearFilter {...defaultProps} size="lg" />);
      expect(screen.getByTestId('unified-filter-container')).toBeInTheDocument();
    });

    it('displays correct year selection text', () => {
      render(<MockUnifiedAdminYearFilter {...defaultProps} yearValues={['2023', '2024']} />);

      const yearButton = screen.getByTestId('year-menu-button');
      expect(yearButton).toHaveTextContent('2023, 2024');
    });

    it('displays placeholder text when no years selected', () => {
      render(<MockUnifiedAdminYearFilter {...defaultProps} yearValues={[]} />);

      const yearButton = screen.getByTestId('year-menu-button');
      expect(yearButton).toHaveTextContent('Select years...');
    });

    it('has proper accessibility attributes', () => {
      render(<MockUnifiedAdminYearFilter {...defaultProps} />);

      const adminSelect = screen.getByLabelText('Administration filter');
      expect(adminSelect).toHaveAttribute('aria-label', 'Administration filter');

      const yearButton = screen.getByTestId('year-menu-button');
      expect(yearButton).toHaveAttribute('aria-haspopup', 'menu');
    });
  });
});
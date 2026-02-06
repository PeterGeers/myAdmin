/**
 * GenericFilter Property-Based Tests
 * 
 * This test suite uses property-based testing (PBT) with fast-check to verify
 * that the GenericFilter component behaves correctly across a wide range of
 * randomly generated inputs and configurations.
 */

import React from 'react';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import * as fc from 'fast-check';

// Mock Chakra UI components before importing the component
const mockOnOpen = jest.fn();
const mockOnClose = jest.fn();

jest.mock('@chakra-ui/react', () => ({
  Button: ({ children, onClick, disabled, rightIcon, textAlign, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
      {rightIcon}
    </button>
  ),
  Checkbox: ({ isChecked, ...props }: any) => (
    <input type="checkbox" checked={isChecked} readOnly {...props} />
  ),
  FormControl: ({ children, isDisabled, size }: any) => (
    <div data-disabled={isDisabled} data-size={size}>{children}</div>
  ),
  FormLabel: ({ children, htmlFor }: any) => (
    <label htmlFor={htmlFor}>{children}</label>
  ),
  Menu: ({ children, isOpen, onClose, closeOnSelect }: any) => (
    <div data-menu-open={isOpen}>{children}</div>
  ),
  MenuButton: ({ children, as: Component = 'button', rightIcon, ...props }: any) => (
    <Component {...props}>
      {children}
      {rightIcon}
    </Component>
  ),
  MenuList: ({ children, maxH, overflowY, minW }: any) => (
    <div role="menu">{children}</div>
  ),
  MenuItem: ({ children, onClick, closeOnSelect, isDisabled, ...props }: any) => (
    <div role="menuitemcheckbox" onClick={onClick} aria-checked="false" {...props}>
      {children}
    </div>
  ),
  Select: ({ children, value, onChange, placeholder, disabled, size, icon, ...props }: any) => (
    <select value={value} onChange={onChange} disabled={disabled} {...props}>
      {placeholder && <option value="">{placeholder}</option>}
      {children}
    </select>
  ),
  Text: ({ children, isTruncated, color, fontSize, fontWeight, ...props }: any) => (
    <span {...props}>{children}</span>
  ),
  HStack: ({ children, spacing, width }: any) => (
    <div style={{ display: 'flex' }}>{children}</div>
  ),
  Spinner: ({ size }: any) => <span data-testid="spinner" className="chakra-spinner">Loading...</span>,
  Alert: ({ children, status, mb, size }: any) => (
    <div role="alert" data-status={status}>{children}</div>
  ),
  AlertIcon: () => <span data-testid="alert-icon">!</span>,
  useDisclosure: () => ({
    isOpen: false,
    onOpen: mockOnOpen,
    onClose: mockOnClose,
  }),
}));

jest.mock('@chakra-ui/icons', () => ({
  ChevronDownIcon: () => <span data-testid="chevron-icon">▼</span>,
}));

// Import component after mocks
import { GenericFilter } from './GenericFilter';

// Custom arbitraries for generating test data
// Use alphanumeric strings to avoid special character issues with mocked components
const stringOptionArbitrary = fc.string({ 
  minLength: 3, 
  maxLength: 20,
  unit: fc.constantFrom(...'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '.split(''))
}).filter(s => s.trim().length >= 3);

const stringArrayArbitrary = fc.array(stringOptionArbitrary, { minLength: 1, maxLength: 10 });
const sizeArbitrary = fc.constantFrom('sm', 'md', 'lg');
const booleanArbitrary = fc.boolean();
const labelArbitrary = fc.string({ 
  minLength: 3, 
  maxLength: 30,
  unit: fc.constantFrom(...'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '.split(''))
}).filter(s => s.trim().length >= 3);

describe('GenericFilter Property-Based Tests', () => {
  afterEach(() => {
    cleanup();
  });

  describe('Property 1: Component Rendering Consistency', () => {
    it('renders correctly with random string options in single-select mode', () => {
      fc.assert(
        fc.property(
          stringArrayArbitrary,
          labelArbitrary,
          sizeArbitrary,
          (options, label, size) => {
            const onChange = jest.fn();
            const uniqueOptions = Array.from(new Set(options));
            
            render(
              <GenericFilter
                values={[]}
                onChange={onChange}
                availableOptions={uniqueOptions}
                label={label}
                size={size}
              />
            );

            // Use semantic queries
            expect(screen.getByLabelText(label)).toBeInTheDocument();
            expect(screen.getByRole('combobox')).toBeInTheDocument();
            
            // Verify all options are rendered
            uniqueOptions.forEach((option) => {
              expect(screen.getByRole('option', { name: option })).toBeInTheDocument();
            });
            
            cleanup();
          }
        ),
        { numRuns: 100 }
      );
    });

    it('renders correctly with random string options in multi-select mode', () => {
      fc.assert(
        fc.property(
          stringArrayArbitrary,
          labelArbitrary,
          sizeArbitrary,
          (options, label, size) => {
            const onChange = jest.fn();
            const uniqueOptions = Array.from(new Set(options));
            
            render(
              <GenericFilter
                values={[]}
                onChange={onChange}
                availableOptions={uniqueOptions}
                multiSelect
                label={label}
                size={size}
              />
            );

            // Use semantic queries
            expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
            
            const button = screen.getByRole('button', { name: label });
            expect(button).toHaveAttribute('aria-label', label);
            expect(button).toHaveAttribute('aria-haspopup', 'true');
            
            cleanup();
          }
        ),
        { numRuns: 100 }
      );
    });
  });

  describe('Property 2: State Management Consistency', () => {
    it('calls onChange with correct value in single-select mode', async () => {
      await fc.assert(
        fc.asyncProperty(
          stringArrayArbitrary,
          labelArbitrary,
          async (options, label) => {
            const user = userEvent.setup();
            const onChange = jest.fn();
            const uniqueOptions = Array.from(new Set(options));
            
            render(
              <GenericFilter
                values={[]}
                onChange={onChange}
                availableOptions={uniqueOptions}
                label={label}
              />
            );

            const select = screen.getByRole('combobox');
            const randomOption = uniqueOptions[Math.floor(Math.random() * uniqueOptions.length)];
            
            await user.selectOptions(select, randomOption);

            expect(onChange).toHaveBeenCalledWith([randomOption]);
            expect(onChange).toHaveBeenCalledTimes(1);
            
            cleanup();
          }
        ),
        { numRuns: 50 }
      );
    });

    it('maintains state isolation between multiple instances', () => {
      fc.assert(
        fc.property(
          stringArrayArbitrary,
          stringArrayArbitrary,
          (options1, options2) => {
            const onChange1 = jest.fn();
            const onChange2 = jest.fn();
            const uniqueOptions1 = Array.from(new Set(options1));
            const uniqueOptions2 = Array.from(new Set(options2));
            
            render(
              <>
                <GenericFilter
                  values={[]}
                  onChange={onChange1}
                  availableOptions={uniqueOptions1}
                  label="Filter 1"
                />
                <GenericFilter
                  values={[]}
                  onChange={onChange2}
                  availableOptions={uniqueOptions2}
                  label="Filter 2"
                />
              </>
            );

            // Verify both filters are rendered independently
            expect(screen.getByLabelText('Filter 1')).toBeInTheDocument();
            expect(screen.getByLabelText('Filter 2')).toBeInTheDocument();
            
            // Verify they have separate select elements
            const selects = screen.getAllByRole('combobox');
            expect(selects).toHaveLength(2);
            
            cleanup();
          }
        ),
        { numRuns: 100 }
      );
    });
  });

  describe('Property 3: Selection Behavior Correctness', () => {
    it('displays selected value correctly in single-select mode', () => {
      fc.assert(
        fc.property(
          stringArrayArbitrary,
          labelArbitrary,
          (options, label) => {
            const onChange = jest.fn();
            const uniqueOptions = Array.from(new Set(options));
            const selectedValue = uniqueOptions[0];
            
            render(
              <GenericFilter
                values={[selectedValue]}
                onChange={onChange}
                availableOptions={uniqueOptions}
                label={label}
              />
            );

            const select = screen.getByRole('combobox') as HTMLSelectElement;
            expect(select.value).toBe(selectedValue);
            
            cleanup();
          }
        ),
        { numRuns: 100 }
      );
    });

    it('handles invalid selections gracefully', () => {
      fc.assert(
        fc.property(
          stringArrayArbitrary,
          labelArbitrary,
          stringOptionArbitrary,
          (options, label, invalidValue) => {
            const onChange = jest.fn();
            const uniqueOptions = Array.from(new Set(options));
            const filteredOptions = uniqueOptions.filter(opt => opt !== invalidValue);
            
            if (filteredOptions.length === 0) {
              return; // Skip if all options match invalid value
            }
            
            // Component should not crash with invalid value
            expect(() => {
              render(
                <GenericFilter
                  values={[invalidValue]}
                  onChange={onChange}
                  availableOptions={filteredOptions}
                  label={label}
                />
              );
            }).not.toThrow();
            
            cleanup();
          }
        ),
        { numRuns: 100 }
      );
    });
  });

  describe('Property 4: Configuration Adaptability', () => {
    it('adapts to different prop combinations without crashing', () => {
      fc.assert(
        fc.property(
          stringArrayArbitrary,
          labelArbitrary,
          sizeArbitrary,
          booleanArbitrary,
          booleanArbitrary,
          booleanArbitrary,
          (options, label, size, multiSelect, disabled, isLoading) => {
            const onChange = jest.fn();
            const uniqueOptions = Array.from(new Set(options));
            
            expect(() => {
              render(
                <GenericFilter
                  values={[]}
                  onChange={onChange}
                  availableOptions={uniqueOptions}
                  label={label}
                  size={size}
                  multiSelect={multiSelect}
                  disabled={disabled}
                  isLoading={isLoading}
                />
              );
            }).not.toThrow();
            
            // Verify component renders
            if (multiSelect) {
              expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
            } else {
              expect(screen.getByLabelText(label)).toBeInTheDocument();
            }
            
            cleanup();
          }
        ),
        { numRuns: 100 }
      );
    });

    it('handles empty options array gracefully', () => {
      fc.assert(
        fc.property(
          labelArbitrary,
          booleanArbitrary,
          (label, multiSelect) => {
            const onChange = jest.fn();
            
            expect(() => {
              render(
                <GenericFilter
                  values={[]}
                  onChange={onChange}
                  availableOptions={[]}
                  label={label}
                  multiSelect={multiSelect}
                />
              );
            }).not.toThrow();
            
            // Verify component renders
            if (multiSelect) {
              expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
            } else {
              expect(screen.getByLabelText(label)).toBeInTheDocument();
            }
            
            cleanup();
          }
        ),
        { numRuns: 100 }
      );
    });
  });

  describe('Property 5: Error Handling Robustness', () => {
    it('displays error messages correctly', () => {
      fc.assert(
        fc.property(
          stringArrayArbitrary,
          labelArbitrary,
          labelArbitrary,
          booleanArbitrary,
          (options, label, errorMessage, multiSelect) => {
            const onChange = jest.fn();
            const uniqueOptions = Array.from(new Set(options));
            
            render(
              <GenericFilter
                values={[]}
                onChange={onChange}
                availableOptions={uniqueOptions}
                label={label}
                error={errorMessage}
                multiSelect={multiSelect}
              />
            );

            // Verify error message is displayed
            expect(screen.getByRole('alert')).toBeInTheDocument();
            
            cleanup();
          }
        ),
        { numRuns: 100 }
      );
    });

    it('handles null error gracefully', () => {
      fc.assert(
        fc.property(
          stringArrayArbitrary,
          labelArbitrary,
          booleanArbitrary,
          (options, label, multiSelect) => {
            const onChange = jest.fn();
            const uniqueOptions = Array.from(new Set(options));
            
            render(
              <GenericFilter
                values={[]}
                onChange={onChange}
                availableOptions={uniqueOptions}
                label={label}
                error={null}
                multiSelect={multiSelect}
              />
            );

            // Verify no error alert is displayed
            expect(screen.queryByRole('alert')).not.toBeInTheDocument();
            
            cleanup();
          }
        ),
        { numRuns: 100 }
      );
    });

    it('degrades gracefully with undefined onChange', () => {
      fc.assert(
        fc.property(
          stringArrayArbitrary,
          labelArbitrary,
          (options, label) => {
            const uniqueOptions = Array.from(new Set(options));
            
            expect(() => {
              render(
                <GenericFilter
                  values={[]}
                  onChange={undefined as any}
                  availableOptions={uniqueOptions}
                  label={label}
                />
              );
            }).not.toThrow();
            
            cleanup();
          }
        ),
        { numRuns: 100 }
      );
    });
  });

  describe('Property 6: Interaction Feedback Consistency', () => {
    it('shows loading state correctly', () => {
      fc.assert(
        fc.property(
          stringArrayArbitrary,
          labelArbitrary,
          booleanArbitrary,
          (options, label, multiSelect) => {
            const onChange = jest.fn();
            const uniqueOptions = Array.from(new Set(options));
            
            render(
              <GenericFilter
                values={[]}
                onChange={onChange}
                availableOptions={uniqueOptions}
                label={label}
                isLoading={true}
                multiSelect={multiSelect}
              />
            );

            // Verify spinner is displayed
            expect(screen.getByText(/loading/i)).toBeInTheDocument();
            
            // Verify component is disabled when loading
            if (multiSelect) {
              const button = screen.getByRole('button', { name: label });
              expect(button).toBeDisabled();
            } else {
              const select = screen.getByRole('combobox');
              expect(select).toBeDisabled();
            }
            
            cleanup();
          }
        ),
        { numRuns: 100 }
      );
    });

    it('shows disabled state correctly', () => {
      fc.assert(
        fc.property(
          stringArrayArbitrary,
          labelArbitrary,
          booleanArbitrary,
          (options, label, multiSelect) => {
            const onChange = jest.fn();
            const uniqueOptions = Array.from(new Set(options));
            
            render(
              <GenericFilter
                values={[]}
                onChange={onChange}
                availableOptions={uniqueOptions}
                label={label}
                disabled={true}
                multiSelect={multiSelect}
              />
            );

            // Verify component is disabled
            if (multiSelect) {
              const button = screen.getByRole('button', { name: label });
              expect(button).toBeDisabled();
            } else {
              const select = screen.getByRole('combobox');
              expect(select).toBeDisabled();
            }
            
            cleanup();
          }
        ),
        { numRuns: 100 }
      );
    });
  });
});

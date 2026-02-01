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

// Use centralized Chakra UI mocks
jest.mock('@chakra-ui/react', () => require('../chakraMock').chakraMock);
jest.mock('@chakra-ui/icons', () => require('../chakraMock').iconsMock);




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







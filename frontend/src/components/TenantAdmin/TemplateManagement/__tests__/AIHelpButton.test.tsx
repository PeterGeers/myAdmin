/**
 * AIHelpButton Component Unit Tests
 * 
 * Tests for AI assistance modal, fix suggestions, and auto-fix application.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AIHelpButton } from '../AIHelpButton';
import type { AIHelpResponse } from '../../../../types/template';

// Use centralized Chakra UI mocks
jest.mock('@chakra-ui/react', () => require('../chakraMock').chakraMock);
jest.mock('@chakra-ui/icons', () => require('../chakraMock').iconsMock);




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







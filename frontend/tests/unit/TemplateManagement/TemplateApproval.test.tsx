/**
 * TemplateApproval Component Unit Tests
 * 
 * Tests for approve/reject buttons, confirmation dialogs, and notes/reason input.
 */

import React from 'react';
import { render, screen, waitFor } from '../../../src/test-utils';
import userEvent from '@testing-library/user-event';
import { TemplateApproval } from '../../../src/components/TenantAdmin/TemplateManagement/TemplateApproval';

describe('TemplateApproval', () => {
  const mockOnApprove = jest.fn();
  const mockOnReject = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Button Rendering', () => {
    it('renders approve and reject buttons', () => {
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      expect(screen.getByRole('button', { name: /approve template/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /reject template/i })).toBeInTheDocument();
    });

    it('disables approve button when template is invalid', () => {
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={false}
        />
      );
      
      expect(screen.getByRole('button', { name: /approve template/i })).toBeDisabled();
    });

    it('enables reject button even when template is invalid', () => {
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={false}
        />
      );
      
      expect(screen.getByRole('button', { name: /reject template/i })).not.toBeDisabled();
    });

    it('shows validation warning when template is invalid', () => {
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={false}
        />
      );
      
      expect(screen.getByText(/template has validation errors/i)).toBeInTheDocument();
      expect(screen.getByText(/fix them before approving/i)).toBeInTheDocument();
    });

    it('hides validation warning when template is valid', () => {
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      expect(screen.queryByText(/template has validation errors/i)).not.toBeInTheDocument();
    });
  });

  describe('Loading State', () => {
    it('shows loading state on approve button', () => {
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
          loading={true}
        />
      );
      
      expect(screen.getByText(/approving.../i)).toBeInTheDocument();
    });

    it('shows loading state on reject button', () => {
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
          loading={true}
        />
      );
      
      expect(screen.getByText(/rejecting.../i)).toBeInTheDocument();
    });

    it('disables both buttons when loading', () => {
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
          loading={true}
        />
      );
      
      expect(screen.getByRole('button', { name: /approving.../i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /rejecting.../i })).toBeDisabled();
    });
  });

  describe('Disabled State', () => {
    it('disables both buttons when disabled prop is true', () => {
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
          disabled={true}
        />
      );
      
      expect(screen.getByRole('button', { name: /approve template/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /reject template/i })).toBeDisabled();
    });
  });

  describe('Approve Dialog', () => {
    it('opens approve dialog when approve button is clicked', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const approveButton = screen.getByRole('button', { name: /approve template/i });
      await user.click(approveButton);
      
      expect(screen.getByText(/approve template/i)).toBeInTheDocument();
      expect(screen.getByText(/save the template to google drive/i)).toBeInTheDocument();
    });

    it('does not open dialog when template is invalid', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={false}
        />
      );
      
      const approveButton = screen.getByRole('button', { name: /approve template/i });
      await user.click(approveButton);
      
      expect(screen.queryByText(/save the template to google drive/i)).not.toBeInTheDocument();
    });

    it('shows approval notes textarea', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const approveButton = screen.getByRole('button', { name: /approve template/i });
      await user.click(approveButton);
      
      expect(screen.getByLabelText(/approval notes/i)).toBeInTheDocument();
    });

    it('shows what happens next information', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const approveButton = screen.getByRole('button', { name: /approve template/i });
      await user.click(approveButton);
      
      expect(screen.getByText(/what happens next:/i)).toBeInTheDocument();
      expect(screen.getByText(/saved to your google drive/i)).toBeInTheDocument();
      expect(screen.getByText(/previous version will be archived/i)).toBeInTheDocument();
      expect(screen.getByText(/become active immediately/i)).toBeInTheDocument();
    });

    it('allows entering approval notes', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const approveButton = screen.getByRole('button', { name: /approve template/i });
      await user.click(approveButton);
      
      const textarea = screen.getByLabelText(/approval notes/i);
      await user.type(textarea, 'Updated branding');
      
      expect(textarea).toHaveValue('Updated branding');
    });

    it('calls onApprove without notes when confirmed', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const approveButton = screen.getByRole('button', { name: /approve template/i });
      await user.click(approveButton);
      
      const confirmButton = screen.getByRole('button', { name: /confirm approval/i });
      await user.click(confirmButton);
      
      expect(mockOnApprove).toHaveBeenCalledWith(undefined);
    });

    it('calls onApprove with notes when provided', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const approveButton = screen.getByRole('button', { name: /approve template/i });
      await user.click(approveButton);
      
      const textarea = screen.getByLabelText(/approval notes/i);
      await user.type(textarea, 'Updated branding');
      
      const confirmButton = screen.getByRole('button', { name: /confirm approval/i });
      await user.click(confirmButton);
      
      expect(mockOnApprove).toHaveBeenCalledWith('Updated branding');
    });

    it('closes dialog when cancel is clicked', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const approveButton = screen.getByRole('button', { name: /approve template/i });
      await user.click(approveButton);
      
      const cancelButton = screen.getAllByRole('button', { name: /cancel/i })[0];
      await user.click(cancelButton);
      
      await waitFor(() => {
        expect(screen.queryByText(/save the template to google drive/i)).not.toBeInTheDocument();
      });
    });

    it('clears notes when dialog is closed', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      // Open dialog and enter notes
      const approveButton = screen.getByRole('button', { name: /approve template/i });
      await user.click(approveButton);
      
      const textarea = screen.getByLabelText(/approval notes/i);
      await user.type(textarea, 'Test notes');
      
      // Close dialog
      const cancelButton = screen.getAllByRole('button', { name: /cancel/i })[0];
      await user.click(cancelButton);
      
      // Reopen dialog
      await user.click(approveButton);
      
      // Notes should be cleared
      const newTextarea = screen.getByLabelText(/approval notes/i);
      expect(newTextarea).toHaveValue('');
    });
  });

  describe('Reject Dialog', () => {
    it('opens reject dialog when reject button is clicked', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const rejectButton = screen.getByRole('button', { name: /reject template/i });
      await user.click(rejectButton);
      
      expect(screen.getByText(/reject template/i)).toBeInTheDocument();
      expect(screen.getByText(/discard the template without saving/i)).toBeInTheDocument();
    });

    it('shows rejection reason textarea', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const rejectButton = screen.getByRole('button', { name: /reject template/i });
      await user.click(rejectButton);
      
      expect(screen.getByLabelText(/rejection reason/i)).toBeInTheDocument();
    });

    it('shows what happens next information', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const rejectButton = screen.getByRole('button', { name: /reject template/i });
      await user.click(rejectButton);
      
      expect(screen.getByText(/what happens next:/i)).toBeInTheDocument();
      expect(screen.getByText(/template will not be saved/i)).toBeInTheDocument();
      expect(screen.getByText(/current active template remains unchanged/i)).toBeInTheDocument();
    });

    it('allows entering rejection reason', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const rejectButton = screen.getByRole('button', { name: /reject template/i });
      await user.click(rejectButton);
      
      const textarea = screen.getByLabelText(/rejection reason/i);
      await user.type(textarea, 'Does not meet brand guidelines');
      
      expect(textarea).toHaveValue('Does not meet brand guidelines');
    });

    it('calls onReject without reason when confirmed', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const rejectButton = screen.getByRole('button', { name: /reject template/i });
      await user.click(rejectButton);
      
      const confirmButton = screen.getByRole('button', { name: /confirm rejection/i });
      await user.click(confirmButton);
      
      expect(mockOnReject).toHaveBeenCalledWith(undefined);
    });

    it('calls onReject with reason when provided', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const rejectButton = screen.getByRole('button', { name: /reject template/i });
      await user.click(rejectButton);
      
      const textarea = screen.getByLabelText(/rejection reason/i);
      await user.type(textarea, 'Missing required fields');
      
      const confirmButton = screen.getByRole('button', { name: /confirm rejection/i });
      await user.click(confirmButton);
      
      expect(mockOnReject).toHaveBeenCalledWith('Missing required fields');
    });

    it('closes dialog when cancel is clicked', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const rejectButton = screen.getByRole('button', { name: /reject template/i });
      await user.click(rejectButton);
      
      const cancelButton = screen.getAllByRole('button', { name: /cancel/i })[0];
      await user.click(cancelButton);
      
      await waitFor(() => {
        expect(screen.queryByText(/discard the template without saving/i)).not.toBeInTheDocument();
      });
    });

    it('clears reason when dialog is closed', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      // Open dialog and enter reason
      const rejectButton = screen.getByRole('button', { name: /reject template/i });
      await user.click(rejectButton);
      
      const textarea = screen.getByLabelText(/rejection reason/i);
      await user.type(textarea, 'Test reason');
      
      // Close dialog
      const cancelButton = screen.getAllByRole('button', { name: /cancel/i })[0];
      await user.click(cancelButton);
      
      // Reopen dialog
      await user.click(rejectButton);
      
      // Reason should be cleared
      const newTextarea = screen.getByLabelText(/rejection reason/i);
      expect(newTextarea).toHaveValue('');
    });
  });

  describe('Dialog Styling', () => {
    it('uses green border for approve dialog', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const approveButton = screen.getByRole('button', { name: /approve template/i });
      await user.click(approveButton);
      
      const dialog = screen.getByText(/save the template to google drive/i).closest('[role="dialog"]');
      expect(dialog).toHaveStyle({ borderColor: expect.stringContaining('green') });
    });

    it('uses red border for reject dialog', async () => {
      const user = userEvent.setup();
      render(
        <TemplateApproval
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          isValid={true}
        />
      );
      
      const rejectButton = screen.getByRole('button', { name: /reject template/i });
      await user.click(rejectButton);
      
      const dialog = screen.getByText(/discard the template without saving/i).closest('[role="dialog"]');
      expect(dialog).toHaveStyle({ borderColor: expect.stringContaining('red') });
    });
  });
});

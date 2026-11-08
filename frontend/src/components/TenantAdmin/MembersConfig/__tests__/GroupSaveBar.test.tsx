/**
 * Tests for GroupSaveBar — the consistent per-group save footer (grouped per-group-save redesign,
 * Task 1).
 *
 * The bar is presentational: it renders a dirty-gated "unsaved" marker, a Save button that is
 * disabled when clean or saving, and an optional inline error slot. These assert that contract so
 * every authoring group's footer behaves identically.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '../../../../test-utils';
import { GroupSaveBar } from '../GroupSaveBar';

describe('GroupSaveBar', () => {
  it('disables Save and hides the unsaved marker when clean', () => {
    render(<GroupSaveBar dirty={false} onSave={vi.fn()} lang="en" data-testid="bar" />);
    expect(screen.getByTestId('bar-save')).toBeDisabled();
    expect(screen.queryByTestId('bar-unsaved')).not.toBeInTheDocument();
  });

  it('enables Save and shows the unsaved marker when dirty', () => {
    render(<GroupSaveBar dirty onSave={vi.fn()} lang="en" data-testid="bar" />);
    expect(screen.getByTestId('bar-save')).toBeEnabled();
    expect(screen.getByTestId('bar-unsaved')).toBeInTheDocument();
  });

  it('calls onSave when the enabled button is clicked', () => {
    const onSave = vi.fn();
    render(<GroupSaveBar dirty onSave={onSave} lang="en" data-testid="bar" />);
    fireEvent.click(screen.getByTestId('bar-save'));
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('shows a loading state and keeps the button disabled while saving', () => {
    render(<GroupSaveBar dirty saving onSave={vi.fn()} lang="en" data-testid="bar" />);
    // isLoading renders a spinner and disables the button.
    expect(screen.getByTestId('bar-save')).toBeDisabled();
  });

  it('renders an inline error when error is set, and none otherwise', () => {
    const { rerender } = render(
      <GroupSaveBar dirty onSave={vi.fn()} error="Slug is already taken" lang="en" data-testid="bar" />,
    );
    expect(screen.getByTestId('bar-error')).toHaveTextContent('Slug is already taken');

    rerender(<GroupSaveBar dirty onSave={vi.fn()} error={null} lang="en" data-testid="bar" />);
    expect(screen.queryByTestId('bar-error')).not.toBeInTheDocument();
  });

  it('uses a custom label when provided', () => {
    render(
      <GroupSaveBar dirty onSave={vi.fn()} label="Save address" lang="en" data-testid="bar" />,
    );
    expect(screen.getByTestId('bar-save')).toHaveTextContent('Save address');
  });
});

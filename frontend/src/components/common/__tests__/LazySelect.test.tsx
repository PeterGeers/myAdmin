/**
 * Unit tests for the LazySelect component.
 *
 * Covers the design's Testing Strategy (Unit) for the always-searchable, tolerate-legacy combobox:
 *   - rest label: in-set → option label; out-of-set → raw value (never the placeholder); empty →
 *     placeholder (R1.1/R1.2/R1.3/R1.4);
 *   - disabled AND read-only → plain text, no combobox role, never opens (R1.5/R2.5);
 *   - open triggers: click / Enter / Space / ArrowDown each open the listbox (R2.2);
 *   - type-to-filter narrows visible options by case-insensitive substring (R2.3);
 *   - close-without-change: Escape / outside click / blur close and never call onChange; Escape
 *     restores focus to the trigger (R2.4);
 *   - pick emits exactly the option value and closes (R3.1);
 *   - filterOption hides options; an out-of-set current value never appears as a selectable option
 *     (R5.1/R5.2);
 *   - async: loading (spinner) while pending, error row (role="alert") on rejection, rest value still
 *     shown during both (R4.2/R4.3);
 *   - ARIA: combobox trigger with aria-expanded/aria-controls; listbox; options with aria-selected on
 *     the current value (R6.1/R6.2).
 *
 * `render` comes from `@/test-utils`; Chakra is auto-mocked. Async sources are plain `vi.fn()`s
 * returning a resolved/rejected Promise — no real network.
 *
 * @see .kiro/specs/Common/Frameworks/lazy-select/design.md
 * _Requirements: 1, 2, 3, 5, 6, 7_
 */

import React from 'react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@/test-utils';
import '../../../i18n';
import { LazySelect } from '../LazySelect';
import type { LazyOption } from '../lazySelect.types';

const OPTIONS: LazyOption[] = [
  { value: 'a', label: 'Alpha' },
  { value: 'b', label: 'Beta' },
  { value: 'g', label: 'Gamma' },
];

/** Convenience render with sensible defaults; overrides win. */
function renderSelect(props: Partial<React.ComponentProps<typeof LazySelect>> = {}) {
  const onChange = props.onChange ?? vi.fn();
  const utils = render(
    <LazySelect
      value=""
      onChange={onChange}
      options={OPTIONS}
      label="Fruit"
      placeholder="Pick one"
      name="fruit"
      {...props}
    />,
  );
  return { onChange, ...utils };
}

describe('LazySelect', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── R1: rest-state display ──────────────────────────────────────────────────
  describe('rest-state display', () => {
    it('shows the option label when the value is in the set', () => {
      renderSelect({ value: 'a' });
      expect(screen.getByText('Alpha')).toBeInTheDocument();
      expect(screen.queryByText('Pick one')).not.toBeInTheDocument();
    });

    it('shows the raw value (not the placeholder) when the value is out of the set', () => {
      renderSelect({ value: 'legacy-region' });
      expect(screen.getByText('legacy-region')).toBeInTheDocument();
      expect(screen.queryByText('Pick one')).not.toBeInTheDocument();
    });

    it('shows the placeholder when the value is empty', () => {
      renderSelect({ value: '' });
      expect(screen.getByText('Pick one')).toBeInTheDocument();
    });
  });

  // ── R1.5 / R2.5: disabled AND read-only ─────────────────────────────────────
  describe('disabled and read-only', () => {
    it('renders plain text with no combobox role', () => {
      renderSelect({ value: 'a', isDisabled: true, isReadOnly: true });
      expect(screen.getByText('Alpha')).toBeInTheDocument();
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    });

    it('does not open on click', () => {
      renderSelect({ value: 'a', isDisabled: true, isReadOnly: true });
      // No combobox to click; the plain text container carries the value.
      fireEvent.click(screen.getByText('Alpha'));
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    it('disabled-only still renders plain text and no combobox', () => {
      renderSelect({ value: 'a', isDisabled: true });
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
      expect(screen.getByText('Alpha')).toBeInTheDocument();
    });

    it('read-only-only still renders plain text and no combobox', () => {
      renderSelect({ value: 'a', isReadOnly: true });
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
      expect(screen.getByText('Alpha')).toBeInTheDocument();
    });
  });

  // ── R2.2: open triggers ─────────────────────────────────────────────────────
  describe('open triggers', () => {
    it('opens on click', () => {
      renderSelect();
      fireEvent.click(screen.getByRole('combobox'));
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    it('opens on Enter', () => {
      renderSelect();
      fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' });
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    it('opens on Space', () => {
      renderSelect();
      fireEvent.keyDown(screen.getByRole('combobox'), { key: ' ' });
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    it('opens on ArrowDown', () => {
      renderSelect();
      fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    it('renders all options as role="option" when open', () => {
      renderSelect();
      fireEvent.click(screen.getByRole('combobox'));
      expect(screen.getAllByRole('option')).toHaveLength(OPTIONS.length);
    });
  });

  // ── R2.3: type-to-filter ────────────────────────────────────────────────────
  describe('type-to-filter', () => {
    it('narrows visible options by case-insensitive substring on the label', () => {
      renderSelect();
      fireEvent.click(screen.getByRole('combobox'));
      const search = screen.getByPlaceholderText('Type to search...');

      fireEvent.change(search, { target: { value: 'a' } });
      // "a" is in Alpha, Beta, and Gamma.
      expect(screen.getAllByRole('option')).toHaveLength(3);

      fireEvent.change(search, { target: { value: 'BET' } });
      const options = screen.getAllByRole('option');
      expect(options).toHaveLength(1);
      expect(options[0]).toHaveTextContent('Beta');
    });

    it('shows a no-options row when nothing matches', () => {
      renderSelect();
      fireEvent.click(screen.getByRole('combobox'));
      fireEvent.change(screen.getByPlaceholderText('Type to search...'), {
        target: { value: 'zzz' },
      });
      expect(screen.queryAllByRole('option')).toHaveLength(0);
      expect(screen.getByText('No options available')).toBeInTheDocument();
    });
  });

  // ── R2.4: close without change ──────────────────────────────────────────────
  describe('close without change', () => {
    it('Escape closes without calling onChange and restores focus to the trigger', () => {
      const { onChange } = renderSelect({ value: 'a' });
      const trigger = screen.getByRole('combobox');
      fireEvent.click(trigger);
      const search = screen.getByPlaceholderText('Type to search...');

      fireEvent.keyDown(search, { key: 'Escape' });

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      expect(onChange).not.toHaveBeenCalled();
      expect(trigger).toHaveFocus();
    });

    it('outside click closes without calling onChange', () => {
      const { onChange } = renderSelect({ value: 'a' });
      fireEvent.click(screen.getByRole('combobox'));
      expect(screen.getByRole('listbox')).toBeInTheDocument();

      fireEvent.mouseDown(document.body);

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      expect(onChange).not.toHaveBeenCalled();
    });
  });

  // ── R3.1: pick emits value + closes ─────────────────────────────────────────
  describe('pick emits value and closes', () => {
    it('selecting an option calls onChange with exactly that value and closes', () => {
      const { onChange } = renderSelect();
      fireEvent.click(screen.getByRole('combobox'));

      const beta = screen.getByRole('option', { name: 'Beta' });
      fireEvent.mouseDown(beta);

      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenCalledWith('b');
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    it('selecting the active option via Enter emits its value', () => {
      const { onChange } = renderSelect();
      fireEvent.click(screen.getByRole('combobox'));
      const search = screen.getByPlaceholderText('Type to search...');

      // Arrow to the first option, then Enter.
      fireEvent.keyDown(search, { key: 'ArrowDown' });
      fireEvent.keyDown(search, { key: 'Enter' });

      expect(onChange).toHaveBeenCalledWith('a');
    });
  });

  // ── R5: filterOption + out-of-set value never selectable ────────────────────
  describe('filterOption and out-of-set value', () => {
    it('only renders options that satisfy filterOption', () => {
      renderSelect({ filterOption: (o) => o.value !== 'b' });
      fireEvent.click(screen.getByRole('combobox'));
      const labels = screen.getAllByRole('option').map((o) => o.textContent);
      expect(labels).toEqual(['Alpha', 'Gamma']);
      expect(screen.queryByRole('option', { name: 'Beta' })).not.toBeInTheDocument();
    });

    it('an out-of-set current value is displayed at rest but never offered as an option', () => {
      renderSelect({ value: 'legacy-region' });
      // Displayed at rest.
      expect(screen.getByText('legacy-region')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('combobox'));
      // Not present as a selectable option.
      const labels = screen.getAllByRole('option').map((o) => o.textContent);
      expect(labels).toEqual(['Alpha', 'Beta', 'Gamma']);
      expect(screen.queryByRole('option', { name: 'legacy-region' })).not.toBeInTheDocument();
    });

    it('a role-gated current value stays displayed but is not selectable', () => {
      renderSelect({ value: 'b', filterOption: (o) => o.value !== 'b' });
      // The current value 'b' (Beta) is still shown at rest via its in-set label.
      expect(screen.getByText('Beta')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('combobox'));
      // But Beta is filtered out of the selectable list.
      expect(screen.queryByRole('option', { name: 'Beta' })).not.toBeInTheDocument();
    });
  });

  // ── R4.2 / R4.3: async loading + error rows ─────────────────────────────────
  describe('async options', () => {
    it('shows a loading spinner while the source is pending; rest value still shown', () => {
      let resolveFn: (v: LazyOption[]) => void = () => {};
      const source = vi.fn(
        () => new Promise<LazyOption[]>((resolve) => { resolveFn = resolve; }),
      );

      renderSelect({ value: 'legacy', options: source });
      // Rest value shown before opening.
      expect(screen.getByText('legacy')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('combobox'));

      // Loading row present while pending.
      expect(screen.getByRole('status')).toBeInTheDocument();
      expect(screen.getByText('Loading...')).toBeInTheDocument();
      // Rest value still displayed inside the trigger.
      expect(screen.getByText('legacy')).toBeInTheDocument();

      // Prevent an unhandled resolution warning.
      resolveFn(OPTIONS);
    });

    it('renders resolved options after the source settles', async () => {
      const source = vi.fn().mockResolvedValue(OPTIONS);
      renderSelect({ options: source });
      fireEvent.click(screen.getByRole('combobox'));

      await waitFor(() => {
        expect(screen.getAllByRole('option')).toHaveLength(OPTIONS.length);
      });
      expect(source).toHaveBeenCalledTimes(1);
    });

    it('shows a non-blocking error row (role="alert") on rejection; rest value still shown', async () => {
      const source = vi.fn().mockRejectedValue(new Error('feed down'));
      renderSelect({ value: 'legacy', options: source });

      expect(screen.getByText('legacy')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('combobox'));

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      });
      // Rest value still displayed despite the error.
      expect(screen.getByText('legacy')).toBeInTheDocument();
    });
  });

  // ── R6: ARIA ────────────────────────────────────────────────────────────────
  describe('ARIA', () => {
    it('trigger exposes role=combobox with aria-expanded and aria-controls', () => {
      renderSelect();
      const trigger = screen.getByRole('combobox');
      expect(trigger).toHaveAttribute('aria-expanded', 'false');
      const controls = trigger.getAttribute('aria-controls');
      expect(controls).toBeTruthy();

      fireEvent.click(trigger);
      expect(trigger).toHaveAttribute('aria-expanded', 'true');

      const listbox = screen.getByRole('listbox');
      expect(listbox).toHaveAttribute('id', controls);
    });

    it('marks the current value option with aria-selected=true and others false', () => {
      renderSelect({ value: 'b' });
      fireEvent.click(screen.getByRole('combobox'));

      const beta = screen.getByRole('option', { name: 'Beta' });
      const alpha = screen.getByRole('option', { name: 'Alpha' });
      expect(beta).toHaveAttribute('aria-selected', 'true');
      expect(alpha).toHaveAttribute('aria-selected', 'false');
    });

    it('has an accessible name derived from the label', () => {
      renderSelect();
      expect(screen.getByRole('combobox', { name: 'Fruit' })).toBeInTheDocument();
      fireEvent.click(screen.getByRole('combobox'));
      expect(screen.getByRole('listbox', { name: 'Fruit' })).toBeInTheDocument();
    });
  });
});

/**
 * Property-based tests for the LazySelect component.
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations and the 30000ms timeout convention
 * (`33-frontend-testing.md`, Requirement 9.5). These encode the four Correctness Properties from
 * design.md as universal invariants over arbitrary values + option sets:
 *
 *   1. Value Preservation (R9.1 / R1.1): for any NON-EMPTY value and any option set, the rest-state
 *      displayed text is non-empty and is never the placeholder — the display equals the in-set
 *      option label, or the raw value when the value is out of the set.
 *   2. No Silent Coercion (R9.2 / R3.2): for any value and option set, rendering then closing
 *      WITHOUT a user selection (Escape or outside click) leaves `onChange` uncalled — the value the
 *      parent holds is unchanged.
 *   3. Pick Fidelity (R9.3 / R3.1): for any option the caller may pick, selecting it calls `onChange`
 *      with exactly that option's value.
 *   4. Filter Soundness (R9.4 / R5.2): for any option set and any caller `filterOption`, every option
 *      OFFERED in the open list satisfies the filter, AND a current out-of-set value never appears as
 *      a selectable option.
 *
 * `render` comes from `@/test-utils`; Chakra is auto-mocked. `../../../i18n` is imported so the
 * translated placeholder / status text resolves (as the unit test does).
 *
 * The RTL render/act cycle is synchronous here (array option sources → no async settle), so — matching
 * the useLazyOptions.property.test.ts convention — each property runs as a loop over `fc.sample(arb,
 * 100)` inputs rather than inside `fc.assert`. Every iteration unmounts to avoid DOM/handler leakage.
 *
 * @see .kiro/specs/Common/Frameworks/lazy-select/design.md
 * _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 1.1, 3.1, 3.2, 5.2_
 */

import React from 'react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@/test-utils';
import fc from 'fast-check';
import '../../../i18n';
import { LazySelect } from '../LazySelect';
import type { LazyOption } from '../lazySelect.types';

// Property-based tests loop many renders; keep the extended timeout (Requirement 9.5).
vi.setConfig({ testTimeout: 30000 });

beforeEach(() => {
  vi.clearAllMocks();
});

const RUNS = 100;

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/**
 * A "token" character set with NO whitespace. Whitespace in a display label is collapsed/trimmed by
 * Testing Library's text normalization, which would break exact `getByText` / `getByRole({ name })`
 * lookups — so we constrain generated tokens to non-space characters. This is purely about making the
 * generated display strings well-formed for lookup; it does not narrow any property's input space in
 * a way that matters to the invariants (values/labels are arbitrary opaque strings either way).
 */
const tokenArbitrary: fc.Arbitrary<string> = fc.stringMatching(/^[A-Za-z0-9._-]{1,6}$/);

/**
 * An option array with UNIQUE `value`s and UNIQUE plain-string `label`s. Uniqueness keeps react keys
 * and `getByRole('option', { name })` lookups unambiguous. We build the labels/values from a set of
 * unique base tokens, then decorate each with its index so both fields stay distinct even if two
 * tokens collide.
 */
const optionSetArbitrary: fc.Arbitrary<LazyOption[]> = fc
  .uniqueArray(tokenArbitrary, { minLength: 0, maxLength: 6 })
  .map((tokens) =>
    tokens.map((tok, i): LazyOption => ({
      value: `v${i}_${tok}`,
      label: `L${i}_${tok}`,
    })),
  );

/** A non-empty current value: either picked from the set (in-set) or a distinct out-of-set string. */
function valueArbitrary(options: LazyOption[]): fc.Arbitrary<string> {
  const outOfSet = tokenArbitrary
    .map((s) => `oos_${s}`)
    .filter((v) => !options.some((o) => o.value === v));
  if (options.length === 0) return outOfSet;
  return fc.oneof(fc.constantFrom(...options.map((o) => o.value)), outOfSet);
}

/** The display label the component shows for an in-set option (plain string labels here). */
function labelOf(opt: LazyOption): string {
  return typeof opt.label === 'string' ? opt.label : opt.value;
}

// ---------------------------------------------------------------------------
// Property 1: Value Preservation (R9.1 / R1.1)
// ---------------------------------------------------------------------------

describe('LazySelect property: Value Preservation', () => {
  /**
   * **Validates: Requirements 9.1, 1.1**
   *
   * For any NON-EMPTY value and any option set, the rest-state trigger shows non-empty text that is
   * never the placeholder: the in-set option's label, or the raw value when out of the set.
   */
  it('never blanks (or placeholder-substitutes) a non-empty value at rest', () => {
    const inputs = fc.sample(
      optionSetArbitrary.chain((options) =>
        valueArbitrary(options).map((value) => ({ options, value })),
      ),
      RUNS,
    );

    for (const { options, value } of inputs) {
      const placeholder = 'PLACEHOLDER_SENTINEL';
      const { unmount } = render(
        <LazySelect
          value={value}
          onChange={vi.fn()}
          options={options}
          label="Field"
          placeholder={placeholder}
          name="vp"
        />,
      );

      const trigger = screen.getByRole('combobox');
      // Placeholder must NOT be shown for a non-empty value.
      expect(within(trigger).queryByText(placeholder)).not.toBeInTheDocument();

      // The exact rest display: in-set → label; out-of-set → raw value.
      const inSet = options.find((o) => o.value === value);
      const expected = inSet ? labelOf(inSet) : value;
      expect(within(trigger).getByText(expected)).toBeInTheDocument();

      unmount();
    }
  });
});

// ---------------------------------------------------------------------------
// Property 2: No Silent Coercion (R9.2 / R3.2)
// ---------------------------------------------------------------------------

describe('LazySelect property: No Silent Coercion', () => {
  /**
   * **Validates: Requirements 9.2, 3.2**
   *
   * For any value and option set, rendering then closing WITHOUT a selection (Escape or outside
   * click) never calls `onChange` — the parent's value is left unchanged.
   */
  it('emits no onChange when opened and closed without a selection', () => {
    const inputs = fc.sample(
      optionSetArbitrary.chain((options) =>
        fc
          .tuple(valueArbitrary(options), fc.boolean())
          .map(([value, viaEscape]) => ({ options, value, viaEscape })),
      ),
      RUNS,
    );

    for (const { options, value, viaEscape } of inputs) {
      const onChange = vi.fn();
      const { unmount } = render(
        <LazySelect
          value={value}
          onChange={onChange}
          options={options}
          label="Field"
          placeholder="Pick"
          name="nsc"
        />,
      );

      // Open the list.
      fireEvent.click(screen.getByRole('combobox'));
      expect(screen.getByRole('listbox')).toBeInTheDocument();

      // Close WITHOUT selecting: Escape on the search box, or an outside pointerdown.
      if (viaEscape) {
        fireEvent.keyDown(screen.getByPlaceholderText('Type to search...'), { key: 'Escape' });
      } else {
        fireEvent.mouseDown(document.body);
      }

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      expect(onChange).not.toHaveBeenCalled();

      unmount();
    }
  });
});

// ---------------------------------------------------------------------------
// Property 3: Pick Fidelity (R9.3 / R3.1)
// ---------------------------------------------------------------------------

describe('LazySelect property: Pick Fidelity', () => {
  /**
   * **Validates: Requirements 9.3, 3.1**
   *
   * For any option the caller may pick (drawn from the generated set), selecting it calls `onChange`
   * with exactly that option's value.
   */
  it('emits exactly the selected option value', () => {
    const inputs = fc.sample(
      optionSetArbitrary
        // Need at least one option to pick.
        .filter((options) => options.length > 0)
        .chain((options) =>
          fc.integer({ min: 0, max: options.length - 1 }).map((pickIdx) => ({ options, pickIdx })),
        ),
      RUNS,
    );

    for (const { options, pickIdx } of inputs) {
      const onChange = vi.fn();
      const { unmount } = render(
        <LazySelect
          value=""
          onChange={onChange}
          options={options}
          label="Field"
          placeholder="Pick"
          name="pf"
        />,
      );

      fireEvent.click(screen.getByRole('combobox'));

      const target = options[pickIdx];
      const optionEl = screen.getByRole('option', { name: labelOf(target) });
      // mousedown drives selection (fires before the outside-click close).
      fireEvent.mouseDown(optionEl);

      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenCalledWith(target.value);
      // List closes on pick.
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

      unmount();
    }
  });
});

// ---------------------------------------------------------------------------
// Property 4: Filter Soundness (R9.4 / R5.2)
// ---------------------------------------------------------------------------

describe('LazySelect property: Filter Soundness', () => {
  /**
   * **Validates: Requirements 9.4, 5.2**
   *
   * For any option set and any caller `filterOption`, every option OFFERED in the open list satisfies
   * the filter, and a current out-of-set value never appears as a selectable option.
   *
   * The arbitrary filter is modelled as an allow-set over option values: `filterOption` permits an
   * option iff its value is in the allow-set. The current value is forced OUT of the set (a distinct
   * `oos_` string) so the "out-of-set value never selectable" half is always meaningfully exercised.
   */
  it('only offers filter-satisfying options and never offers the out-of-set value', () => {
    const inputs = fc.sample(
      optionSetArbitrary.chain((options) =>
        fc
          .tuple(
            // A subset of indices that the filter permits.
            fc.subarray(options.map((_, i) => i)),
            tokenArbitrary,
          )
          .map(([allowedIdx, oosSuffix]) => ({
            options,
            allowedValues: new Set(allowedIdx.map((i) => options[i].value)),
            outOfSetValue: `oos_${oosSuffix}`,
          }))
          // Keep the current value genuinely out of the set.
          .filter(({ options: opts, outOfSetValue }) => !opts.some((o) => o.value === outOfSetValue)),
      ),
      RUNS,
    );

    for (const { options, allowedValues, outOfSetValue } of inputs) {
      const filterOption = (o: LazyOption) => allowedValues.has(o.value);
      const { unmount } = render(
        <LazySelect
          value={outOfSetValue}
          onChange={vi.fn()}
          options={options}
          filterOption={filterOption}
          label="Field"
          placeholder="Pick"
          name="fs"
        />,
      );

      fireEvent.click(screen.getByRole('combobox'));

      const offered = screen.queryAllByRole('option');
      const offeredLabels = offered.map((el) => el.textContent);

      // Every offered option must satisfy the filter.
      const permittedLabels = options.filter(filterOption).map((o) => labelOf(o));
      expect(offeredLabels.sort()).toEqual(permittedLabels.sort());

      // The out-of-set current value is never offered as a selectable option.
      expect(offeredLabels).not.toContain(outOfSetValue);
      expect(
        screen.queryByRole('option', { name: outOfSetValue }),
      ).not.toBeInTheDocument();

      unmount();
    }
  });
});

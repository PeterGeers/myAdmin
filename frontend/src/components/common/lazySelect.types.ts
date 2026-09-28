import type React from 'react';

/**
 * Shared prop/option types for the `LazySelect` building block.
 *
 * `LazySelect` is a single-value, always-searchable dropdown that tolerates a legacy /
 * out-of-set current value (never blanks or coerces it) and accepts options either as an
 * eager array or as a (possibly async) function. See the spec at
 * `.kiro/specs/Common/Frameworks/lazy-select/`.
 */

/** A single selectable option. `label` may be a plain string or a localized map. */
export interface LazyOption<V extends string = string> {
  value: V;
  label?: string | Record<string, string>;
  /** Optional roles permitted to SELECT this option (convenience filter; server authoritative). */
  roles?: string[];
  /** Optionally disable an individual option. */
  disabled?: boolean;
}

/**
 * Options are EITHER an array OR a function returning (a Promise of) an array. That is the whole
 * source model — enum, API feed, SQL query, and external service all fit these two shapes.
 */
export type LazyOptionsSource<V extends string = string> =
  | LazyOption<V>[]
  | (() => Promise<LazyOption<V>[]> | LazyOption<V>[]);

export interface LazySelectProps<V extends string = string> {
  value: V | ''; // always displayed at rest (R1)
  onChange: (value: V) => void; // called on pick (R3)
  options: LazyOptionsSource<V>; // array or async fn (R4)
  optionsDepKey?: string; // re-resolve when this changes (R4.4)

  label: string; // accessible + field label (R6.4)
  placeholder?: string; // shown only when value empty (R1.4)
  filterOption?: (opt: LazyOption<V>) => boolean; // convenience filter, e.g. by role (R5)
  getOptionLabel?: (opt: LazyOption<V>) => string; // default: label/localized/value
  renderMissingValue?: (value: V) => React.ReactNode; // default: raw value text (R1.3)

  isDisabled?: boolean;
  isReadOnly?: boolean;
  isInvalid?: boolean;
  size?: 'sm' | 'md' | 'lg';
  bg?: string;
  color?: string;
  borderColor?: string; // dark-theme defaults otherwise (R7)
  width?: string | Record<string, string>;
  name?: string; // test id / Formik binding
}

export interface UseLazyOptionsResult<V extends string = string> {
  options: LazyOption<V>[];
  isLoading: boolean;
  error: Error | null;
  ensureLoaded: () => void; // idempotent; resolves on first call (or after depKey change)
  reload: () => void; // force re-resolve
}

/**
 * Resolve an option's display label to a plain string, matching the Members `resolveLabel`
 * convention (`components/members/fieldForm.ts`): a localized `Record<string, string>` map picks
 * the current `lang` with an `nl`/`en` fallback chain; a plain string passes through; otherwise we
 * fall back to the option's raw `value`.
 *
 * A caller-supplied `getOptionLabel` takes precedence over the built-in resolution (R1.2).
 */
export function resolveOptionLabel<V extends string = string>(
  opt: LazyOption<V>,
  getOptionLabel?: (opt: LazyOption<V>) => string,
  lang?: string,
): string {
  if (getOptionLabel) return getOptionLabel(opt);

  const { label, value } = opt;
  if (label == null) return value;
  if (typeof label === 'string') return label;

  const l = lang ?? 'nl';
  return label[l] || label.nl || label.en || value;
}

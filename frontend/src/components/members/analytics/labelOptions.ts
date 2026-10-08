/**
 * labelOptions — the ONE shared address-label-options model (R6 / R3, task 6.3).
 *
 * R6 (interactive "Generate address labels" action) and R3's stored `to_fixed` +
 * `pdf_labels` delivery both need to describe HOW a batch of Avery labels is laid
 * out: which stock format, how to sort, font size, alignment, border, country
 * line, and the start cell on a partial sheet. The requirements are explicit —
 * **share ONE label-options model, do not fork two** (R6 "Share one label-options
 * model with R3's `to_fixed` + labels delivery"; design §2.1 "`label_options` is
 * the SAME shape R6 uses interactively (one label-options model, not two)").
 *
 * This module is that single definition. It does NOT invent a parallel shape: it
 * is built directly on the existing, shipped generator primitives in
 * {@link module:components/members/analytics/addressLabelService} —
 * {@link LabelStyleOptions} (the per-run style the interactive
 * {@link AddressLabelGenerator} already collects and
 * {@link generateAddressLabelPdf} already consumes) plus a format KEY (a
 * {@link LabelFormat.key}). So:
 *
 *   - **Interactive R6** uses {@link LabelOptions} as its in-memory options bag and
 *     feeds it straight to the generator via {@link toStyleOptions} +
 *     {@link resolveLabelFormat} — no translation layer of its own.
 *   - **Stored R3 delivery** persists the SAME options as the design's snake_case
 *     `label_options` block (`{ format, sort, font_size, alignment, border,
 *     country, start }`, design §2.1) via {@link toStored} / {@link fromStored}.
 *
 * The model carries only PLAIN, SERIALIZABLE scalars (no jsPDF doc, no resolved
 * `LabelFormat` object) so the stored form round-trips through DynamoDB
 * (`floats_to_decimal` already covers the numeric `font_size` / `start`, design
 * §2.1) and the interactive form is trivially React-state-friendly.
 *
 * @module components/members/analytics/labelOptions
 * @see .kiro/specs/Members/pivot-output-actions (requirements R3, R6; design §2.1, §7)
 */

import {
  AVERY_LABEL_FORMATS,
  DEFAULT_LABEL_FORMAT_KEY,
  MAX_FONT_SIZE,
  MIN_FONT_SIZE,
  clampFontSize,
  getLabelFormat,
  type LabelAlignment,
  type LabelFormat,
  type LabelSortOrder,
  type LabelStyleOptions,
} from './addressLabelService';

// Re-export the primitive unions so a consumer of the shared model never has to
// reach past it into the service for the alignment / sort / format vocabulary.
export type { LabelAlignment, LabelSortOrder, LabelFormat } from './addressLabelService';
export { MIN_FONT_SIZE, MAX_FONT_SIZE } from './addressLabelService';

/** The default font size (points) used when none is supplied. Matches the service clamp band. */
export const DEFAULT_LABEL_FONT_SIZE = 10;
/** The default alignment within a label cell. */
export const DEFAULT_LABEL_ALIGNMENT: LabelAlignment = 'left';
/** The default sort order applied before layout. */
export const DEFAULT_LABEL_SORT_ORDER: LabelSortOrder = 'name';

const ALIGNMENTS: readonly LabelAlignment[] = ['left', 'center', 'right'];
const SORT_ORDERS: readonly LabelSortOrder[] = ['name', 'postcode', 'region'];

/**
 * The ONE canonical, fully-resolved label-options model shared by interactive R6
 * and stored R3 (`pdf_labels`) delivery.
 *
 * It is the interactive-facing (camelCase) form: a format KEY plus every per-run
 * style with its default already applied, so there are no `undefined` holes to
 * reason about downstream. Build one from loose/partial input with
 * {@link normalizeLabelOptions}; convert to the generator's
 * {@link LabelStyleOptions} with {@link toStyleOptions}; persist/load the stored
 * snake_case form with {@link toStored} / {@link fromStored}.
 */
export interface LabelOptions {
  /** The Avery stock format key (a {@link LabelFormat.key}), e.g. `'L7160'`. */
  format: string;
  /** Sort order applied before layout. */
  sortOrder: LabelSortOrder;
  /** Font size in points, clamped to {@link MIN_FONT_SIZE}–{@link MAX_FONT_SIZE}. */
  fontSize: number;
  /** Text alignment within a cell. */
  alignment: LabelAlignment;
  /** Draw a thin cutting-guide border around each cell. */
  showBorder: boolean;
  /** Include the (uppercased) country line. */
  showCountry: boolean;
  /** Skip the first N label cells to reuse a partially used sheet (>= 0). */
  startPosition: number;
}

/**
 * The persisted (snake_case) form of {@link LabelOptions} exactly as design §2.1
 * stores it on the delivery block's `label_options` field:
 * `{ format, sort, font_size, alignment, border, country, start }`.
 *
 * This is the ONLY wire/stored vocabulary; it mirrors the SAM entity + its
 * `toBackendConfig`/`fromBackendConfig` convention (snake_case, plain scalars).
 */
export interface StoredLabelOptions {
  format: string;
  sort: LabelSortOrder;
  font_size: number;
  alignment: LabelAlignment;
  border: boolean;
  country: boolean;
  start: number;
}

/** The default label options (shipped format + sensible per-run defaults). */
export function defaultLabelOptions(): LabelOptions {
  return {
    format: DEFAULT_LABEL_FORMAT_KEY,
    sortOrder: DEFAULT_LABEL_SORT_ORDER,
    fontSize: DEFAULT_LABEL_FONT_SIZE,
    alignment: DEFAULT_LABEL_ALIGNMENT,
    showBorder: false,
    showCountry: true,
    startPosition: 0,
  };
}

/** A format key is valid only if it names a shipped Avery format. */
export function isValidFormatKey(key: unknown): key is string {
  return typeof key === 'string' && getLabelFormat(key) !== undefined;
}

function coerceAlignment(value: unknown): LabelAlignment {
  return ALIGNMENTS.includes(value as LabelAlignment)
    ? (value as LabelAlignment)
    : DEFAULT_LABEL_ALIGNMENT;
}

function coerceSortOrder(value: unknown): LabelSortOrder {
  return SORT_ORDERS.includes(value as LabelSortOrder)
    ? (value as LabelSortOrder)
    : DEFAULT_LABEL_SORT_ORDER;
}

function coerceStart(value: unknown): number {
  const n =
    typeof value === 'number'
      ? value
      : typeof value === 'string'
        ? Number.parseInt(value, 10)
        : NaN;
  if (!Number.isFinite(n) || n < 0) {
    return 0;
  }
  return Math.floor(n);
}

function coerceBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

/**
 * Build a complete, validated {@link LabelOptions} from loose/partial input —
 * the single normalizer BOTH sides use so interactive state and loaded stored
 * state are validated identically.
 *
 * - an unknown / absent `format` falls back to the shipped default
 *   ({@link DEFAULT_LABEL_FORMAT_KEY}) so a stale stored key can never produce an
 *   unresolvable format (design §7: generator falls back to the first shipped
 *   format);
 * - `fontSize` is clamped to the service's 8–12pt band ({@link clampFontSize});
 * - `startPosition` is coerced to a non-negative integer (the component clamps it
 *   further against the chosen format's cells-per-page at render time);
 * - unknown `alignment` / `sortOrder` fall back to their defaults.
 *
 * Pure; never mutates the input.
 */
export function normalizeLabelOptions(input?: Partial<LabelOptions> | null): LabelOptions {
  const src = input ?? {};
  return {
    format: isValidFormatKey(src.format) ? src.format : DEFAULT_LABEL_FORMAT_KEY,
    sortOrder: coerceSortOrder(src.sortOrder),
    fontSize: clampFontSize(src.fontSize),
    alignment: coerceAlignment(src.alignment),
    showBorder: coerceBoolean(src.showBorder, false),
    showCountry: coerceBoolean(src.showCountry, true),
    startPosition: coerceStart(src.startPosition),
  };
}

/**
 * Project the shared model onto the generator's {@link LabelStyleOptions} (the
 * per-run style {@link generateAddressLabelPdf} consumes). The `format` key is
 * resolved separately via {@link resolveLabelFormat} — the generator takes the
 * {@link LabelFormat} object as a distinct argument.
 */
export function toStyleOptions(options: LabelOptions): LabelStyleOptions {
  return {
    fontSize: options.fontSize,
    alignment: options.alignment,
    showBorder: options.showBorder,
    showCountry: options.showCountry,
    startPosition: options.startPosition,
    sortOrder: options.sortOrder,
  };
}

/**
 * Resolve the model's `format` key to a shipped {@link LabelFormat}, falling back
 * to the first shipped Avery format when the key is unknown (never returns
 * `undefined`, so the generator always has a grid).
 */
export function resolveLabelFormat(options: LabelOptions): LabelFormat {
  return getLabelFormat(options.format) ?? AVERY_LABEL_FORMATS[0];
}

/**
 * Serialize the shared model to the stored (snake_case) `label_options` block
 * exactly as design §2.1 persists it. Normalizes first so the stored form is
 * always complete + valid.
 */
export function toStored(options: LabelOptions): StoredLabelOptions {
  const o = normalizeLabelOptions(options);
  return {
    format: o.format,
    sort: o.sortOrder,
    font_size: o.fontSize,
    alignment: o.alignment,
    border: o.showBorder,
    country: o.showCountry,
    start: o.startPosition,
  };
}

/**
 * Load the shared model from a stored (snake_case) `label_options` block (or
 * `null`/absent on a legacy delivery). Normalizes so a partial / stale stored
 * block still yields a complete, valid model.
 */
export function fromStored(stored?: Partial<StoredLabelOptions> | null): LabelOptions {
  const s = stored ?? {};
  return normalizeLabelOptions({
    format: s.format,
    sortOrder: s.sort,
    fontSize: s.font_size,
    alignment: s.alignment,
    showBorder: s.border,
    showCountry: s.country,
    startPosition: s.start,
  });
}

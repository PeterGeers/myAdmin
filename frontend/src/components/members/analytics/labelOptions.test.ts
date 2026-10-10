/**
 * Unit matrix for the ONE shared label-options model (task 6.3).
 *
 * Proves the single `label_options` model shared by R6 (interactive) and R3's
 * stored `to_fixed` + `pdf_labels` delivery:
 *
 *   - `normalizeLabelOptions` fills defaults, clamps the font size to the service
 *     band, coerces an unknown format/alignment/sort to a safe value, and floors a
 *     negative/fractional start;
 *   - `toStyleOptions` + `resolveLabelFormat` feed the EXISTING generator shape
 *     (no parallel shape invented);
 *   - `toStored` / `fromStored` map to/from the design §2.1 snake_case persisted
 *     block (`{ format, sort, font_size, alignment, border, country, start }`) and
 *     round-trip losslessly — the single wire form both sides use.
 *
 * Pure (no React, no I/O): imports the model directly and asserts on returned
 * data.
 *
 * Validates: Requirements R3, R6
 */
import { describe, it, expect } from 'vitest';

import {
  DEFAULT_LABEL_ALIGNMENT,
  DEFAULT_LABEL_FONT_SIZE,
  DEFAULT_LABEL_SORT_ORDER,
  MAX_FONT_SIZE,
  MIN_FONT_SIZE,
  defaultLabelOptions,
  fromStored,
  isValidFormatKey,
  normalizeLabelOptions,
  resolveLabelFormat,
  toStored,
  toStyleOptions,
  type LabelOptions,
  type StoredLabelOptions,
} from './labelOptions';
import {
  AVERY_LABEL_FORMATS,
  DEFAULT_LABEL_FORMAT_KEY,
  generateAddressLabelPdf,
} from './addressLabelService';

describe('defaultLabelOptions', () => {
  it('is the shipped format with sensible per-run defaults', () => {
    expect(defaultLabelOptions()).toEqual({
      format: DEFAULT_LABEL_FORMAT_KEY,
      sortOrder: DEFAULT_LABEL_SORT_ORDER,
      fontSize: DEFAULT_LABEL_FONT_SIZE,
      alignment: DEFAULT_LABEL_ALIGNMENT,
      showBorder: false,
      showCountry: true,
      startPosition: 0,
    });
  });
});

describe('isValidFormatKey', () => {
  it('accepts a shipped Avery format key', () => {
    expect(isValidFormatKey(AVERY_LABEL_FORMATS[0].key)).toBe(true);
  });

  it('rejects an unknown key or a non-string', () => {
    expect(isValidFormatKey('NOPE')).toBe(false);
    expect(isValidFormatKey(undefined)).toBe(false);
    expect(isValidFormatKey(123)).toBe(false);
  });
});

describe('normalizeLabelOptions', () => {
  it('returns the full defaults for empty/null input', () => {
    expect(normalizeLabelOptions()).toEqual(defaultLabelOptions());
    expect(normalizeLabelOptions(null)).toEqual(defaultLabelOptions());
    expect(normalizeLabelOptions({})).toEqual(defaultLabelOptions());
  });

  it('falls back an unknown format to the shipped default', () => {
    expect(normalizeLabelOptions({ format: 'UNKNOWN_FORMAT' }).format).toBe(
      DEFAULT_LABEL_FORMAT_KEY,
    );
  });

  it('keeps a valid format key', () => {
    const key = AVERY_LABEL_FORMATS[1].key;
    expect(normalizeLabelOptions({ format: key }).format).toBe(key);
  });

  it('clamps the font size to the service 8–12pt band', () => {
    expect(normalizeLabelOptions({ fontSize: 2 }).fontSize).toBe(MIN_FONT_SIZE);
    expect(normalizeLabelOptions({ fontSize: 99 }).fontSize).toBe(MAX_FONT_SIZE);
    expect(normalizeLabelOptions({ fontSize: 11 }).fontSize).toBe(11);
    // Non-finite falls back to the default.
    expect(normalizeLabelOptions({ fontSize: NaN }).fontSize).toBe(DEFAULT_LABEL_FONT_SIZE);
  });

  it('coerces an unknown alignment / sort order to the default', () => {
    expect(normalizeLabelOptions({ alignment: 'diagonal' as never }).alignment).toBe(
      DEFAULT_LABEL_ALIGNMENT,
    );
    expect(normalizeLabelOptions({ sortOrder: 'random' as never }).sortOrder).toBe(
      DEFAULT_LABEL_SORT_ORDER,
    );
  });

  it('keeps valid alignment / sort order values', () => {
    expect(normalizeLabelOptions({ alignment: 'right' }).alignment).toBe('right');
    expect(normalizeLabelOptions({ sortOrder: 'postcode' }).sortOrder).toBe('postcode');
  });

  it('floors a fractional start and rejects a negative start', () => {
    expect(normalizeLabelOptions({ startPosition: 3.9 }).startPosition).toBe(3);
    expect(normalizeLabelOptions({ startPosition: -5 }).startPosition).toBe(0);
  });

  it('coerces boolean-ish defaults safely', () => {
    const o = normalizeLabelOptions({
      showBorder: undefined as never,
      showCountry: undefined as never,
    });
    expect(o.showBorder).toBe(false);
    expect(o.showCountry).toBe(true);
  });
});

describe('toStyleOptions / resolveLabelFormat feed the existing generator', () => {
  it('projects onto the generator LabelStyleOptions shape', () => {
    const options: LabelOptions = {
      format: AVERY_LABEL_FORMATS[0].key,
      sortOrder: 'postcode',
      fontSize: 11,
      alignment: 'center',
      showBorder: true,
      showCountry: false,
      startPosition: 4,
    };
    expect(toStyleOptions(options)).toEqual({
      fontSize: 11,
      alignment: 'center',
      showBorder: true,
      showCountry: false,
      startPosition: 4,
      sortOrder: 'postcode',
    });
  });

  it('resolves the format key to a shipped LabelFormat, defaulting unknown keys', () => {
    const good = resolveLabelFormat({ ...defaultLabelOptions(), format: AVERY_LABEL_FORMATS[2].key });
    expect(good.key).toBe(AVERY_LABEL_FORMATS[2].key);

    const bad = resolveLabelFormat({ ...defaultLabelOptions(), format: 'MISSING' });
    expect(bad.key).toBe(AVERY_LABEL_FORMATS[0].key);
  });

  it('drives generateAddressLabelPdf end-to-end (no parallel shape)', () => {
    const options = defaultLabelOptions();
    const result = generateAddressLabelPdf(
      [],
      undefined,
      resolveLabelFormat(options),
      toStyleOptions(options),
    );
    // Empty input → a valid doc with zero labels; proves the shared model's
    // output is exactly what the existing generator consumes.
    expect(result.labelCount).toBe(0);
    expect(result.doc).toBeTruthy();
  });
});

describe('toStored / fromStored (design §2.1 snake_case persisted block)', () => {
  it('serializes to the exact stored vocabulary', () => {
    const options: LabelOptions = {
      format: AVERY_LABEL_FORMATS[1].key,
      sortOrder: 'region',
      fontSize: 9,
      alignment: 'right',
      showBorder: true,
      showCountry: false,
      startPosition: 2,
    };
    const stored: StoredLabelOptions = toStored(options);
    expect(stored).toEqual({
      format: AVERY_LABEL_FORMATS[1].key,
      sort: 'region',
      font_size: 9,
      alignment: 'right',
      border: true,
      country: false,
      start: 2,
    });
  });

  it('round-trips model → stored → model losslessly', () => {
    const options: LabelOptions = {
      format: AVERY_LABEL_FORMATS[3].key,
      sortOrder: 'postcode',
      fontSize: 12,
      alignment: 'center',
      showBorder: false,
      showCountry: true,
      startPosition: 7,
    };
    expect(fromStored(toStored(options))).toEqual(options);
  });

  it('loads a legacy/absent block as the full defaults', () => {
    expect(fromStored(null)).toEqual(defaultLabelOptions());
    expect(fromStored(undefined)).toEqual(defaultLabelOptions());
    expect(fromStored({})).toEqual(defaultLabelOptions());
  });

  it('normalizes a partial / stale stored block on load', () => {
    const loaded = fromStored({ format: 'STALE_KEY', font_size: 42, sort: 'name' });
    expect(loaded.format).toBe(DEFAULT_LABEL_FORMAT_KEY);
    expect(loaded.fontSize).toBe(MAX_FONT_SIZE);
    expect(loaded.sortOrder).toBe('name');
  });

  it('normalizes an out-of-band stored block (toStored clamps too)', () => {
    const stored = toStored({
      ...defaultLabelOptions(),
      fontSize: 100,
      startPosition: -3,
    });
    expect(stored.font_size).toBe(MAX_FONT_SIZE);
    expect(stored.start).toBe(0);
  });
});

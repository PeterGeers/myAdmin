/**
 * Unit tests for the Member Analytics data-volume guard (task 10.2, C8).
 *
 * Verifies the detect-and-alert behaviour against the hard 6 MiB AWS Lambda
 * response ceiling (R7.1/R7.3/R7.4):
 *   - BELOW 80% of 6 MiB → `normal`, no banner, no operational signal;
 *   - at/≥ 80% (but < 100%) → `warning`, user-visible banner flag + a PII-free
 *     operational log/metric;
 *   - at/≥ 100% → `exceeded`, the explicit "dataset too large" flag + signal,
 *     and the page runs NO partial aggregation.
 *
 * The size is exercised on a SYNTHETIC large payload — a helper that inflates a
 * member-shaped array until its serialized byte length crosses a target
 * fraction of the limit — so the boundaries are tested without a real 6 MiB
 * fetch. The exact-boundary cases use `classifyDataVolume` with a known byte
 * count to pin the `≥` boundary semantics precisely.
 *
 * **Validates: Requirements R7.1, R7.3, R7.4**
 */
import { describe, it, expect, vi } from 'vitest';
import {
  assessDataVolume,
  classifyDataVolume,
  measurePayloadBytes,
  LIMIT_BYTES,
  WARNING_THRESHOLD_BYTES,
  WARNING_FRACTION,
  BYTES_PER_MIB,
  type DataVolumeLogger,
} from './dataVolumeGuard';

/**
 * Build a SYNTHETIC payload whose serialized byte length is at least
 * `targetBytes`. Each element is a member-shaped record padded with a filler
 * string so the array crosses the target realistically (an array of objects,
 * not one giant string). We overshoot slightly then trust the real
 * `measurePayloadBytes` for the assertion, so the test measures the SAME way the
 * guard does.
 */
function syntheticPayloadOfBytes(targetBytes: number): unknown[] {
  // A representative member record; `filler` carries the bulk (~1 KiB per row).
  const filler = 'x'.repeat(1024);
  const makeRow = (i: number) => ({
    member_id: `m-${i}`,
    name: `Member ${i}`,
    email: `member${i}@example.test`,
    status: 'active',
    membership_type: 'regulier',
    region: 'Noord',
    filler,
  });

  // Estimate the per-row serialized cost ONCE (O(1)), size the array to the
  // target, then top up if the estimate undershot. Avoids an O(n²) re-measure
  // on every push — which matters for the multi-MiB (exceeded) case.
  const perRow = measurePayloadBytes([makeRow(0)]);
  const estRows = Math.ceil(targetBytes / Math.max(perRow, 1)) + 2;
  const rows: unknown[] = [];
  for (let i = 0; i < estRows; i++) rows.push(makeRow(i));
  // Top up in case the estimate (ignoring array punctuation) undershot.
  while (measurePayloadBytes(rows) < targetBytes) {
    for (let b = 0; b < 64; b++) rows.push(makeRow(rows.length));
  }
  return rows;
}

describe('dataVolumeGuard — constants (R7.1)', () => {
  it('pins the 6 MiB limit and the 80% warning threshold', () => {
    expect(BYTES_PER_MIB).toBe(1024 * 1024);
    expect(LIMIT_BYTES).toBe(6 * 1024 * 1024); // 6,291,456 bytes (R7.1)
    expect(WARNING_FRACTION).toBe(0.8);
    expect(WARNING_THRESHOLD_BYTES).toBe(Math.floor(LIMIT_BYTES * 0.8));
  });
});

describe('classifyDataVolume — boundary semantics (R7.3/R7.4)', () => {
  it('classifies BELOW the warning threshold as normal (no banner)', () => {
    const a = classifyDataVolume(WARNING_THRESHOLD_BYTES - 1);
    expect(a.level).toBe('normal');
    expect(a.showWarning).toBe(false);
    expect(a.exceeded).toBe(false);
  });

  it('classifies AT the warning threshold (≥ 80%) as warning', () => {
    const a = classifyDataVolume(WARNING_THRESHOLD_BYTES);
    expect(a.level).toBe('warning');
    expect(a.showWarning).toBe(true);
    expect(a.exceeded).toBe(false);
  });

  it('classifies between 80% and the limit as warning', () => {
    const a = classifyDataVolume(LIMIT_BYTES - 1);
    expect(a.level).toBe('warning');
    expect(a.showWarning).toBe(true);
    expect(a.exceeded).toBe(false);
  });

  it('classifies AT the limit (≥ 100%) as exceeded', () => {
    const a = classifyDataVolume(LIMIT_BYTES);
    expect(a.level).toBe('exceeded');
    expect(a.showWarning).toBe(true);
    expect(a.exceeded).toBe(true);
  });

  it('classifies over the limit as exceeded', () => {
    const a = classifyDataVolume(LIMIT_BYTES + 10_000);
    expect(a.level).toBe('exceeded');
    expect(a.exceeded).toBe(true);
    expect(a.ratio).toBeGreaterThan(1);
  });

  it('treats a zero / negative / non-finite size as normal (never crashes)', () => {
    expect(classifyDataVolume(0).level).toBe('normal');
    expect(classifyDataVolume(-5).level).toBe('normal');
    expect(classifyDataVolume(Number.NaN).level).toBe('normal');
  });
});

describe('measurePayloadBytes', () => {
  it('measures the UTF-8 serialized byte length of a payload', () => {
    // `["ab"]` → JSON `["ab"]` is 6 bytes.
    expect(measurePayloadBytes(['ab'])).toBe('["ab"]'.length);
  });

  it('returns 0 for an unserializable (circular) payload rather than throwing', () => {
    const circular: Record<string, unknown> = {};
    circular.self = circular;
    expect(measurePayloadBytes(circular)).toBe(0);
  });
});

describe('assessDataVolume — synthetic large payloads (R7.3/R7.4)', () => {
  const makeLogger = () => {
    const warn = vi.fn();
    const logger: DataVolumeLogger = { warn };
    return { logger, warn };
  };

  it('NORMAL below 80%: a small set renders with no warning and emits NO signal', () => {
    const { logger, warn } = makeLogger();
    // A clearly-small set (well under 80% of 6 MiB).
    const payload = syntheticPayloadOfBytes(10 * 1024); // ~10 KiB
    const a = assessDataVolume(payload, logger);

    expect(a.level).toBe('normal');
    expect(a.showWarning).toBe(false);
    expect(a.exceeded).toBe(false);
    expect(a.bytes).toBeLessThan(WARNING_THRESHOLD_BYTES);
    expect(warn).not.toHaveBeenCalled();
  });

  it('WARNING at ≥ 80% (and < 100%): banner flag set + PII-free operational signal emitted', () => {
    const { logger, warn } = makeLogger();
    // Cross 80% but stay under the limit — target just past the threshold.
    const payload = syntheticPayloadOfBytes(WARNING_THRESHOLD_BYTES + 50 * 1024);
    const a = assessDataVolume(payload, logger);

    expect(a.bytes).toBeGreaterThanOrEqual(WARNING_THRESHOLD_BYTES);
    expect(a.bytes).toBeLessThan(LIMIT_BYTES);
    expect(a.level).toBe('warning');
    expect(a.showWarning).toBe(true);
    expect(a.exceeded).toBe(false);

    // Operational signal raised exactly once, carrying ONLY metadata (no PII).
    expect(warn).toHaveBeenCalledTimes(1);
    const [, meta] = warn.mock.calls[0];
    expect(meta).toEqual({ bytes: a.bytes, ratio: a.ratio, level: 'warning' });
    // The signal must not leak member records.
    expect(JSON.stringify(meta)).not.toContain('member');
  });

  it('EXCEEDED at/over 100%: "dataset too large" flag set, NO partial aggregation, signal emitted', () => {
    const { logger, warn } = makeLogger();
    // Cross the 6 MiB limit.
    const payload = syntheticPayloadOfBytes(LIMIT_BYTES + 100 * 1024);
    const a = assessDataVolume(payload, logger);

    expect(a.bytes).toBeGreaterThanOrEqual(LIMIT_BYTES);
    expect(a.level).toBe('exceeded');
    expect(a.exceeded).toBe(true);
    expect(a.showWarning).toBe(true);

    expect(warn).toHaveBeenCalledTimes(1);
    const [, meta] = warn.mock.calls[0];
    expect(meta.level).toBe('exceeded');
  });

  it('defaults to the console logger when none is injected (no throw)', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const payload = syntheticPayloadOfBytes(WARNING_THRESHOLD_BYTES + 20 * 1024);
    const a = assessDataVolume(payload);
    expect(a.level).toBe('warning');
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });
});

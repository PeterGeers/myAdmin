/**
 * dataVolumeGuard — the Member Analytics data-volume guard (C8, R7.1/R7.3/R7.4).
 *
 * Option 2 (client-side aggregation) is viable only while the scope-authorized
 * `GET /members` set serializes comfortably within the **AWS Lambda synchronous
 * invocation response limit of 6 MiB** (6,291,456 bytes) — a hard AWS limit that
 * cannot be raised by configuration (R7.1). This module turns that ceiling into a
 * detect-and-alert gate so analytics never computes over a silently-truncated set.
 *
 * The guard is deliberately a PURE function over a payload:
 *   - it measures the **serialized JSON byte length** of the member set the page
 *     holds (`GET /members`'s response, the same bytes the aggregation runs over);
 *   - it classifies that size against two clearly-defined constants:
 *       • `WARNING_THRESHOLD_BYTES` = 80% of 6 MiB → a user-visible WARNING banner
 *         + an operational log/metric, but analytics STILL renders (R7.3);
 *       • `LIMIT_BYTES` = 6 MiB → the explicit "dataset too large" state; NO
 *         partial aggregation is run (R7.4).
 *   - at/over the warning threshold it emits an operational signal via a logging
 *     seam (`console.warn` by default, injectable for tests / a future metric
 *     sink). The signal carries **only** the byte size + ratio — NEVER member PII
 *     (R8.3).
 *
 * Byte length is measured with `TextEncoder` (UTF-8) when available — the exact
 * wire byte count — falling back to a conservative char-count estimate only in
 * an environment without `TextEncoder`.
 *
 * @module components/members/analytics/dataVolumeGuard
 * @see .kiro/specs/Members/member-analytics (design C8; requirements R7.1, R7.3, R7.4, R8.3)
 */

/** One mebibyte in bytes. */
export const BYTES_PER_MIB = 1024 * 1024;

/**
 * The hard AWS Lambda synchronous-invocation response limit (R7.1): 6 MiB =
 * 6,291,456 bytes. `GET /members` cannot return more than this; a set that
 * serializes at/over it is (or would be) truncated, so analytics must refuse to
 * aggregate over it.
 */
export const LIMIT_BYTES = 6 * BYTES_PER_MIB; // 6,291,456

/**
 * The warning fraction of the limit (R7.3, "default ~80% of 6 MiB"). Kept as a
 * named constant so the threshold is clearly defined and easy to tune.
 */
export const WARNING_FRACTION = 0.8;

/**
 * The warning threshold in bytes: ≥ this (but < the limit) raises the user-visible
 * warning banner + the operational signal, while analytics still renders (R7.3).
 */
export const WARNING_THRESHOLD_BYTES = Math.floor(LIMIT_BYTES * WARNING_FRACTION); // 5,033,164

/** The three distinct data-volume levels (R7.3/R7.4). */
export type DataVolumeLevel = 'normal' | 'warning' | 'exceeded';

/** The result of measuring + classifying a payload against the 6 MiB ceiling. */
export interface DataVolumeAssessment {
  /** The measured serialized byte length of the payload. */
  bytes: number;
  /** `bytes / LIMIT_BYTES` — the fraction of the 6 MiB limit consumed. */
  ratio: number;
  /** The classified level: normal (< 80%), warning (≥ 80%, < 100%), exceeded (≥ 100%). */
  level: DataVolumeLevel;
  /** Convenience: whether a user-visible warning banner should show (warning OR exceeded). */
  showWarning: boolean;
  /** Convenience: whether the explicit "dataset too large" state applies — NO aggregation (exceeded). */
  exceeded: boolean;
}

/**
 * A minimal operational-logging seam so the warning/exceeded signal (R7.3) can be
 * routed to `console.warn` (default) or a metric sink in production / a spy in
 * tests. The payload is metadata ONLY — byte size + ratio + level — never PII (R8.3).
 */
export interface DataVolumeLogger {
  warn: (message: string, meta: { bytes: number; ratio: number; level: DataVolumeLevel }) => void;
}

/** The default logger: `console.warn` with a structured, PII-free metadata object. */
export const consoleDataVolumeLogger: DataVolumeLogger = {
  warn: (message, meta) => {
    // eslint-disable-next-line no-console
    console.warn(message, meta);
  },
};

/**
 * Measure the serialized byte length of a payload (the `GET /members` response /
 * the member set the page holds).
 *
 * Serializes with `JSON.stringify` and measures the UTF-8 byte length with
 * `TextEncoder` (the exact wire byte count). Falls back to the string length only
 * when `TextEncoder` is unavailable. A payload that cannot be serialized
 * (circular ref, etc.) is treated as 0 bytes rather than throwing — the guard must
 * never crash the page (R1.4).
 *
 * @param payload - Any JSON-serializable value (typically the `Member[]` set).
 * @returns The serialized byte length (≥ 0).
 */
export function measurePayloadBytes(payload: unknown): number {
  let serialized: string;
  try {
    serialized = JSON.stringify(payload) ?? '';
  } catch {
    return 0;
  }
  if (typeof TextEncoder !== 'undefined') {
    return new TextEncoder().encode(serialized).length;
  }
  // Conservative fallback (no TextEncoder): UTF-16 code-unit count. Good enough to
  // classify; the real measurement path uses TextEncoder.
  return serialized.length;
}

/**
 * Classify an already-known byte size against the 6 MiB ceiling (R7.3/R7.4).
 *
 * Useful when the size is known from a `Content-Length` header without
 * re-serializing. Boundaries: `≥ WARNING_THRESHOLD_BYTES` → at least `warning`;
 * `≥ LIMIT_BYTES` → `exceeded`.
 *
 * @param bytes - The serialized byte length to classify.
 * @returns The full assessment (level + ratio + convenience flags).
 */
export function classifyDataVolume(bytes: number): DataVolumeAssessment {
  const safeBytes = Number.isFinite(bytes) && bytes > 0 ? bytes : 0;
  const ratio = safeBytes / LIMIT_BYTES;

  let level: DataVolumeLevel = 'normal';
  if (safeBytes >= LIMIT_BYTES) {
    level = 'exceeded';
  } else if (safeBytes >= WARNING_THRESHOLD_BYTES) {
    level = 'warning';
  }

  return {
    bytes: safeBytes,
    ratio,
    level,
    showWarning: level !== 'normal',
    exceeded: level === 'exceeded',
  };
}

/**
 * The guard: measure a payload's serialized byte length, classify it against the
 * 6 MiB ceiling, and emit an operational signal at the warning/exceeded levels.
 *
 * This is the single entry point the analytics page calls on the member set it
 * holds. It returns the assessment so the page can render the warning banner
 * (R7.3) or the explicit "dataset too large" state with no aggregation (R7.4),
 * and — as a side effect at warning/exceeded — logs a PII-free operational signal
 * through the injectable logger (R7.3 / R8.3).
 *
 * @param payload - The member set (or any serializable payload) to guard.
 * @param logger  - The operational-logging seam (defaults to `console.warn`).
 * @returns The data-volume assessment.
 */
export function assessDataVolume(
  payload: unknown,
  logger: DataVolumeLogger = consoleDataVolumeLogger,
): DataVolumeAssessment {
  const assessment = classifyDataVolume(measurePayloadBytes(payload));

  if (assessment.level !== 'normal') {
    const message =
      assessment.level === 'exceeded'
        ? 'member-analytics: GET /members response at/over the 6 MiB limit — dataset too large, aggregation skipped'
        : 'member-analytics: GET /members response ≥ 80% of the 6 MiB limit — results may be incomplete';
    // Metadata only — byte size + ratio + level. NEVER the member records (R8.3).
    logger.warn(message, {
      bytes: assessment.bytes,
      ratio: assessment.ratio,
      level: assessment.level,
    });
  }

  return assessment;
}

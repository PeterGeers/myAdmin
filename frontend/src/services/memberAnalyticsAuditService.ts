/**
 * memberAnalyticsAuditService — client audit signal for client-side analytics
 * outputs (member-analytics task 10.1, Design C7).
 *
 * The CSV export (`csvExport.ts`) and PDF address-label generate (jsPDF) happen
 * entirely in the browser, so there is no server round-trip to audit them. C7
 * requires every output to be audit-logged, so after a successful client-side
 * export/generate the caller fires a small, **metadata-only** POST to
 * `POST /api/members/analytics-audit`. The backend resolves the tenant from the
 * verified auth context (R8.2), sanitizes the filter summary, and writes the C7
 * record (`{ actor, timestamp, tenant, set_key, filter_summary, record_count,
 * output_kind }`) through the platform's structured audit log. The SES mail send
 * is audited server-side inside its own route — it does NOT use this service.
 *
 * Privacy (R8.3): send metadata ONLY — never member rows, names, emails, or
 * addresses. `recordCount` is a count; `filterSummary` is an optional shape
 * descriptor that the backend sanitizes again before logging.
 *
 * Fire-and-forget: auditing must never block or fail a user's export. This
 * resolves to a boolean and swallows errors (logging a warning), so a failed
 * audit never surfaces to the user or interrupts the download.
 *
 * @module services/memberAnalyticsAuditService
 * @see .kiro/specs/Members/member-analytics (design C7; requirements R8.1, R8.3)
 */

import { authenticatedPost, buildEndpoint } from './apiService';

/** The client-side output kinds this signal covers (the SES send audits itself). */
export type ClientAnalyticsOutputKind = 'csv_export' | 'pdf_labels';

/** The metadata-only payload for an analytics output audit (NO PII). */
export interface AnalyticsOutputAudit {
  /** Which client-side output this records. */
  outputKind: ClientAnalyticsOutputKind;
  /** Optional audit label for the set that produced the output (metadata only). */
  setKey?: string;
  /** How many records the output covered (count only). */
  recordCount?: number;
  /**
   * Optional PII-free shape descriptor of the filter in force. The backend
   * sanitizes this again (dropping any PII-looking keys) before logging, so this
   * is best-effort metadata, never member values.
   */
  filterSummary?: Record<string, unknown>;
}

/**
 * Record a client-side analytics output (CSV export / PDF labels) in the audit
 * log. Fire-and-forget: resolves `true` on a logged record, `false` on any
 * failure (never throws, never blocks the export).
 */
export async function recordAnalyticsOutput(
  audit: AnalyticsOutputAudit,
): Promise<boolean> {
  try {
    const res = await authenticatedPost(buildEndpoint('/api/members/analytics-audit'), {
      output_kind: audit.outputKind,
      set_key: audit.setKey,
      record_count: audit.recordCount,
      filter_summary: audit.filterSummary,
    });
    return res.ok;
  } catch (error) {
    // Auditing is best-effort — a failure must not interrupt the user's export.
    // eslint-disable-next-line no-console
    console.warn('member analytics audit signal failed', error);
    return false;
  }
}

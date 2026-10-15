/**
 * memberMailHelpers — the PURE, framework-free helpers behind {@link MemberMailCompose}.
 *
 * These are the recipient-parsing, template-seed, and merge-preview transforms the mail compose
 * modal uses. They carry NO React / Chakra / network dependency (only the `MemberTemplateDto`
 * SHAPE), so they live apart from the modal component along a clean cohesion seam and are unit-
 * testable in isolation. `MemberMailCompose.tsx` re-exports every name here VERBATIM, so the
 * public import surface (`./MemberMailCompose` and the `analytics` barrel) is unchanged —
 * `MemberDeliveryEditor` (which imports `isValidEmail` / `parseExternalRecipients`) and the
 * barrel's `resolveTemplateSeed` / `TemplateSeed` re-exports keep resolving.
 *
 * @module components/members/analytics/memberMailHelpers
 */

import type { MemberTemplateDto } from '../../../services/memberTemplateService';

/**
 * A pragmatic client-side email check (R1): one `@`, a non-empty local part, a
 * dotted domain, no whitespace. This is a client-side guard against obvious
 * typos — the backend/SES remains the authority on deliverability. Deliberately
 * simple (RFC 5322 in full is not worth the complexity for a UI guard).
 */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Whether a trimmed token looks like a valid email address (R1). */
export function isValidEmail(address: string): boolean {
  return EMAIL_RE.test(address.trim());
}

/**
 * Split a free-text external-recipients field into individual tokens on comma,
 * semicolon, newline, or any whitespace, dropping blanks. Order is preserved and
 * duplicates are NOT removed here (the caller de-dupes case-insensitively).
 */
export function parseExternalRecipients(raw: string): string[] {
  return raw
    .split(/[\s,;]+/)
    .map((tok) => tok.trim())
    .filter((tok) => tok.length > 0);
}

/** The subject + body a picked template seeds into the (still-editable) compose fields. */
export interface TemplateSeed {
  subject: string;
  body: string;
}

/**
 * Resolve the subject + body a stored template should SEED for the active language (R2).
 *
 * Prefers the active `language`'s variant; falls back to any other language that carries usable
 * text so a template authored in only one language still seeds something. The body is taken from
 * the resolved `body_html` (returned by GET-by-id); when the body text is not available the
 * subject still seeds and the body is left blank for the user to fill. Returns `null` when the
 * template has no usable language at all (nothing to seed) so the caller leaves the fields as-is.
 */
export function resolveTemplateSeed(
  template: MemberTemplateDto,
  language: string,
): TemplateSeed | null {
  const languages = template.languages ?? {};
  const order = [language, 'nl', 'en', ...Object.keys(languages)];
  const seen = new Set<string>();
  for (const lang of order) {
    if (seen.has(lang)) {
      continue;
    }
    seen.add(lang);
    const variant = languages[lang];
    if (!variant) {
      continue;
    }
    const subject = (variant.subject ?? '').trim();
    const body = (variant.body_html ?? '').trim();
    if (subject || body) {
      return { subject: variant.subject ?? '', body: variant.body_html ?? '' };
    }
  }
  return null;
}

/**
 * Flatten a result row into a `{ key: string }` merge map, mirroring the SAM worker's
 * `_flatten_merge_values`: top-level scalar keys plus one level of nested-mapping leaves (both
 * the dotted `group.key` AND the bare leaf `key`), so a template placeholder resolves the same
 * way whether it references `last_name` or `personal.last_name`.
 */
export function flattenRowMergeValues(
  row: Record<string, unknown> | undefined | null,
): Record<string, string> {
  const out: Record<string, string> = {};
  if (!row) {
    return out;
  }
  for (const [key, value] of Object.entries(row)) {
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      for (const [subKey, subValue] of Object.entries(value as Record<string, unknown>)) {
        if (subValue === null || (typeof subValue === 'object' && !Array.isArray(subValue))) {
          continue;
        }
        out[`${key}.${subKey}`] = String(subValue);
        if (!(subKey in out)) {
          out[subKey] = String(subValue);
        }
      }
    } else if (value !== null && value !== undefined) {
      out[key] = String(value);
    }
  }
  return out;
}

/**
 * Substitute `{{ key }}` placeholders in `text` from `values` (missing/blank -> empty string),
 * mirroring the backend `render_with_merge` grammar (`{{ field_key }}`, optional inner spaces).
 * Pure; used ONLY for the compose preview (the authoritative merge happens on-plane at send).
 */
export function renderMergePreview(
  text: string,
  values: Record<string, string>,
): string {
  return (text ?? '').replace(/\{\{\s*([A-Za-z0-9_.]+)\s*\}\}/g, (_m, key: string) => {
    const v = values[key];
    return v === undefined || v === null ? '' : v;
  });
}
